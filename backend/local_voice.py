"""Asynchronous original Mandarin playback for locally indexed games."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media_tools import ffmpeg_executable
from .game_assets import asset_adapter


class LocalVoiceAssetService:
    def __init__(self, game: str, data_dir: Path, decoder: Path, output_dir: Path):
        self._adapter, self._extractor = asset_adapter(game)
        self.game, self.data_dir, self.decoder, self.output_dir = game, data_dir, decoder, output_dir
        self.ready = False
        self.last_error = None
        self._entries = {}
        self._install = None
        self._fingerprint = ""
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{game}-voice")
        self._slots = threading.BoundedSemaphore(8)
        self.reload()

    def reload(self) -> bool:
        try:
            payload = json.loads((self.data_dir / "textmap.json").read_text(encoding="utf-8"))
            with self._lock:
                self._entries = {r["text_id"]: r["audio"] for r in payload["records"] if r.get("audio")}
                self._install = Path(payload["install"])
                self._fingerprint = payload["fingerprint"]
                self.ready = bool(self._entries and self._install.is_dir() and self.decoder.is_file() and ffmpeg_executable())
                self.last_error = None
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.ready, self.last_error = False, str(error)
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
        identity = hashlib.sha256(f"{stamp}\0{text_id}".encode()).hexdigest()[:16]
        filename = f"official-{self.game}-{line_id}-{identity}.mp3"
        output = self.output_dir / filename
        with tempfile.TemporaryDirectory(prefix=f"{self.game}-voice-", dir=self.output_dir) as scratch_value:
            scratch = Path(scratch_value)
            data = extract_voice(install, audio, self.data_dir / "tools" / self._extractor, scratch)
            wem, wav, mp3 = scratch / "voice.wem", scratch / "voice.wav", scratch / "voice.mp3"
            wem.write_bytes(data)
            options = {"check": True, "capture_output": True, "timeout": 90,
                       "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            subprocess.run([str(self.decoder), "-o", str(wav), str(wem)], **options)
            subprocess.run([str(ffmpeg_executable()), "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)], **options)
            if mp3.stat().st_size < 100:
                raise ValueError("Original voice decoded to an empty clip")
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

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
