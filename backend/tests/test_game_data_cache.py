"""A live storage census tolerates deletion, without masking access/link errors."""
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from backend import atomic_files, game_data


@pytest.mark.parametrize('phase', ['directory', 'attributes'])
def test_census_rechecks_an_owned_entry_after_windows_pending_delete(tmp_path, monkeypatch, phase):
    cache = tmp_path / 'cache'; cache.mkdir()
    stable = cache / 'saved'; stable.write_bytes(b'retained original')
    transient = cache / 'planning'; transient.mkdir()
    leaf = transient / 'partial'; leaf.write_bytes(b'unfinished download')
    target = transient if phase == 'directory' else leaf
    operation = '_cache_entries' if phase == 'directory' else '_cache_attributes'
    actual = getattr(game_data, operation)
    attempts = []

    def deleting(path):
        if path == target:
            attempts.append(path)
            if len(attempts) == 1:
                if phase == 'directory': shutil.rmtree(transient)
                else: leaf.unlink()
                error = PermissionError('Authored Windows pending deletion')
                error.winerror = 5
                raise error
        return actual(path)

    monkeypatch.setattr(atomic_files, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(game_data, operation, deleting)
    assert game_data._size(cache) == len(b'retained original')
    assert len(attempts) == 2 and stable.read_bytes() == b'retained original'


@pytest.mark.parametrize('changed_link', [False, True])
def test_census_never_hides_persistent_denial_or_a_replaced_link(tmp_path, monkeypatch, changed_link):
    cache = tmp_path / 'cache'; cache.mkdir()
    actual_guard = game_data._no_links
    denied = PermissionError('Authored persistent access denial'); denied.winerror = 5
    attempts = []
    clock = iter((0, 0, 2))

    def guarded(path):
        if path == cache and attempts and changed_link:
            raise ValueError('Private data cannot follow filesystem links')
        actual_guard(path)

    def blocked(path):
        attempts.append(path)
        raise denied

    monkeypatch.setattr(atomic_files, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(atomic_files, 'time', SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None))
    monkeypatch.setattr(game_data, '_no_links', guarded)
    monkeypatch.setattr(Path, 'iterdir', blocked)
    with pytest.raises(ValueError if changed_link else PermissionError) as error:
        game_data._size(cache)
    if not changed_link:
        assert error.value is denied and len(attempts) == 2
    else:
        assert len(attempts) == 1
