"""Context-owned HoYoPlay I/O must have no hidden global network fallback."""
import hashlib
import json
from urllib.parse import urlencode

import pytest
import zstandard

from backend import sophon_assets as source
from backend.tests.test_sophon_assets import fixture


def test_unknown_size_original_frame_uses_the_existing_byte_window_cap(tmp_path):
    payload = b'Authored bounded publisher manifest.\n' * 16384
    encoded = zstandard.ZstdCompressor(write_content_size=False).compress(payload)
    maximum = source.MAX_MANIFEST
    assert zstandard.frame_content_size(encoded) == -1
    assert maximum // 1024 < zstandard.get_frame_parameters(encoded).window_size <= maximum
    digest = hashlib.md5(payload).hexdigest()
    def fetch(_url, *, limit):
        assert limit == len(encoded)
        return encoded
    assert source._verified(tmp_path, 'https://publisher.invalid/fixture', len(encoded), len(payload), digest,
        maximum, fetch=fetch) == payload
    assert (tmp_path / digest).read_bytes() == payload


def test_oversized_unknown_window_output_and_extra_frame_still_fail_before_publication(tmp_path):
    payload = b'Authored bounded publisher manifest.\n' * 16384
    encoded = zstandard.ZstdCompressor(write_content_size=False).compress(payload)
    maximum = source.MAX_MANIFEST
    # Unknown-size standard frames have a separate window descriptor. This
    # changes only its advertised window to 256 MiB, beyond the 128-MiB cap.
    assert not encoded[4] & 0x20
    oversized = encoded[:5] + bytes([18 << 3]) + encoded[6:]
    assert zstandard.get_frame_parameters(oversized).window_size > maximum
    digest = hashlib.md5(payload).hexdigest()
    for body, expected_length in ((oversized, len(payload)), (encoded, len(payload) - 1),
                                  (encoded + encoded, len(payload))):
        def fetch(_url, *, limit):
            assert limit == len(body)
            return body
        with pytest.raises((ValueError, zstandard.ZstdError)):
            source._verified(tmp_path, 'https://publisher.invalid/fixture', len(body), expected_length,
                digest, maximum, fetch=fetch)
        assert not (tmp_path / digest).exists()


@pytest.mark.parametrize('channel', ['genshin-global', 'genshin-cn'])
def test_context_fetch_owns_release_build_manifest_file_and_verified_cache(tmp_path, monkeypatch, channel):
    _, _, stamp, original, objects = fixture(tmp_path, monkeypatch, '3.3.0', b'original voice', channel=channel)
    saved = json.loads((tmp_path / 'tools/sophon/releases' / stamp).read_bytes())
    spec = saved['manifests']['en-us']
    (launcher, launcher_id, downloader), game, platform, _ = source.CHANNELS[channel]
    main = {'branch': 'main', 'tag': '3.3.0', 'password': 'temporary', 'package_id': 'package'}
    listing = f'https://{launcher}/hyp/hyp-connect/api/getGameBranches?launcher_id={launcher_id}'
    query = urlencode({key: main[key] for key in ('tag', 'branch', 'password', 'package_id')} | {'plat_app': platform})
    build_url = f'https://{downloader}/downloader/sophon_chunk/api/getBuild?{query}'
    objects[listing] = json.dumps({'retcode': 0, 'data': {'game_branches': [{'game': {'id': game}, 'main': main}]}}).encode()
    rows = []
    for field in ['game', *sorted(set(source.VOICE_FIELDS.values()))]:
        rows.append({'matching_field': field,
            'manifest': {'id': spec[1], 'compressed_size': spec[2], 'uncompressed_size': spec[3], 'checksum': spec[4]},
            'manifest_download': {'encryption': 0, 'compression': 1, 'url_suffix': '', 'url_prefix': spec[0]},
            'chunk_download': {'encryption': 0, 'compression': 1, 'url_suffix': '', 'url_prefix': spec[5]}})
    objects[build_url] = json.dumps({'retcode': 0, 'data': {'tag': '3.3.0', 'build_id': 'SourceA', 'manifests': rows}}).encode()
    calls = []
    def fetch(url, *, limit):
        calls.append((url, limit))
        return objects[url]
    def forbidden(*args, **kwargs):
        raise AssertionError('Context source escaped to the desktop downloader')
    monkeypatch.setattr(source, 'download', forbidden)
    build = source.release(channel, fetch=fetch)
    assert build['channel'] == channel and calls[:2] == [(listing, 2 * 1024**2), (build_url, 4 * 1024**2)]
    directory = tmp_path / 'context-source'
    files = source.manifest(directory, channel, tuple(build['manifests']['game']), ('.pck',), fetch=fetch)
    asset, = files.values()
    # Both the cross-chunk subrange and whole-file digest use context-owned I/O.
    assert asset.read(directory, asset.size - len(original), len(original), fetch=fetch) == original
    complete = asset.read(directory, 0, asset.size, fetch=fetch)
    assert hashlib.md5(complete).hexdigest() == asset.digest
    assert all(not callable(value) for value in vars(asset).values())
    encoded = json.dumps(build, sort_keys=True)
    assert 'fetch' not in encoded and 'temporary' not in encoded
    before = len(calls)
    # Cache reuse still validates bytes, rather than retaining this fetch/context
    # in the ordinary manifest LRU. A second context must not read corrupt data.
    assert source.manifest(directory, channel, tuple(spec), ('.pck',), fetch=forbidden)[asset.name] == asset
    assert asset.read(directory, 0, asset.size, fetch=forbidden) == complete
    assert len(calls) == before
    manifest = directory / 'manifests' / spec[4]
    manifest.write_bytes(b'x' * manifest.stat().st_size)
    with pytest.raises(AssertionError, match='escaped'):
        source.manifest(directory, channel, tuple(spec), ('.pck',), fetch=forbidden)
    assert source.manifest(directory, channel, tuple(spec), ('.pck',), fetch=fetch)[asset.name] == asset
    with pytest.raises(ValueError):
        asset.read(directory, asset.size - 1, 2, fetch=forbidden)


def test_context_retry_digest_and_response_bounds_never_use_global_transport(tmp_path, monkeypatch):
    data = b'authentic original chunk'
    encoded = zstandard.ZstdCompressor().compress(data)
    digest = hashlib.md5(data).hexdigest()
    def forbidden(*args, **kwargs):
        raise AssertionError('Global transport was used')
    monkeypatch.setattr(source, 'download', forbidden)
    responses = [encoded[:-1], encoded]
    calls = []
    def interrupted(url, *, limit):
        calls.append((url, limit))
        return responses.pop(0)
    args = (tmp_path, 'https://publisher.invalid/chunk', len(encoded), len(data), digest, source.MAX_CHUNK)
    assert source._verified(*args, fetch=interrupted) == data
    assert len(calls) == 2 and all(limit == len(encoded) for _, limit in calls)
    (tmp_path / digest).unlink()
    wrong = zstandard.ZstdCompressor().compress(b'x' * len(data))
    with pytest.raises(ValueError):
        source._verified(tmp_path, args[1], len(wrong), len(data), digest, source.MAX_CHUNK,
                         fetch=lambda *a, **k: wrong)
    assert not (tmp_path / digest).exists()
    with pytest.raises(ValueError):
        source._verified(*args, fetch=lambda *a, **k: encoded + b'extra')
    assert not (tmp_path / digest).exists()
    with pytest.raises(ValueError):
        source.release('zzz-global', fetch=lambda *a, **k: 'not original bytes')
