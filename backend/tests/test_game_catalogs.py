"""Catalog refreshes use only synthetic data and mocked network requests."""
import json
from types import SimpleNamespace

import pytest

from backend import game_catalogs as catalogs, honkai_assets as honkai, nte_assets as nte
from backend.local_game import LocalGameTextIndex
from backend.local_game_updates import LocalGameUpdateManager
from backend.tests.test_new_game_assets import catalog, package, nte_cache


REVISION = "1" * 40
NEW_REVISION = "2" * 40


def remote(monkeypatch, data, revision=REVISION, broken=None):
    calls = []
    def download(url, limit=None):
        calls.append(url)
        if "/commits/" in url:
            return json.dumps({"sha": revision}).encode()
        assert f"/{revision}/" in url, "Every file must use the resolved immutable commit"
        name = url.rsplit("/", 1)[-1]
        if name == broken:
            raise OSError("Synthetic interrupted download")
        return json.dumps(data[name]).encode()
    monkeypatch.setattr(catalogs, "download", download)
    return calls


def test_complete_same_commit_snapshot_daily_check_and_explicit_refresh(tmp_path, monkeypatch):
    calls = remote(monkeypatch, catalog())
    first = honkai.refresh_catalog(tmp_path)
    assert first["revision"] == REVISION and not first["warning"]
    assert catalogs.read_snapshot("honkai3", tmp_path)["digest"] == first["digest"]
    assert len(calls) == 6
    calls.clear()
    assert honkai.refresh_catalog(tmp_path)["digest"] == first["digest"]
    assert calls == []
    honkai.refresh_catalog(tmp_path, force=True)
    assert len(calls) == 1  # Recheck revision; immutable cached files need no download.
    monkeypatch.setattr(catalogs.time, "time", lambda: 10 ** 12)
    calls.clear()
    honkai.refresh_catalog(tmp_path)
    assert len(calls) == 1


@pytest.mark.parametrize("broken", ["TextMap_en.json", "InLevelDialog.json"])
def test_interrupted_revision_never_mixes_languages_or_replaces_complete_snapshot(tmp_path, monkeypatch, broken):
    remote(monkeypatch, catalog())
    previous = honkai.refresh_catalog(tmp_path)
    incoming = catalog()
    incoming["TextMap_en.json"][0]["Text"] = "A changed synthetic greeting."
    remote(monkeypatch, incoming, NEW_REVISION, broken)
    result = honkai.refresh_catalog(tmp_path, force=True)
    assert result["revision"] == previous["revision"] and result["warning"]
    assert result["catalog"] == previous["catalog"]
    assert not (tmp_path / "catalog-snapshots" / NEW_REVISION).exists()


@pytest.mark.parametrize("changed", ["language", "schema", "event"])
def test_incompatible_catalog_retains_last_complete_source(tmp_path, monkeypatch, changed):
    remote(monkeypatch, catalog())
    previous = honkai.refresh_catalog(tmp_path)
    incoming = catalog()
    if changed == "language":
        incoming["TextMap_cn.json"] = []
    elif changed == "schema":
        incoming["TextMap_en.json"][0]["Hash"] = "unexpected hash format"
    else:
        incoming["DialogData.json"][0]["audioID"] = "Unverified_Effect"
    remote(monkeypatch, incoming, NEW_REVISION)
    result = honkai.refresh_catalog(tmp_path, force=True)
    assert result["warning"] and result["digest"] == previous["digest"]


def test_offline_upgrade_reuses_complete_legacy_catalog_without_download(tmp_path, monkeypatch):
    source = catalogs.SOURCES["honkai3"]
    folder = tmp_path / source.legacy_folder / source.seed
    folder.mkdir(parents=True)
    for name, rows in catalog().items():
        (folder / name).write_text(json.dumps(rows), encoding="utf8")
    calls = []
    def offline(url, **_):
        calls.append(url)
        raise OSError("Offline")
    monkeypatch.setattr(catalogs, "download", offline)
    result = honkai.refresh_catalog(tmp_path)
    assert result["revision"] == source.seed and result["warning"]
    assert len(calls) == 1 and "/commits/" in calls[0]
    assert "older content only" in catalogs.catalog_status("honkai3", result)["catalog_message"]


def test_missing_latest_source_bootstraps_one_complete_pinned_snapshot(tmp_path, monkeypatch):
    source = catalogs.SOURCES["honkai3"]
    calls = remote(monkeypatch, catalog(), source.seed)
    original = catalogs.download
    def no_latest(url, **kwargs):
        if "/commits/" in url:
            raise OSError("Rate limited")
        return original(url, **kwargs)
    monkeypatch.setattr(catalogs, "download", no_latest)
    result = honkai.refresh_catalog(tmp_path)
    assert result["revision"] == source.seed and result["warning"]
    assert len(calls) == 5


def test_cached_catalog_integrity_and_pointer_paths_are_verified(tmp_path, monkeypatch):
    remote(monkeypatch, catalog())
    honkai.refresh_catalog(tmp_path)
    root = tmp_path / "catalog-snapshots"
    (root / REVISION / "TextMap_en.json").write_text("[]")
    assert catalogs.read_snapshot("honkai3", tmp_path) is None
    (root / "current.json").write_text(json.dumps({"revision": "../escape", "digest": "bad"}))
    assert catalogs.read_snapshot("honkai3", tmp_path) is None


def test_only_fixed_source_data_paths_can_be_downloaded(tmp_path, monkeypatch):
    remote(monkeypatch, catalog())
    honkai.refresh_catalog(tmp_path)
    original = catalogs.download
    calls = []
    def malicious_metadata(url, **kwargs):
        calls.append(url)
        if "/commits/" in url:
            return json.dumps({"sha": "../../outside", "url": "http://localhost/private"}).encode()
        return original(url, **kwargs)
    monkeypatch.setattr(catalogs, "download", malicious_metadata)
    result = honkai.refresh_catalog(tmp_path, force=True)
    assert result["warning"] and len(calls) == 1
    assert all(url.startswith("https://api.github.com/repos/nairieberry/HonkaiImpactData/") for url in calls)


