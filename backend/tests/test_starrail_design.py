"""Validate release-indexed caption discovery across repacked design resources."""
import hashlib
import struct

import pytest

from backend import starrail_design as design


def caption(text, end, mask=9):
    raw = bytes((1, 2, mask, 17, text))
    if mask & 2:
        raw += b'\x02'
    if mask & 4:
        raw += struct.pack('<f', .5)
    raw += struct.pack('<f', end)
    if mask & 16:
        raw += struct.pack('<f', .25)
    if mask & 32:
        raw += struct.pack('<f', .125)
    return raw


def package(rows):
    members, blob = bytearray(), bytearray()
    for key, raw in rows:
        members.extend(struct.pack('>QII', key, len(raw), len(blob)))
        blob.extend(raw)
    digest = hashlib.md5(blob).digest()
    directory = struct.pack('>4I', 255, 4, 1, len(rows))
    directory += struct.pack('>Q16sQI', rows[0][0], digest, len(blob), len(rows))
    return directory + members + b'\x00\x02AB\x80', bytes(blob)


def test_repacked_caption_group_with_unknown_names_remains_separate_from_movies(tmp_path, monkeypatch):
    key, name = next(iter(design.CAPTION_ANCHORS.items()))
    anchor = caption(31, 2.25)
    published = {name: design._caption(anchor)}
    rows = [(5, caption(67, 1)), (6, b'other data'), (key, anchor),
            (7, caption(69, 1, 63)), (8, anchor), (9, b'next schema'), (10, caption(70, 1))]
    source = {}
    monkeypatch.setattr(design.hotfix, 'audio_roots', lambda build: ({'design': 'https://publisher/'}, {}))
    monkeypatch.setattr(design.hotfix, 'index', lambda directory, build, kind: source['index'])
    def read(asset, directory, start, length):
        assert asset.url == 'https://publisher/' + hashlib.md5(source['blob']).hexdigest() + '.bytes'
        return source['blob'][start:start + length]
    monkeypatch.setattr(design.hotfix.AudioFile, 'read', read)
    def release(items):
        source['index'], source['blob'] = package(items)
        return design.extra_captions(tmp_path, {}, published)
    assert release(rows) == {'design_0000000000000007_Caption.json': {'CaptionList': [
        {'CaptionTextID': {'Hash': 69}, 'StartTime': .5, 'EndTime': 1., 'EaseIn': .25, 'EaseOut': .125}]}}
    updated = release([(12, b'new header' * 9000), *rows[:4], (13, caption(71, 1.5)), *rows[4:]])
    assert len(updated) == 2 and updated['design_000000000000000d_Caption.json'] == design._caption(caption(71, 1.5))
    with pytest.raises(ValueError):
        release([(key, caption(31, 99))])


def test_design_rejects_incomplete_indexes_and_invalid_caption_clocks():
    index, _ = package([(4, caption(1, 1.))])
    for raw in (index[:-1], index + b'x', index[:12] + b'\0\0\0\2' + index[16:],
                package([(4, b'one'), (4, b'two')])[0]):
        with pytest.raises(ValueError):
            list(design._packages(raw))
    for raw in (caption(1, float('nan')), caption(1, 0.), caption(1, .25, 13),
                caption(1, 1.) + b'x', caption(1, 1.)[:-1], b'\x01\x82\x00\x09\x01\x02'):
        assert design._caption(raw) is None
