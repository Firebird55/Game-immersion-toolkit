import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import api, mobile_export_controls, language_preparation
from backend.language_preparation import LanguagePreparation
from backend.scoped_mobile_exports import ScopedMobileExports


class Accounts:
    def __init__(self, path):
        self.path, self.active, self.generation = path, 'one', 0
        self.lock = threading.RLock()
        self.select('one')
    def status(self): return {'active': self.active, 'generation': self.generation}
    def select(self, account):
        with self.lock:
            self.active, self.generation = account, self.generation + 1
            self.path.write_text(f'{account}:{self.generation}')


@pytest.fixture
def scoped(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setattr(mobile_export_controls, 'discover_install', lambda _: None)
    accounts = Accounts(tmp_path / 'protected-fixture')
    languages = LanguagePreparation(None, lambda *_: None, None, path=tmp_path / 'languages.json')
    languages.data['prepared'] = {'zzz': {'ja': {'targets':['zh-hans']}, 'ko': {'targets':['zh-hans']}}}
    languages.data['selected'] = {'one': {'zzz': 'ja'}, 'two': {'zzz': 'ko'}}
    root = tmp_path / 'toolkit'
    for locale in ['ja', 'ko']:
        path = root / 'data/languages/zzz' / locale / 'textmap.json'; path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'records': [{'audio': {'fixture': locale}}]}))
    monkeypatch.setattr(language_preparation, 'selected_snapshot', lambda root, game:
        (root / 'data/languages' / game / languages.selected(game, accounts.active) / 'textmap.json', accounts, accounts.active))
    return ScopedMobileExports(root, accounts, languages), accounts, languages


def test_destinations_status_and_transfer_folders_are_separate_per_account_and_language(scoped, tmp_path):
    exports, accounts, languages = scoped
    first, _, _ = exports._manager('zzz')
    old_preferences = first.preferences_path.parent.parent / 'mobile-library.json'
    old_preferences.parent.mkdir(parents=True, exist_ok=True); old_preferences.write_text('legacy preferences retained')
    chosen = tmp_path / 'transfer'
    first._worker_args = lambda *_: [sys.executable, '-c', 'print(\'{"state":"complete","progress":100}\')']
    assert exports.start('zzz', False, str(chosen))
    first._thread.join(timeout=5)
    assert exports.status('zzz')['state'] == 'complete'
    first_folder = first.output_folder(chosen, 'zzz'); assert first_folder.is_dir()
    languages.select('zzz', 'ko', 'one')
    second, _, _ = exports._manager('zzz')
    assert second is not first and second.destination() != chosen and exports.status('zzz')['state'] == 'idle'
    accounts.select('two')
    third, _, _ = exports._manager('zzz')
    assert third is not second and third.destination() != chosen
    assert len({first_folder, second.output_folder(chosen, 'zzz'), third.output_folder(chosen, 'zzz')}) == 3
    accounts.select('one'); languages.select('zzz', 'ja', 'one')
    assert exports.status('zzz')['destinationFolder'] == str(chosen)
    assert exports.status('zzz')['state'] == 'complete'
    assert old_preferences.read_text() == 'legacy preferences retained'


def test_pending_picker_and_scope_cannot_cross_switches_or_switch_away_and_back(scoped, tmp_path):
    exports, accounts, languages = scoped
    manager, token, _ = exports._manager('zzz')
    original = manager.destination(); abandoned = tmp_path / 'picker.json'
    abandoned.write_text(json.dumps({'folder': str(tmp_path / 'abandoned-choice')}))
    manager._picker, manager._picker_result = SimpleNamespace(poll=lambda: 0), abandoned
    accounts.select('two')
    assert exports.status('zzz')['state'] == 'idle' and not abandoned.exists()
    assert manager.destination() == original
    accounts.select('one')
    with pytest.raises(ValueError, match='changed'): exports.require_scope('zzz', token)
    token = exports.status('zzz')['scope']
    languages.select('zzz', 'ko', 'one'); languages.select('zzz', 'ja', 'one')
    with pytest.raises(ValueError, match='changed'): exports.require_scope('zzz', token)
    token = exports.status('zzz')['scope']
    languages.data['prepared']['zzz']['ja']['prepared_at'] = 'automatic refresh'
    languages._save()
    exports.require_scope('zzz', token)  # Refreshing a prepared table is not a selection change.


def test_worker_is_pinned_and_stale_export_requests_are_rejected_before_actions(scoped, monkeypatch):
    exports, accounts, _ = scoped
    token = exports.status('zzz')['scope']
    manager, _, _ = exports._manager('zzz')
    args = manager._worker_args('zzz', False, Path('private-output'))
    assert args[args.index('--source-locale') + 1] == 'ja'
    assert '--account-signature' in args and '--catalog-only' in args
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(mobile_exports=exports, accounts=accounts), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8766')
    headers = {'X-Proxy-Transcript': 'setup', 'Origin': 'http://127.0.0.1:3000', 'X-Proxy-Transcript-Export-Scope': token}
    calls = []
    monkeypatch.setattr(exports, 'start', lambda *args: calls.append(args) or True)
    accounts.select('two')
    assert client.post('/api/setup/games/zzz/mobile-export', json={}, headers=headers).status_code == 409
    assert not calls
    headers['X-Proxy-Transcript-Export-Scope'] = exports.status('zzz')['scope']
    assert client.post('/api/setup/games/zzz/mobile-export', json={}, headers=headers).status_code == 200
    assert calls == [('zzz', True, None)]


def test_unprepared_named_account_cannot_borrow_a_legacy_language_or_start_preparation(scoped, monkeypatch):
    exports, accounts, _ = scoped
    state = exports.status('beyond')
    assert state['sourceLocale'] == 'unconfigured'
    with pytest.raises(ValueError, match='prepare'): exports.require_scope('beyond', state['scope'])
    with pytest.raises(ValueError, match='prepare'): exports.preview('beyond')
    assert not (exports.root / 'data/languages/beyond').exists()
    with pytest.raises(ValueError, match='Unsupported export game'):
        exports.status('hito')
    from backend import accounts as module
    from backend.mobile_library import prepare_source
    monkeypatch.setattr(module, 'AccountStore', lambda: accounts)
    with pytest.raises(ValueError, match='Account changed'):
        prepare_source(exports.root, 'zzz', exports.root / 'decoded', expected_account_signature='stale')
    (exports.root / 'data/languages/zzz/ja/textmap.json').unlink()
    with pytest.raises(ValueError, match='unavailable'):
        exports.require_scope('zzz', exports.status('zzz')['scope'])
