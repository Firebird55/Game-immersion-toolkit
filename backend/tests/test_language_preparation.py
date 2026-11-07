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


@pytest.fixture
def bundle_language_roots(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import httpx
    from backend import accounts, language_preparation, lexirise, runtime_paths
    from backend.runtime_bundle import RuntimeLayout

    def forbidden(*_args, **_options):
        pytest.fail('Language path tests must not use accounts, DPAPI, network or native resources.')

    monkeypatch.setattr(accounts, 'AccountStore', forbidden)
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(httpx, 'Client', forbidden)
    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    root = tmp_path.resolve()
    layout = RuntimeLayout(mode='bundle', application_root=root/'app', resource_root=root/'app/_internal',
        executable=root/'app/GameImmersionToolkit.exe', legacy_root=None, data_root=root/'mutable/data-v1',
        settings_root=root/'mutable/settings', cache_root=root/'mutable/cache-v1', tool_root=root/'mutable/tools-v1',
        work_root=root/'mutable/cache-v1/work', state_root=root/'mutable/host-v1', default_export_root=root/'exports')
    monkeypatch.setattr(language_preparation, 'discover_layout', lambda: layout)
    monkeypatch.setattr(runtime_paths, 'discover_layout', lambda: layout)
    monkeypatch.setattr('sys.frozen', True, raising=False)
    host = root/'host-profile'
    monkeypatch.setenv('LOCALAPPDATA', str(host))
    cwd = root/'unrelated-cwd'; cwd.mkdir()
    monkeypatch.chdir(cwd)
    host_languages = host/'Proxy Transcript/languages.json'
    host_languages.parent.mkdir(parents=True)
    host_languages.write_text(json.dumps({'prepared': {}, 'selected': {'owned': {'halflife': 'zh-Hans'}},
        'selection_generations': {'owned': {'halflife': 17}}}), encoding='utf-8')
    host_languages.with_suffix('.requests.json').write_text(json.dumps({
        'host-only': {'beyond': {'locale': 'nl', 'target': 'en'}}}), encoding='utf-8')
    # Isolate the protected-store locator as well as account construction.
    monkeypatch.setattr(accounts, 'credential_directory', lambda: host/'Programs/Proxy Transcript')
    host_accounts = accounts.accounts_path()
    host_accounts.parent.mkdir(parents=True)
    host_accounts.write_bytes(b'authored protected-store locator sentinel; no credential')
    before = {path: path.read_bytes() for path in (host_languages, host_languages.with_suffix('.requests.json'), host_accounts)}
    return SimpleNamespace(layout=layout, host=host, cwd=cwd, accounts=host_accounts, before=before,
        forbidden=forbidden)


def test_bundle_default_language_registry_and_requests_survive_restart_and_select(bundle_language_roots):
    import json
    roots = bundle_language_roots
    failures, calls = [True], []

    def build(*args):
        calls.append(args)
        if failures[0]: raise ValueError('Authored incomplete language build.')

    def create():
        return LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True, 'audio_count': 3},
            supported=lambda _: ('en',))

    manager = create()
    assert manager.path == roots.layout.settings_root/'languages.json'
    assert manager.request('halflife', 'en', 'zh-Hans', 'owned')
    finish(manager)
    requests = manager.path.with_suffix('.requests.json')
    assert json.loads(requests.read_text(encoding='utf-8')) == {
        'owned': {'halflife': {'locale': 'en', 'target': 'zh-Hans'}}}
    assert manager.selected('halflife', 'owned') is None
    reloaded = create()
    assert reloaded.entries() == [('halflife', 'en', ('zh-Hans',))]
    failures[0] = False
    reloaded.refresh_prepared()
    finish(reloaded)
    assert not requests.exists()
    assert reloaded.selected('halflife', 'owned') == 'en'
    prepared = reloaded.prepared('halflife', 'en')
    failures[0] = True
    assert reloaded.request('halflife', 'en', 'fr', 'waiting-owner')
    finish(reloaded)
    pending = requests.read_bytes()
    selected = create()
    selected.select('halflife', 'en', 'owned', target='zh-Hans')
    assert selected.prepared('halflife', 'en') == prepared
    assert selected.selected_target('halflife', 'en', 'owned') == 'zh-Hans'
    assert selected.selected('halflife', 'waiting-owner') is None
    assert selected.selection_generation('halflife', 'owned') == 1
    assert requests.read_bytes() == pending
    assert create().entries() == [('halflife', 'en', ('zh-Hans', 'fr'))]
    assert len(calls) == 3
    assert all(path.read_bytes() == raw for path, raw in roots.before.items())
    assert not roots.layout.application_root.exists() and not (roots.cwd/'Proxy Transcript').exists()


