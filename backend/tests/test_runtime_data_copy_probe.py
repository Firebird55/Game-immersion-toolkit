"""Authored SQLite/ordering fixtures. Frozen Win32 process proof is separate."""
from contextlib import closing, contextmanager
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from backend import runtime_data_copy_probe as probe
from backend.bundle_host import HostProbeError
from backend.lexirise import LexiriseService
from backend.reading import LexiriseReadingService
from backend.runtime_bundle import RuntimeLayout


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    app, private = tmp_path/'app', tmp_path/'private'
    app.mkdir(); (app/'ProxyTranscriptRuntime.exe').write_bytes(b'authored-placeholder-not-a-native-image')
    layout = RuntimeLayout(mode='bundle', profile='runtime-experiment', application_root=app,
        resource_root=app/'_internal', executable=app/'ProxyTranscriptRuntime.exe', settings_root=private,
        data_root=private/'data-v1', cache_root=private/'cache-v1', work_root=private/'cache-v1/work',
        tool_root=private/'tools-v1', state_root=private/'host-v1', default_export_root=private/'exports',
        source_commit='a'*40, build_id='authored-data-copy-fixture', children=('frontend',))
    monkeypatch.setattr(probe.tempfile, 'gettempdir', lambda: str(tmp_path))
    calls = []
    class FakeHost:
        """Local behavior double; it does not establish Win32 ownership or C2."""
        def __init__(self, layout):
            self.layout = layout
            self.registered = {}
            self.closed = self.recovery_required = False
            self.tree = object()
        def start_registered(self, *, detached_console):
            assert detached_console is True
            calls.append(('create', self))
            self.registered = {role: SimpleNamespace(created=True, resumed=False, exited=False, closed=False)
                               for role in ('frontend', 'api')}
            self.exports = LexiriseService(self.layout.data_root/'lexirise')
            self.reading = LexiriseReadingService(self.layout.data_root/'lexirise', self.exports)
        def resume_registered(self):
            calls.append(('resume', self))
            for child in self.registered.values(): child.resumed = True
        def wait_services(self): calls.append(('ready', self))
        @contextmanager
        def _registered_listener_scope(self):
            calls.append(('identity-before', self))
            yield True
            calls.append(('identity-after', self))
        def quiesce_registered(self):
            calls.append(('strict-c2-double', self))
            self.reading.quiesce(1)
        def close(self):
            calls.append(('retained-signal-double', self))
            for child in self.registered.values(): child.exited = child.closed = True
            self.closed, self.tree = True, None
    monkeypatch.setattr(probe, 'FrozenProbeHost', FakeHost)
    instances = []
    def make(case=probe.CASE):
        phases = probe.RESUME_PHASES if case == probe.RESUME_CASE else probe.PHASES
        stream = io.StringIO(''.join('observed '+phase+'\n' for phase in phases[:-1]))
        value = probe._DataCopyProbe(layout, stream, case=case)
        instances.append(value)
        return value
    def response(request, timeout):
        # Use actual store mutation/row parsing, but this is an HTTP double.
        value = instances[-1]
        connections = []
        try:
            store = probe._SetupStore(value.adapter.layout.data_root/'transcript-v2.db', connections)
            if isinstance(request, probe.Request):
                assert request.get_method() == 'PATCH' and request.data == b'{"favorite":true}'
                assert request.full_url.endswith('/1/favorite')
                result = store.set_favorite(1, True).model_dump(mode='json')
                calls.append(('favorite-sql', value.adapter.host))
            else:
                assert request == 'http://127.0.0.1:8766/api/lines?game=hito'
                result = [row.model_dump(mode='json') for row in store.list()]
            data = json.dumps(result).encode()
        finally:
            for connection in connections: connection.close()
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, limit): return data[:limit]
        return Response()
    monkeypatch.setattr(probe, 'urlopen', response)
    yield SimpleNamespace(make=make, calls=calls, layout=layout, hosts=FakeHost)
    # All children here are explicit local doubles. Only test teardown may
    # replace stop to dispose its own fixture leases after asserting retention.
    for value in instances:
        if value.coordinator and value.coordinator._opened:
            monkeypatch.setattr(value.adapter, 'stop', lambda: probe.STOPPED)
            value.adapter.active = value.adapter.setup_open = value.adapter.poisoned = False
            value.coordinator.close(value.coordinator.owner)


def test_actual_sql_copy_and_chinese_context_with_fresh_cohort_order(fixture, capsys):
    value = fixture.make()
    assert value.run() == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert tuple(event['phase'] for event in events) == probe.PHASES
    assert events[-1]['generation'] == 2 and events[-1]['writers_signaled'] == 4
    assert events[-1]['old_barrier_refused'] is True
    assert events[-1]['source_bytes'] == 'preserved-before-resume'
    assert events[-1]['source_logical'] == 'passed'
    assert value.adapter.cohorts[0] is not value.adapter.cohorts[1]
    assert value.coordinator.pointer_path.read_bytes() == value.pointer
    assert not value.coordinator._leases_held() and value.released
    calls = [name for name, _host in fixture.calls]
    assert calls.index('favorite-sql') < calls.index('strict-c2-double') < calls.index('retained-signal-double')
    assert calls.count('create') == calls.count('resume') == calls.count('retained-signal-double') == 2
    # Metadata does not disclose authored rows, transient roots, UUIDs or PIDs.
    serialized = json.dumps(events, ensure_ascii=False)
    assert '这是' not in serialized and str(value.source.path) not in serialized
    assert value.source.fixture_id not in serialized and 'job_members' not in serialized
    assert all(event['r19_complete'] is False and event['target_activation'] is False for event in events)
    assert all(event['schema'] == probe.SCHEMA and event['case'] == probe.CASE for event in events)
    assert not ({'scope', 'copy_attempts', 'authored_interruptions', 'partial_revalidations'} & set(events[-1]))


