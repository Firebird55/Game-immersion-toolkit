"""Original source bodies must be planned and authenticated before range I/O."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
import zstandard

from backend import sophon_assets as sophon
from backend.game_data_protocol import GameDataError, GameDataRequest
from backend.publisher_transport import PublisherTransport
from backend.tests.test_zzz_game_data import Context, Response
from backend.zzz_pc_sources import Sources, OriginalFile, NeedsFiles
from backend.xxhash64 import xxhash64


def setup(tmp_path, raw, *, base=False):
    request = GameDataRequest('global', 'ja', ('en',))
    ctx = Context(tmp_path, request)
    objects, calls = {}, []
    host = 'https://autopatchos.zenlesszonezero.com/owned'
    if base:
        chunks = []
        for offset, part in [(0, raw[:11]), (11, raw[11:])]:
            digest = hashlib.md5(part).hexdigest()
            identity = '0' * 16 + '_' + digest
            compressed = zstandard.ZstdCompressor().compress(part)
            objects[host + '/' + identity] = compressed
            chunks.append((offset, len(part), len(compressed), identity, digest))
        original = sophon.File('ZenlessZoneZero_Data/StreamingAssets/Blocks/11.blk', len(raw),
                               hashlib.md5(raw).hexdigest(), tuple(chunks), host)
        asset = OriginalFile(original.name, len(raw), xxhash64(raw), '', original)
    else:
        objects[host + '/11.blk'] = raw
        asset = OriginalFile('ZenlessZoneZero_Data/Persistent/Blocks/11.blk', len(raw), xxhash64(raw), host + '/11.blk')
    def factory(context, *, hosts):
        def open(request, **kwargs):
            calls.append((context.phase, request.full_url))
            return Response(request.full_url, objects[request.full_url])
        return PublisherTransport(context, hosts=hosts, opener=open)
    return ctx, Sources(ctx, {'channel': 'zzz-global'}, transport_factory=factory), asset, objects, calls, factory


@pytest.mark.parametrize('base', [False, True])
def test_preflight_whole_container_bounds_and_no_hidden_range_download(tmp_path, base):
    raw = b'An authored complete original container, including unrelated co-resident bytes.'
    ctx, source, asset, objects, calls, factory = setup(tmp_path, raw, base=base)
    selected, network, disk = source.quote([asset, asset], scratch_bytes=4096)
    assert len(selected) == 1 and network == sum(map(len, objects.values()))
    assert disk >= len(raw) + 4096
    with pytest.raises(NeedsFiles):source.read(asset, 1, 3)
    assert calls == []
    # The same planned asset becomes readable only in the explicit download.
    downloaded = Sources(Context(tmp_path, ctx.request, 'download', network), source.build, transport_factory=factory)
    downloaded.download([asset])
    assert downloaded.read(asset, 1, 3) == raw[1:4]
    assert downloaded.read(asset, 0, len(raw)) == raw
    assert all(phase == 'download' for phase, _ in calls)
    assert downloaded.quote([asset])[1] == 0
    assert 'base' not in json.dumps(selected) and not any(callable(value) for value in selected[0].values())


def test_cached_sophon_chunks_materialize_with_zero_network_and_original_md5(tmp_path):
    raw = b'An original base container needs both its SDK MD5 and updater XXH64.'
    ctx, source, asset, objects, calls, factory = setup(tmp_path, raw, base=True)
    _, network, _ = source.quote([asset])
    downloaded = Sources(Context(tmp_path, ctx.request, 'download', network), source.build, transport_factory=factory)
    downloaded.download([asset])
    downloaded.path(asset).unlink()
    before = list(calls)
    next_source = Sources(Context(tmp_path, ctx.request, 'download', 0), source.build, transport_factory=factory)
    assert next_source.quote([asset])[1] == 0
    next_source.download([asset])
    assert next_source.read(asset, 0, len(raw)) == raw and calls == before
    wrong = replace(asset, base=replace(asset.base, digest='0' * 32))
    assert next_source.available(wrong) is False and next_source.available(wrong) is False
    with pytest.raises(GameDataError, match='failed its checksum'):
        next_source.download([wrong])
    assert next_source.path(asset).read_bytes() == raw


def test_corrupt_new_updater_body_cannot_publish_or_replace_old_source(tmp_path):
    raw = b'An authentic retained original file.'
    ctx, source, asset, objects, calls, factory = setup(tmp_path, raw)
    downloaded = Sources(Context(tmp_path, ctx.request, 'download', len(raw)), source.build, transport_factory=factory)
    downloaded.download([asset]); old = downloaded.path(asset).read_bytes()
    newer = replace(asset, digest=xxhash64(b'z' * len(raw)))
    downloaded = Sources(Context(tmp_path, ctx.request, 'download', len(raw)), source.build, transport_factory=factory)
    with pytest.raises(ValueError):downloaded.download([newer])
    assert not downloaded.path(newer).exists() and downloaded.path(asset).read_bytes() == old
    foreign = replace(newer, url='https://foreign.invalid/source')
    before = len(calls)
    with pytest.raises(GameDataError):downloaded.download([foreign])
    assert len(calls) == before


def test_text_source_discovery_does_not_convert_consent_failures_into_endpoint_fallback(tmp_path, monkeypatch):
    from backend import zzz_pc_sources as pc, hoyo_dispatch_metadata as metadata
    from types import SimpleNamespace
    config = {'GameDispatchChannelName': 'T1NQUk9EV2lu', 'ProtoDispatchKey': 'YWFhYWFhYWFhYWFhYWFhYQ==',
              'GameDispatchArrayURL': ['aHR0cHM6Ly9nbG9iYWxkcC1wcm9kLW9zMDEuemVubGVzc3pvbmV6ZXJvLmNvbS9xdWVyeV9kaXNwYXRjaA=='],
              '_official_gateway_keys': (), metadata._PROVENANCE: {}}
    monkeypatch.setattr(pc.bootstrap, 'official', lambda *args, **kwargs: config)
    class Forbidden:
        def __init__(self, *args, **kwargs):pass
        def fetch_bytes(self, *args, **kwargs):raise GameDataError('unapproved_asset_transfer', 'Consent is required.')
    request = GameDataRequest('global', 'ja')
    with pytest.raises(GameDataError) as error:
        pc.discover(Context(tmp_path, request), {'channel': 'zzz-global', 'version': '3.3.0'}, tmp_path,
                    transport_factory=Forbidden)
    assert error.value.code == 'unapproved_asset_transfer'
