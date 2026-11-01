"""Real authored services/SQLite/export bytes; process signals here are doubles."""
from contextlib import closing, contextmanager, ExitStack
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import builtins
import os
import sqlite3
import subprocess
import threading
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from backend import bundle_migration as migration
from backend import runtime_data_copy_probe as probe
from backend.bundle_host import HostProbeError, create_synthetic_root
from backend.runtime_bundle import RuntimeLayout


def bytes_in(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*')
            if path.is_file() and path.name not in {'companion-operation.lock', 'migration-runtime.lock'}}


@pytest.fixture
def populated(tmp_path, monkeypatch):
    import httpx
    from backend import lexirise
    def forbidden(*args, **kwargs):
        pytest.fail('Authored fixture must not reach real network or credential protection.')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    source = create_synthetic_root(tmp_path/'source')
    target = create_synthetic_root(tmp_path/'target', installation_id=source.installation_id)
    external = create_synthetic_root(tmp_path/'external', installation_id=source.installation_id)
    host = create_synthetic_root(tmp_path/'host', installation_id=source.installation_id)
    monkeypatch.setenv('LOCALAPPDATA', str(host.path))
    original_mkdir, original_open = Path.mkdir, Path.open
    def owned_mkdir(path, *args, **kwargs):
        assert path.resolve().is_relative_to(tmp_path.resolve()), 'Fixture attempted an unowned directory write.'
        return original_mkdir(path, *args, **kwargs)
    def owned_open(path, mode='r', *args, **kwargs):
        if any(flag in mode for flag in 'wax+'):
            assert path.resolve().is_relative_to(tmp_path.resolve()), 'Fixture attempted an unowned file write.'
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', owned_mkdir)
    monkeypatch.setattr(Path, 'open', owned_open)
    code = Path(__file__).resolve().parents[2]
    catalog = 'public/mobile-capture/games-data.json'
    layout = RuntimeLayout(mode='bundle', application_root=tmp_path/'app', resource_root=code,
        data_root=source.path/'actual-data-v1', settings_root=source.path/'selected-settings',
        cache_root=source.path/'cache-v1', work_root=source.path/'cache-v1/durable-voice-work',
        tool_root=source.path/'tools-v1', state_root=source.path/'host-v1', default_export_root=source.path/'exports',
        resources={catalog: hashlib.sha256((code/catalog).read_bytes()).hexdigest()})
    fixture = probe.PopulatedStateCopy(source, target, layout, external, host).seed()
    calls = []
    class SourceOnlyHost:
        """No HTTP/Windows authority: only the existing adapter's order contract."""
        def __init__(self, layout):
            self.layout, self.registered = layout, {}
            self.tree = object()
            self.closed = self.recovery_required = False
        def start_registered(self, *, detached_console):
            assert detached_console is True
            self.registered = {role: SimpleNamespace(created=True, resumed=False, exited=False, closed=False)
                for role in ('frontend', 'api')}
            calls.append('create-cohort-double')
        def resume_registered(self):
            for child in self.registered.values(): child.resumed = True
        def wait_services(self): calls.append('ready-double')
        def quiesce_registered(self): calls.append('strict-c2-double')
        def close(self):
            for child in self.registered.values(): child.exited = child.closed = True
            self.closed, self.tree = True, None
            calls.append('retained-signals-double')
    monkeypatch.setattr(probe, 'FrozenProbeHost', SourceOnlyHost)
    adapter = probe._FrozenAuthoredDataRuntime(layout, source.installation_id, calls.append)
    coordinator = probe._ProbeCoordinator(source, target, adapter)
    coordinator.__enter__()
    pointer = coordinator.pointer_path.read_bytes()
    adapter.start()
    value = SimpleNamespace(fixture=fixture, coordinator=coordinator, adapter=adapter, calls=calls,
        source=source, target=target, external=external, host=host, layout=layout, pointer=pointer)
    def copy(**kwargs):
        with coordinator.stopped_writers(coordinator.owner) as barrier:
            value.barrier = barrier
            return fixture.copy_and_verify(coordinator, barrier, **kwargs)
    value.copy = copy
    yield value
    # Teardown disposes only these declared source doubles after assertions;
    # never a product recovery path or a native ownership/cleanup claim.
    if coordinator._opened:
        adapter.layout = layout  # Restore only this source double's original fixture layout.
        adapter.poisoned = False
        coordinator.close(coordinator.owner)


def test_complete_actual_role_mapping_readback_and_unchanged_snapshot_external_state(populated, monkeypatch):
    value, fixture = populated, populated.fixture
    before = bytes_in(value.source.path)
    outside = bytes_in(value.external.path), bytes_in(value.host.path)
    from backend import mobile_export_layout
    monkeypatch.setattr(mobile_export_layout, 'work_folder', lambda *_: pytest.fail('Inventory/readback must never prepare work.'))
    plan = fixture.plan()
    first = migration._source_inventory(plan)
    assert first == migration._source_inventory(plan)
    assert before == bytes_in(value.source.path)
    manifest = value.copy()
    assert manifest['state'] == 'verified' and manifest['activation_allowed'] is False
    assert len(manifest['databases']) == 4
    assert fixture.verification_ownership == [] and fixture.failure is None
    assert before == bytes_in(value.source.path)
    assert outside == (bytes_in(value.external.path), bytes_in(value.host.path))
    assert value.coordinator.pointer_path.read_bytes() == value.pointer
    assert value.adapter.generation == 2 and len(value.adapter.cohorts) == 2
    assert fixture.transport.calls.count(('POST', '/v1/vocabulary')) == 1
    assert fixture.transport.calls.count(('POST', '/v1/decks/1901/items')) == 1
    assert {row['slug']: row['proficiency'] for row in fixture.expected['grammar']} == {
        'r19-populated-known': 4, 'r19-populated-learning': 0}
    assert all(row['localOverride'] for row in fixture.expected['grammar'])
    assert fixture.languages.path.with_suffix('.requests.json').is_file()
    assert value.calls.index('strict-c2-double') < value.calls.index('retained-signals-double')
    with pytest.raises(HostProbeError, match='stopped'):
        value.barrier.check(value.source)
    snapshot = value.target.path/'staging'/manifest['migration_id']
    migration._verify_snapshot(snapshot, *first)
    assert (snapshot/'host-settings/settings.json').read_bytes() == fixture.settings.path.read_bytes()
    assert (snapshot/'work/voice-assets/reviewed-authored-work.json').is_file()
    assert not (snapshot/'host-credentials').exists()
    assert manifest['credentials']['locators'][0]['present'] is True
    assert manifest['credentials']['locators'][0]['external_fixture_id'] == value.host.fixture_id


