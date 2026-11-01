"""Fixed, synthetic probes for an extracted experimental Windows runtime.

Not a launcher or acceptance override. Native OCR/capture, installed games,
accounts, ASR model inference and supervised updates remain separate gates.
"""
from __future__ import annotations

import importlib
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import threading

from .runtime_bundle import EXPERIMENT_CHILDREN, RuntimeBundleError
from .runtime_probe_common import synthetic_roots, block_remote_access, loaded_native, developer_environment

GRAMMAR_TEXT = '这是保留的中文。'
GRAMMAR_SLUG = 'r19-authored-rule'
GRAMMAR_ABSENT_SLUG = 'r19-absent-rule'
GRAMMAR_KEY = 'r19-grammar-fixture-not-a-credential'
GRAMMAR_CHOICE_KEY = hashlib.sha256(GRAMMAR_KEY.encode()).hexdigest()+':zh:'+GRAMMAR_SLUG

POPULATED_KEY = 'lx_r19_authored_profile_one_only'
POPULATED_OTHER_KEY = 'lx_r19_authored_profile_two_only'
POPULATED_RULES = ('r19-populated-known', 'r19-populated-learning')


def authored_test_protect(data, *, decrypt=False):
    """Visibly authored envelope only; never DPAPI, a key locator or a fallback."""
    if type(data) is not bytes or type(decrypt) is not bool or len(data) > 8192:
        raise ValueError('Unknown authored account envelope.')
    if decrypt:
        if not data.startswith(b'R19-TEST\x00'):
            raise ValueError('Unknown authored account envelope.')
        return data[9:]
    return b'R19-TEST\x00'+data


def populated_roots(layout):
    """Fixed private role derivation, not roots learned from a control record."""
    import tempfile
    import uuid
    from .bundle_host import SyntheticRoot
    from .runtime_data_copy_probe import _guard_path
    root = layout.settings_root
    if (layout.mode != 'bundle' or layout.profile != 'runtime-experiment'
            or root.name != 'legacy' or root.parent.name != 'p2-native'
            or not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or layout.data_root != root/'data' or layout.cache_root != root/'cache-v1'
            or layout.work_root != root/'cache-v1/work' or layout.tool_root != root/'tools-v1'
            or layout.state_root != root/'probe-state' or layout.default_export_root != root/'exports'):
        raise RuntimeBundleError('Authored populated role roots differ.')
    roots = {}
    for name in ('legacy', 'private-target', 'external-state', 'host-profile'):
        path = root.parent/name
        _guard_path(path, 'directory')
        marker = path/'.r19-synthetic-fixture.json'
        if _guard_path(marker, 'file').st_size > 4096:
            raise RuntimeBundleError('Authored populated marker differs.')
        with marker.open('rb') as stream:
            value = json.loads(stream.read(4097))
        if type(value) is not dict or set(value) != {'schema', 'fixture_id', 'installation_id'}:
            raise RuntimeBundleError('Authored populated marker differs.')
        for key in ('fixture_id', 'installation_id'):
            if type(value[key]) is not str or str(uuid.UUID(value[key])) != value[key]:
                raise RuntimeBundleError('Authored populated marker identity differs.')
        owned = roots[name] = SyntheticRoot(path, value['fixture_id'], value['installation_id'])
        owned.verify()
    if len({owned.installation_id for owned in roots.values()}) != 1:
        raise RuntimeBundleError('Authored populated installations differ.')
    return roots


