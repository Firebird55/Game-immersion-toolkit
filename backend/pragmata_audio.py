from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


ZERO_GUID = "00000000-0000-0000-0000-000000000000"
SCENE_CLIP_RE = re.compile(r"^cs\d+_s(\d+)$", re.IGNORECASE)


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _i64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<q", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def _ascii(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("Unterminated timeline string")
    return data[offset:end].decode("utf-8", errors="replace")


def _utf16(data: bytes, offset: int) -> str:
    end = offset
    while end + 1 < len(data) and data[end : end + 2] != b"\0\0":
        end += 2
    return data[offset:end].decode("utf-16-le", errors="replace")


def read_tmlfsm_dialogue_segments(path: Path) -> list[dict[str, float | str]]:
    """Read subtitle GUID intervals from a PRAGMATA TMLFSM2 cinematic timeline."""
    data = path.read_bytes()
    if data[:4] != b"tfs2" or len(data) < 88:
        raise ValueError(f"Not a PRAGMATA TMLFSM2 file: {path}")
    clip_count = _i32(data, 12)
    clip_offsets_offset = _u64(data, 40)
    clip_infos_offset = _u64(data, 48)
    unicode_string_offset = _u64(data, 80)
    if not 0 <= clip_count <= 1000:
        raise ValueError("Invalid TMLFSM2 clip count")

    clips: list[tuple[int, str, float, list[tuple[str, float, float]]]] = []
    for index in range(clip_count):
        clip_offset = _u64(data, clip_offsets_offset + index * 8)
        info_offset = clip_infos_offset + index * 32
        name_offset = _i32(data, info_offset + 24)
        name = _utf16(data, unicode_string_offset + name_offset * 2)
        if data[clip_offset : clip_offset + 4] != b"CLIP" or _i32(data, clip_offset + 4) != 91:
            continue
        num_frames = _f32(data, clip_offset + 8)
        property_count = _i32(data, clip_offset + 36)
        no_hermite_count = _i32(data, clip_offset + 52)
        offsets = struct.unpack_from("<19Q", data, clip_offset + 56)
        properties_offset = offsets[6]
        no_hermite_offset = offsets[10]
        names_offset = offsets[15]
        unicode_names_offset = offsets[16]
        if property_count < 0 or no_hermite_count < 0:
            continue

        intervals: list[tuple[str, float, float]] = []
        for prop_index in range(property_count):
            prop = properties_offset + prop_index * 56
            function_offset = _i64(data, prop + 16)
            try:
                function_name = _ascii(data, names_offset + function_offset)
            except (ValueError, IndexError):
                continue
            if function_name != "RequestMessageId":
                continue
            child_start = _i64(data, prop + 32)
            child_count = struct.unpack_from("<H", data, prop + 40)[0]
            flags = data[prop + 47]
            if ((flags >> 4) & 3) != 3:
                continue
            keys: list[tuple[float, str]] = []
            for key_index in range(child_start, child_start + child_count):
                if not 0 <= key_index < no_hermite_count:
                    continue
                key = no_hermite_offset + key_index * 16
                frame = _f32(data, key)
                value_offset = _i64(data, key + 8)
                value = _utf16(data, unicode_names_offset + value_offset * 2).strip().lower()
                if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value):
                    keys.append((frame, value))
            active_guid: str | None = None
            start_frame = end_frame = 0.0
            for frame, guid in sorted(keys):
                if guid == ZERO_GUID:
                    if active_guid:
                        intervals.append((active_guid, start_frame, end_frame))
                    active_guid = None
                elif guid == active_guid:
                    end_frame = frame
                else:
                    if active_guid:
                        intervals.append((active_guid, start_frame, end_frame))
                    active_guid = guid
                    start_frame = end_frame = frame
            if active_guid:
                intervals.append((active_guid, start_frame, end_frame))
        match = SCENE_CLIP_RE.match(name)
        if match:
            clips.append((int(match.group(1)), name, num_frames, intervals))

    elapsed_frames = 0.0
    result: list[dict[str, float | str]] = []
    for _scene, _name, num_frames, intervals in sorted(clips):
        for guid, start, end in intervals:
            if end > start:
                result.append(
                    {
                        "guid": guid,
                        "start_seconds": (elapsed_frames + start) / 60.0,
                        "end_seconds": (elapsed_frames + end) / 60.0,
                    }
                )
        elapsed_frames += num_frames
    return result


