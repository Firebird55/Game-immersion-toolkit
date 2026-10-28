from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.pragmata_audio import (
    INDEX_FORMAT,
    build_sound_id_audio_map,
    cutscene_audio_for_bank,
    read_tmlfsm_dialogue_segments,
)


from backend.runtime_paths import data_root as runtime_data_root
DATA_DIR = runtime_data_root(Path(os.environ.get("PROXY_TRANSCRIPT_PROJECT_ROOT", PROJECT_ROOT))) / "pragmata"
RELEASE_LIST_URL = (
    "https://raw.githubusercontent.com/Ekey/REE.PAK.Tool/main/Projects/P_STM_Release.list"
)
SOUND_GRAPH_URL = (
    "https://raw.githubusercontent.com/seifhassine/REasy/master/"
    "resources/data/sound/pragmata.json.gz"
)
KEY = bytes(
    [0xCF, 0xCE, 0xFB, 0xF8, 0xEC, 0x0A, 0x33, 0x66,
     0x93, 0xA9, 0x1D, 0x93, 0x50, 0x39, 0x5F, 0x09]
)
REF_RE = re.compile(r"<REF\s+([^>]+)>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPEAKER_CODE_RE = re.compile(r"_(Ch\d{5})$", re.IGNORECASE)


def dialogue_kind(relative: str, name: str) -> str | None:
    """Select authored dialogue and narrative bodies, never generic UI labels."""
    relative, name = relative.casefold(), name.casefold()
    if relative.startswith('mes_main/event/cutscene/'):
        return 'cutscene'
    if relative.startswith('mes_main/conv/'):
        if '/conv_battle' in relative:
            return 'combat'
        if relative.endswith(('conv_gimmick.msg.23', 'conv_stagechat.msg.23')):
            return 'ambient'
        if relative.endswith('conv_stagetips.msg.23'):
            return 'guidance'
        return 'conversation'
    if not relative.startswith('mes_main/archive/'):
        return None
    filename = relative.rsplit('/', 1)[-1]
    if filename in ('archive_figure.msg.23', 'archive_hologram.msg.23', 'archive_talk.msg.23'):
        return 'readable' if re.search(r'_desc(?:_\d+)?$', name) else None
    if (filename in ('archive_shop.msg.23', 'archive_wall.msg.23')
            or re.fullmatch(r'archive_stage\d+\.msg\.23', filename)):
        return 'readable' if name.startswith('file_') and not name.endswith('_head') else None
    return None


def align(stream, boundary: int = 8) -> None:
    remainder = stream.tell() % boundary
    if remainder:
        stream.read(boundary - remainder)


def decrypt(data: bytes) -> bytes:
    result = bytearray(data)
    previous = 0
    for index, current in enumerate(result):
        result[index] = current ^ previous ^ KEY[index & 0xF]
        previous = current
    return bytes(result)


def read_strings(pool: bytes) -> dict[int, str]:
    decoded = pool.decode("utf-16-le")
    result: dict[int, str] = {}
    start = 0
    for index, character in enumerate(decoded):
        if character == "\0":
            result[start * 2] = decoded[start:index]
            start = index + 1
    return result


def read_msg(path: Path, locales=None) -> list[dict[str, object]]:
    """Read the subset of RE Engine MSG v23 needed for localization indexing."""
    with path.open("rb") as stream:
        version, magic = struct.unpack("<I4s", stream.read(8))
        if magic != b"GMSG":
            raise ValueError(f"Not an RE Engine MSG file: {path}")
        _header_offset = struct.unpack("<Q", stream.read(8))[0]
        entry_count, attribute_count, language_count = struct.unpack("<III", stream.read(12))
        align(stream)
        data_offset = struct.unpack("<Q", stream.read(8))[0] if version > 12 else None
        unknown_offset, language_offset, attribute_offset, attribute_name_offset = struct.unpack(
            "<QQQQ", stream.read(32)
        )
        entry_offsets = [struct.unpack("<Q", stream.read(8))[0] for _ in range(entry_count)]
        stream.seek(unknown_offset + 8)
        stream.seek(language_offset)
        languages = [struct.unpack("<I", stream.read(4))[0] for _ in range(language_count)]
        align(stream)
        stream.seek(attribute_offset)
        attribute_types = [struct.unpack("<i", stream.read(4))[0] for _ in range(attribute_count)]
        align(stream)
        stream.seek(attribute_name_offset + attribute_count * 8)

        headers = []
        for offset in entry_offsets:
            stream.seek(offset)
            message_guid = str(uuid.UUID(bytes_le=stream.read(16)))
            sound_id = struct.unpack("<I", stream.read(4))[0]
            stream.read(4)   # hash/index
            name_offset, values_offset = struct.unpack("<QQ", stream.read(16))
            content_offsets = [struct.unpack("<Q", stream.read(8))[0] for _ in range(language_count)]
            headers.append((message_guid, sound_id, name_offset, values_offset, content_offsets))

        if data_offset is None:
            if headers:
                stream.seek(headers[0][3] + attribute_count * 8 * entry_count)
            data_offset = stream.tell()
        stream.seek(0, 2)
        end = stream.tell()
        stream.seek(data_offset)
        strings = read_strings(decrypt(stream.read(end - data_offset)) if version > 12 else stream.read())

    language_positions = {language: index for index, language in enumerate(languages)}
    english_index = language_positions.get(1)
    chinese_index = language_positions.get(13)
    if locales is None and (english_index is None or chinese_index is None):
        return []

    def text(offset: int) -> str:
        return strings.get(offset - data_offset, "")

    return [
        {
            "guid": message_guid,
            "sound_id": sound_id,
            "name": text(name_offset),
            "english": text(content_offsets[english_index]) if english_index is not None else '',
            "chinese": text(content_offsets[chinese_index]) if chinese_index is not None else '',
            **({'texts': {locale: text(content_offsets[language_positions[index]]) for locale, index in locales.items()
                          if index in language_positions}} if locales is not None else {}),
        }
        for message_guid, sound_id, name_offset, _values_offset, content_offsets in headers
    ]


def find_install() -> Path | None:
    from backend.game_paths import discover_install
    configured = discover_install("pragmata")
    if configured:
        return configured
    candidates = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\PRAGMATA"),
        Path(r"C:\Program Files\Steam\steamapps\common\PRAGMATA"),
    ]
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.append(Path(f"{letter}:\\SteamLibrary\\steamapps\\common\\PRAGMATA"))
    for path in candidates:
        try:
            if (path / "PRAGMATA.exe").is_file():
                return path
        except OSError:
            # A locked or disconnected drive must not hide an install on a
            # later drive letter.
            continue
    return None


