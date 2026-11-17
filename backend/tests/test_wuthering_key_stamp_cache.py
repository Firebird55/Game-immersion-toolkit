"""Metadata-only key discovery must not redownload identical original recordings."""
import hashlib
import json

import pytest

from backend import wuthering_release as release


DEPOT = 'Client/Content/Aki/WwiseAudio_Generated/Media/en/123.wem'
WEM = b'RIFF\x06\0\0\0WAVEok'


def descriptor(tools, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    stamp = 'wuwa-' + hashlib.sha256(raw).hexdigest()
    path = release._descriptor_path(tools, stamp)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    return stamp


def cached(tools, stamp, depot=DEPOT, data=WEM):
    binding = hashlib.sha256((stamp + '/' + depot).encode()).digest()
    path = release._descriptor_path(tools, stamp).parent/'clips'/hashlib.sha256(depot.encode()).hexdigest()
    path.parent.mkdir(parents=True)
    path.write_bytes(hashlib.sha256(binding + data).digest() + data)
    return path


@pytest.fixture
def catalogues(tmp_path, monkeypatch):
    old = {'schema': 1, 'base': {'base.pak': [1024, 'a' * 32]}, 'root': 'https://owned/release',
        'products': {'en/PatchFiles/dub.pak': ['https://owned/dub.pak', 2048, 'b' * 40]},
        'versions': {'en': '3.8.5'}, 'launcher': '3.8.0'}
    new = {**old, 'native_key_sources': [{'role': 'resource', 'sha256': 'c' * 64}]}
    first = descriptor(tmp_path, old)
    previous = cached(tmp_path, first)
    def no_media(*args, **kwargs):
        pytest.fail('Key-metadata-only transition must not request original media')
    monkeypatch.setattr(release, '_voice_package', no_media)
    return old, new, first, previous


def test_native_input_stamp_change_reuses_only_full_hash_validated_same_catalogue(tmp_path, catalogues):
    _, new, first, previous = catalogues
    stamp = descriptor(tmp_path, new)
    before = previous.read_bytes()
    assert release._source_bytes(tmp_path, stamp, DEPOT, ('would-download', 0)) == WEM
    assert previous.read_bytes() == before
    assert release._cached_source(tmp_path, stamp, DEPOT) == WEM
    assert stamp != first
    # An offline playback miss can make the same bounded local migration.
    later = descriptor(tmp_path, {**new, 'native_key_sources': [{'sha256': 'd' * 64}]})
    assert release._source_bytes(tmp_path, later, DEPOT) == WEM


@pytest.mark.parametrize('changed', ['base', 'products', 'versions', 'region', 'root', 'launcher',
                                   'depot', 'recording-hash', 'old-descriptor-hash'])
def test_changed_authority_locale_or_recording_does_not_borrow_an_old_source(tmp_path, catalogues, changed):
    _, new, first, previous = catalogues
    depot = DEPOT
    if changed in ('base', 'products', 'versions'):
        new[changed] = {}
    elif changed == 'region': new['region'] = 'cn'
    elif changed == 'root': new['root'] += '/other'
    elif changed == 'launcher': new['launcher'] = '3.9.0'
    elif changed == 'depot': depot = DEPOT.replace('/en/', '/ja/')
    elif changed == 'recording-hash': previous.write_bytes(previous.read_bytes()[:-1] + b'x')
    else: release._descriptor_path(tmp_path, first).write_bytes(b'{}')
    stamp = descriptor(tmp_path, new)
    assert release._source_bytes(tmp_path, stamp, depot) is None


def test_interrupted_local_rebinding_preserves_all_prior_recording_bytes(tmp_path, catalogues, monkeypatch):
    _, new, _, previous = catalogues
    stamp = descriptor(tmp_path, new)
    before = previous.read_bytes()
    def interrupted(*args): raise OSError('Owned local cache publication interruption')
    monkeypatch.setattr(release, '_atomic_file', interrupted)
    with pytest.raises(OSError, match='publication'):
        release._source_bytes(tmp_path, stamp, DEPOT)
    assert previous.read_bytes() == before
    assert release._cached_source(tmp_path, stamp, DEPOT) is None
