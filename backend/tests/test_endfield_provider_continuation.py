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
        # The unfinished package/text stage is honest, not another full client
        # download loop or a false ready-library state.
        planning.stage_handle = result.restore_handle
        calls = len(native.calls)
        with pytest.raises(GameDataError) as error:
            provider.plan(native.request, planning)
        assert error.value.code == 'source_not_prepared' and len(native.calls) == calls
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
        assert error.value.code == 'source_not_prepared'
        assert not native.calls
    finally:
        native.service.close()
