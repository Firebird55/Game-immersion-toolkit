"""Asynchronous original voice playback for locally indexed game languages."""
from __future__ import annotations

import hashlib
import math
import json
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media_tools import ffmpeg_executable
from .game_assets import asset_adapter


def _source_suffix(data: bytes, audio=None, game=None) -> str:
    # vgmstream uses both container magic and suffix when selecting its reader.
    # Derive the suffix from extracted bytes, never an arbitrary snapshot path.
    if (audio or {}).get('decoder_format') == 'mul':
        if game != 'riseofthetombraider' or len(data) < 8192 or int.from_bytes(data[:4], 'little') not in {22050, 32000, 44100, 48000}:
            raise ValueError('Invalid original MUL voice container')
        return '.mul'
    return '.fsb' if data[:4] in {b'FSB4', b'FSB5'} else '.wem'


def _audio_options(audio, wav):
    """Apply authored timing and channel gains; never guess a dialogue stem."""
    trim, filters = [], []
    mix = audio.get('channel_mix')
    timed = 'start_ms' in audio or 'end_ms' in audio
    if timed or mix is not None:
        with wave.open(str(wav)) as stream:
            duration_ms = stream.getnframes() / stream.getframerate() * 1000
            channels = stream.getnchannels()
        if timed:
            start, end = audio.get('start_ms'), audio.get('end_ms')
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= duration_ms + 1:
                raise ValueError('Original movie voice timing is outside its source; refresh game data')
            trim = ['-ss', str(start / 1000), '-t', str((end - start) / 1000)]
        if mix is not None:
            if not isinstance(mix, list) or not 1 <= len(mix) == channels <= 12 or any(
                not isinstance(pair, list) or len(pair) != 2 or any(
                    type(gain) not in (int, float) or not math.isfinite(gain) or abs(gain) > 16 for gain in pair)
                for pair in mix):
                raise ValueError('Original voice channel mix does not match its decoded source')
            filters.append('pan=stereo|' + '|'.join(
                f'c{side}=' + '+'.join(f'{pair[side]:.9g}*c{index}' for index, pair in enumerate(mix))
                for side in (0, 1)))
        if timed:
            gain = audio.get('gain_db', 0)
            if type(gain) not in (int, float) or not math.isfinite(gain) or not -60 <= gain <= 24:
                raise ValueError('Invalid original movie voice gain')
            filters.append(f'volume={gain:.6f}dB')
    return trim + (['-af', ','.join(filters)] if filters else [])


