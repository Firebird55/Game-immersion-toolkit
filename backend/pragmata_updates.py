from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .pragmata import PragmataTextIndex
from .pragmata_audio import INDEX_FORMAT, PragmataVoiceAssetService


class PragmataUpdateManager:
    """Refresh PRAGMATA localization in the background when its PAKs change."""

    def __init__(
        self,
        project_root: Path,
        index: PragmataTextIndex,
        voice_assets: PragmataVoiceAssetService,
        on_update: Callable[[dict[str, object]], None] | None = None,
        interval: float = 120,
    ) -> None:
        self.project_root = project_root
        self.index = index
        self.voice_assets = voice_assets
        self.on_update = on_update
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._status: dict[str, object] = {
            "state": "idle",
            "message": "PRAGMATA game files are current",
            "progress": 100,
            "automatic": True,
            "last_error": None,
            "last_checked": None,
        }

    def status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._status)

    def _set(self, **changes: object) -> None:
        with self._lock:
            self._status.update(changes)
            current = dict(self._status)
        if self.on_update:
            self.on_update(current)

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._set(state="checking", message="Checking installed PRAGMATA files", progress=5)
            self._thread = threading.Thread(target=self._loop, name="pragmata-index-update", daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)

    def request_check(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._wake.set()
                return self._status["state"] != "updating"
            self.start()
            return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            self._run()
            self._wake.wait(self.interval)

    def _run(self) -> None:
        try:
            from scripts.index_pragmata_assets import find_install, fingerprint

            path = self.index.path
            install = find_install()
            if install is None:
                self.index.load()
                self.voice_assets.reload()
                self._set(
                    state="waiting",
                    message="Waiting for installed PRAGMATA game files; saved subtitles remain available",
                    progress=100,
                    last_error=None,
                )
                return
            needs_update = not path.is_file()
            if path.is_file():
                payload = json.loads(path.read_text(encoding="utf-8"))
                needs_update = payload.get("format", 0) < INDEX_FORMAT
                needs_update = needs_update or payload.get("install") != str(install)
                needs_update = needs_update or payload.get("fingerprint") != fingerprint(install)
            if not needs_update:
                self.index.load()
                self.voice_assets.reload()
                self._set(state="idle", message="PRAGMATA game files are current", progress=100)
                return
            self._set(state="updating", message="Indexing official PRAGMATA subtitles", progress=15)
            command = [sys.executable, str(self.project_root / "scripts/index_pragmata_assets.py")]
            command.extend(["--install", str(install)])
            result = subprocess.run(command, cwd=self.project_root, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            if not self.index.load():
                raise RuntimeError(self.index.message)
            self.voice_assets.reload()
            self._set(
                state="idle",
                message=f"PRAGMATA index ready: {self.index.entry_count:,} official lines",
                progress=100,
                last_error=None,
            )
        except Exception as error:
            self.index.load()
            self._set(
                state="retrying",
                message="PRAGMATA index needs attention; check Setup before retrying",
                progress=100,
                last_error=str(error),
            )
        finally:
            self._set(last_checked=datetime.now(timezone.utc).isoformat())
