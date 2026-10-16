from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .media_tools import ffmpeg_executable


ZERO_GUID = "00000000-0000-0000-0000-000000000000"
INDEX_FORMAT = 4
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


def read_bank_play_layers(path: Path, *, allowed_versions: tuple[int, ...] = (150,),
                          switch_states: dict[int, int] | None = None) -> dict[int, list[dict[str, object]]]:
    """Read fixed Play -> layer -> source trees, preserving delays/gain.

    Switch containers require an explicit authored Wwise 154 group/value and
    a deterministic branch. Never mix alternatives or choose a default state.
    """
    data = path.read_bytes()
    objects = {}
    version = None
    offset = 0
    while offset + 8 <= len(data):
        tag, size = struct.unpack_from('<4sI', data, offset)
        body = data[offset + 8:offset + 8 + size]
        if len(body) != size:
            raise ValueError('Truncated Wwise bank')
        if tag == b'BKHD':
            version = _u32(body, 0)
        if tag == b'HIRC':
            pos = 4
            for _ in range(_u32(body, 0)):
                kind, length = struct.unpack_from('<BI', body, pos)
                payload = body[pos + 5:pos + 5 + length]
                objects[_u32(payload, 0)] = (kind, payload)
                pos += 5 + length
        offset += 8 + size
    if version not in allowed_versions:
        raise ValueError(f'Unsupported Wwise bank version {version}')
    nodes = {}
    children = {}
    selected_children = {}
    for oid, (kind, payload) in objects.items():
        if kind not in (2, 5, 6, 7, 9):
            continue
        pos, media = 4, None
        if kind == 2:
            plugin = _u32(payload, pos)
            if plugin & 0xF != 1:
                continue
            media = _u32(payload, pos + 5)
            # Wwise 154 prefetch sources insert cacheID before media size.
            # Treating it as size shifts every subsequent node property.
            cache_bytes = 4 if version == 154 and payload[pos+4] == 2 else 0
            pos += 14 + cache_bytes
        fx_count = payload[pos + 1]
        pos += 2 + (1 if fx_count else 0) + fx_count * 6
        metadata_count = payload[pos + 1]
        pos += 2 + metadata_count * 6
        parent = _u32(payload, pos + 4)
        pos += 9
        count = payload[pos]
        ids = payload[pos + 1:pos + 1 + count]
        values = struct.unpack_from(f'<{count}f', payload, pos + 1 + count)
        props = dict(zip(ids, values))
        range_pos = pos + 1 + count * 5
        range_count = payload[range_pos]
        range_ids = payload[range_pos + 1:range_pos + 1 + range_count]
        if set(range_ids) & {0, 0x22}:
            # Keep the child in the tree so its parent cannot silently render
            # only the remaining, supported sources.
            kind = -1
        nodes[oid] = (kind, media, props.get(0, 0.0), props.get(0x22, 0.0))
        children.setdefault(parent, []).append(oid)
        if kind == 6 and version == 154 and switch_states:
            # Narrowly supported NTE player-sex switches. Only a caller's
            # explicit, verified group/value selects a branch. Unknown effects,
            # positioning, states, RTPCs, fades and continuous validation stay
            # unsupported; never mix alternatives or use a default value.
            try:
                extra = range_pos + 1 + range_count * 9
                if fx_count or metadata_count or range_count or payload[extra:extra+6] != bytes(6):
                    continue
                if payload[extra+6] or payload[extra+10:extra+16] != bytes(6):
                    continue
                p = extra + 16
                group_type, group = payload[p], _u32(payload, p+1)
                if group_type != 0 or group not in switch_states or payload[p+9]:
                    continue
                p += 10
                count = _u32(payload, p); p += 4
                if not 0 < count <= 16:
                    continue
                listed = set(struct.unpack_from(f'<{count}I', payload, p)); p += count*4
                group_count = _u32(payload, p); p += 4
                if not 0 < group_count <= 16:
                    continue
                branches = {}
                for _ in range(group_count):
                    state, item_count = struct.unpack_from('<II', payload, p); p += 8
                    if item_count != 1 or state in branches:
                        raise ValueError('Unsupported switch branch')
                    branches[state] = _u32(payload, p); p += 4
                params = _u32(payload, p); p += 4
                if params != count:
                    continue
                checked = set()
                for _ in range(params):
                    child = _u32(payload, p)
                    if payload[p+4:p+13] != bytes(9) or child not in listed or child in checked:
                        raise ValueError('Unsupported switch parameters')
                    checked.add(child); p += 13
                child = branches.get(switch_states[group])
                if p == len(payload) and child in listed and set(branches.values()) <= listed:
                    selected_children[oid] = child
            except (ValueError, IndexError, struct.error):
                continue

    def walk(oid, gain=0.0, delay=0.0, visiting=frozenset()):
        if oid in visiting or oid not in nodes:
            raise ValueError('Incomplete Wwise play tree')
        kind, media, volume, wait = nodes[oid]
        gain, delay = gain + volume, delay + wait
        if kind == 2:
            return [{'media_id': media, 'gain_db': gain, 'delay_seconds': delay}]
        if kind == 6 and oid in selected_children and selected_children[oid] in children.get(oid, []):
            return walk(selected_children[oid], gain, delay, visiting | {oid})
        if kind not in (7, 9) or not children.get(oid):
            raise ValueError('Voice event uses a dynamic container')
        return [item for child in children[oid]
                for item in walk(child, gain, delay, visiting | {oid})]

    events = {}
    for oid, (kind, payload) in objects.items():
        if kind != 4 or payload[4] >= 128:
            continue
        actions = struct.unpack_from(f'<{payload[4]}I', payload, 5)
        layers = []
        try:
            for aid in actions:
                akind, action = objects[aid]
                if akind != 3 or struct.unpack_from('<H', action, 4)[0] != 0x0403:
                    raise ValueError('Unsupported event action')
                layers.extend(walk(_u32(action, 6)))
            if layers:
                events[oid] = layers
        except (KeyError, ValueError):
            continue
    return events


