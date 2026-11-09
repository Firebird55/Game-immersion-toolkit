import hashlib
import json
import struct

import pytest

from backend import endfield_release as publisher, endfield_tables


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
