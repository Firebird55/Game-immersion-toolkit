"""Read-only Cyberpunk extraction using a pinned, checksum-verified WolvenKit CLI."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from .textmaps import display_text

WOLVENKIT_VERSION = "9.0.1"
WOLVENKIT_SHA256 = "364427384c0f4ebb6b157fa9abd01595258af1b7993c7b3a7edd2920f2016e92"
WOLVENKIT_URL = f"https://github.com/WolvenKit/WolvenKit/releases/download/{WOLVENKIT_VERSION}/WolvenKit.Console-{WOLVENKIT_VERSION}.zip"


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
                       ("lang_en_text.archive", "lang_zh-cn_text.archive", "lang_zh-cn_voice.archive")
                       if (directory / (prefix + name)).is_file())
    return sources


def fingerprint(install: Path) -> str:
    return "|".join(f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
                    for p in archive_sources(install))


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
        if not zh:
            continue
        vo = voices.get(string_id, {})
        alternatives = []
        for variant in ("female", "male"):
            en_text = display_text(en.get(f"{variant}Variant") or en.get("femaleVariant", ""))
            zh_text = display_text(zh.get(f"{variant}Variant") or zh.get("femaleVariant", ""))
            depot = resource_path(vo, variant)
            if not en_text or not zh_text or en_text.startswith("[db_"):
                continue
            audio = {"archive": vo["archive"], "depot": depot} if depot else None
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
                    voices[string_id] = {**entry, "archive": archive.relative_to(install).as_posix()}
                elif "lang_en_" in archive.name:
                    english[string_id] = entry
                else:
                    chinese[string_id] = entry
    if fingerprint(install) != source_fingerprint:
        raise ValueError("Cyberpunk files changed while indexing; retry after Steam finishes updating")
    records = build_records(english, chinese, voices)
    if not records:
        raise ValueError("No official bilingual Cyberpunk subtitles could be extracted")
    mapped = sum(bool(r["audio"]) for r in records)
    return {"format": 1, "install": str(install), "fingerprint": source_fingerprint, "records": records,
            "message": (f"{len(records):,} bilingual pairs; {mapped:,} Mandarin voices" if mapped else
                        "Chinese subtitles indexed; install the official Mandarin voice pack in Steam")}


def extract_voice(install: Path, audio: dict, executable: Path, destination: Path) -> bytes:
    archive = (install / audio["archive"]).resolve()
    if not archive.is_relative_to(install.resolve()) or not archive.is_file():
        raise ValueError("Original voice archive is unavailable")
    depot = audio["depot"]
    if not depot.casefold().endswith(".wem") or ".." in depot or ":" in depot:
        raise ValueError("Invalid original voice resource")
    run_wolvenkit(executable, "unbundle", archive, "-o", destination,
                  "-r", "^" + re.escape(depot) + "$", "-v", "quiet")
    path = destination / depot.replace("\\", "/")
    if not path.is_file():
        raise FileNotFoundError("Mandarin voice was not found in the installed archive")
    return path.read_bytes()