def build_sound_id_audio_map(graph: dict[str, object], bank_root: Path | None = None) -> dict[int, dict[str, object]]:
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
        bank_path = bank_root / f'{bank}.sbnk.1.x64.zhcn' if bank_root else None
        play_layers = read_bank_play_layers(bank_path) if bank_path and bank_path.is_file() else {}
        for event_id, event in dict(events).items():
            index = record_index.get((str(bank), int(event_id)))
            candidates = record_media.get(index, set()) & available if index is not None else set()
            layers = play_layers.get(int(event_id), [])
            layered = len(candidates) > 1 and {x['media_id'] for x in layers} == candidates
            if len(candidates) != 1 and not layered:
                continue
            media_id = min(candidates)
            audio = {
                "bank": str(bank),
                "media_id": media_id,
                "index": str(package.get("index", "")),
                "streaming": str(package.get("streaming", "")),
                "mapping": "sound_id",
            }
            if layered:
                audio['layers'] = layers
                audio['mapping'] = 'sound_id_layers'
                # Shared radio/noise layers may loop. Bound playback by the
                # sentence-specific sources, including their authored delays.
                exclusive = [m for m in candidates if len(source_events.get(str(m), [])) == 1]
                audio['duration_media_ids'] = exclusive or sorted(candidates)
            for trigger_id in event.get("trigger_ids", []):
                trigger = int(trigger_id)
                if trigger in mapped and mapped[trigger] != audio:
                    ambiguous.add(trigger)
                else:
                    mapped[trigger] = audio
    for trigger in ambiguous:
        mapped.pop(trigger, None)
    return mapped


