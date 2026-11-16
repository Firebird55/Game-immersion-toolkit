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
    key, name = 0xb42fa30808e62001, 'Reference_Caption.json'
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


def test_authored_caption_path_canonicalization():
    assert design.caption_resource_id('Config/CutSceneCaption/Reference_Caption.json') == 0xb42fa30808e62001
    assert design.caption_resource_id('Config/CutSceneCaption/New_Episode-2_Caption.json') == 0x54c6a61d50e11224
    for path in (None, '', '/Config/CutSceneCaption/A_Caption.json',
                 'Config/CutSceneCaption/../A_Caption.json', 'Config/CutSceneCaption//A_Caption.json',
                 'Config/CutSceneCaption/A_Caption.json/extra', 'Config/CutSceneCaption/A_Caption.json?x',
                 'Config/CutSceneCaption/A%2fB_Caption.json', 'Config\\CutSceneCaption\\A_Caption.json',
                 'C:/Config/CutSceneCaption/A_Caption.json', 'Config/CutSceneCaption/A\0_Caption.json'):
        with pytest.raises(ValueError):
            design.caption_resource_id(path)


def test_declared_resources_follow_normal_updates_and_preserve_unresolved_paths(tmp_path, monkeypatch):
    prefix = 'Config/CutSceneCaption/'
    known, declared, copied, next_name = ('Reference_Caption.json', 'New_Episode-2_Caption.json',
                                        'Other_Caption.json', 'Next_Update_Caption.json')
    anchor = caption(31, 2.25)
    published = {known: design._caption(anchor)}
    source = {}
    monkeypatch.setattr(design.hotfix, 'audio_roots', lambda build: ({'design': 'https://publisher/'}, {}))
    monkeypatch.setattr(design.hotfix, 'index', lambda *args: source['index'])
    monkeypatch.setattr(design.hotfix.AudioFile, 'read',
                        lambda asset, directory, start, length: source['bodies'][asset.digest][start:start + length])
    def release(groups, paths):
        parts = [package(group) for group in groups]
        source['index'] = struct.pack('>4I', 255, 4, len(parts), sum(len(group) for group in groups))
        source['index'] += b''.join(index[16:] for index, _ in parts)
        source['bodies'] = {hashlib.md5(body).hexdigest(): body for _, body in parts}
        identities, unresolved = {}, []
        extras = design.extra_captions(tmp_path, {}, published, paths,
                                       identities=identities, unresolved=unresolved)
        return extras, identities, unresolved
    known_group = [(7, caption(69, 1.5)), (0xb42fa30808e62001, anchor)]
    new_group = [(0x54c6a61d50e11224, caption(69, 1.5)), (0x052d95c54d5fb49e, anchor)]
    missing, wrong = prefix + 'NotShipped_Caption.json', prefix + 'WrongBody_Caption.json'
    paths = [prefix + declared, prefix + copied, missing, wrong]
    new_group.append((design.caption_resource_id(wrong), b'another resource format'))
    extras, identities, unresolved = release([known_group, new_group], paths)
    # Separate authenticated paths retain separate scene identities even when
    # the complete captions are equal. No shared text invents a movie binding.
    assert extras == {declared: design._caption(caption(69, 1.5)), copied: design._caption(anchor)}
    assert identities == {declared: 'design_54c6a61d50e11224', copied: 'design_052d95c54d5fb49e'}
    assert unresolved == sorted([missing, wrong])
    updated = release([[(2, b'padding' * 10000), *new_group, (0xbe61d4f44e067fec, caption(71, 2.5))],
                       known_group], [*paths, prefix + next_name])
    assert updated[0][next_name] == design._caption(caption(71, 2.5))
    assert updated[1][declared] == identities[declared] and updated[2] == unresolved
    empty_path = prefix + 'Empty_Caption.json'
    empty, _, unresolved_empty = release(
        [known_group, [(design.caption_resource_id(empty_path), b'\x01\x00')]], [empty_path])
    assert empty['Empty_Caption.json'] == {'CaptionList': []} and not unresolved_empty
    # Empty payloads are usable only through an explicit authored caption path;
    # they cannot identify neighboring data or independently prove a generation.
    assert design._caption(b'\x01\x00') is None
    # An additional correct reference cannot rescue a conflicting source
    # generation, and duplicate indexed paths cannot choose a package.
    published[copied] = design._caption(anchor)
    with pytest.raises(ValueError):
        release([known_group, [(0x052d95c54d5fb49e, caption(31, 99))]], paths)
    with pytest.raises(ValueError):
        release([known_group, known_group], paths)
    monkeypatch.setattr(design, 'xxhash64', lambda raw: 1)
    with pytest.raises(ValueError):
        release([known_group], paths)


def test_neighbor_caption_cannot_skip_second_published_generation_reference(tmp_path, monkeypatch):
    reference, second = caption(31, 2.25), caption(69, 1.5)
    published = {'Reference_Caption.json': design._caption(reference),
                 'Other_Caption.json': design._caption(second)}
    source = {}
    monkeypatch.setattr(design.hotfix, 'audio_roots', lambda build: ({'design': 'https://publisher/'}, {}))
    monkeypatch.setattr(design.hotfix, 'index', lambda *args: source['index'])
    monkeypatch.setattr(design.hotfix.AudioFile, 'read',
                        lambda asset, directory, start, length: source['blob'][start:start + length])
    def release(other):
        source['index'], source['blob'] = package([(0xb42fa30808e62001, reference),
                                                  (0x052d95c54d5fb49e, other)])
        return design.extra_captions(tmp_path, {}, published)
    assert release(second) == {}
    # The neighbor walk reaches this published anchor before its own loop.
    # Its clock mismatch must fail even after the first reference matched.
    with pytest.raises(ValueError):
        release(caption(69, 99))


def test_design_rejects_incomplete_indexes_and_invalid_caption_clocks():
    index, _ = package([(4, caption(1, 1.))])
    for raw in (index[:-1], index + b'x', index[:12] + b'\0\0\0\2' + index[16:],
                package([(4, b'one'), (4, b'two')])[0]):
        with pytest.raises(ValueError):
            list(design._packages(raw))
    for raw in (caption(1, float('nan')), caption(1, 0.), caption(1, .25, 13),
                caption(1, 1.) + b'x', caption(1, 1.)[:-1], b'\x01\x82\x00\x09\x01\x02'):
        assert design._caption(raw) is None
