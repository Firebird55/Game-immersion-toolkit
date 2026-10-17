"""Read-only Cyberpunk extraction using a pinned, checksum-verified WolvenKit CLI."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path, PureWindowsPath

from .textmaps import display_text

WOLVENKIT_VERSION = "9.0.1"
WOLVENKIT_SHA256 = "364427384c0f4ebb6b157fa9abd01595258af1b7993c7b3a7edd2920f2016e92"
WOLVENKIT_URL = f"https://github.com/WolvenKit/WolvenKit/releases/download/{WOLVENKIT_VERSION}/WolvenKit.Console-{WOLVENKIT_VERSION}.zip"
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'fr', 'it', 'de', 'es-ES', 'ja', 'ko', 'pl', 'pt-BR', 'ru', 'zh-Hans')
TEXT_LOCALES = {'en': 'en', 'fr': 'fr', 'it': 'it', 'de': 'de', 'es-ES': 'es-es', 'es-419': 'es-mx',
    'ja': 'ja', 'ko': 'ko', 'pl': 'pl', 'pt-BR': 'pt', 'ru': 'ru', 'zh-Hans': 'zh-cn', 'zh-Hant': 'zh-tw',
    'ar': 'ar', 'cs': 'cs', 'hu': 'hu', 'th': 'th', 'tr': 'tr', 'uk': 'ua'}


def ensure_wolvenkit(directory: Path) -> Path:
    executable = directory / "WolvenKit.CLI.exe"
    marker = directory / "verified-version.json"
    if executable.is_file() and marker.is_file():
        if json.loads(marker.read_text())["sha256"] == WOLVENKIT_SHA256:
            return executable
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "download.zip.part"
    try:
        with urllib.request.urlopen(WOLVENKIT_URL, timeout=120) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        with archive.open("rb") as downloaded:
            if hashlib.file_digest(downloaded, "sha256").hexdigest() != WOLVENKIT_SHA256:
                raise ValueError("WolvenKit download checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if not (directory / name).resolve().is_relative_to(directory.resolve()):
                    raise ValueError("Unsafe extractor archive path")
            bundle.extractall(directory)
        marker.write_text(json.dumps({"version": WOLVENKIT_VERSION, "sha256": WOLVENKIT_SHA256}))
        return executable
    finally:
        archive.unlink(missing_ok=True)


def run_wolvenkit(executable: Path, *arguments: str) -> None:
    result = subprocess.run([str(executable), *map(str, arguments)], capture_output=True,
                            timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or b"[ 0: Error" in result.stdout:
        raise RuntimeError("WolvenKit extraction failed; check installed archives and extractor dependencies")


def archive_sources(install: Path) -> list[Path]:
    sources = []
    for group in ("content", "ep1"):
        directory = install / "archive/pc" / group
        sources.extend(directory / (prefix + name) for prefix in ("", "ep1_") for name in
                       tuple(f'lang_{code}_{kind}.archive' for code in TEXT_LOCALES.values() for kind in ('text', 'voice'))
                       if (directory / (prefix + name)).is_file())
    return sources


def fingerprint(install: Path) -> str:
    return "reader2|" + "|".join(f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
                    for p in archive_sources(install))


def expansion_status(install: Path, source_locale=None) -> dict:
    paths = [p for p in archive_sources(install) if p.parent.name == "ep1" or p.name.startswith("ep1_")]
    if not paths:
        return {"expansion_state": "not_installed", "expansion_message": "Phantom Liberty not found; the base game can be used on its own."}
    names = {p.name.removeprefix("ep1_") for p in paths}
    code = TEXT_LOCALES[source_locale or 'zh-Hans']
    required = {f'lang_{code}_text.archive'} if source_locale else {'lang_en_text.archive', 'lang_zh-cn_text.archive'}
    if not required <= names:
        state, message = "missing_text", "Phantom Liberty language files are incomplete. Finish the DLC and language downloads in your game launcher, then refresh."
    elif f'lang_{code}_voice.archive' not in names:
        state, message = "missing_voice", f"Phantom Liberty needs its {source_locale} voice archive. Install the selected language pack through your game launcher, then refresh."
    else:
        state, message = "available", f"Phantom Liberty {source_locale} text and original voice archives found. Game-data refresh includes the DLC."
    return {"expansion_state": state, "expansion_message": message}


def json_entries(path: Path) -> list[dict]:
    root = json.loads(path.read_text(encoding="utf-8"))["Data"]["RootChunk"]["root"]["Data"]
    return root.get("entries", [])


def resource_path(entry: dict, variant: str) -> str:
    value = entry.get(f"{variant}ResPath", {}).get("DepotPath", {})
    return str(value.get("$value", "")) if isinstance(value, dict) else str(value)


def build_records(english: dict, chinese: dict, voices: dict) -> list[dict]:
    records = []
    for string_id, en in english.items():
        zh = chinese.get(string_id)
        if not zh or en.get("_content_group") != zh.get("_content_group"):
            continue
        vo = voices.get(string_id, {})
        if vo.get("_content_group") != en.get("_content_group"):
            vo = {}  # DLC text cannot borrow a base-game performance with a reused ID.
        alternatives = []
        for variant in ("female", "male"):
            en_text = display_text(en.get(f"{variant}Variant") or en.get("femaleVariant", ""))
            zh_text = display_text(zh.get(f"{variant}Variant") or zh.get("femaleVariant", ""))
            depot = resource_path(vo, variant)
            if not en_text or not zh_text or en_text.startswith("[db_"):
                continue
            audio = {"archive": vo["archive"], "depot": depot} if depot.casefold().endswith(".wem") else None
            signature = (en_text, zh_text, depot)
            if signature in alternatives:
                continue
            alternatives.append(signature)
            female = resource_path(vo, "female")
            male = resource_path(vo, "male")
            # Different paths can encode V's voice or an NPC addressing male /
            # female V. Both need the configured player variant when text alone
            # cannot establish which performance belongs to this playthrough.
            player_voice = variant if male and female and male != female else None
            records.append({"text_id": f"cyberpunk:{string_id}:{variant}",
                            "english": en_text, "chinese": zh_text, "audio": audio,
                            "player_voice": player_voice})
    return records


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    source_fingerprint = fingerprint(install)
    executable = ensure_wolvenkit(data_dir / "tools")
    cache = data_dir / "index-cache" / hashlib.sha256(source_fingerprint.encode()).hexdigest()[:16]
    english, chinese, voices = {}, {}, {}
    for archive in archive_sources(install):
        if archive.name.removeprefix('ep1_') not in {'lang_en_text.archive', 'lang_zh-cn_text.archive', 'lang_zh-cn_voice.archive'}:
            continue
        group = "ep1" if archive.parent.name == "ep1" or archive.name.startswith("ep1_") else "content"
        destination = cache / archive.parent.name / archive.stem
        complete = destination / "complete.json"
        if not complete.is_file():
            progress(f"Extracting {archive.stem}")
            destination.mkdir(parents=True, exist_ok=True)
            pattern = r".*voiceovermap.*\.json$" if "voice" in archive.name else r".*subtitles.*\.json$"
            run_wolvenkit(executable, "unbundle", archive, "-o", destination, "-r", pattern, "-v", "quiet")
            # Omit --outpath: WolvenKit preserves resource directories when
            # writing beside input files; flattened output loses same-name scenes.
            run_wolvenkit(executable, "cr2w", "-s", destination, "-v", "quiet")
            complete.write_text("{}")
        for path in destination.rglob("*.json.json"):
            for entry in json_entries(path):
                string_id = str(entry.get("stringId", ""))
                if not string_id:
                    continue
                if "voice" in archive.name:
                    # Only ordinary VO: holocall/helmet maps apply audio effects
                    # to the same line and should not replace its clean voice.
                    if path.name not in {"voiceovermap.json.json", "voiceovermap_1.json.json"}:
                        continue
                    voices[string_id] = {**entry, "archive": archive.relative_to(install).as_posix(), "_content_group": group}
                elif "lang_en_" in archive.name:
                    english[string_id] = {**entry, "_content_group": group}
                else:
                    chinese[string_id] = {**entry, "_content_group": group}
    if fingerprint(install) != source_fingerprint:
        raise ValueError("Cyberpunk files changed while indexing; retry after Steam finishes updating")
    records = build_records(english, chinese, voices)
    if not records:
        raise ValueError("No official bilingual Cyberpunk subtitles could be extracted")
    mapped = sum(bool(r["audio"]) for r in records)
    expansion_voices = sum(bool(r["audio"]) and
        (Path(r["audio"]["archive"]).parent.name == "ep1" or Path(r["audio"]["archive"]).name.startswith("ep1_"))
        for r in records)
    expansion_message = f"; {expansion_voices:,} Phantom Liberty voice mappings" if expansion_voices else ""
    return {"format": 1, "install": str(install), "fingerprint": source_fingerprint, "records": records,
            "message": (f"{len(records):,} bilingual pairs; {mapped:,} Mandarin voices{expansion_message}" if mapped else
                        "Chinese subtitles indexed; install the official Mandarin voice pack in Steam")}


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Cyberpunk voice locale')
    stamp = fingerprint(install)
    available = {locale for locale, code in TEXT_LOCALES.items() if any(
        p.name.removeprefix('ep1_') == f'lang_{code}_text.archive' for p in archive_sources(install))}
    targets = {value: resolve_locale(value, available) for value in target_locales}
    if source_locale not in available:
        raise ValueError('Install the selected official Cyberpunk text pack before preparing it.')
    requested = {source_locale, *(value for value in targets.values() if value)}
    selected = {f'lang_{TEXT_LOCALES[locale]}_text.archive' for locale in requested}
    selected.add(f'lang_{TEXT_LOCALES[source_locale]}_voice.archive')
    executable = ensure_wolvenkit(data_dir / 'tools')
    cache = data_dir / 'index-cache' / hashlib.sha256(stamp.encode()).hexdigest()[:16]
    tables = {locale: {} for locale in requested}
    voices = {}
    code_to_locale = {TEXT_LOCALES[locale]: locale for locale in requested}
    for archive in archive_sources(install):
        name = archive.name.removeprefix('ep1_')
        if name not in selected:
            continue
        group = 'ep1' if archive.parent.name == 'ep1' or archive.name.startswith('ep1_') else 'content'
        destination = cache / archive.parent.name / archive.stem
        if not (destination / 'complete.json').is_file():
            progress(f'Extracting selected {archive.stem}')
            destination.mkdir(parents=True, exist_ok=True)
            pattern = r'.*voiceovermap.*\.json$' if '_voice.' in name else r'.*subtitles.*\.json$'
            run_wolvenkit(executable, 'unbundle', archive, '-o', destination, '-r', pattern, '-v', 'quiet')
            run_wolvenkit(executable, 'cr2w', '-s', destination, '-v', 'quiet')
            (destination / 'complete.json').write_text('{}')
        code = name.removeprefix('lang_').removesuffix('_text.archive').removesuffix('_voice.archive')
        for path in destination.rglob('*.json.json'):
            if '_voice.' in name and path.name not in {'voiceovermap.json.json', 'voiceovermap_1.json.json'}:
                continue
            for entry in json_entries(path):
                identity = str(entry.get('stringId', ''))
                if not identity:
                    continue
                key = (group, identity)
                if '_voice.' in name:
                    voices[key] = {**entry, 'archive': archive.relative_to(install).as_posix()}
                else:
                    tables[code_to_locale[code]][key] = entry
    rows = []
    for (group, identity), entry in tables[source_locale].items():
        voice = voices.get((group, identity), {})
        seen = set()
        for variant in ('female', 'male'):
            text = display_text(entry.get(variant + 'Variant') or entry.get('femaleVariant', ''))
            depot = resource_path(voice, variant)
            if not text or text.startswith('[db_') or (text, depot) in seen:
                continue
            seen.add((text, depot))
            texts = {source_locale: text}
            for locale in requested - {source_locale}:
                target = tables[locale].get((group, identity), {})
                value = display_text(target.get(variant + 'Variant') or target.get('femaleVariant', ''))
                if value:
                    texts[locale] = value
            rows.append({'text_id': f'cyberpunk:{identity}:{variant}', 'english': texts.get('en', ''),
                'chinese': texts.get('zh-Hans', ''), 'source_locale': source_locale, 'source_text': text,
                'texts': texts, 'audio_locale': source_locale,
                'audio': {'archive': voice['archive'], 'depot': depot, 'locale': source_locale} if depot.casefold().endswith('.wem') else None,
                'player_voice': variant if resource_path(voice, 'female') and resource_path(voice, 'male')
                    and resource_path(voice, 'female') != resource_path(voice, 'male') else None})
    if not rows or fingerprint(install) != stamp:
        raise ValueError('Cyberpunk language files changed or contain no official dialogue; finish the launcher update and retry.')
    mapped = sum(bool(row['audio']) for row in rows)
    missing = [code for code, locale in targets.items() if locale is None]
    return {'format': 2, 'game': 'cyberpunk', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': rows, 'missing_translation_locales': missing,
        'message': f'{len(rows):,} official {source_locale} lines; {mapped:,} original voices' +
                   (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
                   ('; install the selected voice pack in the game launcher' if not mapped else '')}


def _check_voice_locale(audio, archive):
    locale = audio.get('locale')
    if locale is not None and (locale not in SUPPORTED_LOCALES or
            archive.name.removeprefix('ep1_') != f'lang_{TEXT_LOCALES[locale]}_voice.archive'):
        raise ValueError('Original Cyberpunk voice does not match its selected locale')


def extract_voice(install: Path, audio: dict, executable: Path, destination: Path) -> bytes:
    archive = (install / audio["archive"]).resolve()
    _check_voice_locale(audio, archive)
    if not archive.is_relative_to(install.resolve()) or archive not in [p.resolve() for p in archive_sources(install)] or "voice" not in archive.name:
        raise ValueError("Original voice archive is unavailable")
    depot = audio["depot"]
    if not depot.casefold().endswith(".wem") or ".." in depot or ":" in depot or PureWindowsPath(depot).root:
        raise ValueError("Invalid original voice resource")
    run_wolvenkit(executable, "unbundle", archive, "-o", destination,
                  "-r", "^" + re.escape(depot) + "$", "-v", "quiet")
    path = destination / depot.replace("\\", "/")
    if not path.resolve().is_relative_to(destination.resolve()) or not path.is_file():
        raise FileNotFoundError("Original voice was not found in the selected installed archive")
    return path.read_bytes()


def extract_voices(install: Path, audios: list[dict], executable: Path, destination: Path) -> list[bytes]:
    allowed = {p.resolve() for p in archive_sources(install)}
    groups, bindings = {}, []
    for audio in audios:
        archive = (install / audio['archive']).resolve()
        _check_voice_locale(audio, archive)
        depot = audio['depot']
        if not archive.is_relative_to(install.resolve()) or archive not in allowed or 'voice' not in archive.name:
            raise ValueError('Original voice archive is unavailable')
        if not depot.casefold().endswith('.wem') or '..' in depot or ':' in depot or PureWindowsPath(depot).root:
            raise ValueError('Invalid original voice resource')
        groups.setdefault(archive, []).append(depot)
        bindings.append((archive, depot))
    directories = {}
    for number, (archive, depots) in enumerate(groups.items()):
        directory = destination / str(number); directory.mkdir(parents=True, exist_ok=True)
        directories[archive] = directory
        pattern = '^(?:' + '|'.join(re.escape(p) for p in dict.fromkeys(depots)) + ')$'
        run_wolvenkit(executable, 'unbundle', archive, '-o', directory, '-r', pattern, '-v', 'quiet')
    result = []
    for archive, depot in bindings:
        directory = directories[archive]
        path = directory / depot.replace('\\', '/')
        if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
            raise FileNotFoundError('Original voice is missing from the selected installed archive')
        result.append(path.read_bytes())
    return result
