"""Fixed, synthetic probes for an extracted experimental Windows runtime.

Not a launcher or acceptance override. Native OCR/capture, installed games,
accounts, ASR model inference and supervised updates remain separate gates.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys

from .runtime_bundle import EXPERIMENT_CHILDREN, RuntimeBundleError
from .runtime_probe_common import synthetic_roots, block_remote_access, loaded_native


def worker(layout, kind, arguments):
    result = subprocess.run(layout.child_command(kind, arguments), env=layout.child_environment(kind),
        cwd=layout.work_root, capture_output=True, timeout=90)
    if result.returncode:
        # Raw child output can contain private paths and fixture text.
        raise RuntimeBundleError('Frozen synthetic worker failed: ' + kind)


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
    for kind in EXPERIMENT_CHILDREN:
        if kind not in {'frontend', 'windows-bootstrap', 'asr', 'capture-readiness', 'update-voice'}:
            worker(layout, kind, ['--help'])
    fixture = layout.work_root / 'authored-goldsrc'
    for name, content in {
        'hl.exe': b'owned fixture marker, not an executable',
        'valve/liblist.gam': b'game "Owned runtime fixture"',
        'valve/titles.txt': b'CARD\n{\nAuthored runtime fixture\n}\n',
        'valve_schinese/titles.txt': 'CARD\n{\n\u4e2d\u6587\u6d4b\u8bd5\n}\n'.encode('gbk'),
    }.items():
        path = fixture / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    index = layout.work_root / 'index.json'
    language = layout.work_root / 'language.json'
    worker(layout, 'game-index', ['--game', 'halflife', '--install', str(fixture),
        '--directory', str(layout.work_root), '--output', str(index)])
    worker(layout, 'language', ['--game', 'halflife', '--install', str(fixture),
        '--directory', str(layout.work_root), '--output', str(language), '--locale', 'en', '--targets', '["zh-Hans"]'])
    records = json.loads(language.read_text(encoding='utf-8'))['records']
    if not json.loads(index.read_text(encoding='utf-8'))['records'] or not any(
            row['source_text'] == 'Authored runtime fixture' and row['texts'].get('zh-Hans') == '\u4e2d\u6587\u6d4b\u8bd5' for row in records):
        raise RuntimeBundleError('Frozen worker fixture identity/language was lost.')
    from .mobile_library import export_library
    destination = layout.default_export_root / 'authored-catalog'
    export_library('halflife', [{'textId': 'halflife:owned-runtime-fixture', 'english': 'Authored runtime fixture',
        'chinese': '\u4e2d\u6587\u6d4b\u8bd5', 'channels': ['dialogue']}], destination, include_audio=False)
    return {'registry_readers_imported': len(GAMES), 'real_vad_silence': 'passed',
        'game_index_worker': 'authored-format-passed', 'language_worker': 'authored-format-passed',
        'export': 'authored-catalog-library-only; worker-help-only',
        'worker_entrypoints': [kind for kind in EXPERIMENT_CHILDREN if kind not in
            {'frontend', 'windows-bootstrap', 'asr', 'capture-readiness', 'update-voice'}],
        'native_ocr_capture': 'not-run; proprietary files and Windows 11 required',
        'voice_refresh': 'not-run; game helper rights gate open', 'loaded_native': loaded_native(layout)}


def api(layout):
    # Patch external side effects only in this fixed probe process. The ordinary
    # API child is unchanged. Its real Runtime, SQLite, routes and WS run here.
    from unittest.mock import patch
    from contextlib import ExitStack
    from . import game_paths
    from .accounts import AccountStore
    with ExitStack() as stack:
        for name in ('discover_install', 'configured_install'):
            stack.enter_context(patch.object(game_paths, name, lambda *_a, **_k: None))
        from . import api as service
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
    sys.addaudithook(block_remote_access)
    if kind == 'api':
        return api(layout)
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
