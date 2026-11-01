"""Opt-in R19 copy/verify experiment for synthetic fixture state only.

No CLI, account call, DPAPI decryption, live-data activation or browser-profile
copy is provided. A coordinator-minted stopped-writer barrier is mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
from types import MappingProxyType
from typing import Callable, Mapping
import uuid

from backend.bundle_host import (FRONTEND_ORIGIN, HostProbeError, SyntheticRoot,
                                 SyntheticWriterBarrier, _atomic_json, _reject_links)


@dataclass(frozen=True)
class SyntheticMigrationPlan:
    source: SyntheticRoot
    target: SyntheticRoot
    migration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    external_destinations: tuple[SyntheticRoot, ...] = ()
    database_versions: Mapping[str, int] = field(default_factory=dict)
    named_account_store: str = 'unverified'

    def __post_init__(self):
        object.__setattr__(self, 'database_versions', MappingProxyType(dict(self.database_versions)))

    def verify(self) -> None:
        str(uuid.UUID(self.migration_id))
        roots = (self.source, self.target, *self.external_destinations)
        for root in roots:
            root.verify()
            if root.installation_id != self.source.installation_id:
                raise HostProbeError('ownership-mismatch', 'Every fixture root must have the same installation identity.')
        for index, root in enumerate(roots):
            for other in roots[index + 1:]:
                if root.path.is_relative_to(other.path) or other.path.is_relative_to(root.path):
                    raise HostProbeError('overlapping-roots', 'Migration fixture roots must not overlap.')
        if self.named_account_store not in {'unverified', 'unreadable'}:
            raise HostProbeError('invalid-credential-state', 'Named account verification is unverified or requires preserving repair.')
        if any(not isinstance(version, int) or isinstance(version, bool) or version < 0 for version in self.database_versions.values()):
            raise HostProbeError('invalid-database-version', 'Expected SQLite versions must be nonnegative integers.')


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path, *, prefix: str = '', skip_lock=False, skip_marker=False) -> tuple[list[dict], list[str]]:
    files, directories, aliases = [], [], {}
    if not root.exists():
        return files, directories
    _reject_links(root)
    for directory, children, names in os.walk(root, followlinks=False):
        children.sort()
        names.sort()
        for name in children:
            child = Path(directory) / name
            _reject_links(child)
            directories.append((Path(prefix) / child.relative_to(root)).as_posix())
        for name in names:
            path = Path(directory) / name
            _reject_links(path)
            local = path.relative_to(root).as_posix()
            if (skip_marker and local == '.r19-synthetic-fixture.json') or (skip_lock and local == 'companion-operation.lock'):
                continue
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise HostProbeError('unsupported-file', 'Only regular synthetic files can be copied.')
            identity = (metadata.st_dev, metadata.st_ino)
            alias = aliases.setdefault(identity, len(aliases) + 1)
            files.append({'name': (Path(prefix) / local).as_posix(), 'size': metadata.st_size,
                          'sha256': _digest(path), 'alias_group': alias})
    return files, directories


def _source_inventory(plan: SyntheticMigrationPlan) -> tuple[list[dict], list[str]]:
    files, directories = [], []
    # Settings keep their separate precedence. Only the reviewed ZZZ work group
    # is copied; unrelated old-root content stays in place.
    for group in ('data', 'host-settings', 'work/voice-assets'):
        path = plan.source.path / group
        group_files, group_directories = _inventory(path, prefix=group, skip_lock=group == 'data')
        files.extend(group_files)
        if path.exists():
            directories.append(group)
        directories.extend(group_directories)
    return files, directories


def _fingerprint(files: list[dict], directories: list[str]) -> str:
    return hashlib.sha256(json.dumps([files, directories], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _verify_snapshot(snapshot: Path, files: list[dict], directories: list[str]) -> None:
    actual, actual_directories = _inventory(snapshot)
    fields = ('name', 'size', 'sha256')
    normalized = lambda values: sorted(tuple(item[key] for key in fields) for item in values)
    expected_directories = set(directories)
    for name in (*directories, *(item['name'] for item in files)):
        expected_directories.update(parent.as_posix() for parent in Path(name).parents if parent != Path('.'))
    if normalized(actual) != normalized(files) or set(actual_directories) != expected_directories:
        raise HostProbeError('target-inventory-mismatch', 'The owned snapshot has missing, changed or unexpected entries; retain it for recovery.')


def _verify_databases(snapshot: Path, plan: SyntheticMigrationPlan, files: list[dict]) -> list[dict]:
    result = []
    for item in files:
        path = snapshot / item['name']
        with path.open('rb') as stream:
            sqlite = stream.read(16) == b'SQLite format 3\x00'
        if not sqlite:
            if path.suffix == '.db':
                raise HostProbeError('invalid-database', 'A named synthetic database is not a readable SQLite database.')
            continue
        expected = plan.database_versions.get(item['name'])
        if expected is None:
            raise HostProbeError('unknown-database-schema', 'Record the expected schema version for every synthetic SQLite store.')
        # Read a separate verification copy so SQLite WAL/SHM handling cannot
        # modify the byte-preserving snapshot or the unchanged source.
        with tempfile.TemporaryDirectory(prefix='r19-sqlite-verify-', dir=plan.target.path) as temporary:
            database = Path(temporary) / 'store.db'
            shutil.copy2(path, database)
            for suffix in ('-wal', '-shm'):
                if path.with_name(path.name + suffix).exists():
                    shutil.copy2(path.with_name(path.name + suffix), database.with_name(database.name + suffix))
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
            try:
                integrity = connection.execute('PRAGMA integrity_check').fetchall()
                version = connection.execute('PRAGMA user_version').fetchone()[0]
            finally:
                connection.close()
        if integrity != [('ok',)]:
            raise HostProbeError('database-integrity-failed', 'Synthetic database integrity verification failed.')
        if version != expected:
            raise HostProbeError('incompatible-database-schema', 'The copied database does not match its expected schema version.')
        result.append({'name': item['name'], 'user_version': version, 'integrity': 'ok',
                       'consistency': 'all-writers-stopped-file-set-including-WAL-SHM'})
    return result


def copy_and_verify_synthetic(plan: SyntheticMigrationPlan, barrier: SyntheticWriterBarrier,
                              *, checkpoint: Callable[[str, str | None], None] | None = None) -> dict:
    """Resume an owned partial copy, preserve source, and stop at verified.

    The caller holds coordinator serialization and both leases throughout. A
    callback is only a fault-injection hook; it cannot grant writer exclusion.
    """
    plan.verify()
    if not isinstance(barrier, SyntheticWriterBarrier):
        raise HostProbeError('writer-barrier-required', 'Readiness is not a stopped-writer barrier.')
    barrier.check(plan.source)
    barrier.check_target(plan.target)
    files, directories = _source_inventory(plan)
    fingerprint = _fingerprint(files, directories)
    external = []
    for root in plan.external_destinations:
        inventory, folders = _inventory(root.path, skip_marker=True)
        external.append({'fixture_id': root.fixture_id, 'action': 'preserve-external-in-place',
                         'files': inventory, 'directories': folders,
                         'free_bytes_observed': shutil.disk_usage(root.path).free})
    manifest_path = plan.target.path / 'migrations' / plan.migration_id / 'manifest.json'
    snapshot = plan.target.path / 'staging' / plan.migration_id
    _reject_links(manifest_path)
    _reject_links(snapshot)
    binding = {'source_fixture_id': plan.source.fixture_id, 'target_fixture_id': plan.target.fixture_id,
               'inventory_sha256': fingerprint, 'database_versions': dict(plan.database_versions),
               'external_inventory': [{key: item[key] for key in ('fixture_id', 'files', 'directories')} for item in external],
               'named_account_store': plan.named_account_store}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise HostProbeError('invalid-manifest', 'Retain the partial target; its migration manifest needs recovery.') from error
        if (manifest.get('schema') != 'proxy-storage-migration-v1'
                or manifest.get('migration_id') != plan.migration_id or manifest.get('binding') != binding):
            raise HostProbeError('source-or-plan-changed', 'Retain the partial target and source; the copy identity changed.')
    else:
        if snapshot.exists():
            raise HostProbeError('unowned-staging', 'A staging tree without its matching manifest cannot be adopted.')
        manifest = {'schema': 'proxy-storage-migration-v1', 'migration_id': plan.migration_id,
                    'synthetic_only': True, 'binding': binding, 'state': 'planned', 'completed_files': [],
                    'roots': {'source': str(plan.source.path), 'target': str(plan.target.path)},
                    'consistency': 'coordinator-stopped-all-fixture-writers',
                    'legacy_operation_lock': 'continuously-held-not-copied',
                    'unknown_old_root_files': 'preserved-in-place', 'inventory': files,
                    'external_destinations': external,
                    'credentials': {'protection': 'dpapi-current-user', 'host_locators': 'unchanged',
                                    'locators': [{'role': role, 'source': relative, 'action': 'preserve-host-locator-in-place',
                                                  'present': (plan.source.path / relative).exists()}
                                                 for role, relative in (('named-profiles', 'host-credentials/accounts.dpapi'),
                                                                        ('legacy-host-key', 'host-credentials/key.dpapi'))],
                                    'named_profiles': 'unreadable-repair-required' if plan.named_account_store == 'unreadable' else 'unverified-native',
                                    'legacy_data_fallback': 'encrypted-bytes-preserved-if-present',
                                    'decryption': 'not-attempted'},
                    'browser': {'origin': FRONTEND_ORIGIN, 'profile': 'existing-selected-profile',
                                'localStorage': 'unchanged-unverified', 'indexedDB': 'unchanged-unverified',
                                'opfs': 'unchanged-unverified', 'userscript_storage': 'unchanged-extension-owned',
                                'raw_profile_copy': False},
                    'activation_allowed': False, 'installed_launcher_checkpoint': 'unchanged-unverified-R20',
                    'open_requirements': ['Native Windows process ownership/global writer barrier',
                                          'Guarded source updater without nested lock acquisition',
                                          'Same-user DPAPI and ordinary browser/profile verification']}
        if plan.named_account_store == 'unreadable':
            manifest['open_requirements'].append('Preserving repair and deliberate reconnection for unreadable named account store')
        _atomic_json(manifest_path, manifest)
    # Budget every name, including hardlink aliases; destination volumes may not
    # support source hardlinks. A separate database verification copy also fits.
    required = sum(item['size'] for item in files) * 2 + 1024 * 1024
    if shutil.disk_usage(plan.target.path).free < required:
        raise HostProbeError('insufficient-space', 'The synthetic target needs space for copy and verification while retaining source.')
    snapshot.mkdir(parents=True, exist_ok=True)
    try:
        manifest['state'] = 'copying'
        manifest['last_checkpoint'] = 'inventory-recorded'
        _atomic_json(manifest_path, manifest)
        for directory in directories:
            destination = snapshot / directory
            _reject_links(destination)
            destination.mkdir(parents=True, exist_ok=True)
        for item in files:
            barrier.check(plan.source)
            source = plan.source.path / item['name']
            destination = snapshot / item['name']
            _reject_links(source)
            _reject_links(destination)
            if not (destination.exists() and destination.stat().st_size == item['size'] and _digest(destination) == item['sha256']):
                partial = plan.target.path / 'copy-work' / plan.migration_id / uuid.uuid4().hex
                _reject_links(partial)
                partial.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with source.open('rb') as reader, partial.open('xb') as writer:
                        shutil.copyfileobj(reader, writer, length=1024 * 1024)
                        writer.flush()
                        os.fsync(writer.fileno())
                    if partial.stat().st_size != item['size'] or _digest(partial) != item['sha256']:
                        raise HostProbeError('source-changed', 'The synthetic source changed while copying; retain both trees.')
                    shutil.copystat(source, partial, follow_symlinks=False)
                    os.replace(partial, destination)
                finally:
                    partial.unlink(missing_ok=True)
            if item['name'] not in manifest['completed_files']:
                manifest['completed_files'].append(item['name'])
            manifest['last_checkpoint'] = item['name']
            _atomic_json(manifest_path, manifest)
            if checkpoint:
                checkpoint('file-copied', item['name'])
        barrier.check(plan.source)
        final_files, final_directories = _source_inventory(plan)
        if _fingerprint(final_files, final_directories) != fingerprint:
            raise HostProbeError('source-changed', 'The source file set changed despite the fixture writer barrier.')
        for root, expected in zip(plan.external_destinations, external):
            actual, folders = _inventory(root.path, skip_marker=True)
            if actual != expected['files'] or folders != expected['directories']:
                raise HostProbeError('external-source-changed', 'External export/work state changed; do not activate the snapshot.')
        manifest['databases'] = _verify_databases(snapshot, plan, files)
        for item in files:
            if _digest(snapshot / item['name']) != item['sha256']:
                raise HostProbeError('target-changed', 'The synthetic target changed during verification.')
        _verify_snapshot(snapshot, files, directories)
        barrier.check(plan.source)
        manifest['state'] = 'verified'
        manifest['last_checkpoint'] = 'copy-and-database-verification-complete'
        manifest['copy_verification'] = 'passed'
        manifest['migration_acceptance'] = 'incomplete'
        _atomic_json(manifest_path, manifest)
        if checkpoint:
            checkpoint('verified', None)
        return manifest
    except BaseException as error:
        if isinstance(error, HostProbeError) and error.code in {'source-changed', 'external-source-changed', 'writer-barrier-required'}:
            barrier.invalidate()
        manifest['state'] = 'failed'
        manifest['failure'] = error.code if isinstance(error, HostProbeError) else type(error).__name__
        _atomic_json(manifest_path, manifest)
        raise