def test_explicit_language_path_never_discovers_or_relocates_a_layout(bundle_language_roots, monkeypatch):
    from pathlib import Path
    from backend import language_preparation
    roots = bundle_language_roots
    monkeypatch.setattr(language_preparation, 'discover_layout', roots.forbidden)
    chosen = Path('explicit-language-registry.json')
    manager = LanguagePreparation(lambda *_: None, lambda *_: None, lambda *_: {'ready': True}, path=chosen)
    assert manager.path is chosen
    assert manager.request('zzz', 'zh-Hans', 'en', 'owned')
    finish(manager)
    reloaded = LanguagePreparation(None, None, None, path=chosen)
    assert reloaded.path is chosen and reloaded.selected('zzz', 'owned') == 'zh-Hans'
    assert not roots.layout.settings_root.exists()
    assert all(path.read_bytes() == raw for path, raw in roots.before.items())


def test_invalid_bundle_layout_never_falls_back_to_host_language_state(bundle_language_roots, monkeypatch):
    from backend import language_preparation
    from backend.runtime_bundle import RuntimeBundleError
    roots = bundle_language_roots
    failure = RuntimeBundleError('Authored missing frozen roots.')

    def invalid(): raise failure

    monkeypatch.setattr(language_preparation, 'discover_layout', invalid)
    with pytest.raises(RuntimeBundleError) as refused: LanguagePreparation(None, None, None)
    assert refused.value is failure and not roots.layout.settings_root.exists()
    assert all(path.read_bytes() == raw for path, raw in roots.before.items())


def test_unselected_bundle_account_cannot_borrow_host_language_selection(bundle_language_roots, monkeypatch):
    from types import SimpleNamespace
    from backend import accounts, language_preparation
    roots = bundle_language_roots
    (roots.layout.data_root/'languages/halflife').mkdir(parents=True)
    monkeypatch.setattr(accounts, 'AccountStore', lambda: SimpleNamespace(
        path=roots.accounts, status=lambda: {'active': 'owned'}))
    with pytest.raises(ValueError, match='Select a prepared learning language'):
        language_preparation.selected_snapshot(roots.layout.application_root, 'halflife')
    assert not roots.layout.settings_root.exists()
    assert all(path.read_bytes() == raw for path, raw in roots.before.items())


@pytest.mark.parametrize('local_appdata', ['configured', 'missing'])
def test_windows_source_upgrade_keeps_saved_language_after_working_directory_changes(tmp_path, monkeypatch, local_appdata):
    import json
    monkeypatch.setattr('sys.platform', 'win32')
    monkeypatch.setattr('sys.frozen', False, raising=False)
    if local_appdata == 'configured':
        monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'local'))
        settings = tmp_path/'local'/'Proxy Transcript'
    else:
        monkeypatch.delenv('LOCALAPPDATA', raising=False)
        monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path/'xdg'))
        settings = tmp_path/'xdg'/'game-immersion-toolkit'

    settings.mkdir(parents=True)
    (settings/'languages.json').write_text(json.dumps({
        'prepared': {'halflife': {'en': {'targets': ['fr']}}},
        'selected': {'owned': {'halflife': 'en'}},
    }), encoding='utf-8')
    launch = tmp_path/'new-launch-directory'
    launch.mkdir()
    monkeypatch.chdir(launch)

    manager = LanguagePreparation(None, None, None)
    assert manager.selected('halflife', 'owned') == 'en'
    assert manager.path == settings/'languages.json'


