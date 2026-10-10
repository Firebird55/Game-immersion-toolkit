import json

import pytest

from backend.textmaps import TextMapIndex


def maps(tmp_path):
    index = TextMapIndex(tmp_path)
    for name in index.urls:
        value = {"dialogue_fixture": "The old synthetic dialogue remains available." if name.startswith("en") else "旧台词"} if name.endswith("base") else {}
        index.file_path(name).write_text(json.dumps(value), encoding="utf-8")
    index.load()
    return index


def test_failed_or_invalid_update_keeps_complete_maps_on_disk_and_in_memory(tmp_path, monkeypatch):
    index = maps(tmp_path)
    before = {name: index.file_path(name).read_bytes() for name in index.urls}
    def download(url, target):
        if "Overwrite" in url:
            raise OSError("synthetic network failure")
        target.write_text('{"dialogue_fixture":"new"}', encoding="utf-8")
    monkeypatch.setattr(index, "_download", download)
    with pytest.raises(OSError):
        index.prepare(force_download=True)
    assert index.ready
    assert index.match_text("The old synthetic dialogue remains available.").chinese == "旧台词"
    assert before == {name: index.file_path(name).read_bytes() for name in index.urls}
    monkeypatch.setattr(index, "_download", lambda _url, target: target.write_text("[]", encoding="utf-8"))
    with pytest.raises(ValueError):
        index.prepare(force_download=True)
    assert before == {name: index.file_path(name).read_bytes() for name in index.urls}


def test_complete_snapshot_publishes_atomically_and_survives_restart(tmp_path, monkeypatch):
    index = maps(tmp_path)
    originals = {name: index.file_path(name).read_bytes() for name in index.urls}
    by_url = {url: name for name, url in index.urls.items()}
    def download(url, target):
        name = by_url[url]
        value = {"dialogue_fixture": "The new synthetic dialogue is now available." if name.startswith("en") else "新台词"} if name.endswith("base") else {}
        target.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(index, "_download", download)
    index.prepare(force_download=True)
    assert index.match_text("The new synthetic dialogue is now available.").chinese == "新台词"
    assert index.file_path("en_base").parent.parent.name == "snapshots"
    assert originals == {name: (tmp_path / f"{name}.json").read_bytes() for name in index.urls}
    reopened = TextMapIndex(tmp_path)
    reopened.load()
    assert reopened.match_text("The new synthetic dialogue is now available.").chinese == "新台词"


def test_snapshot_pointer_cannot_read_outside_textmap_cache(tmp_path):
    index = maps(tmp_path)
    (tmp_path / "current.json").write_text('{"snapshot":"../../private"}', encoding="utf-8")
    assert index.active_directory() == tmp_path
