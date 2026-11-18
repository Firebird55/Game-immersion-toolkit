"""Android credential recovery without replacing any existing protected store."""
import json
from pathlib import Path
import re
import secrets

from .accounts import AccountStore
from .lexirise import LexiriseError
from .prepared_library import _json, _no_links
from .protected_storage import private_write

STORE = re.compile(r'accounts-recovered-[0-9a-f]{32}\.gcm')
OWNER = re.compile(r'[0-9a-f]{24}')
MAX_RECOVERED_STORES = 32
RECOVERY_MESSAGE = ('Saved credentials could not be unlocked. Your libraries and transcripts were kept. '
    'Unlock device protected storage and reopen the app, or re-enter the API key for the same account to restore its local data.')


class AndroidCredentialStores:
    """Delegate credentials to the maintained AccountStore; recovery is explicit.

    Only a successful new owner's verification and authenticated readback may
    publish a new locator. An unreadable original blob is never overwritten,
    moved, deleted, treated as an empty profile, or used to infer an owner.
    """
    def __init__(self, directory, *, protect, transport, lock):
        self.directory = Path(directory)
        self.pointer = self.directory / 'accounts-current.json'
        self.protect, self.transport, self.lock = protect, transport, lock
        self.generation = 0
        self.locked = False
        self.on_locked = lambda: None
        self._store = self._new(self.directory / 'accounts.gcm')
        self._had_store = False
        try:
            self._had_store = self.path.exists()
            _no_links(self.pointer)
            if self.pointer.exists():
                if self.pointer.stat().st_size > 256:
                    raise ValueError()
                pointer = _json(self.pointer.read_bytes())
                if (not isinstance(pointer, dict) or set(pointer) != {'schema', 'store'}
                        or type(pointer['schema']) is not int or pointer['schema'] != 1
                        or not isinstance(pointer['store'], str) or not STORE.fullmatch(pointer['store'])):
                    raise ValueError()
                path = self.directory / pointer['store']
                _no_links(path)
                if not path.is_file():
                    raise ValueError()
                self._store = self._new(path)
                self._had_store = True
            self._status_store()
        except (OSError, ValueError, TypeError, KeyError, AttributeError, LexiriseError):
            self._lock()

    def _new(self, path):
        store = AccountStore(path, protect=self.protect, transport=self.transport, trust_env=False)
        store.lock = self.lock
        return store

    def _status_store(self):
        _no_links(self.path)
        if not self.path.exists() and (self._had_store or any(OWNER.fullmatch(path.name)
                for path in (self.directory.parent / 'profiles').glob('*'))):
            raise ValueError('Previously configured protected store is missing')
        if self.path.exists() and self.path.stat().st_size > 1024**2 + 64:
            raise ValueError('Protected store exceeds its native envelope bound')
        value = self._store.status()
        if (len(value['profiles']) > 1024 or any(not isinstance(row.get('id'), str) or not OWNER.fullmatch(row['id'])
                or not isinstance(row.get('name'), str) or len(row['name']) > 80 for row in value['profiles'])):
            raise ValueError('Protected account profile metadata is invalid')
        for profile in self._store._read()['profiles'].values():
            key = profile.get('key')
            if (not isinstance(key, str) or not key.startswith('lx_') or not 20 <= len(key) <= 512
                    or not key.isascii() or not key.isprintable() or ' ' in key):
                raise ValueError('Protected account credential metadata is invalid')
        return value

    def _locator_state(self):
        _no_links(self.pointer)
        if not self.pointer.exists():
            return None
        stat = self.pointer.stat()
        return stat.st_mtime_ns, stat.st_size, self.pointer.read_bytes() if stat.st_size <= 256 else None

    @property
    def path(self):
        return self._store.path

    def recovery(self):
        return {'state': 'credentials_unreadable', 'data_preserved': True,
            'action': 'reenter_verified_account', 'message': RECOVERY_MESSAGE} if self.locked else None

    def _lock(self):
        if not self.locked:
            self.locked = True
            self._store._cached_data = self._store._cached_signature = None
            self.generation += 1
            self.on_locked()

    def status(self):
        with self.lock:
            if not self.locked:
                try:
                    value = self._status_store()
                    return {**value, 'generation': self.generation, 'recovery': None}
                except (OSError, ValueError, TypeError, KeyError, AttributeError, LexiriseError):
                    self._lock()
            return {'active': 'recovery', 'generation': self.generation, 'profiles': [], 'recovery': self.recovery()}

    def _require(self):
        self.status()
        if self.locked:
            raise LexiriseError(RECOVERY_MESSAGE)
        # Preserve the testing seam without changing the native immutable mode.
        self._store.transport = self.transport

    def active_key(self):
        with self.lock:
            self._require()
            return self._store.active_key()

    def add(self, key, name='', *, select=True):
        with self.lock:
            self._require()
            store = self._store
        # The maintained verification must remain outside the session lock.
        value = store.add(key, name, select=select)
        with self.lock:
            self._had_store = True
            self.generation += 1
        return value

    def select(self, identity):
        with self.lock:
            self._require()
            self._store.select(identity)
            self.generation += 1
            return self.status()

    def stage_recovery(self, key, name):
        # A fresh random private file is the only destination; never overwrite a
        # pre-existing failed store or recreate/delete a native Keystore key.
        _no_links(self.pointer)
        self.directory.mkdir(parents=True, exist_ok=True)
        if sum(bool(STORE.fullmatch(path.name)) for path in self.directory.iterdir()) >= MAX_RECOVERED_STORES:
            raise LexiriseError('Protected recovery storage is full. Existing files were kept; preserve an app backup before repair.')
        store = self._new(self.directory / ('accounts-recovered-' + secrets.token_hex(16) + '.gcm'))
        store._recovery_locator_state = self._locator_state()
        if store.path.exists():
            raise LexiriseError('A private recovery destination is already in use. Retry without removing existing data.')
        try:
            profile = store.add(key, name)
            if store.status()['active'] != profile['id']:
                raise LexiriseError('The new protected account could not be reopened. Existing files were kept.')
            return store, profile['id']
        except BaseException:
            self.discard(store)
            raise

    def discard(self, store):
        # Only an uncommitted file created by this recovery attempt is removed.
        # Never delete an adopted file or an original credential-store path.
        if store is not self._store and store.path.parent == self.directory and STORE.fullmatch(store.path.name):
            try:
                locator = self._locator_state()
                if locator is not None and (locator[2] is None or json.loads(locator[2]).get('store') == store.path.name):
                    return  # Publication may have completed before an I/O error.
            except (OSError, ValueError, TypeError, AttributeError):
                return  # An uncertain locator never authorizes deletion.
            _no_links(store.path)
            store.path.unlink(missing_ok=True)

    def publish(self, store):
        with self.lock:
            if not self.locked:
                raise LexiriseError('Credential recovery already completed. Refresh the selected account.')
            if self._locator_state() != store._recovery_locator_state:
                raise LexiriseError('The protected account locator changed during recovery. Existing files were kept; retry explicitly.')
            _no_links(self.pointer)
            private_write(self.pointer, json.dumps({'schema': 1, 'store': store.path.name}).encode('ascii'))
            self._store, self.locked = store, False
            self._had_store = True
            self.generation += 1
