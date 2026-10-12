"""Verified bilingual Honkai Impact 3rd dialogue and installed Mandarin audio.

The public 4.7 catalog supplies explicit TextMap hashes and voice-event IDs.
Every playable mapping is validated against the user's installed Chinese bank
and media tables. Newer/unmapped content has no OCR or recorded-audio fallback.
No Unity assets, game text, voice packs or catalogs are distributed with us.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct

from .bilingual import contains_han
from .game_tools import download
from .nte_assets import wwise_hash
from .textmaps import display_text

CATALOG_REVISION = "01d7afbaf99ff7d3d027e27fe9a4b363a2db7cc1"
CATALOG_VERSION = "4.7"
CATALOG_BASE = f"https://raw.githubusercontent.com/nairieberry/HonkaiImpactData/{CATALOG_REVISION}/Global/ExcelOutputAsset/"
CATALOG_FILES = ("Decrypted/TextMap_cn.json", "Decrypted/TextMap_en.json", "DialogData.json", "StageDialogData.json", "InLevelDialog.json")
MANDARIN = "chinese(prc)"


@dataclass(frozen=True)
class PackageEntry:
    offset: int
    size: int


def packages(install: Path) -> list[Path]:
    paths = [p for layer in ("StreamingAssets", "Persistent") for p in
             (install / "BH3_Data" / layer).rglob("AUDIO*.pck") if p.is_file()]
    return sorted(paths, key=lambda p: ("Persistent" in p.parts, str(p)))


def fingerprint(install: Path) -> str:
    values = [f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in packages(install)]
    # Bump the index when a reviewed catalog or parser revision changes too.
    return hashlib.sha256((CATALOG_REVISION + ":reader2|" + "|".join(values)).encode()).hexdigest()


def package_tables(path: Path) -> tuple[dict[int, str], dict[tuple[int, int], PackageEntry], dict[tuple[int, int], PackageEntry]]:
    total = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(28)
        if len(header) != 28 or header[:4] != b"AKPK":
            raise ValueError("Invalid Honkai audio package")
        size, endian, language_size, bank_size, sound_size, external_size = struct.unpack_from("<6I", header, 4)
        if endian != 1 or size != 20 + language_size + bank_size + sound_size + external_size or not 20 <= size <= min(total - 8, 32 * 1024 * 1024):
            raise ValueError("Unsupported Honkai package table layout")
        raw = stream.read(language_size + bank_size + sound_size + external_size)
    if len(raw) != language_size + bank_size + sound_size + external_size or language_size < 4:
        raise ValueError("Truncated Honkai package tables")
    language_raw = raw[:language_size]
    count = struct.unpack_from("<I", language_raw)[0]
    if 4 + count * 8 > language_size:
        raise ValueError("Invalid audio language table")
    languages = {}
    for i in range(count):
        offset, language_id = struct.unpack_from("<II", language_raw, 4 + i * 8)
        if offset < 4 + count * 8 or offset >= language_size or offset % 2:
            raise ValueError("Invalid audio language name")
        end = offset
        while end + 2 <= language_size and language_raw[end:end + 2] != b"\0\0":
            end += 2
        if end + 2 > language_size:
            raise ValueError("Unterminated audio language name")
        languages[language_id] = language_raw[offset:end].decode("utf-16-le").lower()

    def table(start: int, length: int) -> dict:
        data = raw[start:start + length]
        if len(data) < 4:
            raise ValueError("Missing audio table")
        entries = struct.unpack_from("<I", data)[0]
        if length != 4 + entries * 20:
            raise ValueError("Unsupported Honkai audio entries")
        result = {}
        for entry_id, block, length, position, language in struct.iter_unpack("<5I", data[4:]):
            position *= block or 1
            if language not in languages or length <= 0 or position < size + 8 or position + length > total:
                raise ValueError("Honkai audio entry exceeds package bounds")
            key = (entry_id, language)
            if key in result:
                raise ValueError("Duplicate Honkai audio entry")
            result[key] = PackageEntry(position, length)
        return result
    return languages, table(language_size, bank_size), table(language_size + bank_size, sound_size)


def read_entry(path: Path, entry: PackageEntry) -> bytes:
    if not 0 < entry.size <= 64 * 1024 * 1024 or entry.offset < 28 or entry.offset + entry.size > path.stat().st_size:
        raise ValueError("Original voice entry is outside its package")
    with path.open("rb") as stream:
        stream.seek(entry.offset)
        data = stream.read(entry.size)
    if len(data) != entry.size:
        raise ValueError("Original audio package changed while reading")
    return data


def bank_sources(data: bytes, bank_id: int) -> tuple[dict[int, int], dict[int, PackageEntry]]:
    """Wwise 135: accept one Play action targeting one language-specific sound.

    Reject switches, random containers, silence generators and multiple actions.
    IDs come from serialized event/action/source fields, never audio ordinals.
    """
    if len(data) < 20 or data[:4] != b"BKHD" or struct.unpack_from("<3I", data, 8) != (135, bank_id, wwise_hash(MANDARIN)):
        raise ValueError("Unsupported Honkai Chinese voice bank")
    objects, media = {}, {}
    position, didx, data_start, data_size = 0, b"", 0, 0
    while position + 8 <= len(data):
        kind, size = struct.unpack_from("<4sI", data, position)
        end = position + 8 + size
        if end > len(data):
            raise ValueError("Truncated Honkai bank")
        body = data[position + 8:end]
        if kind == b"HIRC":
            if len(body) < 4:
                raise ValueError("Missing Honkai bank objects")
            pos = 4
            for _ in range(struct.unpack_from("<I", body)[0]):
                if pos + 5 > len(body):
                    raise ValueError("Truncated Honkai bank object")
                obj_type, length = struct.unpack_from("<BI", body, pos)
                payload = body[pos + 5:pos + 5 + length]
                if len(payload) != length or length < 4:
                    raise ValueError("Invalid Honkai bank object size")
                oid = struct.unpack_from("<I", payload)[0]
                if oid in objects:
                    raise ValueError("Duplicate Honkai bank object")
                objects[oid] = (obj_type, payload)
                pos += 5 + length
            if pos != len(body):
                raise ValueError("Invalid Honkai hierarchy bounds")
        elif kind == b"DIDX":
            didx = body
        elif kind == b"DATA":
            data_start, data_size = position + 8, size
        position = end
    if position != len(data) or len(didx) % 12:
        raise ValueError("Invalid Honkai bank chunk bounds")
    for media_id, offset, size in struct.iter_unpack("<3I", didx):
        if not data_start or not size or offset + size > data_size:
            raise ValueError("Honkai media exceeds its bank")
        media[media_id] = PackageEntry(data_start + offset, size)
    events = {}
    for event_id, (obj_type, payload) in objects.items():
        if obj_type != 4 or len(payload) != 9 or payload[4] != 1:
            continue
        action_type, action = objects.get(struct.unpack_from("<I", payload, 5)[0], (0, b""))
        if action_type != 3 or len(action) < 10 or struct.unpack_from("<H", action, 4)[0] != 0x0403:
            continue
        sound_type, sound = objects.get(struct.unpack_from("<I", action, 6)[0], (0, b""))
        if sound_type != 2 or len(sound) < 18 or struct.unpack_from("<I", sound, 4)[0] & 0xf != 1 or not sound[17] & 1:
            continue
        events[event_id] = struct.unpack_from("<I", sound, 9)[0]
    return events, media


def _textmap(rows: list[dict]) -> dict[int, str]:
    values = defaultdict(set)
    for row in rows:
        values[row["Hash"]].add(display_text(row["Text"]))
    return {key: next(iter(texts)) for key, texts in values.items() if len(texts) == 1}


def catalog_links(catalog: dict) -> list[dict]:
    english, chinese = (_textmap(catalog[name]) for name in ("TextMap_en.json", "TextMap_cn.json"))
    records = []
    for table in ("DialogData.json", "StageDialogData.json", "InLevelDialog.json"):
        for row in catalog[table]:
            speaker = None
            pages = None
            if table == "DialogData.json":
                content = row["content"]
                hashes = [page['chatContent']['hash'] for page in content]
                if not hashes or len(set(hashes)) != len(hashes):
                    continue
                text_hash, event, identifier = content[0]["chatContent"]["hash"], row["audioID"], row["dialogID"]
                pages = [(english.get(key, ''), chinese.get(key, '')) for key in hashes]
                if any(not en or not contains_han(zh) for en, zh in pages):
                    continue
            elif table == "StageDialogData.json":
                text_hash, event, identifier = row["Content"]["hash"], row["AudioID"], row["DialogID"]
                speaker = row.get("Name", {}).get("hash")
            else:
                text_hash, event, identifier = row["content"]["hash"], row["audioID"], row["dialogID"]
                speaker = row.get("avatarName", {}).get("hash")
            en, zh = english.get(text_hash, ""), chinese.get(text_hash, "")
            if pages:
                en, zh = ' '.join(p[0] for p in pages), ' '.join(p[1] for p in pages)
            if not en or not contains_han(zh) or not re.fullmatch(r"VO_[A-Za-z0-9_]+", event):
                continue
            records.append({"text_id": f"honkai3:{table[:-5]}:{identifier}:{text_hash}",
                "english": en, "chinese": zh, "event": event,
                "speaker_english": english.get(speaker), "speaker_chinese": chinese.get(speaker)})
            if pages and len(pages) > 1:
                records[-1].update(ocr_english=[p[0] for p in pages], ocr_chinese=[p[1] for p in pages])
    return records


def _load_catalog(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    catalog = {}
    for relative in CATALOG_FILES:
        path = directory / Path(relative).name
        if not path.is_file():
            data = download(CATALOG_BASE + relative)
            value = json.loads(data)
            if not isinstance(value, list) or not value:
                raise ValueError("Honkai bilingual catalog is incomplete")
            temporary = path.with_suffix(".pending")
            temporary.write_bytes(data)
            temporary.replace(path)
        catalog[path.name] = json.loads(path.read_text(encoding="utf-8"))
    return catalog


def validate_catalog(catalog: dict) -> None:
    for name in ("TextMap_en.json", "TextMap_cn.json"):
        rows = catalog[name]
        if not isinstance(rows, list) or not rows or len(rows) > 1_000_000:
            raise ValueError("Honkai bilingual catalog is incomplete")
        for row in rows:
            if (not isinstance(row, dict) or type(row.get("Hash")) is not int or
                    not isinstance(row.get("Text"), str) or len(row["Text"]) > 32768):
                raise ValueError("Unsupported Honkai localization schema")
    for name in ("DialogData.json", "StageDialogData.json", "InLevelDialog.json"):
        if not isinstance(catalog[name], list) or len(catalog[name]) > 1_000_000:
            raise ValueError("Unsupported Honkai dialogue schema")
    if not catalog_links(catalog):
        raise ValueError("Catalog has no bilingual authored voice references")


def refresh_catalog(data_dir: Path, force=False) -> dict:
    from .game_catalogs import refresh_catalog as refresh
    return refresh("honkai3", data_dir, validate_catalog, force)


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    from .game_catalogs import read_snapshot
    stamp = fingerprint(install)
    snapshot = read_snapshot("honkai3", data_dir)
    label = "4.7 (older content only)" if not snapshot or snapshot['revision'] == CATALOG_REVISION else snapshot['revision'][:8]
    progress(f"Reading Honkai bilingual catalog {label}")
    catalog = snapshot['catalog'] if snapshot else _load_catalog(data_dir / "catalog" / CATALOG_REVISION)
    validate_catalog(catalog)
    records = catalog_links(catalog)
    wanted = {wwise_hash(row["event"]) for row in records}
    voices = defaultdict(dict)
    progress("Verifying exact Honkai Chinese events and original sources in installed packages")
    for path in packages(install):
        languages, banks, sounds = package_tables(path)
        for (bank, language), entry in banks.items():
            if languages[language] != MANDARIN:
                continue
            data = read_entry(path, entry)
            try:
                events, embedded = bank_sources(data, bank)
            except (ValueError, struct.error):
                continue  # Unknown bank versions never supply playable mappings.
            for event in wanted & events.keys():
                media = events[event]
                if media in embedded:
                    target = PackageEntry(entry.offset + embedded[media].offset, embedded[media].size)
                else:
                    target = sounds.get((media, language))
                if target is None:
                    continue
                with path.open("rb") as stream:
                    stream.seek(target.offset)
                    if stream.read(4) != b"RIFF":
                        continue
                # Multiple distinct performances for one event are ambiguous.
                identity = (path.relative_to(install).as_posix(), bank, media)
                voices[event][identity] = {"package": identity[0], "bank": bank, "event": event,
                                          "media": media, "language": language}
    verified = []
    for record in records:
        choices = voices.get(wwise_hash(record.pop("event")), {})
        if len(choices) == 1:
            record["audio"] = next(iter(choices.values()))
            verified.append(record)
    if not verified or fingerprint(install) != stamp:
        raise ValueError("No verified Honkai bilingual Mandarin voices are installed. Download Chinese story audio in-game, finish updates, then refresh. Content outside the available bilingual catalog remains unsupported.")
    return {"format": 1, "install": str(install), "fingerprint": stamp, "records": verified,
            "catalog_digest": snapshot['digest'] if snapshot else None,
            "catalog_revision": snapshot['revision'] if snapshot else CATALOG_REVISION,
            "message": f"{len(verified):,} verified Honkai bilingual Mandarin lines; limited to catalog {label} content"}


def extract_voice(install: Path, audio: dict, _executable: Path, _destination: Path) -> bytes:
    relative = audio.get("package", "")
    path = (install / relative).resolve()
    if not path.is_relative_to(install.resolve()) or path not in [p.resolve() for p in packages(install)]:
        raise ValueError("Invalid Honkai original voice package")
    languages, banks, sounds = package_tables(path)
    bank, language, event, media = (audio[name] for name in ("bank", "language", "event", "media"))
    if languages.get(language) != MANDARIN:
        raise ValueError("Honkai voice language is not verified Mandarin")
    entry = banks[(bank, language)]
    events, embedded = bank_sources(read_entry(path, entry), bank)
    if events.get(event) != media:
        raise ValueError("Honkai voice mapping changed; refresh game data")
    target = PackageEntry(entry.offset + embedded[media].offset, embedded[media].size) if media in embedded else sounds[(media, language)]
    data = read_entry(path, target)
    if data[:4] != b"RIFF":
        raise ValueError("Honkai original voice is not a supported WEM")
    return data


def extract_voices(install: Path, audios: list[dict], _executable: Path, _destination: Path) -> list[bytes]:
    allowed = {p.resolve() for p in packages(install)}
    tables, decoded_banks, result = {}, {}, []
    for audio in audios:
        path = (install / audio.get('package', '')).resolve()
        if not path.is_relative_to(install.resolve()) or path not in allowed:
            raise ValueError('Invalid Honkai original voice package')
        if path not in tables:
            tables[path] = package_tables(path)
        languages, banks, sounds = tables[path]
        bank, language, event, media = (audio[name] for name in ('bank', 'language', 'event', 'media'))
        if languages.get(language) != MANDARIN:
            raise ValueError('Honkai voice language is not verified Mandarin')
        entry = banks[(bank, language)]
        key = (path, bank, language)
        if key not in decoded_banks:
            decoded_banks[key] = bank_sources(read_entry(path, entry), bank)
        events, embedded = decoded_banks[key]
        if events.get(event) != media:
            raise ValueError('Honkai voice mapping changed; refresh game data')
        target = PackageEntry(entry.offset + embedded[media].offset, embedded[media].size) if media in embedded else sounds[(media, language)]
        data = read_entry(path, target)
        if data[:4] != b'RIFF':
            raise ValueError('Honkai original voice is not a supported WEM')
        result.append(data)
    return result