def test_interrupted_copy_resumes_same_live_plan_barrier_generation_and_leases(fixture, monkeypatch, capsys):
    value = fixture.make(probe.RESUME_CASE)
    original = probe.migration.copy_and_verify_synthetic
    attempts = []
    closes = []
    prepare = value.prepare
    def prepared():
        prepare()
        for name in ('_legacy_lease', '_target_lease'):
            lease = getattr(value.coordinator, name)
            close = lease.close
            def watched(close=close, name=name):
                closes.append(name)
                return close()
            monkeypatch.setattr(lease, 'close', watched)
    monkeypatch.setattr(value, 'prepare', prepared)
    def copy(plan, barrier, **options):
        barrier.check(value.source)
        attempts.append((plan, barrier, value.adapter.generation, value.coordinator._legacy_lease,
                         value.coordinator._target_lease, len(value.adapter.cohorts)))
        assert value.coordinator._leases_held() and not value.adapter.capture_running()
        assert not closes
        if len(attempts) == 2:
            manifest = json.loads((value.target.path/'migrations'/plan.migration_id/'manifest.json').read_text())
            assert manifest['state'] == 'failed' and len(manifest['completed_files']) == 1
            assert manifest['failure'] == probe._AuthoredCopyInterruption.__name__
            assert manifest['activation_allowed'] is False
        return original(plan, barrier, **options)
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', copy)
    assert value.run() == 0
    assert len(attempts) == 2 and attempts[0] == attempts[1] and attempts[0][2] == attempts[0][5] == 1
    assert all(attempts[0][index] is attempts[1][index] for index in (0, 1, 3, 4))
    assert closes == ['_target_lease', '_legacy_lease']
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert tuple(event['phase'] for event in events) == probe.RESUME_PHASES
    partial = next(event for event in events if event['phase'] == 'copy-interrupted')
    assert partial['generation'] == 1 and partial['writers_signaled'] == 2
    assert partial['copy_attempts'] == partial['authored_interruptions'] == partial['partial_revalidations'] == 1
    assert partial['same_plan_barrier_generation'] is True and partial['copy_resumed'] is False
    final = events[-1]
    assert final['schema'] == probe.RESUME_SCHEMA and final['scope'] == probe.RESUME_SCOPE
    assert final['copy_attempts'] == final['partial_revalidations'] == 2 and final['authored_interruptions'] == 1
    assert final['copy_resumed'] is True and final['old_barrier_refused'] is True
    assert final['generation'] == 2 and final['writers_signaled'] == 4 and value.released


@pytest.mark.parametrize('wrong', ['different-instance', 'unrelated-error', 'missing-callback'])
def test_only_the_exact_intended_interruption_instance_can_authorize_resume(fixture, monkeypatch, capsys, wrong):
    value = fixture.make(probe.RESUME_CASE)
    original = probe.migration.copy_and_verify_synthetic
    attempts = []
    def wrong_sentinel(plan, barrier, **options):
        attempts.append(True)
        if wrong == 'missing-callback':
            return original(plan, barrier)
        try:
            return original(plan, barrier, **options)
        except probe._AuthoredCopyInterruption:
            if wrong == 'unrelated-error':
                raise OSError('authored different copy failure') from None
            raise probe._AuthoredCopyInterruption() from None
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', wrong_sentinel)
    assert value.run() == 2 and attempts == [True]
    assert value.adapter.generation == 1 and not value.copy_resumed and value.authored_interruptions == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['status'] == 'failed'


@pytest.mark.parametrize('mutation', ['source', 'completed-bytes', 'binding', 'generation', 'roots'])
def test_interruption_checkpoint_mutation_refuses_resume_without_changing_core_repair_semantics(fixture, monkeypatch, mutation):
    value = fixture.make(probe.RESUME_CASE)
    observe = value.observe
    copied = probe.migration.copy_and_verify_synthetic
    attempts = []
    def copy(*args, **options):
        attempts.append(True)
        return copied(*args, **options)
    def checkpoint(phase):
        observe(phase)
        if phase != 'copy-interrupted': return
        manifest_path = next((value.target.path/'migrations').glob('*/manifest.json'))
        manifest = json.loads(manifest_path.read_text())
        if mutation == 'source':
            (value.source.path/'data/authored-payload.bin').write_bytes(b'authored source changed')
        elif mutation == 'completed-bytes':
            (value.target.path/'staging'/manifest['migration_id']/manifest['completed_files'][0]).write_bytes(b'authored target changed')
        elif mutation == 'binding':
            manifest['binding']['database_versions']['data/transcript-v2.db'] = 1
            manifest_path.write_text(json.dumps(manifest))
        elif mutation == 'roots':
            manifest['roots'] = {'source': 'untrusted-manifest-source', 'target': 'untrusted-manifest-target'}
            manifest_path.write_text(json.dumps(manifest))
        else:
            value.adapter.generation += 1
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', copy)
    monkeypatch.setattr(value, 'observe', checkpoint)
    # The adapter stores its phase callback at construction during prepare.
    if mutation in {'source', 'generation'}:
        def hold():
            assert value.coordinator._leases_held() and value.adapter.poisoned
            raise HeldRecovery()
        monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
        with pytest.raises(HeldRecovery): value.run()
        assert not value.released
    else:
        assert value.run() == 2 and value.released
    assert attempts == [True] and not value.copy_resumed and not value.adapter.active


def test_resume_case_unconfirmed_fresh_cohort_and_broken_failure_output_keep_live_hold(fixture, monkeypatch):
    value = fixture.make(probe.RESUME_CASE)
    start = fixture.hosts.start_registered
    def partial(host, **options):
        if len(value.adapter.cohorts) == 2:
            raise OSError('authored unconfirmed second-cohort startup')
        return start(host, **options)
    monkeypatch.setattr(fixture.hosts, 'start_registered', partial)
    emit = value.emit
    def broken(phase, **options):
        if phase == 'recovery-required': raise BrokenPipeError('authored failed failure event')
        return emit(phase, **options)
    monkeypatch.setattr(value, 'emit', broken)
    def hold():
        assert value.coordinator._leases_held() and value.adapter.poisoned
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    with pytest.raises(HeldRecovery): value.run()
    assert value.copy_resumed and value.adapter.generation == 2 and not value.released


