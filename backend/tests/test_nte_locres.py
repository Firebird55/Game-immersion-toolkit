"""Original synthetic text, with no game strings or real format parameters."""
import base64
from collections import OrderedDict
import json
import struct

from Crypto.Cipher import AES
import pytest

from backend import nte_archive_metadata as metadata, nte_locres as locres
from backend.preparation_errors import PreparationFailure

KEY = bytes(range(32))


def string(text):
    raw = text.encode('utf-8') + b'\0'
    return struct.pack('<i', len(raw)) + raw


def resource(rows, encrypted=True):
    pool, groups = [], OrderedDict()
    for namespace, key, text, source_hash in rows:
        if text not in pool:
            pool.append(text)
        groups.setdefault(namespace, []).append((key, pool.index(text), source_hash))
    index = struct.pack('<II', len(rows), len(groups))
    for namespace, entries in groups.items():
        index += struct.pack('<I', 0) + string(namespace) + struct.pack('<I', len(entries))
        for key, slot, source_hash in entries:
            index += struct.pack('<I', 0) + string(key) + struct.pack('<Ii', source_hash, slot)
    header = locres.MAGIC + struct.pack('<Biiq', 3, 10100, int(encrypted), 33 + len(index))
    values = struct.pack('<i', len(pool))
    for text in pool:
        value = text
        if encrypted:
            raw = text.encode('utf-8') + b'HottaLocresSplit'
            raw = AES.new(KEY, AES.MODE_ECB).encrypt(raw.ljust((len(raw) + 15) // 16 * 16, b'\0'))
            value = base64.b64encode(raw).decode('ascii').replace('+', '-').replace('/', '_')
        values += string(value) + struct.pack('<i', sum(text == row[2] for row in rows))
    return header + index + values


@pytest.mark.parametrize('encrypted', [False, True])
def test_namespaces_original_keys_source_hashes_and_shared_strings_survive(encrypted):
    rows = [('story', 'spoken', 'Original fixture dialogue.', 100),
            ('story', 'choice', 'A written fixture choice.', 101),
            ('interface', 'choice', 'A written fixture choice.', 102),
            ('story', 'unicode', 'Synthetic \u4e2d\u6587 / \ud55c\uad6d\uc5b4 / caf\u00e9.', 103)]
    actual = locres.parse(resource(rows, encrypted), '0x' + KEY.hex() if encrypted else None)
    assert {(r['ns'], r['key']): (r['value'], r['source_hash']) for r in actual} == {
        (ns, key): (value, source_hash) for ns, key, value, source_hash in rows}
    assert len(actual) == len(rows)


@pytest.mark.parametrize('change', ['version', 'nte-version', 'offset', 'count', 'index', 'truncated', 'tail', 'duplicate'])
def test_unknown_or_inconsistent_layout_never_yields_a_partial_text_table(change):
    rows = [('story', 'spoken', 'Original fixture dialogue.', 0x12345678)]
    if change == 'duplicate':
        rows.append(rows[0])
    data = bytearray(resource(rows))
    if change == 'version':
        data[16] = 4
    elif change == 'nte-version':
        struct.pack_into('<i', data, 17, 10101)
    elif change == 'offset':
        struct.pack_into('<q', data, 25, -1)
    elif change == 'count':
        struct.pack_into('<I', data, 33, 2)
    elif change == 'index':
        at = data.index(struct.pack('<I', 0x12345678))
        struct.pack_into('<i', data, at + 4, 100)
    elif change == 'truncated':
        data.pop()
    elif change == 'tail':
        data.extend(b'unknown field')
    with pytest.raises(PreparationFailure) as failure:
        locres.parse(bytes(data), '0x' + KEY.hex())
    assert failure.value.code == 'unsupported_game_format'


def test_incompatible_format_candidate_is_distinct_from_a_new_resource_schema():
    for key in [None, '0x' + bytes(32).hex()]:
        with pytest.raises(PreparationFailure) as failure:
            locres.parse(resource([('story', 'spoken', 'Fixture.', 1)]), key)
        assert failure.value.code == 'game_metadata_unavailable'


def test_localization_metadata_refresh_and_historical_offline_lookup_are_data_only(tmp_path):
    state = {'revision': 'a' * 40, 'key': KEY}
    fetched = []
    def fetch(url, limit):
        assert limit == metadata.LIMIT
        fetched.append(url)
        if 'api.github' in url:
            return json.dumps([{'sha': state['revision']}]).encode()
        return b'data-only synthetic format candidate 0x' + state['key'].hex().encode()
    before = metadata.load_localization(fetch=fetch, cache=tmp_path)
    assert KEY.hex() not in repr(before)
    assert metadata.LOCALIZATION_PATH in fetched[-1]
    state.update(revision='c' * 40, key=bytes(32))
    after = metadata.load_localization(fetch=fetch, cache=tmp_path)
    assert before.revision != after.revision and before.digest != after.digest and before.parameter != after.parameter
    def offline(*_):
        pytest.fail('Cached historical format metadata must not contact an upstream source')
    assert metadata.load_localization(fetch=offline, cache=tmp_path, revision=before.revision, digest=before.digest) == before
    original = resource([('story', 'spoken', 'Fixture.', 1)])
    assert locres.parse(original, before.parameter)[0]['value'] == 'Fixture.'
    with pytest.raises(PreparationFailure):
        locres.parse(original, after.parameter)
    for raw in (b'no format candidate', b'0x' + KEY.hex().encode() + b' 0x' + KEY.hex().encode()):
        with pytest.raises(PreparationFailure):
            metadata.load_localization(fetch=lambda url, *_:
                json.dumps([{'sha': 'a' * 40}]).encode() if 'api.github' in url else raw)
