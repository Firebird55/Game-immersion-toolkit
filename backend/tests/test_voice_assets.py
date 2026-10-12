import json
import struct
from pathlib import Path

import pytest

from backend.voice_assets import (
    AudioSourceChoice, VoiceAssetService, VoiceEntry, merge_valid_manifest_entries,
    read_external_table, resolve_links, voice_hash, voice_manifest_key,
)


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


def test_new_chapter_resolves_standard_voice_path_without_updated_prefix_metadata(tmp_path):
    source = "GalGame_Chapter999_Belle_010_001"
    path = f"chinese(prc)/ex/VO_Galgame/Ver4_2/VO_Belle/{source}.wem"
    hashed = voice_hash(path)
    entries = {hashed: VoiceEntry(tmp_path / "future.pck", 64, 12, hashed)}
    resolved = resolve_links([{"source": source, "text_id": "future-id"}], [], entries)
    assert resolved["future-id"]["file_id"] == f"{hashed:016x}"


def test_ongoing_voice_uses_any_speaker_prefix_and_keeps_text_variant(tmp_path):
    source = "OngoingLevel_ZenkovS1_Wise_123101026_001"
    prefix = "VO_Ongoing/Ver3_1/VO_Wise/"
    path = f"chinese(prc)/ex/{prefix}{source}.wem"
    hashed = voice_hash(path)
    english = "(Looks like Nanson has something to report. Better go check.)"
    entries = {hashed: VoiceEntry(tmp_path / "future.pck", 64, 12, hashed)}
    resolved = resolve_links(
        [{"source": source, "text_id": "Side_OngoingLevel_Test", "english": english}],
        [prefix],
        entries,
    )
    key = voice_manifest_key("Side_OngoingLevel_Test", english)
    assert resolved[key]["source"] == path


def test_future_ongoing_speaker_resolves_without_new_prefix_metadata(tmp_path):
    source = "OngoingLevel_FutureStory_NewAgent_100_001"
    path = f"chinese(prc)/ex/VO_Ongoing/Ver4_2/VO_NewAgent/{source}.wem"
    hashed = voice_hash(path)
    entries = {hashed: VoiceEntry(tmp_path / "future.pck", 64, 12, hashed)}
    resolved = resolve_links(
        [{"source": source, "text_id": "Side_OngoingLevel_Future", "english": "Future line."}],
        [],
        entries,
    )
    key = voice_manifest_key("Side_OngoingLevel_Future", "Future line.")
    assert resolved[key]["source"] == path


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


def test_incremental_manifest_keeps_only_valid_previous_entries(tmp_path):
    path = package(tmp_path)
    stat = path.stat()
    source = "chinese(prc)/ex/VO_Galgame/Ver1_0/VO_Belle/voice.wem"
    valid = {"source": source, "file_id": f"{voice_hash(source):016x}",
             "package": str(path), "package_size": stat.st_size,
             "package_mtime_ns": stat.st_mtime_ns, "offset": 64, "size": 12}
    stale = {**valid, "package_size": 1}
    merged = merge_valid_manifest_entries({"old": valid, "stale": stale}, {"new": valid})
    assert set(merged) == {"old", "new"}


def test_fingerprint_learned_alias_survives_restart(tmp_path):
    path = package(tmp_path)
    manifest = tmp_path / "manifest.json"
    learned = tmp_path / "learned.json"
    manifest.write_text(json.dumps({"version": 1, "entries": {}}))
    decoder = tmp_path / "decoder.exe"
    decoder.write_bytes(b"decoder")
    entry = read_external_table(path)[0]
    service = VoiceAssetService(manifest, decoder, tmp_path / "out", learned)
    try:
        service.learn("Comic_future", entry)
        assert service.has("Comic_future")
        assert service.status()["learned_lines"] == 1
    finally:
        service.close()

    restored = VoiceAssetService(manifest, decoder, tmp_path / "out", learned)
    try:
        assert restored.has("Comic_future")
        saved = json.loads(learned.read_text(encoding="utf-8"))["entries"]["Comic_future"]
        assert saved["file_id"] == "000000000000007b"
        assert saved["matched_by"] == "audio_fingerprint"
        assert len(saved["sha256"]) == 64
    finally:
        restored.close()


@pytest.mark.parametrize('empty', [False, True])
def test_batch_keeps_exact_player_variants_and_never_publishes_incomplete_audio(tmp_path, monkeypatch, empty):
    from backend import voice_assets as module
    path = tmp_path / 'fixture.pck'
    path.write_bytes(bytes(64) + b'RIFFfirstwav' + b'RIFFotherwav')
    stat = path.stat()
    entries = {}
    for offset, text, number in [(64, 'First performance.', 123), (76, 'Other performance.', 124)]:
        entries[voice_manifest_key('shared-id', text)] = {'package': str(path), 'offset': offset, 'size': 12,
            'file_id': f'{number:016x}', 'package_size': stat.st_size, 'package_mtime_ns': stat.st_mtime_ns}
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'version': 1, 'entries': entries}))
    service = VoiceAssetService(manifest, tmp_path / 'decoder.exe', tmp_path / 'out')
    calls = []
    def run(command, **options):
        calls.append(command)
        if command[0] == str(service.decoder):
            for source in command[1:]:
                Path(source + '.wav').write_bytes(Path(source).read_bytes())
        else:
            inputs = [Path(command[i + 1]) for i, arg in enumerate(command) if arg == '-i']
            outputs = [Path(arg) for arg in command if str(arg).endswith('.mp3')]
            for index, (source, output) in enumerate(zip(inputs, outputs)):
                output.write_bytes(b'' if empty and index == 1 else b'ID3' + source.read_bytes() * 20)
    monkeypatch.setattr(module.subprocess, 'run', run)
    monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'fixture-ffmpeg')
    try:
        requests = [('shared-id', 1, 'First performance.'), ('shared-id', 2, 'Other performance.')]
        if empty:
            with pytest.raises(ValueError, match='Empty or missing'):
                service.extract_batch(requests)
            assert not list(service.output_dir.glob('*.mp3'))
        else:
            filenames = service.extract_batch(requests)
            assert filenames == ['official-1-000000000000007b.mp3', 'official-2-000000000000007c.mp3']
            assert (service.output_dir / filenames[0]).read_bytes() != (service.output_dir / filenames[1]).read_bytes()
        assert len(calls) == 2
        # Stale packages must fail before launching either decoder.
        calls.clear()
        path.write_bytes(path.read_bytes() + b'changed')
        with pytest.raises(ValueError, match='changed'):
            service.extract_batch(requests)
        assert not calls
    finally:
        service.close()
