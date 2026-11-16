"""Synthetic regional archives; no publisher files or real parameters."""
import hashlib
import json
import struct

from Crypto.Cipher import AES
import pytest

from backend import nte_archive_metadata as metadata, nte_assets
from backend.preparation_errors import PreparationFailure


GLOBAL, CHINESE = '0x' + '01' * 32, '0x' + '02' * 32


def pak(key=GLOBAL, encrypted=True):
    index = b'authored synthetic publisher index'
    padded = index.ljust((len(index) + 15) // 16 * 16, b'\0')
    data = AES.new(bytes.fromhex(key[2:]), AES.MODE_ECB).encrypt(padded)
    # NTE's documented v12 offset is the real index position plus one.
    footer = (bytes(16) + bytes([int(encrypted)]) + metadata.MAGIC +
              struct.pack('<IQQ', 12, 49, len(index)) + hashlib.sha1(index).digest() + bytes(160))
    return bytes(48) + data + bytes(64) + footer


def catalog():
    return metadata.Catalog('a' * 40, 'b' * 64, {'nte-global': GLOBAL, 'nte-cn': CHINESE})


def source(global_key=GLOBAL):
    return (f'Other game {"0x" + "03" * 32}\nNeverness to Everness (chinese) {CHINESE}\n'
            f'Neverness to Everness (global)  {global_key}\n').encode()


def test_region_is_proved_by_full_index_checksum_and_explicit_regions_cannot_cross():
    for region, key in [('nte-global', GLOBAL), ('nte-cn', CHINESE)]:
        data = pak(key)
        read = lambda offset, size: data[offset:offset + size]
        assert catalog().verified_key(read, len(data)) == key
        assert catalog().verified_key(read, len(data), region) == key
        other = 'nte-cn' if region == 'nte-global' else 'nte-global'
        with pytest.raises(PreparationFailure):
            catalog().verified_key(read, len(data), other)
        corrupted = bytearray(data)
        corrupted[48] ^= 1
        with pytest.raises(PreparationFailure):
            catalog().verified_key(lambda p, n: corrupted[p:p + n], len(data))


@pytest.mark.parametrize('change', ['index-size', 'index-offset', 'version', 'truncated-range'])
def test_unbounded_or_incomplete_index_is_refused_before_parameter_selection(change):
    data = bytearray(pak())
    marker = data.rfind(metadata.MAGIC)
    if change == 'index-size':
        struct.pack_into('<Q', data, marker + 16, 64 * 1024**2 + 1)
    elif change == 'index-offset':
        struct.pack_into('<Q', data, marker + 8, len(data) + 1)
    elif change == 'version':
        struct.pack_into('<I', data, marker + 4, 13)
    def read(offset, size):
        assert 0 <= offset <= len(data) - size
        return data[offset:offset + size - int(change == 'truncated-range')]
    with pytest.raises(PreparationFailure):
        catalog().verified_key(read, len(data))


def test_plaintext_file_does_not_prove_any_format_parameter():
    data, reads = pak(encrypted=False), []
    def read(offset, size):
        reads.append((offset, size))
        return data[offset:offset + size]
    assert catalog().verified_key(read, len(data)) is None
    assert len(reads) == 1


def test_only_named_regional_entries_are_read_at_one_immutable_commit():
    seen = []
    def fetch(url, limit):
        seen.append(url)
        assert limit == metadata.LIMIT
        return json.dumps([{'sha': 'a' * 40}]).encode() if 'api.github' in url else source()
    result = metadata.load(fetch=fetch)
    assert result.parameters == catalog().parameters
    assert result.revision == 'a' * 40 and not result.fallback
    assert result.digest == hashlib.sha256(source()).hexdigest()
    assert '/a' + 'a' * 39 + '/' in seen[-1]


@pytest.mark.parametrize('text', [b'withdrawn', source() + source(), b'Other game ' + GLOBAL.encode()])
def test_absent_or_ambiguous_game_entry_is_not_replaced_by_another_game(text):
    def fetch(url, *_):
        return json.dumps([{'sha': 'a' * 40}]).encode() if 'api.github' in url else text
    with pytest.raises(PreparationFailure) as failure:
        metadata.load(fetch=fetch)
    assert failure.value.code == 'game_metadata_unavailable'


def test_metadata_only_update_supports_new_archive_while_old_source_remains_bound():
    state = {'revision': 'a' * 40, 'parameter': GLOBAL}
    def fetch(url, *_):
        return json.dumps([{'sha': state['revision']}]).encode() if 'api.github' in url else source(state['parameter'])
    before = metadata.load(fetch=fetch)
    state.update(revision='c' * 40, parameter='0x' + '04' * 32)
    after = metadata.load(fetch=fetch)
    old, new = pak(), pak(state['parameter'])
    assert before.verified_key(lambda p, n: old[p:p + n], len(old), 'nte-global') == GLOBAL
    assert after.verified_key(lambda p, n: new[p:p + n], len(new), 'nte-global') == state['parameter']
    assert before.digest != after.digest and before.revision != after.revision
    with pytest.raises(PreparationFailure):
        before.verified_key(lambda p, n: new[p:p + n], len(new), 'nte-global')


def test_api_outage_uses_pinned_candidate_but_still_checks_archive():
    urls = []
    def fetch(url, *_):
        urls.append(url)
        if 'api.github' in url:
            raise OSError('fixture outage')
        return source()
    result = metadata.load(fetch=fetch)
    assert result.fallback and result.revision == metadata.FALLBACK_REVISION
    assert f'/{metadata.FALLBACK_REVISION}/' in urls[-1]
    data = pak('0x' + '05' * 32)
    with pytest.raises(PreparationFailure):
        result.verified_key(lambda p, n: data[p:p + n], len(data))


def test_historical_metadata_keeps_immutable_identity_after_upstream_rotation_and_offline_restart(tmp_path):
    old = source()
    old_digest = hashlib.sha256(old).hexdigest()
    calls = []
    def fetch(url, *_):
        calls.append(url)
        if 'api.github' in url:
            return json.dumps([{'sha': 'a' * 40}]).encode()
        return old
    before = metadata.load(fetch=fetch, cache=tmp_path)
    assert before.digest == old_digest
    calls.clear()
    def offline(*_):
        pytest.fail('Historical cached data must not request the latest source or need a connection')
    historical = metadata.load(fetch=offline, cache=tmp_path, revision=before.revision, digest=before.digest)
    assert historical == before
    cached = tmp_path / f'{before.revision}-{before.digest}.txt'
    cached.write_bytes(source('0x' + '05' * 32))
    historical = metadata.load(fetch=fetch, cache=tmp_path, revision=before.revision, digest=before.digest)
    assert historical == before and len(calls) == 1 and 'api.github' not in calls[0]
    with pytest.raises(PreparationFailure):
        metadata.load(revision=before.revision, digest=before.digest,
                      fetch=lambda *_: source('0x' + '06' * 32))
    for revision, digest in [('../escape', old_digest), ('a' * 40, None), (None, old_digest)]:
        with pytest.raises(PreparationFailure):
            metadata.load(revision=revision, digest=digest, fetch=offline)


def test_fresh_normal_reader_selects_chinese_metadata_without_existing_private_cache(tmp_path, monkeypatch):
    folder = tmp_path / 'Client/WindowsNoEditor/HT/Content/PatchPaks'
    folder.mkdir(parents=True)
    (folder / 'pakchunk2-Windows_0_P.pak').write_bytes(pak(CHINESE))
    protected = tmp_path / 'protected' / 'metadata'
    monkeypatch.setattr(nte_assets, '_metadata_path', lambda *_: protected)
    monkeypatch.setattr(nte_assets, 'download', lambda url, *_:
        json.dumps([{'sha': 'a' * 40}]).encode() if 'api.github' in url else source())
    nte_assets._archive_metadata.cache_clear()
    try:
        assert nte_assets._archive_metadata(tmp_path, 'fixture-release') == CHINESE
        assert not protected.exists(), 'Parameters are persisted only after successful reader extraction'
    finally:
        nte_assets._archive_metadata.cache_clear()


def test_exact_publisher_ranges_prove_metadata_without_saving_or_installing_an_archive(monkeypatch):
    import io
    from backend import nte_release
    body = pak(CHINESE)
    item = nte_release.File(len(body), hashlib.md5(body).hexdigest(), len(body) + 200, 'b' * 32, 100)
    requested = []
    url = f'https://yhcdn1.wmupd.com/clientRes/PC_150/Res/b/{item.object_digest}.{item.object_size}'
    def open_range(request, timeout):
        assert request.full_url == url and timeout == 60
        interval = request.headers['Range'].removeprefix('bytes=')
        start, end = map(int, interval.split('-'))
        requested.append((start, end))
        class Reply(io.BytesIO):
            status = 206
            headers = {'Content-Range': f'bytes {start}-{end}/{item.object_size}'}
            def geturl(self):
                return url
        return Reply(body[start - item.offset:end - item.offset + 1])
    monkeypatch.setattr(nte_release.urllib.request, 'urlopen', open_range)
    read = lambda at, size: nte_release.read_range('nte-cn', 'PC_150', item, at, size)
    assert catalog().verified_key(read, item.size, 'nte-cn') == CHINESE
    assert len(requested) == 2
    before = len(requested)
    for at, size in [(-1, 20), (0, True), (0, 0), (0, item.size + 1)]:
        with pytest.raises(ValueError):
            read(at, size)
    assert len(requested) == before
