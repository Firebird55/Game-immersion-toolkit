"""Refresh data-only catalogs without downloading or executing reader updates.

Every snapshot uses one immutable commit from a fixed source. Catalog data is
private runtime data; neither game text nor downloaded catalogs are distributed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

from .game_tools import download, _atomic_file

CHECK_INTERVAL = 24 * 60 * 60
FILE_LIMIT = 64 * 1024 * 1024
TOTAL_LIMIT = 192 * 1024 * 1024


@dataclass(frozen=True)
class CatalogSource:
    repository: str
    branch: str
    seed: str
    files: tuple[str, ...]
    legacy_folder: str


SOURCES = {
    "honkai3": CatalogSource("nairieberry/HonkaiImpactData", "master",
        "01d7afbaf99ff7d3d027e27fe9a4b363a2db7cc1",
        ("Global/ExcelOutputAsset/Decrypted/TextMap_cn.json",
         "Global/ExcelOutputAsset/Decrypted/TextMap_en.json",
         "Global/ExcelOutputAsset/DialogData.json",
         "Global/ExcelOutputAsset/StageDialogData.json",
         "Global/ExcelOutputAsset/InLevelDialog.json"), "catalog"),
    "nte": CatalogSource("Waifus-Grace/NTE_Assets", "main",
        "cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7",
        ("DataTable/Skill/DT_MediaFFmpegInfo.json",
         "DataTable/Skill/DT_MediaFFmpegInfo_Quest.json"), "movie-catalog"),
}


def _revision(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Unsupported catalog revision")
    return value


def _parse(payloads):
    if sum(map(len, payloads.values())) > TOTAL_LIMIT or any(len(v) > FILE_LIMIT for v in payloads.values()):
        raise ValueError("Catalog exceeds its size limit")
    return {name: json.loads(data) for name, data in payloads.items()}


def _digests(payloads):
    files = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return files, digest


def _payloads(source, revision, legacy=None):
    payloads, total = {}, 0
    for relative in source.files:
        name = Path(relative).name
        limit = min(FILE_LIMIT, TOTAL_LIMIT - total)
        if legacy is None:
            data = download(f"https://raw.githubusercontent.com/{source.repository}/{revision}/{relative}", limit=limit)
        else:
            with (legacy / name).open("rb") as stream:
                data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Catalog exceeds its size limit")
        total += len(data)
        payloads[name] = data
    return payloads


def read_snapshot(game: str, data_dir: Path) -> dict | None:
    """Verify cached bytes against the receipt before using a complete snapshot."""
    source, root = SOURCES[game], data_dir / "catalog-snapshots"
    try:
        pointer = json.loads((root / "current.json").read_bytes())
        revision = _revision(pointer["revision"])
        folder = root / revision
        receipt = json.loads((folder / "receipt.json").read_bytes())
        if receipt["repository"] != source.repository or receipt["revision"] != revision:
            raise ValueError("Catalog receipt source differs")
        payloads = {}
        for relative in source.files:
            name = Path(relative).name
            with (folder / name).open("rb") as stream:
                payloads[name] = stream.read(FILE_LIMIT + 1)
        files, digest = _digests(payloads)
        if files != receipt["files"] or digest != pointer["digest"]:
            raise ValueError("Catalog cache checksum differs")
        return {"revision": revision, "digest": digest, "catalog": _parse(payloads)}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _store(game, data_dir, revision, payloads, validate):
    source, root = SOURCES[game], data_dir / "catalog-snapshots"
    revision = _revision(revision)
    catalog = _parse(payloads)
    validate(catalog)  # Complete schema and bilingual/event links, before publication.
    files, digest = _digests(payloads)
    receipt = {"repository": source.repository, "revision": revision, "files": files}
    root.mkdir(parents=True, exist_ok=True)
    folder = root / revision
    # A receipt is written last; the active pointer is the only publication step.
    with tempfile.TemporaryDirectory(prefix="catalog-", dir=root) as temporary:
        staging = Path(temporary)
        for name, data in payloads.items():
            (staging / name).write_bytes(data)
        (staging / "receipt.json").write_text(json.dumps(receipt), encoding="utf8")
        folder.mkdir(exist_ok=True)
        for name in [*payloads, "receipt.json"]:
            (staging / name).replace(folder / name)
    _atomic_file(root / "current.json", json.dumps({"revision": revision, "digest": digest}).encode())
    return {"revision": revision, "digest": digest, "catalog": catalog}


def refresh_catalog(game: str, data_dir: Path, validate, force=False) -> dict:
    """Check daily, on a game change, or on explicit Refresh game data.

    Invalid/unavailable updates retain the last validated complete catalog. A
    newly staged catalog never replaces textmap.json; the normal updater still
    verifies installed voices and atomically publishes that separate index.
    """
    source, root = SOURCES[game], data_dir / "catalog-snapshots"
    previous = read_snapshot(game, data_dir)
    checked = {}
    try:
        checked = json.loads((root / "check.json").read_bytes())
    except (OSError, ValueError):
        pass
    if not isinstance(checked, dict) or type(checked.get("checked_at", 0)) not in (int, float):
        checked = {}
    now = time.time()
    if previous and not force and 0 <= now - checked.get("checked_at", 0) < CHECK_INTERVAL:
        return {**previous, "warning": bool(checked.get("warning"))}
    try:
        metadata = json.loads(download(f"https://api.github.com/repos/{source.repository}/commits/{source.branch}", limit=1024 * 1024))
        revision = _revision(metadata["sha"])
        if previous and previous["revision"] == revision:
            validate(previous["catalog"])
            snapshot = previous
        else:
            payloads = _payloads(source, revision)
            snapshot = _store(game, data_dir, revision, payloads, validate)
        warning = False
    except Exception:
        # Never surface upstream JSON, URLs, local paths or raw network errors.
        warning = True
        snapshot = previous
        if snapshot is None:
            legacy = data_dir / source.legacy_folder / source.seed
            try:
                payloads = _payloads(source, source.seed, legacy)
                snapshot = _store(game, data_dir, source.seed, payloads, validate)
            except (OSError, ValueError, KeyError, TypeError):
                payloads = _payloads(source, source.seed)
                snapshot = _store(game, data_dir, source.seed, payloads, validate)
        validate(snapshot["catalog"])
    _atomic_file(root / "check.json", json.dumps({"checked_at": now, "warning": warning}).encode())
    return {**snapshot, "warning": warning}


def catalog_status(game: str, snapshot: dict) -> dict:
    seed = snapshot["revision"] == SOURCES[game].seed
    message = ("Honkai catalog 4.7: older content only; newer chapters are unavailable."
        if game == "honkai3" and seed else
        f"{'Honkai bilingual' if game == 'honkai3' else 'NTE movie'} catalog {snapshot['revision'][:8]}; compatible catalog updates need no toolkit release.")
    if snapshot.get("warning"):
        message += " Catalog update unavailable or incompatible; using the last complete catalog."
    return {"catalog_message": message, "catalog_warning": bool(snapshot.get("warning"))}
