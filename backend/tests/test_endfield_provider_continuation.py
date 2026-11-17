"""Approved client stage -> original member stage through actual shared I/O."""
import io
import json
from email.message import Message

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Shared pure preparation dependency')
pytest.importorskip('backend.publisher_transport', reason='Shared context-owned transport dependency')
from backend.game_data_protocol import GameDataError, PreparationStage, SnapshotSource, GameDataRequest
from backend.publisher_transport import PublisherTransport
from backend.endfield_client_source import Metadata, Image
from backend.endfield_game_data import create_provider, METADATA
from backend import endfield_parameters
from backend.tests.test_endfield_game_data import Fixture as Tables
from backend.tests.test_endfield_native_source import Fixture as Native


def fixture(tmp_path, monkeypatch, mode):
    native = Native(tmp_path, monkeypatch)
    tables = Tables(tmp_path, mode)
    native.request = GameDataRequest('global', 'en', ('ja',), mode)
    tables.client = native.identity
    tables.latest = {'version': native.identity['version'], 'pkg': {
        'file_path': native.identity['url'], 'game_files_md5': native.identity['game_files_md5'],
        'packs': [{'url': item['url'], 'md5': item['md5'], 'package_size': str(item['bytes'])}
                  for item in native.identity['artifacts']]}}
    native.resource_version = '300-1'
    native.control_data = None
    native.text_index = native.text_data = None
    native.control_requests = []
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    class Response:
        def __init__(self, url, raw, status, range_=None):
            self.url, self.status, self.body = url, status, io.BytesIO(raw)
            self.headers = Message()
            self.headers['Content-Length'] = str(len(raw))
            if range_: self.headers['Content-Range'] = range_
        def geturl(self): return self.url
        def read(self, size): return self.body.read(size)
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def server(request, **options):
        if '/get_latest?' in request.full_url:
            return Response(request.full_url, json.dumps(tables.latest).encode(), 200)
        if request.full_url in {item['url'] for item in native.identity['artifacts']}:
            return native.server(request, **options)
        if '/get_latest_resources?' in request.full_url:
            base = native.identity['url'].split('/update/')[0] + '/resource/Windows/'
            detail = {'resources': [{'name': role, 'path': base + role + '/' + version + '_Authored/files', 'version': version}
                for role, version in [('main', native.resource_version), ('initial', '200-1')]]}
            return Response(request.full_url, json.dumps(detail).encode(), 200)
        if '/index_' in request.full_url:
            return Response(request.full_url, b'authored original generation index' * 3, 200)
        if request.full_url.endswith('.blc'):
            if '/VFS/00000018/' in request.full_url:
                assert native.text_index is not None
                return Response(request.full_url, native.text_index, 200)
            from backend.tests.test_endfield_akpk_contract import declaration
            return Response(request.full_url, declaration(native.control_data), 200)
        if request.full_url.endswith('.chk'):
            text_source = '/VFS/00000018/' in request.full_url
            if not text_source:
                native.control_requests.append(request.full_url)
            low, high = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            raw = native.text_data if text_source else native.control_data
            return Response(request.full_url, raw[low:high + 1], 206, f'bytes {low}-{high}/{len(raw)}')
        artifact = next(name for name in tables.data if request.full_url == native.identity['url'] + '/' + name)
        low, high = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
        raw = tables.data[artifact]
        return Response(request.full_url, raw[low:high + 1], 206, f'bytes {low}-{high}/{len(raw)}')
    provider = create_provider(platform='windows', transport_factory=lambda ctx, **kw:
        PublisherTransport(ctx, opener=server, **kw))
    def owned_import(bootstrap):
        # The synthetic client has no Wwise original; simulate only the final
        # named import after exercising the real complete cached table readers.
        # The actual original managed chain has its independent frozen replay.
        assert Metadata(bootstrap.artifact(METADATA)).owner('Owned.Client') == 0
        assert Image(bootstrap.artifact('GameAssembly.dll')).base == 0x190000000
        return native.original_import
    monkeypatch.setattr(provider, '_original_import', owned_import)
    return provider, native


def test_ordinary_provider_continues_exact_bootstrap_plan_without_download_context_stage_handle(tmp_path, monkeypatch):
    provider, native = fixture(tmp_path, monkeypatch, 'text-audio')
    from backend import endfield_publisher_signature
    signature = endfield_publisher_signature.verify
    monkeypatch.setattr(endfield_publisher_signature, 'verify', lambda path: {
        **signature(path), 'publisher': 'Authored non-ASCII publisher: 样例'})
    try:
        first_plan = provider.plan(native.request, native.context('plan'))
        first = provider.download(first_plan, native.context('download', first_plan.download_bytes))
        assert isinstance(first, PreparationStage)
        planning = native.context('plan')
        planning.stage_handle = first.restore_handle
        plan = provider.plan(native.request, planning)
        assert plan.stage == 'original-audio-native-member' and plan.download_is_upper_bound
        assert plan.handle['bootstrap'] == first.restore_handle
        downloading = native.context('download', plan.download_bytes)
        assert downloading.stage_handle is None
        result = provider.download(plan, downloading)
        assert isinstance(result, PreparationStage) and not isinstance(result, SnapshotSource)
        assert result.restore_handle['stage'] == 'original-audio-native-source-downloaded'
        assert 0 < downloading.consumed <= plan.download_bytes
        assert result.restore_handle['bootstrap'] == first.restore_handle
        assert len(result.restore_handle['source_receipt_sha256']) == 64
        module_receipts = list(downloading.cache_directory.glob('endfield-original-native/*/module.json'))
        import hashlib
        assert len(module_receipts) == 1 and result.restore_handle['source_receipt_sha256'] == hashlib.sha256(module_receipts[0].read_bytes()).hexdigest()
        # This synthetic client does not define the real common initializer.
        # It must not bypass that owner proof or repeat the full bootstrap.
        planning.stage_handle = result.restore_handle
        calls = len(native.calls)
        with pytest.raises(GameDataError) as error:
            provider.plan(native.request, planning)
        assert error.value.code == 'unsupported_original_metadata' and len(native.calls) == calls
    finally:
        native.service.close()


