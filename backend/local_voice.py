"""Asynchronous original voice playback for locally indexed game languages."""
from __future__ import annotations

import hashlib
import math
import json
import subprocess
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media_tools import ffmpeg_executable
from .game_assets import asset_adapter


class LocalVoiceAssetService:
    def __init__(self, game: str, data_dir: Path, decoder: Path, output_dir: Path, *, tools_dir: Path | None = None, snapshot_index=None):
        self._adapter, self._extractor = asset_adapter(game)
        self.game, self.data_dir, self.decoder, self.output_dir = game, data_dir, decoder, output_dir
        self.tools_dir = tools_dir or data_dir / 'tools'
        self._snapshot_index = snapshot_index
        self._reload_lock = threading.RLock()
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
        with self._reload_lock:
            return self._reload_snapshot()

    def _reload_snapshot(self) -> bool:
        try:
            path = self.data_dir / "textmap.json"
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size, (self.game in {'beyond', 'heavyrain'} or self.decoder.is_file()), bool(ffmpeg_executable()))
            if self._loaded_signature == signature:
                return self.ready
            payload = (self._snapshot_index.voice_snapshot((stat.st_size, stat.st_mtime_ns))
                       if self._snapshot_index is not None else None)
            if payload is None:
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

    def _validate_sources(self, install, stamp, audios):
        if install is None:
            raise ValueError('Original voice installation is unavailable')
        validate = getattr(self._adapter, 'validate_voice_source', None)
        if validate is not None:
            # Adapters may prove the referenced packages unchanged independently
            # of text, unrelated packs, or game version updates.
            for audio in audios:
                validate(install, audio)
        elif self._adapter.fingerprint(install) != stamp:
            raise ValueError('Game files changed; refresh the original voice index')

    def extract(self, text_id: str, line_id: int, _english=None) -> str:
        with self._lock:
            audio, install, stamp = dict(self._entries[text_id]), self._install, self._fingerprint
        extract_voice = self._adapter.extract_voice
        self._validate_sources(install, stamp, [audio])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(f"{stamp}\0{self.locale}\0{text_id}".encode()).hexdigest()[:16]
        filename = f"official-{self.game}-{line_id}-{identity}.mp3"
        output = self.output_dir / filename
        with tempfile.TemporaryDirectory(prefix=f"{self.game}-voice-", dir=self.output_dir) as scratch_value:
            scratch = Path(scratch_value)
            data = extract_voice(install, audio, self.tools_dir / self._extractor, scratch)
            wem, wav, mp3 = scratch / "voice.wem", scratch / "voice.wav", scratch / "voice.mp3"
            wem.write_bytes(data)
            options = {"check": True, "capture_output": True, "timeout": 90,
                       "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if self.game in {"beyond", "heavyrain"}:
                wav.write_bytes(data)
            else:
                subprocess.run([str(self.decoder), "-i", "-o", str(wav), str(wem)], **options)
            trim = []
            if 'start_ms' in audio or 'end_ms' in audio:
                start, end = audio.get('start_ms'), audio.get('end_ms')
                with wave.open(str(wav)) as stream:
                    duration_ms = stream.getnframes() / stream.getframerate() * 1000
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= duration_ms + 1:
                    raise ValueError('Original movie voice timing is outside its source; refresh game data')
                trim = ['-ss', str(start/1000), '-t', str((end-start)/1000)]
                gain = audio.get('gain_db', 0)
                if not isinstance(gain, (int, float)) or not math.isfinite(gain) or not -60 <= gain <= 24:
                    raise ValueError('Invalid original movie voice gain')
                trim += ['-af', f'volume={gain:.6f}dB']
            subprocess.run([str(ffmpeg_executable()), "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(wav), *trim, "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)], **options)
            if mp3.stat().st_size < 100:
                raise ValueError("Original voice decoded to an empty clip")
            self._validate_sources(install, stamp, [audio])
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
        self._validate_sources(install, stamp, audios)
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
                wem = scratch / f'{index}.wem'; wem.write_bytes(data); inputs.append(wem)
            del payloads
            options = {'check': True, 'capture_output': True, 'timeout': 90 * len(requests),
                       'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
            if self.game in {'beyond', 'heavyrain'}:
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
                trim = []
                if 'start_ms' in audio or 'end_ms' in audio:
                    start, end = audio.get('start_ms'), audio.get('end_ms')
                    with wave.open(str(wem) + '.wav') as stream:
                        duration = stream.getnframes() / stream.getframerate() * 1000
                    if type(start) is not int or type(end) is not int or not 0 <= start < end <= duration + 1:
                        raise ValueError('Original movie voice timing is outside its source; refresh game data')
                    gain = audio.get('gain_db', 0)
                    if not isinstance(gain, (int, float)) or not math.isfinite(gain) or not -60 <= gain <= 24:
                        raise ValueError('Invalid original movie voice gain')
                    trim = ['-ss', str(start/1000), '-t', str((end-start)/1000), '-af', f'volume={gain:.6f}dB']
                mp3 = scratch / f'{index}.mp3'; outputs.append(mp3)
                command += ['-map', f'{source_index}:a:0', *trim, '-codec:a', 'libmp3lame', '-q:a', '2', '-threads', '1', str(mp3)]
            subprocess.run(command, **options)
            if any(not p.is_file() or p.stat().st_size < 100 for p in outputs):
                raise ValueError('Original voice batch decoded to an empty clip')
            self._validate_sources(install, stamp, audios)
            for mp3, filename in zip(outputs, filenames):
                mp3.replace(self.output_dir / filename)
        return filenames

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
