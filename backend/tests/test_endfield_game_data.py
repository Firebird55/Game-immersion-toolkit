"""Actual shared contracts with owned small publisher-client range fixtures."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

# The shared service/transport is an independently reviewed integration wave.
# A game-only checkout must not replace that dependency with a second schema.
protocol = pytest.importorskip('backend.game_data_protocol', reason='Reviewed shared provider contract is a separate dependency')
transport = pytest.importorskip('backend.publisher_transport', reason='Reviewed context transport is a separate dependency')

from backend import endfield_game_data as source, endfield_parameters
from backend.tests.endfield_parameter_fixture import toy_metadata, toy_pe
from backend.tests.test_endfield_client_parameters import identity


class Fixture:
    def __init__(self, tmp_path, mode='text'):
        self.client = identity()
        self.latest = {'version': self.client['version'], 'pkg': {'file_path': self.client['url'],
            'game_files_md5': self.client['game_files_md5'], 'packs': [
                {'url': row['url'], 'md5': row['md5'], 'package_size': str(row['bytes'])}
                for row in self.client['artifacts']]}}
        self.data = {source.METADATA: toy_metadata(), 'GameAssembly.dll': toy_pe()}
        self.calls, self.fail_download, self.owner_delta = [], False, 0
        self.request = protocol.GameDataRequest('global', 'en', ('ja',), mode)
        self.ctx = SimpleNamespace(game='endfield', request=self.request, cache_directory=tmp_path / 'cache',
                                   check=lambda: None)

    def factory(self, ctx, *, hosts):
        fixture = self
        assert ctx is self.ctx
        assert hosts == {'launcher.gryphline.com', 'beyond.hg-cdn.com'}
        class Transport:
            def fetch_bytes(self, url, *, limit, kind, expected_size=None, original_range=None):
                fixture.calls.append(('fetch', kind, url, original_range))
                assert kind == 'metadata'
                if '/get_latest?' in url:
                    data = json.dumps(fixture.latest).encode()
                    owner = None
                else:
                    artifact = next(name for name in fixture.data if url == fixture.client['url'] + '/' + name)
                    raw = fixture.data[artifact]
                    assert original_range == (0, expected_size, None)
                    data, owner = raw[:expected_size], (0, expected_size, len(raw) + fixture.owner_delta)
                assert len(data) <= limit
                return data, transport.TransferReceipt(hashlib.sha256(url.encode()).hexdigest(), len(data),
                    hashlib.sha256(data).hexdigest(), {}, owner)

            def download_to(self, url, destination, *, limit, expected_size, kind, original_range):
                fixture.calls.append(('download', kind, url, original_range))
                assert kind == 'asset'
                if fixture.fail_download:
                    raise protocol.GameDataError('metadata_download_interrupted', 'Authored interrupted range')
                artifact = next(name for name in fixture.data if url == fixture.client['url'] + '/' + name)
                offset, size, total = original_range
                assert total == len(fixture.data[artifact]) and size == expected_size == limit
                data = fixture.data[artifact][offset:offset + size]
                assert len(data) == size
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                return transport.TransferReceipt(hashlib.sha256(url.encode()).hexdigest(), len(data),
                    hashlib.sha256(data).hexdigest(), {}, original_range)
        return Transport()


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_original_size_plan_and_download_are_only_a_non_audio_bootstrap(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path, mode)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    plan = provider.plan(fixture.request, fixture.ctx)
    assert plan.stage == 'client-bootstrap' and plan.runtime_available is True
    assert plan.source_proof is None and plan.download_bytes == sum(row['bytes'] for row in plan.handle['ranges'])
    assert plan.required_disk_bytes == 2 * plan.download_bytes + 4352
    assert not any(row[0] == 'download' for row in fixture.calls)
    result = provider.download(plan, fixture.ctx)
    assert isinstance(result, protocol.PreparationStage)
    assert not isinstance(result, protocol.SnapshotSource)
    assert result.restore_handle['stage'] == 'client-bootstrap-downloaded'
    assert result.restore_handle['request']['content_mode'] == mode
    assert all(call[1] != 'audio' for call in fixture.calls)
    assert 'not complete native artifact hashes' in next(fixture.ctx.cache_directory.rglob('receipt.json')).read_text()
    with pytest.raises(protocol.GameDataError, match='not a restorable game library'):
        provider.restore(result.restore_handle, fixture.ctx)


@pytest.mark.parametrize('change', ['client', 'mode', 'range', 'estimate', 'revision', 'stage'])
def test_changed_source_selection_or_estimate_stops_before_large_transfer(tmp_path, monkeypatch, change):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    plan = provider.plan(fixture.request, fixture.ctx)
    if change == 'client':
        fixture.latest['pkg']['game_files_md5'] = 'f' * 32
    elif change == 'mode':
        fixture.ctx.request = protocol.GameDataRequest('global', 'en', ('ja',), 'text-audio')
    elif change == 'range':
        plan.handle['ranges'][0]['offset'] += 1
    else:
        from dataclasses import replace
        plan = replace(plan, **{'estimate': {'download_bytes': plan.download_bytes + 1},
                                'revision': {'revision': 'changed'}, 'stage': {'stage': 'content'}}[change])
    with pytest.raises(protocol.GameDataError) as caught:
        provider.download(plan, fixture.ctx)
    assert caught.value.code == 'publisher_size_changed'
    assert not any(call[0] == 'download' for call in fixture.calls)


@pytest.mark.parametrize('platform', ['android', 'linux', 'macos'])
def test_unreviewed_host_runtime_never_fetches_native_source(tmp_path, platform):
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform=platform, transport_factory=lambda *_a, **_kw: pytest.fail('No unsupported-host transfer'))
    with pytest.raises(protocol.GameDataError) as caught:
        provider.plan(fixture.request, fixture.ctx)
    assert caught.value.code == 'missing_toolkit_runtime'


def test_incomplete_owner_bounds_and_interruption_preserve_existing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    fixture.owner_delta = -4000
    with pytest.raises(protocol.GameDataError):
        provider.plan(fixture.request, fixture.ctx)
    fixture.owner_delta = 0
    plan = provider.plan(fixture.request, fixture.ctx)
    retained = tmp_path / 'previous-language.json'
    retained.write_bytes(b'authored previous active data')
    fixture.fail_download = True
    with pytest.raises(protocol.GameDataError):
        provider.download(plan, fixture.ctx)
    assert retained.read_bytes() == b'authored previous active data'
    assert not list(fixture.ctx.cache_directory.rglob('receipt.json'))


def test_mode_and_language_selections_keep_distinct_source_stage_identities(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    plans = []
    for request in (fixture.request, protocol.GameDataRequest('global', 'en', ('ja',), 'text-audio'),
                    protocol.GameDataRequest('global', 'ja', ('en',), 'text')):
        fixture.ctx.request = request
        plan = provider.plan(request, fixture.ctx)
        plans.append(plan)
        provider.download(plan, fixture.ctx)
    assert plans[0].revision == plans[1].revision == plans[2].revision
    assert plans[0].handle != plans[1].handle != plans[2].handle
    receipts = list(fixture.ctx.cache_directory.rglob('receipt.json'))
    assert len(receipts) == 3
    assert {json.loads(path.read_bytes())['request']['content_mode'] for path in receipts} == {'text', 'text-audio'}
    assert all(call[1] != 'audio' for call in fixture.calls)


def test_original_artifact_hash_changes_generation_even_with_same_marketing_version(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    first = provider.plan(fixture.request, fixture.ctx)
    fixture.latest['pkg']['game_files_md5'] = 'e' * 32
    second = provider.plan(fixture.request, fixture.ctx)
    assert first.revision != second.revision
    assert first.handle['client']['version'] == second.handle['client']['version']
    assert first.handle['request'] == second.handle['request']
