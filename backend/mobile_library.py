"""Private, resumable mobile exports. Never serialize original archive references."""
from __future__ import annotations

from .runtime_paths import data_root as runtime_data_root
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import shutil
import threading
import time
import zipfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from .game_paths import GAMES, GAME_NAMES
from .textmaps import TextMapIndex, display_text
from .mobile_bundle import write_bundle
from .mobile_export_layout import work_folder, catalog_name, voice_pack_name, export_folder_name, write_instructions, archive_previous_exports, hide_work_metadata

FORMAT = "proxy-mobile-library-v1"
PACK_LIMIT = 512 * 1024 * 1024
CATALOG_LIMIT = 128 * 1024 * 1024
ROW_LIMIT = 250000


def export_workers():
    """Bound decoder CPU/memory use while leaving capacity for the companion."""
    return min(8, max(1, (os.cpu_count() or 2) // 2))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class ExportCancelled(Exception):
    pass


def write_pack(path, manifest, entries):
    """Deterministic STORE archives enable bounded, random-access mobile reads."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, value in [("manifest.json", encoded(manifest)), *entries]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            if isinstance(value, Path):
                with archive.open(info, "w") as dest, value.open("rb") as source:
                    shutil.copyfileobj(source, dest, 1024 * 1024)
            else:
                archive.writestr(info, value)
    if path.stat().st_size > PACK_LIMIT:
        raise ValueError("Pack exceeds the mobile size limit")


def export_library(game, records, output, *, voice=None, include_audio=True, check=lambda: None,
                   cancel=None, progress=lambda value: None, pack_limit=PACK_LIMIT, workers=1):
    """All intermediate work is private; latest.json changes only on complete success."""
    if game not in GAMES or not 4096 <= pack_limit <= PACK_LIMIT or type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("Unsupported game or pack size")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    work = work_folder(output)
    cache = work / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    cancel = cancel or threading.Event()

    def guard():
        if cancel.is_set():
            raise ExportCancelled()
        check()

    guard()
    getattr(check, "force", check)()
    rows, clips, source_cache, identities = [], {}, {}, {}
    sources, source_rows = {}, {}
    for number, original in enumerate(records):
        guard()
        row = {key: original[key] for key in ("textId", "english", "chinese", "speakerEnglish", "speakerChinese",
               "playerVoice", "anchorsEnglish", "anchorsChinese", "channels", "sourceVoice", "sourceLanguage", "sourceLocale", "sourceText", "translationLocale", "translationText", "audioLocale", "anchorsSource", "anchorsTranslation", "memberTextIds") if key in original}
        source = original.get("sourceVoice")
        row["id"] = digest([game, row["textId"], row["english"], row["chinese"], row.get("playerVoice")])
        if row["id"] in identities:
            if identities[row["id"]] != source:
                raise ValueError("Conflicting original voices for one dialogue identity")
            continue
        identities[row["id"]] = source
        row["audio"] = None
        if include_audio and source:
            sources.setdefault(source, (original, number))
            source_rows[source] = source_rows.get(source, 0) + 1
        rows.append(row)
        if len(rows) > ROW_LIMIT:
            raise ValueError("Catalog exceeds the mobile row limit")

    def cached_voice(source):
        cached = cache / (source + ".mp3")
        signature = cache / (source + ".json")
        if cached.is_file() and signature.is_file():
            try:
                sha = file_digest(cached)
                if json.loads(signature.read_text())["sha256"] == sha:
                    return cached, sha
            except (OSError, ValueError, KeyError):
                pass
        return None

    def publish_voice(source, produced):
        cached = cache / (source + ".mp3")
        signature = cache / (source + ".json")
        produced = Path(produced)
        temporary = cached.with_suffix(".pending")
        # Export-owned decoded files can move into cache instead of keeping two
        # copies. Other callers may supply reusable inputs, so retain those.
        if produced.parent.resolve() in {(output / "decoded").resolve(), (work / "decoded").resolve()}:
            produced.replace(temporary)
        else:
            shutil.copyfile(produced, temporary)
        sha = file_digest(temporary)
        temporary.replace(cached)
        marker = signature.with_suffix(".json.pending")
        marker.write_bytes(encoded({"sha256": sha}))
        marker.replace(signature)
        return cached, sha

    batch_voice = getattr(voice, 'batch', None)
    batch_size = 8 if callable(batch_voice) else 1
    def convert(group):
        if cancel.is_set():
            raise ExportCancelled()
        results, missing = {}, []
        for source, original in group:
            cached = cached_voice(source)
            if cached:
                results[source] = cached
            else:
                missing.append((source, original))
        if missing:
            if voice is None:
                raise ValueError("Prepare original voice tools before exporting")
            if cancel.is_set():
                raise ExportCancelled()
            if callable(batch_voice):
                produced = batch_voice([original for source, original in missing])
            else:
                produced = [voice(*missing[0][1])]
            if len(produced) != len(missing):
                raise ValueError("Original voice batch returned incomplete bindings")
            for (source, original), path in zip(missing, produced):
                results[source] = publish_voice(source, path)
        return results

    audio_bytes, done = 0, len(rows) - sum(source_rows.values())
    batch_key = getattr(voice, 'batch_key', None)
    jobs = iter(sorted(sources.items(), key=lambda item: batch_key(item[1][0])) if callable(batch_key) else sources.items())
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mobile-export") as pool:
        pending = {}
        def submit():
            group = list(islice(jobs, batch_size))
            if group:
                pending[pool.submit(convert, group)] = group
        try:
            for _ in range(min(workers, len(sources))):
                submit()
            while pending:
                guard()
                completed, _ = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                results = {future: future.result() for future in completed}
                for future in completed:
                    pending.pop(future)
                    for source, (path, sha) in results[future].items():
                        source_cache[source] = sha
                        if sha not in clips:
                            audio_bytes += path.stat().st_size
                        clips[sha] = path
                        done += source_rows[source]
                        progress({"state": "exporting", "progress": int(done/max(1, len(rows))*85),
                                  "done": done, "total": len(rows), "audioBytes": audio_bytes,
                                  "estimatedAudioBytes": round(audio_bytes * len(sources) / len(source_cache)),
                                  "workers": workers, "batchSize": batch_size,
                                  "message": f"Preparing verified voices · {workers} workers, {batch_size} clips per batch"})
                        guard()
                    guard()
                    submit()
        finally:
            for future in pending:
                future.cancel()
    for row in rows:
        row["audio"] = source_cache.get(row.get("sourceVoice"))
    if not rows:
        raise ValueError("No verified bilingual dialogue available; refresh game data first")
    guard()
    revision = digest([FORMAT, "segmented-catalog", rows])
    destination = output / export_folder_name(game, revision)
    staging = work / (revision + ".pending")
    staging.mkdir(exist_ok=True)
    chunks, current, size = [], [], 2048
    for sha, path in sorted(clips.items()):
        required = path.stat().st_size + 1024
        if required + 2048 > pack_limit or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("A voice clip is too large for a mobile pack")
        if current and (size + required > pack_limit or len(current) >= 65530):
            chunks.append(current)
            current, size = [], 2048
        current.append((sha, path)); size += required
    if current:
        chunks.append(current)
    parts_root = work / 'libraries'
    parts_root.mkdir(exist_ok=True)
    packs = []
    for pack_number, chunk in enumerate(chunks):
        guard()
        index = {sha: {"size": path.stat().st_size, "sha256": sha} for sha, path in chunk}
        pack_id = digest([game, index])
        name = voice_pack_name(game, pack_number + 1, len(chunks), pack_id)
        packs.append({"id": pack_id, "name": name, "clips": list(index)})
        target = staging / name
        manifest = {"format": FORMAT, "kind": "voices", "game": game, "id": pack_id, "clips": index}
        candidates = [*parts_root.glob("*/" + name), *output.glob("*/" + name), *(work / 'previous-libraries').glob("*/" + name)]
        previous = next((p for p in candidates
                         if (p.parent / catalog_name(game)).is_file()), None)
        if previous and previous.stat().st_size <= PACK_LIMIT:
            # Verify an existing completed pack before reuse; cache corruption cannot be promoted.
            try:
                with zipfile.ZipFile(previous) as old:
                    valid = json.loads(old.read("manifest.json")) == manifest and old.testzip() is None
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                valid = False
            if valid:
                shutil.copyfile(previous, target)
            else:
                write_pack(target, manifest, [("audio/" + sha + ".mp3", path) for sha, path in chunk])
        else:
            write_pack(target, manifest, [("audio/" + sha + ".mp3", path) for sha, path in chunk])
        progress({"state": "exporting", "progress": 85 + int(12 * (pack_number+1)/max(1,len(chunks))),
                  "message": f"Completed voice pack {pack_number+1} of {len(chunks)}"})
    segments, segment, segment_size = [], [], 0
    for row in rows:
        line = encoded(row) + b"\n"
        if segment and segment_size + len(line) > 4 * 1024 * 1024:
            segments.append(b"".join(segment)); segment, segment_size = [], 0
        segment.append(line); segment_size += len(line)
    if segment:
        segments.append(b"".join(segment))
    if len(segments) > 32 or sum(map(len, segments)) > CATALOG_LIMIT:
        raise ValueError("Catalog exceeds the mobile memory limit")
    catalog = [{"name": f"catalog/{i:05d}.ndjson", "size": len(value),
                "sha256": hashlib.sha256(value).hexdigest()} for i, value in enumerate(segments)]
    coverage = {"dialogue": len(rows), "mappedVoices": sum(bool(r.get("sourceVoice")) for r in rows),
                "exportedVoices": sum(bool(r["audio"]) for r in rows), "partial": True}
    manifest = {"format": FORMAT, "kind": "catalog", "game": game, "title": GAME_NAMES[game],
                "revision": revision, "sourceLocale": rows[0].get("sourceLocale", "zh-Hans"),
                "audioLocale": rows[0].get("audioLocale", "zh-Hans"), "translationLocale": rows[0].get("translationLocale", "en"), "languages": sorted({locale for row in rows for locale in (row.get("sourceLocale", "zh-Hans"), row.get("translationLocale", "en"))}), "coverage": coverage,
                "catalog": catalog, "packs": packs}
    name = catalog_name(game)
    write_pack(staging / name, manifest, [(item["name"], value) for item, value in zip(catalog, segments)])
    guard()
    getattr(check, "force", check)()
    # Inner packs remain private and resumable; only the bundle is transferred.
    parts = parts_root / revision
    if parts.resolve().parent != parts_root.resolve() or parts.is_symlink():
        raise ValueError("Unsafe private pack location")
    parts.mkdir(exist_ok=True)
    for path in staging.iterdir():
        path.replace(parts / path.name)
    staging.rmdir()
    transfer = work / (revision + ".transfer.pending")
    if destination.exists() and (destination.resolve().parent != output.resolve()
                                 or destination.is_symlink() or not destination.is_dir()):
        raise ValueError("Unsafe export destination")
    bundle = write_bundle(parts / name, transfer, guard=guard, progress=progress, reuse_from=destination)
    reused = bundle.parent == destination
    write_instructions(output, destination if reused else transfer,
                       transfer_folder=destination, library=bundle.name)
    guard()
    getattr(check, "force", check)()
    if not reused:
        if destination.exists():
            destination.rename(work / (revision + ".invalid-" + str(time.time_ns())))
        transfer.replace(destination)
    bundle = destination / bundle.name
    pointer = output / "latest.pending"
    pointer.write_bytes(encoded({"revision": revision, "folder": destination.name, "catalog": bundle.name, "bundle": bundle.name, "coverage": coverage}))
    guard()
    getattr(check, "force", check)()
    os.replace(pointer, output / "latest.json")
    hide_work_metadata(output / 'latest.json')
    # Tidying is optional once publication succeeded; failures must not turn a
    # valid completed export into an error or discard the previous library.
    try:
        archive_previous_exports(output, game, destination)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        pass
    result = {"state": "complete", "progress": 100, "message": "Open the single Mobile Library ZIP on your phone",
              "done": len(rows), "total": len(rows),
              "folder": str(destination), "bundle": str(bundle), "catalog": str(parts / name), "coverage": coverage, "bytes": sum(p.stat().st_size for p in destination.glob("*.zip"))}
    progress(result)
    return result


def prepare_source(root, game, decode_dir, *, expected_account_signature=None, expected_source_locale=None, source_path=None, translation_locale=None):
    """Adapt owned indexes and decoders without touching the user's transcript/audio history."""
    root, decode_dir = Path(root), Path(decode_dir)
    data, decoder = runtime_data_root(root), runtime_data_root(root) / "voice-assets/vgmstream/vgmstream-cli.exe"
    watched = {}
    service = None
    account_check = lambda: True
    if expected_account_signature is not None:
        from .accounts import AccountStore
        from .scoped_mobile_exports import account_signature
        scoped_accounts = AccountStore()
        account_check = lambda: account_signature(scoped_accounts) == expected_account_signature
        if not account_check():
            raise ValueError('Account changed before export preparation.')
    if source_path is None and game == "zzz" and not (data / 'languages/zzz').is_dir():
        if expected_source_locale not in (None, 'zh-Hans'):
            raise ValueError('The selected language table is unavailable; prepare it before exporting.')
        from .voice_assets import VoiceAssetService
        index = TextMapIndex(data / "textmaps")
        index.load(prepare_matching=False)
        service = VoiceAssetService(data / "voice-assets/manifest.json", decoder, decode_dir,
                                   data / "voice-assets/learned-manifest.json")
        from .speakers import _voice_token, _humanize_token
        inputs = [index.file_path(name) for name in ("en_base", "en_overwrite", "zh_base", "zh_overwrite")]
        inputs += [service.manifest]
        learned = data / "voice-assets/learned-manifest.json"
        if learned.exists():
            inputs.append(learned)
        records = []
        speaker_names = {}
        for values in index._records_by_normalized.values():
            for item in values:
                key = service._entry_key(item.text_id, item.english)
                channels = [c for c in ("dialogue", "cinematic", "gameplay") if index._is_allowed_record(item, c)]
                if channels:
                    row = {"textId": item.text_id, "english": display_text(item.english),
                           "chinese": display_text(item.chinese), "channels": channels, "sourceVoice": None}
                    if key is None:
                        records.append(row)
                        continue
                    audio = service._entries[key]
                    package = Path(audio["package"])
                    if package not in watched:
                        stat = package.stat()
                        watched[package] = (stat.st_size, stat.st_mtime_ns)
                    if watched[package] != (audio["package_size"], audio["package_mtime_ns"]):
                        raise ValueError("Game changed; refresh original voices first")
                    row["sourceVoice"] = digest(audio)
                    token = _voice_token(audio.get("source", ""))
                    if token not in speaker_names:
                        speaker_names[token] = index.resolve_display_name(_humanize_token(token)) if token else None
                    names = speaker_names[token]
                    if names:
                        row.update(speakerEnglish=names[0], speakerChinese=names[1])
                    records.append(row)
        package_folders = {path.parent for path in watched}
        def package_inventory():
            return sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns)
                          for folder in package_folders for p in folder.glob("*.pck"))
        inventory = package_inventory()
        source_check = lambda: package_inventory() == inventory
    else:
        from .language_preparation import selected_snapshot
        source, accounts, account = (Path(source_path), None, None) if source_path else selected_snapshot(root, game)
        directory = source.parent
        payload = json.loads(source.read_text(encoding="utf-8"))
        inputs = [source]
        target = None
        if payload.get('format') != 2 and expected_source_locale not in (None, 'zh-Hans'):
            raise ValueError('The selected language table is unavailable; prepare it before exporting.')
        if payload.get('format') == 2 and expected_source_locale and payload['source_locale'] != expected_source_locale:
            raise ValueError('Learning language changed before export preparation.')
        if payload.get('format') == 2:
            from .lexirise import LexiriseService
            from .lexirise_settings import account_settings
            from .languages import study_language, translation_language, resolve_locale
            if source_path:
                if not translation_locale:
                    raise ValueError('Automatic exports require an explicit translation locale.')
                target = translation_locale
            else:
                client = LexiriseService(data / 'lexirise', accounts=accounts).pin(study_language(payload['source_locale']))
                target = translation_language(account_settings(client), study_language(payload['source_locale']))
            if target.casefold() not in {value.casefold() for value in payload.get('targets_requested', [])}:
                raise ValueError('Prepare the account translation table in Languages before exporting.')
            prior_check = account_check
            if source_path:
                pass
            elif hasattr(accounts, 'path'):
                from .scoped_mobile_exports import account_signature
                from .language_preparation import LanguagePreparation
                signature = account_signature(accounts)
                selection = LanguagePreparation(None, None, None).selection_generation(game, account)
                account_check = lambda: (prior_check() and accounts.status()['active'] == account
                    and account_signature(accounts) == signature and selected_snapshot(root, game)[0] == source
                    and LanguagePreparation(None, None, None).selection_generation(game, account) == selection)
            else:
                account_check = lambda: prior_check() and accounts.status()['active'] == account
        if game == "hito":
            from .game_paths import discover_install
            install = discover_install("hito")
            if not install:
                raise ValueError("Configure the installed Hito folder before exporting")
            archive = install / "resources/app.asar"
            if file_digest(archive) != payload.get("archive_hash"):
                raise ValueError("Hito changed; refresh game data first")
            inputs.append(archive)
            source_check = lambda: True
        elif game == 'halflife':
            # Original GoldSrc has authored sound-free screen messages, but no
            # implemented speech/transcript binding. Do not initialize a voice
            # service (and its decoder lookup) for this text-only capability.
            from .game_assets import asset_adapter
            capabilities = payload.get('capture_capabilities', {})
            if (payload.get('format') != 2 or payload.get('game') != game
                    or capabilities.get('voiced') is not False or capabilities.get('unvoiced') is not True
                    or any(item.get('audio') for item in payload['records'])):
                raise ValueError('Prepare the confirmed unvoiced Half-Life language table before exporting.')
            adapter, _ = asset_adapter(game)
            source_check = lambda: adapter.fingerprint(Path(payload['install'])) == payload['fingerprint']
        elif game == "pragmata":
            from .pragmata_audio import PragmataVoiceAssetService
            from scripts.index_pragmata_assets import fingerprint
            service = (PragmataVoiceAssetService(directory, decoder, decode_dir, tools_dir=directory / 'tools' if source_path else data / game / 'tools')
                       if payload.get('format') == 2 else PragmataVoiceAssetService(directory, decoder, decode_dir))
            source_check = lambda: fingerprint(Path(payload["install"])) == payload["fingerprint"]
        else:
            from .local_voice import LocalVoiceAssetService
            if game == 'nte':
                from .nte_assets import ensure_extractor
                ensure_extractor(directory / 'tools' if source_path else data / game / 'tools')
            service = LocalVoiceAssetService(game, directory, decoder, decode_dir, tools_dir=directory / 'tools' if source_path else data / game / 'tools')
            source_check = lambda: service._adapter.fingerprint(Path(payload["install"])) == payload["fingerprint"]
        records = []
        for item in payload["records"]:
            # Other adapters retain their verified performance coverage gates.
            # In particular, unbound Honkai/NTE tables do not verify new scenes.
            if game == 'halflife':
                from .local_game import LocalDialogue
                validated = LocalDialogue(**item)
                if validated.voice_status != 'unvoiced' or validated.dialogue_kind != 'screen_message':
                    continue
            elif game != 'hito' and not item.get('audio'):
                continue
            text_id = str(item.get("text_id", item.get("identity", digest(item))))
            if game == "pragmata" and not text_id.startswith("pragmata:"):
                text_id = "pragmata:" + text_id
            row = {"textId": text_id, "english": display_text(item["english"]), "chinese": display_text(item["chinese"]),
                   "channels": item.get('channels') or ["dialogue", "cinematic", "gameplay"],
                   "sourceVoice": digest([payload.get("fingerprint"), item["audio"]]) if item.get("audio") else None}
            if payload.get('format') == 2:
                locale = resolve_locale(target, item['texts'])
                row.update(sourceLanguage=study_language(payload['source_locale']), sourceLocale=payload['source_locale'],
                           sourceText=item['source_text'], translationLocale=locale or target,
                           translationText=item['texts'].get(locale, '') if locale else '', audioLocale=item['audio_locale'],
                           anchorsSource=item.get('ocr_texts', {}).get(payload['source_locale'], []),
                           anchorsTranslation=item.get('ocr_texts', {}).get(locale, []))
                if item.get('member_text_ids') and ':context-' in text_id:
                    row['memberTextIds'] = item['member_text_ids']
            for old, new in (("speaker_english", "speakerEnglish"), ("speaker_chinese", "speakerChinese"),
                             ("player_voice", "playerVoice"), ("ocr_english", "anchorsEnglish"), ("ocr_chinese", "anchorsChinese")):
                if item.get(old):
                    row[new] = item[old]
            records.append(row)
    for path in inputs:
        watched[path] = (path.stat().st_size, path.stat().st_mtime_ns)

    def full_check():
        if not account_check() or any((p.stat().st_size, p.stat().st_mtime_ns) != sig for p, sig in watched.items()) or source_check() is False:
            raise ValueError("Game or catalog changed; refresh game data and retry")

    last_check = [0.0]
    def check():
        if time.monotonic() - last_check[0] >= 5:
            full_check()
            last_check[0] = time.monotonic()
    check.force = full_check

    def voice(row, number):
        if not service or not service.has_variant(row["textId"], row["english"]):
            raise ValueError("Original voice tools or exact mapping unavailable; refresh Setup")
        return decode_dir / service.extract(row["textId"], number, row["english"])

    if service and hasattr(service, 'extract_batch'):
        def batch(requests):
            if any(not service.has_variant(row['textId'], row['english']) for row, number in requests):
                raise ValueError("Original voice tools or exact mapping unavailable; refresh Setup")
            filenames = service.extract_batch([(row['textId'], number, row['english']) for row, number in requests])
            return [decode_dir / filename for filename in filenames]
        voice.batch = batch
        if game in {'cyberpunk', 'wuwa', 'nte', 'honkai3', 'witcher3'}:
            voice.batch_key = lambda row: encoded(service._entries[row['textId']]).decode('utf8')

    return records, voice, check, service


# Kept here for compatibility with the desktop runtime and existing integrations.
from .mobile_export_controls import MobileExportManager
