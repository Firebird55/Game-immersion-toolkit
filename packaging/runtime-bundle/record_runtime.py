"""Observe a complete experimental environment, never approve redistribution.

The supplier archive and every installed wheel payload are compared byte for
byte before PyInstaller runs. No installer, account, game or user profile is read.
"""
import argparse
import hashlib
from importlib import metadata
import importlib.util
import json
import marshal
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import subprocess
import uuid
import zipfile
from types import CodeType

from closure import ROOT, ClosureError, checked_file, digest, normalized
from record_diagnostic import record, wheel_metadata

RESOURCES = (
    'package.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'public/mobile-capture/games-data.json',
    'assets/fireredvad/fireredvad_vad.onnx', 'assets/fireredvad/cmvn.ark',
    'assets/fireredvad/LICENSE', 'assets/fireredvad/NOTICE.md', 'assets/fireredvad/PROVENANCE.json',
    'scripts/check-capture-readiness.py', 'scripts/select-game-folders.ps1',
    'scripts/select-export-folder.ps1', 'scripts/endfield-reader-sources.json',
)

# Project source observations are deliberately separate from native provenance.
# These are fixed source controls/targets, not a catalog grown from TOC paths.
SOURCE_SCHEMA = 'proxy-r19-runtime-source-inputs-v1'
SOURCE_BASELINE = 'PROJECT-SOURCE-BASELINE.private.json'
SOURCE_OBSERVATION = 'PROJECT-SOURCE-OBSERVATION.private.json'
SOURCE_PUBLIC = 'RUNTIME-SOURCE-INPUTS.json'
SOURCE_TARGETS = {
    'agent-fingerprints': ('module', 'scripts.build_agent_fingerprints'),
    'story-fingerprints': ('module', 'scripts.build_story_fingerprints'),
    'capture-readiness': ('script', 'scripts/check-capture-readiness.py'),
    'account-key': ('module', 'scripts.set_lexirise_key'),
    'index-pragmata': ('module', 'scripts.index_pragmata_assets'),
    'index-voice': ('module', 'scripts.index_voice_assets'),
    'update-voice': ('module', 'scripts.update_voice_assets'),
}
SOURCE_WORKERS = frozenset({'scripts/__init__.py', 'scripts/check-capture-readiness.py',
    *(value[1].replace('.', '/') + '.py' for value in SOURCE_TARGETS.values() if value[0] == 'module')})
SOURCE_CONTROLS = frozenset({'scripts/build-runtime-bundle.ps1', 'scripts/check-evidence.mjs',
    'packaging/runtime-bundle/runtime.spec', 'packaging/runtime-bundle/record_runtime.py',
    'packaging/runtime-bundle/record_diagnostic.py', 'packaging/runtime-bundle/closure.py',
    'packaging/runtime-bundle/build_environment.py', 'packaging/runtime-bundle/native_ownership.py',
    'packaging/runtime-bundle/native_images.py', 'packaging/runtime-bundle/python_supplier.py',
    'packaging/runtime-bundle/windows_runtime.py', 'packaging/runtime-bundle/hooks/hook-webrtcvad.py'})
SOURCE_ROLES = frozenset({'main-pure', 'main-script', 'asr-pure', 'asr-script',
    'build-control', 'runtime-script-resource'})
SOURCE_LIMIT, SOURCE_TOTAL, SOURCE_FILES, SOURCE_ROWS = 2 * 1024**2, 32 * 1024**2, 1024, 20000
SOURCE_COVERAGE = ('project origin files stable at observed boundaries; compiled bytecode, generated code, '
    'suppliers, frontend source-to-assets and OS/toolchain closure are not established')
SOURCE_FAILURES = frozenset({'invalid-identity', 'unsafe-source', 'unmapped-origin', 'source-changed',
    'source-unavailable', 'limit-exceeded', 'cleanup-unconfirmed', 'observation-failed'})
_SOURCE_HELD = []  # Actual uncertain streams/errors only; never public or retry authority.


class SourceInputError(ClosureError):
    def __init__(self, code):
        self.code = code if code in SOURCE_FAILURES else 'observation-failed'
        super().__init__('Project source observation refused: ' + self.code + '.')


def source_canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def source_name(name):
    from native_ownership import _relative
    try:
        result = _relative(name)
        if type(name) is not str or len(name) > 512 or any(ord(c) == 127 for c in name):
            raise ValueError()
        return result
    except Exception:
        raise SourceInputError('unsafe-source') from None


def source_eligible(name):
    source_name(name)
    return name in SOURCE_WORKERS or name in SOURCE_CONTROLS or (name.startswith('backend/')
        and name.endswith('.py') and not {'tests', 'test', '__pycache__', 'data', 'work', 'output',
            'diagnostics', '.venv', '.git'} & set(Path(name).parts))


def source_read(path, *, limit=SOURCE_LIMIT):
    """Root-first bounded ordinary file read, retaining uncertainty on close."""
    stream = None
    error = None
    try:
        path = native_path(path)
        stream = path.open('rb')
        before = os.fstat(stream.fileno())
        if before.st_nlink != 1 or before.st_size > limit:
            raise SourceInputError('limit-exceeded')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        current = native_path(path).stat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if (len(raw) != before.st_size or len(raw) > limit or identity(before) != identity(after)
                or identity(before) != identity(current)):
            raise SourceInputError('source-changed')
    except BaseException as caught:
        error = caught
    if stream is not None:
        try:
            stream.close()
        except BaseException as close_error:
            _SOURCE_HELD.append((stream, error, close_error))
            raise SourceInputError('cleanup-unconfirmed') from None
    if error is not None:
        _SOURCE_HELD.append((None, error))
        raise SourceInputError(error.code if type(error) is SourceInputError else 'source-unavailable') from None
    return raw


def source_text_identity(path, *, limit=SOURCE_LIMIT):
    raw = source_read(path, limit=limit)
    lf = raw.replace(b'\r\n', b'\n')
    try:
        lf.decode('utf-8', errors='strict')
        if b'\0' in lf or b'\r' in lf:
            raise ValueError()
    except (UnicodeError, ValueError):
        raise SourceInputError('source-unavailable') from None
    return {'raw': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
        'canonical_lf': {'bytes': len(lf), 'sha256': hashlib.sha256(lf).hexdigest()}}


def source_json(path, *, limit=2 * 1024**2):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SourceInputError('invalid-identity')
            result[key] = value
        return result
    try:
        return json.loads(source_read(path, limit=limit), object_pairs_hook=unique)
    except SourceInputError:
        raise
    except Exception:
        raise SourceInputError('invalid-identity') from None


def source_file_identity(path, *, limit=2 * 1024**2):
    raw = source_read(path, limit=limit)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def source_write(root, name, value, *, limit=512 * 1024):
    """Close private bytes before no-overwrite publication; no cleanup retry."""
    source_name(name)
    root = native_path(root, directory=True)
    destination = root / name
    temporary = root / ('.' + name + '.' + uuid.uuid4().hex + '.private')
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > limit:
        raise SourceInputError('limit-exceeded')
    stream = None
    try:
        native_path(destination, missing=True)
        stream = temporary.open('xb')
        if stream.write(raw) != len(raw):
            raise SourceInputError('source-unavailable')
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
    except BaseException as error:
        _SOURCE_HELD.append((stream, error, temporary))
        raise SourceInputError('cleanup-unconfirmed') from None
    try:
        os.link(temporary, destination)  # Exclusive publication on every host.
        temporary.unlink()  # Only our own closed private sibling, never a stale destination.
        if source_read(destination, limit=limit) != raw:
            raise SourceInputError('source-changed')
    except BaseException as error:
        _SOURCE_HELD.append((stream, error, temporary, destination))
        raise SourceInputError('observation-failed') from None


def source_snapshot(source, expected):
    """Reuse the existing flags/attributes checks before claiming a clean source."""
    native_path(source, directory=True)
    native_path(source / 'scripts/check-evidence.mjs')
    script = """import {execFileSync} from 'node:child_process';
import {hasHiddenIndexEntries,hasGitSourceTransformAttributes} from './scripts/check-evidence.mjs';
let value={head:null,clean:false,sourceStatus:'unavailable',sourceIssue:null};
try {
  if(hasHiddenIndexEntries()) value.sourceIssue='hidden-index-entries';
  else if(hasGitSourceTransformAttributes()) value.sourceIssue='git-source-transforms';
  else {
    value.head=execFileSync('git',['rev-parse','--verify','HEAD'],{encoding:'utf8',maxBuffer:128}).trim();
    value.clean=execFileSync('git',['status','--porcelain=v1','--untracked-files=all'],{encoding:'utf8',maxBuffer:1048576}).length===0;
    if(value.clean)value.sourceStatus='available';
  }
} catch {}
process.stdout.write(JSON.stringify(value));"""
    try:
        result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=source,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if result.returncode != 0 or result.stderr or len(result.stdout) > 1024:
            raise ValueError()
        value = json.loads(result.stdout)
        return validate_source_snapshot(value, expected)
    except BaseException as error:
        _SOURCE_HELD.append((None, error))
        raise SourceInputError('source-unavailable') from None


def validate_source_snapshot(value, expected):
    if (type(value) is not dict or set(value) != {'head', 'clean', 'sourceStatus', 'sourceIssue'}
            or value['head'] != expected or value['sourceStatus'] != 'available'
            or value['sourceIssue'] is not None or value['clean'] is not True):
        raise SourceInputError('source-unavailable')
    return value


def source_headers(value):
    if (type(value) is not dict or any(type(value.get(k)) is not str
            for k in ('source_commit', 'build_id', 'profile'))):
        raise SourceInputError('invalid-identity')
    headers = native_headers(value)
    if headers['profile'] != 'runtime-experiment':
        raise SourceInputError('invalid-identity')
    return headers


