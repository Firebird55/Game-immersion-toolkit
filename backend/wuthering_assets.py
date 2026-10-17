"""Read installed Wuthering Waves dialogue and exact Mandarin external sources.

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

EXTRACTOR_URL = "https://github.com/Herselfta/FModelCLI/releases/download/v1.0.2/FModelCLI.exe"
EXTRACTOR_SHA256 = "86426493c63f0af2ccf6d1d8b498a737723069f6c25a573a46e94d1a3f26e835"
PUBLIC_METADATA_URL = "https://yarik0chka.github.io/wuwa-keys/keys.json"
EXTERNAL_ROOT = "Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/"
LANGUAGE_INDEX_VERSION = 1
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


def ensure_extractor(directory: Path, decoder: Path) -> Path:
    executable = directory / "FModelCLI.exe"
    if not _matches_digest(executable, EXTRACTOR_SHA256):
        _verified_file(executable, _download(EXTRACTOR_URL), EXTRACTOR_SHA256)
    dependencies = directory / ".data"
    ensure_unreal_decompression(dependencies)
    if not decoder.is_file():
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
    table = struct.unpack_from("<I", blob)[0]
    vtable = table - struct.unpack_from("<i", blob, table)[0]
    size = struct.unpack_from("<H", blob, vtable)[0]
    offset = 4 + slot * 2
    if offset >= size:
        return None
    relative = struct.unpack_from("<H", blob, vtable + offset)[0]
    return table + relative if relative else None


def _string(blob: bytes, slot: int) -> str:
    offset = _field(blob, slot)
    if offset is None:
        return ""
    position = offset + struct.unpack_from("<I", blob, offset)[0]
    size = struct.unpack_from("<I", blob, position)[0]
    if size > len(blob) - position - 4:
        raise ValueError("Invalid dialogue metadata string")
    return blob[position + 4:position + 4 + size].decode("utf-8")


def _boolean(blob: bytes, slot: int) -> bool:
    offset = _field(blob, slot)
    return bool(blob[offset]) if offset is not None else False


def _rows(path: Path, query: str) -> list:
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as connection:
        return connection.execute(query).fetchall()


def build_records(db_root: Path, files: list[str]) -> list[dict]:
    english = dict(_rows(db_root / "en/lang_multi_text.db", "SELECT Id, Content FROM MultiText WHERE Content IS NOT NULL"))
    chinese = dict(_rows(db_root / "zh-Hans/lang_multi_text.db", "SELECT Id, Content FROM MultiText WHERE Content IS NOT NULL"))
    sources = {path.casefold(): path for path in files if path.startswith(EXTERNAL_ROOT) and path.endswith(".wem")}
    records = []
    for text_id, blob in _rows(db_root / "db_plot_audio.db", "SELECT Id, BinData FROM plotaudio"):
        en, zh = display_text(english.get(text_id, "")), display_text(chinese.get(text_id, ""))
        if not en or not zh or _string(blob, 0) != text_id:
            continue
        filename = _string(blob, 2)
        global_language, gender = _boolean(blob, 3), _boolean(blob, 7)
        for variant in (["female", "male"] if gender else [None]):
            suffix = "_F" if variant == "female" else "_M" if variant else ""
            # GlobalLanguage voices are deliberately language independent.
            # Mandarin capture requires an explicit zh resource; don't relabel
            # shared creature voices or other languages as Mandarin.
            resource = EXTERNAL_ROOT + "zh_" + filename + suffix + ".wem"
            mapped = sources.get(resource.casefold()) if not global_language and "{" not in filename else None
            audio = {"depot": mapped} if mapped else None
            records.append({"text_id": f"wuwa:{text_id}" + (f":{variant}" if variant else ""),
                "english": en, "chinese": zh, "audio": audio, "player_voice": variant})
    return records


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    stamp = fingerprint(install)
    decoder = data_dir.parent / "voice-assets/vgmstream/vgmstream-cli.exe"
    executable = ensure_extractor(data_dir / "tools", decoder)
    cache = data_dir / "index-cache" / stamp[:16]
    complete = cache / "complete.json"
    if not complete.is_file():
        for filter_text in ("ConfigDB/en/lang_multi_text.db", "ConfigDB/zh-Hans/lang_multi_text.db", "ConfigDB/db_plot_audio.db"):
            progress("Reading installed Wuthering Waves dialogue metadata")
            run_extractor(install, executable, cache, filter_text)
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
        "message": f"{len(records):,} bilingual pairs; {mapped:,} Mandarin voices" if mapped else
                   f"{len(records):,} dialogue pairs indexed; download the Chinese voice pack in Wuthering Waves"}


def build_language_records(db_root: Path, files: list[str], source_locale: str, target_locales) -> list[dict]:
    from .languages import audio_locale
    tables = {locale: dict(_rows(db_root / TEXT_LOCALES[locale] / 'lang_multi_text.db',
        'SELECT Id, Content FROM MultiText WHERE Content IS NOT NULL')) for locale in {source_locale, *target_locales}}
    sources = {path.casefold(): path for path in files if path.startswith(EXTERNAL_ROOT) and path.endswith('.wem')}
    code, gender_slot = VOICE_LOCALES[source_locale]
    records = []
    for identity, blob in _rows(db_root / 'db_plot_audio.db', 'SELECT Id, BinData FROM plotaudio'):
        text = display_text(tables[source_locale].get(identity, ''))
        if not text or _string(blob, 0) != identity:
            continue
        texts = {locale: value for locale, table in tables.items() if (value := display_text(table.get(identity, '')))}
        filename = _string(blob, 2)
        for variant in (['female', 'male'] if _boolean(blob, gender_slot) else [None]):
            suffix = '_F' if variant == 'female' else '_M' if variant else ''
            resource = EXTERNAL_ROOT + code + '_' + filename + suffix + '.wem'
            mapped = sources.get(resource.casefold()) if not _boolean(blob, 3) and '{' not in filename else None
            records.append({'text_id': f'wuwa:{identity}' + (f':{variant}' if variant else ''),
                'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''), 'source_text': text,
                'source_locale': source_locale, 'texts': texts, 'audio_locale': audio_locale(source_locale),
                'audio': {'depot': mapped, 'locale': audio_locale(source_locale)} if mapped else None, 'player_voice': variant})
    return records


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Wuthering study/audio locale')
    stamp = fingerprint(install)
    executable = ensure_extractor(data_dir / 'tools', data_dir.parent / 'voice-assets/vgmstream/vgmstream-cli.exe')
    cache = data_dir / 'index-cache' / stamp[:16]
    cache.mkdir(parents=True, exist_ok=True)
    targets = {value: resolve_locale(value, TEXT_LOCALES) for value in target_locales}
    requested = {source_locale, *(locale for locale in targets.values() if locale)}
    for relative in ['db_plot_audio.db', *(TEXT_LOCALES[locale] + '/lang_multi_text.db' for locale in requested)]:
        path = cache / 'Client/Content/Aki/ConfigDB' / relative
        if not path.is_file():
            progress(f'Reading selected Wuthering text table {relative}')
            run_extractor(install, executable, cache, 'ConfigDB/' + relative)
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
    missing = [target for target, locale in targets.items() if locale is None]
    return {'format': 2, 'game': 'wuwa', 'install': str(install), 'fingerprint': stamp,
        'source_locale': source_locale, 'records': records, 'missing_translation_locales': missing,
        'message': f'{len(records):,} official {source_locale} lines; {mapped:,} original voices' +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; install the selected voice pack through the game launcher' if not mapped else '')}


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
        raise FileNotFoundError("The original Mandarin clip is missing from the installed voice pack")
    return path.read_bytes()


@lru_cache(maxsize=2)
def _voice_inventory(path: Path, size: int, modified: int) -> tuple[str, ...]:
    values = json.loads(path.read_text(encoding='utf8'))
    return tuple(sorted(p.casefold() for p in values if p.startswith(EXTERNAL_ROOT) and p.endswith('.wem')))


def extract_voices(install: Path, audios: list[dict], executable: Path, destination: Path) -> list[bytes]:
    depots = [_validate_voice(audio) for audio in audios]
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
                raise FileNotFoundError('Original Mandarin clip is missing from the installed voice pack')
            locations[depot] = path
    extract(sorted(set(depots)), 'sources')
    return [locations[depot].read_bytes() for depot in depots]
