"""Desktop-only UI harness; authored owners, mocked vault, no remote transport."""
import base64
import json
from pathlib import Path
import sys

import httpx

from backend.android_host import AndroidHost
from backend.android_probe import TEXT, _library


class AuthoredNative:
    def assertAuthoredGameData(self):
        pass

    def assertAuthoredAccounts(self):
        pass

    def protect(self, *args):
        raise AssertionError('The UI fixture accessed production credentials')

    def protectAuthored(self, value, decrypt):
        return base64.b64encode(bytes(n ^ 173 for n in base64.b64decode(value))).decode()


def forbidden(*args, **kwargs):
    raise AssertionError('The authored UI attempted a real account request')


httpx.HTTPTransport.handle_request = forbidden
root, frontend = map(Path, sys.argv[1:3])
library = _library(root / 'authored-input', duration=8)
host = AndroidHost(root / 'authored-account-ui', frontend, AuthoredNative(), authored_accounts=True, authored_game_data=True)
corrupted_store = None
print(json.dumps({'origin': host.origin, 'library': str(library), 'cookie': host.cookie}), flush=True)
try:
    for raw in sys.stdin:
        action = json.loads(raw)['action']
        if action == 'capture':
            with host.session.lock:
                if host.session.index is None:
                    print(json.dumps({'captured': 0, 'state': host.snapshot(), 'accounts': host.account_sessions.status()}), flush=True)
                    continue
                generation = host.session.start()
                host.session.observe(generation, 1, [TEXT], now=1)
                lines = host.session.observe(generation, 2, [TEXT], now=1.02)
            print(json.dumps({'captured': len(lines)}), flush=True)
        elif action == 'close':
            break
        elif action == 'corrupt':
            corrupted_store = host.account_sessions.accounts.path
            corrupted_store.write_bytes(b'authored-corrupt-credential-fixture')
            print(json.dumps({'locked': host.snapshot()['lexirise']['account'] == 'recovery'}), flush=True)
        elif action == 'verify_recovery':
            print(json.dumps({'old_store_preserved': corrupted_store is not None
                and corrupted_store.read_bytes() == b'authored-corrupt-credential-fixture'}), flush=True)
        else:
            raise ValueError('Unknown authored UI action')
finally:
    host.close()