@pytest.mark.parametrize('changed', ['cohort-before-copy', 'fixture-before-copy', 'during-readback', 'after-return'])
def test_exact_validated_layout_is_pinned_through_actual_source_resume(populated, monkeypatch, changed):
    value, fixture = populated, populated.fixture
    foreign = replace(value.layout, data_root=value.source.path/'different-data')
    if changed == 'cohort-before-copy': value.adapter.layout = foreign
    if changed == 'fixture-before-copy': fixture.layout = foreign
    if changed == 'during-readback':
        readback = fixture._readback
        def mutate(snapshot):
            readback(snapshot)
            value.adapter.layout = foreign
        monkeypatch.setattr(fixture, '_readback', mutate)
    with pytest.raises((probe.DataCopyFailure, HostProbeError)):
        if changed == 'after-return':
            with value.coordinator.stopped_writers(value.coordinator.owner) as barrier:
                fixture.copy_and_verify(value.coordinator, barrier)
                # The copy method has already returned. Actual activate/start
                # must still refuse this different layout at context exit.
                value.adapter.layout = foreign
        else:
            value.copy()
    assert value.adapter.poisoned and value.adapter.generation == 1
    assert value.coordinator._recovery_required and value.coordinator._leases_held()
    assert value.calls.count('create-cohort-double') == 1
    assert value.coordinator.pointer_path.read_bytes() == value.pointer
    assert not foreign.data_root.exists()
    with pytest.raises(probe.DataCopyFailure): value.coordinator.close(value.coordinator.owner)


@pytest.mark.parametrize('fault', ['unknown-schema', 'unknown-table', 'changed-source', 'interrupt', 'space', 'semantic', 'cleanup'])
def test_faults_keep_actual_owner_original_failure_source_and_prior_output(populated, monkeypatch, fault):
    value, fixture = populated, populated.fixture
    if fault in {'unknown-schema', 'unknown-table'}:
        path = value.layout.data_root/('unknown.db' if fault == 'unknown-schema' else 'transcript-v2.db')
        with closing(sqlite3.connect(path)) as db:
            with closing(db.cursor()) as statement:
                statement.execute('CREATE TABLE unknown_fixture(value)')
            db.commit()
    before = bytes_in(value.source.path)
    outside = bytes_in(value.external.path), bytes_in(value.host.path)
    leases = value.coordinator._legacy_lease, value.coordinator._target_lease
    error = OSError('authored private failure sentinel')
    original_usage = migration.shutil.disk_usage
    if fault == 'space':
        monkeypatch.setattr(migration.shutil, 'disk_usage', lambda path: SimpleNamespace(free=0)
            if Path(path) == value.target.path else original_usage(path))
    if fault == 'semantic':
        monkeypatch.setattr(fixture, '_readback', lambda *_: (_ for _ in ()).throw(error))
    if fault == 'cleanup':
        original = probe.shutil.rmtree
        def cleanup(path, *args, **kwargs):
            if Path(path).name.startswith('authored-populated-'):
                raise error
            return original(path, *args, **kwargs)
        monkeypatch.setattr(probe.shutil, 'rmtree', cleanup)
    mutated = []
    def checkpoint(phase, name):
        if phase == 'file-copied' and not mutated:
            mutated.append(name)
            if fault == 'interrupt': raise error
            if fault == 'changed-source':
                (value.layout.work_root/'reviewed-authored-work.json').write_bytes(b'authored changed source')
    with pytest.raises((HostProbeError, probe.DataCopyFailure, OSError)):
        value.copy(checkpoint=checkpoint)
    assert fixture.failure is not None and value.adapter.poisoned
    if fault in {'interrupt', 'semantic', 'cleanup'}: assert fixture.failure is error
    assert value.coordinator._leases_held() and value.adapter.generation == 1
    assert leases == (value.coordinator._legacy_lease, value.coordinator._target_lease)
    assert value.coordinator.pointer_path.read_bytes() == value.pointer
    assert outside == (bytes_in(value.external.path), bytes_in(value.host.path))
    if fault == 'changed-source':
        before['cache-v1/durable-voice-work/reviewed-authored-work.json'] = b'authored changed source'
    assert before == bytes_in(value.source.path)
    with pytest.raises(probe.DataCopyFailure): value.coordinator.close(value.coordinator.owner)
    assert value.coordinator._leases_held()
    if fault == 'cleanup':
        assert fixture.verification_ownership and fixture.verification_ownership[0]['owners']


@pytest.mark.parametrize('fault', ['missing-work', 'missing-external', 'owner-path', 'unknown-manual', 'unknown-automatic', 'retired-setup-fence'])
def test_actual_path_bindings_refuse_missing_changed_and_unowned_configured_roots(populated, fault):
    value, fixture = populated, populated.fixture
    if fault == 'missing-work': fixture.export_work.rename(fixture.export_work.with_name('preserved-moved-work'))
    if fault == 'missing-external': value.external.path.rename(value.external.path.with_name('preserved-moved-external'))
    if fault == 'owner-path': fixture.settings.path = fixture.settings.path.with_name('other.json')
    if fault == 'unknown-manual':
        from backend.runtime_probe import authored_populated_layout
        with authored_populated_layout(value.layout, value.host):
            fixture.manual[0]._save_destination(value.target.path/'not-owned-export')
    if fault == 'unknown-automatic':
        data = json.loads(fixture.automatic.path.read_text())
        data['rules']['halflife']['destination'] = str(value.target.path/'unowned')
        fixture.automatic.path.write_text(json.dumps(data))
    if fault == 'retired-setup-fence':
        owner, fence = next((owner, fence) for owner, fence in fixture.bindings.sql_fences if owner is fixture.ledger)
        owner.resume_connections(fence)
    expected_error = ValueError if fault == 'retired-setup-fence' else (HostProbeError, probe.DataCopyFailure)
    with pytest.raises(expected_error):
        value.copy()
    assert value.coordinator._leases_held() and value.adapter.poisoned
    assert value.adapter.generation == 1


