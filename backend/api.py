from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .audio import AudioCaptureService
from .voice_assets import VoiceAssetService
from .agent_recognition import AgentRecognizer
from .agent_library import AgentLibraryUpdater
from .voice_activity import VoiceActivity
from .capture import CaptureService
from .config import SettingsStore
from .models import AppSettings, CaptureRegion, CaptureSnapshot, TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex
from .windows import list_visible_windows, game_data_directory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class ManualIngest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class FavoriteUpdate(BaseModel):
    favorite: bool


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
        self.textmaps = TextMapIndex(DATA_DIR / "textmaps")
        self.audio = AudioCaptureService(DATA_DIR / "audio")
        self.voice_assets = VoiceAssetService(
            DATA_DIR / "voice-assets/manifest.json",
            DATA_DIR / "voice-assets/vgmstream/vgmstream-cli.exe",
            DATA_DIR / "audio",
        )
        self.event_loop = asyncio.get_running_loop()
        self.voice_activity = VoiceActivity()
        self.agents = AgentRecognizer(DATA_DIR / 'agent-voices', self.audio, self.on_agent_thread, self.on_agent_activity)
        self.agent_updater = AgentLibraryUpdater(self.agents, lambda: game_data_directory(self.settings.get()))
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
            transcript=self.transcript,
            on_line=self.on_line,
            on_delete=self.on_delete,
            on_status=self.on_capture_status,
            audio=self.audio,
            voice_assets=self.voice_assets,
            agent_recognizer=self.agents,
            on_voice=self.on_story_voice,
        )
        self.map_task: asyncio.Task[None] | None = None

    async def on_line(self, line: TranscriptLine) -> None:
        await self.hub.broadcast({"type": "line", "line": line.model_dump(mode="json")})

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

    def status(self) -> dict[str, object]:
        return {
            "capture": self.capture.snapshot().model_dump(mode="json"),
            "textmaps": self.textmaps.status(),
            "audio": self.audio.status(),
            "voice_assets": self.voice_assets.status(),
            "agents": self.agents.status(),
            "voice_activity": self.voice_activity.latest,
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
    runtime.agent_updater.start()
    if runtime.settings.get().auto_start:
        runtime.capture.start()
    try:
        yield
    finally:
        await runtime.capture.close()
        await asyncio.to_thread(runtime.agent_updater.close)
        runtime.voice_assets.close()
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
) -> list[TranscriptLine]:
    return [
        line for line in runtime.transcript.list(limit=limit, before_id=before_id)
        if line.voiced and line.has_audio
        and runtime.textmaps.is_capture_text(line.text_id, line.english, line.channel)
    ]


@app.get("/api/favorites", response_model=list[TranscriptLine])
def get_favorites() -> list[TranscriptLine]:
    return runtime.transcript.list_favorites()


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
