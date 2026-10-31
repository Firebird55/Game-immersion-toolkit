"""First-run setup and local maintenance. No credentials or game assets leave the PC."""
from __future__ import annotations

from .runtime_paths import data_root as runtime_data_root
from .runtime_bundle import child_command, discover_layout, resource_path
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
from .owned_process import OwnedProcess

from .game_paths import GAMES, GAME_NAMES, configured_install, discover_install, load_paths
from .game_tools import missing_tools, prepare_tools
from .media_tools import ffmpeg_executable
from .steam_games import STEAM_GAMES
from .preparation_errors import PreparationFailure, public_failure

FOLDER_HINTS = {
    "riseofthetombraider": "Choose the Rise of the Tomb Raider folder containing ROTTR.exe and bigfile.000.tiger.",
    "shadowofthetombraider": "Choose the Shadow of the Tomb Raider folder containing SOTTR.exe and bigfile.000.tiger.",
    "starrail": "Choose Star Rail Games containing StarRail.exe and StarRail_Data; the launcher folder is also accepted.",
    "genshin": "Choose Genshin Impact game containing GenshinImpact.exe and GenshinImpact_Data; YuanShen clients are accepted too.",
    "endfield": "Choose the Endfield folder containing Endfield.exe and Endfield_Data/StreamingAssets/VFS.",
    "heavyrain": "Choose the HEAVY RAIN folder containing HeavyRain.exe and the Resources archives.",
    "beyond": "Choose the BEYOND Two Souls folder containing BeyondTwoSouls_Steam.exe and BigFile_PC.idx.",
    "zzz": "Choose the game folder containing ZenlessZoneZero_Data, or the Data folder itself.",
    "pragmata": "Choose the folder containing PRAGMATA.exe and re_chunk_*.pak archives.",
    "hito": "Choose the folder containing resources/app.asar.",
    "cyberpunk": "Choose the installation root containing bin/x64 and archive/pc/content.",
    "wuwa": "Choose the installation root containing Client, or the Client folder itself.",
    "witcher3": "Choose the installation root containing bin and content.",
    "nte": "Choose the Neverness to Everness folder containing Client, or Client/WindowsNoEditor/HT itself.",
}
VOICE_HINTS = {
    "riseofthetombraider": "Install the selected spoken language through Steam Properties, wait for its download, then prepare the language. Regional and DLC pack availability is shown separately.",
    "shadowofthetombraider": "Install the selected spoken language through Steam Properties, wait for its download, then prepare the language. Some voice packs require the corresponding regional edition.",
    "starrail": "Install your chosen original voice in the game, then prepare its learning language and translation in Languages.",
    "genshin": "Install your chosen voice pack through the game's language settings, then prepare it in Languages.",
    "endfield": "Install the matching voice pack, then prepare tools and the selected language.",
    "heavyrain": "Use the selected study language's official installed voice data, then explicitly prepare that language in Languages.",
    "beyond": "Select the matching spoken language in Steam Properties, wait for its official pack to finish, then explicitly prepare Languages.",
    "zzz": "Install the selected study language's original voice pack through the launcher, then prepare it in Languages.",
    "pragmata": "The selected study language's original voices are verified from installed PAKs during language preparation.",
    "hito": "Hito uses verified game text and does not need a voice decoder.",
    "cyberpunk": "Install your selected learning language's official voice pack through the game launcher, then prepare it in Languages.",
    "wuwa": "Download the selected study language's voice pack in Wuthering Waves, then prepare it in Languages.",
    "witcher3": "Install the selected study language's official speech pack through your game launcher, then prepare it in Languages.",
    "nte": "Download the selected original voice pack, choose Prepare game tools, then prepare its dialogue and cinematic bindings in Languages.",
}


FOLDER_HINTS.update({game: f"Choose the {spec.title} folder containing {spec.executable}."
                     for game, spec in STEAM_GAMES.items()})
VOICE_HINTS.update({game: "Install the selected original voice language through Steam Properties → Language, "
                          "wait for the download, then prepare its language table here."
                    for game in STEAM_GAMES})


