"""Immutable public-format cache races, using authored bytes only."""
import ctypes
import hashlib
import os

import pytest

from backend import nte_archive_metadata as metadata


def target(root, raw):
    return root / ('a' * 40 + '-' + hashlib.sha256(raw).hexdigest() + '.txt')


@pytest.mark.parametrize('competing', [b'owned metadata', b'wrong metadata'])
def test_competing_metadata_writer_is_accepted_only_when_complete_bytes_agree(tmp_path, monkeypatch, competing):
    raw = b'owned metadata'
    def publish(path, content):
        path.write_bytes(competing)
        raise PermissionError('owned competing writer')
    monkeypatch.setattr(metadata, '_atomic_file', publish)
    if competing == raw:
        metadata._cache_source(tmp_path, 'a' * 40, hashlib.sha256(raw).hexdigest(), raw)
    else:
        with pytest.raises(PermissionError):
            metadata._cache_source(tmp_path, 'a' * 40, hashlib.sha256(raw).hexdigest(), raw)
    assert target(tmp_path, raw).read_bytes() == competing


def test_verified_metadata_is_reused_and_corrupt_cache_is_repaired(tmp_path, monkeypatch):
    raw = b'owned immutable metadata';digest = hashlib.sha256(raw).hexdigest()
    metadata._cache_source(tmp_path, 'a' * 40, digest, raw)
    path = target(tmp_path, raw)
    original = metadata._atomic_file;calls = []
    def publish(*args):
        calls.append(args[0]);original(*args)
    monkeypatch.setattr(metadata, '_atomic_file', publish)
    metadata._cache_source(tmp_path, 'a' * 40, digest, raw)
    assert calls == []
    path.write_bytes(b'?' * len(raw))
    metadata._cache_source(tmp_path, 'a' * 40, digest, raw)
    assert calls == [path] and path.read_bytes() == raw


@pytest.mark.skipif(os.name != 'nt', reason='Windows file-sharing behavior')
def test_real_windows_reader_lock_allows_reusing_identical_metadata(tmp_path):
    from ctypes import wintypes
    raw = b'owned metadata under a real read-sharing lock'
    path = target(tmp_path, raw);path.write_bytes(raw)
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE];api.CloseHandle.restype = wintypes.BOOL
    handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    try:
        metadata._cache_source(tmp_path, 'a' * 40, hashlib.sha256(raw).hexdigest(), raw)
        assert path.read_bytes() == raw
    finally:
        assert api.CloseHandle(handle)
