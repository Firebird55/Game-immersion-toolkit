import json
from pathlib import Path
import threading
import zipfile

import pytest

from backend.mobile_library import export_library, digest, ExportCancelled, FORMAT


def rows(game="zzz"):
    return [{"textId": game+":dialogue1", "english": "The lantern is bright.", "chinese": "灯笼很亮。",
             "sourceVoice": digest("voice1"), "channels": ["dialogue"],
             "anchorsEnglish": ["The lantern"], "playerVoice": "female", "speakerEnglish": "Guide"},
            {"textId": game+":dialogue2", "english": "We can keep walking.", "chinese": "我们可以继续走。",
             "sourceVoice": digest("voice1"), "channels": ["dialogue"], "install": "private-path", "api_key": "private-key"}]


def voice(tmp_path, calls):
    def decode(row, number):
        calls.append(row["textId"])
        target = tmp_path / "decoded.mp3"
        target.write_bytes(b"ID3" + bytes(512))
        return target
    return decode


@pytest.mark.parametrize("game", ["zzz", "pragmata", "cyberpunk", "wuwa", "witcher3", "nte", "honkai3", "hito"])
def test_export_roundtrip_and_private_allowlist(tmp_path, game):
    calls = []
    output = tmp_path / "export"
    result = export_library(game, rows(game), output, voice=voice(tmp_path, calls))
    folder = Path(result["folder"])
    with zipfile.ZipFile(folder / (game+".catalog.zip")) as pack:
        manifest = json.loads(pack.read("manifest.json"))
        catalog = [json.loads(line) for line in pack.read("catalog.ndjson").splitlines()]
        assert manifest["format"] == FORMAT
        assert manifest["coverage"]["exportedVoices"] == 2
        assert "install" not in catalog[1] and "api_key" not in catalog[1]
        assert catalog[0]["anchorsEnglish"] == ["The lantern"]
        assert catalog[0]["audio"] == catalog[1]["audio"]
        assert all(info.compress_type == zipfile.ZIP_STORED for info in pack.infolist())
    assert len(calls) == 1
    assert len(list(folder.glob("*.zip"))) == 2
    export_library(game, rows(game), output, voice=voice(tmp_path, calls))
    assert len(calls) == 1


def test_catalog_only_never_decodes(tmp_path):
    result = export_library("zzz", rows(), tmp_path, include_audio=False)
    assert result["coverage"]["exportedVoices"] == 0
    assert len(list(Path(result["folder"]).glob("*.zip"))) == 1


def test_cancel_preserves_complete_export_and_resumes(tmp_path):
    calls = []
    good = export_library("zzz", rows(), tmp_path / "out", voice=voice(tmp_path, calls))
    before = (tmp_path / "out/latest.json").read_bytes()
    cancel = threading.Event()
    def progress(_):
        cancel.set()
    with pytest.raises(ExportCancelled):
        export_library("zzz", rows()+rows("wuwa"), tmp_path / "out", voice=voice(tmp_path, calls), cancel=cancel, progress=progress)
    assert (tmp_path / "out/latest.json").read_bytes() == before
    assert Path(good["folder"]).is_dir()


def test_source_change_prevents_publication(tmp_path):
    checks = []
    def check():
        checks.append(1)
        if len(checks) > 3:
            raise ValueError("changed")
    with pytest.raises(ValueError, match="changed"):
        export_library("zzz", rows(), tmp_path, include_audio=False, check=check)
    assert not (tmp_path / "latest.json").exists()


def test_corrupt_decoded_cache_is_rebuilt(tmp_path):
    calls = []
    export_library("zzz", rows(), tmp_path / "out", voice=voice(tmp_path, calls))
    next((tmp_path / "out/cache").glob("*.mp3")).write_bytes(b"corrupt" * 100)
    export_library("zzz", rows(), tmp_path / "out", voice=voice(tmp_path, calls))
    assert len(calls) == 2


def test_changed_catalog_reuses_same_voice_pack(tmp_path):
    calls = []
    first = export_library("zzz", rows(), tmp_path / "out", voice=voice(tmp_path, calls))
    newer = rows(); newer[0]["english"] = "The lantern shines brightly."
    second = export_library("zzz", newer, tmp_path / "out", voice=voice(tmp_path, calls))
    assert first["folder"] != second["folder"]
    a = next(Path(first["folder"]).glob("*voices*.zip"))
    b = next(Path(second["folder"]).glob("*voices*.zip"))
    assert a.name == b.name and a.read_bytes() == b.read_bytes()


def test_oversized_clip_rejected_before_complete_pointer(tmp_path):
    def large(_row, _number):
        path = tmp_path / "huge.mp3"; path.write_bytes(bytes(6000)); return path
    with pytest.raises(ValueError, match="too large"):
        export_library("zzz", rows(), tmp_path / "out", voice=large, pack_limit=4096)
    assert not (tmp_path / "out/latest.json").exists()
