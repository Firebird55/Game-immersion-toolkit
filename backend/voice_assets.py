"""Read-only access to ZZZ's Mandarin Wwise external voice files.

Only exact GalScript text-id -> source -> FNV-1 matches are accepted. No
transcript similarity or guessed dialogue ordinals are used here.
"""
from __future__ import annotations

import json
import hashlib
import re
import struct
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from dataclasses import dataclass
from pathlib import Path

from .textmaps import normalize_english
from .media_tools import ffmpeg_executable


def voice_hash(path: str) -> int:
    value = 0xCBF29CE484222325
    for byte in path.lower().encode("utf-8"):
        value = ((value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ byte
    return value


def voice_manifest_key(text_id: str, english: str | None = None) -> str:
    """Address gender-specific assets without changing the official TextMap ID."""
    normalized = normalize_english(english or "")
    return f"{text_id}\0{normalized}" if normalized else text_id


@dataclass(frozen=True)
class VoiceEntry:
    package: Path
    offset: int
    size: int
    file_id: int

    def read(self) -> bytes:
        with self.package.open("rb") as stream:
            stream.seek(self.offset)
            data = stream.read(self.size)
        if len(data) != self.size or data[:4] != b"RIFF":
            raise ValueError("Voice asset missing, changed, or not a RIFF WEM")
        return data


def read_external_table(package: Path) -> list[VoiceEntry]:
    """Read the small PCK table, never the complete audio package."""
    size = package.stat().st_size
    with package.open("rb") as stream:
        header = stream.read(28)
        if len(header) < 28 or header[:4] != b"AKPK":
            raise ValueError("Not a Wwise PCK")
        header_size, flag, languages, banks, sounds, externals = struct.unpack_from("<6I", header, 4)
        if flag != 1 or not 16 <= header_size <= min(size, 32 * 1024 * 1024):
            raise ValueError("Unsupported PCK header")
        if languages + banks + sounds + 16 >= header_size:
            return []
        offset = 28 + languages + banks + sounds
        if not 4 <= externals <= 32 * 1024 * 1024 or offset + externals > min(size, header_size + 8):
            raise ValueError("Invalid external table bounds")
        stream.seek(offset)
        table = stream.read(externals)
    if len(table) != externals:
        raise ValueError("Truncated external table")
    count = struct.unpack_from("<I", table)[0]
    if count == 0:
        return []
    if externals != 4 + count * 24:
        raise ValueError("Unsupported external entry layout")
    entries = []
    for file_id, block, length, position, _language in struct.iter_unpack("<Q4I", table[4:]):
        position *= block or 1
        if not 0 < length <= 64 * 1024 * 1024 or position < header_size or position + length > size:
            raise ValueError("External voice outside package")
        entries.append(VoiceEntry(package, position, length, file_id))
    return entries


def index_mandarin(game_data: Path) -> dict[int, VoiceEntry]:
    entries: dict[int, VoiceEntry] = {}
    # Persistent updates take precedence over base packages.
    for directory in ("StreamingAssets", "Persistent"):
        root = game_data / directory / "Audio/Windows/Full/Cn"
        for package in sorted(root.glob("*.pck")):
            for entry in read_external_table(package):
                entries[entry.file_id] = entry
    return entries


def merge_valid_manifest_entries(previous: dict, refreshed: dict) -> dict:
    """Preserve still-valid exact mappings when an incremental scan is added."""
    merged = {}
    for text_id, item in previous.items():
        try:
            path = Path(item["package"])
            stat = path.stat()
            valid = (
                stat.st_size == item["package_size"]
                and stat.st_mtime_ns == item["package_mtime_ns"]
                and (voice_hash(item["source"]) == int(item["file_id"], 16)
                     or (item.get("matched_by") == "authored_cinematic_event" and not item["source"]
                         and re.fullmatch(r"Play_vo_[A-Za-z0-9_]+", item.get("event", ""), re.I)
                         and 0 < int(item["file_id"], 16) <= 0xffffffff))
                and 0 < item["size"] <= 64 * 1024 * 1024
                and 28 <= item["offset"] < stat.st_size
                and item["offset"] + item["size"] <= stat.st_size
            )
        except (KeyError, OSError, TypeError, ValueError):
            valid = False
        if valid:
            merged[text_id] = item
    merged.update(refreshed)
    return merged


def resolve_links(links: list[dict], prefixes: list[str], entries: dict[int, VoiceEntry], *, namespace='chinese(prc)') -> dict[str, dict]:
    by_speaker: dict[str, list[str]] = {}
    for prefix in prefixes:
        if "/VO_" in prefix:
            speaker = prefix.rstrip("/").rsplit("/VO_", 1)[1].lower()
            by_speaker.setdefault(speaker, []).append(prefix)
    candidates: dict[str, dict[int, str]] = {}
    for link in links:
        source, text_id = link["source"], link["text_id"]
        manifest_key = voice_manifest_key(text_id, link.get("english"))
        paths = [source] if "/" in source else [
            prefix + source for token in source.lower().split("_")
            for prefix in by_speaker.get(token, [])
        ]
        found = False
        for path in paths:
            full = f"{namespace}/ex/{path}.wem"
            hashed = voice_hash(full)
            if hashed in entries:
                candidates.setdefault(manifest_key, {})[hashed] = full
                found = True
        if not found and "/" not in source:
            # VoiceData's prefix list can lag a newly installed chapter. The
            # Wwise file ID validates path guesses exactly, so try conventional
            # version/speaker paths only when metadata found no real asset.
            ignored = {
                "galgame", "ongoinglevel", "level", "main", "companion",
                "chapter", "event", "activity",
            }
            speakers = {
                token for token in source.split("_")
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", token)
                and token.casefold() not in ignored
                and not token.casefold().startswith(("chapter", "ver"))
            }
            source_kind = source.casefold()
            families = (
                ["VO_Ongoing"] if source_kind.startswith("ongoinglevel_")
                else ["VO_Level"] if source_kind.startswith("level_")
                else ["VO_Galgame"]
            )
            for speaker in speakers:
                for major in range(1, 10):
                    for minor in range(10):
                        for family in families:
                            path = f"{family}/Ver{major}_{minor}/VO_{speaker}/{source}"
                            full = f"{namespace}/ex/{path}.wem"
                            hashed = voice_hash(full)
                            if hashed in entries:
                                candidates.setdefault(manifest_key, {})[hashed] = full
    result = {}
    for text_id, values in candidates.items():
        if len(values) != 1:
            continue  # Ambiguous voice variant: preserve recording fallback.
        hashed, source = next(iter(values.items()))
        entry = entries[hashed]
        result[text_id] = {
            "source": source, "file_id": f"{hashed:016x}",
            "package": str(entry.package), "offset": entry.offset, "size": entry.size,
        }
    return result


class VoiceAssetService:
    """Small persistent manifest; decode only requested lines, off the OCR thread."""

    def __init__(
        self,
        manifest: Path,
        decoder: Path,
        output_dir: Path,
        learned_manifest: Path | None = None,
    ):
        self.manifest = manifest
        self.learned_manifest = learned_manifest
        self.decoder = decoder
        self.output_dir = output_dir
        self._entries: dict[str, dict] = {}
        self._learned_entries: dict[str, dict] = {}
        self._manifest_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zzz-original-voice")
        self._slots = threading.BoundedSemaphore(8)
        self.last_error: str | None = None
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                raise ValueError("Unsupported original voice manifest")
            self._entries = data["entries"]
            if learned_manifest and learned_manifest.exists():
                learned = json.loads(learned_manifest.read_text(encoding="utf-8"))
                if learned.get("version") != 1 or not isinstance(learned.get("entries"), dict):
                    raise ValueError("Unsupported learned voice manifest")
                self._learned_entries = learned["entries"]
                self._entries.update(self._learned_entries)
        except (OSError, ValueError, KeyError) as error:
            self.last_error = str(error)
        self.ready = bool(self._entries and decoder.is_file() and ffmpeg_executable())

    def has(self, text_id: str) -> bool:
        return self.has_variant(text_id)

    def _entry_key(self, text_id: str, english: str | None = None) -> str | None:
        variant = voice_manifest_key(text_id, english)
        with self._manifest_lock:
            if variant in self._entries:
                return variant
            if text_id in self._entries:
                return text_id
        return None

    def has_variant(self, text_id: str, english: str | None = None) -> bool:
        entry_key = self._entry_key(text_id, english)
        if not self.ready or entry_key is None:
            return False
        item = self._entries[entry_key]
        try:
            stat = Path(item["package"]).stat()
            return stat.st_size == item["package_size"] and stat.st_mtime_ns == item["package_mtime_ns"]
        except OSError:
            return False

    def reload(self, manifest: Path) -> None:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("entries"), dict):
            raise ValueError("Unsupported original voice manifest")
        with self._manifest_lock:
            self.manifest = manifest
            self._entries = {**data["entries"], **self._learned_entries}
        self.ready = bool(self._entries and self.decoder.is_file() and ffmpeg_executable())
        self.last_error = None

    def status(self) -> dict:
        return {
            "ready": self.ready,
            "mapped_lines": len(self._entries),
            "learned_lines": len(self._learned_entries),
            "last_error": self.last_error,
        }

    def source_for(self, text_id: str, english: str | None = None) -> str:
        entry_key = self._entry_key(text_id, english)
        with self._manifest_lock:
            return str(self._entries.get(entry_key or "", {}).get("source", ""))

    def learn(self, text_id: str, entry: VoiceEntry) -> None:
        """Persist a fingerprint-verified TextMap alias to an unnamed WEM."""
        if self.learned_manifest is None:
            raise ValueError("Learned voice manifest is not configured")
        data = entry.read()
        stat = entry.package.stat()
        item = {
            "source": "",
            "file_id": f"{entry.file_id:016x}",
            "package": str(entry.package),
            "package_size": stat.st_size,
            "package_mtime_ns": stat.st_mtime_ns,
            "offset": entry.offset,
            "size": entry.size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "matched_by": "audio_fingerprint",
        }
        with self._manifest_lock:
            self._learned_entries[text_id] = item
            self._entries[text_id] = item
            self.learned_manifest.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.learned_manifest.with_suffix(".pending")
            temporary.write_text(
                json.dumps({"version": 1, "entries": self._learned_entries}, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(self.learned_manifest)
        self.ready = bool(self._entries and self.decoder.is_file() and ffmpeg_executable())

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _read_voice(self, text_id: str, english: str | None = None) -> tuple[dict, bytes]:
        entry_key = self._entry_key(text_id, english)
        if entry_key is None:
            raise KeyError(text_id)
        item = self._entries[entry_key]
        path = Path(item["package"])
        stat = path.stat()
        if stat.st_size != item["package_size"] or stat.st_mtime_ns != item["package_mtime_ns"]:
            raise ValueError("Game audio package changed; rebuild the original voice index")
        if item.get("source") and voice_hash(item["source"]) != int(item["file_id"], 16):
            raise ValueError("Voice source hash mismatch")
        entry = VoiceEntry(path, item["offset"], item["size"], int(item["file_id"], 16))
        if entry.offset < 28 or not 0 < entry.size <= 64 * 1024 * 1024 or entry.offset + entry.size > stat.st_size:
            raise ValueError("Invalid voice asset bounds")
        data = entry.read()
        if item.get("sha256") and hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Learned voice asset checksum mismatch")
        if path.stat().st_mtime_ns != stat.st_mtime_ns:
            raise ValueError("Audio package changed during reading")
        return item, data

    def extract(self, text_id: str, line_id: int, english: str | None = None) -> str:
        item, data = self._read_voice(text_id, english)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"official-{line_id}-{item['file_id']}.mp3"
        destination = self.output_dir / filename
        # Decode into a task-owned temporary directory; publish only complete files.
        with tempfile.TemporaryDirectory(prefix="voice-", dir=self.output_dir) as scratch:
            scratch = Path(scratch)
            wem, wav, mp3 = scratch / "voice.wem", scratch / "voice.wav", scratch / "voice.mp3"
            wem.write_bytes(data)
            options = {"check": True, "capture_output": True, "timeout": 20,
                       "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            subprocess.run([str(self.decoder), "-o", str(wav), str(wem)], **options)
            subprocess.run([ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin",
                            "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)], **options)
            if mp3.stat().st_size < 100:
                raise ValueError("Empty decoded voice")
            mp3.replace(destination)
        return filename

    def extract_batch(self, requests: list[tuple[str, int, str | None]]) -> list[str]:
        """Amortize decoder launches without concatenating distinct performances."""
        if not 1 <= len(requests) <= 8:
            raise ValueError("Voice batches must contain one to eight clips")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="voice-batch-", dir=self.output_dir) as scratch_value:
            scratch = Path(scratch_value)
            inputs, outputs, filenames = [], [], []
            for index, (text_id, line_id, english) in enumerate(requests):
                item, data = self._read_voice(text_id, english)
                wem = scratch / f"{index}.wem"
                wem.write_bytes(data)
                inputs.append(wem)
                outputs.append(scratch / f"{index}.mp3")
                filenames.append(f"official-{line_id}-{item['file_id']}.mp3")
            options = {"check": True, "capture_output": True, "timeout": 20 * len(requests),
                       "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            # Vgmstream accepts several inputs and writes <input>.wav for each.
            subprocess.run([str(self.decoder), *map(str, inputs)], **options)
            command = [ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin",
                       "-filter_threads", "1", "-filter_complex_threads", "1"]
            for wem in inputs:
                command += ["-i", str(wem) + ".wav"]
            for index, mp3 in enumerate(outputs):
                command += ["-map", f"{index}:a:0", "-codec:a", "libmp3lame", "-q:a", "2",
                            "-threads", "1", str(mp3)]
            subprocess.run(command, **options)
            if any(not mp3.is_file() or mp3.stat().st_size < 100 for mp3 in outputs):
                raise ValueError("Empty or missing decoded batch voice")
            for mp3, filename in zip(outputs, filenames):
                mp3.replace(self.output_dir / filename)
        return filenames

    def schedule(
        self, text_id: str, line_id: int,
        callback: Callable[[int, str | None, bool], None],
        english: str | None = None,
    ) -> bool:
        if not self.has_variant(text_id, english) or not self._slots.acquire(blocking=False):
            return False
        def work():
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


class AudioSourceChoice:
    """Wait for the asset attempt before publishing a parallel recording result."""

    def __init__(self, publish: Callable, discard: Callable, cancel_recording: Callable):
        self._lock = threading.Lock()
        self._state = "pending"
        self._recorded: tuple | None = None
        self.publish, self.discard, self.cancel_recording = publish, discard, cancel_recording

    def recording_result(self, line_id: int, path: str | None, voiced: bool) -> None:
        with self._lock:
            if self._state == "original":
                self.discard(path)
            elif self._state == "fallback":
                self.publish(line_id, path, voiced)
            else:
                self._recorded = (line_id, path, voiced)

    def original_result(self, line_id: int, path: str | None, voiced: bool) -> None:
        with self._lock:
            if path and voiced:
                self._state = "original"
                self.cancel_recording(line_id)
                if self._recorded:
                    self.discard(self._recorded[1])
                self.publish(line_id, path, True)
            else:
                self._state = "fallback"
                if self._recorded:
                    self.publish(*self._recorded)