@pytest.mark.parametrize('fault', ['source-after-precheck', 'source-during-resume', 'source-during-first-copy',
    'barrier-lost', 'source-read-failure', 'owner-changed'])
def test_copy_failure_rechecks_real_source_authority_after_prechecks_and_during_helper(fixture, monkeypatch, fault):
    value = fixture.make(probe.RESUME_CASE)
    original = probe.migration.copy_and_verify_synthetic
    attempts = []
    def copy(plan, barrier, **options):
        attempts.append(True)
        number = len(attempts)
        if number == 2 and fault == 'source-after-precheck':
            (value.source.path/'data/authored-payload.bin').write_bytes(b'authored post-precheck mutation')
        if number == 2 and fault == 'barrier-lost': barrier.invalidate()
        if number == 2 and fault == 'owner-changed':
            value.coordinator.current = SimpleNamespace(runtime_id='authored-unconfirmed-owner')
        if number == 2 and fault == 'source-read-failure':
            def unreadable(*_args): raise OSError('authored source inventory unavailable')
            monkeypatch.setattr(probe.migration, '_source_inventory', unreadable)
        if ((number == 2 and fault == 'source-during-resume')
                or (number == 1 and fault == 'source-during-first-copy')):
            previous = options.get('checkpoint')
            def checkpoint(stage, name):
                if stage == 'file-copied':
                    (value.source.path/'data/authored-payload.bin').write_bytes(b'authored mutation during helper')
                if previous: previous(stage, name)
            options['checkpoint'] = checkpoint
        return original(plan, barrier, **options)
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', copy)
    def hold():
        assert value.adapter.poisoned and value.coordinator._leases_held() and not value.released
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    with pytest.raises(HeldRecovery): value.run()
    assert len(attempts) == (1 if fault == 'source-during-first-copy' else 2)


@pytest.mark.parametrize('changed', ['source', 'target-binding'])
def test_identical_core_binding_error_is_classified_by_actual_source_not_error_label(fixture, monkeypatch, changed):
    value = fixture.make(probe.RESUME_CASE)
    original = probe.migration.copy_and_verify_synthetic
    attempts, codes = [], []
    def copy(plan, barrier, **options):
        attempts.append(True)
        if len(attempts) == 2:
            if changed == 'source':
                (value.source.path/'data/authored-payload.bin').write_bytes(b'authored source differs')
            else:
                path = value.target.path/'migrations'/plan.migration_id/'manifest.json'
                manifest = json.loads(path.read_text())
                manifest['binding']['named_account_store'] = 'unreadable'
                path.write_text(json.dumps(manifest))
        try:
            return original(plan, barrier, **options)
        except HostProbeError as error:
            codes.append(error.code)
            raise
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', copy)
    if changed == 'source':
        emit = value.emit
        def broken(phase, **options):
            if phase == 'recovery-required': raise BrokenPipeError('authored failed failure output')
            return emit(phase, **options)
        monkeypatch.setattr(value, 'emit', broken)
        def hold():
            assert value.adapter.poisoned and value.coordinator._leases_held() and not value.released
            raise HeldRecovery()
        monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
        with pytest.raises(HeldRecovery): value.run()
    else:
        assert value.run() == 2 and value.released and not value.adapter.poisoned
    assert codes == ['source-or-plan-changed'] and len(attempts) == 2 and not value.copy_resumed


@pytest.mark.parametrize('where', ['manifest', 'staging'])
@pytest.mark.parametrize('kind', ['parent-link', 'windows-reparse'])
def test_partial_static_parent_links_refuse_before_outside_descendant_metadata(fixture, monkeypatch, where, kind):
    value = fixture.make(probe.RESUME_CASE)
    observe = value.observe
    original_lstat, original_stat, original_open = Path.lstat, Path.stat, Path.open
    touched, restored = [], []
    def checkpoint(phase):
        observe(phase)
        if phase != 'copy-interrupted': return
        manifest = next((value.target.path/'migrations').glob('*/manifest.json'))
        migration_id = manifest.parent.name
        link = manifest.parent if where == 'manifest' else value.target.path/'staging'/migration_id/'data'
        outside = value.fixture/('authored-outside-'+where)
        if kind == 'parent-link':
            link.rename(outside)
            link.symlink_to(outside, target_is_directory=True)
            restored.append((link, outside))
        def lstat(path, *args, **options):
            if link in path.parents:
                touched.append('lstat');raise AssertionError('Outside descendant metadata is forbidden.')
            info = original_lstat(path, *args, **options)
            if kind == 'windows-reparse' and path == link:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        def stat(path, *args, **options):
            if link in path.parents:
                touched.append('stat');raise AssertionError('Outside descendant metadata is forbidden.')
            return original_stat(path, *args, **options)
        def open_file(path, *args, **options):
            if link in path.parents or path == outside or outside in path.parents:
                touched.append('open');raise AssertionError('Outside content is forbidden.')
            return original_open(path, *args, **options)
        monkeypatch.setattr(Path, 'lstat', lstat)
        monkeypatch.setattr(Path, 'stat', stat)
        monkeypatch.setattr(Path, 'open', open_file)
    monkeypatch.setattr(value, 'observe', checkpoint)
    try:
        assert value.run() == 2 and not value.copy_resumed and value.released
        assert not touched and not value.adapter.poisoned
    finally:
        monkeypatch.setattr(Path, 'lstat', original_lstat)
        monkeypatch.setattr(Path, 'stat', original_stat)
        monkeypatch.setattr(Path, 'open', original_open)
        for link, outside in restored:
            link.unlink();outside.rename(link)