def build_sound_id_audio_map(graph: dict[str, object]) -> dict[int, dict[str, object]]:
    """Map RE Engine MSG SoundIDs to a unique Mandarin Wwise media object."""
    records = graph.get("source_event_records", [])
    source_events = graph.get("source_events", {})
    record_media: dict[int, set[int]] = {}
    if isinstance(source_events, dict):
        for media_id, indexes in source_events.items():
            for index in indexes:
                record_media.setdefault(int(index), set()).add(int(media_id))
    record_index = {
        (str(item[0]), int(item[1])): index
        for index, item in enumerate(records)
        if isinstance(item, list) and len(item) >= 2
    }

    localized_media: dict[str, set[int]] = {}
    for path, links in dict(graph.get("media_links", {})).items():
        if not str(path).casefold().endswith(".sbnk.1.x64.zhcn") or not isinstance(links, dict):
            continue
        for localized_bank, media_ids in links.items():
            localized_media.setdefault(str(localized_bank), set()).update(map(int, media_ids))

    packages = dict(graph.get("media_packages", {}))
    mapped: dict[int, dict[str, object]] = {}
    ambiguous: set[int] = set()
    for bank, events in dict(graph.get("bank_events", {})).items():
        localized_bank = f"{bank}.zhcn"
        available = localized_media.get(localized_bank, set())
        package = packages.get(localized_bank)
        if not available or not isinstance(package, dict):
            continue
        for event_id, event in dict(events).items():
            index = record_index.get((str(bank), int(event_id)))
            candidates = record_media.get(index, set()) & available if index is not None else set()
            if len(candidates) != 1:
                continue
            media_id = next(iter(candidates))
            audio = {
                "bank": str(bank),
                "media_id": media_id,
                "index": str(package.get("index", "")),
                "streaming": str(package.get("streaming", "")),
                "mapping": "sound_id",
            }
            for trigger_id in event.get("trigger_ids", []):
                trigger = int(trigger_id)
                if trigger in mapped and mapped[trigger] != audio:
                    ambiguous.add(trigger)
                else:
                    mapped[trigger] = audio
    for trigger in ambiguous:
        mapped.pop(trigger, None)
    return mapped


def cutscene_audio_for_bank(graph: dict[str, object], bank: str) -> dict[str, object] | None:
    localized_bank = f"{bank}.zhcn"
    package = dict(graph.get("media_packages", {})).get(localized_bank)
    if not isinstance(package, dict):
        return None
    media_ids: set[int] = set()
    for path, links in dict(graph.get("media_links", {})).items():
        if str(path).casefold().endswith(f"/{bank}.sbnk.1.x64.zhcn") and isinstance(links, dict):
            media_ids.update(map(int, links.get(localized_bank, [])))
    if len(media_ids) != 1:
        return None
    return {
        "bank": bank,
        "media_id": next(iter(media_ids)),
        "index": str(package.get("index", "")),
        "streaming": str(package.get("streaming", "")),
        "mapping": "timeline_guid",
    }


