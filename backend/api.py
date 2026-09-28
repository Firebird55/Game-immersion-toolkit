from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .audio import AudioCaptureService
from .voice_assets import VoiceAssetService
from .story_voice import StoryVoiceResolver, StoryVoiceIndexUpdater
from .agent_recognition import AgentRecognizer
from .agent_library import AgentLibraryUpdater
from .voice_activity import VoiceActivity
from .capture import CaptureService
from .config import SettingsStore
from .models import AppSettings, CaptureRegion, CaptureSnapshot, TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex
from .pragmata import PragmataTextIndex
from .pragmata_audio import PragmataVoiceAssetService
from .pragmata_updates import PragmataUpdateManager
from .speakers import SpeakerResolver
from .updates import BackgroundUpdateManager
from .lexirise import LexiriseService, LexiriseError
from .reading import LexiriseReadingService
from .windows import list_visible_windows, game_data_directory, installed_zzz_game_data_directory


PROJECT_ROOT = Path(os.environ.get("PROXY_TRANSCRIPT_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = PROJECT_ROOT / "data"


class ManualIngest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class FavoriteUpdate(BaseModel):
    favorite: bool


class WordProficiencyUpdate(BaseModel):
    start: int = Field(ge=0)
    proficiency: int = Field(ge=1, le=4)


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
        self.settings = SettingsStore(DATA_DIR / "settings.json")
        self.transcript = TranscriptStore(DATA_DIR / "transcript.db")
        self.lexirise = LexiriseService(DATA_DIR / "lexirise")
        self.reading = LexiriseReadingService(DATA_DIR / "lexirise", self.lexirise)
        self.textmaps = TextMapIndex(DATA_DIR / "textmaps")
        self.pragmata = PragmataTextIndex(DATA_DIR / "pragmata")
        self.pragmata.load()
        self.audio = AudioCaptureService(DATA_DIR / "audio")
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
        self.speakers = SpeakerResolver(self.textmaps, self.voice_assets, self.transcript)
        self.story_voices = StoryVoiceResolver(
            DATA_DIR / "voice-assets",
            DATA_DIR / "voice-assets/vgmstream/vgmstream-cli.exe",
            DATA_DIR / "audio",
            self.voice_assets,
        )
        self.story_updater = StoryVoiceIndexUpdater(self.story_voices, self._game_data)
        self.story_voices.updater = self.story_updater
        self.event_loop = asyncio.get_running_loop()
        self.voice_activity = VoiceActivity()
        self.agents = AgentRecognizer(DATA_DIR / 'agent-voices', self.audio, self.on_agent_thread, self.on_agent_activity)
        self.agent_updater = AgentLibraryUpdater(self.agents, lambda: installed_zzz_game_data_directory(self.settings.get()))
        self.agents.updater = self.agent_updater
        removed_rows = self.transcript.purge_unvoiced()
        removed_rows.extend(self.transcript.prune(keep_nonfavorite=50))
        audio_dir = self.audio.output_dir.resolve()
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
            audio=self.audio,
            voice_assets=self.voice_assets,
            pragmata_voice_assets=self.pragmata_voice_assets,
            story_voice_resolver=self.story_voices,
            agent_recognizer=self.agents,
            on_voice=self.on_story_voice,
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
        self.index_task: asyncio.Task[None] | None = None

    async def start_indexes_in_order(self) -> None:
        # Rebuilding several audio fingerprint databases at once can exhaust
        # Windows virtual memory on a portable game drive.
        while self.update_manager.state in {"checking", "updating"}:
            await asyncio.sleep(2)
        self.story_updater.start()
        while self.story_updater.state in {"checking", "updating"}:
            await asyncio.sleep(2)
        self.agent_updater.start()
        while self.agent_updater.state in {"checking", "updating"}:
            await asyncio.sleep(2)
        self.pragmata_updater.start()

    def _game_data(self) -> Path | None:
        discovered = installed_zzz_game_data_directory(self.settings.get())
        if discovered:
            return discovered
        stored = self.agents.library.get("game_data")
        if stored and Path(stored).is_dir():
            return Path(stored)
        return None

    async def on_line(self, line: TranscriptLine) -> None:
        audio_pending = line.audio_pending
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

    def on_agent_thread(self, line: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.hub.broadcast({'type':'agent_line','line':line}), self.event_loop)

    def on_agent_activity(self, agent: str) -> None:
        asyncio.run_coroutine_threadsafe(self.emit_activity('agents', agent), self.event_loop)

    async def on_story_voice(self, line) -> None:
        await self.emit_activity('history')

    async def emit_activity(self, kind, agent=None):
        # Changing characters is still the Agents view. Only leaving the agent
        # screen should prevent a queued agent match from switching the tab.
        activity = self.voice_activity.record(kind, self.capture.snapshot().phase)
        if activity:
            await self.hub.broadcast({'type': 'voice_activity', 'activity': activity})

    async def on_delete(self, line_id: int) -> None:
        await self.hub.broadcast({"type": "line_deleted", "line_id": line_id})

    async def on_capture_status(self, status: CaptureSnapshot) -> None:
        await self.hub.broadcast({"type": "capture_status", "capture": status.model_dump(mode="json")})

    def update_status(self, agents: dict[str, object] | None = None) -> dict[str, object]:
        update = self.update_manager.status()
        if update["state"] in {"checking", "updating"}:
            return update
        agents = agents or self.agents.status()
        agent_update = agents.get("update") or {}
        story_update = self.story_updater.status()
        pragmata_update = self.pragmata_updater.status()
        if pragmata_update.get("state") == "updating":
            return pragmata_update
        if agent_update.get("state") == "updating":
            stage_progress = int(agent_update.get("progress") or 0)
            return {
                **update,
                "state": "updating",
                "message": agent_update.get("message", "Indexing new agent voices"),
                "progress": min(99, 82 + round(17 * stage_progress / 100)),
            }
        if story_update.get("state") == "updating":
            return {
                **update,
                "state": "updating",
                "message": story_update.get("message", "Indexing new story voices"),
                "progress": 94,
            }
        retry = next(
            (
                item for item in (agent_update, story_update, pragmata_update)
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
        return update

    def status(self) -> dict[str, object]:
        agents = self.agents.status()
        return {
            "capture": self.capture.snapshot().model_dump(mode="json"),
            "textmaps": self.textmaps.status(),
            "game_textmaps": {
                "zzz": self.textmaps.status(),
                "pragmata": self.pragmata.status(),
            },
            "audio": self.audio.status(),
            "voice_assets": self.voice_assets.status(),
            "pragmata_voice_assets": self.pragmata_voice_assets.status(),
            "story_voices": self.story_voices.status(),
            "agents": agents,
            "voice_activity": self.voice_activity.latest,
            "updates": self.update_status(agents),
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
            self.textmaps.ready = False
            self.textmaps.state = "error"
            self.textmaps.message = str(error)
        await self.hub.broadcast({"type": "textmaps_status", "textmaps": self.textmaps.status()})


runtime: Runtime


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runtime
    runtime = Runtime()
    runtime.audio.start()
    runtime.start_map_prepare()
    runtime.update_manager.start()
    runtime.index_task = asyncio.create_task(runtime.start_indexes_in_order(), name="voice-index-coordinator")
    if runtime.settings.get().auto_start:
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
        await asyncio.to_thread(runtime.agent_updater.close)
        await asyncio.to_thread(runtime.story_updater.close)
        await asyncio.to_thread(runtime.update_manager.close)
        await asyncio.to_thread(runtime.pragmata_updater.close)
        runtime.story_voices.close()
        runtime.voice_assets.close()
        runtime.pragmata_voice_assets.close()
        runtime.agents.close()
        runtime.audio.stop()
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
    game: str | None = Query(default=None, pattern="^(zzz|pragmata)$"),
) -> list[TranscriptLine]:
    return [
        runtime.speakers.enrich(line) for line in runtime.transcript.list(limit=limit, before_id=before_id, game=game)
        if line.voiced and (line.has_audio or line.channel == "cinematic")
        and (
            runtime.pragmata.is_capture_text(line.text_id, line.english, line.channel)
            if line.game == "pragmata"
            else runtime.textmaps.is_capture_text(line.text_id, line.english, line.channel)
        )
    ]


@app.get("/api/favorites", response_model=list[TranscriptLine])
def get_favorites(
    game: str | None = Query(default=None, pattern="^(zzz|pragmata)$"),
) -> list[TranscriptLine]:
    return [runtime.speakers.enrich(line) for line in runtime.transcript.list_favorites(game=game)]


@app.get('/api/agents')
def get_agents(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return {'lines': runtime.agents.store.list(limit, offset), 'total': runtime.agents.store.count(),
            'status': runtime.agents.status()}


@app.get('/api/agents/{asset_id}/audio')
def get_agent_audio(asset_id: str):
    if not asset_id.isdecimal() or not runtime.agents.store.has_asset(asset_id):
        raise HTTPException(status_code=404, detail='Agent voice not found')
    path = DATA_DIR / 'agent-voices/audio' / f'{asset_id}.wav'
    if not path.is_file():
        raise HTTPException(status_code=404, detail='Agent audio unavailable')
    # Loopback includes browser playback. Do not rediscover our own replay.
    import wave
    with wave.open(str(path)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    runtime.agents.suppress_playback(duration + 1)
    return FileResponse(path, media_type='audio/wav', headers={'Cache-Control':'no-store'})


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
    return runtime.lexirise.status()


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


@app.post("/api/agents/{asset_id}/lexirise")
def send_agent_to_lexirise(asset_id: str, x_proxy_transcript: str = Header(default="")) -> dict:
    if x_proxy_transcript != "lexirise":
        raise HTTPException(403, "Use the companion's Lexirise button.")
    line = runtime.agents.store.get_asset(asset_id) if asset_id.isdecimal() else None
    if line is None:
        raise HTTPException(404, "Agent line not found.")
    try:
        return runtime.lexirise.send(ref=f"agent:{asset_id}", game="zzz", chinese=line["chinese"],
            english="", speaker=line["agent"], audio=DATA_DIR / "agent-voices/audio" / f"{asset_id}.wav",
            audio_source="original; Hanzi automatically transcribed")
    except LexiriseError as error:
        raise HTTPException(409, str(error)) from None
    except OSError:
        raise HTTPException(409, "The local agent voice clip is unavailable.") from None


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
) -> Response:
    values = (left, top, width, height)
    if all(value is not None for value in values):
        try:
            region = CaptureRegion(left=left, top=top, width=width, height=height)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        preview = await asyncio.to_thread(runtime.capture.preview_for_region, region)
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


@app.post("/api/updates/check")
def check_updates() -> dict[str, object]:
    started = runtime.update_manager.request_check()
    pragmata_started = runtime.pragmata_updater.request_check()
    return {"started": started or pragmata_started, "updates": runtime.update_status()}


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
        await websocket.send_json({"type": "snapshot", "snapshot": runtime.status()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await runtime.hub.disconnect(websocket)
    except Exception:
        await runtime.hub.disconnect(websocket)