@pytest.mark.parametrize('which', ['source', 'target'])
@pytest.mark.parametrize('kind', ['parent-link', 'windows-reparse'])
def test_authority_root_link_is_guarded_before_barrier_marker_and_failure_journal_reads(fixture, monkeypatch, which, kind):
    value = fixture.make(probe.RESUME_CASE)
    observe = value.observe
    originals = {'lstat': Path.lstat, 'stat': Path.stat, 'open': Path.open}
    copied = probe.migration.copy_and_verify_synthetic
    touched, restored, plans, leases, denials, installed, held = [], [], [], [], [], [], []
    def copy(plan, barrier, **options):
        plans.append(plan)
        return copied(plan, barrier, **options)
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', copy)
    def root_state():
        return tuple((root.path, originals['stat'](root.path).st_dev,
                      originals['stat'](root.path).st_ino,
                      (root.path/'.r19-synthetic-fixture.json').read_bytes())
                     for root in (value.source, value.target))
    def lease_state():
        return tuple((lease, lease._handle) for lease in
                     (value.coordinator._legacy_lease, value.coordinator._target_lease))
    def same_leases(actual):
        assert len(actual) == len(leases) == 2
        assert all(lease is before and handle is original and handle is not None
                   for (lease, handle), (before, original) in zip(actual, leases))
    def checkpoint(phase):
        observe(phase)
        if phase != 'copy-interrupted': return
        link = getattr(value, which).path
        outside = value.fixture/('authored-outside-'+which)
        leases.extend(lease_state())
        before_roots = root_state()
        before_source = probe.migration._source_inventory(plans[0])
        if kind == 'parent-link':
            try:
                link.rename(outside)
            except OSError as error:
                # Windows may deny renaming a tree containing our share-mode-0
                # lease. This is an unmet fault-injection precondition, not a
                # successful root-link test. Inspect this branch explicitly.
                denials.append((getattr(error, 'winerror', None), before_roots, root_state(),
                    before_source, probe.migration._source_inventory(plans[0]),
                    lease_state(), link.is_symlink(), outside.exists(), value.coordinator._leases_held()))
                raise
            restored.append((link, outside))
            link.symlink_to(outside, target_is_directory=True)
        installed.append(kind)
        for name, original in originals.items():
            def guarded(path, *args, original=original, name=name, **options):
                if link in path.parents:
                    touched.append(name);raise AssertionError('Untrusted root descendant metadata/read is forbidden.')
                info = original(path, *args, **options)
                if kind == 'windows-reparse' and name == 'lstat' and path == link:
                    # Behavior injection only: retain the actual original roots
                    # and native leases while testing the Windows attribute gate.
                    return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
                return info
            monkeypatch.setattr(Path, name, guarded)
    monkeypatch.setattr(value, 'observe', checkpoint)
    def hold():
        assert value.adapter.poisoned and not value.released and value.coordinator._leases_held()
        assert value.coordinator._recovery_required
        same_leases(lease_state())
        held.append(True)
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    try:
        try:
            result = value.run()
        except HeldRecovery:
            result = 'held'
        assert len(plans) == 1 and not value.copy_resumed and not touched
        if denials:
            assert kind == 'parent-link' and probe.os.name == 'nt' and len(denials) == 1
            code, before, after, source_before, source_after, captured_leases, is_link, moved, owned = denials[0]
            assert code in {5, 32}, 'Only explicit Windows access/sharing denial is this precondition outcome.'
            assert before == after and source_before == source_after
            same_leases(captured_leases)
            assert owned and not is_link and not moved and not installed and not restored
            assert result == 2 and value.released and not value.adapter.poisoned and not held
            assert not value.coordinator._leases_held()
            assert root_state() == before and probe.migration._source_inventory(plans[0]) == source_before
        else:
            assert installed == [kind] and result == 'held' and held == [True]
    finally:
        for name, original in originals.items(): monkeypatch.setattr(Path, name, original)
        for link, outside in restored:
            if link.is_symlink(): link.unlink()
            outside.rename(link)


def test_local_tree_guard_bounds_entries_and_bytes_before_content_reads(tmp_path, monkeypatch):
    root = tmp_path/'authored-tree';root.mkdir()
    (root/'first').write_bytes(b'ab');(root/'second').write_bytes(b'c')
    monkeypatch.setattr(probe, 'INSPECTION_BYTES', 1)
    with pytest.raises(probe.DataCopyFailure): probe._guard_tree(root)
    monkeypatch.setattr(probe, 'INSPECTION_BYTES', 64)
    monkeypatch.setattr(probe, 'INSPECTION_ENTRIES', 1)
    class Entries:
        def __enter__(self): return iter([SimpleNamespace(name='first'), SimpleNamespace(name='second')])
        def __exit__(self, *_args): pass
    monkeypatch.setattr(probe.os, 'scandir', lambda _root: Entries())
    original = Path.lstat
    def no_second(path, *args, **options):
        assert path != root/'second', 'Overbound child must be refused before leaf metadata.'
        return original(path, *args, **options)
    monkeypatch.setattr(Path, 'lstat', no_second)
    with pytest.raises(probe.DataCopyFailure): probe._guard_tree(root)


def test_setup_connections_include_constructor_and_are_explicitly_closed(tmp_path, monkeypatch):
    observed = []
    original = probe.TranscriptStore._connect
    def connect(self):
        connection = original(self); observed.append(connection); return connection
    monkeypatch.setattr(probe.TranscriptStore, '_connect', connect)
    rows = probe.seed_authored(tmp_path/'transcript.db')
    assert len(observed) == 3 and len(rows) == 2 and rows[0]['source_locale'] == 'zh-Hans'
    for connection in observed:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'): connection.execute('SELECT 1')


def test_setup_exception_still_closes_constructor_connection(tmp_path, monkeypatch):
    observed = []
    original = probe._SetupStore._connect
    def connect(self):
        connection = original(self); observed.append(connection); return connection
    def fail_add(*_args, **_kwargs): raise RuntimeError('authored add refusal')
    monkeypatch.setattr(probe._SetupStore, '_connect', connect)
    monkeypatch.setattr(probe._SetupStore, 'add', fail_add)
    with pytest.raises(RuntimeError, match='authored add refusal'): probe.seed_authored(tmp_path/'transcript.db')
    assert len(observed) == 1
    with pytest.raises(sqlite3.ProgrammingError): observed[0].execute('SELECT 1')


