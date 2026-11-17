"""Decode materialized ZZZ originals using the verified bundled codec closure."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

from .game_data_protocol import GameDataError
from .native_codecs import packaged_codec_executable
from .private_data_paths import MAX_AUDIO
from .runtime_bundle import discover_layout
from .zzz_game_data import _safe


def available_codecs(*, layout=None):
    layout = layout or discover_layout()
    if layout.mode != 'bundle':return None
    if not all(packaged_codec_executable(tool, layout=layout) for tool in ('vgmstream', 'ffmpeg')):
        return None
    return OwnedCodecs(layout)


class OwnedCodecs:
    def __init__(self, layout):
        self.layout = layout
        values = {name: digest for name, digest in layout.resources.items() if name.startswith('codecs/audio/')}
        self.identity = 'zzz-owned-audio-' + hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def _run(self, tool, arguments, work, cancelled):
        executable = packaged_codec_executable(tool, layout=self.layout)
        if executable is None:
            raise GameDataError('zzz_audio_runtime_missing', 'The verified original-audio decoder is unavailable. Repair the app runtime.', 409)
        if cancelled():raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
        process = subprocess.Popen([str(executable), *map(str, arguments)], cwd=work,
            env=self.layout.child_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = time.monotonic()
        try:
            while True:
                if cancelled():raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
                if time.monotonic() - started > 120:
                    raise GameDataError('zzz_audio_decode_timeout', 'This original recording took too long to decode. Retry.', 409)
                try:
                    process.communicate(timeout=.25)
                    break
                except subprocess.TimeoutExpired:pass
            if process.returncode:
                raise GameDataError('zzz_audio_decode_failed', 'This original recording could not be decoded. Previous recordings are kept.', 409)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.communicate(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)

    def resolve(self, raw, audio, destination, *, cancelled):
        from .local_voice import _audio_options
        if (not isinstance(raw, bytes) or not 12 <= len(raw) <= 64 * 1024**2
                or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE' or int.from_bytes(raw[4:8], 'little') + 8 != len(raw)):
            raise GameDataError('zzz_original_audio_bounds', 'The complete original recording is unavailable.', 409)
        destination = _safe(Path(destination).absolute()).with_suffix('.mp3')
        _safe(destination.parent).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zzz-original-', dir=destination.parent) as name:
            work = Path(name)
            source, wav, mp3 = work / 'original.wem', work / 'original.wav', work / 'original.mp3'
            if cancelled():raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
            source.write_bytes(raw)
            self._run('vgmstream', ['-i', '-o', wav, source], work, cancelled)
            if not wav.is_file() or not 44 < wav.stat().st_size <= MAX_AUDIO:
                raise GameDataError('zzz_audio_decode_bounds', 'This original recording exceeds the supported local decode size.', 409)
            trim = _audio_options(audio, wav)
            self._run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-nostdin', '-i', wav, *trim,
                '-map_metadata', '-1', '-vn', '-ar', '48000', '-ac', '2', '-codec:a', 'libmp3lame', '-q:a', '2', mp3], work, cancelled)
            if not mp3.is_file() or not 100 <= mp3.stat().st_size <= MAX_AUDIO:
                raise GameDataError('zzz_audio_decode_bounds', 'The decoded original recording is empty or exceeds its supported size.', 409)
            if cancelled():raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
            _safe(destination);mp3.replace(destination)
        return destination
