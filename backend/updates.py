from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Callable

from .textmaps import TextMapIndex
from .voice_assets import VoiceAssetService


class BackgroundUpdateManager:
    """Refresh upstream metadata and installed-game indexes without blocking the app."""

    def __init__(
        self,
        project_root: Path,
        textmaps: TextMapIndex,
        voice_assets: VoiceAssetService,
        publish: Callable[[dict[str, object]], None] | None = None,
        interval: float = 15 * 60,
        game_data_provider: Callable[[], Path | None] | None = None,
    ) -> None:
        self.project_root = project_root
        self.textmaps = textmaps
        self.voice_assets = voice_assets
        self.publish = publish
        self.interval = interval
        self.game_data_provider = game_data_provider
        self.state_path = project_root / "data/voice-assets/background-update-state.json"
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[str] | None = None
        self.state = "checking"
        self.message = "Checking data sources and installed game files"
        self.progress = 2
        self.last_checked: str | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="zzz-background-updates", daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
        if self._thread:
            self._thread.join(timeout=5)

    def request_check(self) -> bool:
        with self._lock:
            already_running = self.state in {"checking", "updating"}
        self._wake.set()
        if not self._thread or not self._thread.is_alive():
            self.start()
        return not already_running

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self.state,
                "message": self.message,
                "progress": self.progress,
                "automatic": True,
                "last_checked": self.last_checked,
                "last_error": self.last_error,
            }

    def _set(self, state: str, message: str, progress: int, error: str | None = None) -> None:
        with self._lock:
            self.state = state
            self.message = message
            self.progress = min(100, max(0, int(progress)))
            self.last_error = error
        if self.publish:
            self.publish(self.status())

    @staticmethod
    def _run_command(arguments: list[str], *, cwd: Path, timeout: int = 900) -> str:
        completed = subprocess.run(
            arguments,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (completed.stdout or completed.stderr).strip()

    def _read_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_state(self, value: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.state_path.with_suffix(".pending")
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        pending.replace(self.state_path)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        return digest.hexdigest()

    def _update_metadata_repository(self) -> tuple[str | None, bool, str]:
        repository = self.project_root / "work/voice-assets/ZenlessData"
        if not (repository / ".git").exists() or not shutil.which("git"):
            from .game_tools import refresh_zzz_metadata
            revision, changed = refresh_zzz_metadata(self.project_root)
            return revision, changed, "Local game metadata refreshed" if changed else "Local game metadata is current"
        # Portable USB filesystems do not record Git ownership. Trust only this
        # exact bundled metadata checkout for these invocations, without changing
        # the user's global Git configuration.
        git = ["git", "-c", f"safe.directory={repository.as_posix()}",
               "-c", "http.sslBackend=openssl"]
        dirty = self._run_command(
            [*git, "status", "--porcelain", "--untracked-files=no"], cwd=repository, timeout=30
        )
        before = self._run_command([*git, "rev-parse", "HEAD"], cwd=repository, timeout=30)
        if dirty:
            # Fetch the current upstream files without touching local edits.
            self._run_command([*git, "fetch", "origin", "master", "--quiet"], cwd=repository, timeout=240)
            after = self._run_command([*git, "rev-parse", "FETCH_HEAD"], cwd=repository, timeout=30)
        else:
            self._run_command([*git, "pull", "--ff-only", "--quiet"], cwd=repository, timeout=240)
            after = self._run_command([*git, "rev-parse", "HEAD"], cwd=repository, timeout=30)

        copied = False
        sources = {"PerformTemplateTb.json": "FileCfg/PerformTemplateTb.json",
                   "OngoingTipsConfigTemplateTb.json": "FileCfg/OngoingTipsConfigTemplateTb.json",
                   "VoiceData.json": "Data/_unsorted/VoiceData.json"}
        for name, relative in sources.items():
            destination = self.project_root / "work/voice-assets" / name
            if dirty:
                source_bytes = subprocess.run([*git, "show", f"{after}:{relative}"],
                    cwd=repository, check=True, capture_output=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            else:
                source = repository / relative
                source_bytes = source.read_bytes() if source.is_file() else b""
            if source_bytes and (not destination.is_file() or destination.read_bytes() != source_bytes):
                pending = destination.with_suffix(".pending")
                pending.write_bytes(source_bytes)
                pending.replace(destination)
                copied = True
        changed = (not dirty and before != after) or copied
        suffix = "; local checkout edits preserved" if dirty else ""
        return after, changed, ("Upstream game metadata updated" if changed else "Upstream game metadata is current") + suffix

    def check_once(self) -> None:
        if self.game_data_provider:
            installed = self.game_data_provider()
        else:
            from scripts.update_voice_assets import discover_game_data
            installed = discover_game_data(self.project_root)
        if installed is None:
            self._set("waiting", "Choose your installed ZZZ folder in Setup; saved transcripts remain available", 100)
            return
        from .game_tools import missing_tools
        if missing_tools(self.project_root, "zzz"):
            self._set("waiting", "Install ZZZ game tools in Setup to prepare original voices", 100)
            return
        previous = self._read_state()
        self._set("checking", "Checking upstream metadata", 5)
        commit: str | None = None
        metadata_changed = False
        metadata_message = "Upstream metadata check skipped"
        try:
            commit, metadata_changed, metadata_message = self._update_metadata_repository()
        except Exception as error:
            metadata_message = f"Upstream check unavailable ({error}); using cached data"

        if self._stop.is_set():
            return
        self._set("updating", metadata_message, 20)
        maps_missing = any(not self.textmaps.file_path(name).is_file() for name in self.textmaps.urls)
        refresh_maps = maps_missing or metadata_changed or (
            commit is not None and previous.get("metadata_commit") not in {None, commit}
        )
        if refresh_maps:
            map_steps = iter((28, 33, 38, 43, 47))

            def map_progress(message: str) -> None:
                self._set("updating", message, next(map_steps, 49))

            self.textmaps.prepare(force_download=True, progress=map_progress)
        elif not self.textmaps.ready:
            self.textmaps.prepare(force_download=False)

        if self._stop.is_set():
            return
        self._set("updating", "Checking installed story, event, and comic voices", 55)
        output = self._run_command(
            [sys.executable, "-m", "scripts.update_voice_assets"],
            cwd=self.project_root,
            timeout=900,
        )
        if self.voice_assets.manifest.is_file():
            self.voice_assets.reload(self.voice_assets.manifest)

        self._set("updating", "Handing new game audio to the background indexes", 82)
        self.last_checked = datetime.now(timezone.utc).astimezone().isoformat()
        self._write_state(
            {
                "version": 1,
                "metadata_commit": commit,
                "last_checked": self.last_checked,
                "voice_update": output,
            }
        )
        self._set("ready", "Text and installed voice data are current", 100)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                self.check_once()
            except Exception as error:
                self.last_checked = datetime.now(timezone.utc).astimezone().isoformat()
                self._set("retrying", "Update paused; capture is still running and will retry", 100, str(error))
            self._wake.wait(self.interval)
