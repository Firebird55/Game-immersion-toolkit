"""Pure source-cache publication retains the previous complete file on failure."""
import errno
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import atomic_files


def test_pure_writer_replaces_complete_bytes_and_removes_staging(tmp_path):
    target = tmp_path / 'managed' / 'source'
    atomic_files.write_bytes(target, b'first complete source')
    atomic_files.write_bytes(target, b'next complete source')
    assert target.read_bytes() == b'next complete source'
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize('phase', ['write', 'replace'])
def test_interrupted_staging_or_publication_preserves_the_old_source(tmp_path, monkeypatch, phase):
    target = tmp_path / 'source'
    target.write_bytes(b'old complete source')
    if phase == 'replace':
        def failed(*args, **kwargs): raise OSError('Authored publication failure')
        monkeypatch.setattr(atomic_files, 'replace', failed)
    else:
        original = Path.write_bytes
        def failed(path, value):
            if path.name == 'download': raise OSError('Authored staging failure')
            return original(path, value)
        monkeypatch.setattr(Path, 'write_bytes', failed)
    with pytest.raises(OSError): atomic_files.write_bytes(target, b'new complete source')
    assert target.read_bytes() == b'old complete source'
    assert list(tmp_path.iterdir()) == [target]


def test_transient_windows_replace_does_not_expose_partial_bytes(tmp_path, monkeypatch):
    target = tmp_path / 'source'
    target.write_bytes(b'old complete source')
    actual, attempts = os.replace, []
    def blocked(source, destination):
        assert target.read_bytes() == b'old complete source'
        assert source.read_bytes() == b'new complete source'
        attempts.append(destination)
        if len(attempts) < 3:
            error = PermissionError(errno.EACCES, 'Authored Windows sharing conflict')
            error.winerror = 32
            raise error
        actual(source, destination)
    monkeypatch.setattr(atomic_files, 'os', SimpleNamespace(name='nt', replace=blocked))
    atomic_files.write_bytes(target, b'new complete source')
    assert len(attempts) == 3 and target.read_bytes() == b'new complete source'
    assert list(tmp_path.iterdir()) == [target]
