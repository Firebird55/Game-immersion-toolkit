import hashlib
import json
import struct

import pytest
import zstandard

from backend import genshin_publisher as publisher, sophon_assets as sophon
from backend.voice_assets import voice_hash


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append(128 | (value & 127))
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def fixture(directory, monkeypatch, version, speech):
    source = 'English(US)\\VO_AQ\\synthetic.wem'
    identity = voice_hash(source)
    wem = b'RIFF' + struct.pack('<I', 4 + len(speech)) + b'WAVE' + speech
    table = struct.pack('<I Q4I', 1, identity, 1, len(wem), 56, 0)
    package = b'AKPK' + struct.pack('<6I', 48, 1, 0, 0, 0, len(table)) + table + wem
    base = 'https://autopatchcn.yuanshen.com/test/' + version
    name = 'YuanShen_Data/StreamingAssets/AudioAssets/English(US)/1.pck'
    md5 = lambda data: hashlib.md5(data).hexdigest()
    def encode(data):
        return zstandard.ZstdCompressor(write_content_size=False).compress(data)
    objects = {}
    row = field(1, name.encode()) + field(4, len(package)) + field(5, md5(package).encode())
    for start, chunk in [(0, package[:60]), (60, package[60:])]:
        obj = '0' * 16 + '_' + md5(chunk)
        objects[base + '/' + obj] = encoded = encode(chunk)
        row += field(2, field(1, obj.encode()) + field(2, md5(chunk).encode()) +
                     field(3, start) + field(4, len(encoded)) + field(5, len(chunk)))
    raw = field(1, row)
    manifest_id = 'manifest_' + '0' * 16 + '_' + md5(raw)
    objects[base + '/' + manifest_id] = encoded = encode(raw)
    spec = (base, manifest_id, len(encoded), len(raw), md5(raw), base)
    build = {'channel': publisher.CHANNEL, 'version': version, 'manifests': {'en-us': spec}}
    stamp, descriptor = publisher._descriptor(build)
    sophon._atomic_file(directory / 'tools/sophon/releases' / stamp, descriptor)
    monkeypatch.setattr(sophon, 'download', lambda url, limit: objects[url])
    return source, identity, stamp, wem, objects


def test_new_build_changes_voice_and_old_cached_clip_survives_offline(tmp_path, monkeypatch):
    clips = []
    for version, speech in [('1.0.0', b'first synthetic clip'), ('1.1.0', b'second synthetic clip')]:
        source, identity, stamp, wem, objects = fixture(tmp_path, monkeypatch, version, speech)
        binding = publisher.inventory(tmp_path, stamp, 'en')[identity] | {
            'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
        assert publisher.extract(binding, tmp_path / 'tools') == wem
        clips.append((binding, wem))
    assert clips[0][0]['publisher'] != clips[1][0]['publisher']
    objects.clear()
    sophon.manifest.cache_clear()
    publisher._files.cache_clear()
    publisher._table.cache_clear()
    for binding, wem in clips:
        assert publisher.extract(binding, tmp_path / 'tools') == wem
        with pytest.raises(ValueError):
            publisher.extract(binding | {'locale': 'ja'}, tmp_path / 'tools')


def test_mismatched_or_truncated_chunk_cannot_replace_good_data(tmp_path, monkeypatch):
    source, identity, stamp, wem, objects = fixture(tmp_path, monkeypatch, '2.0.0', b'synthetic')
    binding = publisher.inventory(tmp_path, stamp, 'en')[identity] | {
        'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
    last = next(url for url in objects if not url.split('/')[-1].startswith('manifest_') and
                not (tmp_path / 'tools/sophon/chunks' / url.rsplit('_', 1)[1]).exists())
    objects[last] = objects[last][:-1]
    with pytest.raises(ValueError):
        publisher.extract(binding, tmp_path / 'tools')
    assert not (tmp_path / 'tools/sophon/chunks' / last.rsplit('_', 1)[1]).exists()


def test_catalog_requires_region_and_three_revision_markers(monkeypatch):
    sha = 'a' * 40
    rows = [{'title': 'CNRELWin1.2.0_R10_S20_D31', 'id': 'b' * 40},
            {'title': 'CNRELWin1.2.0_R10_S20_D30', 'id': sha}]
    monkeypatch.setattr(publisher, 'download', lambda *args, **kwargs: json.dumps(rows))
    assert publisher.matching_commit(rows[1]['title']) == sha
    with pytest.raises(publisher.PreparationFailure):
        publisher.matching_commit('OSRELWin1.2.0_R10_S20_D30')
