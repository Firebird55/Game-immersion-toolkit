"""Whole-chunk audio estimates and local reads enforce explicit consent."""
from dataclasses import replace

import pytest

from backend.game_data_protocol import GameDataError
from backend.tests.test_zzz_pc_sources import setup
from backend.tests.test_zzz_game_data import Context
from backend.zzz_audio_sources import AudioSources, MissingAudio


@pytest.mark.parametrize('base', [False, True])
def test_owned_audio_range_quote_charges_actual_container_and_no_read_opens_network(tmp_path, base):
    raw = b'Original complete audio owner with co-resident bytes.'
    ctx, old, asset, bodies, calls, factory = setup(tmp_path, raw, base=base)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    sources = AudioSources(ctx, old.build, 'ja', transport_factory=factory)
    files = {asset.name: asset}
    ranges = [{'name': asset.name, 'offset': 1, 'size': 3}]
    network, disk = sources.quote_ranges(files, ranges)
    assert network == (len(next(iter(bodies.values()))) if base else len(raw))
    assert disk > 3 and calls == []
    with pytest.raises(MissingAudio):sources.read(asset, 1, 3)
    assert calls == []
    download = AudioSources(Context(tmp_path, ctx.request, 'download', network), old.build, 'ja', transport_factory=factory)
    download.download_ranges(files, ranges)
    assert download.read(asset, 1, 3) == raw[1:4]
    assert download.quote_ranges(files, ranges)[0] == 0
    assert download.ranges_available(files, ranges)
    if base:
        # The second original transport chunk was neither selected nor fetched.
        assert len(calls) == 1 and not download.path(asset).exists()
        with pytest.raises(MissingAudio):download.read(asset, 11, 3)
    assert all(phase == 'download' for phase, _ in calls)


def test_range_selection_is_fully_validated_before_first_audio_connection(tmp_path):
    ctx, old, asset, bodies, calls, factory = setup(tmp_path, b'Original audio owner', base=True)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    sources = AudioSources(Context(tmp_path, ctx.request, 'download', 999), old.build, 'ja', transport_factory=factory)
    for invalid in ({'name': 'other-owner', 'offset': 0, 'size': 1},
                    {'name': asset.name, 'offset': True, 'size': 1},
                    {'name': asset.name, 'offset': asset.size, 'size': 1}):
        with pytest.raises(GameDataError):
            sources.download_ranges({asset.name: asset}, [{'name': asset.name, 'offset': 0, 'size': 1}, invalid])
        assert not calls


def test_audio_read_detects_changed_cached_chunk_and_never_repairs_it_implicitly(tmp_path):
    ctx, old, asset, bodies, calls, factory = setup(tmp_path, b'Original immutable audio chunk range', base=True)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    sources = AudioSources(Context(tmp_path, ctx.request, 'download', sum(map(len, bodies.values()))), old.build, 'ja', transport_factory=factory)
    selected = [{'name': asset.name, 'offset': 0, 'size': 3}]
    sources.download_ranges({asset.name: asset}, selected)
    assert sources.read(asset, 0, 3) == b'Ori'
    path = sources.bootstrap_cache / 'chunks' / asset.base.chunks[0][4]
    path.write_bytes(b'x' * path.stat().st_size)
    before = list(calls)
    assert sources.quote_ranges({asset.name: asset}, selected)[0] > 0
    with pytest.raises(MissingAudio):sources.read(asset, 0, 3)
    assert calls == before


def test_text_request_refuses_audio_catalogue_before_any_file_or_network_lookup(tmp_path):
    ctx, old, _, _, calls, factory = setup(tmp_path, b'Original audio owner', base=True)
    with pytest.raises(GameDataError) as failure:AudioSources(ctx, old.build, 'ja', transport_factory=factory)
    assert failure.value.code == 'zzz_audio_not_requested' and not calls
