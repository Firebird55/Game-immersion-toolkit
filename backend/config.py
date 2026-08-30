from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import AppSettings


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._settings = self._load()

    def _load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            return AppSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return AppSettings()

    def get(self) -> AppSettings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def save(self, settings: AppSettings) -> AppSettings:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                settings.model_dump_json(indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._settings = settings.model_copy(deep=True)
            return self.get()