@pytest.mark.parametrize('changed', ['source', 'snapshot', 'external', 'pointer', 'barrier'])
def test_final_semantic_boundary_does_not_adopt_new_source_or_authority(populated, monkeypatch, changed):
    value, fixture = populated, populated.fixture
    source_before = bytes_in(value.source.path)
    external_before = bytes_in(value.external.path)
    readback = fixture._readback
    def mutate(snapshot):
        readback(snapshot)
        if changed == 'source':
            (value.layout.work_root/'reviewed-authored-work.json').write_bytes(b'authored source mutation')
        elif changed == 'snapshot':
            (snapshot/'work/voice-assets/reviewed-authored-work.json').write_bytes(b'authored target mutation')
        elif changed == 'external':
            fixture.previous_bundle.write_bytes(b'authored external mutation')
        elif changed == 'pointer':
            value.coordinator.pointer_path.write_bytes(b'authored pointer mutation')
        else:
            value.coordinator._barrier = object()
    monkeypatch.setattr(fixture, '_readback', mutate)
    with pytest.raises((HostProbeError, probe.DataCopyFailure)):
        value.copy()
    assert value.adapter.poisoned and value.adapter.generation == 1 and value.coordinator._leases_held()
    if changed == 'source':
        source_before['cache-v1/durable-voice-work/reviewed-authored-work.json'] = b'authored source mutation'
    if changed == 'external':
        external_before[fixture.previous_bundle.relative_to(value.external.path).as_posix()] = b'authored external mutation'
    assert source_before == bytes_in(value.source.path)
    assert external_before == bytes_in(value.external.path)


def test_linked_mapping_refused_before_descendant_read(populated, monkeypatch):
    value = populated
    selected = value.layout.work_root
    moved = selected.with_name('owned-unmapped-original')
    selected.rename(moved)
    selected.symlink_to(moved, target_is_directory=True)
    original = Path.open
    def guarded(path, *args, **kwargs):
        if path.is_relative_to(selected): pytest.fail('A rejected parent link must precede descendant content reads.')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    with pytest.raises((HostProbeError, probe.DataCopyFailure)):
        value.copy()
    assert value.coordinator._leases_held() and value.adapter.poisoned