def test_setup_close_refusal_attempts_every_connection_and_is_not_hidden(tmp_path, monkeypatch):
    original = probe.TranscriptStore._connect
    actual, attempts = [], []
    class Connection:
        def __init__(self, connection): self.connection = connection
        def __getattr__(self, name): return getattr(self.connection, name)
        def __enter__(self): self.connection.__enter__(); return self
        def __exit__(self, *args): return self.connection.__exit__(*args)
        def close(self):
            attempts.append(self)
            if self is actual[0]: raise OSError('authored unconfirmed close')
            self.connection.close()
    def connect(self):
        wrapped = Connection(original(self)); actual.append(wrapped); return wrapped
    monkeypatch.setattr(probe.TranscriptStore, '_connect', connect)
    try:
        with pytest.raises(probe.DataCopyFailure, match='setup-close-unconfirmed'):
            probe.seed_authored(tmp_path/'transcript.db')
        assert len(actual) == 3 and set(attempts) == set(actual)
    finally:
        for wrapped in actual: wrapped.connection.close()


class HeldRecovery(BaseException): pass


@pytest.mark.parametrize('boundary', ['create', 'drain', 'close', 'unsignaled', 'identity', 'control', 'setupclose'])
def test_unknown_writer_boundary_holds_live_owner_and_never_copies(fixture, monkeypatch, boundary):
    value = fixture.make()
    original_prepare = value.prepare
    def prepare():
        original_prepare()
        if boundary == 'control':
            value.observe = lambda _phase: (_ for _ in ()).throw(probe.DataCopyFailure('control-unavailable'))
            value.adapter.observe = value.observe
    monkeypatch.setattr(value, 'prepare', prepare)
    def fail(*_args, **_kwargs): raise OSError('private boundary value must not be published')
    if boundary == 'setupclose':
        def unclosed(_path): raise probe.DataCopyFailure('setup-close-unconfirmed')
        monkeypatch.setattr(probe, 'seed_authored', unclosed)
    if boundary == 'create': monkeypatch.setattr(fixture.hosts, 'start_registered', fail)
    if boundary == 'drain': monkeypatch.setattr(fixture.hosts, 'quiesce_registered', fail)
    if boundary == 'close': monkeypatch.setattr(fixture.hosts, 'close', fail)
    if boundary == 'unsignaled':
        original_close = fixture.hosts.close
        def close(host): original_close(host); host.registered['api'].exited = False
        monkeypatch.setattr(fixture.hosts, 'close', close)
    if boundary == 'identity':
        @contextmanager
        def foreign(_host): yield False
        monkeypatch.setattr(fixture.hosts, '_registered_listener_scope', foreign)
    copied = []
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', lambda *_a, **_k: copied.append(True))
    def hold():
        assert value.coordinator._leases_held() and value.adapter.poisoned
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    with pytest.raises(HeldRecovery): value.run()
    assert not copied and not value.released


def test_broken_failure_output_cannot_bypass_live_owner_hold(fixture, monkeypatch):
    value = fixture.make()
    def emit(*_args, **_kwargs): raise BrokenPipeError('private transport error')
    monkeypatch.setattr(value, 'emit', emit)
    def hold():
        assert value.coordinator._leases_held()
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    # Fail while the first real-adapter cohort could write; failure emit fails too.
    original_prepare = value.prepare
    def prepare():
        monkeypatch.setattr(value, 'observe', lambda _phase: None)
        original_prepare()
        value.adapter.start()
        raise OSError('authored active-writer fault')
    monkeypatch.setattr(value, 'prepare', prepare)
    with pytest.raises(HeldRecovery): value.run()
    assert value.adapter.poisoned and not value.released


def test_deterministic_copy_refusal_cannot_restart_source(fixture, monkeypatch, capsys):
    value = fixture.make()
    def refuse(*_args, **_kwargs): raise HostProbeError('insufficient-space', 'authored copy fault')
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', refuse)
    assert value.run() == 2
    assert value.adapter.generation == 1 and not value.adapter.active
    assert value.released and value.target.path.exists() and value.source.path.exists()
    assert value.coordinator.pointer_path.read_bytes() == value.pointer
    final = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert final['status'] == 'failed' and final['failure'] == 'copy-refused'
    checkpoint = json.loads((value.target.path/'host-v1/data-copy-failure.json').read_text())
    assert checkpoint['status'] == 'failed' and checkpoint['failure'] == 'copy-refused'


def test_unconfirmed_lease_close_is_never_retried_with_retained_raw_value(fixture, monkeypatch):
    value = fixture.make()
    original_prepare = value.prepare
    attempts, original_close = [], []
    def prepare():
        original_prepare()
        lease = value.coordinator._target_lease
        original_close.append(lease.close)
        def unconfirmed():
            attempts.append('close')
            raise OSError(6, 'authored invalidated close result')
        monkeypatch.setattr(lease, 'close', unconfirmed)
    monkeypatch.setattr(value, 'prepare', prepare)
    def hold():
        assert value.adapter.poisoned and not value.released
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    try:
        with pytest.raises(HeldRecovery): value.run()
        assert attempts == ['close'] and value.release_attempted
        assert value.adapter.generation == 2 and not value.adapter.active
    finally:
        if original_close: monkeypatch.setattr(value.coordinator._target_lease, 'close', original_close[0])


def test_failed_private_failure_checkpoint_keeps_live_owner_even_after_writer_stop(fixture, monkeypatch):
    value = fixture.make()
    def refuse(*_args, **_kwargs): raise HostProbeError('insufficient-space', 'authored copy fault')
    monkeypatch.setattr(probe.migration, 'copy_and_verify_synthetic', refuse)
    monkeypatch.setattr(probe, '_atomic_json', lambda *_a, **_k: (_ for _ in ()).throw(OSError('authored checkpoint I/O refusal')))
    def hold():
        assert value.coordinator._leases_held() and value.adapter.poisoned and not value.adapter.active
        raise HeldRecovery()
    monkeypatch.setattr(probe, 'hold_keeper_recovery', hold)
    with pytest.raises(HeldRecovery): value.run()
    assert value.adapter.generation == 1 and not value.release_attempted


