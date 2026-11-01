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
    state_bindings: SyntheticStateBindings | None = field(default=None, repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'database_versions', MappingProxyType(dict(self.database_versions)))

    def verify(self) -> None:
        str(uuid.UUID(self.migration_id))
        roots = (self.source, self.target, *self.external_destinations)
        if self.state_bindings is not None:
            if type(self.state_bindings) is not SyntheticStateBindings:
                raise HostProbeError('invalid-state-binding', 'Mapped state needs its actual programmatic owners.')
            for root in roots:
                _state_path(root.path, directory=True)
            self.state_bindings.verify(self.source, self.external_destinations)
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


def _state_path(path, *, directory=None, missing=False):
    """Mapped-state paths are checked root first, before descendant metadata."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise HostProbeError('invalid-state-binding', 'Mapped state paths must be canonical owned paths.')
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing:
                return None
            raise HostProbeError('missing-state-root', 'An explicitly owned state root is unavailable.') from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise HostProbeError('linked-state-root', 'Mapped state cannot traverse links or reparse points.')
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise HostProbeError('invalid-state-binding', 'Mapped state ancestors must be directories.')
    if (directory is True and not stat.S_ISDIR(info.st_mode)
            or directory is False and not stat.S_ISREG(info.st_mode)
            or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
        raise HostProbeError('invalid-state-binding', 'Mapped state contains an unsupported file type.')
    return info


def _test_credential_family(settings_root):
    """One bounded opaque TEST member, for both source and verification clone."""
    credential_root = Path(settings_root)/'credentials'
    _state_path(credential_root, directory=True)
    with os.scandir(credential_root) as entries:
        names = []
        for entry in entries:
            if names or entry.name != 'accounts.dpapi':
                raise HostProbeError('invalid-state-binding', 'The copied TEST credential family differs.')
            names.append(entry.name)
    account = credential_root/'accounts.dpapi'
    if names != ['accounts.dpapi'] or _state_path(account, directory=False).st_size > 8192:
        raise HostProbeError('invalid-state-binding', 'The copied TEST credential family differs.')
    return account


@dataclass(frozen=True, repr=False)
class SyntheticStateBindings:
    """Fixed authored role map from actual owners, never roots read from JSON.

    SQL fences only retire the fixture's setup-operation scopes. The existing
    coordinator's whole-cohort barrier remains separately mandatory for copy.
    """
    source: SyntheticRoot
    layout: object
    settings: object
    languages: object
    installation: object
    manual: tuple
    automatic: object
    accounts: object
    export_root: SyntheticRoot
    host_root: SyntheticRoot
    export_output: Path
    export_work: Path
    sql_fences: tuple = field(repr=False)
    verification_ownership: list = field(default_factory=list, repr=False, compare=False)
    _paths: tuple = field(init=False, repr=False)
    _manual_paths: tuple = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_manual_paths', tuple(manager.preferences_path for manager in self.manual))
        object.__setattr__(self, '_paths', self._owner_paths())
        self.verify(self.source, (self.export_root, self.host_root))

    def _owner_paths(self):
        return (self.settings.path, self.settings.legacy_path, self.languages.path, self.installation.path,
                *((manager.root, manager.scope) for manager in self.manual), self.automatic.home,
                self.automatic.path, self.accounts.path)

    def groups(self):
        root = self.layout.settings_root
        return (('data', self.layout.data_root),
                *((f'host-settings/{name}', root/name) for name in
                  ('settings.json', 'game-paths.json', 'setup.json', 'languages.json',
                   'languages.requests.json', 'mobile-library.json', 'mobile-library', 'credentials')),
                ('work/voice-assets', self.layout.work_root))

    def verify(self, source, external):
        from .accounts import AccountStore
        from .automatic_mobile_export import AutomaticMobileExports
        from .config import SettingsStore
        from .installation import InstallationService
        from .language_preparation import LanguagePreparation
        from .mobile_export_controls import MobileExportManager
        from .runtime_bundle import RuntimeLayout
        from .storage import TranscriptStore
        from .lexirise import LexiriseService
        from .reading import LexiriseReadingService
        if (source is not self.source or tuple(external) != (self.export_root, self.host_root)
                or type(self.layout) is not RuntimeLayout or self.layout.mode != 'bundle'
                or type(self.settings) is not SettingsStore or type(self.languages) is not LanguagePreparation
                or type(self.installation) is not InstallationService or type(self.automatic) is not AutomaticMobileExports
                or type(self.accounts) is not AccountStore or not self.manual
                or any(type(manager) is not MobileExportManager for manager in self.manual)
                or any(manager.scope is not None and (type(manager.scope) is not tuple
                    or len(manager.scope) != 2 or any(type(part) is not str for part in manager.scope))
                    for manager in self.manual)
                or self._owner_paths() != self._paths):
            raise HostProbeError('invalid-state-binding', 'The actual mapped state owners or paths changed.')
        if type(self.verification_ownership) is not list or self.verification_ownership:
            raise HostProbeError('database-verification-cleanup-unconfirmed',
                                 'Retain the mapped verification owner before another operation.')
        layout = self.layout
        if (self.settings.path != layout.settings_root/'settings.json'
                or self.settings.legacy_path != layout.data_root/'settings.json'
                or self.languages.path != layout.settings_root/'languages.json'
                or self.installation.path != layout.settings_root/'setup.json'
                or self.accounts.path != layout.settings_root/'credentials/accounts.dpapi'
                or self.automatic.path != self.automatic.home/'rules.json'
                or self.settings.path == self.settings.legacy_path
                or self.installation.settings is not self.settings
                or self.installation.root != layout.application_root
                or self.automatic.root != layout.application_root
                or any(manager.root != layout.application_root for manager in self.manual)):
            raise HostProbeError('invalid-state-binding', 'Mapped state differs from its selected service layout.')
        for logical, path in self.groups():
            if path == source.path or not path.is_relative_to(source.path):
                raise HostProbeError('invalid-state-binding', 'Copied roles must remain within the owned source.')
            _state_path(path, missing=True)
        for root in (self.export_root, self.host_root):
            _state_path(root.path, directory=True)
            root.verify()
        for path in (self.export_output, self.export_work, self.automatic.home):
            if path == self.export_root.path or not path.is_relative_to(self.export_root.path):
                raise HostProbeError('unbound-external-root', 'Export and recovery roots must have an explicit external owner.')
            _state_path(path, directory=True)
        _test_credential_family(layout.settings_root)
        if (not self.languages.stop_event.is_set() or any(worker.is_alive() for worker in
                (*self.languages._workers, *self.languages._monitors)) or self.languages._cleanup_failures
                or not self.automatic.stop.is_set() or self.automatic.process is not None
                or self.automatic.thread is not None and self.automatic.thread.is_alive()
                or not self.automatic.picker._quiescing
                or any(not manager._quiescing for manager in self.manual)):
            raise HostProbeError('invalid-state-binding', 'Authored setup producers have not settled.')
        self.automatic.owner.require_released()
        for manager, path in zip(self.manual, self._manual_paths):
            if path != layout.settings_root/'mobile-library.json' and path.parent != layout.settings_root/'mobile-library':
                raise HostProbeError('invalid-state-binding', 'Manual preferences differ from their selected settings role.')
            _state_path(path, directory=False)
            if path.stat().st_size > 1024 * 1024:
                raise HostProbeError('state-inventory-bound', 'Manual preferences exceed the fixture bound.')
            preferences = json.loads(path.read_text(encoding='utf-8'))
            destination = Path(preferences['destination_folder'])
            if destination != self.export_root.path and not destination.is_relative_to(self.export_root.path):
                raise HostProbeError('unbound-external-root', 'A configured manual destination has no explicit owner.')
        if _state_path(self.automatic.path, directory=False).st_size > 1024 * 1024:
            raise HostProbeError('state-inventory-bound', 'Automatic rules exceed the fixture bound.')
        saved = json.loads(self.automatic.path.read_text(encoding='utf-8'))
        if saved != self.automatic.data:
            raise HostProbeError('invalid-state-binding', 'Automatic owner state differs from its persisted rules.')
        for rule in saved['rules'].values():
            destination = Path(rule['destination'])
            if destination != self.export_root.path and not destination.is_relative_to(self.export_root.path):
                raise HostProbeError('unbound-external-root', 'A configured automatic destination has no explicit owner.')
        expected_sql = {(TranscriptStore, layout.data_root/'transcript-v2.db'),
            (TranscriptStore, layout.data_root/'transcript.db'),
            (LexiriseService, layout.data_root/'lexirise/exports-v2.db'),
            (LexiriseReadingService, layout.data_root/'lexirise/reading-cache-v2.db')}
        actual_sql = {(type(owner), owner.db_path if type(owner) is LexiriseService else owner.path)
                      for owner, _ in self.sql_fences}
        if len(self.sql_fences) != 4 or actual_sql != expected_sql:
            raise HostProbeError('invalid-state-binding', 'Setup SQL owners differ from the selected data role.')
        for owner, fence in self.sql_fences:
            fence.check(owner)

    def metadata(self):
        return [{'role': role, 'source_relative': path.relative_to(self.source.path).as_posix()}
                for role, path in self.groups()]


def _mapped_inventory(plan):
    bindings = plan.state_bindings
    bindings.verify(plan.source, plan.external_destinations)
    files, directories, aliases = [], [], {}
    inspected = total = 0
    for logical, root in bindings.groups():
        info = _state_path(root, missing=True)
        if info is None:
            continue
        pending = [(root, logical)]
        while pending:
            path, name = pending.pop()
            info = _state_path(path)
            inspected += 1
            if inspected > 4096 or len(Path(name).parts) > 32:
                raise HostProbeError('state-inventory-bound', 'Mapped state exceeds its reviewed fixture bound.')
            if stat.S_ISDIR(info.st_mode):
                directories.append(name)
                with os.scandir(path) as entries:
                    children = []
                    for entry in entries:
                        if inspected + len(pending) + len(children) >= 4096:
                            raise HostProbeError('state-inventory-bound', 'Mapped state exceeds its reviewed fixture bound.')
                        children.append(entry.name)
                pending.extend((path/child, name+'/'+child) for child in sorted(children, reverse=True))
            else:
                if name == 'data/companion-operation.lock':
                    continue
                total += info.st_size
                if total > 64 * 1024 * 1024:
                    raise HostProbeError('state-inventory-bound', 'Mapped state exceeds its reviewed fixture bound.')
                alias = aliases.setdefault((info.st_dev, info.st_ino), len(aliases)+1)
                files.append({'name': name, 'size': info.st_size, 'sha256': _digest(path), 'alias_group': alias})
    return sorted(files, key=lambda item: item['name']), sorted(set(directories))


def _source_file(plan, name):
    if plan.state_bindings is None:
        return plan.source.path/name
    for logical, path in plan.state_bindings.groups():
        if name == logical:
            return path
        if name.startswith(logical+'/'):
            return path/name[len(logical)+1:]
    raise HostProbeError('invalid-state-binding', 'A copied name has no selected state role.')


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
    if plan.state_bindings is not None:
        return _mapped_inventory(plan)
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


def _verify_mapped_database(path: Path, plan: SyntheticMigrationPlan):
    """One opt-in core verifier owns its actual SQL resources before use.

    No TemporaryDirectory finalizer can remove a database whose close is
    uncertain. Body, cursor-close, connection-close and cleanup errors retain
    separate original references. Every native/Python close is attempted once.
    """
    retained = plan.state_bindings.verification_ownership
    record = {'root': Path(tempfile.mkdtemp(prefix='r19-sqlite-verify-', dir=plan.target.path)),
              'connection': None, 'cursors': [], 'operation_error': None,
              'connection_close_attempted': False, 'connection_close_error': None,
              'connection_closed': False, 'cleanup_attempted': False, 'cleanup_error': None}
    retained.append(record)
    results = []
    try:
        database = record['root']/'store.db'
        _state_path(database, directory=False, missing=True)
        _state_path(path, directory=False)
        shutil.copy2(path, database)
        for suffix in ('-wal', '-shm'):
            sidecar = path.with_name(path.name+suffix)
            if _state_path(sidecar, directory=False, missing=True) is not None:
                destination = database.with_name(database.name+suffix)
                _state_path(destination, directory=False, missing=True)
                _state_path(sidecar, directory=False)
                shutil.copy2(sidecar, destination)
        connection = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
        record['connection'] = connection
        for sql in ('PRAGMA integrity_check', 'PRAGMA user_version'):
            cursor = connection.cursor()
            owned = {'cursor': cursor, 'close_attempted': False, 'close_error': None}
            record['cursors'].append(owned)
            results.append(cursor.execute(sql).fetchall())
    except BaseException as error:
        record['operation_error'] = error
    for owned in reversed(record['cursors']):
        owned['close_attempted'] = True
        try:
            owned['cursor'].close()
        except BaseException as error:
            owned['close_error'] = error
    if record['connection'] is not None:
        record['connection_close_attempted'] = True
        try:
            record['connection'].close()
            record['connection_closed'] = True
        except BaseException as error:
            record['connection_close_error'] = error
    cursor_error = next((owned['close_error'] for owned in record['cursors']
                         if owned['close_error'] is not None), None)
    close_error = record['connection_close_error']
    if close_error is None:
        close_error = cursor_error
    if close_error is not None:
        raise close_error from record['operation_error']
    if record['operation_error'] is not None:
        raise record['operation_error']
    record['cleanup_attempted'] = True
    try:
        shutil.rmtree(record['root'])
    except BaseException as error:
        record['cleanup_error'] = error
        raise
    retained.remove(record)
    return results[0], results[1][0][0]


def _verify_databases(snapshot: Path, plan: SyntheticMigrationPlan, files: list[dict]) -> list[dict]:
    result = []
    for item in files:
        path = snapshot / item['name']
        if plan.state_bindings is not None:
            _state_path(path, directory=False)
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
        if plan.state_bindings is not None:
            integrity, version = _verify_mapped_database(path, plan)
        else:
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
    if plan.state_bindings is not None:
        binding['state_roles'] = plan.state_bindings.metadata()
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
        if plan.state_bindings is not None:
            selected = plan.state_bindings
            manifest['credentials'] = {'protection': 'opaque-test-family-copied-and-legacy-canaries-preserved',
                'decryption': 'not-attempted-by-copy', 'named_profiles': 'unverified-native',
                'copied_test_family': {'role': 'named-profiles', 'relative': 'host-settings/credentials/accounts.dpapi',
                    'action': 'copy-with-selected-settings'},
                'locators': [{'role': role, 'external_fixture_id': selected.host_root.fixture_id,
                    'relative': path.relative_to(selected.host_root.path).as_posix(),
                    'present': _state_path(path, directory=False, missing=True) is not None,
                    'action': 'preserve-host-locator-in-place'} for role, path in (
                        ('legacy-host-named-canary', selected.host_root.path/'Programs/Proxy Transcript/accounts.dpapi'),
                        ('legacy-host-key', selected.host_root.path/'Programs/Proxy Transcript/key.dpapi'))],
                'legacy_data_fallback': 'opaque-bytes-copied-with-data-if-present'}
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
            source = _source_file(plan, item['name'])
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
