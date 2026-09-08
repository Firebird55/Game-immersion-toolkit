from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from .pragmata import PragmataTextIndex
from .pragmata_audio import PragmataVoiceAssetService


class PragmataUpdateManager:
    """Refresh PRAGMATA localization in the background when its PAKs change."""

    def __init__(
        self,
        project_root: Path,
        index: PragmataTextIndex,
        voice_assets: PragmataVoiceAssetService,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.project_root = project_root
        self.index = index
        self.voice_assets = voice_assets
        self.on_update = on_update
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._status: dict[str, object] = {
            "state": "idle",
            "message": "PRAGMATA game files are current",
            "progress": 100,
            "automatic": True,
            "last_error": None,
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
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="pragmata-index-update", daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._thread:
            self._thread.join(timeout=2)

    def request_check(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        self.start()
        return True

    def _run(self) -> None:
        try:
            path = self.index.path
            needs_update = not path.is_file()
            install = None
            if path.is_file():
                payload = json.loads(path.read_text(encoding="utf-8"))
                install_value = payload.get("install")
                if install_value:
                    install = Path(str(install_value))
                    if install.is_dir():
                        from scripts.index_pragmata_assets import fingerprint
                        needs_update = payload.get("fingerprint") != fingerprint(install)
            if not needs_update:
                self.index.load()
                self.voice_assets.reload()
                self._set(state="idle", message="PRAGMATA game files are current", progress=100)
                return
            self._set(state="updating", message="Indexing official PRAGMATA subtitles", progress=15)
            command = [sys.executable, str(self.project_root / "scripts/index_pragmata_assets.py")]
            if install:
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
                message="PRAGMATA update will retry next launch",
                progress=100,
                last_error=str(error),
            )
