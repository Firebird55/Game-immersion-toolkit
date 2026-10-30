"""Read selected Wuthering Waves text and authored original voice sources.

The PlotAudio FlatBuffer fields and filename rules follow the game's shipped
Core/Define/Config/PlotAudio.js and Game/Module/Plot/PlotAudioModel.js. No event
hashes, filename guesses, audio recordings, or game modifications are used.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import os
from bisect import bisect_left
from contextlib import closing
import json
import re
import shutil
import sqlite3
import struct
import subprocess
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path

from .textmaps import display_text
from .preparation_errors import PreparationFailure

EXTRACTOR_URL = "https://github.com/Herselfta/FModelCLI/releases/download/v1.0.2/FModelCLI.exe"
EXTRACTOR_SHA256 = "86426493c63f0af2ccf6d1d8b498a737723069f6c25a573a46e94d1a3f26e835"
PUBLIC_METADATA_URL = "https://yarik0chka.github.io/wuwa-keys/keys.json"
EXTERNAL_ROOT = "Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/"
LANGUAGE_INDEX_VERSION = 3
NARRATIVE_TABLES = ('db_flowState.db', 'db_cgVedio.db', 'db_infodisplay.db')
COVERAGE_WARNINGS = [
    'Story-flow text, choices, messages, movie captions and readable records are indexed; presentation-specific OCR coverage is incomplete.',
    'Combat and ambient audio events, embedded movie audio and dynamic voice filenames still lack complete per-line bindings.',
    'Entity-only bubbles, legacy numeric subtitle tables, song lyrics and event-specific text outside story flows are not fully indexed.',
]
SUPPORTED_LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
VOICE_LOCALES = {'en': ('en', 4), 'zh-Hans': ('zh', 7), 'zh-Hant': ('zh', 7), 'ja': ('ja', 5), 'ko': ('ko', 6)}
TEXT_LOCALES = {locale: locale for locale in ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'fr', 'de', 'ru', 'th', 'vi', 'id')}
TEXT_LOCALES.update({'es-ES': 'es', 'pt-BR': 'pt'})


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def _verified_file(path: Path, data: bytes, digest: str) -> None:
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Game extractor download checksum mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def _matches_digest(path: Path, digest: str) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


def ensure_unreal_decompression(dependencies: Path) -> None:
    dependencies.mkdir(parents=True, exist_ok=True)
    # Populate pinned decompression dependencies before the CLI runs. It would
    # otherwise acquire its own dependencies, including a moving audio release.
    oodle = dependencies / "oodle-data-shared.dll"
    oodle_digest = "8f6c0d487573b5a7ea8548407cbf96f5cd833fe7138769914961b6697d74b3b3"
    if not _matches_digest(oodle, oodle_digest):
        archive = _download("https://github.com/WorkingRobot/OodleUE/releases/download/2026-01-25-1223/clang-cl-x64-release.zip")
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            _verified_file(oodle, bundle.read("bin/oodle-data-shared.dll"), oodle_digest)
    zlib = dependencies / "zlib-ng2.dll"
    zlib_digest = "454be2f3d10f804ace577198401431db5e95d0286b59589bc28a40085388e7c2"
    if not _matches_digest(zlib, zlib_digest):
        compressed = _download("https://github.com/NotOfficer/Zlib-ng.NET/releases/download/1.0.0/zlib-ng2.dll.gz")
        _verified_file(zlib, gzip.decompress(compressed), zlib_digest)


def ensure_extractor(directory: Path, decoder: Path | None) -> Path:
    from .bundle_tools import require_source_toolchain
    require_source_toolchain('Unreal archive extractor')
    executable = directory / "FModelCLI.exe"
    if not _matches_digest(executable, EXTRACTOR_SHA256):
        _verified_file(executable, _download(EXTRACTOR_URL), EXTRACTOR_SHA256)
    dependencies = directory / ".data"
    ensure_unreal_decompression(dependencies)
    if decoder is None or not decoder.is_file():
        raise FileNotFoundError("Original voice decoder is missing; run setup again")
    shutil.copyfile(decoder, dependencies / "vgmstream-cli.exe")
    return executable


def _official_archive(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if any(part.startswith("~") for part in relative.parts):
        return False
    if path.name.startswith("pakchunk"):
        return True
    # Optional in-game cinematic downloads use Video_* names rather than
    # pakchunk*. The CLI scans them too; permit only the observed official
    # location and a filename whose cinematic ID matches its parent folder.
    match = re.fullmatch(r"Video/(hd|sd)/Paks/(\d+_\d+)/Video_(\d+_\d+)-(HD|SD)-WindowsNoEditor\.pak", relative.as_posix())
    return bool(match and match[2] == match[3] and match[1].upper() == match[4])


def archive_sources(install: Path) -> list[Path]:
    roots = [install / "Client/Content/Paks", install / "Client/Saved/Resources"]
    return sorted({path for root in roots if root.is_dir() for path in root.rglob("*.pak")
                   if _official_archive(root, path)}, key=str)


def fingerprint(install: Path) -> str:
    values = [f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in archive_sources(install)]
    return hashlib.sha256("|".join(values).encode()).hexdigest()


@lru_cache(maxsize=2)
def _archive_metadata(install: Path, stamp: str) -> tuple[str, ...]:
    # Public archive metadata is held in memory, never written to source,
    # manifests, files, or logs. Select only installed-version entries to stay
    # below Windows' command-line length limit.
    from Crypto.Cipher import AES
    payload = json.loads(_download(PUBLIC_METADATA_URL))
    candidates = list(dict.fromkeys(re.findall(r"0x[0-9a-fA-F]{64}", json.dumps(payload))))
    selected = set()
    for pak in archive_sources(install):
        with pak.open("rb") as stream:
            size = pak.stat().st_size
            if size < 64:
                raise ValueError("Game archive is incomplete; wait for the download to finish")
            # Empty official patch archives can be smaller than our footer
            # probe. Read the available tail and validate its actual structure.
            stream.seek(-min(512, size), 2)
            footer = stream.read()
            magic = footer.rfind(struct.pack("<I", 0x5A6F12E1))
            if magic < 17:
                raise ValueError("Installed game archive format is unsupported or incomplete")
            if not footer[magic - 1]:
                continue
            offset, length = struct.unpack_from("<QQ", footer, magic + 8)
            if length < 16 or offset + length > pak.stat().st_size:
                raise ValueError("Game archive index is incomplete")
            stream.seek(offset)
            sample = stream.read(min(length, 256))
            sample = sample[:len(sample) // 16 * 16]
        found = False
        for value in candidates:
            plain = AES.new(bytes.fromhex(value[2:]), AES.MODE_ECB).decrypt(sample)
            size = struct.unpack_from("<i", plain)[0]
            if 1 < size < min(200, len(plain) - 4) and plain[4:4 + size].startswith(b"../") and plain[3 + size] == 0:
                selected.add(value)
                found = True
                break
        if not found:
            raise ValueError("Installed archive version needs updated public extraction metadata")
    if not selected:
        raise ValueError("No supported installed Wuthering Waves archives were found")
    return tuple(sorted(selected))


def run_extractor(install: Path, executable: Path, destination: Path | None, filter_text: str) -> list[str]:
    from .bundle_tools import require_source_toolchain
    require_source_toolchain('Unreal archive extractor')
    for root in (install / "Client/Content/Paks", install / "Client/Saved/Resources"):
        if root.is_dir() and any(not _official_archive(root, path) for path in root.rglob("*.pak")):
            raise ValueError("Wuthering Waves indexing requires official archives; unsupported mod archives were found")
    metadata = _archive_metadata(install, fingerprint(install))
    arguments = [str(destination), filter_text] if destination else ["--list", filter_text]
    try:
        result = subprocess.run([str(executable), str(install), ";".join(metadata), *arguments],
            capture_output=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        # Never expose subprocess arguments, which contain archive metadata.
        raise RuntimeError("Wuthering Waves extractor could not complete") from None
    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode or "[Fail]" in output or "[Error]" in output:
        raise RuntimeError("Wuthering Waves extraction failed; check the installed archives")
    return [line[7:].strip() for line in output.splitlines() if line.startswith("[File] ")]


def _field(blob: bytes, slot: int) -> int | None:
    if len(blob) < 8 or slot < 0:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata is truncated or uses an unsupported format.')
    table = struct.unpack_from("<I", blob)[0]
    if table < 4 or table + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has an invalid table offset.')
    vtable = table - struct.unpack_from("<i", blob, table)[0]
    if vtable < 4 or vtable + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has an invalid field table.')
    size, object_size = struct.unpack_from('<HH', blob, vtable)
    if size < 4 or size % 2 or vtable + size > len(blob) or object_size < 4 or table + object_size > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has invalid table bounds.')
    offset = 4 + slot * 2
    if offset >= size:
        return None
    relative = struct.unpack_from("<H", blob, vtable + offset)[0]
    if relative and not 4 <= relative < object_size:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has an invalid field offset.')
    return table + relative if relative else None


def _string(blob: bytes, slot: int) -> str:
    offset = _field(blob, slot)
    if offset is None:
        return ""
    if offset + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains a truncated string reference.')
    position = offset + struct.unpack_from("<I", blob, offset)[0]
    if position <= offset or position + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains an invalid string reference.')
    size = struct.unpack_from("<I", blob, position)[0]
    if size > len(blob) - position - 4:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains a truncated string.')
    try:
        return blob[position + 4:position + 4 + size].decode("utf-8")
    except UnicodeDecodeError:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains invalid text encoding.') from None


def _boolean(blob: bytes, slot: int) -> bool:
    offset = _field(blob, slot)
    return bool(blob[offset]) if offset is not None else False


def _rows(path: Path, query: str) -> list:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        return connection.execute(query).fetchall()


def _text_table(db_root: Path, locale: str) -> dict:
    directory = db_root / TEXT_LOCALES[locale]
    path = directory / 'lang_multi_text.db'
    columns = {row[1] for row in _rows(path, 'PRAGMA table_info(MultiText)')}
    if not {'Id', 'Content'} <= columns:
        raise PreparationFailure('unsupported_format', 'Wuthering localization table schema changed; update the toolkit.')
    rows = _rows(path, 'SELECT Id, Content' + (', RedirectDbIndex' if 'RedirectDbIndex' in columns else ', 0') + ' FROM MultiText')
    redirects = {index for _, _, index in rows if index}
    if redirects - {1}:
        raise PreparationFailure('unsupported_format', 'Wuthering localization uses an unsupported text shard; update the toolkit.')
    shard = {}
    if redirects:
        if not (directory / 'lang_multi_text_1sthalf.db').is_file():
            raise PreparationFailure('incomplete_game_data', 'Wuthering localization text shard is missing; verify game files and retry.')
        shard = dict(_rows(directory / 'lang_multi_text_1sthalf.db', 'SELECT Id, Content FROM MultiText'))
        if any(identity not in shard for identity, _, index in rows if index):
            raise PreparationFailure('incomplete_game_data', 'Wuthering redirected localization entries are incomplete; verify game files and retry.')
    # Base Content can be a placeholder even when nonempty. Only the authored
    # RedirectDbIndex selects the shard; never borrow another locale's text.
    return {identity: (shard[identity] if index else content) or '' for identity, content, index in rows}


def _narrative_refs(db_root: Path) -> dict[str, list[tuple[str, str]]]:
    refs = {}
    def add(identity, kind, status):
        if isinstance(identity, str) and identity:
            value = (kind, status)
            if value not in refs.setdefault(identity, []):
                refs[identity].append(value)
    def walk(value, mode=None):
        if isinstance(value, list):
            # Flow mode persists through sequential actions and their options.
            for item in value:
                if isinstance(item, dict) and item.get('Disabled'):
                    continue
                if isinstance(item, dict) and item.get('Name') == 'SetPlotMode':
                    mode = item.get('Params', {}).get('Mode', mode)
                walk(item, mode)
        elif isinstance(value, dict):
            if value.get('Disabled'):
                return
            if value.get('Name') == 'ShowCenterText':
                add(value.get('Params', {}).get('TidCenterText'), 'story_card', 'unknown')
            if 'TidTalkOption' in value:
                add(value['TidTalkOption'], 'choice', 'unvoiced')
            if 'TidTalk' in value:
                kind = value.get('Type', 'Talk')
                message_type = value.get('MessageType', {}).get('Type')
                audio_event = value.get('TalkAkEvent') or value.get('TalkEndAkEvent') or value.get('UniversalTone')
                status = 'unavailable' if value.get('PlayVoice') or audio_event else 'unknown'
                if value.get('PlayVoice') is False and not audio_event:
                    status = 'unvoiced'
                category = 'dialogue'
                if kind == 'PhoneMessage':
                    if message_type in {'Emoji', 'Attachment'}:
                        category = None
                    elif message_type == 'Voice':
                        category, status = 'message', 'unavailable'
                    elif message_type == 'SystemTip':
                        category = 'message'
                        if status == 'unknown':
                            status = 'unvoiced'
                    else:
                        category = None
                elif kind in {'Option', 'SystemOption'}:
                    category = 'choice'
                    if status == 'unknown':
                        status = 'unvoiced'
                elif mode == 'PhoneMessage' and kind == 'Talk':
                    category = 'message'
                    if status == 'unknown':
                        status = 'unvoiced'
                elif kind in {'CenterText', 'AvgCenterText', 'AvgNarration'}:
                    category = 'story_card'
                elif kind in {'NoTextItem', 'QTE'}:
                    category = None
                elif mode == 'Prompt':
                    category = 'ambient'
                if category:
                    add(value['TidTalk'], category, status)
            for child in value.values():
                if isinstance(child, (list, dict)):
                    walk(child, mode)
    path = db_root / 'db_flowState.db'
    if path.is_file():
        for identity, blob in _rows(path, 'SELECT StateKey, BinData FROM flowstate'):
            if _string(blob, 0) != identity:
                raise PreparationFailure('unsupported_format', 'Wuthering story-flow identities do not match their metadata.')
            try:
                actions = json.loads(_string(blob, 6))
            except (ValueError, TypeError):
                raise PreparationFailure('unsupported_format', 'Wuthering story-flow actions use an unsupported format.') from None
            if not isinstance(actions, list):
                raise PreparationFailure('unsupported_format', 'Wuthering story-flow actions use an unsupported container.')
            walk(actions)
    path = db_root / 'db_cgVedio.db'
    if path.is_file():
        for blob, in _rows(path, 'SELECT BinData FROM videocaption'):
            # IsPlaySubtitleVoice false does not mean silent: speech may be
            # embedded in the video. Never substitute the whole movie track.
            add(_string(blob, 4), 'cinematic', 'unavailable')
    path = db_root / 'db_infodisplay.db'
    if path.is_file():
        for blob, in _rows(path, 'SELECT BinData FROM infodisplay'):
            add(_string(blob, 4), 'readable', 'unavailable' if _string(blob, 6) else 'unknown')
    return refs


def build_records(db_root: Path, files: list[str]) -> list[dict]:
    return [row for row in build_language_records(db_root, files, 'zh-Hans', ['en']) if row['english']]


def _prepare_text_tables(install, executable, cache, locales, progress):
    db_root = cache / 'Client/Content/Aki/ConfigDB'
    for locale in sorted(locales):
        directory = db_root / TEXT_LOCALES[locale]
        path = directory / 'lang_multi_text.db'
        needs_read = not path.is_file()
        if not needs_read:
            columns = {row[1] for row in _rows(path, 'PRAGMA table_info(MultiText)')}
            needs_read = ('RedirectDbIndex' in columns and not (directory / 'lang_multi_text_1sthalf.db').is_file()
                          and bool(_rows(path, 'SELECT 1 FROM MultiText WHERE RedirectDbIndex > 0 LIMIT 1')))
        if needs_read:
            progress('Reading selected Wuthering localization tables')
            # Substring selects both the base table and its authored shard.
            run_extractor(install, executable, cache, 'ConfigDB/' + TEXT_LOCALES[locale] + '/lang_multi_text')
    for relative in ('db_plot_audio.db', *NARRATIVE_TABLES):
        if not (db_root / relative).is_file():
            progress('Reading installed Wuthering narrative metadata')
            run_extractor(install, executable, cache, 'ConfigDB/' + relative)
        if not (db_root / relative).is_file():
            raise PreparationFailure('unsupported_format', 'Required Wuthering narrative tables were not found; update the toolkit or verify game files.')


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    from .media_tools import vgmstream_executable
    stamp = fingerprint(install)
    decoder = vgmstream_executable(data_dir.parent.parent)
    executable = ensure_extractor(data_dir / "tools", decoder)
    cache = data_dir / "index-cache" / stamp[:16]
    _prepare_text_tables(install, executable, cache, {'en', 'zh-Hans'}, progress)
    complete = cache / "complete.json"
    if not complete.is_file():
        progress("Checking exact Mandarin voice paths")
        files = run_extractor(install, executable, None, "WwiseExternalSource/")
        complete.parent.mkdir(parents=True, exist_ok=True)
        complete.write_text(json.dumps(files), encoding="utf-8")
    files = json.loads(complete.read_text(encoding="utf-8"))
    records = build_records(cache / "Client/Content/Aki/ConfigDB", files)
    if not records or fingerprint(install) != stamp:
        raise ValueError("Game files are incomplete or changed while indexing; retry after the download finishes")
    mapped = sum(bool(record["audio"]) for record in records)
    return {"format": 1, "install": str(install), "fingerprint": stamp, "records": records,
        'coverage_warnings': COVERAGE_WARNINGS,
        "message": f"{len(records):,} bilingual pairs; {mapped:,} Mandarin voices" if mapped else
                   f"{len(records):,} dialogue pairs indexed; download the Chinese voice pack in Wuthering Waves"}


def build_language_records(db_root: Path, files: list[str], source_locale: str, target_locales) -> list[dict]:
    from .languages import audio_locale
    if not (db_root / TEXT_LOCALES[source_locale] / 'lang_multi_text.db').is_file():
        raise ValueError('Install the selected official Wuthering text pack before preparing it.')
    tables = {locale: _text_table(db_root, locale) for locale in {source_locale, *target_locales}}
    if not any(display_text(text) for text in tables[source_locale].values()):
        raise ValueError('The selected official Wuthering text pack is empty; no other language was substituted.')
    sources = {path.casefold(): path for path in files if path.startswith(EXTERNAL_ROOT) and path.endswith('.wem')}
    code, gender_slot = VOICE_LOCALES[source_locale]
    records = []
    narrative = _narrative_refs(db_root)
    emitted = set()
    def text_fields(identity):
        texts = {locale: value for locale, table in tables.items() if (value := display_text(table.get(identity, '')))}
        return {'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                'source_text': texts.get(source_locale, ''), 'source_locale': source_locale,
                'texts': texts, 'audio_locale': audio_locale(source_locale)}
    def category(identity):
        kinds = {kind for kind, _ in narrative.get(identity, [])}
        return next((kind for kind in ('cinematic', 'story_card', 'message', 'readable', 'ambient', 'choice', 'dialogue') if kind in kinds), 'dialogue')
    for identity, blob in _rows(db_root / 'db_plot_audio.db', 'SELECT Id, BinData FROM plotaudio'):
        text = display_text(tables[source_locale].get(identity, ''))
        if not text or _string(blob, 0) != identity:
            continue
        fields = text_fields(identity)
        emitted.add(identity)
        filename = _string(blob, 2)
        for variant in (['female', 'male'] if _boolean(blob, gender_slot) else [None]):
            suffix = '_F' if variant == 'female' else '_M' if variant else ''
            resource = EXTERNAL_ROOT + code + '_' + filename + suffix + '.wem'
            mapped = sources.get(resource.casefold()) if not _boolean(blob, 3) and '{' not in filename else None
            records.append({'text_id': f'wuwa:{identity}' + (f':{variant}' if variant else ''), **fields,
                'audio': {'depot': mapped, 'locale': audio_locale(source_locale)} if mapped else None, 'player_voice': variant,
                'voice_status': 'voiced' if mapped else 'unavailable', 'dialogue_kind': category(identity)})
    for identity, evidence in narrative.items():
        if identity in emitted:
            continue
        fields = text_fields(identity)
        if not fields['source_text']:
            continue
        statuses = {status for _, status in evidence}
        # Any voiced or unresolved context prevents calling a shared ID silent.
        status = 'unavailable' if 'unavailable' in statuses else 'unknown' if 'unknown' in statuses else 'unvoiced'
        records.append({'text_id': f'wuwa:{identity}', **fields, 'audio': None,
                        'voice_status': status, 'dialogue_kind': category(identity)})
    return records


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    from .media_tools import vgmstream_executable
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Wuthering study/audio locale')
    stamp = fingerprint(install)
    executable = ensure_extractor(data_dir / 'tools', vgmstream_executable(data_dir.parent.parent))
    cache = data_dir / 'index-cache' / stamp[:16]
    cache.mkdir(parents=True, exist_ok=True)
    targets = {value: resolve_locale(value, TEXT_LOCALES) for value in target_locales}
    requested = {source_locale, *(locale for locale in targets.values() if locale)}
    _prepare_text_tables(install, executable, cache, requested, progress)
    for target, locale in list(targets.items()):
        if locale and not (cache / 'Client/Content/Aki/ConfigDB' / TEXT_LOCALES[locale] / 'lang_multi_text.db').is_file():
            targets[target] = None
    inventory = cache / 'complete.json'
    if not inventory.is_file():
        progress('Checking installed original voice paths')
        files = run_extractor(install, executable, None, 'WwiseExternalSource/')
        pending = inventory.with_suffix('.pending'); pending.write_text(json.dumps(files), encoding='utf8'); pending.replace(inventory)
    files = json.loads(inventory.read_text(encoding='utf8'))
    records = build_language_records(cache / 'Client/Content/Aki/ConfigDB', files, source_locale,
                                    {locale for locale in targets.values() if locale})
    if not records or fingerprint(install) != stamp:
        raise ValueError('Wuthering files changed or dialogue is incomplete; previous table retained.')
    mapped = sum(bool(row['audio']) for row in records)
    available = {locale for row in records for locale in row['texts']}
    missing = [target for target, locale in targets.items() if locale not in available]
    return {'format': 2, 'game': 'wuwa', 'install': str(install), 'fingerprint': stamp,
        'source_locale': source_locale, 'records': records, 'missing_translation_locales': missing,
        'coverage_warnings': COVERAGE_WARNINGS,
        'message': f'{len(records):,} official {source_locale} lines; {mapped:,} original voices' +
        (f'; {len(records) - mapped:,} entries without a verified voice binding' if mapped < len(records) else '') +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; check the selected voice pack through the game launcher' if not mapped else '')}


def _validate_voice(audio):
    depot = audio.get('depot', '')
    code = VOICE_LOCALES.get(audio.get('locale', 'zh-Hans'), (None,))[0]
    if code is None or not depot.startswith(EXTERNAL_ROOT + code + '_') or not depot.endswith('.wem') or '..' in depot or ':' in depot:
        raise ValueError('Invalid original voice locale or reference')
    return depot


def extract_voice(install: Path, audio: dict, executable: Path, destination: Path) -> bytes:
    depot = _validate_voice(audio)
    run_extractor(install, executable, destination, depot)
    path = (destination / depot).resolve()
    if not path.is_relative_to(destination.resolve()) or not path.is_file():
        raise FileNotFoundError("The selected original clip is missing from the installed voice pack")
    return path.read_bytes()


@lru_cache(maxsize=2)
def _voice_inventory(path: Path, size: int, modified: int) -> tuple[str, ...]:
    values = json.loads(path.read_text(encoding='utf8'))
    return tuple(sorted(p.casefold() for p in values if p.startswith(EXTERNAL_ROOT) and p.endswith('.wem')))


def extract_voices(install: Path, audios: list[dict], executable: Path, destination: Path) -> list[bytes]:
    if not audios:
        return []
    depots = [_validate_voice(audio) for audio in audios]
    if len({VOICE_LOCALES[audio.get('locale', 'zh-Hans')][0] for audio in audios}) != 1:
        raise ValueError('Original voice batch crosses study/audio locales')
    inventory_path = executable.parent.parent / 'index-cache' / fingerprint(install)[:16] / 'complete.json'
    try:
        stat = inventory_path.stat()
        inventory = _voice_inventory(inventory_path, stat.st_size, stat.st_mtime_ns)
    except (OSError, ValueError, TypeError):
        inventory = ()
    locations = {}
    def extract(group, number):
        # The pinned reader supports substring filters. Use a shared prefix only
        # when the indexed inventory proves it selects exactly requested WEMs.
        prefix = os.path.commonprefix(group)
        low = bisect_left(inventory, prefix.casefold())
        high = bisect_left(inventory, prefix.casefold() + '\uffff')
        wanted = {p.casefold() for p in group}
        bounded = inventory and len(prefix) > len(EXTERNAL_ROOT + 'zh_') and set(inventory[low:high]) == wanted
        if len(group) > 1 and not bounded:
            middle = len(group) // 2
            extract(group[:middle], number + 'a'); extract(group[middle:], number + 'b')
            return
        directory = destination / number; directory.mkdir(parents=True, exist_ok=True)
        run_extractor(install, executable, directory, prefix if bounded else group[0])
        for depot in group:
            path = (directory / depot).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file():
                raise FileNotFoundError('The selected original clip is missing from the installed voice pack')
            locations[depot] = path
    extract(sorted(set(depots)), 'sources')
    return [locations[depot].read_bytes() for depot in depots]