def read_pck_media(path: Path, media_id: int) -> bytes:
    """Return one WEM from a standard Wwise AKPK package."""
    data = path.read_bytes()
    if data[:4] != b"AKPK" or len(data) < 32:
        raise ValueError(f"Not a Wwise PCK: {path}")
    _header_size, _version, language_size, bank_size, sound_size, _external_size = struct.unpack_from(
        "<6I", data, 4
    )
    table = 28 + language_size + bank_size
    count = _u32(data, table)
    if 4 + count * 20 > sound_size:
        raise ValueError("Invalid Wwise sound table")
    for index in range(count):
        entry_id, block, length, position, _language = struct.unpack_from("<5I", data, table + 4 + index * 20)
        if entry_id == media_id:
            offset = position * max(block, 1)
            if not 0 < length <= 256 * 1024 * 1024 or offset + length > len(data):
                raise ValueError("Invalid Wwise media bounds")
            payload = data[offset : offset + length]
            if payload[:4] != b"RIFF":
                raise ValueError("Wwise media entry is not a RIFF WEM")
            return payload
    raise KeyError(f"Media {media_id} is not in {path.name}")


def _archive_order(path: Path) -> tuple[int, str]:
    name = path.name.casefold()
    return (int("patch" in name), name)


def pragmata_install_fingerprint(install: Path) -> str:
    return "|".join(
        f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}"
        for path in sorted(install.glob("re_chunk_*.pak*"), key=lambda item: item.name)
    )


@dataclass(frozen=True, slots=True)
class PragmataAudioEntry:
    text_id: str
    media_id: int
    index: str
    streaming: str
    bank: str
    mapping: str
    start_seconds: float | None = None
    end_seconds: float | None = None


