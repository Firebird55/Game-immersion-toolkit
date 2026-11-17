"""Text key fallback accepts complete original members, never partial parsing."""
import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from backend import nte_archive_metadata as metadata, nte_community_metadata as community
from backend import nte_locres as locres
from backend.nte_localization_keys import LocalizationKeys
from backend.preparation_errors import PreparationFailure
from backend.tests import test_nte_locres as fixtures


def fixture(tmp_path, monkeypatch):
    cache = tmp_path/'nte-publisher'
    def source(key): return b'data-only key 0x'+key.hex().encode()
    raw = source(bytes(32)); digest = hashlib.sha256(raw).hexdigest()
    metadata.load_localization(revision='a'*40, digest=digest, cache=cache/'format', fetch=lambda *_: raw)
    original = {'region': 'nte-global', 'branch': 'PC_150', 'version': '1.5.4', 'sha256': 'c'*64}
    catalog = SimpleNamespace(cache=cache, region='nte-global',
        keyring=SimpleNamespace(original=original, allow_community_fallback=True),
        snapshot={'localization': ['a'*40, digest], 'files': {'owned.pak': {'digest': 'b'*32}}},
        location=lambda path: ('owned.pak', None, path))
    requests = []
    def fetch(url, limit):
        requests.append(url)
        if 'api.github.com/' in url: return json.dumps([{'sha': 'b'*40}]).encode()
        return source(fixtures.KEY)
    monkeypatch.setattr(community, 'download', fetch)
    return catalog, requests


def test_rotated_key_requires_complete_original_and_reuses_pinned_description(tmp_path, monkeypatch):
    catalog, requests = fixture(tmp_path, monkeypatch)
    path = 'HT/Content/Localization/Game/en/Game.locres'
    data = fixtures.resource([('Owned', 'One', 'Original words.', 123)])
    keys = LocalizationKeys(catalog)
    assert keys.parse(path, data)[0]['value'] == 'Original words.'
    assert len(requests) == 2
    binding = keys.bindings[path]
    proof = community.check_receipt(binding['metadata'], catalog.keyring.original, keys.cache)
    assert proof['verification'] == {'kind': 'localization', 'sha256': hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Retained candidate refreshed latest'))
    assert LocalizationKeys(catalog).parse(path, data)[0]['value'] == 'Original words.'


@pytest.mark.parametrize('change', ['schema', 'index', 'tail'])
def test_unsupported_or_incomplete_original_is_not_a_key_rotation(tmp_path, monkeypatch, change):
    catalog, requests = fixture(tmp_path, monkeypatch)
    data = bytearray(fixtures.resource([('Owned', 'One', 'Original words.', 123)]))
    if change == 'schema': data[16] = 4
    if change == 'index': struct.pack_into('<i', data, data.index(struct.pack('<I', 123))+4, 999)
    if change == 'tail': data.extend(b'unknown format')
    keys = LocalizationKeys(catalog)
    with pytest.raises(PreparationFailure) as error: keys.parse('owned', bytes(data))
    assert error.value.code == 'unsupported_game_format'
    assert requests == [] and not keys.bindings


def test_healthy_primary_does_not_query_latest(tmp_path, monkeypatch):
    catalog, requests = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(fixtures, 'KEY', bytes(32))
    keys = LocalizationKeys(catalog)
    assert keys.parse('owned', fixtures.resource([('Owned', 'One', 'Original words.', 123)]))
    assert requests == []


def test_plaintext_original_never_proves_an_unused_key(tmp_path, monkeypatch):
    catalog, requests = fixture(tmp_path, monkeypatch)
    keys = LocalizationKeys(catalog)
    assert keys.parse('owned', fixtures.resource([('Owned', 'One', 'Original words.', 123)], encrypted=False))
    assert requests == [] and keys.bindings['owned']['metadata'] is None
    assert keys.bindings['owned']['key_required'] is False


def test_default_rotation_requires_official_first_admission_before_community(tmp_path, monkeypatch):
    catalog, requests = fixture(tmp_path, monkeypatch)
    catalog.keyring.allow_community_fallback = False
    keys = LocalizationKeys(catalog)
    with pytest.raises(locres.LocalizationParameterMismatch):
        keys.parse('owned', fixtures.resource([('Owned', 'One', 'Original words.', 123)]))
    assert requests == [] and not keys.bindings