def source_tracked(source):
    try:
        result = subprocess.run(['git', 'ls-files', '--cached', '-z'], cwd=source,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if result.returncode or result.stderr or len(result.stdout) > 4 * 1024**2:
            raise ValueError()
        names = result.stdout.decode('utf-8').split('\0')
        if names.pop() != '' or len(names) != len(set(n.casefold() for n in names)):
            raise ValueError()
        for name in names:
            source_name(name)
        return names
    except BaseException as error:
        _SOURCE_HELD.append((None, error))
        raise SourceInputError('source-unavailable') from None


def begin_project_sources(value, source, evidence, input_manifest):
    from backend.runtime_bundle import CHILD_TARGETS
    headers = source_headers(value)
    source, evidence = native_path(source, directory=True), native_path(evidence, directory=True)
    source_snapshot(source, headers['source_commit'])
    actual = {key: item for key, item in CHILD_TARGETS.items() if item[1].startswith('scripts')}
    if actual != SOURCE_TARGETS:
        raise SourceInputError('invalid-identity')
    names = sorted(name for name in source_tracked(source) if source_eligible(name))
    if not SOURCE_WORKERS | SOURCE_CONTROLS <= set(names) or len(names) > SOURCE_FILES:
        raise SourceInputError('invalid-identity')
    files, used = {}, 0
    for name in names:
        files[name] = source_text_identity(source / name, limit=min(SOURCE_LIMIT, SOURCE_TOTAL-used))
        used += files[name]['raw']['bytes']
    source_snapshot(source, headers['source_commit'])
    baseline = {'schema': 'proxy-r19-project-source-baseline-v1', **headers,
        'source_clean_before': True, 'input_manifest': source_file_identity(input_manifest, limit=64 * 1024**2), 'files': files}
    source_write(evidence, SOURCE_BASELINE, baseline, limit=2 * 1024**2)
    return baseline


class ProjectSourceObservation:
    """Actual selected origin files only; never code-cache or native authority."""
    def __init__(self, value, source, evidence, input_manifest):
        self.headers = source_headers(value)
        self.source = native_path(source, directory=True)
        self.evidence = native_path(evidence, directory=True)
        self.manifest = native_path(input_manifest)
        self.baseline = source_json(self.evidence / SOURCE_BASELINE)
        self.baseline_identity = source_file_identity(self.evidence / SOURCE_BASELINE)
        if (type(self.baseline) is not dict
                or set(self.baseline) != {'schema', *self.headers, 'source_clean_before', 'input_manifest', 'files'}
                or self.baseline['schema'] != 'proxy-r19-project-source-baseline-v1'
                or any(self.baseline.get(k) != v for k, v in self.headers.items())
                or self.baseline['source_clean_before'] is not True
                or self.baseline['input_manifest'] != source_file_identity(self.manifest, limit=64 * 1024**2)):
            raise SourceInputError('invalid-identity')
        files = validate_source_baseline_files(self.baseline['files'])
        self.records, self.analyses, self.rows, self.seen = {}, {}, 0, set()
        self._phase, self._reads = 'controls', {}
        self._origins = {}
        self.excluded = dict(supplier=0, builtin=0, namespace_generated=0)
        self.supplier = set()
        from native_ownership import _relative
        for component in value['components']:
            prefix = Path(sys.base_prefix if normalized(component['name']) == 'cpython' else sys.prefix)
            for item in component['installed_files']:
                self.supplier.add(os.path.normcase(str(prefix / _relative(item['path']))))
        for name in SOURCE_CONTROLS:
            self._project(name, 'build-control')
        resource = next((r for r in value['resources'] if r['path'] == 'scripts/check-capture-readiness.py'), None)
        if resource is None or files['scripts/check-capture-readiness.py']['raw']['sha256'] != resource['sha256']:
            raise SourceInputError('invalid-identity')
        self._project('scripts/check-capture-readiness.py', 'runtime-script-resource')

    def _project(self, name, role):
        if name not in self.baseline['files'] or not source_eligible(name):
            raise SourceInputError('unmapped-origin')
        key = self._phase, name
        if key not in self._reads:
            self._reads[key] = source_text_identity(self.source / name)
        identity = self._reads[key]
        if identity != self.baseline['files'][name]:
            raise SourceInputError('source-changed')
        record = self.records.setdefault(name, {'path': name, 'roles': [], **identity})
        if role not in record['roles']:
            record['roles'].append(role); record['roles'].sort()

    def observe_analysis(self, process, analysis):
        if process not in {'main', 'asr'} or process in self.analyses:
            raise SourceInputError('invalid-identity')
        self._phase = process
        from PyInstaller.lib.modulegraph.modulegraph import NamespacePackage, BuiltinModule
        snapshots = []
        for label, rows in [('pure', analysis.pure), ('script', analysis.scripts)]:
            if not isinstance(rows, (list, tuple)) or len(rows) > SOURCE_ROWS:
                raise SourceInputError('limit-exceeded')
            if any(not isinstance(row, (tuple, list)) or len(row) != 3 for row in rows):
                raise SourceInputError('invalid-identity')
            current = tuple(tuple(row) for row in rows)
            snapshots.append((label, rows, current))
            for row in current:
                self.rows += 1
                if self.rows > SOURCE_ROWS or len(row) != 3:
                    raise SourceInputError('limit-exceeded')
                name, origin, kind = row
                if (type(name) is not str or not 1 <= len(name) <= 512
                        or any(ord(c) < 32 or ord(c) == 127 for c in name)
                        or type(kind) is not str or kind not in {'PYMODULE', 'PYMODULE-1', 'PYMODULE-2', 'PYSOURCE', 'PYSOURCE-1', 'PYSOURCE-2', 'BUILTIN'}
                        or (origin is not None and type(origin) is not str)):
                    raise SourceInputError('unmapped-origin')
                if (label == 'pure' and kind.startswith('PYSOURCE')) or (label == 'script' and kind.startswith('PYMODULE')):
                    raise SourceInputError('invalid-identity')
                key = process, label, name, origin, kind
                origin_key = process, label, name
                if origin_key in self._origins and self._origins[origin_key] != (origin, kind):
                    raise SourceInputError('invalid-identity')
                self._origins[origin_key] = origin, kind
                if key in self.seen:
                    continue
                self.seen.add(key)
                if origin in (None, '', '-'):
                    node = analysis.graph.find_node(name)
                    if (label == 'pure' and origin == '-' and kind.startswith('PYMODULE')
                            and type(node) is NamespacePackage and node.identifier == name
                            and node.filename == '-' and node.code is None):
                        self.excluded['namespace_generated'] += 1
                    elif (kind == 'BUILTIN' and type(node) is BuiltinModule
                            and node.identifier == name and node.filename is None and node.code is None):
                        self.excluded['builtin'] += 1
                    else:
                        raise SourceInputError('unmapped-origin')
                    continue
                if type(origin) is not str:
                    raise SourceInputError('unsafe-source')
                path = Path(origin)
                if not path.is_absolute() or '..' in path.parts or any(ord(c) < 32 or ord(c) == 127 for c in origin):
                    raise SourceInputError('unsafe-source')
                if os.path.normcase(str(path)) in self.supplier:
                    self.excluded['supplier'] += 1
                    continue
                if self.source not in path.parents:
                    raise SourceInputError('unmapped-origin')
                relative = path.relative_to(self.source).as_posix()
                if not relative.endswith('.py'):
                    raise SourceInputError('unmapped-origin')
                self._project(relative, process + '-' + label)
        self.analyses[process] = (analysis, analysis.graph, snapshots)

    def finish(self):
        if set(self.analyses) != {'main', 'asr'}:
            raise SourceInputError('invalid-identity')
        for analysis, graph, snapshots in self.analyses.values():
            if analysis.graph is not graph:
                raise SourceInputError('source-changed')
            for label, rows, before in snapshots:
                if getattr(analysis, label if label == 'pure' else 'scripts') is not rows or tuple(tuple(row) for row in rows) != before:
                    raise SourceInputError('source-changed')
        records = [self.records[name] for name in sorted(self.records)]
        observation = {'schema': 'proxy-r19-project-source-observation-v1', **self.headers,
            'input_manifest': self.baseline['input_manifest'], 'private_baseline': self.baseline_identity,
            'analyses': {'main': 'observed', 'asr': 'observed'},
            'records': records, 'excluded_origin_counts': self.excluded}
        source_write(self.evidence, SOURCE_OBSERVATION, observation)
        return observation


def source_identity(value):
    if type(value) is not dict or set(value) != {'bytes', 'sha256'}:
        raise SourceInputError('invalid-identity')
    if (type(value['bytes']) is not int or not 0 <= value['bytes'] <= SOURCE_LIMIT
            or type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise SourceInputError('invalid-identity')
    return value


def validate_source_baseline_files(files):
    if (type(files) is not dict or not 1 <= len(files) <= SOURCE_FILES
            or not SOURCE_WORKERS | SOURCE_CONTROLS <= set(files)
            or any(type(name) is not str for name in files)
            or len({name.casefold() for name in files}) != len(files)):
        raise SourceInputError('invalid-identity')
    for name, item in files.items():
        if not source_eligible(name) or type(item) is not dict or set(item) != {'raw', 'canonical_lf'}:
            raise SourceInputError('invalid-identity')
        source_identity(item['raw']); source_identity(item['canonical_lf'])
        if item['canonical_lf']['bytes'] > item['raw']['bytes']:
            raise SourceInputError('invalid-identity')
    if sum(x['raw']['bytes'] for x in files.values()) > SOURCE_TOTAL:
        raise SourceInputError('limit-exceeded')
    return files


def source_record(value):
    if type(value) is not dict or set(value) != {'path', 'roles', 'raw', 'canonical_lf'}:
        raise SourceInputError('invalid-identity')
    if not source_eligible(value['path']):
        raise SourceInputError('unsafe-source')
    roles = value['roles']
    if (type(roles) is not list or not roles or any(type(x) is not str or x not in SOURCE_ROLES for x in roles)
            or roles != sorted(set(roles))):
        raise SourceInputError('invalid-identity')
    if (('build-control' in roles and value['path'] not in SOURCE_CONTROLS)
            or ('runtime-script-resource' in roles and value['path'] != 'scripts/check-capture-readiness.py')
            or (set(roles) - {'build-control', 'runtime-script-resource'} and not value['path'].endswith('.py'))):
        raise SourceInputError('invalid-identity')
    source_identity(value['raw']); source_identity(value['canonical_lf'])
    if value['canonical_lf']['bytes'] > value['raw']['bytes']:
        raise SourceInputError('invalid-identity')
    return value


def validate_source_report(value):
    fixed = {'schema': SOURCE_SCHEMA, 'profile': 'runtime-experiment',
        'scope': 'observed-project-origin-files-and-fixed-build-controls',
        'coverage': SOURCE_COVERAGE, 'compiled_code_identity': 'unverified',
        'supplier_input_closure': 'separate-component-evidence', 'OS_prerequisites': 'unbound',
        'source_delivery_approved': False, 'runtime_collection_allowed': False,
        'production_execution_allowed': False, 'rights_approval': False,
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False, 'installer': 'not-built'}
    flexible = {'source_commit', 'build_id', 'status', 'stage', 'failure_code', 'input_manifest',
        'private_baseline', 'source_clean_before', 'source_clean_after', 'analyses',
        'source_before_sha256', 'source_after_sha256', 'records_sha256', 'records', 'excluded_origin_counts'}
    if type(value) is not dict or set(value) != set(fixed) | flexible:
        raise SourceInputError('invalid-identity')
    if any(type(value[k]) is not type(v) or value[k] != v for k, v in fixed.items()):
        raise SourceInputError('invalid-identity')
    source_headers(value)
    for key in ('input_manifest', 'private_baseline'):
        item = value[key]
        if (type(item) is not dict or set(item) != {'bytes', 'sha256'} or type(item['bytes']) is not int
                or not 0 < item['bytes'] <= 64 * 1024**2 or type(item['sha256']) is not str
                or not re.fullmatch('[0-9a-f]{64}', item['sha256'])):
            raise SourceInputError('invalid-identity')
    counts = value['excluded_origin_counts']
    if (type(counts) is not dict or set(counts) != {'supplier', 'builtin', 'namespace_generated'}
            or any(type(x) is not int or not 0 <= x <= SOURCE_ROWS for x in counts.values())
            or sum(counts.values()) > SOURCE_ROWS):
        raise SourceInputError('invalid-identity')
    if (value['status'] != 'observed-not-approved' or value['stage'] != 'finalize'
            or value['failure_code'] != 'none' or value['source_clean_before'] is not True
            or value['source_clean_after'] is not True
            or type(value['analyses']) is not dict or value['analyses'] != {'main': 'observed', 'asr': 'observed'}):
        raise SourceInputError('invalid-identity')
    records = value['records']
    if type(records) is not list or not 1 <= len(records) <= SOURCE_FILES:
        raise SourceInputError('invalid-identity')
    for row in records:
        source_record(row)
    names = [row['path'] for row in records]
    if names != sorted(set(names)) or len({n.casefold() for n in names}) != len(names):
        raise SourceInputError('invalid-identity')
    roles = {row['path']: row['roles'] for row in records}
    if (not SOURCE_CONTROLS <= set(names)
            or any('build-control' not in roles[name] for name in SOURCE_CONTROLS)
            or 'runtime-script-resource' not in roles.get('scripts/check-capture-readiness.py', [])):
        raise SourceInputError('invalid-identity')
    if sum(row['raw']['bytes'] for row in records) > SOURCE_TOTAL:
        raise SourceInputError('limit-exceeded')
    selected = {row['path']: {k: row[k] for k in ('raw', 'canonical_lf')} for row in records}
    checksum = hashlib.sha256(source_canonical(selected)).hexdigest()
    if (value['source_before_sha256'] != checksum or value['source_after_sha256'] != checksum
            or value['records_sha256'] != hashlib.sha256(source_canonical(records)).hexdigest()):
        raise SourceInputError('invalid-identity')
    return value


def finalize_project_sources(value, source, evidence, output, input_manifest):
    headers = source_headers(value)
    source, evidence = native_path(source, directory=True), native_path(evidence, directory=True)
    source_snapshot(source, headers['source_commit'])
    baseline = source_json(evidence / SOURCE_BASELINE)
    observation = source_json(evidence / SOURCE_OBSERVATION)
    required = {'schema', *headers, 'input_manifest', 'private_baseline', 'analyses', 'records', 'excluded_origin_counts'}
    if (type(baseline) is not dict or type(observation) is not dict or set(observation) != required
            or observation['schema'] != 'proxy-r19-project-source-observation-v1'
            or any(observation[k] != v for k, v in headers.items())
            or observation['private_baseline'] != source_file_identity(evidence / SOURCE_BASELINE)
            or observation['input_manifest'] != source_file_identity(input_manifest, limit=64 * 1024**2)
            or baseline.get('input_manifest') != observation['input_manifest']
            or any(baseline.get(k) != v for k, v in headers.items())
            or baseline.get('source_clean_before') is not True):
        raise SourceInputError('invalid-identity')
    records = observation['records']
    validate_source_baseline_files(baseline.get('files'))
    tracked = set(source_tracked(source))
    if type(records) is not list or not 1 <= len(records) <= SOURCE_FILES:
        raise SourceInputError('invalid-identity')
    selected = {}
    for row in records:
        source_record(row)
        name = row['path']
        if name not in tracked:
            raise SourceInputError('unmapped-origin')
        before = baseline['files'].get(name)
        expected = {k: row[k] for k in ('raw', 'canonical_lf')}
        if source_canonical(before) != source_canonical(expected) or source_text_identity(source / name) != expected:
            raise SourceInputError('source-changed')
        selected[name] = expected
    if not SOURCE_CONTROLS <= set(selected) or any('build-control' not in row['roles'] for row in records if row['path'] in SOURCE_CONTROLS):
        raise SourceInputError('invalid-identity')
    native = source_json(output / NATIVE_SOURCE_FINAL)
    if native.get('build_inputs') != observation['input_manifest'] or any(native.get(k) != v for k, v in headers.items()):
        raise SourceInputError('invalid-identity')
    checksum = hashlib.sha256(source_canonical(selected)).hexdigest()
    report = {'schema': SOURCE_SCHEMA, **headers,
        'scope': 'observed-project-origin-files-and-fixed-build-controls', 'status': 'observed-not-approved',
        'stage': 'finalize', 'failure_code': 'none', 'input_manifest': observation['input_manifest'],
        'private_baseline': observation['private_baseline'], 'source_clean_before': True,
        'source_clean_after': True, 'analyses': observation['analyses'],
        'source_before_sha256': checksum, 'source_after_sha256': checksum,
        'records_sha256': hashlib.sha256(source_canonical(records)).hexdigest(), 'records': records,
        'excluded_origin_counts': observation['excluded_origin_counts'], 'coverage': SOURCE_COVERAGE,
        'compiled_code_identity': 'unverified', 'supplier_input_closure': 'separate-component-evidence',
        'OS_prerequisites': 'unbound', 'source_delivery_approved': False, 'runtime_collection_allowed': False,
        'production_execution_allowed': False, 'rights_approval': False,
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False, 'installer': 'not-built'}
    validate_source_report(report)
    source_snapshot(source, headers['source_commit'])
    source_write(output, SOURCE_PUBLIC, report)
    if source_json(output / SOURCE_PUBLIC, limit=512 * 1024) != report:
        raise SourceInputError('source-changed')
    return report


def check_project_sources(value, source, evidence, output, input_manifest):
    """Required pre-publication readback, never input recovery or activation."""
    headers = source_headers(value)
    source_snapshot(source, headers['source_commit'])
    public = output / SOURCE_PUBLIC
    before = source_file_identity(public, limit=512 * 1024)
    report = validate_source_report(source_json(public, limit=512 * 1024))
    if (any(report[k] != v for k, v in headers.items())
            or report['input_manifest'] != source_file_identity(input_manifest, limit=64 * 1024**2)
            or report['private_baseline'] != source_file_identity(evidence / SOURCE_BASELINE)):
        raise SourceInputError('invalid-identity')
    baseline = source_json(evidence / SOURCE_BASELINE)
    observation = source_json(evidence / SOURCE_OBSERVATION)
    required = {'schema', *headers, 'input_manifest', 'private_baseline', 'analyses', 'records', 'excluded_origin_counts'}
    if (type(baseline) is not dict or type(observation) is not dict or set(observation) != required
            or observation['schema'] != 'proxy-r19-project-source-observation-v1'
            or any(observation[k] != v or baseline.get(k) != v for k, v in headers.items())
            or baseline.get('source_clean_before') is not True
            or baseline.get('input_manifest') != report['input_manifest']
            or any(source_canonical(observation[key]) != source_canonical(report[key])
                for key in ('input_manifest', 'private_baseline', 'analyses', 'records', 'excluded_origin_counts'))):
        # Self-consistent public hashes cannot replace the map actually emitted
        # by Analysis. Retain every recorded origin, role and exclusion count.
        raise SourceInputError('invalid-identity')
    validate_source_baseline_files(baseline.get('files'))
    tracked = set(source_tracked(source))
    for row in report['records']:
        if row['path'] not in tracked:
            raise SourceInputError('unmapped-origin')
        expected = {k: row[k] for k in ('raw', 'canonical_lf')}
        if (source_canonical(baseline['files'].get(row['path'])) != source_canonical(expected)
                or source_text_identity(source / row['path']) != expected):
            raise SourceInputError('source-changed')
    native = source_json(output / NATIVE_SOURCE_FINAL)
    if native.get('build_inputs') != report['input_manifest'] or any(native.get(k) != v for k, v in headers.items()):
        raise SourceInputError('invalid-identity')
    source_snapshot(source, headers['source_commit'])
    if source_file_identity(public, limit=512 * 1024) != before:
        raise SourceInputError('source-changed')
    return report


def verified_nte(evidence, resources, commit, source):
    """Bind only the owned bridge. An external game chain cannot enter here."""
    from types import SimpleNamespace
    from backend.prebuilt_readers import prebuilt_reader
    entries = {item['path']: item['sha256'] for item in resources}
    def resource(name):
        if name not in entries:
            raise ClosureError('NTE helper is missing from the outer resource inventory.')
        return checked_file(evidence, {'path': name, 'sha256': entries[name]})
    helper = prebuilt_reader('nte', layout=SimpleNamespace(mode='bundle', source_commit=commit,
        resource_root=evidence, resources=entries, resource=resource))
    if helper.manifest['source_inputs'] != {name: digest(source / name) for name in helper.manifest['source_inputs']}:
        raise ClosureError('Owned NTE bridge sources differ from the runtime source commit.')
    return helper


def collect_nte(helper_root, evidence, commit, source):
    import shutil
    from backend.prebuilt_readers import _no_links
    helper_root = helper_root.absolute()
    for path in (helper_root, *helper_root.rglob('*')):
        _no_links(path)
        if not (path.is_file() or path.is_dir()):
            raise ClosureError('Owned helper inputs must be regular files/directories.')
    target = evidence / 'helpers/nte'
    # Check destination ancestry before copytree can traverse an existing
    # helpers junction and write owned bytes outside the private evidence root.
    _no_links(target.absolute())
    target.parent.mkdir(exist_ok=True)
    shutil.copytree(helper_root, target)
    resources = [{'path': path.relative_to(evidence).as_posix(), 'sha256': digest(path), 'version': commit,
        'source': 'https://github.com/Firebird55/Game-immersion-toolkit/tree/' + commit,
        'license_expression': 'Owned bridge and exact Microsoft runtime notices; exact-output review pending'}
        for path in sorted(target.rglob('*')) if path.is_file()]
    helper = verified_nte(evidence, resources, commit, source)
    return resources, {'nte': {'build_id': helper.manifest['build_id'], 'source_identity': helper.source_identity,
        'manifest_sha256': digest(target / 'helper-manifest.json'), 'game_execution_approved': False}}


def verified_codec(evidence, resources, commit, source):
    from types import SimpleNamespace
    from backend.prebuilt_codecs import prebuilt_flac_decoder
    entries = {item['path']: item['sha256'] for item in resources}
    def resource(name):
        if name not in entries:
            raise ClosureError('Codec is missing from the outer resource inventory.')
        return checked_file(evidence, {'path': name, 'sha256': entries[name]})
    codec = prebuilt_flac_decoder(layout=SimpleNamespace(mode='bundle', profile='runtime-experiment',
        source_commit=commit, resource_root=evidence, resources=entries, resource=resource))
    if codec.manifest['source_inputs'] != {name: digest(source / name) for name in codec.manifest['source_inputs']}:
        raise ClosureError('Codec preparation sources differ from the runtime source commit.')
    return codec


def codec_identity(codec):
    return {'xiph-flac': {'build_id': codec.manifest['build_id'],
        'manifest_sha256': digest(codec.executable.parent / 'codec-manifest.json'),
        'artifact_sha256': codec.manifest['archive_sha256'], 'production_execution_allowed': False}}


def collect_codec(codec_root, evidence, commit, source):
    import shutil
    from backend.prebuilt_readers import _no_links
    codec_root = codec_root.absolute()
    for path in (codec_root, *codec_root.rglob('*')):
        _no_links(path)
        if not (path.is_file() or path.is_dir()):
            raise ClosureError('Codec inputs must be regular files/directories.')
    target = evidence / 'codecs/xiph-flac'
    _no_links(target.absolute())
    target.parent.mkdir(exist_ok=True)
    shutil.copytree(codec_root, target)
    resources = [{'path': path.relative_to(evidence).as_posix(), 'sha256': digest(path), 'version': '1.5.0',
        'source': 'https://github.com/xiph/flac/releases/tag/1.5.0',
        'license_expression': 'GPL-2.0-or-later CLI, BSD library, LGPL support; source kit retained; production/native review pending'}
        for path in sorted(target.rglob('*')) if path.is_file()]
    codec = verified_codec(evidence, resources, commit, source)
    return resources, codec_identity(codec)


def verify_python(archive, prefix, pin):
    from python_supplier import archive_plan, verify_installed
    try:
        # Preserve the legacy native observer's refusal category before a raw
        # linked ancestor can be resolved or any native leaf can be inspected.
        for name, member in archive_plan(archive, pin).items():
            if member.isfile() and Path(name).suffix.lower() in {'.dll', '.exe', '.pyd'}:
                native_path(prefix / name[len('python/'):])
        return verify_installed(archive, prefix, pin)
    except NativeCollectionError:
        raise
    except (ValueError, OSError, tarfile.TarError) as error:
        raise ClosureError(str(error)) from error


def verified_recompiled_cache(package, name, installed, distribution):
    """Accept pip's generated bytecode only when it compiles verified source."""
    if installed.suffix != '.pyc' or installed.parent.name != '__pycache__':
        return False
    try:
        source_name = Path(importlib.util.source_from_cache(name)).as_posix()
        source = Path(distribution.locate_file(source_name))
        if (source.is_symlink() or Path(sys.prefix).resolve() not in source.resolve().parents
                or source.read_bytes() != package.read(source_name)):
            return False
        # Only this interpreter's standard cache names and optimization levels
        # may differ. Sourceless/vendor bytecode still requires exact bytes.
        optimization = next((level for level in (0, 1, 2)
            if Path(importlib.util.cache_from_source(str(source), optimization=level or '')) == installed), None)
        if optimization is None:
            return False
        payload = installed.read_bytes()
        if len(payload) < 16 or payload[:4] != importlib.util.MAGIC_NUMBER:
            return False
        code = marshal.loads(payload[16:])
        return isinstance(code, CodeType) and code == compile(
            package.read(source_name), str(source), 'exec', dont_inherit=True, optimize=optimization)
    except (OSError, KeyError, ValueError, EOFError, TypeError):
        return False


def verify_wheel(wheel):
    native = []
    with zipfile.ZipFile(wheel) as package:
        info = wheel_metadata(package)
        distribution = metadata.distribution(info['Name'])
        seen = set()
        for member in package.infolist():
            from backend.runtime_bundle import relative_resource
            name = relative_resource(member.filename.rstrip('/'))
            archive_member = name
            if name.casefold() in seen:
                raise ClosureError('Wheel contains aliased or duplicated files.')
            seen.add(name.casefold())
            if member.is_dir():
                continue
            if name.endswith('.dist-info/RECORD'):
                # pip rewrites RECORD to include installed scripts, bytecode
                # and INSTALLER/REQUESTED. It is not executable wheel payload;
                # the recorder separately hashes its actual installed bytes.
                continue
            # Windows entry scripts have installer-rewritten shebangs. They
            # are build-only; no scripts/SDK/compiler enter the frozen tree.
            data_path = None
            if '.data/' in name:
                group, _, rest = name.partition('.data/')
                category, _, tail = rest.partition('/')
                if category == 'scripts':
                    continue
                if category == 'data':
                    # sherpa-onnx-core installs its duplicate command-line DLLs
                    # in prefix/Scripts; these stay build-only, but are verified.
                    relative_resource(tail)
                    data_path = Path(sys.prefix) / tail
                elif category not in {'purelib', 'platlib'}:
                    raise ClosureError('Unreviewed wheel installation scheme: ' + group)
                name = tail
            installed = data_path or Path(distribution.locate_file(name))
            if installed.suffix.lower() in {'.dll', '.pyd', '.exe'}:
                native_path(installed)  # Reject linked ancestors before resolution.
            path = installed.resolve()
            reason = None
            if Path(sys.prefix).resolve() not in path.parents:
                reason = 'outside interpreter prefix'
            elif installed.is_symlink():
                reason = 'symbolic link'
            elif not path.is_file():
                reason = 'missing file'
            elif (path.read_bytes() != package.read(member)
                    and not verified_recompiled_cache(package, name, installed, distribution)):
                reason = 'content mismatch'
            if reason:
                # Report only the archive-relative name, never a host profile
                # path. A distribution name alone cannot diagnose native CI.
                raise ClosureError('Installed wheel payload differs from archive: '
                    + info['Name'] + ': ' + member.filename + ' (' + reason + ')')
            if path.suffix.lower() in {'.dll', '.pyd', '.exe'}:
                native.append({'path': path.relative_to(Path(sys.prefix).resolve()).as_posix(),
                    'archive_member': archive_member, 'bytes': member.file_size,
                    'sha256': hashlib.sha256(package.read(member)).hexdigest()})
    return native


NATIVE_SOURCE_INPUTS = 'NATIVE-COLLECTION-INPUTS.json'
NATIVE_SOURCE_FINAL = 'NATIVE-COLLECTION.json'
NATIVE_SOURCE_FAILED = 'NATIVE-COLLECTION-FAILED.json'
NATIVE_GENERATED = {'main': 'GameImmersionToolkit.exe', 'asr': 'asr/GameImmersionToolkitAsr.exe'}
NATIVE_FAILURES = {'invalid-identity', 'unsafe-source', 'source-unavailable', 'source-changed',
    'unbound-supplier-member', 'other-host-unresolved', 'invalid-toc', 'missing-source',
    'unexpected-transformation', 'invalid-snapshot', 'output-mismatch', 'observation-failed'}
NATIVE_ANALYSIS_ROW_LIMIT = 50000
NATIVE_ANALYSIS_NATIVE_LIMIT = 20000
NATIVE_DIAGNOSTIC_SCHEMA = 'proxy-r19-native-analysis-census-v1'
NATIVE_DIAGNOSTIC_FAMILIES = {'api-core', 'api-crt', 'ucrt', 'vc-runtime', 'not-allowlisted'}
NATIVE_DIAGNOSTIC_ROOTS = {'current-environment', 'base-interpreter', 'declared-evidence',
    'build-root', 'system-directory-descendant', 'windows-outside-system', 'other', 'unavailable'}
NATIVE_DIAGNOSTIC_PROCESSING = {'analysis-native', 'explicit-native-resource'}
NATIVE_DIAGNOSTIC_BUCKET_LIMIT = (len(NATIVE_DIAGNOSTIC_FAMILIES)
    * len(NATIVE_DIAGNOSTIC_ROOTS) * len(NATIVE_DIAGNOSTIC_PROCESSING))


class NativeCollectionError(ClosureError):
    def __init__(self, code):
        self.code = code if code in NATIVE_FAILURES else 'observation-failed'
        super().__init__('Native collection provenance refused: ' + self.code + '.')


def native_path(path, *, directory=False, missing=False):
    """Canonical local identity; never expose an underlying filesystem error."""
    try:
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts or any(ord(c) < 32 for c in str(path)):
            raise NativeCollectionError('unsafe-source')
        # Walk top-down: a leaf-first lstat/is_symlink itself traverses any
        # linked parent before that parent can be rejected.
        for item in reversed((path, *path.parents)):
            try:
                attributes = item.lstat()
            except FileNotFoundError:
                if missing and item == path:
                    return path
                raise NativeCollectionError('unsafe-source') from None
            if (stat.S_ISLNK(attributes.st_mode) or getattr(attributes, 'st_file_attributes', 0)
                    & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                raise NativeCollectionError('unsafe-source')
        if not (stat.S_ISDIR(attributes.st_mode) if directory else stat.S_ISREG(attributes.st_mode)):
            raise NativeCollectionError('unsafe-source')
        if os.path.normcase(str(path.resolve())) != os.path.normcase(str(path)):
            raise NativeCollectionError('unsafe-source')
        return path
    except NativeCollectionError:
        raise
    except Exception:
        raise NativeCollectionError('unsafe-source') from None


def native_file_identity(path):
    path = native_path(path)
    try:
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = os.fstat(stream.fileno())
        current = native_path(path).stat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if identity(before) != identity(after) or identity(before) != identity(current):
            raise NativeCollectionError('source-changed')
        return {'bytes': before.st_size, 'sha256': checksum}
    except NativeCollectionError:
        raise
    except Exception:
        raise NativeCollectionError('source-unavailable') from None


def native_system_directory():
    """Use the authoritative Win32 API, never WINDIR/SystemRoot/PATH."""
    try:
        import ctypes
        from ctypes import wintypes
        if sys.platform != 'win32':
            raise NativeCollectionError('source-unavailable')
        function = ctypes.WinDLL('kernel32.dll', use_last_error=True).GetSystemDirectoryW
        function.argtypes = (wintypes.LPWSTR, wintypes.UINT)
        function.restype = wintypes.UINT
        buffer = ctypes.create_unicode_buffer(32768)
        count = function(buffer, len(buffer))
        if not 0 < count < len(buffer):
            raise NativeCollectionError('source-unavailable')
        return native_path(buffer.value, directory=True)
    except NativeCollectionError:
        raise
    except Exception:
        raise NativeCollectionError('source-unavailable') from None


def native_windows_directory():
    """Diagnostic root only: shared Windows directory, never an admission rule."""
    try:
        import ctypes
        from ctypes import wintypes
        if sys.platform != 'win32':
            raise NativeCollectionError('source-unavailable')
        function = ctypes.WinDLL('kernel32.dll', use_last_error=True).GetSystemWindowsDirectoryW
        function.argtypes = (wintypes.LPWSTR, wintypes.UINT)
        function.restype = wintypes.UINT
        buffer = ctypes.create_unicode_buffer(32768)
        count = function(buffer, len(buffer))
        if not 0 < count < len(buffer):
            raise NativeCollectionError('source-unavailable')
        return native_path(buffer.value, directory=True)
    except NativeCollectionError:
        raise
    except Exception:
        raise NativeCollectionError('source-unavailable') from None


def native_diagnostic_family(path):
    """A finite spelling category; never supplier identity or source authority."""
    name = path.name.casefold()
    if re.fullmatch(r'api-ms-win-core-(?:[a-z0-9]+-)+l[0-9]+-[0-9]+-[0-9]+\.dll', name):
        return 'api-core'
    if re.fullmatch(r'api-ms-win-crt-(?:[a-z0-9]+-)+l[0-9]+-[0-9]+-[0-9]+\.dll', name):
        return 'api-crt'
    if name == 'ucrtbase.dll':
        return 'ucrt'
    if name in {'vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll', 'msvcp140_1.dll',
            'msvcp140_2.dll', 'msvcp140_atomic_wait.dll', 'msvcp140_codecvt_ids.dll',
            'concrt140.dll', 'vcomp140.dll'}:
        return 'vc-runtime'
    return 'not-allowlisted'


def native_project_analysis_diagnostic(value):
    """Rebuild every public field; malformed/private diagnostic input is unavailable."""
    unavailable = {'schema': NATIVE_DIAGNOSTIC_SCHEMA, 'status': 'unavailable'}
    keys = {'schema', 'status', 'scope', 'process', 'analyses', 'rows_examined',
        'native_rows_examined', 'unresolved_rows', 'row_limit', 'native_row_limit',
        'windows_root_query', 'buckets'}
    if type(value) is not dict or set(value) != keys:
        return unavailable
    if (type(value['schema']) is not str or value['schema'] != NATIVE_DIAGNOSTIC_SCHEMA
            or type(value['scope']) is not str or value['scope'] != 'current-observe-analysis-call'
            or type(value['process']) is not str or value['process'] not in NATIVE_GENERATED
            or type(value['status']) is not str or value['status'] not in {
                'complete-current-call', 'incomplete-current-call', 'truncated-row-limit', 'truncated-native-limit'}
            or type(value['windows_root_query']) is not str
            or value['windows_root_query'] not in {'not-needed', 'observed', 'unavailable'}):
        return unavailable
    analyses = value['analyses']
    if (type(analyses) is not dict or set(analyses) != set(NATIVE_GENERATED)
            or any(type(state) is not str or state not in {'current-call', 'previous-call', 'not-run'}
                for state in analyses.values())
            or {name for name, state in analyses.items() if state == 'current-call'} != {value['process']}):
        return unavailable
    for name, limit in (('row_limit', NATIVE_ANALYSIS_ROW_LIMIT), ('native_row_limit', NATIVE_ANALYSIS_NATIVE_LIMIT)):
        if type(value[name]) is not int or value[name] != limit:
            return unavailable
    for name, limit in (('rows_examined', NATIVE_ANALYSIS_ROW_LIMIT),
            ('native_rows_examined', NATIVE_ANALYSIS_NATIVE_LIMIT), ('unresolved_rows', NATIVE_ANALYSIS_NATIVE_LIMIT)):
        if type(value[name]) is not int or not 0 <= value[name] <= limit:
            return unavailable
    if (not value['unresolved_rows'] <= value['native_rows_examined'] <= value['rows_examined']
            or (value['status'] == 'truncated-row-limit' and value['rows_examined'] != NATIVE_ANALYSIS_ROW_LIMIT)
            or (value['status'] == 'truncated-native-limit' and value['native_rows_examined'] != NATIVE_ANALYSIS_NATIVE_LIMIT)):
        return unavailable
    rows = value['buckets']
    if type(rows) is not list or len(rows) > NATIVE_DIAGNOSTIC_BUCKET_LIMIT:
        return unavailable
    projected, seen = [], set()
    for row in rows:
        if (type(row) is not dict or set(row) != {'processing', 'family', 'root', 'count'}
                or any(type(row[name]) is not str for name in ('processing', 'family', 'root'))
                or row['processing'] not in NATIVE_DIAGNOSTIC_PROCESSING
                or row['family'] not in NATIVE_DIAGNOSTIC_FAMILIES or row['root'] not in NATIVE_DIAGNOSTIC_ROOTS
                or type(row['count']) is not int or not 0 < row['count'] <= NATIVE_ANALYSIS_NATIVE_LIMIT):
            return unavailable
        key = row['processing'], row['family'], row['root']
        if (key in seen or (row['root'] in {'other', 'windows-outside-system'} and value['windows_root_query'] != 'observed')
                or (row['root'] == 'unavailable' and value['windows_root_query'] != 'unavailable')):
            return unavailable
        seen.add(key)
        projected.append({'processing': key[0], 'family': key[1], 'root': key[2], 'count': row['count']})
    if sum(row['count'] for row in projected) != value['unresolved_rows']:
        return unavailable
    projected.sort(key=lambda row: (row['processing'], row['family'], row['root']))
    return {'schema': NATIVE_DIAGNOSTIC_SCHEMA, 'status': value['status'],
        'scope': 'current-observe-analysis-call', 'process': value['process'],
        'analyses': {name: analyses[name] for name in NATIVE_GENERATED},
        'rows_examined': value['rows_examined'], 'native_rows_examined': value['native_rows_examined'],
        'unresolved_rows': value['unresolved_rows'], 'row_limit': NATIVE_ANALYSIS_ROW_LIMIT,
        'native_row_limit': NATIVE_ANALYSIS_NATIVE_LIMIT, 'windows_root_query': value['windows_root_query'],
        'buckets': projected}


def native_headers(value):
    if (not isinstance(value, dict) or value.get('profile') != 'runtime-experiment'
            or not re.fullmatch(r'[a-f0-9]{40}', value.get('source_commit', ''))
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value.get('build_id', ''))):
        raise NativeCollectionError('invalid-identity')
    return {'source_commit': value['source_commit'], 'build_id': value['build_id'], 'profile': value['profile']}


def native_pending():
    return {'status': 'observed-not-approved', 'native_closure': 'unverified',
        'rights_review': 'pending-exact-output', 'source_delivery_approved': False,
        'production_execution_allowed': False, 'native_windows_11_acceptance': 'unavailable',
        'r19_complete': False, 'installer': 'not-built'}


def write_native_json(root, name, value):
    root = native_path(root, directory=True, missing=True)
    try:
        root.mkdir(exist_ok=True)
        destination = root / name
        native_path(destination, missing=True)
        with destination.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(value, indent=2) + '\n')
    except Exception:
        raise NativeCollectionError('observation-failed') from None


def native_failure(value, output, phase, error, count=0, *, analysis_diagnostic=None):
    """Best-effort fixed metadata; neither raw exceptions nor arbitrary fields."""
    try:
        try:
            headers = native_headers(value)
        except Exception:
            headers = {'source_commit': None, 'build_id': None, 'profile': 'runtime-experiment'}
        if type(phase) is not str or phase not in {'analysis', 'generated', 'collection', 'input-snapshot', 'finalize'}:
            phase = 'finalize'
        code = error.code if isinstance(error, NativeCollectionError) else None
        report = {'schema': 'proxy-r19-native-collection-failure-v1', **headers, **native_pending(),
            'status': 'failed', 'phase': phase,
            'failure_code': code if type(code) is str and code in NATIVE_FAILURES else 'observation-failed',
            'observed_records': min(max(count, 0), 20000) if type(count) is int else 0,
            'raw_paths_published': False, 'raw_toc_published': False}
        if analysis_diagnostic is not None:
            report['analysis_diagnostic'] = native_project_analysis_diagnostic(
                analysis_diagnostic if phase == 'analysis' else None)
        write_native_json(output, NATIVE_SOURCE_FAILED, report)
    except Exception:
        pass


def native_supplier_index(value, evidence):
    """Reuse archiveâ†’installed verification; input metadata cannot invent a member."""
    from native_ownership import _label, _version, _relative, _sha, _public_source
    evidence = native_path(evidence, directory=True)
    python_prefix = native_path(sys.base_prefix, directory=True)
    environment_prefix = native_path(sys.prefix, directory=True)
    index = {}
    def add(root, relative, owner, expected):
        relative = _relative(relative)
        path = root / relative
        key = os.path.normcase(str(path))
        entry = index.setdefault(key, {'path': path, 'owners': [], 'identity': expected})
        if entry['identity'] != expected:
            raise NativeCollectionError('unbound-supplier-member')
        if owner not in entry['owners']:
            entry['owners'].append(owner)
    for component in value['components']:
        name, version = _label(component['name']), _version(component['version'])
        archive = native_path(evidence / _relative(component['artifact']['path']))
        checked_file(evidence, component['artifact'])
        artifact_hash = _sha(component['artifact']['sha256'])
        artifact_identity = native_file_identity(archive)
        if artifact_identity['sha256'] != artifact_hash:
            raise NativeCollectionError('source-changed')
        installed = {_relative(item['path']).casefold(): _sha(item['sha256']) for item in component['installed_files']}
        if normalized(name) == 'cpython':
            entries = verify_python(archive, python_prefix, {'sha256': artifact_hash})
            native = []
            for item in entries:
                if Path(item['path']).suffix.lower() not in {'.dll', '.exe', '.pyd'}:
                    continue
                identity = native_file_identity(python_prefix / item['path'])
                if identity['sha256'] != item['sha256']:
                    raise NativeCollectionError('source-changed')
                native.append({**item, 'archive_member': 'python/' + item['path'], 'bytes': identity['bytes']})
            entries = native
            prefix = python_prefix
        else:
            with zipfile.ZipFile(archive) as package:
                info = wheel_metadata(package)
            if normalized(info['Name']) != normalized(name) or info['Version'] != version:
                raise NativeCollectionError('unbound-supplier-member')
            entries = verify_wheel(archive)
            prefix = environment_prefix
        if native_file_identity(archive) != artifact_identity:
            raise NativeCollectionError('source-changed')
        for item in entries:
            if installed.get(item['path'].casefold()) != item['sha256']:
                raise NativeCollectionError('unbound-supplier-member')
            owner = {'kind': 'component', 'component': name, 'version': version,
                'artifact_sha256': artifact_hash, 'input_path': _relative(item['path']),
                'archive_member': _relative(item['archive_member']), 'input_sha256': item['sha256']}
            add(prefix, item['path'], owner, {key: item[key] for key in ('bytes', 'sha256')})
    for resource in value.get('resources', []):
        name = _relative(resource['path'])
        if Path(name).suffix.lower() not in {'.dll', '.exe', '.pyd'}:
            continue
        if not name.startswith(('helpers/nte/', 'codecs/xiph-flac/')):
            raise NativeCollectionError('unbound-supplier-member')
        path = native_path(evidence / name)
        checked_file(evidence, resource)
        owner = {'kind': 'resource', 'input_path': name, 'version': _version(resource['version']),
            'input_sha256': _sha(resource['sha256']), 'source': _public_source(resource['source'])}
        identity = native_file_identity(path)
        if identity['sha256'] != resource['sha256']:
            raise NativeCollectionError('source-changed')
        add(evidence, name, owner, identity)
    return index


def native_source_record(path, index, system):
    path = native_path(path)
    entry = index.get(os.path.normcase(str(path)))
    if entry is not None:
        identity = native_file_identity(path)
        if identity != entry['identity']:
            raise NativeCollectionError('source-changed')
        candidates = [owner for item in index.values() if item['identity'] == identity for owner in item['owners']]
        source = {'role': 'declared-supplier-observed',
            'resolved_inputs': native_sorted_owners(entry['owners']),
            'byte_identical_inputs': native_sorted_owners(candidates)}
    elif system in path.parents:
        from native_ownership import _relative
        source = {'role': 'windows-system-observed', 'system_member': _relative(path.relative_to(system).as_posix()),
            'provider': 'GetSystemDirectoryW'}
        identity = native_file_identity(path)
    else:
        raise NativeCollectionError('other-host-unresolved')
    return path, identity, source


def native_sorted_owners(rows):
    return [json.loads(row) for row in sorted({json.dumps(row, sort_keys=True) for row in rows})]


class NativeCollectionObservation:
    """Consume real existing TOCs; never discover, copy or omit a DLL."""
    def __init__(self, value, evidence, output, build_root, input_manifest, *, system_directory_provider=None,
            windows_directory_provider=None):
        self.value, self.output, self.records, self.private = value, output, {}, {}
        self.analysis_started = set()
        self.windows_directory_provider = windows_directory_provider or native_windows_directory
        self.windows_root_query, self.windows_root = 'not-needed', None
        try:
            self.headers = native_headers(value)
            self.output = native_path(output, directory=True, missing=True)
            self.build_root = native_path(build_root, directory=True)
            self.input_manifest = native_path(input_manifest)
            self.input_identity = native_file_identity(self.input_manifest)
            if json.loads(self.input_manifest.read_bytes()) != value:
                raise NativeCollectionError('invalid-identity')
            self.index = native_supplier_index(value, evidence)
            self.system = (system_directory_provider or native_system_directory)()
            self.system = native_path(self.system, directory=True)
            # These roots have already passed supplier/build identity checks.
            # Retain only canonical roots, never environment/PATH guesses.
            self.diagnostic_roots = tuple((role, native_path(path, directory=True)) for role, path in (
                ('system-directory-descendant', self.system), ('current-environment', sys.prefix),
                ('base-interpreter', sys.base_prefix), ('declared-evidence', evidence), ('build-root', self.build_root)))
        except Exception as error:
            native_failure(value, self.output, 'analysis', error)
            raise NativeCollectionError(error.code if isinstance(error, NativeCollectionError) else 'observation-failed') from None

    def _source(self, path):
        return native_source_record(path, self.index, self.system)

    def _diagnostic_root(self, path):
        matches = [(len(root.parts), -order, role) for order, (role, root) in enumerate(self.diagnostic_roots)
            if path == root or root in path.parents]
        if matches:
            return max(matches)[2]
        if self.windows_root_query == 'not-needed':
            try:
                self.windows_root = native_path(self.windows_directory_provider(), directory=True)
                self.windows_root_query = 'observed'
            except Exception:
                # This root is diagnostic only. Unavailability never selects a
                # fallback root or changes the existing source refusal.
                self.windows_root_query = 'unavailable'
        if self.windows_root_query == 'unavailable':
            return 'unavailable'
        return 'windows-outside-system' if self.windows_root in path.parents else 'other'

    def _add(self, name, record, path):
        if len(self.records) >= 20000 and name not in self.records:
            raise NativeCollectionError('invalid-toc')
        if any(prior.casefold() == name.casefold() and prior != name for prior in self.records):
            raise NativeCollectionError('invalid-toc')
        if name in self.records and self.records[name] != record:
            raise NativeCollectionError('invalid-toc')
        self.records[name] = record; self.private[name] = path

    def refuse_collection(self, error):
        native_failure(self.value, self.output, 'collection', error, len(self.records))
        raise NativeCollectionError('observation-failed') from None

    def observe_analysis(self, process, binaries, explicit=()):
        diagnostic = None
        try:
            if process not in NATIVE_GENERATED:
                raise NativeCollectionError('invalid-toc')
            diagnostic = {'schema': NATIVE_DIAGNOSTIC_SCHEMA, 'status': 'incomplete-current-call',
                'scope': 'current-observe-analysis-call', 'process': process,
                'analyses': {name: ('current-call' if name == process else
                    'previous-call' if name in self.analysis_started else 'not-run') for name in NATIVE_GENERATED},
                'rows_examined': 0, 'native_rows_examined': 0, 'unresolved_rows': 0,
                'row_limit': NATIVE_ANALYSIS_ROW_LIMIT, 'native_row_limit': NATIVE_ANALYSIS_NATIVE_LIMIT,
                'windows_root_query': 'not-needed', 'buckets': []}
            self.analysis_started.add(process)
            buckets = {}
            for rows, processing in ((binaries, 'analysis-native'), (explicit, 'explicit-native-resource')):
                for row in rows:
                    if diagnostic['rows_examined'] >= NATIVE_ANALYSIS_ROW_LIMIT:
                        diagnostic['status'] = 'truncated-row-limit'
                        raise NativeCollectionError('invalid-toc')
                    diagnostic['rows_examined'] += 1
                    if not isinstance(row, (tuple, list)) or len(row) != 3:
                        raise NativeCollectionError('invalid-toc')
                    destination, origin, kind = row
                    from native_ownership import _relative
                    destination = _relative(destination.replace('\\', '/'))
                    if Path(destination).suffix.lower() not in {'.dll', '.exe', '.pyd'}:
                        continue
                    if diagnostic['native_rows_examined'] >= NATIVE_ANALYSIS_NATIVE_LIMIT:
                        diagnostic['status'] = 'truncated-native-limit'
                        raise NativeCollectionError('invalid-toc')
                    diagnostic['native_rows_examined'] += 1
                    if kind not in {'BINARY', 'EXTENSION', 'DATA'}:
                        raise NativeCollectionError('invalid-toc')
                    try:
                        path, identity, source = self._source(origin)
                    except NativeCollectionError as error:
                        if error.code != 'other-host-unresolved':
                            raise
                        # Canonical path metadata only. Never open/hash the
                        # unknown source or add a source/output record for it.
                        path = native_path(origin)
                        key = processing, native_diagnostic_family(path), self._diagnostic_root(path)
                        diagnostic['windows_root_query'] = self.windows_root_query
                        if key not in buckets:
                            bucket = {'processing': key[0], 'family': key[1], 'root': key[2], 'count': 0}
                            buckets[key] = bucket
                            diagnostic['buckets'].append(bucket)
                        buckets[key]['count'] += 1
                        diagnostic['unresolved_rows'] += 1
                        continue
                    if processing == 'explicit-native-resource' and (source['role'] != 'declared-supplier-observed'
                            or not any(item['kind'] == 'resource' for item in source['resolved_inputs'])):
                        raise NativeCollectionError('unbound-supplier-member')
                    name = ('asr/' if process == 'asr' else '') + '_internal/' + destination
                    record = {'path': name, 'process': process, 'processing': processing, **identity, 'source': source}
                    self._add(name, record, path)
            diagnostic['status'] = 'complete-current-call'
            if diagnostic['unresolved_rows']:
                raise NativeCollectionError('other-host-unresolved')
        except Exception as error:
            native_failure(self.value, self.output, 'analysis', error, len(self.records), analysis_diagnostic=diagnostic)
            raise NativeCollectionError(error.code if isinstance(error, NativeCollectionError) else 'observation-failed') from None

    def observe_generated(self, process, path):
        try:
            if process not in NATIVE_GENERATED:
                raise NativeCollectionError('invalid-toc')
            path = native_path(path)
            if self.build_root not in path.parents:
                raise NativeCollectionError('unsafe-source')
            name = NATIVE_GENERATED[process]
            if name in self.records:
                raise NativeCollectionError('invalid-toc')
            self.records[name] = {'path': name, 'process': process, 'processing': 'pyinstaller-generated-executable',
                **native_file_identity(path), 'source': {'role': 'generated-processing-observed',
                'internals_provenance': 'unverified'}}
            self.private[name] = path
        except Exception as error:
            native_failure(self.value, self.output, 'generated', error, len(self.records))
            raise NativeCollectionError(error.code if isinstance(error, NativeCollectionError) else 'observation-failed') from None

    def finish(self):
        try:
            if not set(NATIVE_GENERATED.values()) <= set(self.records):
                raise NativeCollectionError('missing-source')
            if native_file_identity(self.input_manifest) != self.input_identity:
                raise NativeCollectionError('source-changed')
            for name, path in self.private.items():
                if native_file_identity(path) != {key: self.records[name][key] for key in ('bytes', 'sha256')}:
                    raise NativeCollectionError('source-changed')
            report = {'schema': 'proxy-r19-native-collection-inputs-v1', **self.headers, **native_pending(),
                'build_inputs': self.input_identity, 'records': [self.records[name] for name in sorted(self.records)],
                'raw_paths_published': False, 'raw_toc_published': False}
            write_native_json(self.output, NATIVE_SOURCE_INPUTS, report)
            return report
        except Exception as error:
            native_failure(self.value, self.output, 'input-snapshot', error, len(self.records))
            raise NativeCollectionError(error.code if isinstance(error, NativeCollectionError) else 'observation-failed') from None


def python_supplier_notice_files(source, pin):
    """Validate retained primary texts, without approving native applicability."""
    from backend.prebuilt_readers import _no_links
    root = source / 'packaging/runtime-bundle/python-notices'
    _no_links(root.absolute())
    provenance = root / 'PROVENANCE.json'
    _no_links(provenance.absolute())
    if not provenance.is_file() or provenance.stat().st_size > 65536:
        raise ClosureError('Retained Python supplier notice provenance is missing or oversized.')
    value = json.loads(provenance.read_text(encoding='utf-8'))
    supplier = {key: pin[key] for key in ('supplier', 'version', 'architecture', 'release', 'source_commit', 'sha256')}
    archive = value.get('archive', {})
    name = f"cpython-{pin['version']}+{pin['release']}-x86_64-pc-windows-msvc-pgo-full.tar.zst"
    url = f"https://github.com/astral-sh/python-build-standalone/releases/download/{pin['release']}/{name.replace('+', '%2B')}"
    if (value.get('schema') != 'proxy-python-supplier-notices-v1' or value.get('supplier') != supplier
            or value.get('native_closure') != 'unverified' or value.get('redistribution_review') != 'pending-exact-output'
            or not isinstance(archive, dict) or archive.get('name') != name or archive.get('url') != url
            or archive.get('github_release_id') != pin['github_release_id']
            or type(archive.get('github_asset_id')) is not int or archive['github_asset_id'] <= 0
            or type(archive.get('bytes')) is not int or not 0 < archive['bytes'] <= 100 * 1024 * 1024
            or not isinstance(archive.get('sha256'), str) or len(archive['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in archive['sha256'])):
        raise ClosureError('Retained Python notices differ from the exact observed supplier identity.')
    files = value.get('files')
    if not isinstance(files, list) or len(files) != 20:
        raise ClosureError('Retain all twenty original supplier notice files.')
    entries, names = [], set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {'path', 'archive_member', 'bytes', 'sha256'}:
            raise ClosureError('Supplier notice attributes are incomplete.')
        name = entry['path']
        if (not isinstance(name, str) or not name.startswith('LICENSE.') or not name.endswith('.txt')
                or Path(name).name != name or '/' in name or '\\' in name or ':' in name
                or name.casefold() in names or entry['archive_member'] != 'python/licenses/' + name
                or type(entry['bytes']) is not int or not 0 < entry['bytes'] <= 256 * 1024):
            raise ClosureError('Supplier notice member identity is invalid or aliased.')
        _no_links((root / name).absolute())
        original = checked_file(root, entry)
        if original.stat().st_size != entry['bytes']:
            raise ClosureError('Retained supplier notice length differs from provenance.')
        names.add(name.casefold()); entries.append(original)
    if {path.name.casefold() for path in root.iterdir()} != names | {'provenance.json'}:
        raise ClosureError('Retained supplier notice directory contains unrecorded files.')
    return [provenance, *entries]


def expected_python_notice_records(source, pin):
    return [{'path': 'licenses/cpython/supplier/' + path.name,
        'sha256': digest(path), 'bytes': path.stat().st_size}
        for path in python_supplier_notice_files(source, pin)]


def collect_python_notices(evidence, source, pin):
    """Copy notice-only delivery into the existing hashed THIRD_PARTY path."""
    import shutil
    from backend.prebuilt_readers import _no_links
    originals = python_supplier_notice_files(source, pin)
    target = evidence / 'licenses/cpython/supplier'
    _no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Never replace an existing evidence set.
    records = []
    for original in originals:
        destination = target / original.name
        shutil.copyfile(original, destination)
        if digest(destination) != digest(original):
            raise ClosureError('Supplier notice changed during evidence delivery.')
        records.append({'path': destination.relative_to(evidence).as_posix(),
            'sha256': digest(destination), 'bytes': destination.stat().st_size})
    return records


def collect_onnx_third_party_notice(evidence, component):
    """Bind the wheel's incorporated notices, which the generic prefix scan misses."""
    import hashlib
    from backend.prebuilt_readers import _no_links
    member = 'onnxruntime/ThirdPartyNotices.txt'
    if normalized(component['name']) != 'onnxruntime' or component['architecture'] != 'win-amd64':
        raise ClosureError('ONNX native notices need the selected Windows x64 component.')
    archive = checked_file(evidence, component['artifact'])
    _no_links(archive.absolute())
    with zipfile.ZipFile(archive) as package:
        info = wheel_metadata(package)
        if (normalized(info['Name']) != 'onnxruntime' or info['Version'] != component['version']
                or package.namelist().count(member) != 1):
            raise ClosureError('ONNX third-party notices are missing, ambiguous or from another wheel.')
        data = package.read(member)
    if not 1 <= len(data) <= 2 * 1024 * 1024:
        raise ClosureError('ONNX third-party notice text is empty or oversized.')
    checksum = hashlib.sha256(data).hexdigest()
    installed = metadata.distribution(component['name'])
    original = Path(installed.locate_file(member)).absolute()
    prefix = Path(sys.prefix).absolute()
    _no_links(original)
    if installed.version != component['version'] or prefix not in original.parents:
        raise ClosureError('Installed ONNX notice differs from the selected build environment.')
    installed_record = {'path': original.relative_to(prefix).as_posix(), 'sha256': checksum}
    if installed_record not in component['installed_files']:
        raise ClosureError('Installed ONNX third-party notice is not bound to its observed wheel bytes.')
    if checked_file(prefix, installed_record).stat().st_size != len(data):
        raise ClosureError('Installed ONNX third-party notice length differs from the wheel.')
    target = evidence / 'licenses/onnxruntime/ThirdPartyNotices.txt'
    _no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    return {'path': target.relative_to(evidence).as_posix(), 'sha256': checksum, 'bytes': len(data)}


def _flatbuffers_notice_inputs(evidence, source, component, *, check_installed):
    """Bind the retained source notice to the exact source-identical wheel."""
    import hashlib
    from backend.prebuilt_readers import _no_links
    from backend.runtime_bundle import relative_resource
    root = source / 'packaging/runtime-bundle/flatbuffers-notices'
    provenance = root / 'PROVENANCE.json'
    _no_links(provenance.absolute())
    if not provenance.is_file() or provenance.stat().st_size > 65536:
        raise ClosureError('Retained Flatbuffers source provenance is missing or oversized.')
    value = json.loads(provenance.read_bytes())
    if not isinstance(value, dict):
        raise ClosureError('Retained Flatbuffers source provenance is invalid.')
    wheel, origin, notice = value.get('wheel', {}), value.get('source', {}), value.get('notice', {})
    version = component['version']
    if (value.get('schema') != 'proxy-flatbuffers-source-notices-v1' or value.get('version') != version
            or normalized(component['name']) != 'flatbuffers' or component['architecture'] != 'any'
            or value.get('redistribution_review') != 'pending-exact-output' or value.get('native_closure') != 'unverified'
            or value.get('production_execution_allowed') is not False or value.get('upstream_NOTICE_file_observed') is not False
            or not isinstance(wheel, dict) or wheel.get('sha256') != component['artifact']['sha256']
            or wheel.get('name') != f'flatbuffers-{version}-py2.py3-none-any.whl'
            or not isinstance(origin, dict) or origin.get('repository') != 'https://github.com/google/flatbuffers'
            or origin.get('tag') != 'v' + version or not isinstance(origin.get('commit'), str)
            or len(origin['commit']) != 40 or any(c not in '0123456789abcdef' for c in origin['commit'])
            or origin.get('archive_url') != 'https://codeload.github.com/google/flatbuffers/tar.gz/' + origin['commit']
            or not isinstance(origin.get('archive_sha256'), str) or len(origin['archive_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in origin['archive_sha256'])
            or not isinstance(notice, dict) or set(notice) != {'path', 'source_member', 'bytes', 'sha256'}
            or notice.get('path') != 'LICENSE' or notice.get('source_member') != 'LICENSE'
            or type(notice.get('bytes')) is not int or not 0 < notice['bytes'] <= 256 * 1024):
        raise ClosureError('Retained Flatbuffers notice differs from the exact observed wheel/source identity.')
    license_file = checked_file(root, notice)
    _no_links(license_file.absolute())
    if license_file.stat().st_size != notice['bytes']:
        raise ClosureError('Retained Flatbuffers notice length differs from source provenance.')
    payload = value.get('python_payload')
    if not isinstance(payload, list) or len(payload) != 10:
        raise ClosureError('Retain all ten source-identical Flatbuffers Python member identities.')
    archive = checked_file(evidence, component['artifact'])
    _no_links(archive.absolute())
    if archive.stat().st_size != wheel.get('bytes'):
        raise ClosureError('Flatbuffers wheel length differs from source provenance.')
    installed = metadata.distribution('flatbuffers') if check_installed else None
    if installed is not None and installed.version != version:
        raise ClosureError('Installed Flatbuffers version differs from the observed wheel.')
    seen = set()
    with zipfile.ZipFile(archive) as package:
        info = wheel_metadata(package)
        if normalized(info['Name']) != 'flatbuffers' or info['Version'] != version:
            raise ClosureError('Flatbuffers source notices belong to another wheel identity.')
        for entry in payload:
            if not isinstance(entry, dict) or set(entry) != {'path', 'source_member', 'bytes', 'sha256'}:
                raise ClosureError('Flatbuffers source member attributes are incomplete.')
            name = relative_resource(entry['path'])
            if (not name.startswith('flatbuffers/') or not name.endswith('.py') or name in seen
                    or entry['source_member'] != 'python/' + name or package.namelist().count(name) != 1
                    or type(entry['bytes']) is not int or not 0 < entry['bytes'] <= 1024 * 1024):
                raise ClosureError('Flatbuffers source member identity is missing or aliased.')
            seen.add(name)
            data = package.read(name)
            records = [row for row in component.get('installed_files', [])
                if row['path'] == name or row['path'].endswith('/' + name)]
            if (len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']
                    or len(records) != 1 or records[0]['sha256'] != entry['sha256']):
                raise ClosureError('Flatbuffers source/wheel/observed installed bytes differ.')
            relative_resource(records[0]['path'])
            if installed is not None:
                original = Path(installed.locate_file(name)).absolute()
                _no_links(original)
                prefix = Path(sys.prefix).absolute()
                if (prefix not in original.parents or original.relative_to(prefix).as_posix() != records[0]['path']
                        or checked_file(prefix, records[0]).stat().st_size != entry['bytes']):
                    raise ClosureError('Installed Flatbuffers payload differs from its verified wheel.')
        if seen != {name for name in package.namelist() if name.startswith('flatbuffers/') and name.endswith('.py')}:
            raise ClosureError('Flatbuffers wheel has unbound Python source members.')
    return [license_file, provenance]


def expected_flatbuffers_notice_records(evidence, source, component):
    return [{'path': 'licenses/flatbuffers/source/' + path.name,
        'sha256': digest(path), 'bytes': path.stat().st_size}
        for path in _flatbuffers_notice_inputs(evidence, source, component, check_installed=False)]


def collect_flatbuffers_notices(evidence, source, component):
    import shutil
    from backend.prebuilt_readers import _no_links
    originals = _flatbuffers_notice_inputs(evidence, source, component, check_installed=True)
    target = evidence / 'licenses/flatbuffers/source'
    _no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Preserve any existing evidence instead of replacing it.
    records = []
    for original in originals:
        destination = target / original.name
        shutil.copyfile(original, destination)
        if digest(destination) != digest(original):
            raise ClosureError('Retained Flatbuffers notice changed during delivery.')
        records.append({'path': destination.relative_to(evidence).as_posix(),
            'sha256': digest(destination), 'bytes': destination.stat().st_size})
    return records


def observe(evidence, frontend, build_id, source=ROOT, *, nte_helper_root, codec_root):
    import shutil
    pin = json.loads((source / 'packaging/runtime-bundle/python-supplier.json').read_text())
    installed_python = verify_python(evidence / pin['archive'], Path(sys.base_prefix), pin)
    for wheel in sorted((evidence / 'wheelhouse').glob('*.whl')):
        verify_wheel(wheel)
    value = record(evidence, pin['archive'], pin['url'], build_id, source, frontend, metadata_notices=True)
    value['profile'] = 'runtime-experiment'
    for item in value['components']:
        item['review_status'] = 'observed-experiment'
    python = value['components'][0]
    if python['version'] != pin['version']:
        raise ClosureError('Interpreter version differs from the pinned supplier.')
    python['installed_files'] = installed_python
    python['licenses'].extend(collect_python_notices(evidence, source, pin))
    python['notice_review'] = 'Exact supplier texts retained; native applicability, ownership and redistribution conditions remain pending'
    onnx = next((item for item in value['components'] if normalized(item['name']) == 'onnxruntime'), None)
    if onnx is None:
        raise ClosureError('The locked ONNX Runtime component is missing.')
    onnx['licenses'].append(collect_onnx_third_party_notice(evidence, onnx))
    flatbuffers = next((item for item in value['components'] if normalized(item['name']) == 'flatbuffers'), None)
    if flatbuffers is None:
        raise ClosureError('The locked Flatbuffers component is missing.')
    flatbuffers['licenses'].extend(collect_flatbuffers_notices(evidence, source, flatbuffers))
    value['python_supplier'] = pin
    value['runtime_lock_sha256'] = digest(source / 'requirements.lock.txt')
    helpers, value['helpers'] = collect_nte(nte_helper_root, evidence, value['source_commit'], source)
    value['resources'].extend(helpers)
    codecs, value['codecs'] = collect_codec(codec_root, evidence, value['source_commit'], source)
    value['resources'].extend(codecs)
    for name in RESOURCES:
        original = source / name
        destination = evidence / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        value['resources'].append({'path': name, 'sha256': digest(original), 'version': value['source_commit'],
            'source': 'https://github.com/Firebird55/Game-immersion-toolkit/tree/' + value['source_commit'],
            'license_expression': 'Observed source/model notices; exact-output review pending'})
    model = json.loads((source / 'assets/fireredvad/PROVENANCE.json').read_text())
    for item in model['files']:
        checked_file(source / 'assets/fireredvad', {'path': item['file'], 'sha256': item['sha256']})
    value['status'] = 'Quarantined integrated runtime experiment; rights, Windows 11 and full R19 acceptance remain open'
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--frontend-root', type=Path, required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nte-helper-root', type=Path, required=True)
    parser.add_argument('--codec-root', type=Path, required=True)
    args = parser.parse_args()
    value = observe(args.evidence.resolve(), args.frontend_root.resolve(), args.build_id,
        nte_helper_root=args.nte_helper_root, codec_root=args.codec_root)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
