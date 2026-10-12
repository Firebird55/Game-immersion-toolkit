"""Private, resumable mobile exports. Never serialize original archive references."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import zipfile

from .game_paths import GAMES, GAME_NAMES
from .textmaps import TextMapIndex, display_text

FORMAT = "proxy-mobile-library-v1"
PACK_LIMIT = 512 * 1024 * 1024
CATALOG_LIMIT = 128 * 1024 * 1024
ROW_LIMIT = 200000


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
                   cancel=None, progress=lambda value: None, pack_limit=PACK_LIMIT):
    """All intermediate work is private; latest.json changes only on complete success."""
    if game not in GAMES or not 4096 <= pack_limit <= PACK_LIMIT:
        raise ValueError("Unsupported game or pack size")
    output = Path(output)
    cache = output / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    cancel = cancel or threading.Event()

    def guard():
        if cancel.is_set():
            raise ExportCancelled()
        check()

    guard()
    getattr(check, "force", check)()
    rows, clips, source_cache, identities = [], {}, {}, {}
    total_sources = len({r.get("sourceVoice") for r in records if r.get("sourceVoice")}) if include_audio else 0
    audio_bytes = 0
    for number, original in enumerate(records):
        guard()
        row = {key: original[key] for key in ("textId", "english", "chinese", "speakerEnglish", "speakerChinese",
               "playerVoice", "anchorsEnglish", "anchorsChinese", "channels", "sourceVoice") if key in original}
        source = original.get("sourceVoice")
        row["id"] = digest([game, row["textId"], row["english"], row["chinese"], row.get("playerVoice")])
        if row["id"] in identities:
            if identities[row["id"]] != source:
                raise ValueError("Conflicting original voices for one dialogue identity")
            continue
        identities[row["id"]] = source
        row["audio"] = None
        if include_audio and source:
            guard()
            cached = cache / (source + ".mp3")
            signature = cache / (source + ".json")
            valid = False
            if cached.is_file() and signature.is_file() and source not in source_cache:
                try:
                    valid = json.loads(signature.read_text())["sha256"] == file_digest(cached)
                except (OSError, ValueError, KeyError):
                    pass
            if source in source_cache:
                valid = True
            if not valid:
                if voice is None:
                    raise ValueError("Prepare original voice tools before exporting")
                produced = Path(voice(original, number))
                temporary = cached.with_suffix(".pending")
                shutil.copyfile(produced, temporary)
                temporary.replace(cached)
                signature.write_bytes(encoded({"sha256": file_digest(cached)}))
            if source not in source_cache:
                source_cache[source] = file_digest(cached)
            sha = source_cache[source]
            row["audio"] = sha
            if sha not in clips:
                audio_bytes += cached.stat().st_size
            clips[sha] = cached
        rows.append(row)
        if len(rows) > ROW_LIMIT:
            raise ValueError("Catalog exceeds the mobile row limit")
        progress({"state": "exporting", "progress": int((number+1)/max(1, len(records))*85),
                  "done": number+1, "total": len(records), "audioBytes": audio_bytes,
                  "estimatedAudioBytes": round(audio_bytes * total_sources / max(1, len(source_cache))),
                  "message": "Preparing verified dialogue and original voices"})
    if not rows:
        raise ValueError("No verified bilingual dialogue available; refresh game data first")
    guard()
    revision = digest([FORMAT, "segmented-catalog", rows])
    destination = output / revision
    staging = output / (revision + ".pending")
    staging.mkdir(exist_ok=True)
    chunks, current, size = [], [], 2048
    for sha, path in sorted(clips.items()):
        required = path.stat().st_size + 1024
        if required + 2048 > pack_limit or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("A voice clip is too large for a mobile pack")
        if current and size + required > pack_limit:
            chunks.append(current)
            current, size = [], 2048
        current.append((sha, path)); size += required
    if current:
        chunks.append(current)
    packs = []
    for pack_number, chunk in enumerate(chunks):
        guard()
        index = {sha: {"size": path.stat().st_size, "sha256": sha} for sha, path in chunk}
        pack_id = digest([game, index])
        name = f"{game}.voices-{pack_id[:16]}.zip"
        packs.append({"id": pack_id, "name": name, "clips": list(index)})
        target = staging / name
        manifest = {"format": FORMAT, "kind": "voices", "game": game, "id": pack_id, "clips": index}
        previous = next((p for p in output.glob("*/" + name) if len(p.parent.name) == 64
                         and (p.parent / (game + ".catalog.zip")).is_file()), None)
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
                "revision": revision, "languages": ["zh-Hans", "en"], "coverage": coverage,
                "catalog": catalog, "packs": packs}
    name = game + ".catalog.zip"
    write_pack(staging / name, manifest, [(item["name"], value) for item, value in zip(catalog, segments)])
    guard()
    getattr(check, "force", check)()
    if destination.exists():
        try:
            with zipfile.ZipFile(destination / name) as previous_catalog:
                valid = json.loads(previous_catalog.read("manifest.json")) == manifest and previous_catalog.testzip() is None
            for pack in packs:
                with zipfile.ZipFile(destination / pack["name"]) as previous_pack:
                    valid = valid and previous_pack.testzip() is None
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            valid = False
        if not valid:
            # Checked, same-parent private move; retain damaged files for diagnosis.
            if destination.resolve().parent != output.resolve():
                raise ValueError("Unsafe export destination")
            destination.rename(output / (revision + ".invalid-" + str(time.time_ns())))
    if not destination.exists():
        staging.replace(destination)
    else:
        # An identical revision is immutable. Leave resumable staging private.
        for path in staging.iterdir():
            path.unlink()
        staging.rmdir()
    pointer = output / "latest.pending"
    pointer.write_bytes(encoded({"revision": revision, "catalog": name, "coverage": coverage}))
    guard()
    getattr(check, "force", check)()
    os.replace(pointer, output / "latest.json")
    result = {"state": "complete", "progress": 100, "message": "Copy the catalog and voice ZIPs to On My iPhone",
              "folder": str(destination), "coverage": coverage, "bytes": sum(p.stat().st_size for p in destination.glob("*.zip"))}
    progress(result)
    return result


def prepare_source(root, game, decode_dir):
    """Adapt owned indexes and decoders without touching the user's transcript/audio history."""
    root, decode_dir = Path(root), Path(decode_dir)
    data, decoder = root / "data", root / "data/voice-assets/vgmstream/vgmstream-cli.exe"
    watched = {}
    service = None
    if game == "zzz":
        from .voice_assets import VoiceAssetService
        index = TextMapIndex(data / "textmaps")
        index.load()
        service = VoiceAssetService(data / "voice-assets/manifest.json", decoder, decode_dir,
                                   data / "voice-assets/learned-manifest.json")
        from .speakers import _voice_token, _humanize_token
        inputs = [index.file_path(name) for name in ("en_base", "en_overwrite", "zh_base", "zh_overwrite")]
        inputs += [service.manifest]
        learned = data / "voice-assets/learned-manifest.json"
        if learned.exists():
            inputs.append(learned)
        records = []
        for values in index._records_by_normalized.values():
            for item in values:
                key = service._entry_key(item.text_id, item.english)
                channels = [c for c in ("dialogue", "cinematic", "gameplay") if index._is_allowed_record(item, c)]
                if key is not None and channels:
                    audio = service._entries[key]
                    package = Path(audio["package"])
                    if (package.stat().st_size, package.stat().st_mtime_ns) != (audio["package_size"], audio["package_mtime_ns"]):
                        raise ValueError("Game changed; refresh original voices first")
                    watched[package] = (package.stat().st_size, package.stat().st_mtime_ns)
                    row = {"textId": item.text_id, "english": display_text(item.english),
                           "chinese": display_text(item.chinese), "channels": channels, "sourceVoice": digest(audio)}
                    token = _voice_token(audio.get("source", ""))
                    names = index.resolve_display_name(_humanize_token(token)) if token else None
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
        source = data / game / "textmap.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        inputs = [source]
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
        elif game == "pragmata":
            from .pragmata_audio import PragmataVoiceAssetService
            from scripts.index_pragmata_assets import fingerprint
            service = PragmataVoiceAssetService(data / game, decoder, decode_dir)
            source_check = lambda: fingerprint(Path(payload["install"])) == payload["fingerprint"]
        else:
            from .local_voice import LocalVoiceAssetService
            service = LocalVoiceAssetService(game, data / game, decoder, decode_dir)
            source_check = lambda: service._adapter.fingerprint(Path(payload["install"])) == payload["fingerprint"]
        records = []
        for item in payload["records"]:
            if game != "hito" and not item.get("audio"):
                continue
            text_id = str(item.get("text_id", item.get("identity", digest(item))))
            if game == "pragmata" and not text_id.startswith("pragmata:"):
                text_id = "pragmata:" + text_id
            row = {"textId": text_id, "english": display_text(item["english"]), "chinese": display_text(item["chinese"]),
                   "channels": ["dialogue", "cinematic", "gameplay"],
                   "sourceVoice": digest([payload.get("fingerprint"), item["audio"]]) if item.get("audio") else None}
            for old, new in (("speaker_english", "speakerEnglish"), ("speaker_chinese", "speakerChinese"),
                             ("player_voice", "playerVoice"), ("ocr_english", "anchorsEnglish"), ("ocr_chinese", "anchorsChinese")):
                if item.get(old):
                    row[new] = item[old]
            records.append(row)
    for path in inputs:
        watched[path] = (path.stat().st_size, path.stat().st_mtime_ns)

    def full_check():
        if any((p.stat().st_size, p.stat().st_mtime_ns) != sig for p, sig in watched.items()) or source_check() is False:
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

    return records, voice, check, service


# Kept here for compatibility with the desktop runtime and existing integrations.
from .mobile_export_controls import MobileExportManager
