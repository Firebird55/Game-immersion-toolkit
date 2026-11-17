"""Bound explicit approved bootstrap receipts, not discovered cache folders."""
import copy
import hashlib
import json

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Shared pure preparation dependency')
pytest.importorskip('backend.publisher_transport', reason='Shared context-owned transport dependency')
from backend.game_data_protocol import GameDataError, GameDataRequest
from backend.publisher_transport import TransferReceipt
from backend import endfield_bootstrap_source as source, endfield_parameters
from backend.endfield_game_data import create_provider
from backend.endfield_client_source import Metadata, Image
from backend.tests.test_endfield_game_data import Fixture


def prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    fixture.data['GameAssembly.dll'] += bytes(100000)
    provider = create_provider(platform='windows', transport_factory=fixture.factory)
    plan = provider.plan(fixture.request, fixture.ctx)
    result = provider.download(plan, fixture.ctx)
    calls = []
    class SmallTransport:
        def fetch_bytes(self, url, *, limit, expected_size, kind, original_range):
            artifact = next(name for name in fixture.data if url == fixture.client['url'] + '/' + name)
            offset, size, total = original_range
            assert expected_size == limit == size and kind == 'metadata' and total == len(fixture.data[artifact])
            raw = fixture.data[artifact][offset:offset + size]
            calls.append((artifact, offset, size))
            return raw, TransferReceipt(hashlib.sha256(url.encode()).hexdigest(), size,
                hashlib.sha256(raw).hexdigest(), {}, original_range)
    return fixture, result.restore_handle, SmallTransport(), calls


def test_real_bootstrap_output_reopens_original_tables_and_only_small_missing_headers(tmp_path, monkeypatch):
    fixture, stage, transport, calls = prepare(tmp_path, monkeypatch)
    bootstrap = source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    metadata = Metadata(bootstrap.artifact(source.METADATA))
    image = Image(bootstrap.artifact('GameAssembly.dll'))
    assert metadata.method('Owned.Client', 'Prepare', 0)['token'] == 0x06000001
    assert image.base == 0x190000000
    assert calls == [(source.METADATA, 0, 256), ('GameAssembly.dll', 0, 4096)]
    # Another reader reuses immutable exact-range receipts without any fetch.
    again = source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    assert again.artifact(source.METADATA).read(0, 256) == fixture.data[source.METADATA][:256]
    assert len(calls) == 2
    with pytest.raises(GameDataError) as error:
        bootstrap.artifact('GameAssembly.dll').read(7000, source.SMALL_RANGE + 1)
    assert error.value.code == 'source_not_prepared' and len(calls) == 2


@pytest.mark.parametrize('change', ['request', 'client', 'receipt_sha', 'stage', 'boolean_schema'])
def test_other_stage_or_selection_is_not_searched_for_in_the_cache(tmp_path, monkeypatch, change):
    fixture, stage, transport, calls = prepare(tmp_path, monkeypatch)
    stage = copy.deepcopy(stage)
    if change == 'request':
        fixture.ctx.request = GameDataRequest('global', 'ko', (), 'text')
    elif change == 'client':
        stage['client']['game_files_md5'] = 'f' * 32
    elif change == 'receipt_sha':
        stage['receipt_sha256'] = '0' * 64
    elif change == 'stage':
        stage['stage'] = 'another-stage'
    elif change == 'boolean_schema':
        stage['schema'] = True
    with pytest.raises(GameDataError) as error:
        source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    assert error.value.code == 'invalid_local_state' and not calls


@pytest.mark.parametrize('change', ['path', 'url', 'range', 'total', 'incomplete', 'duplicate'])
def test_even_rehashed_inert_receipt_must_retain_original_artifact_ownership(tmp_path, monkeypatch, change):
    fixture, stage, transport, calls = prepare(tmp_path, monkeypatch)
    bootstrap = source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    path = bootstrap.root / 'receipt.json'
    receipt = json.loads(path.read_bytes())
    if change == 'path':
        receipt['ranges'][0]['file'] = '../other.bin'
    elif change == 'url':
        receipt['ranges'][0]['receipt']['source_url_sha256'] = '0' * 64
    elif change == 'range':
        receipt['ranges'][0]['range']['offset'] += 1
    elif change == 'total':
        receipt['ranges'][0]['receipt']['original_range'][2] = 1
    elif change == 'incomplete':
        receipt['ranges'] = [row for row in receipt['ranges'] if row['range']['artifact'] != 'GameAssembly.dll']
    elif change == 'duplicate':
        item = copy.deepcopy(receipt['ranges'][-1])
        item['file'] = str(len(receipt['ranges'])) + '.bin'
        receipt['ranges'].append(item)
    path.write_bytes(source._json(receipt))
    stage = {**stage, 'receipt_sha256': hashlib.sha256(source._json(receipt)).hexdigest()}
    with pytest.raises(GameDataError):
        source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    assert not calls


def test_loaded_original_bytes_stay_immutable_and_new_reader_rejects_changed_table(tmp_path, monkeypatch):
    fixture, stage, transport, _ = prepare(tmp_path, monkeypatch)
    bootstrap = source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    row = bootstrap.rows[source.METADATA][0]
    artifact = bootstrap.artifact(source.METADATA)
    old = artifact.read(row['offset'], row['bytes'])
    changed = bytes([old[0] ^ 1]) + old[1:]
    row['path'].write_bytes(changed)
    assert artifact.read(row['offset'], row['bytes']) == old
    fresh = source.Bootstrap(fixture.ctx, fixture.client, transport, stage)
    with pytest.raises(GameDataError) as error:
        fresh.artifact(source.METADATA).read(row['offset'], row['bytes'])
    assert error.value.code == 'invalid_local_state'
