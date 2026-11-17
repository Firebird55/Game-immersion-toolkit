"""Original generation and selected audio controls with real shared budgets."""
import copy
import io
import json
from email.message import Message
from types import SimpleNamespace as NS

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Shared pure preparation dependency')
from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataRequest, GameDataError
from backend.publisher_transport import PublisherTransport
from backend import endfield_resource_source as source
from backend.tests.test_endfield_client_parameters import identity
from backend.tests.test_endfield_akpk_contract import declaration
from backend.tests.test_endfield_vfs import PARAMETERS, package, CHUNK


class Fixture:
    def __init__(self, tmp_path):
        self.identity, self.root = identity(), tmp_path
        self.common = NS(key=PARAMETERS.key, directories=PARAMETERS.directories, protocol=3)
        self.data = package()
        self.index = declaration(self.data)
        self.calls = []
        self.service = GameDataService(tmp_path, {})
        self.request = GameDataRequest('global', 'en', (), 'text-audio')
        self.layers = {role: self.identity['url'].split('/update/')[0] + '/resource/Windows/' + role +
                       ('/300-1_Authored/files' if role == 'main' else '/200-1_Authored/files') for role in ('main', 'initial')}
        self.detail = {'resources': [{'name': role, 'path': url,
            'version': '300-1' if role == 'main' else '200-1'} for role, url in self.layers.items()]}

    def context(self, phase, budget=None):
        return _Context(self.service, self.root, 'local', 'endfield', self.request,
                        self.root / phase, phase, budget=budget)

    def transport(self, ctx):
        fixture = self
        class Response:
            def __init__(self, url, data, status, range_=None):
                self.url, self.status, self.body = url, status, io.BytesIO(data)
                self.headers = Message()
                self.headers['Content-Length'] = str(len(data))
                if range_: self.headers['Content-Range'] = range_
            def geturl(self): return self.url
            def read(self, size): return self.body.read(size)
            def __enter__(self): return self
            def __exit__(self, *_): pass
        def server(request, **_):
            url = request.full_url
            fixture.calls.append(url)
            if '/get_latest_resources?' in url:
                return Response(url, json.dumps(fixture.detail).encode(), 200)
            if '/index_' in url:
                return Response(url, b'authored complete resource index' * 3, 200)
            if url.endswith('.blc'):
                return Response(url, fixture.index, 200)
            assert url.endswith('/' + CHUNK)
            start, end = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            return Response(url, fixture.data[start:end + 1], 206, f'bytes {start}-{end}/{len(fixture.data)}')
        return PublisherTransport(ctx, hosts={'beyond.hg-cdn.com', 'launcher.gryphline.com'}, opener=server)


@pytest.fixture
def original(tmp_path):
    fixture = Fixture(tmp_path)
    try: yield fixture
    finally: fixture.service.close()


def test_original_generation_and_typed_selected_package_precede_explicit_audio_download(original):
    ctx = original.context('plan')
    generation = source.discover(ctx, original.identity, original.transport(ctx))
    plan, index = source.control_plan(ctx, original.identity, original.common, generation, original.transport(ctx))
    assert not any(url.endswith('.chk') for url in original.calls)
    assert plan['payload_bytes'] == len(original.data) and plan['download_is_upper_bound']
    json.dumps(plan)  # Inert handles contain no byte/non-JSON parameter values.
    downloading = original.context('download', plan['download_bytes'])
    row, payload = source.download_control(downloading, original.identity, original.common, plan, index,
                                           original.transport(downloading))
    assert payload == original.data and row.name == 'default_owned_banks.pck'
    assert downloading.consumed == len(original.data)


@pytest.mark.parametrize('change', ['other_host', 'other_minor', 'other_version', 'missing_layer', 'duplicate_layer'])
def test_original_resource_owner_changes_are_not_accepted(original, change):
    if change == 'other_host': original.detail['resources'][0]['path'] = 'https://other.invalid/files'
    elif change == 'other_minor': original.detail['resources'][0]['path'] = original.detail['resources'][0]['path'].replace('/9.8/', '/9.9/')
    elif change == 'other_version': original.detail['resources'][0]['version'] = '999-9'
    elif change == 'missing_layer': original.detail['resources'].pop()
    elif change == 'duplicate_layer': original.detail['resources'].append(copy.deepcopy(original.detail['resources'][0]))
    ctx = original.context('plan')
    with pytest.raises(GameDataError):
        source.discover(ctx, original.identity, original.transport(ctx))
    assert not any(url.endswith('.chk') for url in original.calls)


@pytest.mark.parametrize('change', ['text', 'unsupported_dub', 'bad_index_crc', 'no_small_control'])
def test_audio_metadata_is_not_acquired_for_text_and_invalid_controls_remain_unavailable(original, change):
    ctx = original.context('plan')
    generation = source.discover(ctx, original.identity, original.transport(ctx))
    if change == 'text': ctx.request = GameDataRequest('global', 'en', (), 'text')
    elif change == 'unsupported_dub': ctx.request = GameDataRequest('global', 'ar', (), 'text-audio')
    elif change == 'bad_index_crc': original.index = original.index[:-1] + bytes([original.index[-1] ^ 1])
    elif change == 'no_small_control':
        from backend.tests.test_endfield_vfs import index
        original.index = index(50, name='authored_media.pck')
    before = len(original.calls)
    with pytest.raises(GameDataError):
        source.control_plan(ctx, original.identity, original.common, generation, original.transport(ctx))
    if change in {'text', 'unsupported_dub'}:
        assert len(original.calls) == before
    assert not any(url.endswith('.chk') for url in original.calls)


@pytest.mark.parametrize('change', ['plan', 'index', 'payload', 'no_consent', 'text'])
def test_changed_audio_control_does_not_return_crypto_input(original, change):
    ctx = original.context('plan')
    generation = source.discover(ctx, original.identity, original.transport(ctx))
    plan, index = source.control_plan(ctx, original.identity, original.common, generation, original.transport(ctx))
    downloading = original.context('plan' if change == 'no_consent' else 'download', plan['download_bytes'])
    if change == 'plan': plan['file']['offset'] += 1
    elif change == 'index': index = index[:-1] + bytes([index[-1] ^ 1])
    elif change == 'payload': original.data = original.data[:-1] + bytes([original.data[-1] ^ 1])
    elif change == 'text': downloading.request = GameDataRequest('global', 'en', (), 'text')
    with pytest.raises(GameDataError):
        source.download_control(downloading, original.identity, original.common, plan, index, original.transport(downloading))
