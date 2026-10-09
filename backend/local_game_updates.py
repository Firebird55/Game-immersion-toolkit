from __future__ import annotations

import json
import threading

from .game_paths import discover_install


class LocalGameUpdateManager:
    """Build complete snapshots, preserving the previous index on failures."""
    def __init__(self, game, index, voices, on_update=None):
        self.game, self.index, self.voices, self.on_update = game, index, voices, on_update
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._status = {"state": "idle", "message": "Waiting for game-file check", "progress": 100,
                        "automatic": True, "last_error": None}

    def status(self):
        with self._lock:
            return dict(self._status)

    def _set(self, **changes):
        with self._lock:
            self._status.update(changes)
        if self.on_update and not self._stop.is_set():
            self.on_update(self.status())

    def start(self):
        return self.request_check()

    def request_check(self):
        if self.status()["state"] == "updating":
            return False
        if not self._thread or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name=f"{self.game}-index", daemon=True)
            self._thread.start()
        else:
            self._wake.set()
        return True

    def _loop(self):
        while not self._stop.is_set():
            self._wake.clear()
            self._run()
            self._wake.wait(120)

    def _run(self):
        try:
            from .cyberpunk_assets import fingerprint, index_install
            install = discover_install(self.game)
            if install is None:
                self._set(state="waiting", message=f"Waiting for installed {self.game} files")
                return
            path = self.index.path
            try:
                old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except ValueError:
                old = {}
            if old.get("format") == 1 and old.get("install") == str(install) and old.get("fingerprint") == fingerprint(install):
                self.index.load()
                self.voices.reload()
            else:
                self._set(state="updating", progress=10, message=f"Indexing {self.game} subtitles and Mandarin voices")
                payload = index_install(install, path.parent, lambda message: self._set(message=message, progress=50))
                from .local_game import LocalDialogue
                if not payload.get("records"):
                    raise ValueError("Extracted dialogue index is empty")
                for record in payload["records"]:
                    LocalDialogue(**record)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".json.part")
                temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                temporary.replace(path)
                if not self.index.load():
                    raise ValueError(self.index.message)
                self.voices.reload()
            self._set(state="idle", message=self.index.message, progress=100, last_error=None)
        except Exception as error:
            self._set(state="retrying", message=f"{self.game} index needs attention", last_error=str(error), progress=100)

    def close(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)
