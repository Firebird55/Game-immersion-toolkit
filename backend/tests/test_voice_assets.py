import json
import struct
from pathlib import Path

import pytest

from backend.voice_assets import AudioSourceChoice, VoiceAssetService, VoiceEntry, read_external_table, resolve_links, voice_hash


def package(tmp_path, *, offset=64):
    path = tmp_path / "voice.pck"
    # 28-byte fixed header + 28-byte external table, payload at 64.
    path.write_bytes(b"AKPK" + struct.pack("<6I", 48, 1, 0, 0, 0, 28)
                     + struct.pack("<IQ4I", 1, 123, 1, 12, offset, 0)
                     + b"\0" * 8 + b"RIFF\x04\0\0\0WAVE")
    return path


def test_reads_only_exact_external_entry(tmp_path):
    entries = read_external_table(package(tmp_path))
    assert len(entries) == 1
    assert entries[0].file_id == 123
    assert entries[0].read() == b"RIFF\x04\0\0\0WAVE"


def test_rejects_out_of_bounds_entry(tmp_path):
    with pytest.raises(ValueError):
        read_external_table(package(tmp_path, offset=999))


def test_known_nanson_hash():
    path = "chinese(prc)/ex/VO_Galgame/Ver3_1/VO_Nanson/GalGame_ZenkovS1_Nanson_100100007_001.wem"
    assert voice_hash(path) == 0xC115AA5DA661096E
    assert voice_hash(path.upper()) == voice_hash(path)


def test_exact_link_and_ambiguous_prefixes(tmp_path):
    leaf = "GalGame_Test_Nanson_001"
    prefixes = ["VO_Galgame/Ver3_1/VO_Nanson/", "VO_Galgame/Ver2_5/VO_Nanson/"]
    hashes = [voice_hash(f"chinese(prc)/ex/{p}{leaf}.wem") for p in prefixes]
    entries = {h: VoiceEntry(tmp_path / "a.pck", 64, 12, h) for h in hashes}
    links = [{"source": leaf, "text_id": "exact-id"}]
    assert resolve_links(links, prefixes, entries) == {}
    del entries[hashes[1]]
    assert list(resolve_links(links, prefixes, entries)) == ["exact-id"]


@pytest.mark.parametrize("recording_first", [True, False])
def test_original_wins_without_late_recording_deletion(recording_first):
    published, discarded, cancelled = [], [], []
    choice = AudioSourceChoice(lambda *v: published.append(v), discarded.append, cancelled.append)
    if recording_first:
        choice.recording_result(1, "1.mp3", True)
        assert not published
    choice.original_result(1, "official-1.mp3", True)
    if not recording_first:
        choice.recording_result(1, "1.mp3", True)
    assert published == [(1, "official-1.mp3", True)]
    assert discarded == ["1.mp3"]
    assert cancelled == [1]


@pytest.mark.parametrize("recording_first", [True, False])
def test_asset_failure_keeps_recording_fallback(recording_first):
    published = []
    choice = AudioSourceChoice(lambda *v: published.append(v), lambda _: None, lambda _: None)
    if recording_first:
        choice.recording_result(1, "1.mp3", True)
    choice.original_result(1, None, False)
    if not recording_first:
        choice.recording_result(1, "1.mp3", True)
    assert published == [(1, "1.mp3", True)]


def test_package_update_rejected_before_decode(tmp_path):
    manifest = tmp_path / "manifest.json"
    path = package(tmp_path)
    manifest.write_text(json.dumps({"version": 1, "entries": {"id": {
        "package": str(path), "package_size": 1, "package_mtime_ns": 0,
    }}}))
    service = VoiceAssetService(manifest, tmp_path / "decoder.exe", tmp_path / "out")
    try:
        with pytest.raises(ValueError, match="changed"):
            service.extract("id", 1)
    finally:
        service.close()
