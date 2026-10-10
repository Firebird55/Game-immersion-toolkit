from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ConfigDict

from .voice_assets import VoiceAssetService
from .capture import CaptureService
from .config import SettingsStore
from .models import AppSettings, CaptureRegion, CaptureSnapshot, TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex
from .pragmata import PragmataTextIndex
from .hito import HitoTextIndex
from .pragmata_audio import PragmataVoiceAssetService
from .pragmata_updates import PragmataUpdateManager
from .local_game import LocalGameTextIndex
from .local_voice import LocalVoiceAssetService
from .local_game_updates import LocalGameUpdateManager
from .game_assets import LOCAL_GAMES
from .speakers import SpeakerResolver
from .updates import BackgroundUpdateManager
from .lexirise import LexiriseService, LexiriseError
from .reading import LexiriseReadingService
from .lexirise_settings import account_settings
from .windows import list_visible_windows, game_data_directory, installed_zzz_game_data_directory
from .installation import InstallationService
from .game_paths import GAMES, configured_install, clear_install, discover_install, save_install, validate_install


PROJECT_ROOT = Path(os.environ.get("PROXY_TRANSCRIPT_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = PROJECT_ROOT / "data"


class ManualIngest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class FavoriteUpdate(BaseModel):
    favorite: bool


class WordProficiencyUpdate(BaseModel):
    start: int = Field(ge=0)
    proficiency: int = Field(ge=1, le=4)


class WordContextQuestion(BaseModel):
    start: int = Field(ge=0)
    question: str = Field(min_length=1, max_length=500)


class GrammarKnownUpdate(BaseModel):
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_-]+$")
    known: bool = Field(strict=True)


class SetupFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = Field(default=None, max_length=4096)
    use_automatic: bool = Field(default=False, strict=True)


class SetupComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_start: bool = Field(strict=True)


class SetupAction(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.clients.discard(websocket)

    async def broadcast(self, event: dict[str, object]) -> None:
        async with self._lock:
            clients = list(self.clients)
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(event)
            except Exception:
                stale.append(client)
        if stale:
            async with self._lock:
                for client in stale:
                    self.clients.discard(client)


class Runtime:
    def __init__(self) -> None:
        self.hub = EventHub()
        local_settings = Path(os.environ.get("LOCALAPPDATA", PROJECT_ROOT / "data")) / "Proxy Transcript/settings.json"
        existing_user = local_settings.is_file() or (DATA_DIR / "settings.json").is_file()
        self.settings = SettingsStore(local_settings, legacy_path=DATA_DIR / "settings.json")
        self.transcript = TranscriptStore(DATA_DIR / "transcript.db")
        self.lexirise = LexiriseService(DATA_DIR / "lexirise")
        self.reading = LexiriseReadingService(DATA_DIR / "lexirise", self.lexirise)
        self.textmaps = TextMapIndex(DATA_DIR / "textmaps")
        self.pragmata = PragmataTextIndex(DATA_DIR / "pragmata")
        self.pragmata.load()
        self.hito = HitoTextIndex(DATA_DIR / "hito")
        self.hito.ensure_game_files(None)
        self.voice_assets = VoiceAssetService(
            DATA_DIR / "voice-assets/manifest.json",
            DATA_DIR / "voice-assets/vgmstream/vgmstream-cli.exe",
            DATA_DIR / "audio",
            DATA_DIR / "voice-assets/learned-manifest.json",
        )
        self.pragmata_voice_assets = PragmataVoiceAssetService(
            DATA_DIR / "pragmata",
            DATA_DIR / "voice-assets/vgmstream/vgmstream-cli.exe",
            DATA_DIR / "audio",
        )
        self.game_indexes = {game: LocalGameTextIndex(game, DATA_DIR / game) for game in LOCAL_GAMES}
        self.game_voice_assets = {game: LocalVoiceAssetService(game, DATA_DIR / game,
            DATA_DIR / "voice-assets/vgmstream/vgmstream-cli.exe", DATA_DIR / "audio") for game in self.game_indexes}
        self.speakers = SpeakerResolver(self.textmaps, self.voice_assets, self.transcript)
        self.event_loop = asyncio.get_running_loop()
        removed_rows = self.transcript.purge_unvoiced()
        removed_rows.extend(self.transcript.prune(keep_nonfavorite=50))
        audio_dir = (DATA_DIR / "audio").resolve()
        for _, filename in removed_rows:
            if not filename:
                continue
            path = (audio_dir / filename).resolve()
            if path.parent == audio_dir:
                path.unlink(missing_ok=True)
        self.capture = CaptureService(
            settings=self.settings,
            textmaps=self.textmaps,
            pragmata=self.pragmata,
            transcript=self.transcript,
            on_line=self.on_line,
            on_delete=self.on_delete,
            on_status=self.on_capture_status,
            audio_dir=DATA_DIR / "audio",
            voice_assets=self.voice_assets,
            pragmata_voice_assets=self.pragmata_voice_assets,
            hito=self.hito,
            game_indexes=self.game_indexes,
            game_voice_assets=self.game_voice_assets,
        )
        for line in self.transcript.list(limit=50):
            self.capture.repair_recorded_line(line)
        self.map_task: asyncio.Task[None] | None = None
        self.update_manager = BackgroundUpdateManager(
            PROJECT_ROOT, self.textmaps, self.voice_assets, self.on_update_thread
        )
        self.pragmata_updater = PragmataUpdateManager(
            PROJECT_ROOT, self.pragmata, self.pragmata_voice_assets, self.on_update_thread
        )
        self.game_updaters = {game: LocalGameUpdateManager(game, self.game_indexes[game], voices,
            self.on_update_thread, project_root=PROJECT_ROOT) for game, voices in self.game_voice_assets.items()}
        self.installation = InstallationService(PROJECT_ROOT, settings=self.settings,
            game_state=self.setup_game_state, refresh=self.refresh_game, existing_user=existing_user,
            account_configured=lambda: self.lexirise.status()["configured"], install_lookup=self.setup_install)
        self.index_task: asyncio.Task[None] | None = None

    def setup_install(self, game: str) -> Path | None:
        install = discover_install(game)
        if install:
            return install
        if game == "zzz":
            data = installed_zzz_game_data_directory(self.settings.get())
            return data.parent if data else None
        if game == "pragmata":
            from scripts.index_pragmata_assets import find_install
            return find_install()
        from .games import GAME_PROFILES
        from .windows import executable_path_for_window
        for window in list_visible_windows():
            if window.process_name.casefold() not in {name.casefold() for name in GAME_PROFILES[game].process_names}:
                continue
            executable = executable_path_for_window(window)
            if executable:
                depth = 5 if game == "nte" else 3 if game == "wuwa" else 2 if game in {"cyberpunk", "witcher3"} else 0
                try:
                    return validate_install(game, executable.parents[depth])
                except (OSError, ValueError, IndexError):
                    continue
        return None

    def setup_game_state(self, game: str) -> dict:
        if game == "zzz":
            index, audio, update = self.textmaps.status(), self.voice_assets.status(), self.update_manager.status()
        elif game == "pragmata":
            index, audio, update = self.pragmata.status(), self.pragmata_voice_assets.status(), self.pragmata_updater.status()
        elif game == "hito":
            index, audio, update = self.hito.status(), {}, {"state": "automatic", "progress": 100}
        else:
            index, audio, update = self.game_indexes[game].status(), self.game_voice_assets[game].status(), self.game_updaters[game].status()
        return {"index_ready": bool(index.get("ready")), "index_state": index.get("state"),
                "index_message": index.get("message", ""), "indexed_lines": index.get("entry_count", 0),
                "audio_ready": bool(audio.get("ready")), "update_state": update.get("state", "idle"),
                "update_message": update.get("message", "Game data checks run automatically"),
                "progress": update.get("progress", 100), "last_checked": update.get("last_checked"),
                "catalog_message": update.get("catalog_message"), "catalog_warning": update.get("catalog_warning", False),
                "needs_attention": bool(update.get("last_error"))}

    def refresh_game(self, game: str) -> bool:
        if game not in GAMES:
            raise ValueError("Unsupported game")
        from .game_tools import missing_tools
        if missing_tools(PROJECT_ROOT, game):
            return False
        if game == "zzz":
            return self.update_manager.request_check()
        if game == "pragmata":
            return self.pragmata_updater.request_check()
        if game == "hito":
            self.hito.ensure_game_files(None)
            return self.hito.refresh()
        if game in {"nte", "honkai3"}:
            return self.game_updaters[game].request_check(force_catalog=True)
        return self.game_updaters[game].request_check()

    async def start_indexes_in_order(self) -> None:
        # Refresh exact game-file mappings before checking the second game.
        while self.update_manager.state in {"checking", "updating"}:
            await asyncio.sleep(2)
        self.pragmata_updater.start()
        while self.pragmata_updater.status()["state"] in {"checking", "updating"}:
            await asyncio.sleep(2)
        for updater in self.game_updaters.values():
            updater.start()

    async def on_line(self, line: TranscriptLine) -> None:
        audio_pending = line.audio_pending
        if line.game == "zzz":
            line = self.speakers.enrich(line)
        if audio_pending and not line.audio_pending:
            # Speaker enrichment can round-trip through SQLite; preserve this
            # transient delivery state on the WebSocket payload.
            line = line.model_copy(update={"audio_pending": True})
        await self.hub.broadcast({"type": "line", "line": line.model_dump(mode="json")})

    def on_update_thread(self, update: dict[str, object]) -> None:
        asyncio.run_coroutine_threadsafe(
            self.hub.broadcast({"type": "update_status", "updates": self.update_status()}),
            self.event_loop,
        )

    async def on_delete(self, line_id: int) -> None:
        await self.hub.broadcast({"type": "line_deleted", "line_id": line_id})

    async def on_capture_status(self, status: CaptureSnapshot) -> None:
        await self.hub.broadcast({"type": "capture_status", "capture": status.model_dump(mode="json")})

    def update_status(self) -> dict[str, object]:
        update = self.update_manager.status()
        if update["state"] in {"checking", "updating"}:
            return update
        pragmata_update = self.pragmata_updater.status()
        if pragmata_update.get("state") in {"checking", "updating"}:
            return pragmata_update
        retry = next(
            (
                item for item in (pragmata_update,)
                if item.get("state") == "retrying"
            ),
            None,
        )
        if retry:
            return {
                **update,
                "state": "retrying",
                "message": retry.get("message", "An audio index will retry automatically"),
                "progress": 100,
            }
        for updater in self.game_updaters.values():
            current = updater.status()
            if current["state"] in {"updating", "retrying"}:
                return current
        return update

    def status(self) -> dict[str, object]:
        return {
            "capture": self.capture.snapshot().model_dump(mode="json"),
            "textmaps": self.textmaps.status(),
            "game_textmaps": {
                "zzz": self.textmaps.status(),
                "pragmata": self.pragmata.status(),
                "hito": self.hito.status(),
                **{game: index.status() for game, index in self.game_indexes.items()},
            },
            "audio": {"ready": self.voice_assets.ready or self.pragmata_voice_assets.ready or any(v.ready for v in self.game_voice_assets.values()),
                      "message": "Original voices from game files; matched by visible subtitles",
                      "clip_mode": "subtitle-game-files", "listening": False},
            "voice_assets": self.voice_assets.status(),
            "pragmata_voice_assets": self.pragmata_voice_assets.status(),
            "game_voice_assets": {game: v.status() for game, v in self.game_voice_assets.items()},
            "updates": self.update_status(),
            "settings": self.settings.get().model_dump(mode="json"),
            "session": {
                "id": self.capture.session_id,
                "line_count": self.transcript.count(self.capture.session_id),
                "total_line_count": self.transcript.count(),
            },
        }

    def start_map_prepare(self, force: bool = False) -> bool:
        if self.map_task and not self.map_task.done():
            return False
        self.map_task = asyncio.create_task(self.prepare_maps(force), name="textmap-prepare")
        return True

    async def prepare_maps(self, force: bool = False) -> None:
        try:
            await asyncio.to_thread(
                self.textmaps.prepare,
                force_download=force,
                progress=self.textmaps.set_message,
            )
            await asyncio.to_thread(self.speakers.backfill)
        except Exception as error:
            self.textmaps.state = "ready" if self.textmaps.ready else "error"
            self.textmaps.message = "Refresh failed; keeping the previous complete TextMaps" if self.textmaps.ready else str(error)
        await self.hub.broadcast({"type": "textmaps_status", "textmaps": self.textmaps.status()})


runtime: Runtime


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runtime
    runtime = Runtime()
    if runtime.textmaps.file_path("zh_base").is_file():
        runtime.start_map_prepare()
    runtime.update_manager.start()
    runtime.index_task = asyncio.create_task(runtime.start_indexes_in_order(), name="voice-index-coordinator")
    if runtime.settings.get().auto_start and runtime.installation.completed:
        runtime.capture.start()
    try:
        yield
    finally:
        if runtime.index_task:
            runtime.index_task.cancel()
            try:
                await runtime.index_task
            except asyncio.CancelledError:
                pass
        await runtime.capture.close()
        await asyncio.to_thread(runtime.hito.close)
        await asyncio.to_thread(runtime.update_manager.close)
        await asyncio.to_thread(runtime.pragmata_updater.close)
        runtime.voice_assets.close()
        runtime.pragmata_voice_assets.close()
        for updater in runtime.game_updaters.values():
            await asyncio.to_thread(updater.close)
        for voices in runtime.game_voice_assets.values():
            voices.close()
        if runtime.map_task and not runtime.map_task.done():
            runtime.map_task.cancel()
            try:
                await runtime.map_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Proxy Transcript API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def get_status() -> dict[str, object]:
    return runtime.status()


def setup_access(request: Request, header: str | None = None, *, write: bool = False) -> None:
    if request.url.hostname not in {"localhost", "127.0.0.1"}:
        raise HTTPException(403, "Setup is available only on this PC")
    origin = request.headers.get("origin")
    if origin and origin not in {"http://localhost:3000", "http://127.0.0.1:3000",
                                  "http://localhost:3001", "http://127.0.0.1:3001"}:
        raise HTTPException(403, "Use the local companion to configure setup")
    if write and header != "setup":
        raise HTTPException(403, "Setup action header required")


@app.get("/api/setup")
def setup_status(request: Request) -> dict:
    setup_access(request)
    return runtime.installation.status()


@app.get("/api/setup/report")
def setup_report(request: Request) -> dict:
    setup_access(request)
    return runtime.installation.report()


@app.post("/api/setup/games/{game}")
def setup_folder(game: str, payload: SetupFolder, request: Request,
                 x_proxy_transcript: str | None = Header(default=None)) -> dict:
    setup_access(request, x_proxy_transcript, write=True)
    if game not in GAMES:
        raise HTTPException(404, "Unsupported game")
    if runtime.installation.status()["native"].get("folders"):
        raise HTTPException(409, "Finish the Windows folder picker first")
    try:
        if payload.use_automatic and payload.path is None:
            clear_install(game)
        elif not payload.use_automatic and payload.path and payload.path.strip():
            value = payload.path.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            save_install(game, Path(value))
        else:
            raise ValueError("Choose a folder or explicitly use automatic detection")
    except (ValueError, OSError):
        raise HTTPException(400, "Required game files were not found. Choose the installation folder shown in Setup; the previous folder was kept.") from None
    runtime.refresh_game(game)
    return runtime.installation.status()


@app.post("/api/setup/games/{game}/tools")
def setup_tools(game: str, payload: SetupAction, request: Request,
                x_proxy_transcript: str | None = Header(default=None)) -> dict:
    setup_access(request, x_proxy_transcript, write=True)
    try:
        started = runtime.installation.prepare(game)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    return {"started": started}


@app.post("/api/setup/games/{game}/refresh")
def setup_refresh(game: str, payload: SetupAction, request: Request,
                  x_proxy_transcript: str | None = Header(default=None)) -> dict:
    setup_access(request, x_proxy_transcript, write=True)
    if game not in GAMES:
        raise HTTPException(404, "Unsupported game")
    if not runtime.setup_install(game):
        raise HTTPException(400, "Choose an installed game folder first")
    from .game_tools import missing_tools
    if missing_tools(PROJECT_ROOT, game):
        raise HTTPException(409, "Install this game's tools before refreshing")
    return {"started": runtime.refresh_game(game)}


@app.post("/api/setup/native/{kind}")
def setup_native(kind: str, payload: SetupAction, request: Request,
                 x_proxy_transcript: str | None = Header(default=None)) -> dict:
    setup_access(request, x_proxy_transcript, write=True)
    try:
        return {"started": runtime.installation.launch_native(kind)}
    except (ValueError, OSError):
        raise HTTPException(400, "The setup dialog could not open. Re-run Install.cmd on Windows and retry.") from None


@app.post("/api/setup/complete")
def setup_complete(payload: SetupComplete, request: Request,
                   x_proxy_transcript: str | None = Header(default=None)) -> dict:
    setup_access(request, x_proxy_transcript, write=True)
    runtime.installation.complete(payload.auto_start)
    if payload.auto_start:
        runtime.capture.start()
    return {"completed": True}


@app.get("/api/settings", response_model=AppSettings)
def get_settings() -> AppSettings:
    return runtime.settings.get()


@app.patch("/api/settings", response_model=AppSettings)
async def update_settings(settings: AppSettings) -> AppSettings:
    saved = runtime.settings.save(settings)
    await runtime.hub.broadcast({"type": "settings", "settings": saved.model_dump(mode="json")})
    return saved


@app.get("/api/lines", response_model=list[TranscriptLine])
def get_lines(
    limit: int = Query(default=250, ge=1, le=1000),
    before_id: int | None = Query(default=None, ge=1),
    game: str | None = Query(default=None, pattern="^(zzz|pragmata|hito|cyberpunk|wuwa|witcher3|nte|honkai3)$"),
) -> list[TranscriptLine]:
    return [
        runtime.speakers.enrich(line) if line.game == "zzz" else line
        for line in runtime.transcript.list(limit=limit, before_id=before_id, game=game)
        if line.game == "hito" or (line.voiced and (
            runtime.pragmata.is_capture_text(line.text_id, line.english, line.channel)
            if line.game == "pragmata"
            else runtime.game_indexes[line.game].is_capture_text(line.text_id, line.english, line.channel)
            if line.game in runtime.game_indexes
            else runtime.textmaps.is_capture_text(line.text_id, line.english, line.channel)
        ))
    ]


@app.get("/api/favorites", response_model=list[TranscriptLine])
def get_favorites(
    game: str | None = Query(default=None, pattern="^(zzz|pragmata|hito|cyberpunk|wuwa|witcher3|nte|honkai3)$"),
) -> list[TranscriptLine]:
    return [runtime.speakers.enrich(line) if line.game == "zzz" else line
            for line in runtime.transcript.list_favorites(game=game)]


@app.get("/api/lines/{line_id}/audio")
def get_line_audio(line_id: int) -> FileResponse:
    filename = runtime.transcript.audio_path(line_id)
    if not filename:
        raise HTTPException(status_code=404, detail="This line has no captured voice clip")
    audio_dir = (DATA_DIR / "audio").resolve()
    path = (audio_dir / filename).resolve()
    if path.parent != audio_dir or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file is unavailable")
    media_type = "audio/mpeg" if path.suffix.casefold() == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@app.patch("/api/lines/{line_id}/favorite", response_model=TranscriptLine)
async def update_line_favorite(line_id: int, payload: FavoriteUpdate) -> TranscriptLine:
    line = runtime.transcript.set_favorite(line_id, payload.favorite)
    if line is None:
        raise HTTPException(status_code=404, detail="Transcript line not found")
    await runtime.on_line(line)
    return line


@app.get("/api/lexirise")
def lexirise_status() -> dict:
    status = runtime.lexirise.status()
    if status["configured"] and not hasattr(runtime.lexirise, "_settings_scope"):
        try:
            account_settings(runtime.lexirise)
        except LexiriseError:
            pass  # Reading/panel errors remain actionable without blocking capture.
    return status


@app.get("/api/lexirise/decks")
def lexirise_available_decks() -> dict:
    try:
        return {"decks":runtime.lexirise.available_decks()}
    except LexiriseError as error:
        raise HTTPException(503,str(error)) from None


@app.post("/api/lexirise/decks")
def lexirise_configure_deck(payload:dict,x_proxy_transcript:str=Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403,"Use the companion's destination controls.")
    if set(payload)-{"game","deck_id","create"} or type(payload.get("game")) is not str or (payload.get("create") is not True and type(payload.get("deck_id")) is not int):
        raise HTTPException(422,"Select a destination or explicitly create one.")
    if payload.get("create") is True and "deck_id" in payload:
        raise HTTPException(422,"Choose selection or creation, not both.")
    try:
        runtime.lexirise.configure_game_deck(payload["game"],None if payload.get("create") is True else payload["deck_id"])
        return runtime.lexirise.status()
    except LexiriseError as error:
        raise HTTPException(503,str(error)) from None


@app.get("/api/lexirise/settings")
def lexirise_get_settings() -> dict:
    try:
        return account_settings(runtime.lexirise)
    except LexiriseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None


@app.patch("/api/lexirise/settings")
def lexirise_patch_settings(payload: dict, x_proxy_transcript: str = Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(status_code=403, detail="Explicit Lexirise action required.")
    try:
        return account_settings(runtime.lexirise, payload)
    except LexiriseError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@app.get("/api/lines/{line_id}/reading")
def line_reading(line_id: int) -> dict:
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        return runtime.reading.analyze(line.chinese)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None


@app.get("/api/lines/{line_id}/reading/lookup")
def line_word_lookup(line_id: int, start: int) -> dict:
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.lookup(line.chinese, start)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.post("/api/lines/{line_id}/reading/grammar")
def line_grammar_known(line_id: int, payload: GrammarKnownUpdate,
                       x_proxy_transcript: str = Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403, "Use the companion's grammar controls.")
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.set_grammar_known(line.chinese, payload.slug, payload.known)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Grammar rule not found in this line")
    return result


@app.get("/api/lines/{line_id}/reading/context")
def line_word_context(line_id: int, start: int = Query(ge=0)) -> dict:
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.context(line.chinese, start)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.post("/api/lines/{line_id}/reading/context")
def ask_line_word_context(line_id: int, payload: WordContextQuestion,
                          x_proxy_transcript: str = Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403, "Use the companion's word controls.")
    question = payload.question.strip()
    if not question:
        raise HTTPException(422, "Question cannot be blank")
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.context(line.chinese, payload.start, question)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.get("/api/lines/{line_id}/reading/examples")
def line_word_examples(line_id: int, start: int = Query(ge=0)) -> dict:
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.examples(line.chinese, start)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.get("/api/lines/{line_id}/reading/similar")
def line_word_similar(line_id: int, start: int = Query(ge=0)) -> dict:
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.similar(line.chinese, start)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.post("/api/lines/{line_id}/reading/examples/{example_index}/save")
def save_line_word_example(line_id: int, example_index: int, start: int = Query(ge=0),
                           x_proxy_transcript: str = Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403, "Use the companion's example bookmark.")
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.save_example(line.chinese, start, example_index)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Example not found for this word")
    return result


@app.get("/api/lines/{line_id}/reading/characters")
def line_word_characters(line_id: int, start: int = Query(ge=0)) -> dict:
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.characters(line.chinese, start)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.post("/api/lines/{line_id}/reading/proficiency")
def line_word_proficiency(line_id: int, payload: WordProficiencyUpdate,
                          x_proxy_transcript: str = Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403, "Use the companion's word controls.")
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "Transcript line not found")
    try:
        result = runtime.reading.set_proficiency(line.chinese, payload.start, payload.proficiency)
    except LexiriseError as error:
        raise HTTPException(503, str(error)) from None
    if result is None:
        raise HTTPException(404, "Word not found in this line")
    return result


@app.post("/api/lines/{line_id}/lexirise")
def send_line_to_lexirise(line_id: int, x_proxy_transcript: str = Header(default="")) -> dict:
    # Custom header forces cross-origin browsers through the existing allowlist.
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403, "Use the companion's Lexirise button.")
    line = runtime.transcript.get(line_id)
    if line is None:
        raise HTTPException(404, "This line is no longer in local history.")
    if not line.voiced:
        raise HTTPException(409, "Wait until this line is confirmed voiced.")
    if line.game == "zzz":
        line = runtime.speakers.enrich(line)
    root = (DATA_DIR / "audio").resolve()
    path = (root / (runtime.transcript.audio_path(line_id) or "missing")).resolve()
    if path.parent != root:
        raise HTTPException(404, "Voice file unavailable.")
    try:
        return runtime.lexirise.send(ref=f"line:{line_id}", game=line.game, chinese=line.chinese,
            english=line.english, speaker=" / ".join(filter(None, [line.speaker_english, line.speaker_chinese])),
            audio=path, audio_source=line.audio_source)
    except LexiriseError as error:
        raise HTTPException(409, str(error)) from None
    except OSError:
        raise HTTPException(409, "The local voice clip became unavailable. Try a saved favorite.") from None


@app.post("/api/capture/start")
async def start_capture() -> dict[str, object]:
    started = runtime.capture.start()
    return {"started": started, "capture": runtime.capture.snapshot().model_dump(mode="json")}


@app.post("/api/capture/stop")
async def stop_capture() -> dict[str, object]:
    stopped = await runtime.capture.stop()
    return {"stopped": stopped, "capture": runtime.capture.snapshot().model_dump(mode="json")}


@app.get("/api/capture/preview.jpg")
async def capture_preview(
    left: float | None = Query(default=None, ge=0, le=1),
    top: float | None = Query(default=None, ge=0, le=1),
    width: float | None = Query(default=None, gt=0, le=1),
    height: float | None = Query(default=None, gt=0, le=1),
    picture_area: Literal["window", "16:9"] | None = Query(default=None),
) -> Response:
    values = (left, top, width, height)
    if all(value is not None for value in values):
        try:
            region = CaptureRegion(left=left, top=top, width=width, height=height)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        preview = await asyncio.to_thread(runtime.capture.preview_for_region, region, picture_area)
    else:
        preview = runtime.capture.preview_bytes()
    if not preview:
        raise HTTPException(status_code=404, detail="No capture preview is available yet")
    return Response(
        content=preview,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.post("/api/textmaps/update")
def update_textmaps() -> dict[str, object]:
    started = runtime.start_map_prepare(force=True)
    return {"started": started, "textmaps": runtime.textmaps.status()}


@app.post("/api/games/{game}/update")
def update_local_game(game: str) -> dict:
    updater = runtime.game_updaters.get(game)
    if updater is None:
        raise HTTPException(404, "Unsupported game-file index")
    return {"started": updater.request_check(), "updates": updater.status()}


@app.post("/api/hito/update")
def update_hito_text() -> dict[str, object]:
    started = runtime.hito.refresh()
    return {"started": started, "hito": runtime.hito.status()}


@app.post("/api/updates/check")
def check_updates() -> dict[str, object]:
    started = runtime.update_manager.request_check()
    pragmata_started = runtime.pragmata_updater.request_check()
    new_started = [updater.request_check() for updater in runtime.game_updaters.values()]
    return {"started": started or pragmata_started or any(new_started), "updates": runtime.update_status()}


@app.post("/api/ingest", response_model=TranscriptLine)
async def manual_ingest(payload: ManualIngest) -> TranscriptLine:
    if not runtime.textmaps.ready:
        raise HTTPException(status_code=409, detail="TextMaps are not ready")
    match = await asyncio.to_thread(
        runtime.textmaps.match_text,
        payload.text,
        runtime.settings.get().fuzzy_threshold,
    )
    if match is None:
        raise HTTPException(status_code=404, detail="No bilingual TextMap match found")
    line = runtime.transcript.add(match, runtime.capture.session_id)
    await runtime.on_line(line)
    return line


@app.get("/api/windows")
def windows() -> list[dict[str, object]]:
    return [
        {
            "handle": window.handle,
            "title": window.title,
            "process_name": window.process_name,
            "bounds": window.bounds,
        }
        for window in list_visible_windows()
    ]


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await runtime.hub.connect(websocket)
    try:
        snapshot = await asyncio.to_thread(runtime.status)
        await websocket.send_json({"type": "snapshot", "snapshot": snapshot})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await runtime.hub.disconnect(websocket)
    except Exception:
        await runtime.hub.disconnect(websocket)
