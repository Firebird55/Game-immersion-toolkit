from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import AppSettings


class SettingsStore:
    def __init__(self, path: Path, legacy_path: Path | None = None):
        self.path = path
        self.legacy_path = legacy_path
        self._lock = threading.RLock()
        self._settings = self._load()
        if not path.exists() and legacy_path and legacy_path.exists():
            self.save(self._settings)

    def _load(self) -> AppSettings:
        source = self.path if self.path.exists() else self.legacy_path
        if source is None or not source.exists():
            return AppSettings()
        try:
            return AppSettings.model_validate_json(source.read_text(encoding="utf-8"))
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

    def remember_zzz_proxy(self, voice: str) -> AppSettings:
        """Persist conclusive scene evidence without overwriting concurrent edits."""
        with self._lock:
            current = self.get()
            if voice in {'male', 'female'} and current.zzz_detected_proxy != voice:
                current.zzz_detected_proxy = voice
                return self.save(current)
            return current
