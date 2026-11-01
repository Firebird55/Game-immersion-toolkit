"""Exercise the actual bundled NTE/Wuwa providers on authored compressed archives.

No game files, archive keys, accounts, source compiler or machine runtime are
used. Python runs this build-host probe; the child is the self-contained apphost.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import nte_toolchain
from backend.node_tools import host_platform
from backend.owned_process import OwnedProcess
from backend.prebuilt_readers import _no_links, _source_names, prebuilt_reader, reader_environment, RUNTIME
from backend.runtime_bundle import RuntimeLayout, relative_resource

RESOURCE_SOURCES = {'scripts/build-nte-toolchain.py', 'backend/nte_toolchain.py',
                    'packaging/game-readers/managed-components.json'}
ZERO_KEY = '0x' + '0' * 64  # Authored unencrypted archives; never a game key.
VOICE_LOCALES = {'Chinese': 'zh', 'English': 'en', 'Japanese': 'ja', 'Korean': 'ko'}
WUWA_PREFIX = 'Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/'
CONFIG_PATH = 'Client/Content/Aki/ConfigDB/db_plot_audio.db'
WUWA_OPERATIONS = {WUWA_PREFIX + suffix: role for suffix, role in (
    ('zh_owned.wem', 'wuwa-extract-zh'), ('en_owned.wem', 'wuwa-extract-en'),
    ('ja_owned.wem', 'wuwa-extract-ja'), ('ko_owned.wem', 'wuwa-extract-ko'))}
WUWA_OPERATIONS[CONFIG_PATH] = 'wuwa-extract-config'
CHECKS = ('app_local_runtime_identity', 'nte_real_provider_inventory',
          'nte_managed_zlib_all_voice_identifiers', 'wuwa_real_provider_inventory',
          'wuwa_managed_zlib_config_and_all_voice_identifiers',
          'both_managed_entries_reject_unbounded_selection', 'immutable_runtime_and_inputs_unchanged')
STAGES = {
    **{s: ('not-run',) for s in ('not-observed', 'fixture-create', 'source-identity', 'resource-receipt',
       'immutable-copy', 'helper-receipt', 'runtime-resolve', 'authored-fixture', 'immutable-recheck',
       'final-resolve', 'fixture-cleanup')},
    'runtime-identity': ('runtime-identity',), 'nte-inventory': ('nte-inventory',),
    'nte-voice': ('nte-voice-zh', 'nte-voice-en', 'nte-voice-ja', 'nte-voice-ko'),
    'wuwa-inventory': ('wuwa-inventory',),
    'wuwa-extract': ('wuwa-extract-zh', 'wuwa-extract-en', 'wuwa-extract-ja', 'wuwa-extract-ko', 'wuwa-extract-config'),
    'nte-rejection': ('nte-rejection',), 'wuwa-rejection': ('wuwa-rejection',)}
PREFIX = {**{s: 0 for s in ('not-observed', 'fixture-create', 'source-identity', 'resource-receipt',
           'immutable-copy', 'helper-receipt', 'runtime-resolve', 'runtime-identity')},
          'authored-fixture': 1, 'nte-inventory': 1, 'nte-voice': 2, 'wuwa-inventory': 3,
          'wuwa-extract': 4, 'nte-rejection': 5, 'wuwa-rejection': 5, 'immutable-recheck': 6,
          'final-resolve': 7, 'fixture-cleanup': 7}
KINDS = {'unknown', 'spawn', 'timeout', 'exit-mismatch', 'output-limit', 'identity-json', 'identity-schema',
         'identity-version', 'identity-origin', 'identity-corelib', 'inventory-json', 'inventory-members',
         'extracted-bytes', 'immutable-changed', 'validation', 'cleanup'}
_RETAINED_FAILURES = []  # Actual holder/fixture/returned owners/errors, never serialized or retried.


def _require(condition):
    if not condition:
        raise ValueError('Native reader observation is unavailable')


def _child_default():
    return dict(state='not-observed', exit='not-observed', stdout='not-observed',
                stderr='not-observed', reply='not-observed')


def validate_failure(value):
    """Closed labels only; never infer a child, callback or cleanup from absence."""
    _require(type(value) is dict and set(value) == {'schema', 'platform', 'passed', 'error', 'stage', 'operation',
        'failure_kind', 'completed_checks', 'child', 'cleanup'})
    _require(value['schema'] == 'toolkit-unreal-native-probe-failure-v2' and value['passed'] is False
             and value['error'] == 'native-reader-probe-failed' and value['platform'] in ('win-x64', 'linux-x64', 'darwin-arm64'))
    stage, op, kind = value['stage'], value['operation'], value['failure_kind']
    _require(type(stage) is str and stage in STAGES and type(op) is str and op in STAGES[stage]
             and type(kind) is str and kind in KINDS)
    completed = value['completed_checks']
    _require(type(completed) is list and completed == list(CHECKS[:PREFIX[stage]]))
    child, cleanup = value['child'], value['cleanup']
    _require(type(child) is dict and set(child) == {'state', 'exit', 'stdout', 'stderr', 'reply'})
    for name, choices in {'state': ('not-observed', 'returned'), 'exit': ('not-observed', 'zero', 'one', 'three', 'other-nonzero'),
                         'stdout': ('not-observed', 'empty', 'nonempty', 'over-limit'),
                         'stderr': ('not-observed', 'empty', 'nonempty', 'over-limit'),
                         'reply': ('not-observed', 'other', 'identity-json', 'completed', 'reader-failed', 'unsupported-format')}.items():
        _require(type(child[name]) is str and child[name] in choices)
    if child['state'] == 'not-observed': _require(child == _child_default())
    else: _require(op != 'not-run' and child['exit'] != 'not-observed'
                   and child['stdout'] != 'not-observed' and child['stderr'] != 'not-observed')
    _require(type(cleanup) is dict and set(cleanup) == {'state', 'step'}
             and cleanup in [dict(state='not-started', step='not-run'), dict(state='confirmed', step='complete'),
                            *[dict(state='unconfirmed', step=s) for s in ('not-run', 'stop', 'close', 'fixture')]])
    if op == 'not-run': _require(child == _child_default())
    if kind in ('spawn', 'timeout', 'exit-mismatch', 'output-limit'): _require(op != 'not-run')
    if kind == 'spawn': _require(child == _child_default() and cleanup == dict(state='unconfirmed', step='not-run'))
    if kind in ('exit-mismatch', 'output-limit'): _require(child['state'] == 'returned')
    if kind == 'output-limit': _require('over-limit' in (child['stdout'], child['stderr']))
    if kind.startswith('identity-'): _require(stage == 'runtime-identity')
    if kind.startswith('inventory-'): _require(stage in ('nte-inventory', 'wuwa-inventory', 'wuwa-extract'))
    if kind == 'extracted-bytes': _require(stage in ('nte-voice', 'wuwa-extract'))
    if kind == 'immutable-changed': _require(stage == 'immutable-recheck')
    if kind == 'cleanup': _require(cleanup['state'] == 'unconfirmed')
    return value


class _Observation:
    def __init__(self):
        self.stage = 'not-observed'; self.operation = 'not-run'; self.kind = 'unknown'
        self.completed = []; self.child = _child_default(); self.cleanup = dict(state='not-started', step='not-run')
        self.first = None; self.errors = []; self.owners = []; self.fixture = None

    def at(self, stage, operation='not-run', kind='validation'):
        _require(stage in STAGES and operation in STAGES[stage] and kind in KINDS)
        if operation != self.operation:
            self.child = _child_default(); self.cleanup = dict(state='not-started', step='not-run')
        self.stage, self.operation, self.kind = stage, operation, kind

    def failed(self, error, kind=None):
        self.errors.append(error)
        if self.first is None:
            self.first = dict(stage=self.stage, operation=self.operation, failure_kind=kind or self.kind,
                              completed_checks=list(self.completed), child=dict(self.child))

    def failure(self):
        _require(self.first is not None)
        return validate_failure(dict(schema='toolkit-unreal-native-probe-failure-v2', platform=host_platform(),
            passed=False, error='native-reader-probe-failed', **self.first, cleanup=dict(self.cleanup)))


def _at(observation, stage, operation='not-run', kind='validation'):
    if observation is not None: observation.at(stage, operation, kind)


def _completed(observation, check):
    if observation is not None:
        _require(check == CHECKS[len(observation.completed)])
        observation.completed.append(check)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(root):
    result = {}
    for path in root.rglob('*'):
        _no_links(path)
        result[path.relative_to(root).as_posix()] = digest(path.read_bytes()) if path.is_file() else 'directory'
    return result


def authored_wave():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setparams((1, 1, 8000, 0, 'NONE', 'not compressed'))
        output.writeframes(bytes(range(256)) * 2)
    return stream.getvalue()


def authored_pak(path, files, *, nte=False):
    """Legacy Pak v4 with zlib blocks, using the pinned CUE4Parse schema.

    NTE stores IndexOffset + 1 (FPakInfo.cs at the pinned parser revision).
    Every member is authored here, unencrypted, and unrelated to game content.
    """
    if not files or len(files) > 16:
        raise ValueError('Authored archive member count is outside probe bounds')
    payload, directory = bytearray(), bytearray()
    def fstring(text):
        data = text.encode('utf-8') + b'\0'
        return struct.pack('<i', len(data)) + data
    for name, raw in sorted(files.items()):
        relative_resource(name)
        if not raw or len(raw) > 16 * 1024:
            raise ValueError('Authored archive payload is outside probe bounds')
        offset = len(payload)
        chunks = [zlib.compress(raw[i:i + 64]) for i in range(0, len(raw), 64)]
        position = offset + 57 + 16 * len(chunks)
        blocks = []
        for chunk in chunks:
            blocks.append((position, position + len(chunk))); position += len(chunk)
        compressed = b''.join(chunks)
        tail = struct.pack('<I', len(blocks)) + b''.join(struct.pack('<QQ', *block) for block in blocks)
        tail += struct.pack('<BI', 0, 64)
        entry = struct.pack('<QQI', len(compressed), len(raw), 1) + hashlib.sha1(raw).digest() + tail
        payload += struct.pack('<Q', 0) + entry + compressed
        directory += fstring(name) + struct.pack('<Q', offset) + entry
    index = fstring('../../../') + struct.pack('<I', len(files)) + directory
    footer = b'\0' + struct.pack('<IIQQ', 0x5A6F12E1, 4, len(payload) + int(nte), len(index)) + hashlib.sha1(index).digest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload + index + footer)


def _copy_closed(source, destination):
    source = Path(source).absolute()
    for path in (source, *source.rglob('*')):
        _no_links(path)
        if not (path.is_file() or path.is_dir()):
            raise ValueError('Probe input contains an unsupported filesystem entry')
    shutil.copytree(source, destination)


def _source_identity(receipt, names, commit):
    if (receipt.get('source_commit') != commit or receipt.get('source_dirty') is not False
            or set(receipt.get('source_inputs', {})) != names):
        raise ValueError('Probe inputs require a matching clean source receipt')
    if receipt['source_inputs'] != {name: digest((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Probe inputs differ from the current committed helper sources')


def _layout(helper_root, resources, temporary, *, observation=None):
    """Validate source receipts and reuse production immutable resource checks."""
    _at(observation, 'source-identity')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Probe source identity is unavailable')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip():
        raise ValueError('Native acceptance requires a clean source checkout')
    _at(observation, 'resource-receipt')
    resource_receipt = resources / 'resource-manifest.json'
    _no_links(resource_receipt.absolute())
    receipt = json.loads(resource_receipt.read_text(encoding='utf-8'))
    if receipt.get('schema') != 'toolkit-native-resources-v1' or receipt.get('platform') != host_platform():
        raise ValueError('Probe dependencies are for another native platform')
    _source_identity(receipt, RESOURCE_SOURCES, commit)
    _at(observation, 'immutable-copy')
    application = temporary / 'Immutable reader 漢字'
    resource_root = application / 'resources'
    _copy_closed(helper_root, resource_root / 'helpers/nte')
    _copy_closed(resources / nte_toolchain.PREFIX, resource_root / nte_toolchain.PREFIX)
    _at(observation, 'helper-receipt')
    helper_manifest = json.loads((resource_root / 'helpers/nte/helper-manifest.json').read_text(encoding='utf-8'))
    _source_identity(helper_manifest, _source_names('nte'), commit)
    entries = {'helpers/nte/' + name: value['sha256'] for name, value in helper_manifest['files'].items()}
    entries['helpers/nte/helper-manifest.json'] = digest((resource_root / 'helpers/nte/helper-manifest.json').read_bytes())
    rows = receipt.get('files', [])
    if not rows or len(rows) > 128:
        raise ValueError('Probe dependency inventory is incomplete')
    for row in rows:
        name = relative_resource(row['path'])
        if not name.startswith(nte_toolchain.PREFIX) or name in entries:
            raise ValueError('Probe dependency inventory contains an unexpected member')
        path = resource_root / name
        if path.stat().st_size != row['bytes'] or digest(path.read_bytes()) != row['sha256']:
            raise ValueError('Probe dependency differs from its collection receipt')
        entries[name] = row['sha256']
    private = temporary / 'private'
    layout = RuntimeLayout(mode='bundle', application_root=application, resource_root=resource_root,
        executable=application / 'probe-host', data_root=private / 'data', settings_root=private,
        cache_root=private / 'cache', tool_root=private / 'tools', work_root=private / 'work',
        state_root=private / 'state', default_export_root=private / 'exports', source_commit=commit,
        resources=entries)
    _at(observation, 'runtime-resolve')
    helper = prebuilt_reader('nte', layout=layout)
    nte_toolchain.resolve(layout=layout)
    return layout, helper, {'helper_manifest_sha256': entries['helpers/nte/helper-manifest.json'],
        'resource_manifest_sha256': digest(resource_receipt.read_bytes()),
        'managed_components_sha256': entries[nte_toolchain.PREFIX + 'notices/MANAGED-COMPONENTS.json']}


def _execute(command, request, env, cwd, *, reject=False, observation=None):
    observation = observation or _Observation()
    # Constructor failure is not proof that no underlying process was created.
    try:
        child = OwnedProcess(command, cwd=cwd, env=env)
    except BaseException as error:
        observation.cleanup = dict(state='unconfirmed', step='not-run')
        observation.failed(error, 'spawn')
        raise
    observation.owners.append(child)  # Retain the actual returned object immediately.
    body_error = None; cleanup_error = None
    try:
        observation.kind = 'unknown'
        stdout, stderr = child.process.communicate(input=json.dumps(request).encode(), timeout=60)
        observation.child = dict(state='returned', exit={0:'zero', 1:'one', 3:'three'}.get(child.process.returncode, 'other-nonzero'),
            stdout='over-limit' if len(stdout)>8192 else 'nonempty' if stdout else 'empty',
            stderr='over-limit' if len(stderr)>8192 else 'nonempty' if stderr else 'empty', reply='not-observed')
        if len(stdout)<=8192:
            observation.child['reply'] = {b'Game reader completed':'completed',
                b'Game reader failed; check the game files and reader version':'reader-failed',
                b'Unsupported NTE localization format; update the toolkit reader':'unsupported-format'}.get(stdout.strip(), 'other')
        if len(stdout) > 8192 or len(stderr) > 8192 or (child.process.returncode == 0) == reject:
            observation.kind = 'output-limit' if len(stdout)>8192 or len(stderr)>8192 else 'exit-mismatch'
            raise ValueError('Native reader returned an unexpected operation result')
    except BaseException as error:
        body_error = error
        observation.failed(error, 'timeout' if isinstance(error, subprocess.TimeoutExpired) else observation.kind)
    finally:
        try:
            child.stop()
        except BaseException as error:
            cleanup_error = error; observation.cleanup = dict(state='unconfirmed', step='stop')
            observation.failed(error, 'cleanup')
        else:
            # Only confirmed stop permits closing buffered streams: a reader
            # left by communicate(timeout) may still hold their internal locks.
            try:
                child.close_streams()
            except BaseException as error:
                cleanup_error = error; observation.cleanup = dict(state='unconfirmed', step='close')
                observation.failed(error, 'cleanup')
        if cleanup_error is None:
            observation.cleanup = dict(state='confirmed', step='complete')
            if body_error is None: observation.owners.remove(child)
    if body_error is not None: raise body_error
    if cleanup_error is not None: raise cleanup_error
    return stdout


def run_checks(layout, helper, temporary, *, observation=None):
    checks = {}
    _at(observation, 'runtime-identity', 'runtime-identity')
    raw_identity = _execute(helper.runtime_identity_command(), {}, reader_environment(), temporary, observation=observation)
    if observation is not None: observation.kind = 'identity-json'
    identity = json.loads(raw_identity)
    if observation is not None:
        observation.kind = ('identity-schema' if not isinstance(identity, dict) or identity.get('schema') != 'proxy-nte-runtime-identity-v1'
            else 'identity-version' if identity.get('runtime_version') != RUNTIME
            else 'identity-origin' if identity.get('runtime_origin') != 'app-local' or identity.get('game_execution_approved') is not False
            else 'identity-corelib')
    if (identity.get('schema') != 'proxy-nte-runtime-identity-v1' or identity.get('runtime_version') != RUNTIME
            or identity.get('runtime_origin') != 'app-local' or identity.get('game_execution_approved') is not False
            or identity.get('corelib_sha256') != helper.manifest['files']['System.Private.CoreLib.dll']['sha256']):
        raise ValueError('Native runtime identity differs from its bundle receipt')
    checks['app_local_runtime_identity'] = True
    _completed(observation, 'app_local_runtime_identity')
    if observation is not None: observation.child['reply'] = 'identity-json'
    _at(observation, 'authored-fixture')
    game_nte, game_wuwa = temporary / 'Authored NTE 漢字', temporary / 'Authored Wuwa 漢字'
    voice = authored_wave()
    nte_files = {f'HT/Content/WwiseAudio/Media/{language}/42.wem': voice for language in VOICE_LOCALES}
    wuwa_files = {WUWA_PREFIX + prefix + '_owned.wem': voice for prefix in VOICE_LOCALES.values()}
    config = b'Authored toolkit configuration extraction fixture.\n' * 16
    wuwa_files[CONFIG_PATH] = config
    authored_pak(game_nte / 'owned.pak', nte_files, nte=True)
    authored_pak(game_wuwa / 'owned.pak', wuwa_files)
    snapshots = {root: snapshot(root) for root in (layout.application_root, game_nte, game_wuwa)}
    def operation(mode, install, request, suffix, *, reject=False, role):
        stage = 'nte-rejection' if role == 'nte-rejection' else 'wuwa-rejection' if role == 'wuwa-rejection' else (
            'nte-voice' if role.startswith('nte-voice-') else 'wuwa-extract' if role.startswith('wuwa-extract-') else role)
        _at(observation, stage, role)
        destination = layout.work_root / suffix
        command, env, cwd = nte_toolchain.command(install, destination, mode, layout=layout)
        _execute(command, request, env, cwd, reject=reject, observation=observation)
        return destination
    inventory = operation('inventory', game_nte, {'archive_metadata': ZERO_KEY}, 'nte-inventory', role='nte-inventory')
    if observation is not None: observation.kind = 'inventory-json'
    if set(json.loads((inventory / 'inventory.json').read_text())) != set(nte_files):
        if observation is not None: observation.kind = 'inventory-members'
        raise ValueError('NTE provider did not mount the authored archive')
    checks['nte_real_provider_inventory'] = True
    _completed(observation, 'nte_real_provider_inventory')
    for language in VOICE_LOCALES:
        output = operation('voice', game_nte, {'archive_metadata': ZERO_KEY, 'voice_language': language,
            'depot': f'HT/Content/WwiseAudio/Media/{language}/42.wem'}, 'nte-' + language, role='nte-voice-' + VOICE_LOCALES[language])
        if observation is not None: observation.kind = 'extracted-bytes'
        if (output / 'voice.wem').read_bytes() != voice:
            raise ValueError('NTE managed zlib extraction changed authored bytes')
    checks['nte_managed_zlib_all_voice_identifiers'] = True
    _completed(observation, 'nte_managed_zlib_all_voice_identifiers')
    inventory = operation('wuwa-list', game_wuwa, {'archive_metadata': [ZERO_KEY],
        'filter': 'WwiseExternalSource/'}, 'wuwa-inventory', role='wuwa-inventory')
    if observation is not None: observation.kind = 'inventory-json'
    if set(json.loads((inventory / 'files.json').read_text())) != set(wuwa_files) - {CONFIG_PATH}:
        if observation is not None: observation.kind = 'inventory-members'
        raise ValueError('Wuwa provider did not list the authored voice paths')
    checks['wuwa_real_provider_inventory'] = True
    _completed(observation, 'wuwa_real_provider_inventory')
    for name in wuwa_files:
        output = operation('wuwa-extract', game_wuwa, {'archive_metadata': [ZERO_KEY],
            'filter': 'ConfigDB/db_plot_audio.db' if name == CONFIG_PATH else name}, 'wuwa-' + Path(name).stem,
            role=WUWA_OPERATIONS[name])
        if observation is not None: observation.kind = 'extracted-bytes'
        if (output / name).read_bytes() != wuwa_files[name] or json.loads((output / 'files.json').read_text()) != [name]:
            raise ValueError('Wuwa managed zlib extraction changed authored bytes')
    checks['wuwa_managed_zlib_config_and_all_voice_identifiers'] = True
    _completed(observation, 'wuwa_managed_zlib_config_and_all_voice_identifiers')
    operation('voice', game_nte, {'archive_metadata': ZERO_KEY, 'depot': '../unrequested'}, 'nte-reject', reject=True, role='nte-rejection')
    operation('wuwa-extract', game_wuwa, {'archive_metadata': [ZERO_KEY], 'filter': '../unrequested'}, 'wuwa-reject', reject=True, role='wuwa-rejection')
    checks['both_managed_entries_reject_unbounded_selection'] = True
    _completed(observation, 'both_managed_entries_reject_unbounded_selection')
    _at(observation, 'immutable-recheck', kind='immutable-changed')
    if any(snapshot(root) != before for root, before in snapshots.items()):
        raise ValueError('Reader modified an immutable runtime or authored archive')
    checks['immutable_runtime_and_inputs_unchanged'] = True
    _completed(observation, 'immutable_runtime_and_inputs_unchanged')
    _at(observation, 'final-resolve')
    nte_toolchain.resolve(layout=layout)
    return checks


def probe(helper_root, resources):
    observation = _Observation()
    try:
        observation.at('fixture-create', kind='unknown')
        temporary = tempfile.mkdtemp(prefix='toolkit-unreal-probe-')
        observation.fixture = Path(temporary)  # Retain even if resolve itself fails.
        root = observation.fixture.resolve()
        layout, helper, identities = _layout(Path(helper_root), Path(resources), root, observation=observation)
        checks = run_checks(layout, helper, root, observation=observation)
        result = {'schema': 'toolkit-unreal-native-probe-v1', 'platform': host_platform(),
            'source_commit': layout.source_commit, 'source_dirty': False, 'execution': 'actual-app-local-process',
            **identities, 'probe_source_sha256': digest(Path(__file__).read_bytes()), 'checks': checks,
            'passed': True, 'real_games_accessed': False, 'real_accounts_accessed': False,
            'game_asset_validation': 'not-performed', 'encrypted_archive_validation': 'not-performed',
            'oodle_validation': 'not-performed', 'rights_review': 'pending'}
        observation.at('fixture-cleanup', kind='cleanup')
        try:
            shutil.rmtree(root)
        except BaseException:
            observation.cleanup = dict(state='unconfirmed', step='fixture')
            raise
        return result
    except BaseException as error:
        observation.failed(error)
        _RETAINED_FAILURES.append(observation)
        if not isinstance(error, Exception): raise
        return observation.failure()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper-root', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    try:
        result = probe(options.helper_root, options.resources)
    except Exception:
        # Raw dependency exceptions can contain machine paths. Keep public CI
        # reports fixed and fail visibly; no game/account diagnostics are read.
        # Projection failure cannot serialize a partial or passing native result.
        observation = _Observation()
        observation.cleanup = dict(state='unconfirmed', step='not-run')
        error = sys.exception(); observation.failed(error, 'unknown'); _RETAINED_FAILURES.append(observation)
        result = observation.failure()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
