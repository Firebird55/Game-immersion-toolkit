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
    def make():
        stream = io.StringIO(''.join('observed '+phase+'\n' for phase in probe.PHASES[:-1]))
        value = probe._DataCopyProbe(layout, stream)
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
