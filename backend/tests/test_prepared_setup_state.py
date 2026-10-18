from types import SimpleNamespace
import json

import pytest

from backend import api
from backend.language_preparation import LanguagePreparation
from backend.installation import _voice_state


def runtime(tmp_path, account='owner', locale='nl'):
    value = api.Runtime.__new__(api.Runtime)
    value.accounts = SimpleNamespace(status=lambda: {'active': account})
    value.languages = LanguagePreparation(None, None, None, path=tmp_path / 'languages.json')
    if locale:
        value.languages.data['selected'] = {account: {'beyond': locale}}
        value.languages.data['prepared'] = {'beyond': {locale: {'targets': ['zh-hans'], 'prepared_at': 'fixture'}}}
    return value


def test_setup_reads_prepared_dutch_counts_before_capture_activation_without_side_effects(tmp_path):
    value = runtime(tmp_path)
    observed = []
    value.language_state = lambda *args: observed.append(args) or {'ready': True, 'state': 'ready', 'source_locale': 'nl',
        'entry_count': 100, 'audio_count': 80, 'message': 'Prepared Dutch originals'}
    state = value.setup_game_state('beyond')
    assert observed == [('beyond', 'nl')]
    assert state['index_ready'] and state['audio_ready'] and state['indexed_lines'] == 100
    assert state['source_locale'] == 'nl' and state['last_checked'] == 'fixture'
    assert not value.languages.path.exists(), 'Merely reading setup must not prepare or save anything'
    assert _voice_state('beyond', tmp_path, state) == 'present'


def test_another_accounts_unconfigured_setup_cannot_reuse_the_prior_active_index(tmp_path):
    value = runtime(tmp_path, locale=None)
    value.game_indexes = {'beyond': SimpleNamespace(status=lambda: pytest.fail('Do not use another account\'s activated index'))}
    state = value.setup_game_state('beyond')
    assert not state['index_ready'] and not state['audio_ready'] and state['source_locale'] is None
    assert _voice_state('beyond', tmp_path, state) == 'needs_language_setup'


def test_prepared_text_with_a_missing_pack_is_not_reported_as_original_audio_ready(tmp_path):
    value = runtime(tmp_path)
    value.language_state = lambda *_: {'ready': True, 'state': 'missing_voice', 'source_locale': 'nl', 'entry_count': 100, 'audio_count': 0}
    state = value.setup_game_state('beyond')
    assert state['index_ready'] and not state['audio_ready']
    assert _voice_state('beyond', tmp_path, state) == 'missing'


def test_missing_scoped_snapshot_cannot_fall_back_to_another_locale(tmp_path, monkeypatch):
    value = runtime(tmp_path)
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    value.game_indexes = {'beyond': SimpleNamespace(status=lambda: pytest.fail('Missing Dutch table must not borrow another locale'))}
    assert not value.language_state('beyond', 'nl')['ready']
    (tmp_path / 'languages/beyond').mkdir(parents=True)
    assert not value.language_state('beyond', 'zh-Hans')['ready']


def test_legacy_chinese_setup_keeps_its_own_index_after_another_account_captured(tmp_path):
    value = runtime(tmp_path, account='legacy', locale=None)
    value.textmaps = SimpleNamespace(status=lambda: pytest.fail('Do not reuse the other account\'s Japanese index'))
    value.voice_assets = SimpleNamespace(status=lambda: pytest.fail('Do not reuse the other account\'s Japanese voices'))
    value._legacy_zzz_index = SimpleNamespace(status=lambda: {'ready': True, 'entry_count': 5})
    value._legacy_zzz_voice = SimpleNamespace(status=lambda: {'ready': True, 'mapped_lines': 5})
    value.update_manager = SimpleNamespace(status=lambda: {})
    state = value.setup_game_state('zzz')
    assert state['index_ready'] and state['audio_ready'] and state['indexed_lines'] == 5


def test_a_snapshot_from_another_locale_is_not_ready_for_the_selected_language(tmp_path, monkeypatch):
    value = runtime(tmp_path); value._locale_indexes = {}
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    directory = tmp_path / 'languages/beyond/nl'; directory.mkdir(parents=True)
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'ja', 'records': []}))
    assert not value.language_state('beyond', 'nl')['ready']
