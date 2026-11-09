import hashlib
import json
import struct
from types import SimpleNamespace

import brotli
import pytest

from backend import endfield_release as publisher, endfield_tables
from backend import endfield_film_registry as registry, endfield_film_sources as sources, endfield_global_1_6 as profile


def text_table(name, key, value):
    root = bytes([endfield_tables.MAP]) + name.encode() + bytes([0, endfield_tables.LONG, endfield_tables.STRING])
    string_pos = 16 + len(root)
    string = value.encode() + b'\0'
    data_pos = (string_pos + len(string) + 7) // 8 * 8
    header = struct.pack('<4i', 12, 16, data_pos, 0)
    # Count and lookup bucket precede the aligned int64 key.
    return (header + root + string).ljust(data_pos, b'\0') + struct.pack('<i12xqi', 1, key, string_pos)


def test_owned_sparkbuffer_reads_exact_name_signed_key_and_utf8():
    raw = text_table('I18nTextTable_EN', -120, 'Quoted ☀')
    assert endfield_tables.read(raw, 'I18nTextTable_EN') == {'-120': 'Quoted ☀'}
    with pytest.raises(ValueError):
        endfield_tables.read(raw, 'I18nTextTable_JP')
    with pytest.raises(ValueError):
        endfield_tables.read(raw[:-4] + struct.pack('<i', len(raw)), 'I18nTextTable_EN')


def test_released_generation_follows_both_layers_and_preserves_old_descriptor(tmp_path, monkeypatch):
    version = '1.0.3'
    current = {'initial': b'a' * 40, 'main': b'b' * 40}
    def fetch(url, **_limits):
        if url == publisher.LATEST:
            return json.dumps({'version': version, 'pkg': {'packs': [
                {'url': publisher.CDN + '/1.0/update/6/6/Windows/1.0.3_test/packs/a.zip'}]}})
        if 'get_latest_resources?' in url:
            assert 'rand_str=test' in url
            return json.dumps({'resources': [{'name': role, 'version': '123-1', 'path':
                publisher.CDN + '/1.0/resource/Windows/' + role + '/123-1_test/files'} for role in current]})
        return current[url.rsplit('index_', 1)[1].split('.')[0]]
    monkeypatch.setattr(publisher, 'download', fetch)
    first, data = publisher.discover()
    publisher._atomic_file(tmp_path / 'endfield-releases' / first, data)
    current['initial'] += b'x'
    second, raw = publisher.discover()
    assert second != first
    assert publisher.descriptor(tmp_path, first)['layers']['initial']['sha256'] == hashlib.sha256(b'a' * 40).hexdigest()
    assert json.loads(raw)['layers']['initial']['sha256'] == hashlib.sha256(current['initial']).hexdigest()
    with pytest.raises(ValueError):
        publisher._resource_url('https://example.org/file', 'main')


def test_regional_timeline_profile_requires_both_publisher_indexes(tmp_path, monkeypatch):
    catalog = object.__new__(publisher.Catalog)
    catalog.tools, catalog.stamp = tmp_path, 'fixture'
    layers = {role: {'sha256': digest} for role, digest in publisher.FILM_MANIFESTS.items()}
    monkeypatch.setattr(publisher, 'descriptor', lambda *_: {'layers': layers})
    assert catalog.has_verified_clocks()
    layers['main'] = {'sha256': '0' * 64}
    assert not catalog.has_verified_clocks()


def test_cinematic_registry_selects_full_asset_path_and_bounds_decompression():
    def field(data):
        return struct.pack('<i', len(data)) + data

    path = 'assets/beyond/test.playable'
    name = 'main/abc123.ab'
    first = field(brotli.compress(path.encode('utf-16le')))
    assets = bytes(4) + struct.pack('<qii8x', 27, 0, 11)
    bundles = struct.pack('<iii40x', 1, 11, len(first))
    strings = first + field(name.encode('utf-16le'))
    data = bytes.fromhex('11ff11ff00000000f4f3f2f1') + bytes(8)
    data += field(assets) + field(b'') + field(bundles) + field(strings)
    assert registry.bindings(data, path_hashes={27}) == [(27, path, name)]
    assert registry.bindings(data, bundle_indices={11}) == [(27, path, name)]
    assert registry.bindings(data, path_hashes={11}) == []
    with pytest.raises(ValueError):
        registry.bindings(data[:-1], path_hashes={27})
    with pytest.raises(ValueError):
        registry.inflate(brotli.compress(bytes(65536)), 1024)


def test_carry_forward_requires_current_clock_bank_and_recording(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher, 'descriptor', lambda *_: {'layers': {k: {'sha256': 'changed'} for k in publisher.FILM_MANIFESTS}})
    bank = 'default_english_banks.pck'
    monkeypatch.setattr(sources, 'BANKS', {bank: 'original'})
    row = SimpleNamespace(name=bank, content_hashes=('', 'original'))
    monkeypatch.setattr(publisher, 'group', lambda _tools, _stamp, block: ('', [] if block == 21 else [row]))
    monkeypatch.setattr(profile, 'FILMS', {k: (None, (i, str(i)), None, None)
                                          for i, k in enumerate(('same', 'retimed', 'new_voice'))})
    assets = {'singleconfigs/' + k + '.asset' for k in profile.FILMS}
    assets.update({'same_others_au_en.playable', 'new_voice_others_au_en.playable'})
    monkeypatch.setattr(publisher, '_unchanged_film_assets', lambda *_: assets)
    def media(_tools, _stamp, dub, identity, digest):
        assert dub == 'english' and digest == str(identity)
        if identity == 2:
            raise publisher.UnmatchedRecording()
        assert identity == 0
    monkeypatch.setattr(publisher, 'media', media)
    assert publisher.verified_films(tmp_path, 'first', 'english') == {'same'}
    row.content_hashes = ('', 'new bank')
    assert publisher.verified_films(tmp_path, 'next', 'english') == set()
