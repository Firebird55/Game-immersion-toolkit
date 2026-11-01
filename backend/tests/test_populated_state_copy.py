"""Real authored services/SQLite/export bytes; process signals here are doubles."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import builtins
import os
import sqlite3
import subprocess
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


def test_real_public_mobile_importer_reads_current_previous_and_preserved_chinese(populated):
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
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True, timeout=20)
    rows = json.loads(completed.stdout)
    assert [(row['source'], row['target']) for row in rows] == [('zh-Hans', 'en'), ('en', 'zh-Hans')]
    assert rows[0]['sourceText'] == rows[1]['translation'] == '自制屏幕消息'
    assert rows[0]['translation'] == rows[1]['sourceText'] == 'Authored screen message'