def _target_read_spies(monkeypatch, selected, *, descendants=False):
    """Observe actual follow-metadata/open/copy calls, not refusal labels."""
    reads = []
    original_path_open, original_open = Path.open, builtins.open
    original_stat, original_copy = os.stat, migration.shutil.copy2
    def matches(path):
        if not isinstance(path, (str, Path)): return False
        path = Path(path)
        return path == selected or descendants and path.is_relative_to(selected)
    def path_open(path, mode='r', *args, **kwargs):
        if matches(path) and ('r' in mode or '+' in mode): reads.append('path-open')
        return original_path_open(path, mode, *args, **kwargs)
    def opening(path, mode='r', *args, **kwargs):
        if matches(path) and ('r' in mode or '+' in mode): reads.append('open')
        return original_open(path, mode, *args, **kwargs)
    def metadata(path, *args, **kwargs):
        if matches(path) and kwargs.get('follow_symlinks', True): reads.append('follow-stat')
        return original_stat(path, *args, **kwargs)
    def copy(source, destination, *args, **kwargs):
        if matches(source): reads.append('copy2')
        return original_copy(source, destination, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', path_open)
    monkeypatch.setattr(builtins, 'open', opening)
    monkeypatch.setattr(os, 'stat', metadata)
    monkeypatch.setattr(migration.shutil, 'copy2', copy)
    return reads


@pytest.mark.parametrize('boundary', ['header-file', 'header-parent', 'primary-copy',
    'wal-metadata', 'shm-metadata', 'wal-copy', 'shm-copy', 'semantic-clone'])
def test_static_verification_links_refuse_before_real_header_metadata_or_copy_read(populated, monkeypatch, boundary):
    value, fixture = populated, populated.fixture
    plan = fixture.plan()
    snapshot = value.target.path/'staging'/plan.migration_id
    primary = snapshot/'data/transcript-v2.db'
    outside = value.target.path/'authored-unmapped-marker.bin'
    marker = b'Owned malformed boundary marker; no WAL/database/account acceptance.'
    outside.write_bytes(marker)
    reads, injected = [], []
    if boundary.startswith('header-'):
        last = migration._source_inventory(plan)[0][-1]['name']
        def checkpoint(phase, name):
            if phase != 'file-copied' or name != last: return
            if boundary == 'header-parent':
                selected = snapshot/'data'
                moved = value.target.path/'owned-preserved-snapshot-data'
                selected.rename(moved)
                selected.symlink_to(moved, target_is_directory=True)
            else:
                selected = primary
                selected.unlink()
                selected.symlink_to(outside)
            reads.append(_target_read_spies(monkeypatch, selected, descendants=boundary == 'header-parent'))
            injected.append(True)
    elif boundary == 'semantic-clone':
        original = probe.shutil.copytree
        def copytree(source, destination, *args, **kwargs):
            result = original(source, destination, *args, **kwargs)
            if Path(source) == snapshot:
                selected = Path(destination)/'data/transcript-v2.db'
                selected.unlink()
                selected.symlink_to(outside)
                reads.append(_target_read_spies(monkeypatch, selected))
                injected.append(True)
            return result
        monkeypatch.setattr(probe.shutil, 'copytree', copytree)
        checkpoint = None
    else:
        verify = migration._verify_mapped_database
        def substitute(path, current_plan):
            if path == primary:
                if boundary == 'primary-copy':
                    path.unlink()
                    path.symlink_to(outside)
                    reads.append(_target_read_spies(monkeypatch, path))
                    injected.append(True)
                else:
                    suffix = '-wal' if boundary.startswith('wal-') else '-shm'
                    sidecar = path.with_name(path.name+suffix)
                    if boundary.endswith('metadata'):
                        sidecar.symlink_to(outside)
                        reads.append(_target_read_spies(monkeypatch, sidecar))
                        injected.append(True)
                    else:
                        # Malformed authored regular bytes are only a negative
                        # fixture, never fabricated WAL/SHM acceptance evidence.
                        sidecar.write_bytes(marker)
                        guard = migration._state_path
                        def before_copy(candidate, *args, **kwargs):
                            info = guard(candidate, *args, **kwargs)
                            if Path(candidate) == sidecar and not injected:
                                sidecar.unlink()
                                sidecar.symlink_to(outside)
                                reads.append(_target_read_spies(monkeypatch, sidecar))
                                injected.append(True)
                            return info
                        monkeypatch.setattr(migration, '_state_path', before_copy)
            return verify(path, current_plan)
        monkeypatch.setattr(migration, '_verify_mapped_database', substitute)
        checkpoint = None
    with pytest.raises((HostProbeError, probe.DataCopyFailure, sqlite3.DatabaseError)):
        value.copy(checkpoint=checkpoint)
    assert injected == [True] and reads == [[]]
    assert outside.read_bytes() == marker
    assert value.coordinator._leases_held() and value.adapter.poisoned and value.adapter.generation == 1


@pytest.mark.parametrize('bound', ['entries', 'bytes-before-read'])
def test_mapped_inventory_bound_refuses_before_unbounded_enumeration_or_payload_read(populated, monkeypatch, bound):
    value = populated
    inspected = []
    if bound == 'entries':
        original = migration.os.scandir
        class Entries:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self):
                for index in range(5000):
                    inspected.append(index)
                    assert len(inspected) <= 4096, 'The bounded census consumed an unbounded entry stream.'
                    yield SimpleNamespace(name=f'authored-{index}')
        monkeypatch.setattr(migration.os, 'scandir', lambda path: Entries()
            if isinstance(path, (str, Path)) and Path(path) == value.layout.data_root else original(path))
    else:
        large = value.layout.data_root/'z-authored-sparse.bin'
        with large.open('wb') as stream: stream.truncate(65 * 1024 * 1024)
        original = Path.open
        def guarded(path, mode='r', *args, **kwargs):
            if path == large and 'r' in mode: pytest.fail('Payload read must follow the size-bound refusal.')
            return original(path, mode, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', guarded)
    with pytest.raises(HostProbeError) as refused:
        value.copy()
    assert refused.value.code == 'state-inventory-bound'
    assert value.coordinator._leases_held() and value.adapter.poisoned and value.adapter.generation == 1


@pytest.mark.parametrize('phase,fault', [('core', 'before'), ('core', 'after'), ('normal-store-constructor', 'after')])
def test_actual_sqlite_close_failure_keeps_original_object_and_no_retry(populated, monkeypatch, phase, fault):
    value, fixture = populated, populated.fixture
    original = sqlite3.connect
    failed = []
    error = OSError('authored SQLite close uncertainty')
    class CloseFault(sqlite3.Connection):
        closes = 0
        def close(self):
            self.closes += 1
            if fault == 'after': super().close()
            raise error
    def connect(database, *args, **kwargs):
        text = str(database)
        selected = ('r19-sqlite-verify-' in text if phase == 'core' else
            'authored-populated-' in text and '/clone/data/transcript-v2.db' in text.replace('\\', '/'))
        if selected and not failed:
            connection = original(database, *args, factory=CloseFault, **kwargs)
            import weakref
            failed.append(weakref.ref(connection))
            return connection
        return original(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    try:
        with pytest.raises((OSError, probe.TranscriptConnectionCloseError)):
            value.copy()
        assert fixture.failure is not None and failed[0]() is not None
        connection = failed[0]()
        assert connection.closes == 1 and value.coordinator._leases_held() and value.adapter.poisoned
        if phase == 'core':
            assert fixture.failure is error
            record = fixture.verification_ownership[0]
            assert record['connection'] is connection and record['connection_close_error'] is error
            assert record['connection_close_attempted'] and not record['connection_closed']
            assert not record['cleanup_attempted'] and (record['root']/'store.db').is_file()
            assert all(item['close_attempted'] for item in record['cursors'])
            with pytest.raises(HostProbeError):
                fixture.bindings.verify(value.source, (value.external, value.host))
            if fault == 'before':
                with closing(connection.cursor()) as cursor:
                    assert cursor.execute('PRAGMA user_version').fetchone() == (0,)
        else:
            assert fixture.failure.close_error is error and fixture.failure.connection is connection
            assert fixture.verification_ownership[0]['owners'][0] is fixture.failure.store
        with pytest.raises(probe.DataCopyFailure): value.coordinator.close(value.coordinator.owner)
        assert connection.closes == 1
    finally:
        # Deliberate pre-close injection leaves a known owned test connection
        # open. Dispose only that genuine object after all retention assertions;
        # this is not a product retry or raw-handle recovery path.
        if fault == 'before' and failed and failed[0]() is not None:
            sqlite3.Connection.close(failed[0]())


def test_existing_authored_root_is_not_a_seed_overwrite_permission(tmp_path):
    source = create_synthetic_root(tmp_path/'source')
    target = create_synthetic_root(tmp_path/'target', installation_id=source.installation_id)
    export = create_synthetic_root(tmp_path/'external', installation_id=source.installation_id)
    host = create_synthetic_root(tmp_path/'host', installation_id=source.installation_id)
    sentinel = host.path/'opaque-authored-state'
    sentinel.write_bytes(b'preserve this authored prior file')
    layout = RuntimeLayout(mode='bundle', application_root=tmp_path/'app', resource_root=tmp_path/'app/internal',
        data_root=source.path/'data-v1', settings_root=source.path/'settings', cache_root=source.path/'cache',
        work_root=source.path/'cache/work', tool_root=source.path/'tools', state_root=source.path/'state',
        default_export_root=source.path/'exports')
    fixture = probe.PopulatedStateCopy(source, target, layout, export, host)
    before = bytes_in(host.path)
    with pytest.raises(probe.DataCopyFailure): fixture.seed()
    assert before == bytes_in(host.path) and not layout.data_root.exists()


@pytest.mark.parametrize('linked', ['source', 'target', 'export', 'host'])
def test_seed_rechecks_every_raw_root_before_any_listing(tmp_path, monkeypatch, linked):
    source = create_synthetic_root(tmp_path/'source')
    roots = {'source': source, **{name: create_synthetic_root(tmp_path/name,
        installation_id=source.installation_id) for name in ('target', 'export', 'host')}}
    layout = RuntimeLayout(mode='bundle', application_root=tmp_path/'app', resource_root=tmp_path/'app/internal',
        data_root=source.path/'data', settings_root=source.path/'settings', cache_root=source.path/'cache',
        work_root=source.path/'cache/work', tool_root=source.path/'tools', state_root=source.path/'state',
        default_export_root=source.path/'exports')
    fixture = probe.PopulatedStateCopy(source, roots['target'], layout, roots['export'], roots['host'])
    selected = roots[linked].path
    moved = selected.with_name('preserved-owned-root')
    selected.rename(moved)
    before = bytes_in(moved)
    selected.symlink_to(moved, target_is_directory=True)
    original = Path.iterdir
    listed = []
    def listing(path):
        if path in {root.path for root in roots.values()}: listed.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', listing)
    with pytest.raises((probe.DataCopyFailure, HostProbeError)):
        fixture.seed()
    assert listed == [] and before == bytes_in(moved)
    assert fixture.owners == [] and not fixture.seeded


def test_mapped_core_retains_body_cursor_and_connection_errors_as_distinct_actual_owners(populated, monkeypatch):
    value, fixture = populated, populated.fixture
    original = sqlite3.connect
    body_error, cursor_error, close_error = (OSError('authored query failure'),
        OSError('authored cursor close failure'), OSError('authored connection close failure'))
    held = []
    class CursorFault(sqlite3.Cursor):
        closes = 0
        def execute(self, sql, *args): raise body_error
        def close(self):
            self.closes += 1
            super().close()
            raise cursor_error
    class ConnectionFault(sqlite3.Connection):
        closes = 0
        def cursor(self, *args, **kwargs): return super().cursor(*args, factory=CursorFault, **kwargs)
        def close(self):
            self.closes += 1
            super().close()
            raise close_error
    def connect(database, *args, **kwargs):
        if 'r19-sqlite-verify-' in str(database) and not held:
            connection = original(database, *args, factory=ConnectionFault, **kwargs)
            held.append(connection)
            return connection
        return original(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    with pytest.raises(OSError) as refused:
        value.copy()
    record = fixture.verification_ownership[0]
    assert refused.value is fixture.failure is close_error
    assert record['connection'] is held[0] and held[0].closes == 1
    assert record['operation_error'] is body_error and record['connection_close_error'] is close_error
    assert len(record['cursors']) == 1
    assert record['cursors'][0]['close_error'] is cursor_error and record['cursors'][0]['cursor'].closes == 1
    assert not record['cleanup_attempted'] and (record['root']/'store.db').is_file()
    assert value.adapter.poisoned and value.coordinator._leases_held()


def test_mapped_core_cleanup_follows_confirmed_real_closes_and_is_never_retried(populated, monkeypatch):
    value, fixture = populated, populated.fixture
    original = migration.shutil.rmtree
    error, attempts = OSError('authored mapped core cleanup failure'), []
    def cleanup(path, *args, **kwargs):
        if Path(path).name.startswith('r19-sqlite-verify-'):
            record = fixture.verification_ownership[0]
            assert record['connection_closed'] and record['connection_close_attempted']
            with pytest.raises(sqlite3.ProgrammingError): record['connection'].execute('PRAGMA user_version')
            for owned in record['cursors']:
                assert owned['close_attempted'] and owned['close_error'] is None
                with pytest.raises(sqlite3.ProgrammingError): owned['cursor'].execute('PRAGMA user_version')
            attempts.append(path)
            raise error
        return original(path, *args, **kwargs)
    monkeypatch.setattr(migration.shutil, 'rmtree', cleanup)
    with pytest.raises(OSError) as refused: value.copy()
    record = fixture.verification_ownership[0]
    assert refused.value is fixture.failure is record['cleanup_error'] is error
    assert record['cleanup_attempted'] and (record['root']/'store.db').is_file()
    assert len(attempts) == 1
    with pytest.raises(HostProbeError): fixture.bindings.verify(value.source, (value.external, value.host))
    with pytest.raises(probe.DataCopyFailure): value.coordinator.close(value.coordinator.owner)
    assert len(attempts) == 1 and value.coordinator._leases_held()


@pytest.mark.parametrize('method,path,key,body', [
    ('GET', 'https://unowned.invalid/v1/me', 'fixed', None),
    ('GET', 'https://api.lexirise.app/v1/me', 'unowned', None),
    ('GET', 'https://api.lexirise.app/v1/settings?unowned=1', 'fixed', None),
    ('GET', 'https://api.lexirise.app/v1/decks/1901?limit=999', 'fixed', None),
    ('POST', 'https://api.lexirise.app/v1/vocabulary/audio', 'fixed', {}),
    ('POST', 'https://api.lexirise.app/v1/analyze/text', 'fixed', {'text': 'unowned input'}),
])
def test_fixed_mock_transport_has_no_catch_all_account_write_or_foreign_response(method, path, key, body):
    import httpx
    from backend.runtime_probe import AuthoredPopulatedTransport, POPULATED_KEY
    from backend.runtime_bundle import RuntimeBundleError
    policy = AuthoredPopulatedTransport()
    credential = POPULATED_KEY if key == 'fixed' else 'unowned-authored-key'
    with httpx.Client(transport=policy.transport, headers={'Authorization': 'Bearer '+credential}) as client:
        with pytest.raises(RuntimeBundleError) as refused:
            client.request(method, path, json=body)
    assert credential not in str(refused.value) and path not in str(refused.value)
    assert not policy.items and not policy.members


@pytest.mark.parametrize('legacy_default', [False, True], ids=['ordinary-default', 'cp1252-default'])
def test_real_public_mobile_importer_reads_current_previous_and_preserved_chinese(populated, monkeypatch, legacy_default):
    # Buildhost compatibility only. Runtime adapter gains no Node/PATH caller.
    script = r"""
import {readFileSync} from 'node:fs';
import {openLibraryFiles,readCatalog} from './public/mobile-capture/library.mjs';
const result=[];
for(const path of process.argv.slice(1)){
  const blob=new Blob([readFileSync(path)]);
  const opened=await openLibraryFiles([blob]);
  const data=await readCatalog(opened[0]);
  if(opened.length!==1||data.rows.length!==1||data.manifest.packs.length!==0)throw Error('Unexpected authored unvoiced library');
  result.push({source:data.rows[0].sourceLocale,target:data.rows[0].translationLocale,
    chinese:data.rows[0].chinese,sourceText:data.rows[0].sourceText,translation:data.rows[0].translationText});
}
console.log(JSON.stringify(result));
"""
    value = populated
    value.copy()
    command = ['node', '--input-type=module', '-e', script,
        str(value.fixture.current_bundle), str(value.fixture.previous_bundle)]
    defaults = []
    if legacy_default:
        def cp1252_default():
            defaults.append('cp1252')
            return 'cp1252'
        monkeypatch.setattr(subprocess, '_text_encoding', cp1252_default)
        errors = []
        # Windows communicate() decodes in joined reader threads; POSIX reads
        # here. Observe that exact old failure without leaking a thread warning.
        with monkeypatch.context() as legacy:
            legacy.setattr(threading, 'excepthook', lambda info: errors.append(info.exc_value))
            try:
                old = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
                    capture_output=True, text=True, check=True, timeout=20)
            except UnicodeDecodeError as error:
                errors.append(error)
            else:
                assert old.stdout is None
        assert len(errors) == 1 and isinstance(errors[0], UnicodeDecodeError)
        assert errors[0].encoding == 'charmap' and errors[0].object[errors[0].start] == 0x8f
        assert defaults == ['cp1252']
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, encoding='utf-8', errors='strict', check=True, timeout=20)
    assert defaults == (['cp1252'] if legacy_default else [])
    rows = json.loads(completed.stdout)
    assert [(row['source'], row['target']) for row in rows] == [('zh-Hans', 'en'), ('en', 'zh-Hans')]
    assert rows[0]['sourceText'] == rows[1]['translation'] == '自制屏幕消息'
    assert rows[0]['translation'] == rows[1]['sourceText'] == 'Authored screen message'


@pytest.fixture
def native_populated(tmp_path, monkeypatch):
    """Real normal owners/ASGI only; no Windows process or native proof here."""
    import httpx
    from backend import lexirise, runtime_probe
    def forbidden(*_args, **_kwargs):
        pytest.fail('Private populated fixture reached a real network or credential fallback.')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    original_mkdir, original_open = Path.mkdir, Path.open
    def owned_mkdir(path, *args, **kwargs):
        assert path.resolve().is_relative_to(tmp_path.resolve()), 'Native-source fixture attempted an unowned directory write.'
        return original_mkdir(path, *args, **kwargs)
    def owned_open(path, mode='r', *args, **kwargs):
        if any(flag in mode for flag in 'wax+'):
            assert path.resolve().is_relative_to(tmp_path.resolve()), 'Native-source fixture attempted an unowned file write.'
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', owned_mkdir)
    monkeypatch.setattr(Path, 'open', owned_open)
    source = create_synthetic_root(tmp_path/'p2-native/legacy')
    roots = {name:create_synthetic_root(source.path.parent/name, installation_id=source.installation_id)
        for name in ('private-target', 'external-state', 'host-profile')}
    code = Path(__file__).resolve().parents[2]
    catalog = 'public/mobile-capture/games-data.json'
    layout = RuntimeLayout(mode='bundle', profile='runtime-experiment', application_root=tmp_path/'app',
        resource_root=code, source_commit='b'*40, build_id='authored-populated-api-fixture',
        data_root=source.path/'data', settings_root=source.path, cache_root=source.path/'cache-v1',
        work_root=source.path/'cache-v1/work', tool_root=source.path/'tools-v1', state_root=source.path/'probe-state',
        default_export_root=source.path/'exports', resources={catalog:hashlib.sha256((code/catalog).read_bytes()).hexdigest()})
    fixture = probe.PopulatedStateCopy(source, roots['private-target'], layout, roots['external-state'], roots['host-profile']).seed(api_fixture=True)
    monkeypatch.setenv('LOCALAPPDATA', str(roots['host-profile'].path))
    monkeypatch.setenv('PROXY_TRANSCRIPT_STANDBY', '1')
    from backend import language_preparation
    # Exercise its real frozen locator branch; this remains a source ASGI fixture.
    monkeypatch.setattr(language_preparation, 'sys', SimpleNamespace(frozen=True))
    monkeypatch.setattr(language_preparation, 'discover_layout', lambda: layout)
    from backend import api
    monkeypatch.setattr(api, 'RUNTIME_LAYOUT', layout)
    monkeypatch.setattr(api, 'DATA_DIR', layout.data_root)
    monkeypatch.setattr(api, 'PROJECT_ROOT', code)
    async def no_ocr(_self): return None
    monkeypatch.setattr(api.CaptureService, 'warmup', no_ocr)
    monkeypatch.setattr(api.Runtime, 'start_updates', lambda _self: None)
    with runtime_probe.authored_populated_layout(layout, roots['host-profile']):
        yield SimpleNamespace(fixture=fixture, layout=layout, roots=roots, api=api)


def test_fixed_populated_actual_api_reads_same_owners_and_idempotent_saved_line(native_populated):
    from fastapi.testclient import TestClient
    from backend import runtime_probe
    value = native_populated
    with runtime_probe.authored_populated_api(value.layout, value.api) as policy:
        with TestClient(value.api.app, base_url='http://127.0.0.1:8766') as client:
            policy.check_runtime(value.api.runtime)
            state = probe._PopulatedCopyProbe.__new__(probe._PopulatedCopyProbe)
            state.state, state.external = value.fixture, value.roots['external-state']
            state.host_profile = value.roots['host-profile']
            state.external_inventory = tuple(migration._inventory(root.path, skip_marker=True)
                for root in (state.external, state.host_profile))
            def request(path, *, method='GET', body=None, status=200, account=None):
                headers = {'X-Proxy-Transcript':'lexirise'}
                if account is not None: headers['X-Proxy-Transcript-Account'] = account
                response = client.request(method, path, json=body, headers=headers)
                assert response.status_code == status
                return response.json()
            state._http = request  # Only transport: routes/middleware/Runtime/stores are real.
            state._read_api(fresh=False)
            assert state.first_api and policy.ledger.status()['sent']['line:3'] == 1901
            assert not policy.transport.items and not policy.transport.members
            assert policy.account_path.read_bytes() == value.fixture.expected['protected']
            assert value.api.runtime.languages.entries() == value.fixture.languages.entries()


@pytest.fixture
def populated_native_runner(native_populated, monkeypatch):
    """Actual two ASGI lifetimes and C2; process/object/listener signals are doubles."""
    from fastapi.testclient import TestClient
    from backend import runtime_probe, language_preparation
    value = native_populated
    calls = []
    class ASGIHost:
        def __init__(self, layout):
            self.layout, self.registered = layout, {}
            self.closed = self.recovery_required = False
            self.tree, self.stack = object(), None
        def start_registered(self, *, detached_console, populated_probe):
            assert detached_console is populated_probe is True
            self.registered = {role:SimpleNamespace(created=True, resumed=False, exited=False, closed=False)
                for role in ('frontend', 'api')}
            calls.append(('created-source-double', self))
        def resume_registered(self):
            self.stack = ExitStack()
            roots = runtime_probe.populated_roots(self.layout)
            self.stack.enter_context(runtime_probe.authored_populated_layout(self.layout, roots['host-profile']))
            for name, selected in (('RUNTIME_LAYOUT', self.layout), ('DATA_DIR', self.layout.data_root),
                                   ('PROJECT_ROOT', self.layout.application_root)):
                self.stack.enter_context(patch.object(value.api, name, selected))
            self.stack.enter_context(patch.object(language_preparation, 'discover_layout', lambda:self.layout))
            self.policy = self.stack.enter_context(runtime_probe.authored_populated_api(self.layout, value.api))
            self.client = self.stack.enter_context(TestClient(value.api.app, base_url='http://127.0.0.1:8766'))
            for child in self.registered.values(): child.resumed = True
        def wait_services(self):
            assert self.client.get('/api/health').json() == {'status':'ok'}
            assert self.client.get('/api/runtime/ready').json()['ready'] is True
        @contextmanager
        def _registered_listener_scope(self):
            calls.append(('listener-double-before', self))
            yield True
            calls.append(('listener-double-after', self))
        def quiesce_registered(self):
            response = self.client.post('/api/runtime/quiesce?writers=true', headers={'X-Proxy-Transcript':'update'})
            assert response.status_code == 200 and response.json()['running'] is False
            assert self.client.get('/api/status').status_code == 503
            assert self.client.get('/api/health').json() == {'status':'ok'}
            calls.append(('actual-c2-asgi', self))
        def close(self):
            if self.stack is not None:
                self.stack.close()
            for child in self.registered.values(): child.exited = child.closed = True
            self.tree, self.closed = None, True
            calls.append(('signaled-source-double', self))
    monkeypatch.setattr(probe, 'FrozenProbeHost', ASGIHost)
    outer = replace(value.layout, work_root=value.layout.cache_root/'native-controller-work')
    stream = io.StringIO(''.join('observed '+phase+'\n' for phase in probe.POPULATED_PHASES[:-1]))
    current = probe._PopulatedCopyProbe(outer, stream)
    def response(request, timeout):
        assert timeout == 5
        host = current.adapter.host
        result = host.client.request(request.get_method(), request.full_url,
            headers=dict(request.header_items()), content=request.data)
        data = result.content
        if result.status_code >= 400:
            raise probe.HTTPError(request.full_url, result.status_code, 'Authored ASGI status', {}, io.BytesIO(data))
        return Response(result.status_code, data)
    class Response:
        def __init__(self, status, data): self.code, self.data = status, data
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, limit): return self.data[:limit]
    monkeypatch.setattr(probe, 'urlopen', response)
    class Held(RuntimeError): pass
    def held(): raise Held('Authored source hold sentinel')
    monkeypatch.setattr(probe, 'hold_keeper_recovery', held)
    yield SimpleNamespace(probe=current, calls=calls, held=Held, host_type=ASGIHost)
    if current.coordinator is not None and not current.released:
        # Test-only cleanup for known ASGI doubles, never a recovery implementation.
        for host in current.adapter.cohorts:
            if not host.closed: host.close()
        current.adapter.poisoned = current.adapter.active = False
        current.coordinator._recovery_required = False
        current.adapter.stop = lambda: probe.STOPPED
        current.coordinator.close(current.coordinator.owner)