def cutscene_audio_for_bank(graph: dict[str, object], bank: str, bank_root: Path | None = None) -> dict[str, object] | None:
    localized_bank = f"{bank}.zhcn"
    package = dict(graph.get("media_packages", {})).get(localized_bank)
    if not isinstance(package, dict):
        return None
    media_ids: set[int] = set()
    for path, links in dict(graph.get("media_links", {})).items():
        if str(path).casefold().endswith(f"/{bank}.sbnk.1.x64.zhcn") and isinstance(links, dict):
            media_ids.update(map(int, links.get(localized_bank, [])))
    layers = []
    if len(media_ids) > 1 and bank_root:
        path = bank_root / f'{bank}.sbnk.1.x64.zhcn'
        if path.is_file():
            candidates = [ls for ls in read_bank_play_layers(path).values()
                          if {x['media_id'] for x in ls} == media_ids]
            if len(candidates) == 1:
                layers = candidates[0]
    if not media_ids or (len(media_ids) != 1 and not layers):
        return None
    result = {
        "bank": bank,
        "media_id": min(media_ids),
        "index": str(package.get("index", "")),
        "streaming": str(package.get("streaming", "")),
        "mapping": "timeline_guid",
    }
    if layers:
        result['layers'] = layers
    return result


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
    layers: tuple[dict[str, object], ...] = ()
    duration_media_ids: tuple[int, ...] = ()

    @property
    def media_ids(self) -> set[int]:
        return {int(layer["media_id"]) for layer in self.layers} or {self.media_id}


def _voice_mix(entry, waves, offset=0, prefix=''):
    paths, filters, ends = [], [], []
    layers = entry.layers or ({"media_id": entry.media_id},)
    for index, layer in enumerate(layers):
        media_id = int(layer["media_id"])
        path = waves[media_id]; paths.append(path)
        delay = max(0.0, float(layer.get("delay_seconds", 0)))
        gain = float(layer.get("gain_db", 0))
        filters.append(f"[{offset+index}:a]aformat=channel_layouts=stereo,volume={gain:.6f}dB,"
                       f"adelay={delay * 1000:.3f}:all=1[{prefix}a{index}]")
        if media_id in entry.duration_media_ids:
            with wave.open(str(path)) as stream:
                ends.append(delay + stream.getnframes() / stream.getframerate())
    inputs = "".join(f"[{prefix}a{i}]" for i in range(len(layers)))
    filters.append(f"{inputs}amix=inputs={len(layers)}:normalize=0:dropout_transition=0[{prefix}mix]")
    tail = f"[{prefix}mix]"
    if entry.start_seconds is not None and entry.end_seconds is not None:
        start = max(0.0, entry.start_seconds - 0.08)
        tail += f"atrim=start={start:.4f}:end={entry.end_seconds + 0.25:.4f},asetpts=PTS-STARTPTS,"
    elif ends:
        tail += f"atrim=end={max(ends):.4f},"
    filters.append(tail + f"alimiter=limit=0.95:level=0:latency=1[{prefix}out]")
    return paths, filters, f"[{prefix}out]"


