import threading
import time

import pytest

from backend.language_preparation import LanguagePreparation


@pytest.mark.parametrize('action,game,locale', [('prepare', 'beyond', 'nl'),
    ('rebuild', 'deathstranding', 'el'), ('select', 'deathstranding', 'el')])
def test_account_membership_does_not_block_local_source_language(monkeypatch, action, game, locale):
    from types import SimpleNamespace
    from starlette.requests import Request
    from backend import api

    calls = []
    preferences = {'languages': ['zh'], 'global': {'effectiveTranslationLanguage': 'de'}, 'languageSettings': {}}
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(
        accounts=SimpleNamespace(status=lambda: {'active': 'synthetic'}),
        lexirise=SimpleNamespace(status=lambda: {'configured': True}),
        account_preferences=lambda: preferences,
        languages=SimpleNamespace(select=lambda *args, **kwargs: calls.append(('select', args, kwargs)),
            request=lambda *args, **kwargs: calls.append(('prepare', args, kwargs)) or True)), raising=False)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/setup/games/beyond/languages',
                       'headers': [(b'host', b'127.0.0.1:8766')], 'server': ('127.0.0.1', 8766), 'scheme': 'http'})
    api.prepare_game_language(game, api.LanguageAction(locale=locale, action=action, target='en'), request, 'setup')
    if action == 'select':
        assert calls == [('select', (game, locale, 'synthetic'), {'target': 'en'})]
    else:
        assert calls == [('prepare', (game, locale, 'en', 'synthetic'), {'rebuild': action == 'rebuild'})]
    assert preferences['languages'] == ['zh'], 'Local language preparation must not change the account'


def test_optional_account_status_does_not_reject_a_greek_game_language(monkeypatch):
    from types import SimpleNamespace
    from backend import api
    from backend.lexirise_settings import STUDY_LANGUAGES

    pinned = []
    def pin(language):
        assert language in STUDY_LANGUAGES, 'Local Greek capture must not request unsupported account features'
        pinned.append(language)
        return SimpleNamespace(_settings_scope='fixture', status=lambda:
            {'configured': True, 'sent': {}, 'decks': {}})
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(
        accounts=SimpleNamespace(status=lambda: {'active': 'synthetic'}),
        lexirise=SimpleNamespace(pin=pin), languages=SimpleNamespace(
            selected=lambda game, _: 'el' if game == 'deathstranding' else None)), raising=False)
    result = api.integration_status('en')
    assert result['configured'] and 'el' not in result['by_language'] and 'el' not in pinned


def test_enabled_source_keeps_its_account_translation_target(monkeypatch):
    from types import SimpleNamespace
    from starlette.requests import Request
    from backend import api

    calls = []
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(
        accounts=SimpleNamespace(status=lambda: {'active': 'synthetic'}),
        lexirise=SimpleNamespace(status=lambda: {'configured': True}),
        account_preferences=lambda: {'languages': ['nl'], 'global': {'effectiveTranslationLanguage': 'en'},
            'languageSettings': {'nl': {'effectiveTranslationLanguage': 'fr'}}},
        languages=SimpleNamespace(request=lambda *args, **kwargs: calls.append(args) or True)), raising=False)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/setup/games/beyond/languages',
                       'headers': [(b'host', b'127.0.0.1:8766')], 'server': ('127.0.0.1', 8766), 'scheme': 'http'})
    api.prepare_game_language('beyond', api.LanguageAction(locale='nl', target='en'), request, 'setup')
    assert calls == [('beyond', 'nl', 'fr', 'synthetic')]


def test_independent_preparation_without_account(monkeypatch):
    from types import SimpleNamespace
    from starlette.requests import Request
    from backend import api

    calls = []
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(
        accounts=SimpleNamespace(status=lambda: {'active': 'synthetic'}),
        lexirise=SimpleNamespace(status=lambda: {'configured': False}),
        account_preferences=lambda: pytest.fail('No account request in Migaku mode'),
        languages=SimpleNamespace(request=lambda *args, **kwargs: calls.append(args) or True)), raising=False)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/setup/games/beyond/languages',
                       'headers': [(b'host', b'127.0.0.1:8766')], 'server': ('127.0.0.1', 8766), 'scheme': 'http'})
    api.prepare_game_language('beyond', api.LanguageAction(locale='nl', target='en'), request, 'setup')
    assert calls == [('beyond', 'nl', 'en', 'synthetic')]