def test_fixed_populated_full_asgi_c2_copy_and_fresh_source_readback(populated_native_runner, capsys):
    value = populated_native_runner.probe
    assert value.run() == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    keys = set('schema kind case scope phase status failure source_commit build_id generation writers_created '
        'writers_resumed writers_signaled strict_drains owner_interval fixture_seed api_readback copy_verification '
        'service_readback source_bytes snapshot_bytes source_logical external_state pointer old_barrier_refused '
        'setup_sql_fences api_external_side_effects sqlite native_owned_process_tree writer_console_mode authority '
        'credentials wal_claim browser keeper_loss dynamic_writer_admission warm_routing physical_replace windows11 '
        'rights_review production_activation target_activation installer r19_complete'.split())
    assert len(keys) == 44 and all(set(event) == keys for event in events)
    assert [event['phase'] for event in events] == list(probe.POPULATED_PHASES)
    assert [(event['generation'], event['writers_signaled'], event['strict_drains']) for event in events] == [
        (0,0,0), (0,0,0), (1,0,0), (1,0,1), (1,2,1), (1,2,1), (1,2,1), (2,2,1), (2,2,2), (2,4,2), (2,4,2)]
    assert all(event['r19_complete'] is False and event['production_activation'] is False for event in events)
    assert all(event['source_commit'] == 'b'*40 for event in events)
    assert [event['owner_interval'] for event in events] == ['not-entered']+['leases-held']*9+['leases-released']
    assert events[-1]['api_readback'] == 'both-cohorts-passed' and events[-1]['service_readback'] == 'passed'
    serialized = json.dumps(events, ensure_ascii=False)
    assert all(secret not in serialized for secret in (str(value.source.path), value.source.fixture_id,
        value.host_profile.fixture_id, 'lx_r19_authored_profile_one_only', probe.GRAMMAR_TEXT))
    assert value.copy_verified and value.second_api and value.old_barrier_refused and value.released
    assert value.coordinator.pointer_path.read_bytes() == value.pointer
    assert value.state.manifest['activation_allowed'] is False
    assert len(value.state.manifest['databases']) == 4 and not value.state.verification_ownership
    assert value.state.expected['ledger']['sent']['line:3'] == 1901
    assert len(value.adapter.cohorts) == 2
    for host in value.adapter.cohorts:
        assert not host.policy.transport.items and not host.policy.transport.members


