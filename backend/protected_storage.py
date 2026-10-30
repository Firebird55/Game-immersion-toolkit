"""Authenticated blobs backed by the desktop user's protected credential store.

Windows keeps its existing DPAPI format in lexirise._protect. Other platforms
hold a random encryption key in the OS store; only ciphertext and a key locator
are written to application storage. No configurable/plaintext keyring fallback.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import secrets
import sys

from .export_lock import ExportLock

MAGIC = b'GIT-CREDENTIALS\x00\x01'
SERVICE = 'Game Immersion Toolkit protected storage'
KEY_ID = re.compile(r'[a-f0-9]{32}')


class ProtectedStorageError(RuntimeError):
    """Messages are safe to show; provider exceptions may contain secrets."""


def credential_directory():
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle' or sys.platform != 'win32':
        return layout.settings_root / 'credentials'
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Programs/Proxy Transcript'


def private_write(path: Path, value: bytes):
    """Set permissions before publishing, keeping an existing file on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + secrets.token_hex(8) + '.pending')
    try:
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        from .atomic_files import replace
        replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def native_store():
    try:
        if sys.platform == 'darwin':
            from keyring.backends.macOS import Keyring
        elif sys.platform.startswith('linux'):
            from keyring.backends.SecretService import Keyring
        else:
            raise ProtectedStorageError('Protected account storage is unavailable on this platform.')
        return Keyring()
    except ProtectedStorageError:
        raise
    except Exception:
        raise ProtectedStorageError('Protected account storage is unavailable. Repair the toolkit installation.') from None


def _unavailable():
    return ProtectedStorageError('Unlock or allow access to your desktop credential store, then retry. Existing accounts were kept.')


class ProtectedBlobs:
    def __init__(self, directory=None, *, provider=None):
        self.directory = Path(directory) if directory is not None else credential_directory()
        self._provider = provider

    @property
    def provider(self):
        if self._provider is None:
            self._provider = native_store()
        return self._provider

    def _read_key(self, identifier):
        try:
            encoded = self.provider.get_password(SERVICE, identifier)
            if not encoded:
                raise _unavailable()
            key = base64.b64decode(encoded, validate=True)
            if len(key) != 32:
                raise _unavailable()
            return key
        except Exception:
            raise _unavailable() from None

    def _current_key(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise ProtectedStorageError('Protected storage cannot use a linked credential directory.')
        lock = ExportLock(self.directory / 'master-key.lock')
        if not lock.acquire():
            raise ProtectedStorageError('Another account operation is finishing. Retry in a moment.')
        try:
            locator = self.directory / 'master-key-id'
            if locator.exists():
                identifier = locator.read_text(encoding='ascii')
                if not KEY_ID.fullmatch(identifier):
                    raise ProtectedStorageError('The protected account locator is invalid. Existing accounts were kept.')
                return identifier, self._read_key(identifier)
            identifier, key = secrets.token_hex(16), secrets.token_bytes(32)
            try:
                self.provider.set_password(SERVICE, identifier, base64.b64encode(key).decode('ascii'))
                if self._read_key(identifier) != key:
                    raise _unavailable()
            except Exception:
                raise _unavailable() from None
            # A failure here leaves an unused OS entry, never an unreadable
            # profile or a locator pointing at an unconfirmed key.
            private_write(locator, identifier.encode('ascii'))
            return identifier, key
        except (OSError, UnicodeError):
            raise ProtectedStorageError('Cannot access protected account storage. Existing accounts were kept.') from None
        finally:
            lock.close()

    def protect(self, value: bytes, decrypt=False):
        from Crypto.Cipher import AES
        if not decrypt:
            identifier, key = self._current_key()
            nonce = secrets.token_bytes(12)
            header = MAGIC + identifier.encode('ascii') + nonce
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            cipher.update(header)
            ciphertext, tag = cipher.encrypt_and_digest(value)
            return header + tag + ciphertext
        prefix = len(MAGIC)
        if len(value) < prefix + 32 + 12 + 16 or not value.startswith(MAGIC):
            raise ProtectedStorageError('Saved accounts use an invalid or unsupported format. Existing accounts were kept.')
        try:
            identifier = value[prefix:prefix + 32].decode('ascii')
            if not KEY_ID.fullmatch(identifier):
                raise ValueError()
            header = value[:prefix + 44]
            nonce, tag, ciphertext = value[prefix + 32:prefix + 44], value[prefix + 44:prefix + 60], value[prefix + 60:]
            cipher = AES.new(self._read_key(identifier), AES.MODE_GCM, nonce=nonce)
            cipher.update(header)
            return cipher.decrypt_and_verify(ciphertext, tag)
        except (ValueError, UnicodeError):
            raise ProtectedStorageError('Saved accounts could not be authenticated. Existing accounts were kept.') from None
