"""Local restoration and explicit stage selection cannot masquerade as audio."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import zzz_pc_stages as stages, hoyo_publisher_voice as voice
from backend.game_data_protocol import GameDataError, GameDataRequest
from backend.zzz_pc_sources import OriginalFile


def test_each_typed_phase_uses_only_its_owned_inputs_and_final_ranges():
    scene = {'presentationConfigRoots': [{'block': 'Blocks/1.blk', 'offset': 1, 'size': 4}],
             'comics': {'ranges': [{'block': 'Blocks/2.blk', 'offset': 2, 'size': 5}]},
             'ranges': [{'block': 'Blocks/3.blk', 'offset': 3, 'size': 6}]}
    op = {}
    assert stages._mode_inputs(op) == ('scene-plan', [])
    op['scene-plan'] = {'output': scene}
    assert stages._mode_inputs(op) == ('presentation-config-plan', scene['presentationConfigRoots'])
    op['presentation-config-plan'] = {'output': {'ranges': [{'block': 'Blocks/4.blk', 'offset': 4, 'size': 7}]}}
    assert stages._mode_inputs(op)[0] == 'presentation-owners'
    op['presentation-owners'] = {'output': {'cinemaRanges': [{'block': 'Blocks/5.blk', 'offset': 5, 'size': 8}]}}
    assert stages._mode_inputs(op) == ('comic-plan', scene['comics']['ranges'])
    op['comic-plan'] = {'output': {'ranges': [{'block': 'Blocks/6.blk', 'offset': 6, 'size': 9}]}}
    assert stages._mode_inputs(op) == ('catalogue', [*scene['ranges'], *op['presentation-owners']['output']['cinemaRanges'],
                                                   *op['comic-plan']['output']['ranges']])


@pytest.mark.parametrize('row', [{'block': 'Blocks/2.blk', 'offset': 0, 'size': 3},
                               {'block': 'Blocks/1.blk', 'offset': 99, 'size': 2},
                               {'block': 'Blocks/1.blk', 'offset': 0, 'size': 0},
                               {'block': 'Blocks/1.blk', 'offset': True, 'size': 3}])
def test_wrong_or_unbounded_scene_owners_are_rejected_before_reading(row):
    asset = OriginalFile('authored', 100, 17, 'https://publisher.invalid/authored')
    with pytest.raises(GameDataError):stages._selected({'metadata': asset}, {'Blocks/1.blk': asset}, [row])


def test_audio_request_is_an_honest_gate_without_text_snapshot_or_asset_download(tmp_path, monkeypatch):
    current = {'channel': 'zzz-global', 'version': '3.3.0', 'build': 'authored'}
    monkeypatch.setattr(stages, 'discover', lambda *args, **kwargs: current)
    def forbidden(*args, **kwargs):raise AssertionError('Audio gate acquired text or audio assets')
    monkeypatch.setattr(stages, 'Sources', forbidden)
    request = GameDataRequest('global', 'ja', ('en',), 'text-audio')
    ctx = SimpleNamespace(request=request)
    plan = stages.plan(ctx, {}, tmp_path, SimpleNamespace(identity='reviewed-reader'))
    assert plan.stage == 'audio-materialization' and not plan.runtime_available
    assert plan.download_bytes is None and plan.required_disk_bytes is None
    assert plan.revision == voice.descriptor(current)[0]


def fixture(tmp_path):
    request = GameDataRequest('global', 'en', ('ja',))
    build = {'channel': 'zzz-global', 'version': '3.3.0', 'build': 'authored'}
    revision = voice.descriptor(build)[0]
    snapshot = tmp_path / 'textmap.json';snapshot.write_bytes(b'authored already validated text payload')
    sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    receipt = {'schema': stages.SCHEMA, 'request': request.json(), 'revision': revision, 'build': build, 'snapshot_sha256': sha}
    raw = stages.encoded(receipt);(tmp_path / 'source-receipt.json').write_bytes(raw)
    handle = {'schema': stages.SCHEMA, 'game': 'zzz', 'request': request.json(), 'revision': revision,
              'snapshot_sha256': sha, 'receipt_sha256': hashlib.sha256(raw).hexdigest()}
    ctx = SimpleNamespace(request=request, directory=tmp_path, check=lambda: None)
    return ctx, handle


def test_offline_restore_uses_only_bound_receipt_and_snapshot(tmp_path, monkeypatch):
    ctx, handle = fixture(tmp_path)
    def forbidden(*args, **kwargs):raise AssertionError('Offline restore entered a reader or source downloader')
    monkeypatch.setattr(stages, 'discover', forbidden)
    monkeypatch.setattr(stages, '_execute', forbidden)
    source = stages.restore(ctx, handle)
    assert source.snapshot_path == tmp_path / 'textmap.json' and source.voice_source is None
    assert source.restore_handle == handle and source.source_proof.origin == 'official'
    (tmp_path / 'textmap.json').write_bytes(b'changed')
    with pytest.raises(GameDataError):stages.restore(ctx, handle)


def test_restored_receipt_and_selection_cannot_be_replaced(tmp_path):
    ctx, handle = fixture(tmp_path)
    (tmp_path / 'source-receipt.json').write_bytes(b'{}')
    with pytest.raises(GameDataError):stages.restore(ctx, handle)
    wrong = SimpleNamespace(request=GameDataRequest('cn', 'en', ('ja',)), directory=tmp_path, check=lambda: None)
    with pytest.raises(GameDataError):stages.restore(wrong, handle)


@pytest.mark.parametrize('pointer_changed', [False, True])
def test_final_publisher_guard_and_snapshot_digest(tmp_path, monkeypatch, pointer_changed):
    """Only the current source can publish a snapshot and its streamed digest."""
    request = GameDataRequest('global', 'ja', ('en',))
    build = {'channel': 'zzz-global', 'version': '3.3.0', 'build': 'candidate'}
    reader = SimpleNamespace(identity='frozen-reader')
    revision = voice.descriptor(build)[0]
    handle = {'schema': stages.SCHEMA, 'request': request.json(), 'reader': reader.identity,
              'revision': revision, 'build': build, 'mode': 'catalogue', 'files': [], 'source_network_bytes': 0}
    from backend.game_data_protocol import GameDataPlan
    planned = GameDataPlan(revision, stages.FINAL_METADATA_BYTES, 1024, handle=handle)
    ctx = SimpleNamespace(request=request, cache_directory=tmp_path, directory=tmp_path, check=lambda: None)
    asset = SimpleNamespace(size=1)
    class OriginalSources:
        unique = staticmethod(lambda values: tuple(values))
        def __init__(self, *args, **kwargs):pass
        def index_file(self, name):return asset
        def available(self, value):return True
        def read(self, *args):return b'[]'
        def quote(self, *args):return [], 0, 1024
        def download(self, values):assert not values
    monkeypatch.setattr(stages, 'Sources', OriginalSources)
    monkeypatch.setattr(stages.zzz_hotfix, 'inventory_rows', lambda raw: [])
    monkeypatch.setattr(stages, '_metadata', lambda *args: ({}, {}, {}))
    monkeypatch.setattr(stages, '_load_operations', lambda *args: {'operations': {}})
    monkeypatch.setattr(stages, '_mode_inputs', lambda *args: ('catalogue', []))
    payload = {'format': 2, 'game': 'zzz', 'source_locale': 'ja', 'records': [{
        'text_id': 'AuthoredLine', 'source_locale': 'ja', 'source_text': '合成字幕',
        'texts': {'ja': '合成字幕', 'en': 'Authored line'},
        'english': 'Authored line', 'chinese': '', 'audio_locale': 'ja',
    }]}
    monkeypatch.setattr(stages, '_execute', lambda *args: payload)
    monkeypatch.setattr(stages.sophon_assets, 'release', lambda *args, **kwargs: build)
    monkeypatch.setattr(stages, 'discover', lambda *args, **kwargs:
                        {**build, 'build': 'new-generation'} if pointer_changed else build)
    destination = tmp_path / 'textmap.json'
    receipt_path = tmp_path / 'source-receipt.json'
    if pointer_changed:
        with pytest.raises(GameDataError) as failure:
            stages.download(ctx, planned, reader)
        assert failure.value.code == 'zzz_publisher_changed'
        assert not destination.exists() and not receipt_path.exists()
        return

    read_bytes = Path.read_bytes

    def forbid_snapshot_read(path):
        if path == destination:
            pytest.fail('ZZZ loaded the complete written snapshot to compute its digest')
        return read_bytes(path)

    monkeypatch.setattr(Path, 'read_bytes', forbid_snapshot_read)
    snapshot = stages.download(ctx, planned, reader)
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()
    assert snapshot.restore_handle['snapshot_sha256'] == digest
    assert json.loads(receipt_path.read_bytes())['snapshot_sha256'] == digest


def test_stage_receipts_are_bound_to_current_request_reader_and_source(tmp_path):
    request = GameDataRequest('global', 'ja', ('en',))
    reader = SimpleNamespace(identity='frozen-reader')
    ctx = SimpleNamespace(request=request, cache_directory=tmp_path)
    operation = {'revision': 'original-generation', 'reader': reader.identity,
                 'request': request.json(), 'operations': {'scene-plan': {'output': {'ranges': []}}}}
    raw = stages.encoded(operation); digest = hashlib.sha256(raw).hexdigest()
    path = stages._operation_path(ctx, digest); path.parent.mkdir(parents=True); path.write_bytes(raw)
    handle = {'schema': stages.SCHEMA, 'revision': operation['revision'], 'reader': reader.identity,
              'request': request.json(), 'operations': digest}
    assert stages._load_operations(ctx, handle, operation['revision'], reader) == operation
    assert stages._load_operations(ctx, handle, 'new-generation', reader)['operations'] == {}
    assert stages._load_operations(ctx, handle, operation['revision'], SimpleNamespace(identity='new-reader'))['operations'] == {}
    changed = SimpleNamespace(request=GameDataRequest('global', 'ja', ('de',)), cache_directory=tmp_path)
    assert stages._load_operations(changed, handle, operation['revision'], reader)['operations'] == {}
    path.write_bytes(b'{}')
    with pytest.raises(GameDataError):stages._load_operations(ctx, handle, operation['revision'], reader)