@pytest.mark.parametrize('phase', ['strict-drain-complete', 'writers-signaled'])
@pytest.mark.parametrize('field', ['owner', 'current', 'owned', 'generation', 'barrier', 'lease', 'layout'])
def test_populated_both_drain_acks_recheck_actual_owner_frame_before_copy(populated_native_runner, phase, field):
    fixture, value = populated_native_runner, populated_native_runner.probe
    original = value.observe
    saved = {}
    def observe(stage):
        original(stage)
        if stage != phase: return
        coord, adapter = value.coordinator, value.adapter
        saved.update(owner=coord._owner, current=coord.current, owned=list(coord._owned),
            generation=adapter.generation, barrier=coord._barrier, lease=coord._legacy_lease, layout=adapter.layout)
        if field == 'owner': coord._owner = object()
        elif field == 'current': coord.current = probe._FrozenAuthoredDataRuntime(value.inner, value.source.installation_id, lambda _:None)
        elif field == 'owned': coord._owned.append(adapter)
        elif field == 'generation': adapter.generation += 1
        elif field == 'barrier': coord._barrier = object()
        elif field == 'lease': coord._legacy_lease = SimpleNamespace(held=True)
        else: adapter.layout = replace(value.inner, data_root=value.inner.settings_root/'foreign-data')
    value.observe = observe
    try:
        with pytest.raises(fixture.held): value.run()
        assert value.adapter.poisoned and value.coordinator._recovery_required and not value.released
        assert saved['lease'].held and value.coordinator._target_lease.held
        assert len(value.adapter.cohorts) == 1 and value.state.manifest is None
    finally:
        if saved:
            coord, adapter = value.coordinator, value.adapter
            coord._owner, coord.current, coord._owned = saved['owner'], saved['current'], saved['owned']
            coord._barrier, coord._legacy_lease = saved['barrier'], saved['lease']
            adapter.generation, adapter.layout = saved['generation'], saved['layout']