class _AuthoredPopulatedAPI:
    """Strict factories return real owners; account and remote effects are TEST only."""
    def __init__(self, layout, service):
        from .accounts import AccountStore, accounts_path
        from .automatic_mobile_export import AutomaticMobileExports
        from .lexirise import LexiriseService
        from .runtime_data_copy_probe import _guard_path
        self.layout, self.service, self.roots, self.guard = layout, service, populated_roots(layout), _guard_path
        if (service.RUNTIME_LAYOUT != layout or service.DATA_DIR != layout.data_root
                or service._SQL_LEDGER_TYPE is not LexiriseService):
            raise RuntimeBundleError('Authored populated API layout differs.')
        self.account_type, self.ledger_type, self.automatic_type = AccountStore, LexiriseService, AutomaticMobileExports
        self.transport = AuthoredPopulatedTransport(writes=False)
        self.owners = []
        self.account = self.ledger = self.automatic = self.runtime = None
        self.failure = None
        self.account_path = layout.settings_root/'credentials/accounts.dpapi'
        if accounts_path() != self.account_path:
            raise RuntimeBundleError('Authored populated credential layout differs.')
        self.account_bytes = self._read_account_bytes()
        first, second = (hashlib.sha256(value).hexdigest()[:24] for value in (b'r19-one', b'r19-two'))
        expected = {'active':first, 'profiles':{
            first:{'key':POPULATED_KEY, 'name':'Authored first profile'},
            second:{'key':POPULATED_OTHER_KEY, 'name':'Authored second profile'}}}
        if json.loads(authored_test_protect(self.account_bytes, decrypt=True)) != expected:
            raise RuntimeBundleError('Authored populated TEST profiles differ.')

    def _read_account_bytes(self):
        if self.guard(self.account_path, 'file').st_size > 8192:
            raise RuntimeBundleError('Authored populated TEST envelope exceeds its bound.')
        with self.account_path.open('rb') as stream:
            value = stream.read(8193)
        if len(value) > 8192:
            raise RuntimeBundleError('Authored populated TEST envelope exceeds its bound.')
        return value

    def _own(self, kind, *args, **kwargs):
        if self.failure is not None:
            raise RuntimeBundleError('Authored populated constructor cleanup remains unconfirmed.') from self.failure
        owner = object.__new__(kind)
        self.owners.append(owner)  # Preserve real partial constructors on any failure.
        try:
            kind.__init__(owner, *args, **kwargs)
            return owner
        except BaseException as error:
            self.failure = error
            raise

    def accounts(self, *args, **options):
        if self.failure is not None or args or options or self.account is not None:
            raise RuntimeBundleError('Authored populated account constructor differs.')
        self.guard(self.account_path, 'file')
        self.account = self._own(self.account_type, self.account_path, protect=authored_test_protect,
                                  transport=self.transport.transport)
        status = self.account.status()
        if (self.account.active_key() != POPULATED_KEY or len(status['profiles']) != 2
                or status['active'] == 'legacy' or self._read_account_bytes() != self.account_bytes):
            raise RuntimeBundleError('Authored populated account fixture differs.')
        return self.account

    def lexirise(self, directory, *args, **options):
        expected = self.layout.data_root/'lexirise'
        if (self.failure is not None or args or set(options) != {'accounts'} or self.account is None
                or options['accounts'] is not self.account or directory != expected or self.ledger is not None):
            raise RuntimeBundleError('Authored populated ledger constructor differs.')
        self.guard(expected, 'directory')
        self.ledger = self._own(self.ledger_type, expected, accounts=self.account,
            api_key=POPULATED_KEY, transport=self.transport.transport)
        return self.ledger

    def automatic_exports(self, root, *args, **options):
        if (self.failure is not None or self.runtime is None or args or root != self.service.PROJECT_ROOT or set(options) != {'install_lookup'}
                or options['install_lookup'] != self.runtime.setup_install or self.automatic is not None):
            raise RuntimeBundleError('Authored populated automatic constructor differs.')
        home = self.roots['external-state'].path/'automatic'
        self.guard(home, 'directory')
        self.automatic = self._own(self.automatic_type, root, home=home, **options)
        return self.automatic

    def initialize(self, runtime, initialize):
        if self.runtime is not None:
            raise RuntimeBundleError('Authored populated Runtime was already initialized.')
        self.runtime = runtime
        try:
            initialize(runtime)
            self.check_runtime(runtime)
        except BaseException as error:
            self.failure = error
            raise

    def check_runtime(self, runtime):
        from .storage import TranscriptStore
        from .reading import LexiriseReadingService
        layout = self.layout
        checks = {'runtime': runtime is self.runtime and runtime.standby,
            'accounts': runtime.accounts is self.account and runtime.accounts.path == self.account_path,
            'ledger': runtime.lexirise is self.ledger,
            'automatic': runtime.automatic_exports is self.automatic,
            'transcript': type(runtime.transcript) is TranscriptStore and runtime.transcript.path == layout.data_root/'transcript-v2.db',
            'reading': type(runtime.reading) is LexiriseReadingService and runtime.reading.path == layout.data_root/'lexirise/reading-cache-v2.db',
            'settings': runtime.settings.path == layout.settings_root/'settings.json',
            'languages': runtime.languages.path == layout.settings_root/'languages.json',
            'installation': runtime.installation.completed,
            'requests': any('fr' in targets for _game, _locale, targets in runtime.languages.entries()),
            'opaque-account': self._read_account_bytes() == self.account_bytes}
        for name, confirmed in checks.items():
            if confirmed is not True:
                raise RuntimeBundleError('Authored populated normal owner differs: '+name)


