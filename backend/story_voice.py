"""Learn exact local WEM aliases for voiced lines missing direct game metadata."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import wave

import numpy as np

from .agent_fingerprint import RATE, landmarks, mono_audio, waveform_score
from .voice_assets import VoiceAssetService, VoiceEntry
from .media_tools import ffmpeg_executable


STORY_PACKAGE = re.compile(r"10[1-3]\d\d")


def story_package_inventory(game_data: Path) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for layer in ("StreamingAssets", "Persistent"):
        folder = game_data / layer / "Audio/Windows/Full/Cn"
        for path in sorted(folder.glob("*.pck")):
            if STORY_PACKAGE.fullmatch(path.stem):
                stat = path.stat()
                result[str(path.resolve())] = [stat.st_size, stat.st_mtime_ns]
    return result


def story_index_inventory(game_data: Path, manifest: Path) -> dict[str, list[int]]:
    result = story_package_inventory(game_data)
    if manifest.exists():
        stat = manifest.stat()
        result[str(manifest.resolve())] = [stat.st_size, stat.st_mtime_ns]
    return result


def _decode_entry(entry: VoiceEntry, decoder: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="story-voice-") as folder:
        wem, wav = Path(folder) / "voice.wem", Path(folder) / "voice.wav"
        wem.write_bytes(entry.read())
        subprocess.run(
            [str(decoder), "-o", str(wav), str(wem)],
            capture_output=True,
            check=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with wave.open(str(wav)) as audio:
            if audio.getsampwidth() != 2:
                raise ValueError("Unsupported decoded voice sample width")
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
            samples = samples.astype(np.float32).reshape(-1, audio.getnchannels()) / 32768
            return mono_audio(samples, audio.getframerate())


def _recording_samples(path: Path) -> np.ndarray:
    result = subprocess.run(
        [
            ffmpeg_executable(), "-v", "error", "-nostdin", "-i", str(path),
            "-f", "f32le", "-ac", "1", "-ar", str(RATE), "-",
        ],
        capture_output=True,
        check=True,
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return np.frombuffer(result.stdout, dtype="<f4").copy()


def _verification_score(reference: np.ndarray, observed: np.ndarray) -> float:
    scores: list[float] = []
    if len(observed) >= len(reference):
        scores.append(waveform_score(reference, observed)[0])
    window = min(len(reference), len(observed), round(1.5 * RATE))
    if window >= round(0.8 * RATE):
        maximum = max(0, len(reference) - window)
        starts = {0, maximum, maximum // 3, maximum * 2 // 3}
        for start in starts:
            scores.append(waveform_score(reference[start:start + window], observed)[0])
    return max(scores, default=0.0)


class StoryVoiceResolver:
    """Fingerprint loopback speech, then replace it with the isolated local WEM."""

    def __init__(
        self,
        folder: Path,
        decoder: Path,
        output_dir: Path,
        voice_assets: VoiceAssetService,
    ) -> None:
        self.folder = folder
        self.database_path = folder / "story-fingerprints.db"
        self.decoder = decoder
        self.output_dir = output_dir
        self.voice_assets = voice_assets
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zzz-story-voice")
        self._lock = threading.RLock()
        self._requests: dict[int, tuple[str, str, object]] = {}
        self._active: set[int] = set()
        self.ready = self.database_path.is_file()
        self.last_error: str | None = None
        self.last_match: dict[str, object] | None = None
        self.updater: StoryVoiceIndexUpdater | None = None

    def schedule(self, line_id: int, text_id: str, recording: str, callback) -> bool:
        path = (self.output_dir / recording).resolve()
        if path.parent != self.output_dir.resolve() or not path.is_file():
            return False
        with self._lock:
            self._requests[line_id] = (text_id, recording, callback)
            while len(self._requests) > 50:
                self._requests.pop(next(iter(self._requests)))
            if not self.ready or line_id in self._active:
                return True
            self._submit(line_id)
        return True

    def _submit(self, line_id: int) -> None:
        self._active.add(line_id)
        self._executor.submit(self._work, line_id)

    def index_ready(self) -> None:
        with self._lock:
            self.ready = self.database_path.is_file()
            if not self.ready:
                return
            for line_id in list(self._requests):
                if line_id not in self._active:
                    self._submit(line_id)

    def _work(self, line_id: int) -> None:
        success = False
        try:
            with self._lock:
                request = self._requests.get(line_id)
            if request is None:
                return
            text_id, recording, callback = request
            source = (self.output_dir / recording).resolve()
            if source.parent != self.output_dir.resolve() or not source.is_file():
                return
            entry, diagnostics = self.match(source)
            self.last_match = diagnostics
            if entry is None:
                return
            self.voice_assets.learn(text_id, entry)
            official = self.voice_assets.extract(text_id, line_id)
            callback(line_id, text_id, official)
            success = True
            self.last_error = None
        except Exception as error:
            self.last_error = str(error)
        finally:
            with self._lock:
                self._active.discard(line_id)
                if success:
                    self._requests.pop(line_id, None)

    def match(self, recording: Path) -> tuple[VoiceEntry | None, dict[str, object]]:
        observed = _recording_samples(recording)
        points = landmarks(observed)
        if len(points) > 1800:
            step = (len(points) + 1799) // 1800
            points = points[::step]
        diagnostics: dict[str, object] = {
            "recording": recording.name,
            "seconds": round(len(observed) / RATE, 2),
            "query_landmarks": len(points),
        }
        if len(points) < 15 or not self.database_path.is_file():
            return None, diagnostics

        query: dict[int, list[int]] = {}
        for value, frame in points:
            for delta in (-1, 0, 1):
                query.setdefault(value + delta, []).append(frame)
        votes: Counter[tuple[str, int]] = Counter()
        with closing(sqlite3.connect(
            f"file:{self.database_path.as_posix()}?mode=ro", uri=True, timeout=2
        )) as database:
            keys = list(query)
            for start in range(0, len(keys), 400):
                batch = keys[start:start + 400]
                sql = (
                    "SELECT hash, asset_id, frame FROM hashes WHERE hash IN ("
                    + ",".join("?" for _ in batch) + ")"
                )
                for value, asset_id, reference_frame in database.execute(sql, batch):
                    for observed_frame in query[value]:
                        offset = observed_frame - reference_frame
                        if offset >= -6:
                            votes[(asset_id, round(offset / 4))] += 1
            by_asset: dict[str, int] = {}
            for (asset_id, _offset), count in votes.items():
                by_asset[asset_id] = max(by_asset.get(asset_id, 0), count)
            ranked = sorted(by_asset.items(), key=lambda item: item[1], reverse=True)
            diagnostics["landmark_candidates"] = ranked[:5]
            if not ranked:
                return None, diagnostics
            best_votes = ranked[0][1]
            second_votes = ranked[1][1] if len(ranked) > 1 else 0
            # Quiet speech and short recap bubbles can leave few robust peaks,
            # but a real source still separates sharply from the background.
            # Waveform verification below remains the final acceptance gate.
            if best_votes < 7 or best_votes < second_votes + 3 or best_votes < second_votes * 1.5:
                return None, diagnostics

            verified: list[tuple[float, int, VoiceEntry]] = []
            for asset_id, landmark_votes in ranked[:6]:
                row = database.execute(
                    "SELECT file_id, package, offset, size FROM clips WHERE asset_id = ?",
                    (asset_id,),
                ).fetchone()
                if row is None:
                    continue
                entry = VoiceEntry(Path(row[1]), int(row[2]), int(row[3]), int(row[0], 16))
                reference = _decode_entry(entry, self.decoder)
                verified.append((_verification_score(reference, observed), landmark_votes, entry))

        verified.sort(key=lambda item: (item[0], item[1]), reverse=True)
        diagnostics["waveform_candidates"] = [
            [round(score, 3), count, f"{entry.file_id:016x}"]
            for score, count, entry in verified[:5]
        ]
        if not verified or verified[0][0] < 0.22:
            return None, diagnostics
        if len(verified) > 1 and verified[0][0] - verified[1][0] < 0.08:
            return None, diagnostics
        score, count, entry = verified[0]
        diagnostics["accepted"] = {
            "file_id": f"{entry.file_id:016x}",
            "landmark_votes": count,
            "waveform_score": round(score, 3),
        }
        return entry, diagnostics

    def status(self) -> dict[str, object]:
        indexed = 0
        try:
            with closing(sqlite3.connect(
                f"file:{self.database_path.as_posix()}?mode=ro", uri=True, timeout=0.1
            )) as database:
                indexed = int(database.execute("SELECT COUNT(*) FROM clips").fetchone()[0])
        except sqlite3.Error:
            pass
        return {
            "ready": self.ready,
            "indexed_clips": indexed,
            "pending": len(self._requests),
            "last_match": self.last_match,
            "last_error": self.last_error,
            "update": self.updater.status() if self.updater else None,
        }

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


class StoryVoiceIndexUpdater:
    def __init__(self, resolver: StoryVoiceResolver, discover_game, interval: float = 60) -> None:
        self.resolver = resolver
        self.discover_game = discover_game
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self.state = "checking"
        self.message = "Checking isolated story voices"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="zzz-story-index", daemon=True)
        self._thread.start()

    def status(self) -> dict[str, object]:
        return {"state": self.state, "message": self.message, "automatic": True}

    def close(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
        if self._thread:
            self._thread.join(timeout=5)

    def check_once(self) -> None:
        game_data = self.discover_game()
        if game_data is None:
            self.state, self.message = "waiting", "Waiting for installed Mandarin story voices"
            return
        manifest = self.resolver.voice_assets.manifest
        inventory = story_index_inventory(game_data, manifest)
        state_path = self.resolver.folder / "story-index-state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if (
            self.resolver.database_path.is_file()
            and state.get("version") == 1
            and state.get("inventory") == inventory
        ):
            self.state, self.message = "ready", "All installed story voice fallbacks are indexed"
            self.resolver.index_ready()
            return

        self.state = "updating"
        self.message = "Indexing isolated story voices; capture continues"
        from .runtime_bundle import child_command, discover_layout
        layout = discover_layout()
        log_path = self.resolver.folder / "story-index.log"
        with log_path.open("w", encoding="utf-8") as log:
            self._process = subprocess.Popen(
                child_command('story-fingerprints', ['--game-data', str(game_data)]),
                cwd=layout.resource_root,
                env=layout.child_environment('story-fingerprints'),
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            while self._process.poll() is None:
                if self._stop.wait(1):
                    self._process.terminate()
                    return
            if self._process.returncode:
                raise RuntimeError("Could not finish the isolated story voice index; retrying")
        self.state, self.message = "ready", "All installed story voice fallbacks are indexed"
        self.resolver.index_ready()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as error:
                self.state, self.message = "retrying", str(error)
            if self._stop.wait(self.interval):
                break