@pytest.mark.parametrize('phase', ['strict-drain-complete', 'writers-signaled'])
def test_populated_checks_barrier_none_before_each_drain_event_not_just_after_ack(populated_native_runner, monkeypatch, capsys, phase):
    fixture, value = populated_native_runner, populated_native_runner.probe
    method = 'quiesce_registered' if phase == 'strict-drain-complete' else 'close'
    original = getattr(fixture.host_type, method)
    def finish(host):
        original(host)
        if value.adapter.generation == 1:
            value.coordinator._barrier = object()
    monkeypatch.setattr(fixture.host_type, method, finish)
    with pytest.raises(fixture.held): value.run()
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert phase not in [event['phase'] for event in events]
    assert events[-1]['phase'] == 'recovery-required'
    assert value.adapter.poisoned and value.coordinator._leases_held() and not value.released
    assert value.state.manifest is None


@pytest.mark.parametrize('stage', ['api-populated-checked', 'copy-progress', 'copy-verified'])
def test_populated_source_mutation_after_ack_holds_leases_and_never_admits_fresh_source(populated_native_runner, stage):
    fixture, value = populated_native_runner, populated_native_runner.probe
    original = value.observe
    def observe(phase):
        original(phase)
        if phase == stage:
            (value.inner.data_root/'authored-payload.bin').write_bytes(b'authored unexpected source replacement')
    value.observe = observe
    with pytest.raises(fixture.held): value.run()
    assert value.adapter.poisoned and value.coordinator._leases_held() and value.coordinator._recovery_required
    assert len(value.adapter.cohorts) == 1 and not value.released


