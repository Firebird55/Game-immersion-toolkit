"""Type metadata follows compatible game updates without changing toolkit code."""
import hashlib
import json
import struct

import pytest

from backend import nte_type_metadata as types
from backend.preparation_errors import PreparationFailure


def listing(rows):
    return json.dumps({'game': 'HT-NTE_UE5_6', 'mapping': [
        {'url': 'https://github.com/555me/NTE-usmap/raw/refs/heads/main/mapping/' + name,
         'name': name, 'versionInfo': version} for name, version in rows]}).encode()


def schema(data=b'independently authored schema'):
    return b'\xc4\x30\x04' + bytes(5) + struct.pack('<II', len(data), len(data)) + data


def test_version_selection_is_immutable_offline_and_adopts_new_type_data(tmp_path):
    index = listing([('HT-1.4-143.usmap', '1.4-1.4.3'), ('HT-1.5-153.usmap', '1.5-1.5.3'),
                     ('HT-1.6-161.usmap', '1.6-1.6.1')])
    revision = ['a' * 40]
    payload = [schema()]
    requests = []
    def fetch(url, limit):
        requests.append(url)
        if 'api.github.com' in url:
            return json.dumps([{'sha': revision[0]}]).encode()
        if url.endswith('/index.json'):
            return index
        assert url.endswith('/mapping/HT-1.5-153.usmap') and '/refs/heads/' not in url
        return payload[0]
    first = types.load('1.5.6', tmp_path, fetch=fetch)
    assert first.reference['path'] == 'mapping/HT-1.5-153.usmap'
    assert first.reference['sha256'] == hashlib.sha256(first.data).hexdigest()
    assert first.reference['revision'] == 'a' * 40
    def offline(*_):
        pytest.fail('Immutable cached type data contacted the network')
    assert types.load('1.5.6', tmp_path, reference=first.reference, fetch=offline) == first
    revision[0] = 'b' * 40
    payload[0] = schema(b'new compatible fields')
    second = types.load('1.5.6', tmp_path, fetch=fetch)
    assert second.reference['sha256'] != first.reference['sha256']
    assert types.load('1.5.6', tmp_path, reference=first.reference, fetch=offline) == first
    (tmp_path / (first.reference['sha256'] + '.usmap')).write_bytes(b'bad cached schema')
    with pytest.raises(PreparationFailure):
        types.load('1.5.6', tmp_path, reference=first.reference, fetch=fetch)
    assert all('/' + 'a' * 40 + '/' in u for u in requests[-1:] if 'api.github.com' not in u)


@pytest.mark.parametrize('change', ['external-url', 'future-only', 'duplicate-version', 'wrong-game', 'bad-header'])
def test_unusable_type_metadata_does_not_select_an_arbitrary_schema(tmp_path, change):
    rows = [('HT-1.5-153.usmap', '1.5-1.5.3')]
    if change == 'future-only':
        rows = [('HT-1.6-161.usmap', '1.6-1.6.1')]
    if change == 'duplicate-version':
        rows.append(('HT-1.5-154.usmap', '1.5-1.5.3'))
    index = json.loads(listing(rows))
    if change == 'external-url':
        index['mapping'][0]['url'] = 'https://other.example/schema.usmap'
    if change == 'wrong-game':
        index['game'] = 'unrelated-game'
    def fetch(url, limit):
        if 'api.github.com' in url:
            return json.dumps([{'sha': 'a' * 40}]).encode()
        if url.endswith('/index.json'):
            return json.dumps(index).encode()
        return b'wrong schema header' if change == 'bad-header' else schema()
    with pytest.raises(PreparationFailure):
        types.load('1.5.6', tmp_path, fetch=fetch)


@pytest.mark.parametrize('change', ['version', 'flag', 'method', 'truncated', 'expansion', 'uncompressed-size'])
def test_type_profile_cannot_request_unbounded_or_inconsistent_native_expansion(change):
    data = bytearray(schema())
    if change == 'version':
        data[2] = 255
    elif change == 'flag':
        data[3] = 2
    elif change == 'method':
        data[7] = 255
    elif change == 'truncated':
        data = data[:-1]
    elif change == 'expansion':
        struct.pack_into('<I', data, 12, 2**31)
    else:
        struct.pack_into('<I', data, 12, 1)
    with pytest.raises(PreparationFailure):
        types.validate(bytes(data))
