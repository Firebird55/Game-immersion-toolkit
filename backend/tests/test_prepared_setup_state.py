from types import SimpleNamespace
import json
import threading

import pytest

from backend import api
from backend.language_preparation import LanguagePreparation
from backend.installation import _voice_state


def runtime(tmp_path, account='owner', locale='nl'):
    value = api.Runtime.__new__(api.Runtime)
    value._locale_voice_lock = threading.RLock()
    value._locale_indexes = {}
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


@pytest.mark.parametrize('game', ['beyond', 'cyberpunk'])
def test_matching_metadata_cannot_hide_a_broken_table(tmp_path, monkeypatch, game):
    from backend import game_assets
    from backend.languages import audio_locale
    value = runtime(tmp_path, locale='nl')
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    install = tmp_path / 'game'; install.mkdir()
    directory = tmp_path / 'languages' / game / 'nl'; directory.mkdir(parents=True)
    payload = {'format': 2, 'game': game, 'install': str(install), 'source_locale': 'nl',
               'fingerprint': 'unchanged', 'targets_requested': ['en'], 'reader_revision': 1,
               'records': []}
    (directory / 'textmap.json').write_text(json.dumps(payload))
    monkeypatch.setattr(game_assets, 'asset_adapter', lambda _: (SimpleNamespace(
        index_language=True, fingerprint=lambda _: 'unchanged', LANGUAGE_INDEX_VERSION=1), None))
    value.setup_install = lambda _: install
    extracted = []
    def run(command, **options):
        extracted.append(command)
        payload['records'] = [{'text_id': 'fixture', 'source_locale': 'nl', 'source_text': 'Blijf hier.',
            'audio_locale': audio_locale('nl'), 'texts': {'nl': 'Blijf hier.', 'en': 'Stay here.'}, 'audio': {'voice': 1}}]
        from pathlib import Path
        Path(command[command.index('--output') + 1]).write_text(json.dumps(payload))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(api.subprocess, 'run', run)
    value.build_language(game, 'nl', ('en',))
    assert len(extracted) == 1, 'Invalid unchanged snapshots must be repaired without Rebuild'
    value.build_language(game, 'nl', ('en',))
    assert len(extracted) == 1, 'A valid unchanged table must not be extracted again'
    monkeypatch.setattr(api.json, 'loads', lambda *_: pytest.fail('Unchanged validated data should not be parsed again'))
    value.build_language(game, 'nl', ('en',))


def test_changed_game_format_failure_keeps_snapshot_and_explains_change(tmp_path, monkeypatch):
    from pathlib import Path
    from backend import game_assets
    from backend.preparation_errors import PreparationFailure, public_failure
    value = runtime(tmp_path)
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    install = tmp_path / 'game'; install.mkdir()
    directory = tmp_path / 'languages/beyond/nl'; directory.mkdir(parents=True)
    original = json.dumps({'fingerprint': 'previous-game-version', 'records': [{'synthetic': True}]})
    (directory / 'textmap.json').write_text(original)
    monkeypatch.setattr(game_assets, 'asset_adapter', lambda _: (SimpleNamespace(
        index_language=True, fingerprint=lambda _: 'new-game-version', LANGUAGE_INDEX_VERSION=1), None))
    value.setup_install = lambda _: install
    def run(command, **options):
        output = Path(command[command.index('--output') + 1])
        output.with_name('failure.json').write_text(json.dumps({'code': 'unsupported_game_format',
            'message': 'This archive format needs a newer reader. Update the toolkit and retry.'}))
        output.with_name('failure.log').write_text('Synthetic private diagnostic.')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(api.subprocess, 'run', run)
    with pytest.raises(PreparationFailure) as caught:
        value.build_language('beyond', 'nl', ('en',))
    failure = public_failure(caught.value)
    assert failure['code'] == 'unsupported_game_format' and failure['game_files_changed']
    assert failure['previous_snapshot_retained']
    assert 'Installed game files changed' in failure['message'] and 'newer reader' in failure['message']
    assert str(tmp_path) not in failure['message']
    assert (directory / 'textmap.json').read_text() == original
    assert (directory / 'last-preparation-error.log').is_file()