@contextmanager
def authored_populated_api(layout, service):
    """One fixed probe-only construction context; normal API/routes are untouched."""
    from contextlib import ExitStack
    from unittest.mock import patch
    policy = _AuthoredPopulatedAPI(layout, service)
    initialize = service.Runtime.__init__
    def authored_install(_runtime, game):
        if game != 'halflife':
            return None
        path = policy.roots['external-state'].path/'authored-install'
        policy.guard(path, 'directory')
        return path
    with ExitStack() as stack:
        stack.enter_context(patch.object(service, 'runtime', getattr(service, 'runtime', None), create=True))
        stack.enter_context(patch.object(service.Runtime, 'setup_install', authored_install))
        stack.enter_context(patch.object(service, 'AccountStore', policy.accounts))
        stack.enter_context(patch.object(service, 'LexiriseService', policy.lexirise))
        stack.enter_context(patch.object(service, 'AutomaticMobileExports', policy.automatic_exports))
        stack.enter_context(patch.object(service.Runtime, '__init__', lambda runtime: policy.initialize(runtime, initialize)))
        yield policy


def populated_api(layout):
    if 'backend.api' in sys.modules:
        raise RuntimeBundleError('Authored populated API import was not isolated.')
    populated_roots(layout)
    from unittest.mock import patch
    from contextlib import ExitStack
    from . import game_paths
    with ExitStack() as stack:
        for name in ('discover_install', 'configured_install'):
            stack.enter_context(patch.object(game_paths, name, lambda *_a, **_k: None))
        service = importlib.import_module('backend.api')
        stack.enter_context(authored_populated_api(layout, service))
        async def no_ocr(_self):
            return None
        stack.enter_context(patch.object(service.Runtime, 'start_updates', lambda _self: None))
        stack.enter_context(patch.object(service.CaptureService, 'warmup', no_ocr))
        import uvicorn
        uvicorn.run(service.app, host='127.0.0.1', port=8766, log_level='warning', access_log=False)
    return 0