def mix_voice_layers(entry: PragmataAudioEntry, waves: dict[int, Path], destination: Path) -> None:
    """Render fixed simultaneous layers; never choose/mix random alternatives."""
    paths, filters, label = _voice_mix(entry, waves)
    command = [ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin"]
    for path in paths:
        command += ['-i', str(path)]
    command += ['-filter_complex', ';'.join(filters), '-map', label, '-ac', '2',
                '-codec:a', 'libmp3lame', '-q:a', '2', str(destination)]
    subprocess.run(command, check=True, capture_output=True, timeout=90,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def mix_voice_batches(requests):
    command = [ffmpeg_executable(), '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-filter_threads', '1', '-filter_complex_threads', '1']
    filters, outputs, offset = [], [], 0
    for number, (entry, waves, destination) in enumerate(requests):
        paths, clip_filters, label = _voice_mix(entry, waves, offset, f'clip{number}_')
        for path in paths:
            command += ['-i', str(path)]
        filters.extend(clip_filters); offset += len(paths)
        outputs += ['-map', label, '-ac', '2', '-codec:a', 'libmp3lame', '-q:a', '2',
                    '-threads', '1', str(destination)]
    command += ['-filter_complex', ';'.join(filters), *outputs]
    subprocess.run(command, check=True, capture_output=True, timeout=90 * len(requests),
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


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
        self._package_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pragmata-original-voice")
        self._slots = threading.BoundedSemaphore(8)
        self.last_error: str | None = None
        self.ready = False
        self._loaded_signature = None
        self.reload()

    def reload(self) -> bool:
        try:
            stat = self.manifest.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if self.ready and self._loaded_signature == signature:
                return True
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
                    layers=tuple(audio.get("layers", [])),
                    duration_media_ids=tuple(map(int, audio.get("duration_media_ids", []))),
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
                    and ffmpeg_executable()
                )
                self.last_error = None
                self._loaded_signature = signature
            return self.ready
        except (OSError, ValueError, KeyError, TypeError) as error:
            with self._lock:
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
        # The unpacker uses one project list and shared extraction cache. Only
        # package preparation is serialized; independent decoding stays parallel.
        with self._package_lock:
            return self._prepare_package(entry)

    def _prepare_package(self, entry: PragmataAudioEntry) -> Path:
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
                        for media_id in entry.media_ids:
                            read_pck_media(candidate, media_id)
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
                    for media_id in entry.media_ids:
                        read_pck_media(candidate, media_id)
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
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"official-pragmata-{line_id}-{entry.media_id}.mp3"
        destination = self.output_dir / filename
        with tempfile.TemporaryDirectory(prefix="pragmata-voice-", dir=self.output_dir) as scratch_value:
            scratch = Path(scratch_value)
            mp3 = scratch / "voice.mp3"
            options = {
                "check": True,
                "capture_output": True,
                "timeout": 90,
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
            }
            waves = {}
            for media_id in entry.media_ids:
                wem, wav = scratch / f"{media_id}.wem", scratch / f"{media_id}.wav"
                wem.write_bytes(read_pck_media(package, media_id))
                subprocess.run([str(self.decoder), "-o", str(wav), str(wem)], **options)
                waves[media_id] = wav
            mix_voice_layers(entry, waves, mp3)
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

    def extract_batch(self, requests) -> list[str]:
        if not 1 <= len(requests) <= 8:
            raise ValueError('Voice batches must contain one to eight clips')
        with self._lock:
            entries = [self._entries[text_id] for text_id, number, english in requests]
        if sum(len(entry.media_ids) for entry in entries) > 64:
            return [self.extract(*request) for request in requests]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filenames = [f'official-pragmata-{number}-{entry.media_id}.mp3' for entry, (text_id, number, english) in zip(entries, requests)]
        with tempfile.TemporaryDirectory(prefix='pragmata-batch-', dir=self.output_dir) as value:
            scratch = Path(value)
            sources, clips = {}, []
            for number, entry in enumerate(entries):
                package = self._package(entry)
                waves = {}
                for media_id in sorted(entry.media_ids):
                    key = (package, media_id)
                    if key not in sources:
                        wem = scratch / f'{len(sources)}.wem'
                        wem.write_bytes(read_pck_media(package, media_id))
                        sources[key] = wem
                    waves[media_id] = Path(str(sources[key]) + '.wav')
                clips.append((entry, waves, scratch / f'{number}.mp3'))
            subprocess.run([str(self.decoder), *map(str, sources.values())], check=True, capture_output=True,
                           timeout=90 * len(requests), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            mix_voice_batches(clips)
            if any(not path.is_file() or path.stat().st_size < 100 for entry, waves, path in clips):
                raise ValueError('Empty decoded PRAGMATA batch voice')
            for (entry, waves, path), filename in zip(clips, filenames):
                path.replace(self.output_dir / filename)
        return filenames

    def close(self) -> None:
        self._executor.shutdown(wait=True)
