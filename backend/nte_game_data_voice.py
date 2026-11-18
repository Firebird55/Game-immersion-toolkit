"""Offline original-WEM bindings and explicitly inventoried Windows decoding."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from collections.abc import Mapping

from .game_data_protocol import GameDataError
from .private_data_paths import _no_links

MAX_WEM = 512*1024**2
DUBS = {'en': 'English', 'ja': 'Japanese', 'ko': 'Korean', 'zh-Hans': 'Chinese', 'zh-Hant': 'Chinese'}


def failure():
    return GameDataError('nte_original_audio_invalid',
        'The downloaded NTE recording could not be verified. Download or repair this game; saved history is retained.', 409)


def identity(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def binding(row):
    from .local_game import dialogue_audio_scope
    value = {key: row.get(key) for key in ('text_id', 'audio', 'player_voice',
        'audio_locale', 'source_locale', 'voice_status')}
    value['audio_scope'] = dialogue_audio_scope(row.get('audio'), row.get('audio_scope', 'line'))
    return identity(value)


def check_wem(raw):
    if (not isinstance(raw, bytes) or not 12 <= len(raw) <= MAX_WEM or raw[:4] != b'RIFF'
            or raw[8:12] != b'WAVE' or int.from_bytes(raw[4:8], 'little')+8 != len(raw)):
        raise failure()


def codecs(layout):
    """No source-tool/PATH fallback; the whole existing bundle is required."""
    from .native_codecs import packaged_codec_executable, PREFIX
    try:
        values = {tool: packaged_codec_executable(tool, layout=layout) for tool in ('vgmstream', 'ffmpeg')}
        if not all(values.values()): raise ValueError('Missing inventoried voice decoder')
        packet = layout.resource(PREFIX+'runtime.json').read_bytes()
        proof = {'schema': 'nte-inventoried-audio-codecs-v1', 'manifest_sha256': hashlib.sha256(packet).hexdigest(),
            'executables': {name: layout.resources[PREFIX+path.name] for name, path in values.items()}}
        return values, proof
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        raise GameDataError('nte_audio_runtime_unavailable',
            'This application needs its compatible original-voice decoder before preparing NTE audio. Text-only remains available.', 409) from error


class OriginalVoiceSource:
    def __init__(self, ctx, payload, originals, codec_identity, layout):
        self.context, self.originals, self.codec_identity, self.layout = ctx, originals, codec_identity, layout
        self.bindings = {binding(row) for row in payload['records'] if row.get('audio')}

    def _path(self, row):
        if not isinstance(row, Mapping) or not isinstance(row.get('audio'), Mapping) or not row['audio'] or binding(row) not in self.bindings: raise failure()
        item = self.originals.get(row['audio'].get('depot'))
        if not isinstance(item, dict): raise failure()
        path = self.context.directory/'originals'/(item['sha256']+'.wem'); _no_links(path)
        if not path.is_file() or path.stat().st_size != item['bytes']: raise failure()
        with path.open('rb') as stream:
            header = stream.read(12)
            if header[:4] != b'RIFF' or header[8:] != b'WAVE' or int.from_bytes(header[4:8], 'little')+8 != item['bytes']: raise failure()
            stream.seek(0)
            if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']: raise failure()
        return path

    def has(self, row):
        # This predicate performs no codec, archive, native-reader or HTTP work.
        try:
            self._path(row)
            return True
        except (GameDataError, OSError, ValueError, KeyError, TypeError):
            return False

    def resolve(self, row, destination, *, cancelled):
        ctx = self.context; ctx.check()
        if cancelled(): return None
        original = self._path(row)
        tools, proof = codecs(self.layout)
        if proof != self.codec_identity: raise failure()
        destination = Path(destination); _no_links(destination)
        roots = (ctx.directory, self.layout.data_root, self.layout.work_root)
        if (not destination.is_absolute() or destination != destination.resolve() or destination.suffix != '.mp3'
                or not any(destination != root and destination.is_relative_to(root) for root in roots)):
            raise failure()
        destination.parent.mkdir(parents=True, exist_ok=True)
        from .local_voice import _audio_options
        with tempfile.TemporaryDirectory(prefix='nte-offline-voice-', dir=destination.parent) as name:
            scratch = Path(name); wem, wav, mp3 = scratch/'original.wem', scratch/'decoded.wav', scratch/'voice.mp3'
            os.link(original, wem)
            environment = {key: value for key, value in os.environ.items()
                if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR'}}
            environment['PATH'] = str(tools['vgmstream'].parent)
            def run(command):
                if codecs(self.layout)[1] != proof: raise failure()
                process = subprocess.Popen(command, cwd=scratch, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                started = time.monotonic()
                try:
                    while True:
                        ctx.check()
                        if cancelled(): return False
                        if time.monotonic()-started > 90: raise failure()
                        try:
                            process.communicate(timeout=.1)
                            if process.returncode: raise failure()
                            return True
                        except subprocess.TimeoutExpired: pass
                finally:
                    if process.poll() is None: process.kill(); process.wait(timeout=5)
            if not run([str(tools['vgmstream']), '-i', '-o', str(wav), str(wem)]): return None
            options = _audio_options(row['audio'], wav)
            if not run([str(tools['ffmpeg']), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    '-i', str(wav), *options, '-codec:a', 'libmp3lame', '-q:a', '2', '-threads', '1', str(mp3)]): return None
            if not mp3.is_file() or mp3.stat().st_size < 100: raise failure()
            ctx.check()
            if cancelled(): return None
            if self._path(row) != original or codecs(self.layout)[1] != proof: raise failure()
            mp3.replace(destination)
        return destination