class LocalVoiceAssetService:
    def __init__(self, game: str, data_dir: Path, decoder: Path, output_dir: Path, *, tools_dir: Path | None = None):
        self._adapter, self._extractor = asset_adapter(game)
        self.game, self.data_dir, self.decoder, self.output_dir = game, data_dir, decoder, output_dir
        self.tools_dir = tools_dir or data_dir / 'tools'
        self.locale = 'zh-Hans'
        self.ready = False
        self.last_error = None
        self._entries = {}
        self._install = None
        self._fingerprint = ""
        self._loaded_signature = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{game}-voice")
        self._slots = threading.BoundedSemaphore(8)
        self.reload()

    def reload(self) -> bool:
        try:
            path = self.data_dir / "textmap.json"
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size, (self.game in {'beyond', 'heavyrain'} or self.decoder.is_file()), bool(ffmpeg_executable()))
            if self._loaded_signature == signature:
                return self.ready
            payload = json.loads(path.read_text(encoding="utf-8"))
            locale = payload.get('source_locale', 'zh-Hans')
            entries = {r["text_id"]: r["audio"] for r in payload["records"] if r.get("audio")}
            install = Path(payload["install"])
            stamp = payload["fingerprint"]
            ready = bool(entries and install.is_dir() and (self.game in {'beyond', 'heavyrain'} or self.decoder.is_file()) and ffmpeg_executable())
            with self._lock:
                self.locale = locale
                self._entries, self._install, self._fingerprint = entries, install, stamp
                self.ready = ready
                self._loaded_signature = signature
                self.last_error = None
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.last_error = str(error)
        return self.ready

    def status(self) -> dict:
        return {"ready": self.ready, "mapped_lines": len(self._entries), "last_error": self.last_error}

    def has_variant(self, text_id: str, _english=None) -> bool:
        return self.ready and text_id in self._entries

    def extract(self, text_id: str, line_id: int, _english=None) -> str:
        with self._lock:
            audio, install, stamp = dict(self._entries[text_id]), self._install, self._fingerprint
        extract_voice, fingerprint = self._adapter.extract_voice, self._adapter.fingerprint
        if install is None or fingerprint(install) != stamp:
            raise ValueError("Game files changed; refresh the original voice index")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        full_track = audio.get('playback_scope') == 'full_track'
        binding = json.dumps(audio, sort_keys=True, separators=(',', ':')) if full_track else text_id
        identity = hashlib.sha256(f"{stamp}\0{self.locale}\0{binding}".encode()).hexdigest()[:16]
        filename = f"official-{self.game}-{line_id}-{identity}.mp3"
        output = self.output_dir / filename
        if full_track:
            # Independent captions can refer to the same complete performance.
            # Reuse its verified encoding while retaining per-history filenames
            # so deleting one saved line cannot remove another line's audio.
            for cached in self.output_dir.glob(f'official-{self.game}-*-{identity}.mp3'):
                if not cached.is_file() or cached.is_symlink() or cached.stat().st_size < 100:
                    continue
                if cached != output:
                    try:
                        os.link(cached, output)
                    except FileExistsError:
                        pass
                    except OSError:
                        with tempfile.TemporaryDirectory(prefix='voice-copy-', dir=self.output_dir) as folder:
                            copy = Path(folder) / 'voice.mp3'
                            shutil.copyfile(cached, copy)
                            copy.replace(output)
                if fingerprint(install) != stamp:
                    raise ValueError('Game files changed during original voice extraction')
                return filename
        with tempfile.TemporaryDirectory(prefix=f"{self.game}-voice-", dir=self.output_dir) as scratch_value:
            scratch = Path(scratch_value)
            data = extract_voice(install, audio, self.tools_dir / self._extractor, scratch)
            wem, wav, mp3 = scratch / ('voice' + _source_suffix(data, audio, self.game)), scratch / "voice.wav", scratch / "voice.mp3"
            wem.write_bytes(data)
            options = {"check": True, "capture_output": True, "timeout": 90,
                       "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            custom_decode = getattr(self._adapter, 'decode_voice_source', None)
            if custom_decode:
                custom_decode(data, audio, wav, self.decoder, scratch)
            elif self.game in {"beyond", "heavyrain"}:
                wav.write_bytes(data)
            else:
                subprocess.run([str(self.decoder), "-i", "-o", str(wav), str(wem)], **options)
            trim = _audio_options(audio, wav)
            subprocess.run([str(ffmpeg_executable()), "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(wav), *trim, "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)], **options)
            if mp3.stat().st_size < 100:
                raise ValueError("Original voice decoded to an empty clip")
            if fingerprint(install) != stamp:
                raise ValueError("Game files changed during original voice extraction")
            mp3.replace(output)
        return filename

    def schedule(self, text_id: str, line_id: int, callback, english=None) -> bool:
        if not self.has_variant(text_id) or not self._slots.acquire(blocking=False):
            return False
        def work():
            result = None
            try:
                result = self.extract(text_id, line_id, english)
                self.last_error = None
            except Exception as error:
                self.last_error = str(error)
            finally:
                self._slots.release()
            callback(line_id, result, result is not None)
        self._executor.submit(work)
        return True

    def extract_batch(self, requests) -> list[str]:
        if not 1 <= len(requests) <= 8:
            raise ValueError('Voice batches must contain one to eight clips')
        with self._lock:
            audios = [dict(self._entries[text_id]) for text_id, number, english in requests]
            install, stamp = self._install, self._fingerprint
        if any(audio.get('playback_scope') == 'full_track' for audio in audios):
            return [self.extract(text_id, number, english) for text_id, number, english in requests]
        if install is None or self._adapter.fingerprint(install) != stamp:
            raise ValueError('Game files changed; refresh the original voice index')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filenames = [f"official-{self.game}-{number}-{hashlib.sha256(f'{stamp}\0{self.locale}\0{text_id}'.encode()).hexdigest()[:16]}.mp3"
                     for text_id, number, english in requests]
        with tempfile.TemporaryDirectory(prefix=f'{self.game}-batch-', dir=self.output_dir) as value:
            scratch = Path(value)
            extractor = self.tools_dir / self._extractor
            source_ids, originals, indexes = {}, [], []
            for audio in audios:
                source = json.dumps({k: v for k, v in audio.items() if k not in {'start_ms', 'end_ms', 'gain_db'}}, sort_keys=True)
                if source not in source_ids:
                    source_ids[source] = len(originals); originals.append(audio)
                indexes.append(source_ids[source])
            bulk = getattr(self._adapter, 'extract_voices', None)
            if bulk:
                payloads = bulk(install, originals, extractor, scratch)
            else:
                payloads = []
                for index, audio in enumerate(originals):
                    directory = scratch / str(index); directory.mkdir()
                    payloads.append(self._adapter.extract_voice(install, audio, extractor, directory))
            if len(payloads) != len(originals):
                raise ValueError('Original voice extraction returned incomplete bindings')
            inputs = []
            for index, data in enumerate(payloads):
                wem = scratch / f'{index}{_source_suffix(data, originals[index], self.game)}'; wem.write_bytes(data); inputs.append(wem)
            del payloads
            options = {'check': True, 'capture_output': True, 'timeout': 90 * len(requests),
                       'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
            custom_decode = getattr(self._adapter, 'decode_voice_source', None)
            if custom_decode:
                for index, source in enumerate(inputs):
                    decode_scratch = scratch / f'decode-{index}'; decode_scratch.mkdir()
                    custom_decode(source.read_bytes(), originals[index], Path(str(source) + '.wav'), self.decoder, decode_scratch)
            elif self.game in {'beyond', 'heavyrain'}:
                for wem in inputs:
                    Path(str(wem) + '.wav').write_bytes(wem.read_bytes())
            else:
                subprocess.run([str(self.decoder), '-i', *map(str, inputs)], **options)
            command = [str(ffmpeg_executable()), '-hide_banner', '-loglevel', 'error', '-nostdin',
                       '-filter_threads', '1', '-filter_complex_threads', '1']
            for wem in inputs:
                command += ['-i', str(wem) + '.wav']
            outputs = []
            for index, (source_index, audio) in enumerate(zip(indexes, audios)):
                wem = inputs[source_index]
                trim = _audio_options(audio, str(wem) + '.wav')
                mp3 = scratch / f'{index}.mp3'; outputs.append(mp3)
                command += ['-map', f'{source_index}:a:0', *trim, '-codec:a', 'libmp3lame', '-q:a', '2', '-threads', '1', str(mp3)]
            subprocess.run(command, **options)
            if any(not p.is_file() or p.stat().st_size < 100 for p in outputs):
                raise ValueError('Original voice batch decoded to an empty clip')
            if self._adapter.fingerprint(install) != stamp:
                raise ValueError('Game files changed during voice extraction')
            for mp3, filename in zip(outputs, filenames):
                mp3.replace(self.output_dir / filename)
        return filenames

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