class PragmataVoiceAssetService:
    """Extract exact Mandarin PRAGMATA voice media lazily from the installed PAKs."""

    def __init__(self, data_dir: Path, decoder: Path, output_dir: Path):
        self.data_dir = data_dir.resolve()
        self.manifest = data_dir / "textmap.json"
        self.manifest = self.manifest.resolve()
        self.decoder = decoder.resolve()
        self.output_dir = output_dir.resolve()
        self.tools = (self.data_dir / "tools").resolve()
        self._entries: dict[str, PragmataAudioEntry] = {}
        self._install: Path | None = None
        self._fingerprint: str | None = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pragmata-original-voice")
        self._slots = threading.BoundedSemaphore(8)
        self.last_error: str | None = None
        self.ready = False
        self.reload()

    def reload(self) -> bool:
        try:
            payload = json.loads(self.manifest.read_text(encoding="utf-8"))
            entries: dict[str, PragmataAudioEntry] = {}
            for record in payload.get("records", []):
                audio = record.get("audio")
                if not isinstance(audio, dict):
                    continue
                raw_id = str(record["text_id"])
                text_id = raw_id if raw_id.startswith("pragmata:") else f"pragmata:{raw_id}"
                entries[text_id] = PragmataAudioEntry(
                    text_id=text_id,
                    media_id=int(audio["media_id"]),
                    index=str(audio.get("index", "")),
                    streaming=str(audio.get("streaming", "")),
                    bank=str(audio.get("bank", "")),
                    mapping=str(audio.get("mapping", "")),
                    start_seconds=float(audio["start_seconds"]) if "start_seconds" in audio else None,
                    end_seconds=float(audio["end_seconds"]) if "end_seconds" in audio else None,
                )
            install_value = payload.get("install")
            with self._lock:
                self._entries = entries
                self._install = Path(str(install_value)) if install_value else None
                self._fingerprint = str(payload.get("fingerprint") or "")
                self.ready = bool(
                    entries
                    and self._install
                    and self._install.is_dir()
                    and self.decoder.is_file()
                    and (self.tools / "REE.Unpacker.exe").is_file()
                    and shutil.which("ffmpeg")
                )
                self.last_error = None
            return self.ready
        except (OSError, ValueError, KeyError, TypeError) as error:
            with self._lock:
                self.ready = False
                self.last_error = str(error)
            return False

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "ready": self.ready,
                "mapped_lines": len(self._entries),
                "last_error": self.last_error,
            }

    def has(self, text_id: str) -> bool:
        with self._lock:
            return self.ready and text_id in self._entries

    def has_variant(self, text_id: str, _english: str | None = None) -> bool:
        return self.has(text_id)

    def _cache_root(self) -> Path:
        fingerprint = hashlib.sha256((self._fingerprint or "unknown").encode()).hexdigest()[:16]
        return self.data_dir / "audio-assets" / fingerprint

    def _package(self, entry: PragmataAudioEntry) -> Path:
        install = self._install
        if install is None:
            raise FileNotFoundError("PRAGMATA installation is unavailable")
        if pragmata_install_fingerprint(install) != self._fingerprint:
            raise ValueError("PRAGMATA game files changed; waiting for the background reindex")
        cache = self._cache_root()
        for virtual in (entry.streaming, entry.index):
            if virtual:
                candidate = cache / Path(virtual.replace("/", "\\"))
                if candidate.is_file():
                    try:
                        read_pck_media(candidate, entry.media_id)
                        return candidate
                    except KeyError:
                        pass
        virtuals = [value for value in (entry.streaming, entry.index) if value]
        if not virtuals:
            raise ValueError("PRAGMATA audio package path is missing")
        project = self.tools / "Projects" / "P_PRAGMATA_CURRENT.list"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_text("\n".join(virtuals) + "\n", encoding="utf-8")
        cache.mkdir(parents=True, exist_ok=True)
        for archive in sorted(install.glob("re_chunk_*.pak*"), key=_archive_order):
            result = subprocess.run(
                [str(self.tools / "REE.Unpacker.exe"), "P_PRAGMATA_CURRENT", str(archive), str(cache)],
                cwd=self.tools,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout[-1000:])
        for virtual in virtuals:
            candidate = cache / Path(virtual.replace("/", "\\"))
            if candidate.is_file():
                try:
                    read_pck_media(candidate, entry.media_id)
                    return candidate
                except KeyError:
                    pass
        raise FileNotFoundError(f"Mandarin media {entry.media_id} was not extracted")

    def extract(self, text_id: str, line_id: int, _english: str | None = None) -> str:
        with self._lock:
            entry = self._entries.get(text_id)
        if entry is None:
            raise KeyError(text_id)
        package = self._package(entry)
        wem_data = read_pck_media(package, entry.media_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"official-pragmata-{line_id}-{entry.media_id}.mp3"
        destination = self.output_dir / filename
        with tempfile.TemporaryDirectory(prefix="pragmata-voice-", dir=self.output_dir) as scratch_value:
            scratch = Path(scratch_value)
            wem, wav, mp3 = scratch / "voice.wem", scratch / "voice.wav", scratch / "voice.mp3"
            wem.write_bytes(wem_data)
            options = {
                "check": True,
                "capture_output": True,
                "timeout": 90,
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
            }
            subprocess.run([str(self.decoder), "-o", str(wav), str(wem)], **options)
            command = [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin"]
            if entry.start_seconds is not None and entry.end_seconds is not None:
                start = max(0.0, entry.start_seconds - 0.08)
                duration = max(0.1, entry.end_seconds - start + 0.25)
                command.extend(["-ss", f"{start:.4f}", "-t", f"{duration:.4f}"])
            command.extend(["-i", str(wav), "-ac", "2", "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)])
            subprocess.run(command, **options)
            if mp3.stat().st_size < 100:
                raise ValueError("Empty decoded PRAGMATA voice")
            mp3.replace(destination)
        return filename

    def schedule(
        self,
        text_id: str,
        line_id: int,
        callback: Callable[[int, str | None, bool], None],
        english: str | None = None,
    ) -> bool:
        if not self.has(text_id) or not self._slots.acquire(blocking=False):
            return False

        def work() -> None:
            result = None
            try:
                result = self.extract(text_id, line_id, english)
                self.last_error = None
            except Exception as error:
                self.last_error = str(error)
            finally:
                self._slots.release()
            callback(line_id, result, result is not None)

        self._executor.submit(work)
        return True

    def close(self) -> None:
        self._executor.shutdown(wait=True)