def finish(manager):
    deadline = time.monotonic() + 3
    while manager._workers and time.monotonic() < deadline:
        time.sleep(.005)
    assert not manager._workers


def test_structured_format_error_survives_job_status_and_malformed_retry_is_ignored(tmp_path):
    import json
    from backend.preparation_errors import PreparationFailure
    path = tmp_path / 'languages.json'
    path.with_suffix('.requests.json').write_text(json.dumps({'bad': [], 'owner': {
        'zzz': {'locale': 'not-a-language'}, 'cyberpunk': None, 'beyond': {'locale': 'nl', 'target': 'en'}}}))
    def build(*_):
        raise PreparationFailure('unsupported_game_format', 'Update the toolkit reader.', game_files_changed=True)
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {}, path=path, supported=lambda _: ('nl',))
    assert manager.entries() == [('beyond', 'nl', ('en',))]
    manager.refresh_prepared()
    finish(manager)
    status = manager.update_status()
    assert status['code'] == 'unsupported_game_format' and status['game_files_changed']
    assert status['state'] == 'retrying' and 'reader' in status['message']


def test_metadata_rate_limit_has_a_network_message_and_background_cooldown(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    import backend.language_preparation as module
    from backend.preparation_errors import public_failure
    failure = HTTPError('https://example.invalid/private', 429, 'Rate limited', {'Retry-After': '900'}, None)
    public = public_failure(failure)
    assert public['code'] == 'metadata_rate_limited' and public['retry_seconds'] == 900
    assert 'download service' in public['message'] and 'example.invalid' not in public['message']
    calls = []
    now = [1000.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    def build(*_):
        calls.append(True)
        raise failure
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {}, path=tmp_path / 'languages.json')
    manager.request('zzz', 'zh-Hans', 'en')
    # Join directly: the synthetic monotonic clock intentionally does not tick.
    for worker in list(manager._workers):
        worker.join(2)
    assert not manager._workers and len(calls) == 1
    manager.refresh_prepared()
    assert len(calls) == 1
    assert manager.update_status()['code'] == 'metadata_rate_limited'
    now[0] += 901
    manager.refresh_prepared()
    for worker in list(manager._workers):
        worker.join(2)
    assert not manager._workers and len(calls) == 2


def test_local_file_write_permission_failure_is_not_reported_as_missing_game_data(tmp_path):
    private_path = tmp_path / 'toolkit-storage' / 'snapshot.pending'
    def build(*_):
        raise PermissionError(13, 'Synthetic access denied', str(private_path))
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {}, path=tmp_path / 'languages.json')
    manager.request('zzz', 'zh-Hans', 'en')
    finish(manager)
    status = manager.update_status()
    assert status['state'] == 'retrying' and status['code'] == 'file_access_denied'
    assert 'toolkit file' in status['message'] and 'local preparation log' in status['message']
    assert str(private_path) not in status['message']
    assert 'game files changed' not in status['message'].lower()


