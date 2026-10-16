from __future__ import annotations

import json
import threading
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from .game_paths import discover_install
from .game_assets import asset_adapter, LOCAL_GAMES
from .update_workers import INDEX_BUILD_LOCK, subprocess_options


class LocalGameUpdateManager:
    """Build complete snapshots, preserving the previous index on failures."""
    def __init__(self, game, index, voices, on_update=None, project_root=None):
        self.game, self.index, self.voices, self.on_update = game, index, voices, on_update
        self.project_root = project_root
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._force_catalog = False
        self._process = None
        self._status = {"state": "idle", "message": "Waiting for game-file check", "progress": 100,
                        "automatic": True, "last_error": None, "last_checked": None}

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

    def request_check(self, force_catalog=False):
        with self._lock:
            self._stop.clear()
            self._force_catalog = self._force_catalog or force_catalog
            self._wake.set()
            if self._status["state"] == "updating":
                return False
            if not self._thread or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._loop, name=f"{self.game}-index", daemon=True)
                self._thread.start()
            return True

    def _loop(self):
        while not self._stop.is_set():
            self._wake.clear()
            self._run()
            self._wake.wait(120)

    def _run(self):
        with self._lock:
            force_catalog, self._force_catalog = self._force_catalog, False
        try:
            adapter, _executable = asset_adapter(self.game)
            fingerprint, index_install = adapter.fingerprint, adapter.index_install
            install = discover_install(self.game)
            if install is None:
                self._set(state="waiting", message=f"Waiting for installed {LOCAL_GAMES[self.game]} files",
                          progress=100, last_error=None)
                return
            if self.project_root:
                from .game_tools import missing_tools
                if missing_tools(self.project_root, self.game):
                    self._set(state="waiting", message="Install this game's tools in Setup before indexing",
                              progress=100, last_error=None)
                    return
            path = self.index.path
            try:
                old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except ValueError:
                old = {}
            stamp = fingerprint(install)
            catalog = None
            if hasattr(adapter, "refresh_catalog"):
                self._set(state="checking", message="Checking compatible catalog updates", progress=5)
                catalog = adapter.refresh_catalog(path.parent, force=force_catalog or old.get("fingerprint") != stamp)
                from .game_catalogs import catalog_status
                self._set(**catalog_status(self.game, catalog))
            if (old.get("format") == 1 and old.get("install") == str(install) and old.get("fingerprint") == stamp
                    and (catalog is None or old.get("catalog_digest") == catalog["digest"])):
                self.index.load()
                self.voices.reload()
            else:
                self._set(state="updating", progress=10, message=f"Indexing {self.game} subtitles and Mandarin voices")
                with INDEX_BUILD_LOCK:
                    if self._stop.is_set():
                        return
                    payload = self._build_candidate(install, path.parent, index_install)
                from .local_game import LocalDialogue
                if not payload.get("records"):
                    raise ValueError("Extracted dialogue index is empty")
                if catalog and payload.get("catalog_digest") != catalog["digest"]:
                    raise ValueError("Catalog changed while indexing; retry refresh")
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
        finally:
            self._set(last_checked=datetime.now(timezone.utc).isoformat())

    def close(self):
        self._stop.set()
        self._wake.set()
        process = self._process
        if process and process.poll() is None:
            process.terminate()
        if self._thread:
            self._thread.join(timeout=2)

    def _build_candidate(self, install, directory, index_install):
        # In-process adapters remain injectable for fixture-only unit tests.
        # Every live Runtime supplies project_root and uses a separate process.
        if self.project_root is None:
            return index_install(install, directory, lambda message: self._set(message=message, progress=50))
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory, prefix='candidate-') as temporary:
            output = Path(temporary) / 'index.json'
            command = [sys.executable, '-m', 'backend.game_index_worker', '--game', self.game,
                       '--install', str(install), '--directory', str(directory), '--output', str(output)]
            self._process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                             text=True, **subprocess_options())
            try:
                _, error = self._process.communicate(timeout=1800)
                if self._process.returncode:
                    raise RuntimeError(error.strip() or 'Game index worker failed; previous index kept')
                if self._stop.is_set():
                    raise RuntimeError('Game refresh cancelled; previous index kept')
                return json.loads(output.read_text(encoding='utf-8'))
            except BaseException:
                if self._process.poll() is None:
                    self._process.kill()
                    self._process.communicate()
                raise
            finally:
                self._process = None
