"""Host-local, DPAPI protected account profiles. No credential leaves this host."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading

import httpx

from .lexirise import API_BASE, LexiriseError, LexiriseService, _protect


def accounts_path() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'Programs/Proxy Transcript/accounts.dpapi'


class AccountStore:
    def __init__(self, path: Path | None = None, *, protect=_protect, transport=None):
        self.path = path or accounts_path()
        self.protect, self.transport = protect, transport
        self.lock = threading.RLock()
        self.generation = 0

    def _read(self) -> dict:
        if not self.path.exists():
            return {'active': None, 'profiles': {}}
        try:
            value = json.loads(self.protect(self.path.read_bytes(), decrypt=True))
            if not isinstance(value.get('profiles'), dict) or value.get('active') not in {None, *value['profiles']}:
                raise ValueError()
            return value
        except (OSError, ValueError, TypeError, KeyError):
            raise LexiriseError('Saved accounts could not be read for this Windows user.') from None

    def _write(self, value: dict) -> None:
        data = self.protect(json.dumps(value, ensure_ascii=False).encode())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix('.pending')
        pending.write_bytes(data)
        pending.replace(self.path)
        self.generation += 1

    def active_key(self) -> str | None:
        with self.lock:
            value = self._read()
            return value['profiles'].get(value['active'], {}).get('key')

    def status(self) -> dict:
        with self.lock:
            value = self._read()
            return {'active': value['active'] or 'legacy', 'generation': self.generation,
                    'profiles': [{'id': key, 'name': profile['name']} for key, profile in value['profiles'].items()]}

    def add(self, key: str, name: str = '', *, select: bool = True) -> dict:
        key = key.strip()
        if not key.startswith('lx_') or not 20 <= len(key) <= 512:
            raise LexiriseError('Enter a valid Lexirise API key in the local hidden-input prompt.')
        # Verify identity before persisting a profile. Registration never edits
        # account settings, creates decks or performs dictionary operations.
        with httpx.Client(base_url=API_BASE, headers={'Authorization': f'Bearer {key}'},
                          transport=self.transport, timeout=25, follow_redirects=False) as client:
            response = LexiriseService._request(client, 'GET', '/v1/me')
        user = response.get('user') or {}
        if not isinstance(user.get('id'), str) or not user['id']:
            raise LexiriseError('Lexirise did not confirm the account owner.')
        identity = hashlib.sha256(user['id'].encode()).hexdigest()[:24]
        label = (name.strip() or user.get('name') or 'Lexirise account')[:80]
        with self.lock:
            value = self._read()
            value['profiles'][identity] = {'key': key, 'name': label}
            if select:
                value['active'] = identity
            self._write(value)
        return {'id': identity, 'name': label}

    def select(self, identity: str) -> dict:
        with self.lock:
            value = self._read()
            if identity != 'legacy' and identity not in value['profiles']:
                raise LexiriseError('Choose a saved account on this PC.')
            value['active'] = None if identity == 'legacy' else identity
            self._write(value)
            return self.status()

    def remove(self, identity: str) -> dict:
        with self.lock:
            value = self._read()
            if identity not in value['profiles']:
                raise LexiriseError('Choose a saved account on this PC.')
            del value['profiles'][identity]
            if value['active'] == identity:
                value['active'] = None
            self._write(value)
            return self.status()