def test_local_targets_survive_activation_history_account_switch_and_refresh(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from backend import api
    from backend.models import TranscriptLine

    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    active = ['first']
    settings = {'languages': ['zh'], 'global': {'effectiveTranslationLanguage': 'de'}, 'languageSettings': {}}
    runtime = api.Runtime.__new__(api.Runtime)
    runtime.accounts = SimpleNamespace(status=lambda: {'active': active[0]})
    runtime.account_preferences = lambda: settings
    runtime.lexirise = SimpleNamespace(status=lambda: {'configured': True})
    runtime.capture = SimpleNamespace(_scan_epoch=0)
    runtime._locale_indexes, runtime._active_locales = {}, {}
    runtime.game_indexes, runtime.game_voice_assets = {}, {}
    runtime.language_voice_assets = lambda *_: object()
    source = 'Blijf hier. Ik kom zo terug.'

    def build(game, locale, targets):
        directory = tmp_path / 'languages' / game / locale
        directory.mkdir(parents=True, exist_ok=True)
        texts = {'nl': source, **{target: {'en': 'Stay here. I will be right back.', 'fr': 'Reste ici. Je reviens.'}[target] for target in targets}}
        row = {'text_id': 'beyond:fixture', 'source_locale': locale, 'source_text': source,
               'audio_locale': locale, 'texts': texts, 'audio': {'voice': 1}}
        (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': game,
            'source_locale': locale, 'records': [row]}), encoding='utf-8')

    manager = runtime.languages = LanguagePreparation(build, runtime.activate_language,
        lambda *_: {'ready': True}, path=tmp_path / 'languages.json', supported=lambda _: ('nl',))
    def displayed():
        index = runtime.game_indexes['beyond']
        match = index.match_lines([source])
        line = TranscriptLine(id=1, created_at=datetime.now(timezone.utc), session_id='synthetic',
                              match_kind=match.kind, **match.model_dump())
        return index, runtime.present_line(line)

    manager.request('beyond', 'nl', 'en', 'first')
    finish(manager)
    index, old_line = displayed()
    assert index.target_locale == old_line.translation_locale == 'en'
    assert old_line.translation_text == 'Stay here. I will be right back.'
    manager.request('beyond', 'nl', 'fr', 'first')
    finish(manager)
    assert displayed()[0].target_locale == displayed()[1].translation_locale == 'fr'
    assert runtime.present_line(old_line).translation_text == old_line.translation_text

    active[0] = 'second'
    manager.select('beyond', 'nl', 'second', target='en')
    assert displayed()[1].translation_locale == 'en'
    active[0] = 'first'
    manager.select('beyond', 'nl', 'first')
    manager.refresh_prepared()
    finish(manager)
    assert displayed()[1].translation_locale == 'fr'
    reloaded = LanguagePreparation(None, None, None, path=manager.path)
    assert reloaded.selected_target('beyond', 'nl', 'first') == 'fr'
    assert reloaded.selected_target('beyond', 'nl', 'second') == 'en'
    with pytest.raises(ValueError, match='Prepare this translation'):
        manager.select('beyond', 'nl', 'first', target='de')
    settings['languages'].append('nl')
    settings['languageSettings']['nl'] = {'effectiveTranslationLanguage': 'en'}
    manager.select('beyond', 'nl', 'first')
    assert displayed()[0].target_locale == displayed()[1].translation_locale == 'en'
    manager.remove('beyond', 'nl')
    assert manager.selected_target('beyond', 'nl', 'first') == ''


def test_nothing_is_built_until_explicit_selection_and_only_prepared_languages_refresh(tmp_path):
    builds, activations = [], []
    manager = LanguagePreparation(lambda *args: builds.append(args), lambda *args: activations.append(args),
        lambda *_: {'ready': True, 'audio_count': 5}, path=tmp_path / 'languages.json',
        supported=lambda _: ('zh-Hans', 'ko', 'en'))
    manager.refresh_prepared()
    assert builds == [] and not manager.path.exists()
    manager.request('wuwa', 'ko', 'nl', 'account-one')
    finish(manager)
    assert builds == [('wuwa', 'ko', ('nl',))]
    assert manager.selected('wuwa', 'account-one') == 'ko'
    assert manager.selected('wuwa', 'account-two') is None
    manager.refresh_prepared()
    finish(manager)
    assert builds == [('wuwa', 'ko', ('nl',))] * 2
    assert manager.prepared('wuwa', 'zh-Hans') is None
    assert manager.prepared('cyberpunk', 'ko') is None
    manager.remove('wuwa', 'ko')
    manager.refresh_prepared()
    assert len(builds) == 2 and manager.selected('wuwa', 'account-one') is None


