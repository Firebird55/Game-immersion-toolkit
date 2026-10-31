"""Fixed, synthetic probes for an extracted experimental Windows runtime.

Not a launcher or acceptance override. Native OCR/capture, installed games,
accounts, ASR model inference and supervised updates remain separate gates.
"""
from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import threading

from .runtime_bundle import EXPERIMENT_CHILDREN, RuntimeBundleError
from .runtime_probe_common import synthetic_roots, block_remote_access, loaded_native, developer_environment


def worker(layout, kind, arguments, *, expected_status=0):
    result = subprocess.run(layout.child_command(kind, arguments), env=layout.child_environment(kind),
        cwd=layout.work_root, capture_output=True, timeout=90)
    if result.returncode != expected_status:
        # Raw child output can contain private paths and fixture text.
        raise RuntimeBundleError('Frozen synthetic worker failed: ' + kind)
    return result


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
    for kind in EXPERIMENT_CHILDREN:
        if kind not in {'frontend', 'windows-bootstrap', 'asr', 'capture-readiness', 'update-voice'}:
            worker(layout, kind, ['--help'])
    from .unvoiced_export_probe import probe as export_probe
    unvoiced_export = export_probe(layout, lambda kind, arguments, **options: worker(layout, kind, arguments, **options))
    from .source_pcm_probe import probe as source_pcm_probe
    source_pcm = source_pcm_probe(layout, lambda kind, arguments, **options: worker(layout, kind, arguments, **options))
    return {'registry_readers_imported': len(GAMES), 'real_vad_silence': 'passed', 'nte_bridge_runtime': identity,
        'codec': codec, 'source_pcm': source_pcm,
        'game_index_worker': 'authored-format-passed', 'language_worker': 'authored-format-passed',
        'export': 'authored-unvoiced-worker-roundtrip; voiced-export-not-verified', 'unvoiced_export': unvoiced_export,
        'worker_entrypoints': [kind for kind in EXPERIMENT_CHILDREN if kind not in
            {'frontend', 'windows-bootstrap', 'asr', 'capture-readiness', 'update-voice'}],
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


def api(layout, *, wal_probe=False):
    # Patch external side effects only in this fixed probe process. The ordinary
    # API child is unchanged. Its real Runtime, SQLite, routes and WS run here.
    if type(wal_probe) is not bool:
        raise RuntimeBundleError('Unknown fixed authored API policy.')
    if wal_probe and 'backend.api' in sys.modules:
        raise RuntimeBundleError('Authored WAL API import was not isolated.')
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
    if kind in {'api', 'api-wal'}:
        if kind == 'api-wal' and sys.version_info[:3] != (3, 12, 16):
            raise RuntimeBundleError('Authored WAL probe requires its exact reviewed Python supplier.')
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