class AuthoredPopulatedTransport:
    """Finite normal-service mock; no real credentials or catch-all responses."""
    def __init__(self, *, writes=True):
        import httpx
        if type(writes) is not bool:
            raise RuntimeBundleError('Authored populated transport policy differs.')
        self.writes, self.calls, self.items, self.members = writes, [], [], []
        self.transport = httpx.MockTransport(self.reply)

    def reply(self, request):
        import httpx
        if (len(self.calls) >= 128 or request.url.scheme != 'https'
                or request.url.host != 'api.lexirise.app' or request.url.port not in {None, 443}
                or request.url.fragment or len(request.content) > 8192):
            raise RuntimeBundleError('Authored populated transport identity differs.')
        key = request.headers.get('Authorization')
        if key not in {'Bearer '+POPULATED_KEY, 'Bearer '+POPULATED_OTHER_KEY}:
            raise RuntimeBundleError('Authored populated credential differs.')
        method, path = request.method, request.url.path
        self.calls.append((method, path))
        if method == 'GET' and path == '/v1/me' and not request.url.query and not request.content:
            return httpx.Response(200, json={'user': {'id': 'r19-one' if key.endswith(POPULATED_KEY) else 'r19-two'}})
        if key != 'Bearer '+POPULATED_KEY:
            raise RuntimeBundleError('Authored second profile permits identity verification only.')
        if method == 'GET' and path == '/v1/settings' and not request.url.query and not request.content:
            return httpx.Response(200, json={'languages': ['zh'], 'global': {'effectiveTranslationLanguage': 'en'},
                'languageSettings': {'zh': {'effectiveTranslationLanguage': 'en'}}})
        if method == 'POST' and path == '/v1/analyze/text' and not request.url.query:
            if json.loads(request.content) != {'text': GRAMMAR_TEXT, 'language': 'zh', 'fast': False}:
                raise RuntimeBundleError('Authored populated analysis differs.')
            return httpx.Response(200, json={'occurrences': [{'charStart': 0, 'charEnd': 1, 'word': '这',
                    'isWordLike': True, 'entryId': 1}], 'entryMetaById': {'1': {'gloss': 'authored demonstrative'}},
                'stateByEntryId': {'1': {'proficiency': 4}},
                'morphoPending': False, 'grammar': [{'slug': slug, 'title': 'Authored rule', 'indices': [0]}
                    for slug in POPULATED_RULES],
                'grammarStates': dict(zip(POPULATED_RULES, (0, 4)))})
        query = dict(request.url.params)
        unique_query = len(request.url.params.multi_items()) == len(query)
        if (method == 'GET' and path == '/v1/decks/1901' and unique_query
                and query in ({'limit': '1'}, {'limit': '100', 'offset': '0'}) and not request.content):
            return httpx.Response(200, json={'deck': {'owner_user_id': 'r19-one', 'lang': 'zh',
                'unit_type': 'sentence', 'deck_type': 'snapshot', 'title': 'Authored deck'},
                'items': self.members, 'hasMore': False})
        if (method == 'GET' and path == '/v1/vocabulary' and unique_query and query == {
                'language': 'zh', 'mode': 'sentences', 'search': GRAMMAR_TEXT, 'limit': '100', 'offset': '0'}
                and not request.content):
            return httpx.Response(200, json={'items': self.items, 'nextOffset': None})
        if not self.writes:
            raise RuntimeBundleError('Copied export ledger attempted a remote write.')
        if method == 'POST' and path == '/v1/vocabulary' and not request.url.query:
            body = json.loads(request.content)
            if (set(body) != {'language', 'text', 'mode', 'notes', 'tags', 'audioUrls', 'translation'}
                    or body['text'] != GRAMMAR_TEXT or body['language'] != 'zh'
                    or body['mode'] != 'sentence' or body['tags'] != ['zzz'] or body['audioUrls'] != []):
                raise RuntimeBundleError('Authored populated export differs.')
            item = {'id': 777, 'expression_text': GRAMMAR_TEXT, 'audio_urls': []}
            self.items.append(item)
            return httpx.Response(200, json={'item': item})
        if method == 'POST' and path == '/v1/decks/1901/items' and not request.url.query:
            if json.loads(request.content) != {'saved_expression_selection': {'mode': 'explicit', 'ids': [777]}} or len(self.items) != 1:
                raise RuntimeBundleError('Authored populated membership differs.')
            self.members = list(self.items)
            return httpx.Response(200, json={'success': True, 'added_count': 1})
        raise RuntimeBundleError('Unknown authored populated transport request.')


@contextmanager
def authored_populated_layout(layout, host_root):
    """Fixed authored service wiring only; never an ordinary Runtime entrypoint."""
    from contextlib import ExitStack
    from unittest.mock import patch
    from . import automatic_mobile_export, installation, mobile_export_controls, runtime_bundle, runtime_paths
    from .runtime_data_copy_probe import _guard_path
    _guard_path(host_root.path, 'directory')
    host_root.verify()
    with ExitStack() as stack:
        stack.enter_context(patch.dict('os.environ', {'LOCALAPPDATA': str(host_root.path)}))
        for module in (runtime_bundle, installation, runtime_paths):
            stack.enter_context(patch.object(module, 'discover_layout', lambda: layout))
        stack.enter_context(patch.object(mobile_export_controls, 'discover_install', lambda *_: None))
        stack.enter_context(patch.object(automatic_mobile_export, 'resource_path', layout.resource))
        yield


