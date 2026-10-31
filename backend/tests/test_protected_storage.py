"""Host storage failures must never replace readable accounts or reveal keys."""
import json
import os

import httpx
import pytest

from backend.accounts import AccountStore
from backend.protected_storage import ProtectedBlobs, ProtectedStorageError, SERVICE, private_write


class Store:
    def __init__(self):
        self.values = {}
        self.locked = False
        self.writes = 0

    def get_password(self, service, identifier):
        if self.locked:
            raise RuntimeError('PRIVATE PROVIDER ERROR')
        return self.values.get((service, identifier))

    def set_password(self, service, identifier, value):
        if self.locked:
            raise RuntimeError('PRIVATE PROVIDER ERROR')
        self.writes += 1
        self.values[service, identifier] = value


def test_multiple_account_blobs_reuse_one_protected_master_and_randomize_ciphertext(tmp_path):
    provider = Store()
    blobs = ProtectedBlobs(tmp_path, provider=provider)
    value = b'lx_TEST_ONLY_mock_credential'
    first, second = blobs.protect(value), blobs.protect(value)
    assert first != second and value not in first
    assert blobs.protect(first, decrypt=True) == value
    assert ProtectedBlobs(tmp_path, provider=provider).protect(second, decrypt=True) == value
    assert provider.writes == 1
    assert set(path.name for path in tmp_path.iterdir()) == {'master-key-id', 'master-key.lock'}


@pytest.mark.parametrize('mutation', ['tag', 'identifier', 'version', 'truncated'])
def test_corrupt_or_unknown_envelope_fails_without_generating_replacement_keys(tmp_path, mutation):
    provider = Store()
    blobs = ProtectedBlobs(tmp_path, provider=provider)
    value = blobs.protect(b'TEST_ONLY')
    if mutation == 'tag':
        value = value[:-1] + bytes([value[-1] ^ 1])
    elif mutation == 'identifier':
        value = value.replace((tmp_path / 'master-key-id').read_bytes(), b'0' * 32)
    elif mutation == 'version':
        value = b'unknown!' + value
    else:
        value = value[:10]
    with pytest.raises(ProtectedStorageError):
        blobs.protect(value, decrypt=True)
    assert provider.writes == 1


def test_locked_store_preserves_account_file_and_never_exposes_provider_exception(tmp_path):
    provider = Store()
    blobs = ProtectedBlobs(tmp_path / 'host', provider=provider)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'user': {'id': 'TEST', 'name': 'Test'}})
        if request.method == 'GET' and request.url.path == '/v1/me' else pytest.fail('Unexpected account write'))
    store = AccountStore(tmp_path / 'accounts', protect=blobs.protect, transport=transport)
    store.add('lx_TEST_ONLY_valid_mock_credential')
    before = store.path.read_bytes()
    provider.locked = True
    with pytest.raises(ProtectedStorageError, match='Unlock') as error:
        store.add('lx_TEST_ONLY_another_mock_credential')
    assert 'PRIVATE' not in str(error.value)
    assert store.path.read_bytes() == before and provider.writes == 1


def test_missing_master_does_not_reset_locator_or_generate_key_on_read_or_write(tmp_path):
    provider = Store()
    blobs = ProtectedBlobs(tmp_path, provider=provider)
    value = blobs.protect(b'TEST_ONLY')
    locator = (tmp_path / 'master-key-id').read_bytes()
    provider.values.clear()
    for decrypt, data in [(True, value), (False, b'new_TEST')]:
        with pytest.raises(ProtectedStorageError, match='Unlock'):
            blobs.protect(data, decrypt=decrypt)
    assert (tmp_path / 'master-key-id').read_bytes() == locator
    assert provider.writes == 1


def test_concurrent_initialization_fails_closed_until_owner_releases_lock(tmp_path):
    from backend.export_lock import ExportLock
    lease = ExportLock(tmp_path / 'master-key.lock')
    assert lease.acquire()
    provider = Store()
    try:
        with pytest.raises(ProtectedStorageError, match='Another account operation'):
            ProtectedBlobs(tmp_path, provider=provider).protect(b'TEST_ONLY')
        assert not provider.values
    finally:
        lease.close()
    assert ProtectedBlobs(tmp_path, provider=provider).protect(b'TEST_ONLY')


def test_interrupted_atomic_write_keeps_previous_file(tmp_path, monkeypatch):
    from backend import atomic_files
    target = tmp_path / 'account'
    private_write(target, b'old ciphertext')
    def fail(*_):
        raise OSError('Disk unavailable')
    monkeypatch.setattr(atomic_files, 'replace', fail)
    with pytest.raises(OSError):
        private_write(target, b'new ciphertext')
    assert target.read_bytes() == b'old ciphertext'
    assert [path.name for path in tmp_path.iterdir()] == ['account']


@pytest.mark.skipif(os.name == 'nt', reason='POSIX file mode contract')
def test_private_permissions_exist_before_atomic_publish(tmp_path, monkeypatch):
    from backend import atomic_files
    original = atomic_files.replace
    def replace(path, destination):
        assert path.stat().st_mode & 0o777 == 0o600
        return original(path, destination)
    monkeypatch.setattr(atomic_files, 'replace', replace)
    private_write(tmp_path / 'account', b'TEST encrypted bytes')
