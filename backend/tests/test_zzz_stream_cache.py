"""Whole-source streaming verification with checked cached byte ranges."""
import ctypes
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import zzz_hotfix as live
from backend.xxhash64 import xxhash64


URL = 'https://autopatchos.zenlesszonezero.com/game_res/9.0_live/output_2000_abcdef/client/StandaloneWindows64/oversea/Audio/Windows/Full/Jp/Patch.pck'


class Response(io.BytesIO):
    def __init__(self, raw, fragment=None):
        super().__init__(raw)
        self.requests, self.fragment = [], fragment

    def read(self, size=-1):
        assert 0 < size <= live.VERIFY_BLOCK_SIZE
        self.requests.append(size)
        return super().read(min(size, self.fragment) if self.fragment else size)


def file(raw):
    return live.File(live.PERSISTENT + 'Audio/Windows/Full/Jp/Patch.pck', len(raw), xxhash64(raw), URL)


def cache_path(root, asset):
    return root / 'zzz-files' / f'{asset.digest:016x}-{asset.size}'


@pytest.fixture(autouse=True)
def small_blocks(monkeypatch):
    monkeypatch.setattr(live, 'VERIFY_BLOCK_SIZE', 17)
    live._verified_file.cache_clear()
    yield
    live._verified_file.cache_clear()


def test_package_larger_than_metadata_limit_streams_and_reopens_offline_without_whole_reads(tmp_path, monkeypatch):
    raw = bytes(range(256)) * 3
    monkeypatch.setattr(live, 'MAX_FILE', 32)
    monkeypatch.setattr(live, 'MAX_STREAM_FILE', 1024)
    build = {'version': '9.0.0', 'hotfix': {'roots': {'resource': URL.split('Audio/')[0]}}}
    row = {'remoteName': 'Audio/Windows/Full/Jp/Patch.pck', 'fileSize': len(raw),
           'md5': str(xxhash64(raw)), 'isPatch': True}
    asset = live.resource(build, row)
    response = Response(raw, fragment=3)
    monkeypatch.setattr(live, '_stream_response', lambda *_: response)
    monkeypatch.setattr(Path, 'read_bytes', lambda *_: pytest.fail('whole source retained in memory'))
    assert asset.read(tmp_path, 19, 80) == raw[19:99]
    assert max(response.requests) == 17 and response.closed
    assert cache_path(tmp_path, asset).stat().st_size == len(raw)
    live._verified_file.cache_clear()
    monkeypatch.setattr(live, '_stream_response', lambda *_: pytest.fail('network used after reopen'))
    assert asset.read(tmp_path, 90, 89) == raw[90:179]
    # Large voice packages do not enlarge the full-decoding metadata bound.
    with pytest.raises(ValueError):
        live.resource(build, {**row, 'remoteName': 'Blocks/3.blk'})
    with pytest.raises(ValueError):
        live.resource(build, {**row, 'fileSize': 1025})


def test_preserved_size_and_mtime_tampering_cannot_supply_changed_range_bytes(tmp_path, monkeypatch):
    raw = bytes(range(128))
    asset = file(raw)
    monkeypatch.setattr(live, '_stream_response', lambda *_: Response(raw))
    assert asset.read(tmp_path, 0, 3) == raw[:3]
    path = cache_path(tmp_path, asset)
    before = path.stat()
    with path.open('r+b') as handle:
        handle.seek(37)
        handle.write(b'x')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
    def offline(*_):
        raise OSError('owned offline source')
    monkeypatch.setattr(live, '_stream_response', offline)
    assert asset.read(tmp_path, 0, 3) == raw[:3]
    with pytest.raises(OSError, match='offline'):
        asset.read(tmp_path, 35, 7)
    live._verified_file.cache_clear()
    with pytest.raises(OSError, match='offline'):
        asset.read(tmp_path, 0, 3)


@pytest.mark.parametrize('failure', ['truncated', 'overlong', 'wrong-hash', 'interrupted'])
def test_failed_stream_never_replaces_existing_cache_or_leaves_partial_files(tmp_path, monkeypatch, failure):
    raw = bytes(range(96))
    asset = file(raw)
    path = cache_path(tmp_path, asset)
    path.parent.mkdir()
    path.write_bytes(b'preserve previous cache bytes')
    payload = {'truncated': raw[:-1], 'overlong': raw + b'x', 'wrong-hash': b'x' * len(raw), 'interrupted': raw}[failure]
    class Interrupted(Response):
        def read(self, size=-1):
            if self.tell() >= 17:
                raise ConnectionResetError('owned interrupted transfer')
            return super().read(size)
    response = Interrupted(payload) if failure == 'interrupted' else Response(payload)
    monkeypatch.setattr(live, '_stream_response', lambda *_: response)
    with pytest.raises((ValueError, ConnectionResetError)):
        asset.read(tmp_path, 0, 5)
    assert path.read_bytes() == b'preserve previous cache bytes'
    assert list(path.parent.iterdir()) == [path] and response.closed


@pytest.mark.parametrize('identical', [False, True])
def test_concurrent_publication_permission_error_requires_full_hash_and_identical_blocks(tmp_path, monkeypatch, identical):
    raw = bytes(range(96))
    asset = file(raw)
    path = cache_path(tmp_path, asset)
    monkeypatch.setattr(live, '_stream_response', lambda *_: Response(raw))
    original = Path.replace
    def concurrent(source, target):
        if source.name == 'download' and target == path:
            path.write_bytes(raw if identical else b'x' * len(raw))
            raise PermissionError('owned concurrent reader')
        return original(source, target)
    monkeypatch.setattr(Path, 'replace', concurrent)
    if identical:
        assert asset.read(tmp_path, 20, 40) == raw[20:60]
    else:
        with pytest.raises(PermissionError):
            asset.read(tmp_path, 20, 40)
        assert path.read_bytes() == b'x' * len(raw)
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.skipif(os.name != 'nt', reason='Windows file-sharing behavior')
def test_real_windows_read_sharing_lock_keeps_identical_streamed_publication_usable(tmp_path, monkeypatch):
    from ctypes import wintypes
    raw = b'owned immutable publisher stream with a Windows reader'
    asset = file(raw)
    path = cache_path(tmp_path, asset)
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handles, denied = [], []
    original = Path.replace
    def concurrent(source, target):
        if source.name == 'download' and target == path:
            path.write_bytes(raw)
            handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
            assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
            handles.append(handle)
            try:
                return original(source, target)
            except PermissionError:
                denied.append(True)
                raise
        return original(source, target)
    monkeypatch.setattr(Path, 'replace', concurrent)
    monkeypatch.setattr(live, '_stream_response', lambda *_: Response(raw))
    try:
        assert asset.read(tmp_path, 5, 30) == raw[5:35]
        assert denied == [True]
    finally:
        for handle in handles:
            assert api.CloseHandle(handle)


@pytest.mark.parametrize('change', ['partial', 'redirected', 'short-length', 'oversized-length'])
def test_stream_response_rejects_wrong_http_identity_or_declared_length(monkeypatch, change):
    class Http(Response):
        status = 206 if change == 'partial' else 200
        headers = {'Content-Length': '2' if change == 'short-length' else '4' if change == 'oversized-length' else '3'}
        def geturl(self):
            return 'https://other.example/' if change == 'redirected' else URL
    reply = Http(b'abc')
    monkeypatch.setattr(live, 'build_opener', lambda *_: SimpleNamespace(open=lambda *_args, **_kwargs: reply))
    with pytest.raises(ValueError):
        live._stream_response(URL, 3)
    assert reply.closed