@pytest.mark.parametrize('version,extra', [(1, False), (0, True)])
def test_fixed_schema_verification_refuses_changed_version_or_extra_table(fixture, monkeypatch, version, extra):
    value = fixture.make()
    original = probe.verify_authored_snapshot
    def verify(snapshot, target, expected):
        with closing(sqlite3.connect(snapshot/'data/transcript-v2.db')) as connection, connection:
            connection.execute('PRAGMA user_version='+str(version))
            if extra: connection.execute('CREATE TABLE unknown_authored_store(value TEXT)')
        original(snapshot, target, expected)
    monkeypatch.setattr(probe, 'verify_authored_snapshot', verify)
    assert value.run() == 2 and value.adapter.generation == 1
    assert value.released and value.target.path.exists()


def test_snapshot_semantic_check_does_not_change_source_or_snapshot_bytes(fixture, monkeypatch):
    value = fixture.make()
    observed = []
    original = probe.verify_authored_snapshot
    def verify(snapshot, target, expected):
        before = probe.migration._inventory(snapshot)
        original(snapshot, target, expected)
        assert probe.migration._inventory(snapshot) == before
        observed.append(True)
    monkeypatch.setattr(probe, 'verify_authored_snapshot', verify)
    assert value.run() == 0 and observed == [True]


@pytest.mark.parametrize('field,value', [('favorite', 1), ('id', True), ('id', 1.0), ('texts', []), ('source_locale', None)])
def test_authored_row_validation_rejects_bool_integer_and_context_coercions(tmp_path, field, value):
    row = probe.seed_authored(tmp_path/'store.db')[0]
    row[field] = value
    with pytest.raises(probe.DataCopyFailure, match='authored-rows-differ'): probe._row(row)


def test_adapter_never_admits_setup_or_warm_readiness_as_proof(fixture):
    value = fixture.make()
    value.prepare()
    adapter = value.adapter
    with pytest.raises(probe.DataCopyFailure): adapter.ready()
    with pytest.raises(probe.DataCopyFailure): adapter.prepare()
    adapter.setup_open = True
    with pytest.raises(probe.DataCopyFailure): adapter.start()
    assert adapter.generation == 0 and not adapter.cohorts
    adapter.setup_open = False


def test_partial_fresh_start_increments_generation_and_never_reuses_old_children(fixture, monkeypatch):
    value = fixture.make()
    value.prepare(); value.adapter.start()
    # Checkpoint controls in prepare consumed setup-closed only; suppress the
    # fixed native-stage handshake for this local admission-order regression.
    value.adapter.observe = lambda _phase: None
    value.adapter.quiesce()
    old = value.adapter.host
    def fail(_host, **_kwargs): raise OSError('authored second-cohort creation fault')
    monkeypatch.setattr(fixture.hosts, 'start_registered', fail)
    with pytest.raises(OSError): value.adapter.activate(probe.SyntheticHandoff(False))
    assert value.adapter.generation == 2 and value.adapter.poisoned
    assert old is not value.adapter.host and all(child.closed and child.exited for child in old.registered.values())
    assert [host for name, host in fixture.calls if name == 'resume'] == [old]


def _powershell_contract(script, functions, body, payload=None):
    executable = shutil.which('pwsh')
    if not executable: pytest.skip('PowerShell parser/contract unavailable locally; required on hosted Windows.')
    text = "$ErrorActionPreference='Stop'\n"
    text += "$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors)\n"
    text += "if ($errors) { throw 'Data-copy harness parse failure.' }\n"
    for function in functions:
        text += "$definition=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq '"+function+"'},$true)\n"
        text += "if (-not $definition) { throw 'Missing fixed data-copy function.' };. ([scriptblock]::Create($definition.Extent.Text))\n"
    text += "$script:ProbeCase='authored-data-copy'\n"
    text += body
    with tempfile.TemporaryDirectory(prefix='r19-data-copy-contract-') as temporary:
        driver = Path(temporary)/'contract.ps1'
        driver.write_text(text, encoding='utf-8')
        result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-File', str(driver), str(script)],
            input=json.dumps(payload).encode() if payload is not None else None, capture_output=True, timeout=20)
    diagnostic = 'unavailable'
    if result.returncode and isinstance(payload, list):
        try:
            value = json.loads(result.stdout)
            if (set(value) == {'schema', 'case_index', 'expected', 'actual'}
                    and value['schema'] == 'proxy-r19-data-copy-contract-failure-v1'
                    and type(value['case_index']) is int and 0 <= value['case_index'] < len(payload)
                    and type(value['expected']) is bool and type(value['actual']) is bool):
                diagnostic = f"case={value['case_index']},expected={value['expected']},actual={value['actual']}"
        except (ValueError, TypeError, KeyError):
            pass
    assert result.returncode == 0, 'Fixed data-copy PowerShell contract failed: '+diagnostic


def test_powershell_roots_use_actual_child_temp_and_failure_receipt_cannot_skip_live_hold(tmp_path):
    script = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-data-copy.ps1'
    _powershell_contract(script, ['Get-DataCopyRoots', 'Complete-DataCopyHarness'], r'''
$roots=Get-DataCopyRoots ([IO.Path]::GetTempPath())
$prefix=Join-Path ([IO.Path]::GetTempPath()) 'empty-host'
if (-not $roots.PROXY_TRANSCRIPT_WORK_ROOT.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Child TEMP containment differs.' }
$script:held=$false;$script:ownerExitConfirmed=$false
$owned=@([pscustomobject]@{HasExited=$false})
function Write-DataCopyReceipt { throw 'authored failed receipt channel' }
function Wait-DataCopyRecovery { $script:held=$true;throw 'authored held sentinel' }
$Output=Join-Path ([IO.Path]::GetTempPath()) ('r19-unused-'+[guid]::NewGuid().ToString('N')+'.json')
try { Complete-DataCopyHarness $true } catch {}
if (-not $script:held) { throw 'Receipt failure bypassed live owner hold.' }
$script:held=$false;$script:ownerExitConfirmed=$true
$script:queried=0
$observer=[pscustomobject]@{}
$observer | Add-Member ScriptProperty HasExited { $script:queried++;throw 'authored unavailable disposed observer' }
$owned=@($observer)
try { Complete-DataCopyHarness $true } catch {}
if ($script:held -or $script:queried -ne 0) { throw 'Known signaled owner cannot be queried again through disposed observer state.' }
''')


