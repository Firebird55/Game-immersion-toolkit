"""First-run setup and local maintenance. No credentials or game assets leave the PC."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading

from .game_paths import GAMES, GAME_NAMES, configured_install, discover_install, load_paths
from .game_tools import missing_tools, prepare_tools
from .media_tools import ffmpeg_executable

FOLDER_HINTS = {
    "zzz": "Choose the game folder containing ZenlessZoneZero_Data, or the Data folder itself.",
    "pragmata": "Choose the folder containing PRAGMATA.exe and re_chunk_*.pak archives.",
    "hito": "Choose the folder containing resources/app.asar.",
    "cyberpunk": "Choose the installation root containing bin/x64 and archive/pc/content.",
    "wuwa": "Choose the installation root containing Client, or the Client folder itself.",
    "witcher3": "Choose the installation root containing bin and content.",
    "nte": "Choose the Neverness to Everness folder containing Client, or Client/WindowsNoEditor/HT itself.",
    "honkai3": "Choose the Honkai Impact 3rd folder containing BH3.exe and BH3_Data, or BH3_Data itself.",
}
VOICE_HINTS = {
    "zzz": "Install the Mandarin voice pack through the game launcher.",
    "pragmata": "Mandarin voices are verified from the installed PAKs during indexing.",
    "hito": "Hito uses verified game text and does not need a voice decoder.",
    "cyberpunk": "Install the official Simplified Chinese voice pack through your game launcher.",
    "wuwa": "Download the Chinese voice pack in Wuthering Waves, then refresh game data.",
    "witcher3": "Install the official Chinese speech pack through your game launcher.",
    "nte": "Download Chinese voices in NTE. Only exact installed bilingual dialogue and Chinese voice sources are captured.",
    "honkai3": "Download Chinese story audio in Honkai Impact 3rd. Only dialogue in the available bilingual catalog with verified original voices is supported. The default catalog covers older 4.7 content; refresh checks for compatible catalog updates.",
}


def _voice_state(game: str, install: Path | None, state: dict) -> str:
    if game == "hito":
        return "not_required"
    if not install:
        return "not_checked"
    if state.get("audio_ready"):
        return "present"
    if game == "zzz":
        present = any(any((install / "ZenlessZoneZero_Data" / layer / "Audio/Windows/Full/Cn").glob("*.pck"))
                      for layer in ("StreamingAssets", "Persistent"))
    elif game == "cyberpunk":
        present = (install / "archive/pc/content/lang_zh-cn_voice.archive").is_file()
    elif game == "witcher3":
        present = any(any((install / folder).rglob(name)) for folder in ("content", "dlc")
                      for name in ("cnpc.w3speech", "zhpc.w3speech"))
    else:
        return "missing" if state.get("index_state") == "missing_voice" else "verify_during_indexing"
    return "present" if present else "missing"


class InstallationService:
    def __init__(self, root: Path, *, settings, game_state, refresh, account_configured,
                 existing_user: bool = False, install_lookup=discover_install):
        self.root, self.settings = root, settings
        self.game_state, self.refresh_game = game_state, refresh
        self.account_configured, self.install_lookup = account_configured, install_lookup
        self.path = Path(os.environ.get("LOCALAPPDATA", root / "data")) / "Proxy Transcript/setup.json"
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._tool_thread: threading.Thread | None = None
        self._native: dict[str, subprocess.Popen] = {}
        self.completed = existing_user
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value.get("completed"), bool):
                self.completed = value["completed"]
        except (OSError, ValueError, AttributeError):
            pass

    def status(self) -> dict:
        saved = load_paths()
        games = []
        for game in GAMES:
            try:
                install = self.install_lookup(game)
            except (OSError, ValueError):
                install = None
            state = self.game_state(game)
            if game == "cyberpunk" and install:
                from .cyberpunk_assets import expansion_status
                state = {**state, **expansion_status(install)}
            configured = configured_install(game)
            folder_state = "configured" if configured else "invalid" if game in saved else "detected" if install else "missing"
            try:
                voice = _voice_state(game, install, state)
            except OSError:
                voice = "not_checked"
            games.append({"id": game, "title": GAME_NAMES[game], "configured_path": saved.get(game),
                          "detected_path": str(install) if install else None, "folder_state": folder_state,
                          "folder_hint": FOLDER_HINTS[game], "voice_state": voice,
                          "voice_hint": VOICE_HINTS[game], "tools_missing": missing_tools(self.root, game), **state})
        ocr = Path.home() / ".config/oneocr"
        requirements = [
            {"id": "windows", "title": "Windows", "ready": sys.platform == "win32",
             "help": "Desktop game capture requires Windows. The mobile capture test is a separate browser page."},
            {"id": "ocr", "title": "Subtitle OCR", "ready": all((ocr / name).is_file() for name in
              ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll")),
             "help": "Install or update Windows Snipping Tool, then re-run Install.cmd to repair OCR."},
            {"id": "audio", "title": "Audio conversion", "ready": bool(ffmpeg_executable()),
             "help": "Re-run Install.cmd to repair the local audio dependencies."},
            {"id": "node", "title": "Node.js", "ready": bool(shutil.which("node")),
             "help": "Install Node.js 24 with npm, then re-run Install.cmd."},
        ]
        try:
            free_gb = round(shutil.disk_usage(self.root).free / 1024 ** 3, 1)
        except OSError:
            free_gb = None
        with self._lock:
            jobs = {game: dict(job) for game, job in self._jobs.items()}
            native = {kind: process.poll() is None for kind, process in self._native.items()}
            check = self._native.get("checks")
            capture_check = check.poll() == 0 if check and check.poll() is not None else None
        return {"completed": self.completed, "games": games, "requirements": requirements, "jobs": jobs,
                "native": native, "free_gb": free_gb, "lexirise_configured": self.account_configured(),
                "auto_start": self.settings.get().auto_start if self.completed else False,
                "version": json.loads((self.root / "package.json").read_text(encoding="utf-8"))["version"],
                "capture_check": capture_check}

    def complete(self, auto_start: bool) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".pending")
            temporary.write_text(json.dumps({"version": 1, "completed": True}), encoding="utf-8")
            self.settings.save(self.settings.get().model_copy(update={"auto_start": auto_start}))
            temporary.replace(self.path)
            self.completed = True

    def prepare(self, game: str) -> bool:
        if game not in GAMES:
            raise ValueError("Unsupported game")
        install = self.install_lookup(game)
        if install and self.root.resolve().is_relative_to(install.resolve()):
            raise ValueError("Move the toolkit to a folder outside the game installation before preparing tools")
        with self._lock:
            if self._tool_thread and self._tool_thread.is_alive():
                return False
            self._jobs[game] = {"state": "preparing", "message": "Preparing game tools", "progress": 5}
            self._tool_thread = threading.Thread(target=self._prepare, args=(game,), daemon=True,
                                                  name="game-setup-tools")
            self._tool_thread.start()
            return True

    def _prepare(self, game: str) -> None:
        def progress(message):
            with self._lock:
                self._jobs[game] = {"state": "preparing", "message": message, "progress": 50}
        try:
            prepare_tools(self.root, game, progress)
            missing = missing_tools(self.root, game)
            if missing:
                raise ValueError("Tools are incomplete")
            with self._lock:
                self._jobs[game] = {"state": "ready", "message": "Tools ready; checking game data", "progress": 100}
            if self.install_lookup(game):
                self.refresh_game(game)
        except Exception:
            with self._lock:
                self._jobs[game] = {"state": "error", "message": "Preparation failed. Check your connection and retry. Re-run Install.cmd if dependencies are missing.", "progress": 100}

    def launch_native(self, kind: str) -> bool:
        if kind not in {"folders", "lexirise", "checks"}:
            raise ValueError("Unsupported setup action")
        if sys.platform != "win32":
            raise ValueError("Native setup dialogs require Windows")
        with self._lock:
            if any(process.poll() is None for process in self._native.values()):
                return False
            before = load_paths()
            if kind == "folders":
                args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(self.root / "scripts/select-game-folders.ps1")]
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            elif kind == "lexirise":
                # The hidden-input prompt owns its console. No key is sent to the browser or command line.
                args = [sys.executable, "-m", "scripts.set_lexirise_key"]
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            else:
                args = [sys.executable, str(self.root / "scripts/check-capture-readiness.py"), "--pause"]
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            process = subprocess.Popen(args, cwd=self.root, creationflags=flags)
            self._native[kind] = process
            threading.Thread(target=self._native_finished, args=(kind, process, before), daemon=True).start()
            return True

    def _native_finished(self, kind, process, before):
        process.wait()
        if kind == "folders":
            after = load_paths()
            for game in GAMES:
                if before.get(game) != after.get(game):
                    self.refresh_game(game)

    def report(self) -> dict:
        value = self.status()
        # Build an allowlist; never serialize paths, account details, raw errors or transcript contents.
        return {"version": value["version"], "platform": platform.system(), "python": platform.python_version(),
                "requirements": {item["id"]: item["ready"] for item in value["requirements"]},
                "capture_check": value["capture_check"],
                "games": [{key: item.get(key) for key in ("id", "folder_state", "voice_state", "tools_missing",
                           "index_ready", "audio_ready", "indexed_lines", "update_state", "last_checked")}
                          for item in value["games"]]}