def test_failed_translation_build_keeps_previous_complete_preparation(tmp_path):
    fails = []
    def build(*args):
        if fails:
            raise ValueError('Official target text missing')
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True}, path=tmp_path / 'languages.json')
    manager.request('cyberpunk', 'zh-Hans', 'en', 'first')
    finish(manager)
    original = manager.prepared('cyberpunk', 'zh-Hans')
    fails.append(True)
    manager.request('cyberpunk', 'zh-Hans', 'nl', 'second')
    finish(manager)
    assert manager.prepared('cyberpunk', 'zh-Hans') == original
    assert manager.prepared('cyberpunk', 'zh-Hans')['targets'] == ['en']
    assert manager.selected('cyberpunk', 'second') is None
    assert next(item for item in manager.status('cyberpunk')['locales'] if item['locale']=='zh-Hans')['job']['state'] == 'error'
    # The failed account's explicit request survives restart without replacing
    # anyone's working selection. Background retry completes that request only.
    fails.clear()
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True}, path=manager.path)
    manager.refresh_prepared()
    finish(manager)
    assert manager.selected('cyberpunk', 'first') == 'zh-Hans'
    assert manager.selected_target('cyberpunk', 'zh-Hans', 'first') == 'en'
    assert manager.selected_target('cyberpunk', 'zh-Hans', 'second') == 'nl'
    assert manager.selected('cyberpunk', 'unrelated') is None


def test_new_request_supersedes_an_inflight_choice_without_cross_account_selection(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def build(game, locale, targets):
        if locale == 'en':
            entered.set()
            assert release.wait(3)
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True},
        path=tmp_path / 'languages.json', supported=lambda _: ('en', 'ko'))
    manager.request('zzz', 'en', 'nl', 'first')
    assert entered.wait(3)
    manager.request('zzz', 'ko', 'en', 'first')
    manager.request('zzz', 'en', 'nl', 'second')
    release.set()
    finish(manager)
    assert manager.selected('zzz', 'first') == 'ko'
    assert manager.selected('zzz', 'second') == 'en'
    manager.remove('zzz', 'en')
    assert not any(game=='zzz' and locale=='en' for game, locale, _ in manager.entries())


def test_unprepared_selection_and_unknown_locales_are_rejected(tmp_path):
    manager = LanguagePreparation(lambda *_: None, lambda *_: None, lambda *_: {}, path=tmp_path / 'languages.json')
    with pytest.raises(ValueError, match='Prepare'):
        manager.select('nte', 'zh-Hans')
    with pytest.raises(ValueError, match='compatible reader'):
        manager.request('nte', 'ja', 'en')
    with pytest.raises(ValueError):
        manager.request('honkai3', 'zh-Hans', 'en')


def test_explicit_rebuild_uses_forced_builder_but_automatic_refresh_does_not(tmp_path):
    builds = []
    manager = LanguagePreparation(lambda *args: builds.append(('cached', args)), lambda *_: None,
        lambda *_: {'ready': True, 'audio_count': 1}, path=tmp_path / 'languages.json',
        supported=lambda _: ('en',), rebuild=lambda *args: builds.append(('forced', args)))
    manager.request('nte', 'en', 'zh-Hans', 'account')
    finish(manager)
    manager.request('nte', 'en', 'zh-Hans', 'account', rebuild=True)
    finish(manager)
    manager.refresh_prepared()
    finish(manager)
    assert [mode for mode, _ in builds] == ['cached', 'forced', 'cached']
    assert all(args == ('nte', 'en', ('zh-Hans',)) for _, args in builds)


def test_background_status_reports_real_jobs_and_repairs_saved_selections(tmp_path):
    entered, release = threading.Event(), threading.Event()
    built = []
    def build(game, locale, targets):
        built.append((game, locale, targets)); entered.set(); release.wait(3)
    manager = LanguagePreparation(build, lambda *args: None, lambda *args: {'ready': True},
        path=tmp_path/'languages.json', supported=lambda _: ('nl',))
    manager.data['selected'] = {'owner': {'beyond': 'nl'}}
    manager.data['local_targets'] = {'owner': {'beyond': {'nl': 'en'}}}
    manager.start()
    try:
        assert entered.wait(2)
        status = manager.update_status()
        assert status['state'] == 'updating' and status['progress'] is None
        assert status['game'] == 'beyond' and 'Dutch' in status['message']
        assert status['elapsed_seconds'] >= 0
        release.set(); finish(manager)
        assert manager.prepared('beyond', 'nl')['targets'] == ['en']
        assert manager.selected('beyond', 'owner') == 'nl'
        assert manager.update_status()['state'] == 'ready'
    finally:
        release.set(); manager.close()