def test_powershell_event_validation_requires_exact_types_lifecycle_and_safe_scope(fixture, capsys):
    value = fixture.make()
    value.prepare()
    event = json.loads(capsys.readouterr().out.splitlines()[0])
    cases = [{'name': 'valid-setup', 'event': event, 'accept': True}]
    for field, changed in [('generation', True), ('generation', 1), ('r19_complete', 'false'),
            ('kind', ['data-copy']), ('copy_verification', 'passed'), ('old_barrier_refused', True),
            ('source_commit', 'b'*40), ('authority', 'http-only'), ('phase', 'released'),
            ('wal_files', 4), ('failure', 'private-unapproved-category')]:
        cases.append({'name': field+'-refusal', 'event': {**event, field: changed}, 'accept': False})
    cases.append({'name': 'extra-property-refusal', 'event': {**event, 'unexpected': 'private sentinel'}, 'accept': False})
    script = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-data-copy.ps1'
    _powershell_contract(script, ['New-DataCopyControlReader','Read-DataCopyControlLine','Read-DataCopyEvent'], r'''
$proof=[pscustomobject]@{source_commit=('a'*40);build_id='authored-data-copy-fixture'}
$cases=[Console]::In.ReadToEnd() | ConvertFrom-Json
$index=0
foreach ($case in $cases) {
    $bytes=[Text.UTF8Encoding]::new($false,$true).GetBytes(($case.event | ConvertTo-Json -Depth 8 -Compress)+"`n")
    $stream=[IO.MemoryStream]::new($bytes,$false)
    $script:controlReader=New-DataCopyControlReader $stream ([Threading.Tasks.Task]::CompletedTask)
    $accepted=$true
    try { Read-DataCopyEvent 'setup-closed' } catch { $accepted=$false }
    if ($accepted -ne $case.accept) {
        [Console]::Out.WriteLine((@{schema='proxy-r19-data-copy-contract-failure-v1';case_index=$index;
            expected=[bool]$case.accept;actual=[bool]$accepted} | ConvertTo-Json -Compress))
        exit 2
    }
    $stream.Dispose()
    $index++
}
''', cases)


def test_powershell_control_reader_caps_raw_bytes_and_faults_hold_live_owner_even_if_receipt_fails():
    script = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-data-copy.ps1'
    _powershell_contract(script, ['New-DataCopyControlReader','Read-DataCopyControlLine','Complete-DataCopyHarness'], r'''
$utf8=[Text.UTF8Encoding]::new($false,$true)
$complete=[Threading.Tasks.Task]::CompletedTask
$stream=[IO.MemoryStream]::new($utf8.GetBytes("{}`n[]`n"),$false)
$reader=New-DataCopyControlReader $stream $complete
if ((Read-DataCopyControlLine $reader) -cne '{}' -or (Read-DataCopyControlLine $reader) -cne '[]' -or
    $null -ne (Read-DataCopyControlLine $reader 1000 $true) -or $reader.buffer.Length -ne 4096 -or
    $reader.line.Length -ne 8192 -or $null -ne $reader.pending) { throw 'Fixed control buffer/consumer contract differs.' }
$stream.Dispose()
$multibyte=([char]0x6f22).ToString()*3000
if ($multibyte.Length -ge 8192 -or $utf8.GetByteCount($multibyte) -le 8192) { throw 'Authored multibyte boundary differs.' }
$cases=@(
    @{bytes=$utf8.GetBytes(('x'*8193)+"`n");reason='control-overflow'},
    @{bytes=$utf8.GetBytes($multibyte+"`n");reason='control-overflow'},
    @{bytes=$utf8.GetBytes(('x'*100));reason='control-eof'},
    @{bytes=$utf8.GetBytes('{"partial":');reason='control-eof'},
    @{bytes=[byte[]]@(255,10);reason='control-invalid-utf8'})
foreach ($case in $cases) {
    $stream=[IO.MemoryStream]::new($case.bytes,$false)
    $reader=New-DataCopyControlReader $stream $complete
    $accepted=$true
    try { $null=Read-DataCopyControlLine $reader 1000 } catch { $accepted=$false }
    if ($accepted -or $reader.fault -cne $case.reason) { throw 'Fixed byte/framing refusal differs.' }
    # A poisoned reader cannot consume a newly substituted valid stream.
    $sentinel=[IO.MemoryStream]::new([byte[]]@(123,125,10),$false)
    $reader.stream=$sentinel
    try { $null=Read-DataCopyControlLine $reader 1000 } catch {}
    if ($sentinel.Position -ne 0 -or $reader.fault -cne $case.reason) { throw 'Poisoned control reader was rearmed.' }
    $sentinel.Dispose();$stream.Dispose()
}
$stream=[IO.MemoryStream]::new([byte[]]@(123,125,10),$false)
$reader=New-DataCopyControlReader $stream $complete
$stream.Dispose()
try { $null=Read-DataCopyControlLine $reader 1000 } catch {}
if ($reader.fault -cne 'control-reader-unavailable') { throw 'Reader I/O refusal differs.' }
$stream=[IO.MemoryStream]::new([byte[]]@(123,125,10),$false)
$discard=[Threading.Tasks.Task]::FromException([IO.IOException]::new('authored discard refusal'))
$reader=New-DataCopyControlReader $stream $discard
try { $null=Read-DataCopyControlLine $reader 1000 } catch {}
if ($reader.fault -cne 'stderr-unavailable' -or $stream.Position -ne 0) { throw 'Discard I/O refusal differs.' }
$stream.Dispose()
# The exact overflow path and a broken failure publisher still retain a live owner.
$stream=[IO.MemoryStream]::new($utf8.GetBytes(('x'*8193)+"`n"),$false)
$reader=New-DataCopyControlReader $stream $complete
try { $null=Read-DataCopyControlLine $reader 1000 } catch {}
if ($reader.fault -cne 'control-overflow') { throw 'Expected fixed overflow is unavailable.' }
$script:held=$false;$script:ownerExitConfirmed=$false
$owned=@([pscustomobject]@{HasExited=$false})
function Write-DataCopyReceipt { throw 'authored failed receipt channel' }
function Wait-DataCopyRecovery { $script:held=$true;throw 'authored livehold sentinel' }
$Output=Join-Path ([IO.Path]::GetTempPath()) ('r19-unused-'+[guid]::NewGuid().ToString('N')+'.json')
try { Complete-DataCopyHarness $true } catch {}
if (-not $script:held) { throw 'Control overflow/receipt failure bypassed live owner hold.' }
$stream.Dispose()
''')


