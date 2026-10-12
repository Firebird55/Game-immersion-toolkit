import json
from pathlib import Path
import threading
import zipfile

import pytest
from backend.mobile_export_layout import catalog_name

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
    with zipfile.ZipFile(folder / catalog_name(game)) as pack:
        manifest = json.loads(pack.read("manifest.json"))
        catalog = [json.loads(line) for item in manifest["catalog"] for line in pack.read(item["name"]).splitlines()]
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


def test_audio_size_estimate_tracks_deduplicated_completed_clips(tmp_path):
    records = rows()
    records[1]["sourceVoice"] = digest("voice2")
    events = []
    calls = []
    export_library("zzz", records, tmp_path / "out", voice=voice(tmp_path, calls), progress=events.append)
    conversion = [e for e in events if "estimatedAudioBytes" in e]
    assert conversion[0]["estimatedAudioBytes"] == 1030
    assert conversion[-1]["estimatedAudioBytes"] == conversion[-1]["audioBytes"] == 515
    assert len(calls) == 2  # distinct source bindings, identical decoded content


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
    next((tmp_path / "out/.toolkit-work/cache").glob("*.mp3")).write_bytes(b"corrupt" * 100)
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


def test_corrupt_completed_pack_is_repaired_from_verified_cache(tmp_path):
    calls = []
    output = tmp_path / "out"
    first = export_library("zzz", rows(), output, voice=voice(tmp_path, calls))
    pack = next(Path(first["folder"]).glob("*voices*.zip"))
    pack.write_bytes(b"broken")
    second = export_library("zzz", rows(), output, voice=voice(tmp_path, calls))
    with zipfile.ZipFile(next(Path(second["folder"]).glob("*voices*.zip"))) as archive:
        assert archive.testzip() is None
    assert len(calls) == 1
    assert list((output / ".toolkit-work").glob("*.invalid-*"))


def parallel_fixture(tmp_path, count=12):
    records = [dict(rows()[0], textId=f'fixture:{i}', sourceVoice=digest(f'voice:{i}')) for i in range(count)]
    def decode(row, number):
        path = tmp_path / f'clip-{number}.mp3'
        path.write_bytes(b'ID3' + bytes([number % 3]) * 512)  # Three distinct clips; exact deduplication.
        return path
    return records, decode


def test_parallel_export_is_bounded_deduplicated_and_byte_identical_to_serial(tmp_path):
    records, decode = parallel_fixture(tmp_path)
    records += [dict(records[0], textId='fixture:alias')]
    serial = export_library('zzz', records, tmp_path / 'serial', voice=decode)
    lock, barrier = threading.Lock(), threading.Barrier(4)
    calls, active, peak = [], [0], [0]
    def concurrent(row, number):
        with lock:
            calls.append(number); active[0] += 1; peak[0] = max(peak[0], active[0])
        try:
            if number < 4:
                barrier.wait(timeout=5)  # The first batch must run concurrently.
            return decode(row, number)
        finally:
            with lock:
                active[0] -= 1
    parallel = export_library('zzz', records, tmp_path / 'parallel', voice=concurrent, workers=4)
    assert 1 < peak[0] <= 4 and len(calls) == 12
    a, b = Path(serial['folder']), Path(parallel['folder'])
    assert a.name == b.name
    assert {p.name: p.read_bytes() for p in a.glob('*.zip')} == {p.name: p.read_bytes() for p in b.glob('*.zip')}
    assert parallel['coverage']['exportedVoices'] == 13
    export_library('zzz', records, tmp_path / 'parallel', voice=concurrent, workers=4)
    assert len(calls) == 12


