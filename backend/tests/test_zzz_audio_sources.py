"""Whole-chunk audio estimates and local reads enforce explicit consent."""
from dataclasses import replace
import json

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


def test_many_distinct_utterance_ranges_check_each_shared_transport_chunk_once(tmp_path, monkeypatch):
    ctx, old, asset, bodies, calls, factory = setup(tmp_path, b'Original audio owner with many short utterances', base=True)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    sources = AudioSources(ctx, old.build, 'ja', transport_factory=factory)
    original, checked = sources._chunk_available, []
    def available(digest, size):
        checked.append(digest)
        return original(digest, size)
    monkeypatch.setattr(sources, '_chunk_available', available)
    ranges = [{'name': asset.name, 'offset': offset, 'size': 1} for offset in range(asset.size)]
    assert sources.quote_ranges({asset.name: asset}, ranges)[0] == sum(map(len, bodies.values()))
    assert len(checked) == len(set(checked)) == 2
    ctx.stopped = True
    with pytest.raises(GameDataError):sources.quote_ranges({asset.name: asset}, ranges)
    assert calls == []


def test_sdk_base_identity_uses_verified_current_revision_bytes_without_repair(tmp_path, monkeypatch):
    raw = b'1234567890123456'
    ctx, old, asset, bodies, calls, factory = setup(tmp_path, raw, base=True)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    build = {**old.build, 'hotfix': {'base_revision': '1234567890123456_abcdef'}}
    sources = AudioSources(Context(tmp_path, ctx.request, 'download', sum(map(len, bodies.values()))), build, 'ja', transport_factory=factory)
    monkeypatch.setattr(sources, '_markers', lambda: dict.fromkeys(('audio_revision', 'data_revision', 'res_revision', 'silence_revision'), asset.base))
    with pytest.raises(GameDataError):sources._base_matches()
    assert calls == []
    sources.download_ranges({asset.name: asset}, [{'name': asset.name, 'offset': 0, 'size': len(raw)}])
    assert sources._base_matches()
    sources.build = {**build, 'hotfix': {'base_revision': '9876543210987654_abcdef'}}
    before = list(calls)
    assert not sources._base_matches() and calls == before


@pytest.mark.parametrize('matching,size_changed', [(False, False), (True, False), (True, True)])
def test_current_updater_owns_base_rollovers_or_different_package_sizes(tmp_path, monkeypatch, matching, size_changed):
    from backend import sophon_assets as sophon, zzz_hotfix as hotfix
    from backend.tests.test_zzz_hotfix import snapshot, inventory, row
    raw = b'Original voice owner with exact authored package identity'
    ctx, _, asset, _, calls, factory = setup(tmp_path, raw, base=True)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    remote = 'Audio/Windows/Full/Jp/Owned.pck'
    sdk = replace(asset.base, name=hotfix.BASE + remote)
    body = inventory([row(remote, raw + (b'new' if size_changed else b''), patch=False)])
    build = snapshot(2000, {'audio': body});build['manifests']['ja-jp'] = ['owned-manifest']
    sources = AudioSources(ctx, build, 'ja', transport_factory=factory)
    monkeypatch.setattr(sources, 'inputs_available', lambda: True)
    monkeypatch.setattr(sources, '_base_matches', lambda: matching)
    sources._game_files = {}
    monkeypatch.setattr(sophon, 'manifest', lambda *args, **kwargs: {sdk.name: sdk})
    index = sources.index_file('audio');path = sources.path(index);path.parent.mkdir(parents=True);path.write_bytes(body)
    selected, = sources.assets().values()
    if matching and not size_changed:
        assert selected.base == sdk
    else:
        assert selected.base is None and '/output_1000_abcdef/' in selected.url
        assert selected.digest == int(json.loads(body)['files'][0]['md5'])
    assert calls == []


def test_verified_immutable_chunk_memory_reuses_hashes_and_rechecks_changed_files(tmp_path, monkeypatch):
    from backend import zzz_audio_sources as module
    ctx, old, asset, bodies, calls, factory = setup(tmp_path, b'Original data retained across recording lookups', base=True)
    ctx.request = replace(ctx.request, content_mode='text-audio')
    verification = {};selected = [{'name': asset.name, 'offset': 0, 'size': 3}]
    first = AudioSources(Context(tmp_path, ctx.request, 'download', 1000), old.build, 'ja', transport_factory=factory, verification=verification)
    first.download_ranges({asset.name: asset}, selected)
    assert first.ranges_available({asset.name: asset}, selected)
    actual, inspected = module._valid_file, []
    def check(*args):
        inspected.append(args[0])
        return actual(*args)
    monkeypatch.setattr(module, '_valid_file', check)
    following = AudioSources(Context(tmp_path, ctx.request, 'restore', 0), old.build, 'ja', transport_factory=factory, verification=verification)
    assert following.ranges_available({asset.name: asset}, selected) and inspected == []
    path = following.bootstrap_cache / 'chunks' / asset.base.chunks[0][4]
    path.write_bytes(b'x' * path.stat().st_size)
    assert not following.ranges_available({asset.name: asset}, selected) and len(inspected) == 1
    other = AudioSources(Context(tmp_path / 'other-profile', ctx.request, 'restore', 0), old.build, 'ja', transport_factory=factory, verification=verification)
    assert not other.ranges_available({asset.name: asset}, selected)