def test_powershell_resume_protocol_is_distinct_and_requires_exact_partial_revalidation(fixture, capsys):
    value = fixture.make(probe.RESUME_CASE)
    assert value.run() == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    cases = [{'probe_case': probe.RESUME_CASE, 'phase': event['phase'], 'event': event, 'accept': True} for event in events]
    partial = next(event for event in events if event['phase'] == 'copy-interrupted')
    for field, changed in [('schema', probe.SCHEMA), ('generation', 2), ('copy_attempts', 2),
            ('authored_interruptions', 2), ('partial_completed_files', 2), ('partial_revalidations', 0),
            ('same_plan_barrier_generation', False), ('copy_resumed', True), ('copy_attempts', True)]:
        cases.append({'probe_case': probe.RESUME_CASE, 'phase': 'copy-interrupted',
                      'event': {**partial, field: changed}, 'accept': False})
    cases.append({'probe_case': probe.CASE, 'phase': 'setup-closed',
        'event': {**events[0], 'schema': probe.SCHEMA, 'case': probe.CASE}, 'accept': False})
    verified = next(event for event in events if event['phase'] == 'copy-verified')
    cases.append({'probe_case': probe.RESUME_CASE, 'phase': 'copy-verified',
                  'event': {**verified, 'partial_revalidations': 1}, 'accept': False})
    script = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-data-copy.ps1'
    _powershell_contract(script, ['New-DataCopyControlReader','Read-DataCopyControlLine','Read-DataCopyEvent'], r'''
$proof=[pscustomobject]@{source_commit=('a'*40);build_id='authored-data-copy-fixture'}
$cases=[Console]::In.ReadToEnd() | ConvertFrom-Json
$index=0
foreach ($case in $cases) {
    $script:ProbeCase=$case.probe_case
    $bytes=[Text.UTF8Encoding]::new($false,$true).GetBytes(($case.event | ConvertTo-Json -Depth 8 -Compress)+"`n")
    $stream=[IO.MemoryStream]::new($bytes,$false)
    $script:controlReader=New-DataCopyControlReader $stream ([Threading.Tasks.Task]::CompletedTask)
    $accepted=$true
    try { Read-DataCopyEvent $case.phase } catch { $accepted=$false }
    if ($accepted -ne $case.accept) {
        [Console]::Out.WriteLine((@{schema='proxy-r19-data-copy-contract-failure-v1';case_index=$index;
            expected=[bool]$case.accept;actual=[bool]$accepted} | ConvertTo-Json -Compress))
        exit 2
    }
    $stream.Dispose();$index++
}
''', cases)


def test_powershell_resume_receipt_cannot_relabel_positive_case_or_omit_extra_source_block():
    script = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-data-copy.ps1'
    _powershell_contract(script, ['Write-DataCopyReceipt'], r'''
$private=Join-Path ([IO.Path]::GetTempPath()) ('r19-authored-receipt-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $private
$slotSourceOperation=Join-Path $private 'source-fixture.ps1'
[IO.File]::WriteAllText($slotSourceOperation,'authored source-operation fixture')
$proof=[pscustomobject]@{source_commit=('a'*40);build_id='authored-data-copy-fixture'}
$sourceBlocks=9;$walFiles=0;$shmFiles=0;$stage='release';$failureCategory='none'
try {
    $script:ProbeCase='authored-data-copy';$Output=Join-Path $private 'positive.json'
    Write-DataCopyReceipt 'passed'
    $positive=Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
    if ($positive.schema -cne 'proxy-r19-frozen-data-copy-receipt-v1' -or $positive.case -cne 'authored-data-copy' -or
        $positive.scope -cne 'authored-transcript-copy-with-living-coordinator' -or
        $positive.source_operation_blocked_observations -ne 9 -or $null -ne $positive.PSObject.Properties['fault_model']) {
        throw 'The existing positive receipt changed meaning.'
    }
    $script:ProbeCase='authored-data-copy-resume';$Output=Join-Path $private 'resume.json'
    $accepted=$true
    try { Write-DataCopyReceipt 'passed' } catch { $accepted=$false }
    if ($accepted -or (Test-Path -LiteralPath $Output)) { throw 'Resume receipt omitted the extra actual source block.' }
    $sourceBlocks=10;Write-DataCopyReceipt 'passed'
    $resume=Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
    if ($resume.schema -cne 'proxy-r19-frozen-data-copy-resume-receipt-v1' -or $resume.case -cne 'authored-data-copy-resume' -or
        $resume.scope -cne 'authored-transcript-interrupted-copy-resume-with-living-coordinator' -or
        $resume.copy_attempts -ne 2 -or $resume.authored_interruptions -ne 1 -or $resume.partial_completed_files -ne 1 -or
        $resume.partial_revalidations -ne 2 -or $resume.resume_authority -cne 'same-live-owner-plan-barrier-generation-leases' -or
        $resume.target_activation -isnot [bool] -or $resume.target_activation -or $resume.production_activation -or $resume.r19_complete) {
        throw 'Fixed resume receipt scope or gates differ.'
    }
} finally { Remove-Item -LiteralPath $private -Recurse -Force }
''')