def test_populated_snapshot_is_rechecked_after_fresh_source_without_freezing_live_source_sql(populated_native_runner):
    fixture, value = populated_native_runner, populated_native_runner.probe
    original = value.observe
    def observe(phase):
        original(phase)
        if phase == 'source-resumed':
            (value.snapshot/'data/authored-payload.bin').write_bytes(b'authored snapshot mutation')
    value.observe = observe
    with pytest.raises(fixture.held): value.run()
    assert value.adapter.poisoned and value.coordinator._leases_held() and not value.released
    assert len(value.adapter.cohorts) == 2 and value.second_api


@pytest.mark.parametrize('fault', ['emit-fails', 'bad-ack'])
def test_populated_control_failure_before_owner_has_no_lease_or_copy_claim_and_retains_live_holder(populated_native_runner, monkeypatch, capsys, fault):
    fixture, value = populated_native_runner, populated_native_runner.probe
    if fault == 'emit-fails':
        monkeypatch.setattr(value, 'emit', lambda *_args, **_kwargs: (_ for _ in ()).throw(BrokenPipeError('authored closed control')))
    else:
        import queue
        value.commands = queue.Queue(maxsize=1)
        value.commands.put('unexpected authored ACK\n')
    with pytest.raises(fixture.held): value.run()
    assert value.state is not None and value.state.seeded and value.failure is not None
    assert value.coordinator is None and value.adapter is None and not value.entered and not value.released
    if fault == 'bad-ack':
        event = json.loads(capsys.readouterr().out.splitlines()[-1])
        assert event['status'] == 'failed' and event['owner_interval'] == 'not-entered'
        assert event['copy_verification'] == 'not-run' and event['writers_created'] == 0


@pytest.mark.parametrize('selection', ['account-arguments', 'ledger-before-account', 'wrong-account', 'automatic-root', 'duplicate-account'])
def test_populated_strict_factories_reject_conflicting_or_repeated_normal_owner_inputs(native_populated, selection):
    from backend import runtime_probe
    from backend.runtime_bundle import RuntimeBundleError
    value = native_populated
    policy = runtime_probe._AuthoredPopulatedAPI(value.layout, value.api)
    with pytest.raises(RuntimeBundleError):
        if selection == 'account-arguments': policy.accounts(path=policy.account_path)
        elif selection == 'ledger-before-account': policy.lexirise(value.layout.data_root/'lexirise', accounts=None)
        elif selection == 'wrong-account':
            policy.accounts(); policy.lexirise(value.layout.data_root/'lexirise', accounts=object())
        elif selection == 'automatic-root': policy.automatic_exports(value.layout.application_root/'foreign', install_lookup=None)
        else: policy.accounts(); policy.accounts()
    assert not policy.transport.calls


@pytest.mark.parametrize('fault', ['wrong-prefix', 'extra-field', 'other-key'])
def test_populated_account_codec_refuses_every_other_envelope_before_normal_constructor(native_populated, fault):
    from backend import runtime_probe
    from backend.runtime_bundle import RuntimeBundleError
    value = native_populated
    path = value.fixture.accounts.path
    payload = json.loads(runtime_probe.authored_test_protect(path.read_bytes(), decrypt=True))
    if fault == 'wrong-prefix':
        path.write_bytes(b'not-an-authored-TEST-envelope')
    else:
        if fault == 'extra-field': payload['unowned'] = True
        else: payload['profiles'][next(key for key in payload['profiles'] if key != payload['active'])]['key'] = 'not-an-approved-fake-key'
        path.write_bytes(runtime_probe.authored_test_protect(json.dumps(payload).encode()))
    with pytest.raises((RuntimeBundleError, ValueError)):
        runtime_probe._AuthoredPopulatedAPI(value.layout, value.api)


def test_populated_factory_retains_actual_partial_sql_owner_and_original_preclose_failure(native_populated, monkeypatch):
    from backend import runtime_probe
    from backend.lexirise import LexiriseConnectionCloseError
    value = native_populated
    policy = runtime_probe._AuthoredPopulatedAPI(value.layout, value.api)
    account = policy.accounts()
    original = sqlite3.connect
    close_error = OSError('Authored actual constructor connection close failure')
    class FailedClose(sqlite3.Connection):
        def close(self):
            self.calls = getattr(self, 'calls', 0)+1
            raise close_error
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs:original(*args, factory=FailedClose, **kwargs))
    with pytest.raises(LexiriseConnectionCloseError) as refused:
        policy.lexirise(value.layout.data_root/'lexirise', accounts=account)
    error = refused.value
    assert policy.failure is error and policy.owners[-1] is error.service
    assert error.close_error is close_error and error.connection.calls == 1
    assert error.connection.execute('PRAGMA user_version').fetchone()[0] == 0
    from backend.runtime_bundle import RuntimeBundleError
    for _ in range(2):
        with pytest.raises(RuntimeBundleError): policy.lexirise(value.layout.data_root/'lexirise', accounts=account)
        assert policy.failure is error and error.connection.calls == 1 and policy.owners[-1] is error.service
    # Explicit disposal of this source-test connection; the product factory
    # never retries the failed close or drops its partial-owner/error record.
    sqlite3.Connection.close(error.connection)
