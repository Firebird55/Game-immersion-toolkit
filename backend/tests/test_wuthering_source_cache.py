"""Normal text updates reuse only the same fully owned original recording."""
import copy
import hashlib
from types import SimpleNamespace

import pytest

from backend import wuthering_release as release, wuthering_source_cache as cache
from backend.tests.test_wuthering_key_stamp_cache import descriptor, cached


DEPOT = 'Client/Content/Aki/WwiseAudio_Generated/Media/en/123.wem'
REFERENCE = (('https://owned.aki-game.net/current/dub.pak', 2048, 'a' * 40), 9)
WEM = b'RIFF\x08\0\0\0WAVEfull'


def test_real_extraction_populates_owned_cache_and_changed_text_update_reuses_it(tmp_path, monkeypatch):
    first = descriptor(tmp_path, {'schema': 1, 'versions': {'resource': '3.8.11'}})
    second = descriptor(tmp_path, {'schema': 1, 'versions': {'resource': '3.8.12'}})
    calls = []
    monkeypatch.setattr(release, '_voice_package', lambda *args:
        SimpleNamespace(extract=lambda pos: calls.append((args[-1], pos)) or WEM))
    assert release._source_bytes(tmp_path, first, DEPOT, REFERENCE) == WEM
    before = release._descriptor_path(tmp_path, first).parent / 'clips' / hashlib.sha256(DEPOT.encode()).hexdigest()
    original = before.read_bytes()
    assert release._source_bytes(tmp_path, second, DEPOT, REFERENCE) == WEM
    assert len(calls) == 1
    assert before.read_bytes() == original
    assert release._cached_source(tmp_path, second, DEPOT) == WEM


@pytest.mark.parametrize('change', ['url', 'size', 'digest', 'position', 'dub', 'player', 'depot'])
def test_different_authored_owner_member_dub_and_player_cannot_reuse(tmp_path, change):
    cache.remember(tmp_path, DEPOT, REFERENCE, WEM)
    reference, depot = copy.deepcopy(REFERENCE), DEPOT
    url, size, digest = reference[0]
    position = reference[1]
    if change == 'url': url += '.new'
    elif change == 'size': size += 1
    elif change == 'digest': digest = 'b' * 40
    elif change == 'position': position += 1
    elif change == 'dub': depot = depot.replace('/en/', '/ja/')
    elif change == 'player': depot = depot.replace('123.wem', '123_F.wem')
    else: depot = depot.replace('123.wem', '124.wem')
    assert cache.cached(tmp_path, depot, ((url, size, digest), position)) is None


def test_incomplete_or_tombstoned_reference_never_reads_an_owned_recording(tmp_path, monkeypatch):
    cache.remember(tmp_path, DEPOT, REFERENCE, WEM)
    assert cache.cached(tmp_path, DEPOT, (REFERENCE[0], -2147483648)) is None
    assert cache.cached(tmp_path, DEPOT, None) is None
    assert cache.cached(tmp_path, DEPOT, (('unowned',), 9)) is None
    stamp = descriptor(tmp_path, {'schema': 1, 'versions': {'resource': 'changed'}})
    monkeypatch.setattr(release, '_voice_package', lambda *args: pytest.fail('No live reference means no extraction'))
    assert release._source_bytes(tmp_path, stamp, DEPOT) is None


@pytest.mark.parametrize('fault', ['data', 'identity', 'digest', 'truncated', 'header'])
def test_corrupt_owned_cache_never_publishes_a_new_snapshot_recording(tmp_path, fault):
    cache.remember(tmp_path, DEPOT, REFERENCE, WEM)
    path = next((tmp_path / 'wuwa-publisher/owned-sources').iterdir())
    value = bytearray(path.read_bytes())
    if fault == 'data': value[-1] ^= 1
    elif fault == 'identity': value[4] ^= 1
    elif fault == 'digest': value[36] ^= 1
    elif fault == 'header': value[0] ^= 1
    else: value = value[:50]
    path.write_bytes(value)
    assert cache.cached(tmp_path, DEPOT, REFERENCE) is None


def test_existing_ambient_snapshot_cache_does_not_gain_unproven_member_ownership(tmp_path, monkeypatch):
    first = descriptor(tmp_path, {'schema': 1, 'versions': {'resource': 'old'}})
    second = descriptor(tmp_path, {'schema': 1, 'versions': {'resource': 'new'}})
    previous = cached(tmp_path, first, DEPOT, WEM)
    original = previous.read_bytes()
    def failed(*args): raise OSError('Original download interrupted')
    monkeypatch.setattr(release, '_voice_package', failed)
    with pytest.raises(OSError, match='interrupted'):
        release._source_bytes(tmp_path, second, DEPOT, REFERENCE)
    assert previous.read_bytes() == original
    assert cache.cached(tmp_path, DEPOT, REFERENCE) is None
    assert release._cached_source(tmp_path, second, DEPOT) is None


def test_interrupted_owned_publication_preserves_prior_owned_and_snapshot_bytes(tmp_path, monkeypatch):
    cache.remember(tmp_path, DEPOT, REFERENCE, WEM)
    before = next((tmp_path / 'wuwa-publisher/owned-sources').iterdir()).read_bytes()
    def fail(*args): raise OSError('Atomic publication interrupted')
    monkeypatch.setattr(cache, '_atomic_file', fail)
    with pytest.raises(OSError, match='Atomic'):
        cache.remember(tmp_path, DEPOT, REFERENCE, b'RIFF\x08\0\0\0WAVEnew!')
    assert next((tmp_path / 'wuwa-publisher/owned-sources').iterdir()).read_bytes() == before
    assert cache.cached(tmp_path, DEPOT, REFERENCE) == WEM


def test_text_only_preparation_does_not_request_original_voice_or_owned_cache(tmp_path, monkeypatch):
    # The existing pure-text lane never calls either decoder-dependent stage.
    monkeypatch.setattr(release, '_movie_locations', lambda *args: pytest.fail('Text-only cannot resolve movie media'))
    monkeypatch.setattr(release, '_shared_locations', lambda *args: pytest.fail('Text-only cannot resolve song media'))
    monkeypatch.setattr(cache, 'cached', lambda *args: pytest.fail('Text-only cannot inspect audio'))
    monkeypatch.setattr(cache, 'remember', lambda *args: pytest.fail('Text-only cannot write audio'))
    release._movie_records(tmp_path, {}, 'unused', (), tmp_path, [], {}, 'en', None)
    release._movie_context_records(tmp_path, {}, 'unused', (), tmp_path, [], 'en', None)
    assert release._music_records(tmp_path, {}, 'unused', (), tmp_path, 'en', (), None) == []