def fingerprint(install: Path) -> str:
    return "|".join(
        f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}"
        for path in sorted(install.glob("re_chunk_*.pak*"), key=lambda item: item.name)
    )


def update_asset_list(tools: Path, locale_code='zhcn') -> None:
    projects = tools / "Projects"
    projects.mkdir(parents=True, exist_ok=True)
    release = projects / "P_STM_Release.list"
    try:
        request = urllib.request.Request(RELEASE_LIST_URL, headers={"User-Agent": "ProxyTranscript/1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            release.write_bytes(response.read())
    except Exception:
        if not release.is_file():
            raise
    paths = [
        line.strip()
        for line in release.read_text(encoding="utf-8-sig").splitlines()
        if line.casefold().startswith("natives/stm/message/")
        or (
            line.casefold().startswith("natives/stm/sound/wwise/")
            # Several authored voice banks (earth, chp7/chp8, cmn) do not use
            # the "dialogue" suffix. Select localized headers, not voice media.
            and line.casefold().endswith(f'.sbnk.1.x64.{locale_code}')
        )
        or (
            line.casefold().startswith("natives/stm/event/cs/")
            and "/flow/" in line.casefold()
            and ".tmlfsm2." in line.casefold()
        )
    ]
    (projects / "P_PRAGMATA_INDEX.list").write_text("\n".join(paths) + "\n", encoding="utf-8")


def archive_order(path: Path) -> tuple[int, str]:
    name = path.name.casefold()
    return (int("patch" in name), name)


def extract_assets(install: Path, destination: Path, tools: Path, locale_code=None) -> None:
    from backend.ree_extractor import extract_project
    if locale_code is None:
        update_asset_list(tools)
    else:
        update_asset_list(tools, locale_code)
    destination.mkdir(parents=True, exist_ok=True)
    for archive in sorted(install.glob("re_chunk_*.pak*"), key=archive_order):
        extract_project(tools, 'P_PRAGMATA_INDEX', archive, destination)


def clean_text(value: str, references: dict, language: str) -> str:
    def resolve(text, visiting=frozenset()):
        def replace(match):
            name = match[1]
            candidates = references.get(language, {}).get(name, set())
            if name in visiting or len(candidates) != 1:
                return match[0]
            return resolve(next(iter(candidates)), visiting | {name})
        return REF_RE.sub(replace, text)

    value = resolve(value)
    # A missing, conflicting or cyclic alias invalidates the whole text.
    if REF_RE.search(value):
        return ''
    value = TAG_RE.sub("", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(line.split()) for line in value.splitlines()).strip()


def load_sound_graph(directory=None) -> dict[str, object]:
    path = (directory or DATA_DIR) / "sound-graph.json.gz"
    try:
        request = urllib.request.Request(SOUND_GRAPH_URL, headers={"User-Agent": "ProxyTranscript/1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            temporary = path.with_suffix(".pending")
            temporary.write_bytes(response.read())
            with gzip.open(temporary, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            temporary.replace(path)
            return payload
    except Exception:
        if not path.is_file():
            raise
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)


def build_index(
    message_root: Path,
    install: Path | None,
    timeline_root: Path | None = None,
    sound_graph: dict[str, object] | None = None,
) -> dict[str, object]:
    parsed: list[tuple[Path, list[dict[str, object]]]] = []
    references: dict[str, dict[str, set[str]]] = {}
    for path in sorted(message_root.rglob("*.msg.*")):
        entries = read_msg(path)
        parsed.append((path, entries))
        for entry in entries:
            for locale, field in [('en', 'english'), ('zh-Hans', 'chinese')]:
                text = str(entry[field])
                if text:
                    references.setdefault(locale, {}).setdefault(str(entry['name']), set()).add(text)

    bank_root = message_root.parent / "sound" / "wwise"
    sound_audio = build_sound_id_audio_map(sound_graph, bank_root) if sound_graph else {}
    timeline_audio: dict[str, dict[str, object] | None] = {}
    voice_triggers = {int(trigger) for events in (sound_graph or {}).get('bank_events', {}).values()
                      for event in events.values() for trigger in event.get('trigger_ids', [])}
    voice_guids = set()
    if timeline_root is not None and sound_graph:
        for path in sorted(timeline_root.rglob("*.tmlfsm2.*")):
            bank_match = re.search(r"/(cs\d+)/flow/", path.as_posix(), re.IGNORECASE)
            if not bank_match:
                continue
            bank = f"{bank_match.group(1).lower()}_dialogue"
            base_audio = cutscene_audio_for_bank(sound_graph, bank, bank_root)
            try:
                for segment in read_tmlfsm_dialogue_segments(path):
                    guid = str(segment['guid']).lower()
                    if bank in sound_graph.get('banks', {}) or base_audio:
                        voice_guids.add(guid)
                    if base_audio is None:
                        continue
                    audio = {
                        **base_audio,
                        "start_seconds": segment["start_seconds"],
                        "end_seconds": segment["end_seconds"],
                    }
                    timeline_audio[guid] = audio if guid not in timeline_audio or timeline_audio[guid] == audio else None
            except (OSError, ValueError, struct.error):
                continue

    speakers: dict[str, list[str]] = {}
    records: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    unresolved_reasons: dict[str, str] = {}
    for path, entries in parsed:
        relative = path.relative_to(message_root).as_posix().casefold()
        for entry in entries:
            name = str(entry["name"])
            english = clean_text(str(entry["english"]), references, 'en')
            chinese = clean_text(str(entry["chinese"]), references, 'zh-Hans')
            if relative.endswith("ingame/speakername.msg.23") and english and chinese:
                speakers[english] = [english, chinese]
            kind = dialogue_kind(relative, name)
            if not kind or not english or not chinese:
                continue
            reason = (
                "credits" if name.startswith("OP_StaffList_") else
                "sound_effect_caption" if name.casefold().startswith("soundsupport_") else
                "rejected_development_text" if "#rejected#" in (english + chinese).casefold() else
                "nonverbal_caption" if not re.search(r"[A-Za-z]", english) or re.fullmatch(r"\[[^\]]+\]", english) else None
            )
            if reason:
                excluded.append({"text_id": f"{relative}:{name}", "reason": reason})
                continue
            code = SPEAKER_CODE_RE.search(name)
            record = {
                "text_id": f"{relative}:{name}",
                "english": english,
                "chinese": chinese,
                "source": relative,
                "speaker_code": code.group(1) if code else None,
                "dialogue_kind": kind,
            }
            audio = sound_audio.get(int(entry.get("sound_id") or 0))
            if audio is None:
                audio = timeline_audio.get(str(entry.get("guid") or "").lower())
            if audio and not (bank_root / (str(audio.get('bank', '')) + '.sbnk.1.x64.zhcn')).is_file():
                audio = None
            record['voice_status'] = ('voiced' if audio else 'unavailable'
                if int(entry.get('sound_id') or 0) in voice_triggers
                or str(entry.get('guid') or '').lower() in voice_guids else 'unknown')
            if audio is not None:
                record["audio"] = audio
            else:
                bank_name = f"{Path(relative).name.split('.')[0]}_dialogue"
                if "/cutscene/" in relative:
                    reason = ("no_audio_bank_in_asset_index" if bank_name not in (sound_graph or {}).get("banks", {})
                              else "no_subtitle_guid_interval")
                else:
                    reason = "no_unique_supported_event_tree"
                unresolved_reasons[record["text_id"]] = reason
            records.append(record)

    # Preserve distinct IDs for repeated lines, while eliminating accidental
    # duplicate records from overlaying base and patch archives.
    unique = {record["text_id"]: record for record in records}
    # Equal text and speaker do not prove the same recorded performance.
    # Only the entry's authored SoundID or timeline GUID may attach a voice.
    return {
        "format": INDEX_FORMAT,
        "game": "pragmata",
        "install": str(install) if install else None,
        "fingerprint": fingerprint(install) if install else None,
        "records": list(unique.values()),
        "speakers": speakers,
        "audio_count": sum(1 for record in unique.values() if "audio" in record),
        "excluded": excluded,
        "unresolved_audio": [record["text_id"] for record in unique.values() if "audio" not in record],
        "audio_diagnostics": [{"text_id": record["text_id"], "reason": unresolved_reasons[record["text_id"]]}
                              for record in unique.values() if "audio" not in record],
    }


def refresh_install(install: Path) -> dict:
    """Extract a fresh overlay and publish only an unchanged, complete install."""
    stamp = fingerprint(install)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="index-", dir=DATA_DIR) as temporary:
        extracted = Path(temporary)
        extract_assets(install, extracted, DATA_DIR / "tools")
        message_root = extracted / "natives/stm/message"
        payload = build_index(message_root, install, extracted, load_sound_graph())
        if not payload.get("records"):
            raise ValueError("No official bilingual PRAGMATA dialogue could be extracted; previous index preserved")
        if fingerprint(install) != stamp:
            raise ValueError("PRAGMATA files changed while indexing; finish the game update, then refresh")
        payload["fingerprint"] = stamp
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Index official PRAGMATA English and Chinese dialogue")
    parser.add_argument("--install", type=Path)
    parser.add_argument("--source", type=Path, help="Use an already-extracted natives/stm/message folder")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "textmap.json")
    args = parser.parse_args()
    install = args.install or find_install()
    if args.source:
        message_root = args.source
        extraction_root = message_root.parents[2] if message_root.name.casefold() == "message" else None
        payload = build_index(message_root, install, extraction_root, load_sound_graph())
    else:
        if install is None:
            raise SystemExit("PRAGMATA installation was not found")
        payload = refresh_install(install)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(args.output)
    print(
        f"Indexed {len(payload['records']):,} official dialogue records; "
        f"mapped {payload['audio_count']:,} directly to Mandarin game audio"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