def test_same_game_files_new_catalog_rebuilds_and_keeps_exact_original_voice_contract(tmp_path, monkeypatch):
    import backend.local_game_updates as updates
    install, cache = tmp_path / "game", tmp_path / "cache"
    package(install / "BH3_Data/StreamingAssets/Audio/AUDIO_Default.pck")
    remote(monkeypatch, catalog())
    monkeypatch.setattr(updates, "discover_install", lambda _: install)
    manager = LocalGameUpdateManager("honkai3", LocalGameTextIndex("honkai3", cache), SimpleNamespace(reload=lambda: None))
    manager._run()
    assert manager.status()["state"] == "idle"
    old = json.loads(manager.index.path.read_bytes())
    incoming = catalog()
    incoming["TextMap_en.json"][0]["Text"] = "A new synthetic edition."
    incoming["TextMap_cn.json"][0]["Text"] = "新测试版本。"
    remote(monkeypatch, incoming, NEW_REVISION)
    manager._force_catalog = True
    manager._run()
    new = json.loads(manager.index.path.read_bytes())
    assert old["fingerprint"] == new["fingerprint"] and old["catalog_digest"] != new["catalog_digest"]
    assert new["catalog_revision"] == NEW_REVISION
    assert new["records"][0]["audio"] == old["records"][0]["audio"]
    assert manager.index.match_lines(["A new synthetic edition."], exact_only=True)
    assert not manager.index.match_lines(["A synthetic greeting."], exact_only=True)
    # A structurally valid catalog with no matching installed event must not
    # replace the previous playable index or claim expanded support.
    incoming["DialogData.json"][0]["audioID"] = "VO_Synthetic_Absent"
    remote(monkeypatch, incoming, "3" * 40)
    manager._force_catalog = True
    manager._run()
    assert manager.status()["state"] == "retrying"
    assert json.loads(manager.index.path.read_bytes()) == new


def test_unrelated_game_does_not_contact_catalog_sources(tmp_path, monkeypatch):
    import backend.local_game_updates as updates
    import backend.cyberpunk_assets as adapter
    monkeypatch.setattr(updates, "discover_install", lambda _: tmp_path)
    monkeypatch.setattr(catalogs, "download", lambda *_: pytest.fail("Unselected catalog download"))
    monkeypatch.setattr(adapter, "fingerprint", lambda _: "current")
    monkeypatch.setattr(adapter, "index_install", lambda *_: {"format": 1, "install": str(tmp_path),
        "fingerprint": "current", "records": [{"text_id": "cyberpunk:synthetic", "english": "Synthetic line.",
            "chinese": "测试台词。", "audio": {"depot": "synthetic.wem"}}]})
    manager = LocalGameUpdateManager("cyberpunk", LocalGameTextIndex("cyberpunk", tmp_path), SimpleNamespace(reload=lambda: None))
    manager._run()
    assert manager.status()["state"] == "idle"


def nte_catalog(event="Synthetic"):
    row = {"StringTableID": "Sequence", "Path": {"FilePath": "../../../Projects/HT/Content/Movies/FFMpeg/Story/Synthetic.mp4"},
           "PlayVoice": {"AssetPathName": f"/Game/WwiseAudio/Events/CG/Guide/Play_Vo_CG_{event}.Play_Vo_CG_{event}"}}
    return {name.rsplit("/", 1)[-1]: [{"Type": "DataTable", "Rows": {"Synthetic": row}}]
            for name in catalogs.SOURCES["nte"].files}


def test_new_movie_catalog_reextracts_nte_events_with_unchanged_game_files(tmp_path, monkeypatch):
    remote(monkeypatch, nte_catalog())
    nte.refresh_catalog(tmp_path)
    monkeypatch.setattr(nte, "fingerprint", lambda _: "unchanged-game-files")
    monkeypatch.setattr(nte, "ensure_extractor", lambda _: tmp_path / "synthetic-reader")
    calls = []
    def reader(_install, _executable, destination, _mode, **kwargs):
        calls.append(kwargs["cinema_events"])
        nte_cache(destination)
        (destination / "cinema-subtitles.json").write_text("{}")
    monkeypatch.setattr(nte, "run_reader", reader)
    first = nte.index_install(tmp_path / "game", tmp_path)
    assert len(calls) == 1
    assert nte.index_install(tmp_path / "game", tmp_path) == first
    assert len(calls) == 1
    remote(monkeypatch, nte_catalog("NewSynthetic"), NEW_REVISION)
    nte.refresh_catalog(tmp_path, force=True)
    second = nte.index_install(tmp_path / "game", tmp_path)
    assert len(calls) == 2 and calls[0] != calls[1]
    assert first["fingerprint"] == second["fingerprint"]
    assert first["catalog_digest"] != second["catalog_digest"]


def test_oversized_catalog_is_rejected_before_replacing_working_snapshot(tmp_path, monkeypatch):
    remote(monkeypatch, catalog())
    previous = honkai.refresh_catalog(tmp_path)
    monkeypatch.setattr(catalogs, "FILE_LIMIT", 200)
    remote(monkeypatch, {name: [{"oversized": "x" * 400}] for name in catalog()}, NEW_REVISION)
    # The stored synthetic snapshot is smaller than the lowered per-file limit.
    result = honkai.refresh_catalog(tmp_path, force=True)
    assert result["warning"] and result["digest"] == previous["digest"]