def test_text_bootstrap_never_enters_audio_source_or_repeats_large_client_download(tmp_path, monkeypatch):
    provider, native = fixture(tmp_path, monkeypatch, 'text')
    try:
        plan = provider.plan(native.request, native.context('plan'))
        result = provider.download(plan, native.context('download', plan.download_bytes))
        planning = native.context('plan')
        planning.stage_handle = result.restore_handle
        monkeypatch.setattr(provider, '_original_import', lambda _: pytest.fail('Text must not acquire original audio runtime'))
        with pytest.raises(GameDataError) as error:
            provider.plan(native.request, planning)
        # This fixture has no original common initializer. Text now proceeds
        # directly to that required proof, without entering the audio route.
        assert error.value.code == 'unsupported_original_metadata'
        assert not native.calls
    finally:
        native.service.close()


@pytest.mark.parametrize('change_generation', [False, True])
def test_full_provider_quotes_selected_control_and_only_explicitly_publishes_its_witness(tmp_path, monkeypatch, change_generation):
    from types import SimpleNamespace as NS
    from backend import endfield_akpk_witness as witness
    from backend.endfield_akpk_contract import Candidate
    from backend.tests.test_endfield_vfs import PARAMETERS, package
    provider, native = fixture(tmp_path, monkeypatch, 'text-audio')
    common = NS(key=PARAMETERS.key, directories={**PARAMETERS.directories, 18: '00000018'}, protocol=3)
    from backend.tests.test_endfield_text_source import catalog
    from backend.tests.test_endfield_release import text_table
    native.text_index, native.text_data = catalog([(name, text_table(name, 1, text)) for name, text in (
        ('TextTable', 'Authored reference'), ('I18nTextTable_EN', 'Owned English'), ('I18nTextTable_JP', '日本語'))])
    native.control_data = package()
    # Only original code/source candidates are authored seams. Real metadata
    # readers, generation/index/MD5/bank gates, persistent witness, shared
    # context/transport and every step's byte consent remain in the path.
    monkeypatch.setattr(provider, '_common', lambda _: common)
    monkeypatch.setattr(witness, 'managed_import', lambda *_: native.original_import)
    monkeypatch.setattr(witness, 'common_candidate', lambda *_: common)
    monkeypatch.setattr(witness, 'NativeImage', lambda _: NS())
    monkeypatch.setattr(witness, 'audio_candidate', lambda *_: Candidate(5, 7))
    old = tmp_path / 'previous-library.json'
    old.write_bytes(b'previous exact source remains active')
    try:
        stage = None
        for expected in ('client-bootstrap', 'original-audio-native-member'):
            planning = native.context('plan')
            planning.stage_handle = stage
            plan = provider.plan(native.request, planning)
            assert plan.stage == expected
            stage = provider.download(plan, native.context('download', plan.download_bytes)).restore_handle
        planning = native.context('plan')
        planning.stage_handle = stage
        plan = provider.plan(native.request, planning)
        assert plan.stage == 'original-audio-package-control'
        assert plan.handle['control']['payload_bytes'] == len(native.control_data)
        assert not native.control_requests
        if change_generation:
            native.resource_version = '301-2'
            with pytest.raises(GameDataError) as error:
                provider.download(plan, native.context('download', plan.download_bytes))
            assert error.value.code == 'publisher_size_changed'
            assert not native.control_requests and not list(tmp_path.rglob('endfield-original-akpk/*/*.json'))
        else:
            downloading = native.context('download', plan.download_bytes)
            result = provider.download(plan, downloading)
            assert isinstance(result, PreparationStage) and not isinstance(result, SnapshotSource)
            assert result.restore_handle['stage'] == 'original-audio-master-verified'
            assert len(native.control_requests) == 1
            assert len(native.control_data) < downloading.consumed <= plan.download_bytes
            reference = result.restore_handle['witness']
            assert witness.restore(downloading, reference, native.identity, result.restore_handle['generation']) == PARAMETERS
            assert 'key' not in reference and 'multiplier' not in reference
            planning.stage_handle = result.restore_handle
            text_plan = provider.plan(native.request, planning)
            assert text_plan.stage == 'original-text-tables'
            text_downloading = native.context('download', text_plan.download_bytes)
            text_result = provider.download(text_plan, text_downloading)
            assert isinstance(text_result, PreparationStage) and not isinstance(text_result, SnapshotSource)
            assert text_result.restore_handle['stage'] == 'original-text-tables-downloaded'
            assert text_result.restore_handle['source']['witness'] == reference
            assert 0 < text_downloading.consumed <= text_plan.download_bytes
            assert len(native.control_requests) == 1  # No extra audio during text acquisition.
        assert old.read_bytes() == b'previous exact source remains active'
    finally:
        native.service.close()
