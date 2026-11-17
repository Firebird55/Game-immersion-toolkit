"""A concurrent winner must be identical, not merely present or equal-sized."""
import pytest

from backend import wuthering_release_pak as pak


def test_identical_complete_concurrent_index_winner_satisfies_publication(tmp_path, monkeypatch):
    path = tmp_path / 'index'
    data = b'complete originally hash-verified index'
    def racing(destination, value):
        assert value == data
        destination.write_bytes(value)
        raise PermissionError('Another verified reader holds the winning file')
    monkeypatch.setattr(pak, '_atomic_file', racing)
    pak._publish_index(path, data)
    assert path.read_bytes() == data


@pytest.mark.parametrize('winner', [None, b'complete originally hash-verified indeX', b'truncated'])
def test_absent_corrupt_or_truncated_concurrent_winner_is_not_accepted(tmp_path, monkeypatch, winner):
    path = tmp_path / 'index'
    if winner is not None:
        path.write_bytes(winner)
    def denied(*args): raise PermissionError('Publication unavailable')
    monkeypatch.setattr(pak, '_atomic_file', denied)
    monkeypatch.setattr(pak, 'sharing_retry', lambda operation: operation())
    with pytest.raises(PermissionError):
        pak._publish_index(path, b'complete originally hash-verified index')
    assert (path.read_bytes() if path.exists() else None) == winner


def test_unrelated_io_failure_keeps_existing_index(tmp_path, monkeypatch):
    path = tmp_path / 'index'
    path.write_bytes(b'previous verified index')
    def interrupted(*args): raise OSError('Original index publication interrupted')
    monkeypatch.setattr(pak, '_atomic_file', interrupted)
    with pytest.raises(OSError, match='interrupted'):
        pak._publish_index(path, b'new verified index')
    assert path.read_bytes() == b'previous verified index'
