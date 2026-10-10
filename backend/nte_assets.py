"""Read NTE localization and exact Chinese Wwise event/source references.

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


def run_reader(install: Path, executable: Path, destination: Path, mode: str, depot: str | None = None, cinema_events: list[str] | None = None) -> None:
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
    if depot is not None:
        request["depot"] = depot
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


def build_records(cache: Path, cinema_bindings: list[dict] | None = None) -> list[dict]:
    localization = json.loads((cache / "localization.json").read_text(encoding="utf-8"))
    english = {(r["ns"], r["key"]): display_text(r["value"]) for r in localization["en"]}
    chinese = {(r["ns"], r["key"]): display_text(r["value"]) for r in localization["zh-CN"]}
    media = set(json.loads((cache / "media.json").read_text(encoding="utf-8")))
    events = {}
    cinema_events = {}
    for path in (cache / "banks").glob("Play_Vo_*.bnk"):
        data = path.read_bytes()
        if len(data) < 20 or data[:4] != b"BKHD" or struct.unpack_from("<I", data, 16)[0] != wwise_hash("Chinese"):
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
            depot = f"{MEDIA_ROOT}{layer['media_id']}.wem"
            if depot not in media:
                continue
            audio = {"depot": depot, "event": event}
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
        if en and contains_han(zh) and audio and len(pairs_by_key[key.lower()]) == 1:
            records.append({"text_id": f"nte:{ns}:{key}", "english": en, "chinese": zh, "audio": audio})
    if cinema_bindings:
        from .nte_cinematics import movie_records
        subtitles = json.loads((cache / 'cinema-subtitles.json').read_text(encoding='utf8'))
        existing = {r['text_id'] for r in records}
        records.extend(r for r in movie_records(cinema_bindings, subtitles, english, chinese, cinema_events) if r['text_id'] not in existing)
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


def extract_voice(install: Path, audio: dict, executable: Path, destination: Path) -> bytes:
    if not re.fullmatch(re.escape(MEDIA_ROOT) + r"\d+\.wem", audio.get("depot", "")):
        raise ValueError("Invalid NTE Mandarin source reference")
    run_reader(install, executable, destination, "voice", audio["depot"])
    data = (destination / "voice.wem").read_bytes()
    if data[:4] != b"RIFF":
        raise ValueError("NTE voice is not a supported original WEM")
    return data