def test_windows_source_invalid_settings_root_cannot_redirect_language_state_to_working_directory(tmp_path, monkeypatch):
    from backend.runtime_bundle import RuntimeBundleError

    monkeypatch.setattr('sys.platform', 'win32')
    monkeypatch.setattr('sys.frozen', False, raising=False)
    monkeypatch.setenv('LOCALAPPDATA', '')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeBundleError, match='settings_root must be an absolute path'):
        LanguagePreparation(None, None, None)


def test_macos_source_language_default_uses_selected_platform_root_without_legacy_dot_fallback(bundle_language_roots, monkeypatch):
    from backend import language_preparation
    roots = bundle_language_roots
    monkeypatch.setattr('sys.frozen', False, raising=False)
    monkeypatch.setattr('sys.platform', 'darwin')
    monkeypatch.setenv('LOCALAPPDATA', '')
    observed = []
    def selected():
        observed.append(roots.layout)
        return roots.layout
    monkeypatch.setattr(language_preparation, 'discover_layout', selected)
    manager = LanguagePreparation(None, None, None)
    assert manager.path == roots.layout.settings_root/'languages.json'
    assert observed == [roots.layout] and not manager.path.exists()
    assert all(path.read_bytes() == raw for path, raw in roots.before.items())


def test_real_frozen_language_discovery_validates_manifest_and_roots_without_source_fallback(bundle_language_roots, monkeypatch):
    import json
    from pathlib import Path
    from backend import language_preparation, runtime_bundle, runtime_paths
    roots = bundle_language_roots
    layout = roots.layout
    layout.resource_root.mkdir(parents=True)
    manifest = layout.resource_root/'runtime-manifest.json'
    manifest.write_text(json.dumps({'schema': runtime_bundle.MANIFEST_SCHEMA, 'profile': 'diagnostic',
        'version': '0.22.0', 'source_commit': 'a'*40, 'build_id': 'authored-language-path',
        'children': [], 'resources': {}}), encoding='utf-8')
    original = manifest.read_bytes()
    monkeypatch.setattr('sys._MEIPASS', str(layout.resource_root), raising=False)
    monkeypatch.setattr('sys.executable', str(layout.executable))
    for name, value in layout.child_environment(environ={}).items(): monkeypatch.setenv(name, value)
    monkeypatch.setattr(language_preparation, 'discover_layout', runtime_bundle.discover_layout)
    monkeypatch.setattr(runtime_paths, 'discover_layout', runtime_bundle.discover_layout)
    actual = runtime_bundle.discover_layout()
    assert actual.mode == 'bundle' and actual.settings_root == layout.settings_root
    manager = LanguagePreparation(lambda *_: None, lambda *_: None, lambda *_: {'ready': True})
    manager.request('zzz', 'zh-Hans', 'en', 'owned')
    finish(manager)
    assert manager.path == layout.settings_root/'languages.json'
    assert LanguagePreparation(None, None, None).selected('zzz', 'owned') == 'zh-Hans'
    with monkeypatch.context() as missing:
        missing.delenv('PROXY_TRANSCRIPT_SETTINGS_ROOT')
        with pytest.raises(runtime_bundle.RuntimeBundleError): LanguagePreparation(None, None, None)
    assert manifest.read_bytes() == original
    manifest.write_text('{}', encoding='utf-8')
    with pytest.raises(runtime_bundle.RuntimeBundleError): LanguagePreparation(None, None, None)
    explicit = Path('explicit-with-invalid-frozen-layout.json')
    assert LanguagePreparation(None, None, None, path=explicit).path is explicit
    assert not explicit.exists() and all(path.read_bytes() == raw for path, raw in roots.before.items())


