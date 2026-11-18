"""A concurrent winner must be identical, not merely present or equal-sized."""
import errno
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import wuthering_release_pak as pak
from backend import atomic_files


class Clock:
    now = 0
    def monotonic(self): return self.now
    def sleep(self, delay): self.now += delay


def sharing_error(winerror=None, error_number=errno.EACCES):
    error = PermissionError(error_number, 'Authored blocked index cache')
    if winerror is not None: error.winerror = winerror
    return error


@pytest.fixture
def windows_cache_clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(pak, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(atomic_files, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(pak, 'time', clock)
    monkeypatch.setattr(atomic_files, 'time', clock)
    return clock


def index_reader(tmp_path):
    package = object.__new__(pak.Package)
    package.cache = tmp_path / 'kuro-package-index' / ('a' * 40)
    package.cache.mkdir(parents=True)
    package._verify_original_indices, package._key = False, None
    data = b'complete original index'
    path = package.cache / hashlib.sha1(data).hexdigest()
    path.write_bytes(data)
    return package, path, data


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


@pytest.mark.parametrize('winerror', [None, 32])
@pytest.mark.parametrize('blocked_operation', ['stat', 'read_bytes'])
def test_temporarily_blocked_index_stat_or_read_recovers_without_source_io(
        tmp_path, monkeypatch, windows_cache_clock, winerror, blocked_operation):
    package, path, data = index_reader(tmp_path)
    original = getattr(Path, blocked_operation)
    failures = []
    def blocked(candidate, *args, **kwargs):
        if candidate == path and not failures:
            failures.append(sharing_error(winerror))
            raise failures[-1]
        return original(candidate, *args, **kwargs)
    monkeypatch.setattr(Path, blocked_operation, blocked)
    package.range = lambda *a: pytest.fail('A temporary sharing failure cannot force a source download')
    assert package.index(0, len(data), hashlib.sha1(data).digest()) == data
    assert len(failures) == 1 and 0 < windows_cache_clock.now <= 1


@pytest.mark.parametrize('winner', [b'truncated', b'complete original indeX'])
def test_recovered_reader_never_accepts_a_malformed_concurrent_winner(
        tmp_path, monkeypatch, windows_cache_clock, winner):
    package, path, data = index_reader(tmp_path)
    original = Path.read_bytes
    failures = []
    def replaced(candidate):
        if candidate == path and not failures:
            path.write_bytes(winner)
            failures.append(sharing_error())
            raise failures[-1]
        return original(candidate)
    monkeypatch.setattr(Path, 'read_bytes', replaced)
    # Neither a malformed local winner nor corrupt original bytes may publish.
    package.range = lambda *a: b'X' * len(data)
    monkeypatch.setattr(pak, '_publish_index', lambda *a: pytest.fail('Invalid index cannot publish'))
    with pytest.raises(ValueError, match='inconsistent'):
        package.index(0, len(data), hashlib.sha1(data).digest())
    assert original(path) == winner


@pytest.mark.parametrize('winerror', [None, 32])
def test_permanent_cache_read_permission_failure_is_bounded_and_propagates(
        tmp_path, monkeypatch, windows_cache_clock, winerror):
    package, path, data = index_reader(tmp_path)
    error, reads = sharing_error(winerror), []
    original = Path.read_bytes
    def denied(candidate):
        if candidate == path:
            reads.append(candidate)
            raise error
        return original(candidate)
    monkeypatch.setattr(Path, 'read_bytes', denied)
    package.range = lambda *a: pytest.fail('Persistent denied reads must remain actionable')
    with pytest.raises(PermissionError) as failure:
        package.index(0, len(data), hashlib.sha1(data).digest())
    assert failure.value is error and len(reads) > 1 and 1 <= windows_cache_clock.now < 1.03


@pytest.mark.parametrize('error', [PermissionError(errno.EPERM, 'Permanent permission policy'),
                                  OSError(errno.EIO, 'Disk failure'), sharing_error(1314)])
def test_unrelated_cache_read_errors_are_not_retried(
        tmp_path, monkeypatch, windows_cache_clock, error):
    package, path, data = index_reader(tmp_path)
    original = Path.read_bytes
    reads = []
    def denied(candidate):
        if candidate == path:
            reads.append(candidate)
            raise error
        return original(candidate)
    monkeypatch.setattr(Path, 'read_bytes', denied)
    with pytest.raises(type(error)) as failure:
        package.index(0, len(data), hashlib.sha1(data).digest())
    assert failure.value is error and len(reads) == 1 and windows_cache_clock.now == 0


def test_posix_eacces_does_not_gain_windows_cache_read_retries(tmp_path, monkeypatch, windows_cache_clock):
    monkeypatch.setattr(pak, 'os', SimpleNamespace(name='posix'))
    monkeypatch.setattr(atomic_files, 'os', SimpleNamespace(name='posix'))
    package, path, data = index_reader(tmp_path)
    original = Path.read_bytes
    reads = []
    def denied(candidate):
        if candidate == path:
            reads.append(candidate)
            raise sharing_error()
        return original(candidate)
    monkeypatch.setattr(Path, 'read_bytes', denied)
    with pytest.raises(PermissionError): package.index(0, len(data), hashlib.sha1(data).digest())
    assert len(reads) == 1 and windows_cache_clock.now == 0
