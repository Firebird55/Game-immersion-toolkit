"""Read selected NTE localization and exact original Wwise event references.

The native reader is toolkit-owned glue for separately downloaded UEExtractor.
Only installed game data is extracted, into private caches outside the game.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from .bilingual import contains_han
from .game_tools import download, install_archive
from .pragmata_audio import read_bank_play_layers
from .textmaps import display_text

READER_URL = "https://github.com/SolicenTEAM/UEExtractor/releases/download/v.1.0.8.7/UEExtractor.zip"
READER_SHA = "e89ffece53cc11970d08f6d0a683b67ca58882e8c51fb99de07923175eb96660"
READER_REVISION = "1dff3554320d530efff26a827819f0e011f1b892"
METADATA_URL = "https://api.github.com/repos/BlueHeisenberg/SCSKiller/issues/14"
MEDIA_ROOT = "HT/Content/WwiseAudio/Media/Chinese/"
LANGUAGE_INDEX_VERSION = 3
SUPPORTED_LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
TEXT_LOCALES = {'en': 'en', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-Hant', 'ja': 'ja', 'ko': 'ko',
    'fr': 'fr', 'de': 'de', 'es-ES': 'es', 'pt-BR': 'pt-BR', 'ru': 'ru', 'th': 'th', 'vi': 'vi', 'id': 'id'}
VOICE_LOCALES = {'en': 'English', 'zh-Hans': 'Chinese', 'zh-Hant': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean'}


def wwise_hash(value: str) -> int:
    result = 2166136261
    for byte in value.lower().encode("utf-8"):
        result = ((result * 16777619) & 0xffffffff) ^ byte
    return result


def dotnet_sdk() -> Path | None:
    candidates = [shutil.which("dotnet"), str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "dotnet/dotnet.exe")]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            result = subprocess.run([candidate, "--list-sdks"], capture_output=True, timeout=15,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0 and re.search(rb"(?m)^10\.\d+\.\d+ ", result.stdout):
                return Path(candidate)
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def ensure_extractor(directory: Path) -> Path:
    sdk = dotnet_sdk()
    if sdk is None:
        raise ValueError("NTE needs the .NET 10 SDK. Install it from https://dotnet.microsoft.com/download/dotnet/10.0, then prepare tools again.")
    upstream = directory / "upstream"
    install_archive(READER_URL, READER_SHA, upstream, ("UEExtractor.dll", "UEExtractor.runtimeconfig.json"))
    from .wuthering_assets import ensure_unreal_decompression
    ensure_unreal_decompression(upstream)
    notice = upstream / "UEEXTRACTOR-LICENSE.txt"
    if not notice.is_file():
        data = download(f"https://raw.githubusercontent.com/SolicenTEAM/UEExtractor/{READER_REVISION}/LICENSE")
        if b"MIT License" not in data:
            raise ValueError("Game reader license notice is unavailable")
        notice.write_bytes(data)
    source = Path(__file__).resolve().parents[1] / "scripts/game-readers"
    inputs = [source / "NteReader.cs", source / "NteReader.csproj"]
    revision = hashlib.sha256(b"".join(path.read_bytes() for path in inputs)).hexdigest()
    target, marker = directory / "NteReader.dll", directory / "reader-build.json"
    try:
        receipt = json.loads(marker.read_text(encoding="utf-8"))
        if receipt["source"] == revision and all((directory / name).is_file() and
                hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
                for name, digest in receipt["files"].items()) and target.is_file():
            return target
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Build intermediates and binaries stay in the ignored tool cache. No NuGet
    # package is needed; use the installed .NET 10 framework reference packs.
    with tempfile.TemporaryDirectory(prefix="nte-build-", dir=directory) as value:
        build = Path(value)
        result = subprocess.run([str(sdk), "build", str(inputs[1]), "-c", "Release", "-o", str(build / "out"),
            f"-p:BaseIntermediateOutputPath={build / 'obj'}/", "--nologo", "--ignore-failed-sources"],
            capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("NTE reader build failed; install or repair the .NET 10 SDK")
        files = {}
        for name in ("NteReader.dll", "NteReader.deps.json", "NteReader.runtimeconfig.json"):
            content = (build / "out" / name).read_bytes()
            files[name] = hashlib.sha256(content).hexdigest()
            (directory / name).write_bytes(content)
        marker.write_text(json.dumps({"source": revision, "files": files}), encoding="utf-8")
    return target


def archive_sources(install: Path) -> list[Path]:
    root = install / "Client/WindowsNoEditor/HT/Content"
    return sorted((p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in
                   {".pak", ".utoc", ".ucas", ".hpw"}), key=str)


def fingerprint(install: Path) -> str:
    sources = archive_sources(install)
    executable = install / "Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe"
    if executable.is_file():
        sources.append(executable)
    values = [f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in sources]
    from .nte_cinematics import CATALOG_REVISION
    return hashlib.sha256(("reader4|" + CATALOG_REVISION + '|' + "|".join(values)).encode()).hexdigest()


def _metadata_path(install: Path, stamp: str) -> Path:
    identity = hashlib.sha256((str(install.resolve()) + stamp).encode()).hexdigest()
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Proxy Transcript/nte-archive" / (identity + ".dpapi")


@lru_cache(maxsize=2)
def _archive_metadata(install: Path, stamp: str) -> str:
    from .lexirise import _protect
    path = _metadata_path(install, stamp)
    if path.is_file():
        try:
            value = _protect(path.read_bytes(), decrypt=True).decode()
            if re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
                return value
        except Exception:
            pass
    payload = json.loads(download(METADATA_URL))
    values = list(dict.fromkeys(re.findall(r"0x[0-9a-fA-F]{64}", payload.get("body", ""))))
    if len(values) != 1:
        raise ValueError("NTE archive version needs updated reader metadata")
    return values[0]


def run_reader(install: Path, executable: Path, destination: Path, mode: str, depot: str | None = None, cinema_events: list[str] | None = None, depots: list[str] | None = None, *, locales=None, voice_language=None) -> None:
    install, executable, destination = install.resolve(), executable.resolve(), destination.resolve()
    if destination.resolve().is_relative_to(install.resolve()):
        raise ValueError("Reader outputs must stay outside the game installation")
    sdk = dotnet_sdk()
    if sdk is None or not executable.is_file():
        raise ValueError("Prepare NTE tools in Setup before indexing")
    stamp = fingerprint(install)
    root = install / "Client/WindowsNoEditor/HT/Content"
    if any(any(part.startswith("~") for part in path.relative_to(root).parts) or
           not re.fullmatch(r"pakchunk\d+[-A-Za-z0-9_]*\.pak", path.name)
           for path in root.rglob("*.pak")):
        raise ValueError("NTE indexing requires official archives; remove unsupported mod archives before indexing")
    # Metadata is never an argument or a log entry. Keep it in memory and pass
    # via stdin. A host-protected cache allows playback without a network call.
    key = _archive_metadata(install, stamp)
    request = {"archive_metadata": key}
    if locales is not None:
        request['locales'] = locales
    if voice_language is not None:
        if voice_language not in set(VOICE_LOCALES.values()):
            raise ValueError('Unsupported NTE voice locale')
        request['voice_language'] = voice_language
    if depot is not None:
        request["depot"] = depot
    if depots is not None:
        request['depots'] = depots
    if cinema_events is not None:
        request['cinema_events'] = cinema_events
    try:
        result = subprocess.run([str(sdk), str(executable), mode, str(install), str(executable.parent / "upstream"), str(destination)],
            input=json.dumps(request).encode(), capture_output=True, timeout=600, cwd=executable.parent / "upstream",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("NTE reader could not complete") from None
    if result.returncode:
        raise RuntimeError("NTE extraction failed; check installed archives and reader compatibility")
    if os.name == "nt":
        from .lexirise import _protect
        path = _metadata_path(install, stamp)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".pending")
            temporary.write_bytes(_protect(key.encode()))
            temporary.replace(path)


def punctuation_anchors(text):
    # Native OCR can read the game's authored opening double dash as one or
    # two Han horizontal strokes. Keep the official text and voice unchanged;
    # ordinary words and unsupported dialogue rewrites remain exact-only.
    match = re.match(r'^[—–―]{2,}\s*(.+)', text)
    return [prefix + match[1] for prefix in ('一', '一一', 'ー', 'ーー')] if match else []


def ocr_anchors(text, locale):
    forms = [text, *punctuation_anchors(text)]
    if locale == 'ja':
        # A repeated vowel may be typeset small for expressive speech. Native
        # OCR sometimes gives it full size. Do not fold digraphs such as ティ
        # or small ゃ/ゅ/ょ, whose size can change the actual syllable.
        vowels = [('あかがさざただなはばぱまやらわ', 'ぁ', 'あ'),
                  ('いきぎしじちぢにひびぴみり', 'ぃ', 'い'),
                  ('うくぐすずつづぬふぶぷむゆる', 'ぅ', 'う'),
                  ('えけげせぜてでねへべぺめれ', 'ぇ', 'え'),
                  ('おこごそぞとどのほぼぽもよろを', 'ぉ', 'お')]
        for form in list(forms):
            changes = [(i, full) for preceding, small, full in vowels for i in range(1, len(form))
                       if form[i] == small and form[i - 1] in preceding]
            if len(changes) <= 4:
                for mask in range(1, 1 << len(changes)):
                    value = list(form)
                    for bit, (position, full) in enumerate(changes):
                        if mask & (1 << bit):
                            value[position] = full
                    forms.append(''.join(value))
    return list(dict.fromkeys(value for value in forms if value != text))


def build_records(cache: Path, cinema_bindings: list[dict] | None = None, *, source_locale=None, target_locales=()) -> list[dict]:
    localization = json.loads((cache / "localization.json").read_text(encoding="utf-8"))
    source_code = TEXT_LOCALES[source_locale] if source_locale else 'en'
    if not localization.get(source_code):
        raise ValueError('Install the selected official NTE text pack before preparing this language.')
    english = {(r["ns"], r["key"]): display_text(r["value"]) for r in localization[source_code]}
    chinese = english if source_locale else {(r["ns"], r["key"]): display_text(r["value"]) for r in localization['zh-CN']}
    voice_language = VOICE_LOCALES[source_locale] if source_locale else 'Chinese'
    media_root = 'HT/Content/WwiseAudio/Media/' + voice_language + '/'
    media = set(json.loads((cache / "media.json").read_text(encoding="utf-8")))
    events = {}
    cinema_events = {}
    for path in (cache / "banks").glob("Play_Vo_*.bnk"):
        data = path.read_bytes()
        if len(data) < 20 or data[:4] != b"BKHD" or struct.unpack_from("<I", data, 16)[0] != wwise_hash(voice_language):
            continue
        event = path.stem
        if struct.unpack_from("<I", data, 12)[0] != wwise_hash(event):
            continue
        try:
            layers = read_bank_play_layers(path, allowed_versions=(154,)).get(wwise_hash(event), [])
        except (ValueError, IndexError, struct.error):
            continue
        variants = [(None, layers)]
        if not layers and event.startswith('Play_Vo_CG_'):
            try:
                variants = [(gender, read_bank_play_layers(path, allowed_versions=(154,),
                             switch_states={wwise_hash('Sex_Switch'): wwise_hash(gender)}).get(wwise_hash(event), []))
                            for gender in ['female', 'male']]
            except (ValueError, IndexError, struct.error):
                continue
        for gender, selected in variants:
            if len(selected) != 1:
                continue
            layer = selected[0]
            depot = f"{media_root}{layer['media_id']}.wem"
            if depot not in media:
                continue
            audio = {"depot": depot, "event": event, **({'locale': 'zh-Hans' if source_locale == 'zh-Hant' else source_locale} if source_locale else {})}
            if gender is None:
                events[event.lower()] = audio
            if layer['delay_seconds'] == 0:
                cinema_events.setdefault(event.lower(), []).append({'player_voice': gender,
                    'audio': {**audio, 'gain_db': layer['gain_db']}})
    pairs_by_key = {}
    for (ns, key), en in english.items():
        pairs_by_key.setdefault(key.lower(), set()).add((en, chinese.get((ns, key), "")))
    records = []
    for (ns, key), en in english.items():
        zh = chinese.get((ns, key), "")
        audio = events.get(("Play_Vo_" + key).lower())
        if en and (source_locale or (contains_han(zh) and audio)) and len(pairs_by_key[key.lower()]) == 1:
            records.append({"text_id": f"nte:{ns}:{key}", "english": en, "chinese": zh, "audio": audio})
    if cinema_bindings:
        from .nte_cinematics import movie_records
        subtitles = json.loads((cache / 'cinema-subtitles.json').read_text(encoding='utf8'))
        existing = {r['text_id'] for r in records}
        movies = movie_records(cinema_bindings, subtitles, english, chinese, cinema_events, require_han=source_locale is None)
        if source_locale:
            movie_ids = {r['text_id'] for r in movies}
            records = [r for r in records if r['audio'] or r['text_id'] not in movie_ids]
            existing = {r['text_id'] for r in records}
        records.extend(r for r in movies if r['text_id'] not in existing)
    if source_locale:
        from .languages import audio_locale
        tables = {locale: {(r['ns'], r['key']): display_text(r['value']) for r in localization.get(TEXT_LOCALES[locale], [])}
                  for locale in {source_locale, *target_locales}}
        for row in records:
            identity = row['text_id'].split(':', 2)[1:]
            if row.get('player_voice'):
                identity[1] = identity[1].removesuffix(':' + row['player_voice'])
            texts = {locale: table[tuple(identity)] for locale, table in tables.items() if table.get(tuple(identity))}
            row.update(source_text=row['english'], source_locale=source_locale, texts=texts,
                       audio_locale=audio_locale(source_locale), english=texts.get('en', ''), chinese=texts.get('zh-Hans', ''))
            row['ocr_texts'] = {locale: anchors for locale, text in texts.items() if (anchors := ocr_anchors(text, locale))}
    return records


def refresh_catalog(data_dir: Path, force=False) -> dict:
    from .game_catalogs import refresh_catalog as refresh
    from .nte_cinematics import catalog_rows
    return refresh('nte', data_dir, catalog_rows, force)


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    from .nte_cinematics import load_catalog, catalog_rows, movie_bindings, CATALOG_REVISION
    from .game_catalogs import read_snapshot
    snapshot = read_snapshot('nte', data_dir)
    bindings = movie_bindings(catalog_rows(snapshot['catalog']) if snapshot else load_catalog(data_dir / 'movie-catalog' / CATALOG_REVISION))
    stamp = fingerprint(install)
    executable = ensure_extractor(data_dir / "tools")
    # New movie bindings must invalidate extracted event caches even when the
    # game files themselves have not changed. Voice staleness remains physical.
    cache_id = hashlib.sha256((stamp + (snapshot['digest'] if snapshot else CATALOG_REVISION)).encode()).hexdigest()
    cache = data_dir / "index-cache" / cache_id[:16]
    if not (cache / "complete.json").is_file():
        progress("Reading installed NTE English and Chinese dialogue and exact Chinese voice events")
        with tempfile.TemporaryDirectory(prefix="nte-index-", dir=data_dir) as value:
            staging = Path(value)
            run_reader(install, executable, staging, "index", cinema_events=sorted({r['event'] for r in bindings}))
            records = build_records(staging, bindings)
            if not records or fingerprint(install) != stamp:
                raise ValueError("NTE files changed or contain no supported bilingual voices; finish the game download and retry")
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "complete.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    records = json.loads((cache / "complete.json").read_text(encoding="utf-8"))
    if not records or fingerprint(install) != stamp:
        raise ValueError("NTE files changed while indexing; retry after the game update finishes")
    return {"format": 1, "install": str(install), "fingerprint": stamp, "records": records,
            "catalog_digest": snapshot['digest'] if snapshot else None,
            "catalog_revision": snapshot['revision'] if snapshot else CATALOG_REVISION,
            "message": f"{len(records):,} verified bilingual NTE lines with original Mandarin voices"}


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    from .nte_cinematics import load_catalog, catalog_rows, movie_bindings, CATALOG_REVISION
    from .game_catalogs import read_snapshot
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported NTE study/audio locale')
    snapshot = read_snapshot('nte', data_dir)
    bindings = movie_bindings(catalog_rows(snapshot['catalog']) if snapshot else load_catalog(data_dir / 'movie-catalog' / CATALOG_REVISION))
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(locale for locale in targets.values() if locale)}
    stamp = fingerprint(install)
    cache_id = hashlib.sha256(json.dumps([stamp, source_locale, sorted(selected),
        snapshot['digest'] if snapshot else CATALOG_REVISION, LANGUAGE_INDEX_VERSION]).encode()).hexdigest()[:16]
    cache = data_dir / 'language-cache' / cache_id
    tool = ensure_extractor(data_dir / 'tools')
    if not (cache / 'complete.json').is_file():
        progress(f'Reading selected NTE {source_locale} text and original voice events')
        with tempfile.TemporaryDirectory(prefix='nte-language-', dir=data_dir) as value:
            staging = Path(value)
            run_reader(install, tool, staging, 'index', cinema_events=sorted({r['event'] for r in bindings}),
                       locales=[TEXT_LOCALES[locale] for locale in sorted(selected)], voice_language=VOICE_LOCALES[source_locale])
            localization = json.loads((staging / 'localization.json').read_text(encoding='utf8'))
            available = {locale for locale in selected if TEXT_LOCALES[locale] in localization}
            rows = build_records(staging, bindings, source_locale=source_locale, target_locales=available - {source_locale})
            if not rows or fingerprint(install) != stamp:
                raise ValueError('NTE files changed or selected dialogue is incomplete; previous table retained.')
            cache.mkdir(parents=True, exist_ok=True)
            (cache / 'complete.json').write_text(json.dumps({'records': rows, 'available': sorted(available)}, ensure_ascii=False), encoding='utf8')
    result = json.loads((cache / 'complete.json').read_text(encoding='utf8'))
    if fingerprint(install) != stamp:
        raise ValueError('NTE files changed during preparation; previous table retained.')
    rows = result['records']; mapped = sum(bool(row.get('audio')) for row in rows)
    missing = [target for target, locale in targets.items() if locale not in result['available']]
    return {'format': 2, 'game': 'nte', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': rows, 'missing_translation_locales': missing,
        'message': f'{len(rows):,} official {source_locale} lines; {mapped:,} original voices' +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; install the selected official voice pack' if not mapped else '')}


def _voice_language(audio):
    locale = audio.get('locale', 'zh-Hans')
    language = VOICE_LOCALES.get(locale)
    if language is None or not re.fullmatch(re.escape('HT/Content/WwiseAudio/Media/' + language + '/') + r'\d+\.wem', audio.get('depot', '')):
        raise ValueError('Invalid NTE original voice locale or reference')
    return language


def extract_voice(install: Path, audio: dict, executable: Path, destination: Path) -> bytes:
    language = _voice_language(audio)
    options = {'voice_language': language} if audio.get('locale') else {}
    run_reader(install, executable, destination, "voice", audio["depot"], **options)
    data = (destination / "voice.wem").read_bytes()
    if data[:4] != b"RIFF":
        raise ValueError("NTE voice is not a supported original WEM")
    return data


def extract_voices(install: Path, audios: list[dict], executable: Path, destination: Path) -> list[bytes]:
    depots = [audio.get('depot', '') for audio in audios]
    languages = {_voice_language(audio) for audio in audios}
    if not 1 <= len(depots) <= 8 or len(languages) != 1:
        raise ValueError('NTE batches require one selected original voice language')
    options = {'voice_language': next(iter(languages))} if any(audio.get('locale') for audio in audios) else {}
    run_reader(install, executable, destination, 'voices', depots=depots, **options)
    result = [(destination / f'{i}.wem').read_bytes() for i in range(len(depots))]
    if any(data[:4] != b'RIFF' for data in result):
        raise ValueError('NTE voice is not a supported original WEM')
    return result