def test_selected_snapshot_and_export_worker_reconstruct_bundle_defaults_without_host_account_move(bundle_language_roots, monkeypatch, capsys):
    import hashlib
    import json
    from types import SimpleNamespace
    from backend import accounts, game_assets, language_preparation, lexirise, lexirise_settings
    from backend import export_lock, game_paths, media_tools, mobile_export_worker
    roots = bundle_language_roots
    manager = LanguagePreparation(None, lambda *_: None, None)
    manager.data = {'prepared': {'halflife': {locale: {'targets': ['zh-Hans']} for locale in ('en', 'zh-Hans')}},
        'selected': {'owned': {'halflife': 'en'}}, 'selection_generations': {'owned': {'halflife': 4}},
        'requested': {'waiting-owner': {'beyond': {'locale': 'nl', 'target': 'en'}}}}
    manager._save()
    pending = manager.path.with_suffix('.requests.json').read_bytes()
    source = roots.layout.data_root/'languages/halflife/en/textmap.json'
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({'format': 2, 'game': 'halflife', 'source_locale': 'en',
        'targets_requested': ['zh-Hans'], 'install': str(roots.cwd/'absent-authored-install'), 'fingerprint': 'authored-index',
        'capture_capabilities': {'voiced': False, 'unvoiced': True}, 'records': [{
            'text_id': 'halflife:owned:message', 'english': 'Owned message', 'chinese': '合成消息',
            'source_locale': 'en', 'source_text': 'Owned message', 'audio_locale': 'en',
            'texts': {'en': 'Owned message', 'zh-Hans': '合成消息'}, 'audio': None,
            'voice_status': 'unvoiced', 'dialogue_kind': 'screen_message'}]}), encoding='utf-8')
    protected = SimpleNamespace(path=roots.accounts, status=lambda: {'active': 'owned'})
    monkeypatch.setattr(accounts, 'AccountStore', lambda: protected)
    assert language_preparation.selected_snapshot(roots.layout.application_root, 'halflife') == (source, protected, 'owned')

    def client(directory, *, accounts):
        assert directory == roots.layout.data_root/'lexirise' and accounts is protected
        return SimpleNamespace(pin=lambda language: SimpleNamespace(language=language))

    def preferences(client):
        assert client.language == 'en'
        return {'global': {'effectiveTranslationLanguage': 'zh-Hans'}, 'languageSettings': {}}

    monkeypatch.setattr(lexirise, 'LexiriseService', client)
    monkeypatch.setattr(lexirise_settings, 'account_settings', preferences)
    monkeypatch.setattr(game_assets, 'asset_adapter', lambda game: (SimpleNamespace(fingerprint=lambda _: 'authored-index'), None))
    monkeypatch.setattr(media_tools, 'vgmstream_executable', lambda _root: None)
    locks, exported = [], []
    monkeypatch.setattr(game_paths, 'settings_path', lambda: roots.layout.settings_root/'game-paths.json')
    monkeypatch.setattr(export_lock, 'ExportLock', lambda path: SimpleNamespace(
        acquire=lambda: locks.append(('acquire', path)) or True, close=lambda: locks.append(('close', path))))

    def export(game, records, output, *, check, **options):
        assert game == 'halflife' and records[0]['sourceLocale'] == 'en' and records[0]['translationText'] == '合成消息'
        assert options['include_audio'] is False and output == roots.layout.default_export_root
        check.force()
        manager.select('halflife', 'zh-Hans', 'owned')
        with pytest.raises(ValueError, match='changed'): check.force()
        manager.select('halflife', 'en', 'owned')
        # Same snapshot pathname after switching away/back still retires the
        # worker: both default generation reconstructions read bundle settings.
        with pytest.raises(ValueError, match='changed'): check.force()
        exported.append(True)

    monkeypatch.setattr(mobile_export_worker, 'export_library', export)
    monkeypatch.setattr('sys.argv', ['mobile-export', '--root', str(roots.layout.application_root),
        '--game', 'halflife', '--output', str(roots.layout.default_export_root), '--catalog-only',
        '--source-locale', 'en', '--account-signature', hashlib.sha256(roots.accounts.read_bytes()).hexdigest()])
    assert mobile_export_worker.main() == 0 and exported == [True]
    assert [action for action, _ in locks] == ['acquire', 'close']
    assert all(path == roots.layout.settings_root/'mobile-export.lock' for _, path in locks)
    assert LanguagePreparation(None, None, None).selection_generation('halflife', 'owned') == 6
    assert manager.path.with_suffix('.requests.json').read_bytes() == pending
    assert accounts.accounts_path() == roots.accounts
    assert all(path.read_bytes() == raw for path, raw in roots.before.items())
    assert not roots.layout.application_root.exists() and not (roots.cwd/'Proxy Transcript').exists()
    frames = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert frames and all(frame['state'] == 'exporting' for frame in frames)


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
    import threading
    runtime._locale_voice_lock = threading.RLock()
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