def _voice_state(game: str, install: Path | None, state: dict) -> str:
    if game == "hito":
        return "not_required"
    if not install:
        return "not_checked"
    if (spec := STEAM_GAMES.get(game)) and not spec.voiced_capture:
        return 'unvoiced_only'
    if state.get('index_state') == 'needs_language_setup':
        return 'needs_language_setup'
    if state.get("audio_ready"):
        return "present"
    if state.get('source_locale'):
        return 'missing' if state.get('index_state') == 'missing_voice' else 'verify_during_indexing'
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
        layout = discover_layout()
        self.path = (layout.settings_root / 'setup.json' if layout.mode == 'bundle' or sys.platform != 'win32' else
                     Path(os.environ.get("LOCALAPPDATA", runtime_data_root(root))) / "Proxy Transcript/setup.json")
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._tool_thread: threading.Thread | None = None
        self._native: dict[str, subprocess.Popen] = {}
        self._native_owners = {}
        self._native_threads = []
        self._paused = False
        self.completed = existing_user
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value.get("completed"), bool):
                self.completed = value["completed"]
        except (OSError, ValueError, AttributeError):
            pass

    def status(self) -> dict:
        layout = discover_layout()
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
                state = {**state, **expansion_status(install, state.get('source_locale'))}
            configured = configured_install(game)
            folder_state = "configured" if configured else "invalid" if game in saved else "detected" if install else "missing"
            try:
                voice = _voice_state(game, install, state)
            except OSError:
                voice = "not_checked"
            voice_hint = VOICE_HINTS[game]
            games.append({"id": game, "title": GAME_NAMES[game], "configured_path": saved.get(game),
                          "detected_path": str(install) if install else None, "folder_state": folder_state,
                          "folder_hint": FOLDER_HINTS[game], "voice_state": voice,
                          "voice_hint": voice_hint, "tools_missing": missing_tools(self.root, game), **state})
        ocr = Path.home() / ".config/oneocr"
        from .ocr_engine import portable_models_available
        from .desktop_capabilities import capture_capability
        requirements = [
            capture_capability(),
            {"id": "ocr", "title": "Subtitle OCR", "ready": portable_models_available() or all((ocr / name).is_file() for name in
              ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll")),
             "help": "Offline OCR is included. Repair the toolkit installation if its model files are missing."},
            {"id": "audio", "title": "Audio conversion", "ready": bool(ffmpeg_executable()),
             "help": "Repair the toolkit installation if the bundled audio converter is missing."},
        ]
        if layout.mode == 'bundle':
            requirements[1]['help'] = "Offline OCR is included. This experimental bundle still needs native capture verification."
            requirements[2]['help'] = "Audio conversion is unavailable until this bundle's codec and game-tool verification is complete. Keep using your existing toolkit installation."
            requirements.append({'id': 'runtime-acceptance', 'title': 'Runtime verification', 'ready': False,
                'help': "This candidate is awaiting native capture, game-tool and distribution review."})
        else:
            requirements.append({"id": "node", "title": "Node.js", "ready": bool(shutil.which("node")),
                "help": "Install Node.js 24 with npm, then re-run Install.cmd."})
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
                "version": json.loads(resource_path('package.json').read_text(encoding="utf-8"))["version"],
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
            if self._paused:
                return False
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
                raise PreparationFailure('tools_incomplete',
                    'Preparation still needs: ' + ', '.join(missing) + '. Retry preparation or repair the toolkit installation.')
            with self._lock:
                self._jobs[game] = {"state": "ready", "message": "Tools ready; checking game data", "progress": 100}
            if self.install_lookup(game):
                self.refresh_game(game)
        except Exception as error:
            logging.getLogger(__name__).exception('Tool preparation failed for %s', game)
            failure = public_failure(error)
            with self._lock:
                self._jobs[game] = {"state": "error", "message": failure['message'],
                                    "code": failure['code'], "progress": 100}

    def launch_native(self, kind: str) -> bool:
        if kind not in {"folders", "lexirise", "checks"}:
            raise ValueError("Unsupported setup action")
        with self._lock:
            if self._paused:
                return False
            if any(process.poll() is None for process in self._native.values()):
                return False
            before = load_paths()
            layout = discover_layout()
            source = layout.resource_root
            if kind == 'lexirise':
                # A password field on the host owns the credential. No key is
                # sent to the browser, command line or process environment.
                args = child_command('account-key', ['--account', '--gui'])
            else:
                args = child_command('native-setup', [kind])
            environment = {'env': layout.child_environment()} if layout.mode == 'bundle' else {}
            owner = OwnedProcess(args, cwd=source, stdin=None, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, **environment)
            process = owner.process
            self._native_owners[kind] = owner
            self._native[kind] = process
            monitor = threading.Thread(target=self._native_finished, args=(kind, process, before), daemon=True)
            self._native_threads.append(monitor)
            monitor.start()
            return True

    def pause(self):
        with self._lock:
            self._paused = True
            owners = list(self._native_owners.values())
            threads = [self._tool_thread, *self._native_threads]
        for owner in owners:
            owner.stop()
        for thread in threads:
            if thread is not None:
                thread.join(timeout=30)
                if thread.is_alive():
                    raise RuntimeError('Game setup is still finishing; runtime handoff is blocked.')

    def resume(self):
        with self._lock:
            if self._tool_thread and self._tool_thread.is_alive():
                raise RuntimeError('Game setup has not finished stopping.')
            if any(thread.is_alive() for thread in self._native_threads):
                raise RuntimeError('Setup dialogs have not finished stopping.')
            self._paused = False

    def _native_finished(self, kind, process, before):
        process.wait()
        owner = self._native_owners[kind]
        owner.stop()
        owner.close_streams()
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