@pytest.mark.parametrize('failure', ['cancel', 'decode', 'changed'])
def test_parallel_failure_preserves_previous_export_and_can_resume(tmp_path, failure):
    output = tmp_path / 'out'
    export_library('zzz', rows(), output, include_audio=False)
    before = (output / 'latest.json').read_bytes()
    records, decode = parallel_fixture(tmp_path)
    cancel, changed = threading.Event(), threading.Event()
    calls = []
    def failing(row, number):
        calls.append(number)
        if number == 0:
            if failure == 'decode':
                raise ValueError('fixture decoder failed')
            if failure == 'changed':
                changed.set()
        return decode(row, number)
    def check():
        if changed.is_set():
            raise ValueError('game changed')
    def progress(_):
        if failure == 'cancel':
            cancel.set()
    with pytest.raises(ExportCancelled if failure == 'cancel' else ValueError):
        export_library('zzz', records, output, voice=failing, workers=4, cancel=cancel, check=check, progress=progress)
    assert (output / 'latest.json').read_bytes() == before
    assert len(calls) <= 4
    completed = len(list((output / '.toolkit-work/cache').glob('*.json')))
    calls.clear()
    def resume(row, number):
        calls.append(number)
        return decode(row, number)
    result = export_library('zzz', records, output, voice=resume, workers=4)
    assert result['coverage']['exportedVoices'] == 12
    assert len(calls) == 12 - completed


def test_export_moves_only_its_owned_decoded_files_into_verified_cache(tmp_path):
    records, _ = parallel_fixture(tmp_path, 2)
    output = tmp_path / 'out'
    decoded = output / 'decoded'
    decoded.mkdir(parents=True)
    def voice(row, number):
        path = decoded / f'{number}.mp3'
        path.write_bytes(b'ID3' + bytes([number]) * 512)
        return path
    export_library('zzz', records, output, voice=voice, workers=2)
    assert not list(decoded.glob('*.mp3'))
    assert len(list((output / '.toolkit-work/cache').glob('*.mp3'))) == 2


def test_batched_export_preserves_variants_deduplication_and_partial_cache(tmp_path):
    records, scalar = parallel_fixture(tmp_path, 21)
    records[0]['playerVoice'] = 'female'
    records[1]['playerVoice'] = 'male'
    records.append(dict(records[0], textId='fixture:alias'))
    expected = export_library('zzz', records, tmp_path / 'scalar', voice=scalar, workers=4)
    output = tmp_path / 'batch'
    export_library('zzz', records[:3], output, voice=scalar)
    decoded, batches = [], []
    def voice(row, number):
        raise AssertionError('Batch-capable source must use its verified batch path')
    def batch(requests):
        batches.append(len(requests))
        decoded.extend(number for row, number in requests)
        return [scalar(row, number) for row, number in requests]
    voice.batch = batch
    actual = export_library('zzz', records, output, voice=voice, workers=4)
    assert sorted(decoded) == list(range(3, 21))
    assert all(1 <= size <= 8 for size in batches)
    a, b = Path(expected['folder']), Path(actual['folder'])
    assert a.name == b.name
    assert {p.name: p.read_bytes() for p in a.glob('*.zip')} == {p.name: p.read_bytes() for p in b.glob('*.zip')}
    decoded.clear()
    export_library('zzz', records, output, voice=voice, workers=4)
    assert not decoded


@pytest.mark.parametrize('failure', ['incomplete', 'decoder', 'cancel', 'changed'])
def test_batch_failures_never_replace_valid_export_and_resume_from_completed_clips(tmp_path, failure):
    output = tmp_path / 'batch'
    export_library('zzz', rows(), output, include_audio=False)
    before = (output / 'latest.json').read_bytes()
    records, scalar = parallel_fixture(tmp_path, 21)
    cancel, changed = threading.Event(), threading.Event()
    def voice(row, number):
        return scalar(row, number)
    def batch(requests):
        result = [scalar(row, number) for row, number in requests]
        if failure == 'incomplete':
            return result[:-1]
        if failure == 'decoder':
            raise ValueError('fixture decoder failure')
        if failure == 'changed':
            changed.set()
        return result
    voice.batch = batch
    def progress(_):
        if failure == 'cancel':
            cancel.set()
    def check():
        if changed.is_set():
            raise ValueError('game changed')
    with pytest.raises(ExportCancelled if failure == 'cancel' else ValueError):
        export_library('zzz', records, output, voice=voice, workers=2, cancel=cancel, check=check, progress=progress)
    assert (output / 'latest.json').read_bytes() == before
    completed = len(list((output / '.toolkit-work/cache').glob('*.json')))
    calls = []
    def resume(requests):
        calls.extend(requests)
        return [scalar(row, number) for row, number in requests]
    voice.batch = resume
    result = export_library('zzz', records, output, voice=voice, workers=2)
    assert len(calls) == 21 - completed
    assert result['coverage']['exportedVoices'] == 21
