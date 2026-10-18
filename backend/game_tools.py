"""Separately download verified tools; all outputs stay in ignored local caches."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

VGM_URL = "https://github.com/vgmstream/vgmstream/releases/download/r2117/vgmstream-win64.zip"
VGM_SHA = "6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c"
REE_URL = "https://github.com/Ekey/REE.PAK.Tool/releases/download/Latest/REE.Unpacker-x86.zip"
REE_SHA = "caa20e3ad94a4e9f09d2a53b7aceaa4ca0dc6bdba403904da6b43ceffb510884"
READER_REVISION = "bb2b9790d2d45a5c662c36cd9f046d05893d0ef4"
READER_BASE = f"https://raw.githubusercontent.com/simon300000/zenless-voice/{READER_REVISION}/"
READER_SHA = "176491a567b6152f5031b71ea7d742dba3228462d404a6abf03c2242c6ca2731"
METADATA_BASE = "https://git.mero.moe/dimbreath/ZenlessData/raw/branch/master/"
METADATA_FILES = {"PerformTemplateTb.json": "FileCfg/PerformTemplateTb.json",
                  "OngoingTipsConfigTemplateTb.json": "FileCfg/OngoingTipsConfigTemplateTb.json",
                  "AudioResourceData.json": "Data/JsonBytes/Audio/AudioResourceData.json",
                  "VoiceData.json": "Data/_unsorted/VoiceData.json"}


def download(url: str, limit: int = 64 * 1024 * 1024) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "GameImmersionToolkit/1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Tool download exceeds its size limit")
    return data


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_bytes(data)
    temporary.replace(path)


def install_archive(url: str, digest: str, directory: Path, required: tuple[str, ...]) -> None:
    marker = directory / "verified-download.json"
    try:
        receipt = json.loads(marker.read_text(encoding="utf-8"))
        if receipt["archive_sha256"] == digest and receipt["files"] and all(
            (directory / name).is_file() and _digest((directory / name).read_bytes()) == sha
            for name, sha in receipt["files"].items()
        ) and all((directory / name).is_file() for name in required):
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass
    data = download(url)
    if _digest(data) != digest:
        raise ValueError("Tool download checksum mismatch; no files were installed")
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total = 0
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or ":" in entry.filename:
                raise ValueError("Unsafe tool archive path")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Tool archive links are not allowed")
            total += entry.file_size
            if total > 256 * 1024 * 1024:
                raise ValueError("Tool archive expands beyond its size limit")
            if not entry.is_dir():
                files[entry.filename] = archive.read(entry)
    if any(name not in files for name in required):
        raise ValueError("Tool archive is missing required files")
    directory.mkdir(parents=True, exist_ok=True)
    # Validate the whole archive before touching an existing working tool.
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix="tool-download-") as staged:
        staging = Path(staged)
        if any(not (directory / name).resolve().is_relative_to(directory.resolve()) for name in files):
            raise ValueError("Tool destination escapes its cache")
        for name, content in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        for name in files:
            target = directory / name
            if target.is_file() and target.read_bytes() == files[name]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            (staging / name).replace(target)
    _atomic_file(marker, json.dumps({"url": url, "archive_sha256": digest,
                                  "files": {name: _digest(content) for name, content in files.items()}}).encode())


def refresh_zzz_metadata(root: Path, *, revision=None) -> tuple[str, bool]:
    directory = root / "work/voice-assets"
    base = METADATA_BASE.replace('/branch/master/', '/commit/' + revision + '/') if revision else METADATA_BASE
    payloads = {name: download(base + source) for name, source in METADATA_FILES.items()}
    for name, data in payloads.items():
        value = json.loads(data)
        if not isinstance(value, dict) or not value:
            raise ValueError("Game metadata is empty or has an unsupported format")
        if name == "VoiceData.json" and not isinstance(value.get("allPrefixes"), list):
            raise ValueError("Game voice metadata is incomplete")
    changed = any(not (directory / name).is_file() or (directory / name).read_bytes() != data
                  for name, data in payloads.items())
    # Download and validate every source before replacing any cached metadata.
    for name, data in payloads.items():
        if not (directory / name).is_file() or (directory / name).read_bytes() != data:
            _atomic_file(directory / name, data)
    digest = _digest(b"".join(payloads[name] for name in sorted(payloads)))
    return digest, changed


def missing_tools(root: Path, game: str) -> list[str]:
    if game in {"hito", "beyond", "heavyrain"}:
        return []
    required = [("Voice decoder", root / "data/voice-assets/vgmstream/vgmstream-cli.exe")]
    if game == "zzz":
        required += [("ZZZ scene reader", root / "work/voice-assets/galgame-perform.ts")]
        required += [(name, root / "work/voice-assets" / name) for name in METADATA_FILES]
        required += [(name, root / "node_modules" / name / "package.json") for name in ("ooz-wasm", "xxhash-wasm")]
    if game == "pragmata":
        required += [("PRAGMATA extractor", root / "data/pragmata/tools/REE.Unpacker.exe")]
    if game == "cyberpunk":
        required += [("Cyberpunk extractor", root / "data/cyberpunk/tools/WolvenKit.CLI.exe")]
    if game == "wuwa":
        required += [("Wuthering Waves extractor", root / "data/wuwa/tools/FModelCLI.exe"),
                     ("Wuthering Waves decompression", root / "data/wuwa/tools/.data/oodle-data-shared.dll"),
                     ("Wuthering Waves decompression", root / "data/wuwa/tools/.data/zlib-ng2.dll")]
    if game == "nte":
        from .nte_assets import dotnet_sdk
        if dotnet_sdk() is None:
            required.append((".NET 10 SDK", root / "data/nte/tools/missing-sdk"))
        required += [("NTE reader", root / "data/nte/tools/NteReader.dll"),
                     ("NTE archive reader", root / "data/nte/tools/upstream/UEExtractor.dll"),
                     ("NTE decompression", root / "data/nte/tools/upstream/oodle-data-shared.dll"),
                     ("NTE decompression", root / "data/nte/tools/upstream/zlib-ng2.dll")]
    return list(dict.fromkeys(name for name, path in required if not path.is_file()))


def prepare_tools(root: Path, game: str, progress=lambda _message: None) -> None:
    from .game_paths import GAMES
    if game not in GAMES:
        raise ValueError("Unsupported game")
    if game in {"hito", "beyond", "heavyrain"}:
        return
    decoder = root / "data/voice-assets/vgmstream"
    progress("Preparing the verified original-voice decoder")
    install_archive(VGM_URL, VGM_SHA, decoder, ("vgmstream-cli.exe", "COPYING"))
    if game == "zzz":
        directory = root / "work/voice-assets"
        progress("Preparing the ZZZ scene reader and metadata")
        source = download(READER_BASE + "galgame-perform.ts")
        if _digest(source) != READER_SHA:
            raise ValueError("ZZZ reader checksum mismatch")
        license_text = download(READER_BASE + "LICENSE")
        if not license_text.startswith(b"MIT License"):
            raise ValueError("ZZZ reader license notice is unavailable")
        _atomic_file(directory / "galgame-perform.ts", source)
        _atomic_file(directory / "ZENLESS-VOICE-LICENSE.txt", license_text)
        shutil.copytree(decoder, directory / "vgmstream", dirs_exist_ok=True)
        refresh_zzz_metadata(root)
    elif game == "pragmata":
        progress("Preparing the separately downloaded PRAGMATA extractor")
        install_archive(REE_URL, REE_SHA, root / "data/pragmata/tools", ("REE.Unpacker.exe",))
    elif game == "cyberpunk":
        from .cyberpunk_assets import ensure_wolvenkit
        progress("Preparing the verified Cyberpunk extractor")
        ensure_wolvenkit(root / "data/cyberpunk/tools")
    elif game == "wuwa":
        from .wuthering_assets import ensure_extractor
        progress("Preparing the verified Wuthering Waves extractor")
        ensure_extractor(root / "data/wuwa/tools", decoder / "vgmstream-cli.exe")
    elif game == "nte":
        from .nte_assets import ensure_extractor
        progress("Preparing the verified NTE archive reader and local .NET bridge")
        ensure_extractor(root / "data/nte/tools")
