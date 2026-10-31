"""One authored frozen store copy; never a production migration authority."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import shutil
import sqlite3
import tempfile
import threading
import uuid
from urllib.request import Request, urlopen

from . import bundle_migration as migration
from .bundle_host import (HostProbeError, SyntheticHandoff, SyntheticHostCoordinator,
                          WriterStopProof, _atomic_json, create_synthetic_root)
from .models import TextMatch
from .runtime_host import FrozenProbeHost, HostProbeFailure, hold_keeper_recovery
from .storage import TranscriptStore

SCHEMA = 'proxy-r19-frozen-data-copy-probe-v1'
CASE = 'authored-data-copy'
PHASES = ('setup-closed', 'favorite-written', 'strict-drain-complete', 'writers-signaled',
          'copy-progress', 'copy-verified', 'source-resumed', 'final-strict-drain-complete',
          'final-writers-signaled', 'released')
FAILURES = frozenset({'fixture-unavailable', 'setup-close-unconfirmed', 'setup-still-open',
    'cohort-unconfirmed', 'owned-host-unconfirmed', 'copy-refused', 'copy-result-unconfirmed',
    'schema-unconfirmed', 'authored-rows-differ', 'pointer-changed', 'source-changed',
    'control-unavailable', 'control-invalid', 'lease-release-unconfirmed', 'unexpected-data-copy-failure'})
DATABASE_VERSIONS = {'data/transcript-v2.db': 0, 'data/lexirise/exports-v2.db': 0,
                     'data/lexirise/reading-cache-v2.db': 0}
TABLE_COLUMNS = {
    'data/transcript-v2.db': {'transcript_lines': ('id', 'created_at', 'session_id', 'game',
        'source_ocr', 'english', 'chinese', 'text_id', 'score', 'match_kind', 'ambiguous',
        'channel', 'voiced', 'audio_path', 'speaker_english', 'speaker_chinese', 'favorite',
        'language_context'), 'sqlite_sequence': ('name', 'seq')},
    'data/lexirise/exports-v2.db': {'exports': ('key', 'state'), 'export_refs': ('ref', 'export_key'),
        'scoped_exports': ('scope', 'key', 'state'),
        'scoped_export_refs': ('scope', 'ref', 'export_key'),
        'game_decks': ('scope', 'game', 'deck_id', 'title')},
    'data/lexirise/reading-cache-v2.db': {'cache': ('kind', 'key', 'value', 'at'),
        'grammar_choices': ('slug', 'proficiency')},
}
OPTIONAL_TABLE_COLUMNS = {'data/transcript-v2.db': {'sqlite_stat1': ('tbl', 'idx', 'stat')}}
ROW_FIELDS = ('id', 'game', 'text_id', 'english', 'chinese', 'source_ocr', 'source_language',
    'source_locale', 'source_text', 'translation_locale', 'translation_text', 'audio_locale',
    'texts', 'voice_status', 'dialogue_kind', 'favorite', 'voiced', 'has_audio')
STOPPED = WriterStopProof(True, True, True, True, True)


class DataCopyFailure(RuntimeError):
    def __init__(self, code):
        self.code = code if code in FAILURES else 'unexpected-data-copy-failure'
        super().__init__('Authored frozen data copy failed: '+self.code)


def _row(value):
    if not isinstance(value, dict) or any(key not in value for key in ROW_FIELDS):
        raise DataCopyFailure('authored-rows-differ')
    if (type(value['id']) is not int or value['id'] < 1
            or any(type(value[key]) is not bool for key in ('favorite', 'voiced', 'has_audio'))
            or any(type(value[key]) is not str for key in ROW_FIELDS
                   if key not in {'id', 'favorite', 'voiced', 'has_audio', 'texts'})
            or type(value['texts']) is not dict
            or any(type(key) is not str or type(text) is not str for key, text in value['texts'].items())):
        raise DataCopyFailure('authored-rows-differ')
    return {key: value[key] for key in ROW_FIELDS}


class _SetupStore(TranscriptStore):
    def __init__(self, path, connections):
        self._owned_connections = connections
        super().__init__(path)

    def _connect(self):
        connection = super()._connect()
        self._owned_connections.append(connection)
        return connection


def seed_authored(path):
    """Actual production SQL, with explicit ownership of every setup connection."""
    connections = []
    try:
        store = _SetupStore(path, connections)
        rows = []
        for index, (chinese, english) in enumerate((('这是保留的中文。', 'This Chinese text stays.'),
                ('第二行保持原样。', 'The second line stays unchanged.')), 1):
            match = TextMatch(game='hito', text_id=f'r19-authored-{index}', english=english,
                chinese=chinese, source_ocr=chinese, score=1, kind='exact',
                source_language='zh', source_locale='zh-Hans', source_text=chinese,
                translation_locale='en', translation_text=english, audio_locale='zh-Hans',
                texts={'zh-Hans': chinese, 'en': english}, voice_status='unvoiced',
                dialogue_kind='ordinary-conversation')
            line = store.add(match, 'r19-authored-session',
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            rows.append(_row(line.model_dump(mode='json')))
        return rows
    finally:
        failed = False
        for connection in reversed(connections):
            try:
                connection.close()
            except BaseException:
                failed = True
        if failed:
            raise DataCopyFailure('setup-close-unconfirmed')


def verify_authored_snapshot(snapshot, target, expected):
    """Read separate verification copies; never run store initialization here."""
    for name, tables in TABLE_COLUMNS.items():
        with tempfile.TemporaryDirectory(prefix='authored-semantic-', dir=target) as temporary:
            database = Path(temporary)/'store.db'
            source = snapshot/name
            shutil.copy2(source, database)
            for suffix in ('-wal', '-shm'):
                sidecar = source.with_name(source.name+suffix)
                if sidecar.exists():
                    shutil.copy2(sidecar, database.with_name(database.name+suffix))
            connection = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
            connection.row_factory = sqlite3.Row
            try:
                actual = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                known = {**tables, **OPTIONAL_TABLE_COLUMNS.get(name, {})}
                if (not set(tables) <= actual or not actual <= set(known)
                        or connection.execute('PRAGMA user_version').fetchone()[0] != 0):
                    raise DataCopyFailure('schema-unconfirmed')
                for table in actual:
                    columns = known[table]
                    # Every identifier above is a fixed authored constant.
                    found = tuple(row[1] for row in connection.execute('PRAGMA table_info('+table+')'))
                    if found != columns:
                        raise DataCopyFailure('schema-unconfirmed')
                if name == 'data/transcript-v2.db':
                    rows = [_row(TranscriptStore._row_to_line(row).model_dump(mode='json'))
                            for row in connection.execute('SELECT * FROM transcript_lines ORDER BY id')]
                    if rows != expected:
                        raise DataCopyFailure('authored-rows-differ')
            finally:
                connection.close()


class _FrozenAuthoredDataRuntime:
    """Fixed writer admission only. The coordinator, not this adapter, owns leases."""
    def __init__(self, layout, installation_id, observe):
        self.layout, self.installation_id, self.observe = layout, installation_id, observe
        self.runtime_id = 'authored-source'
        self.generation = self.drains = 0
        self.setup_open = self.active = self.poisoned = False
        self.host = None
        self.cohorts = []

    def _require_owned(self):
        if self.poisoned:
            raise DataCopyFailure('cohort-unconfirmed')

    def prepare(self):
        raise DataCopyFailure('cohort-unconfirmed')  # No warm-candidate preparation in this case.

    def ready(self):
        raise DataCopyFailure('cohort-unconfirmed')  # Readiness cannot become a copy token.

    def capture_running(self):
        # Conservative producer state, not an observation of physical capture.
        return self.setup_open or self.active or self.poisoned

    def write_generation(self):
        return self.generation

    def start(self):
        self._require_owned()
        if self.setup_open or self.active or self.generation >= 2:
            raise DataCopyFailure('setup-still-open')
        self.generation += 1  # Invalidate older proof before even a partial creation attempt.
        self.active = True
        try:
            self.host = FrozenProbeHost(self.layout)
            self.cohorts.append(self.host)
            self.host.start_registered(detached_console=True)
            self.host.resume_registered()
            self.host.wait_services()
        except BaseException:
            self.poisoned = True
            raise

    def request(self, request):
        self._require_owned()
        if not self.active:
            raise DataCopyFailure('cohort-unconfirmed')
        try:
            with self.host._registered_listener_scope() as owned:
                if not owned:
                    raise DataCopyFailure('owned-host-unconfirmed')
                with urlopen(request, timeout=5) as response:
                    data = response.read(65537)
                    if response.status != 200 or len(data) > 65536:
                        raise DataCopyFailure('owned-host-unconfirmed')
                    return json.loads(data)
        except BaseException:
            self.poisoned = True
            raise

    def quiesce(self):
        self._require_owned()
        if self.setup_open or not self.active or self.host is None:
            raise DataCopyFailure('cohort-unconfirmed')
        try:
            self.host.quiesce_registered()
            self.drains += 1
            prefix = 'final-' if self.generation == 2 else ''
            self.observe(prefix+'strict-drain-complete')
            self.host.close()
            children = self.host.registered
            if (not self.host.closed or self.host.tree is not None or self.host.recovery_required
                    or set(children) != {'frontend', 'api'} or
                    not all(child.created and child.resumed and child.exited and child.closed
                            for child in children.values())):
                raise DataCopyFailure('cohort-unconfirmed')
            self.active = False
            self.observe(prefix+'writers-signaled')
            return STOPPED, SyntheticHandoff(False)
        except BaseException:
            self.poisoned = True
            raise

    def activate(self, handoff):
        self._require_owned()
        if type(handoff) is not SyntheticHandoff or handoff.running is not False or self.active or self.generation != 1:
            self.poisoned = True
            raise DataCopyFailure('cohort-unconfirmed')
        self.start()  # A new same-source Job/cohort; never the snapshot or old exited handles.

    def stop(self):
        self._require_owned()
        if self.setup_open:
            self.poisoned = True
            raise DataCopyFailure('setup-still-open')
        if self.active:
            return self.quiesce()[0]
        return STOPPED


class _DataCopyProbe:
    def __init__(self, layout, stream):
        FrozenProbeHost(layout)  # Existing exact-image/profile/private-root/dev-tool guards.
        self.outer, self.stream = layout, stream
        self.adapter = self.coordinator = None
        self.enter_attempted = self.entered = self.released = self.release_attempted = False
        self.phase = 'prepare'
        self.copy_verified = self.source_preserved = self.logical_preserved = False
        self.old_barrier_refused = False
        self.wal_files = self.shm_files = 0
        self.commands = queue.Queue(maxsize=1)
        def read():
            try:
                while True:
                    value = stream.readline(257)
                    self.commands.put(value)
                    if not value:
                        return
            except BaseException:
                self.commands.put(None)
        threading.Thread(target=read, name='authored-copy-control', daemon=True).start()

    def emit(self, phase, *, failure='none'):
        adapter = self.adapter
        children = [child for host in adapter.cohorts for child in host.registered.values()] if adapter else []
        value = {'schema': SCHEMA, 'kind': 'data-copy', 'case': CASE, 'phase': phase,
            'status': 'failed' if failure != 'none' else 'passed' if phase == 'released' else 'observing',
            'failure': failure, 'source_commit': self.outer.source_commit, 'build_id': self.outer.build_id,
            'generation': adapter.generation if adapter else 0,
            'writers_created': sum(bool(child.created) for child in children),
            'writers_resumed': sum(bool(child.resumed) for child in children),
            'writers_signaled': sum(bool(child.exited) for child in children),
            'strict_drains': adapter.drains if adapter else 0,
            'copy_verification': 'passed' if self.copy_verified else 'not-run',
            'source_bytes': 'preserved-before-resume' if self.source_preserved else 'not-run',
            'source_logical': 'passed' if self.logical_preserved else 'not-run',
            'wal_files': self.wal_files, 'shm_files': self.shm_files,
            'old_barrier_refused': self.old_barrier_refused,
            'api_external_side_effects': 'mocked', 'sqlite': 'real', 'native_owned_process_tree': 'real',
            'writer_console_mode': 'detached-process', 'authority': 'retained-creation-objects-and-typed-barrier',
            'production_activation': False, 'target_activation': False, 'r19_complete': False,
            'keeper_loss': 'unavailable', 'dynamic_writer_admission': 'unavailable',
            'warm_routing': 'unavailable', 'credentials': 'not-accessed', 'browser': 'not-run', 'installer': 'not-built'}
        print(json.dumps(value, separators=(',', ':')), flush=True)

    def observe(self, phase):
        if phase not in PHASES or phase == 'released':
            raise DataCopyFailure('control-invalid')
        self.phase = phase
        self._pointer_unchanged()
        self.emit(phase)
        try:
            command = self.commands.get(timeout=45)
        except queue.Empty:
            raise DataCopyFailure('control-unavailable') from None
        if command != 'observed '+phase+'\n':
            raise DataCopyFailure('control-invalid')

    def _pointer_unchanged(self):
        if self.coordinator.pointer_path.read_bytes() != self.pointer:
            raise DataCopyFailure('pointer-changed')

    def prepare(self):
        work = self.outer.work_root
        temporary = Path(tempfile.gettempdir()).resolve()
        if work == temporary or not work.is_relative_to(temporary):
            raise DataCopyFailure('fixture-unavailable')
        self.fixture = work/'authored-data-copy'
        self.fixture.mkdir(parents=True, exist_ok=False)
        self.source = create_synthetic_root(self.fixture/'legacy')
        self.target = create_synthetic_root(self.fixture/'private-target', installation_id=self.source.installation_id)
        root = self.source.path
        layout = replace(self.outer, settings_root=root, data_root=root/'data', cache_root=root/'cache-v1',
            work_root=root/'cache-v1/work', tool_root=root/'tools-v1', state_root=root/'probe-state',
            default_export_root=root/'exports')
        layout.state_root.mkdir()
        (layout.state_root/'synthetic-probe.json').write_text(
            json.dumps({'build_id': layout.build_id, 'synthetic': True}), encoding='utf-8')
        self.adapter = _FrozenAuthoredDataRuntime(layout, self.source.installation_id, self.observe)
        self.coordinator = SyntheticHostCoordinator(self.source, self.target, self.adapter)
        self.enter_attempted = True
        self.coordinator.__enter__()
        self.entered = True
        self.pointer = self.coordinator.pointer_path.read_bytes()
        self.adapter.setup_open = True
        try:
            self.expected = seed_authored(layout.data_root/'transcript-v2.db')
            (layout.data_root/'authored-payload.bin').write_bytes(b'R19 authored bytes only\x00\xff')
        except BaseException as error:
            if isinstance(error, DataCopyFailure) and error.code == 'setup-close-unconfirmed':
                self.adapter.poisoned = True
            raise
        finally:
            self.adapter.setup_open = False
        self.observe('setup-closed')

    def exercise(self):
        self.adapter.start()
        first = self.expected[0]
        value = self.adapter.request(Request('http://127.0.0.1:8766/api/lines/'+str(first['id'])+'/favorite',
            data=b'{"favorite":true}', method='PATCH', headers={'Content-Type': 'application/json'}))
        first['favorite'] = True
        if _row(value) != first:
            raise DataCopyFailure('authored-rows-differ')
        self.observe('favorite-written')
        plan = migration.SyntheticMigrationPlan(self.source, self.target, str(uuid.uuid4()),
            database_versions=DATABASE_VERSIONS)
        with self.coordinator.stopped_writers(self.coordinator.owner) as barrier:
            baseline = migration._source_inventory(plan)
            progress = False
            def checkpoint(stage, _name):
                nonlocal progress
                if stage == 'file-copied' and not progress:
                    progress = True
                    self.observe('copy-progress')
            result = migration.copy_and_verify_synthetic(plan, barrier, checkpoint=checkpoint)
            if (result.get('state') != 'verified' or result.get('activation_allowed') is not False
                    or result.get('migration_acceptance') != 'incomplete' or not progress):
                raise DataCopyFailure('copy-result-unconfirmed')
            snapshot = self.target.path/'staging'/plan.migration_id
            verify_authored_snapshot(snapshot, self.target.path, self.expected)
            if migration._source_inventory(plan) != baseline:
                raise DataCopyFailure('source-changed')
            migration._verify_snapshot(snapshot, *baseline)
            self.wal_files = sum((snapshot/name).with_name(Path(name).name+'-wal').is_file() for name in DATABASE_VERSIONS)
            self.shm_files = sum((snapshot/name).with_name(Path(name).name+'-shm').is_file() for name in DATABASE_VERSIONS)
            self.copy_verified = self.source_preserved = True
            self.observe('copy-verified')
        try:
            barrier.check(self.source)
        except HostProbeError as error:
            if error.code != 'writer-barrier-required':
                raise
            self.old_barrier_refused = True
        else:
            raise DataCopyFailure('cohort-unconfirmed')
        rows = self.adapter.request('http://127.0.0.1:8766/api/lines?game=hito')
        if not isinstance(rows, list) or sorted((_row(row) for row in rows), key=lambda row: row['id']) != self.expected:
            raise DataCopyFailure('authored-rows-differ')
        self.logical_preserved = True
        self.observe('source-resumed')
        self.adapter.quiesce()
        self._pointer_unchanged()
        self.phase = 'release'
        self.release_attempted = True
        try:
            self.coordinator.close(self.coordinator.owner)
        except BaseException:
            raise DataCopyFailure('lease-release-unconfirmed') from None
        self.released = True
        self._pointer_unchanged()
        self.emit('released')

    def run(self):
        try:
            self.prepare()
            self.exercise()
            return 0
        except BaseException as error:
            hold = ((self.enter_attempted and not self.entered)
                    or (self.release_attempted and not self.released))
            if self.adapter and self.adapter.capture_running():
                self.adapter.poisoned = True
                hold = True
            if isinstance(error, DataCopyFailure):
                code = error.code
            elif isinstance(error, HostProbeFailure):
                code = 'owned-host-unconfirmed'
            elif isinstance(error, HostProbeError):
                code = 'copy-refused'
            else:
                code = 'unexpected-data-copy-failure'
            if self.entered and not self.release_attempted:
                try:
                    _atomic_json(self.target.path/'host-v1/data-copy-failure.json', {
                        'schema': SCHEMA, 'status': 'failed', 'failure': code, 'phase': self.phase,
                        'source_commit': self.outer.source_commit, 'build_id': self.outer.build_id,
                        'target_activation': False, 'r19_complete': False})
                except BaseException:
                    hold = True
            if self.entered and not self.released and not hold:
                try:
                    self.release_attempted = True
                    self.coordinator.close(self.coordinator.owner)
                    self.released = True
                except BaseException:
                    hold = True
            if hold and self.adapter:
                self.adapter.poisoned = True
            try:
                self.emit('recovery-required', failure=code)
            except BaseException:
                pass
            if hold:
                # Neither failed metadata output nor closed stdin may release
                # exclusion while writer/handle cleanup is unconfirmed.
                hold_keeper_recovery()
            return 2


def run(layout, stream):
    return _DataCopyProbe(layout, stream).run()