class _AuthoredGrammarService:
    """Actual service/SQL; only fixed external settings and analysis are mocked."""
    def __init__(self, layout, service_type):
        import httpx
        from .runtime_data_copy_probe import _guard_path
        self.layout, self.service_type, self.guard = layout, service_type, _guard_path
        self.directory = layout.data_root/'lexirise'
        self.constructed = False
        self.calls = 0
        self.lock = threading.Lock()
        self.transport = httpx.MockTransport(self.reply)

    def create(self, directory, *args, **options):
        from .accounts import AccountStore
        if (not isinstance(directory, (Path, str)) or Path(directory) != self.directory or args
                or set(options) != {'accounts'} or type(options['accounts']) is not AccountStore
                or options['accounts'].path != self.layout.work_root/'absent-test-account.dpapi'):
            raise RuntimeBundleError('Authored grammar service selection differs.')
        self.guard(self.layout.data_root, 'directory')
        self.guard(Path(directory), 'directory', missing=True)
        if self.guard(options['accounts'].path, 'file', missing=True) is not None:
            raise RuntimeBundleError('Authored grammar account fixture must be absent.')
        if Path(directory).resolve() != self.directory:
            raise RuntimeBundleError('Authored grammar service identity differs.')
        with self.lock:
            if self.constructed:
                raise RuntimeBundleError('Authored grammar service was already constructed.')
            self.constructed = True
        return self.service_type(directory, accounts=options['accounts'], api_key=GRAMMAR_KEY,
                                 transport=self.transport)

    def reply(self, request):
        import httpx
        with self.lock:
            if self.calls >= 16:
                raise RuntimeBundleError('Authored grammar transport bound exceeded.')
            self.calls += 1
        if (request.url.scheme != 'https' or request.url.host != 'api.lexirise.app'
                or request.url.port not in {None, 443} or request.url.query or request.url.fragment
                or request.headers.get('Authorization') != 'Bearer '+GRAMMAR_KEY):
            raise RuntimeBundleError('Authored grammar transport identity differs.')
        if request.method == 'GET' and request.url.path == '/v1/settings' and not request.content:
            return httpx.Response(200, json={'languages': ['zh'],
                'global': {'effectiveTranslationLanguage': 'en'},
                'languageSettings': {'zh': {'effectiveTranslationLanguage': 'en'}}})
        if request.method != 'POST' or request.url.path != '/v1/analyze/text' or len(request.content) > 4096:
            raise RuntimeBundleError('Authored grammar transport request differs.')
        def unique(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise RuntimeBundleError('Authored grammar request fields differ.')
                value[key] = item
            return value
        try:
            body = json.loads(request.content, object_pairs_hook=unique)
        except (ValueError, UnicodeError):
            raise RuntimeBundleError('Authored grammar request body differs.') from None
        if (type(body) is not dict or set(body) != {'text', 'language', 'fast'}
                or body['text'] != GRAMMAR_TEXT or body['language'] != 'zh' or body['fast'] is not False):
            raise RuntimeBundleError('Authored grammar request body differs.')
        return httpx.Response(200, json={
            'occurrences': [{'charStart': 0, 'charEnd': 1, 'word': '这', 'isWordLike': True, 'entryId': 1}],
            'entryMetaById': {'1': {'gloss': 'authored demonstrative'}},
            'stateByEntryId': {'1': {'proficiency': 4}}, 'morphoPending': False,
            'grammar': [{'slug': GRAMMAR_SLUG, 'title': 'Owned fixture rule', 'level': 'authored', 'indices': [0]}],
            'grammarStates': {GRAMMAR_SLUG: 0}})


def worker(layout, kind, arguments, *, expected_status=0):
    result = subprocess.run(layout.child_command(kind, arguments), env=layout.child_environment(kind),
        cwd=layout.work_root, capture_output=True, timeout=90)
    if result.returncode != expected_status:
        # Raw child output can contain private paths and fixture text.
        raise RuntimeBundleError('Frozen synthetic worker failed: ' + kind)
    return result


def worker_entrypoints(layout):
    checked = []
    for kind in EXPERIMENT_CHILDREN:
        if kind not in {'frontend', 'windows-bootstrap', 'asr', 'capture-readiness', 'update-voice'}:
            # The binary capture worker has no help CLI. Invalid arguments must
            # refuse before opening a capture session, with its exact status2.
            result = worker(layout, kind, ['--help'], expected_status=2 if kind == 'window-capture' else 0)
            if kind == 'window-capture' and (result.stdout != b'' or result.stderr != b''):
                # Dispatcher refusals also use2 but emit a diagnostic. Never
                # promote those, or private child output, to an entrypoint pass.
                raise RuntimeBundleError('Frozen synthetic worker failed: ' + kind)
            checked.append(kind)
    return checked


def native(layout):
    import numpy as np
    # These imports exercise native loaders in the extracted process, including
    # dynamic registry readers which ordinary source imports cannot prove frozen.
    for name in ('cv2', 'PIL.Image', 'windows_capture', 'pyaudiowpatch', 'oneocr',
                 'Crypto.Cipher.AES', 'rapidfuzz', 'opencc', 'pypinyin', 'scipy.signal'):
        importlib.import_module(name)
    from .game_assets import asset_adapter
    from .game_paths import GAMES
    for game in GAMES:
        asset_adapter(game)
    from .firered_vad import FireRedVad
    segments = FireRedVad().segments(np.zeros(16000, dtype=np.float32), 16000)
    if segments:
        raise RuntimeBundleError('Real bundled VAD produced speech for authored silence.')
    layout.work_root.mkdir(parents=True, exist_ok=True)
    from .prebuilt_readers import prebuilt_reader, reader_environment
    helper = prebuilt_reader('nte', layout=layout)
    result = subprocess.run(helper.runtime_identity_command(), env=reader_environment(), cwd=layout.work_root,
        capture_output=True, timeout=20, check=True)
    identity = json.loads(result.stdout)
    if (identity.get('schema') != 'proxy-nte-runtime-identity-v1' or identity.get('runtime_origin') != 'app-local'
            or identity.get('runtime_version') != '10.0.14' or identity.get('game_execution_approved') is not False
            or identity.get('corelib_sha256') != helper.manifest['files']['System.Private.CoreLib.dll']['sha256']):
        raise RuntimeBundleError('The collected NTE bridge did not use its own exact runtime.')
    from .codec_probe import probe as codec_probe
    codec = codec_probe(layout)
    entrypoints = worker_entrypoints(layout)
    from .unvoiced_export_probe import probe as export_probe
    unvoiced_export = export_probe(layout, lambda kind, arguments, **options: worker(layout, kind, arguments, **options))
    from .source_pcm_probe import probe as source_pcm_probe
    source_pcm = source_pcm_probe(layout, lambda kind, arguments, **options: worker(layout, kind, arguments, **options))
    return {'registry_readers_imported': len(GAMES), 'real_vad_silence': 'passed', 'nte_bridge_runtime': identity,
        'codec': codec, 'source_pcm': source_pcm,
        'game_index_worker': 'authored-format-passed', 'language_worker': 'authored-format-passed',
        'export': 'authored-unvoiced-worker-roundtrip; voiced-export-not-verified', 'unvoiced_export': unvoiced_export,
        'worker_entrypoints': entrypoints,
        'native_ocr_capture': 'not-run; proprietary files and Windows 11 required',
        'voice_refresh': 'not-run; game helper rights gate open', 'loaded_native': loaded_native(layout)}


class _AuthoredWalConnections:
    """Only the three fixed authored stores; no successful connection retention."""
    def __init__(self, layout, connect):
        import sqlite3
        from .runtime_data_copy_probe import _guard_path
        self.guard = _guard_path
        self.guard(layout.data_root, 'directory')
        self.root = layout.data_root
        self.paths = {self.root/'transcript-v2.db': 'transcript',
            self.root/'lexirise/exports-v2.db': 'exports',
            self.root/'lexirise/reading-cache-v2.db': 'reading'}
        self.original = connect
        self.configured = set()
        self.opens = 0
        self.lock = threading.Lock()
        if (not callable(getattr(sqlite3.Connection, 'setconfig', None))
                or not callable(getattr(sqlite3.Connection, 'getconfig', None))
                or type(getattr(sqlite3, 'SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE', None)) is not int):
            raise RuntimeBundleError('Authored WAL configuration is unavailable.')
        self.option = sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE

    def connect(self, database, *args, **options):
        # No caller-controlled URI, memory database, factory or alternate root.
        if (not isinstance(database, (str, Path)) or args or 'uri' in options or 'factory' in options
                or type(database) is str and (database.startswith('file:') or database == ':memory:')):
            raise RuntimeBundleError('Authored WAL database selection differs.')
        path = Path(database)
        if path not in self.paths:
            raise RuntimeBundleError('Authored WAL database selection differs.')
        self.guard(self.root, 'directory')
        self.guard(path, 'file', missing=True)  # Raw ancestors before resolve/open.
        if path.resolve() != path:
            raise RuntimeBundleError('Authored WAL database identity differs.')
        with self.lock:
            if self.opens >= 256:
                raise RuntimeBundleError('Authored WAL connection bound exceeded.')
            self.opens += 1
        connection = self.original(database, **options)
        try:
            connection.setconfig(self.option, True)
            if connection.getconfig(self.option) is not True:
                raise RuntimeBundleError('Authored WAL configuration readback differs.')
        except BaseException:
            try:
                connection.close()
            except BaseException:
                raise RuntimeBundleError('Authored WAL connection cleanup is unconfirmed.') from None
            raise RuntimeBundleError('Authored WAL configuration is unavailable.') from None
        with self.lock:
            self.configured.add(self.paths[path])
        return connection

    def require_stores(self):
        with self.lock:
            if self.configured != {'transcript', 'exports', 'reading'}:
                raise RuntimeBundleError('Authored WAL constructor configuration is incomplete.')

    def begin_constructor(self):
        with self.lock:
            if self.opens or self.configured:
                raise RuntimeBundleError('Authored WAL stores opened before the fixed Runtime constructor.')


@contextmanager
def _authored_wal_connections(layout):
    import sqlite3
    from unittest.mock import patch
    policy = _AuthoredWalConnections(layout, sqlite3.connect)
    with patch.object(sqlite3, 'connect', policy.connect):
        yield policy


def api(layout, *, wal_probe=False, grammar_probe=False):
    # Patch external side effects only in this fixed probe process. The ordinary
    # API child is unchanged. Its real Runtime, SQLite, routes and WS run here.
    if type(wal_probe) is not bool or type(grammar_probe) is not bool or wal_probe and grammar_probe:
        raise RuntimeBundleError('Unknown fixed authored API policy.')
    if wal_probe and 'backend.api' in sys.modules:
        raise RuntimeBundleError('Authored WAL API import was not isolated.')
    if grammar_probe and 'backend.api' in sys.modules:
        raise RuntimeBundleError('Authored grammar API import was not isolated.')
    from unittest.mock import patch
    from contextlib import ExitStack
    from . import game_paths
    from .accounts import AccountStore
    with ExitStack() as stack:
        for name in ('discover_install', 'configured_install'):
            stack.enter_context(patch.object(game_paths, name, lambda *_a, **_k: None))
        policy = stack.enter_context(_authored_wal_connections(layout)) if wal_probe else None
        if wal_probe and 'backend.api' in sys.modules:
            raise RuntimeBundleError('Authored WAL API import was not isolated.')
        service = importlib.import_module('backend.api')
        if grammar_probe:
            grammar = _AuthoredGrammarService(layout, service.LexiriseService)
            stack.enter_context(patch.object(service, 'LexiriseService', grammar.create))
        if policy is not None:
            initialize = service.Runtime.__init__
            constructed = False
            def authored_runtime(runtime):
                nonlocal constructed
                if constructed:
                    raise RuntimeBundleError('Authored WAL runtime was already initialized.')
                constructed = True
                policy.begin_constructor()
                initialize(runtime)
                policy.require_stores()  # All three actual constructor paths, before readiness.
            stack.enter_context(patch.object(service.Runtime, '__init__', authored_runtime))
        async def no_ocr(_self):
            return None
        stack.enter_context(patch.object(service.Runtime, 'start_updates', lambda _self: None))
        stack.enter_context(patch.object(service.CaptureService, 'warmup', no_ocr))
        stack.enter_context(patch.object(service, 'AccountStore', lambda: AccountStore(path=layout.work_root / 'absent-test-account.dpapi')))
        import uvicorn
        uvicorn.run(service.app, host='127.0.0.1', port=8766, log_level='warning', access_log=False)
    return 0


def main(kind, layout):
    if sys.platform != 'win32':
        raise RuntimeBundleError('Extracted native probes require Windows x64.')
    synthetic_roots(layout)
    developer_environment()
    sys.addaudithook(block_remote_access)
    if kind == 'api-populated':
        return populated_api(layout)
    if kind in {'api', 'api-wal', 'api-grammar'}:
        if kind == 'api-wal' and sys.version_info[:3] != (3, 12, 16):
            raise RuntimeBundleError('Authored WAL probe requires its exact reviewed Python supplier.')
        if kind == 'api-grammar':
            return api(layout, grammar_probe=True)
        return api(layout, wal_probe=kind == 'api-wal')
    try:
        details = native(layout)
    except Exception as error:
        failure = {'type': type(error).__name__}
        if isinstance(error, ModuleNotFoundError):
            failure['module'] = error.name
        elif isinstance(error, RuntimeBundleError):
            failure['contract'] = str(error)
        print(json.dumps({'status': 'failed', 'kind': kind, 'error': failure}))
        return 2
    print(json.dumps({'schema': 'proxy-r19-runtime-probe-v1', 'source_commit': layout.source_commit,
        'build_id': layout.build_id, 'kind': kind, 'status': 'passed', 'details': details,
        'real_accounts_accessed': False, 'installed_game_probe': 'not-run', 'rights_review': 'pending-exact-output',
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}))
    return 0
