"""Scoped behavior fixtures; real extracted Job/handle cases run on Windows."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend import bundle_entry, runtime_host
from backend.runtime_bundle import RuntimeLayout


@pytest.fixture
def layout(tmp_path, monkeypatch):
    app, private = tmp_path/'app', tmp_path/'private'
    app.mkdir(); (app/'ProxyTranscriptRuntime.exe').write_bytes(b'authored-image-placeholder')
    state = private/'host-v1'; state.mkdir(parents=True)
    (state/'synthetic-probe.json').write_text(json.dumps({'build_id': 'host-fixture', 'synthetic': True}))
    value = RuntimeLayout(mode='bundle', profile='runtime-experiment', application_root=app,
        resource_root=app/'_internal', executable=app/'ProxyTranscriptRuntime.exe', data_root=private/'data-v1',
        settings_root=private, cache_root=private/'cache-v1', tool_root=private/'tools-v1',
        work_root=private/'cache-v1/work', state_root=state, default_export_root=private/'exports',
        build_id='host-fixture', source_commit='a'*40, children=('frontend', 'api', 'windows-bootstrap'))
    monkeypatch.setattr(runtime_host, 'sys', SimpleNamespace(platform='win32', stdin=io.StringIO('normal\nstop\n')))
    monkeypatch.setattr(runtime_host, 'developer_environment', lambda: None)
    return value


@pytest.fixture
def owned(layout, monkeypatch):
    calls = []
    class Kernel:
        def OpenProcess(self, _access, _inherit, pid): return pid
        def IsProcessInJob(self, _handle, _job, result):
            result._obj.value = True
            return True
        def WaitForSingleObject(self, _handle, _timeout): return 258
        def CloseHandle(self, _handle): return True
    class Tree:
        kernel, handle = Kernel(), 123
        def command(self, command):
            calls.append(('wrap', command))
            return ['fixed-bootstrap', *command]
        def _process_ids(self, _deadline): return [101, 102, 103, 104]
        def terminate(self, timeout): calls.append('job-drain')
        def close(self): calls.append('job-close')
    class Process:
        def __init__(self, command, **options):
            self.role = 'frontend' if 'frontend' in command else 'api'
            self.code = None
            calls.append(('spawn', self.role, command, options))
        def poll(self): return self.code
        def kill(self):
            calls.append(('kill-bootstrap', self.role)); self.code = 1
        def wait(self, timeout):
            calls.append(('reap-bootstrap', self.role)); return self.code
    monkeypatch.setattr(runtime_host, 'WindowsPreparationProcess', Tree)
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: {3000: {102}, 8766: {104}})
    monkeypatch.setattr(runtime_host, 'subprocess', SimpleNamespace(Popen=Process,
        CREATE_NO_WINDOW=0, DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired))
    return runtime_host.FrozenProbeHost(layout), calls


def test_fixed_children_keep_bootstraps_and_job_until_real_drain(owned, layout):
    host, calls = owned
    host.start()
    assert host.members() == [101, 102, 103, 104]
    wrapped = [call[1] for call in calls if isinstance(call, tuple) and call[0] == 'wrap']
    assert wrapped == [layout.child_command('frontend', ['--port', '3000']),
        [str(layout.executable), '--runtime-probe', 'api']]
    for call in calls:
        if isinstance(call, tuple) and call[0] == 'spawn':
            options = call[3]
            assert options['cwd'].is_relative_to(layout.work_root)
            assert options['env']['PROXY_TRANSCRIPT_SETTINGS_ROOT'] == str(layout.settings_root)
    scratch = host.scratch
    host.close()
    assert calls[-6:] == [('kill-bootstrap', 'frontend'), ('reap-bootstrap', 'frontend'),
        ('kill-bootstrap', 'api'), ('reap-bootstrap', 'api'), 'job-drain', 'job-close']
    assert host.closed and host.tree is None and not scratch.exists()
    host.close()
    with pytest.raises(runtime_host.HostProbeFailure): host.start()


def test_partial_start_failure_still_reaps_bootstrap_and_job(owned, monkeypatch):
    host, calls = owned
    spawn = runtime_host.subprocess.Popen
    def fail_second(command, **options):
        if command[-1] == 'api': raise OSError('authored API spawn failure')
        return spawn(command, **options)
    monkeypatch.setattr(runtime_host.subprocess, 'Popen', fail_second)
    with pytest.raises(OSError): host.start()
    host.close()
    assert ('reap-bootstrap', 'frontend') in calls
    assert calls[-2:] == ['job-drain', 'job-close'] and host.closed


def test_failed_job_drain_retains_ownership_and_private_logs(owned, monkeypatch):
    host, calls = owned
    host.start()
    tree = host.tree
    def fail(**_): raise TimeoutError('authored unconfirmed native cleanup')
    monkeypatch.setattr(tree, 'terminate', fail)
    with pytest.raises(runtime_host.HostProbeFailure, match='owned-cleanup-unconfirmed'): host.close()
    assert host.tree is tree and not host.closed and host.scratch.exists()
    assert 'job-close' not in calls


def test_failed_native_job_close_keeps_host_unclosed_until_same_handle_retry(owned, monkeypatch):
    import ctypes
    from backend.windows_preparation_process import WindowsPreparationProcess
    host, calls = owned
    host.start()
    original = host.tree
    owner = WindowsPreparationProcess.__new__(WindowsPreparationProcess)
    owner.handle = object()
    exact_handle = owner.handle
    attempts = []
    def close(handle):
        attempts.append(handle)
        return len(attempts) > 1
    owner.kernel = SimpleNamespace(CloseHandle=close)
    owner.terminate = original.terminate
    host.tree = owner
    scratch = host.scratch
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 6, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda error: OSError(error, 'authored close failure'), raising=False)
    with pytest.raises(runtime_host.HostProbeFailure, match='owned-cleanup-unconfirmed'):
        host.close()
    assert host.tree is owner and owner.handle is exact_handle
    assert not host.closed and scratch.exists() and attempts == [exact_handle]
    host.close()
    assert host.closed and host.tree is None and owner.handle is None
    assert not scratch.exists() and attempts == [exact_handle, exact_handle]
    assert calls.count('job-drain') == 2


def test_exit_frontend_uses_retained_handle_and_monitor_stops_slot(owned):
    host, calls = owned
    host.start()
    try:
        with pytest.raises(runtime_host.HostProbeFailure, match='child-exited'):
            host.monitor(io.StringIO('exit-frontend\n'))
        assert calls.count(('kill-bootstrap', 'frontend')) == 1
    finally:
        host.close()
    assert ('reap-bootstrap', 'api') in calls and calls[-1] == 'job-close'


def test_readiness_refusal_cannot_be_replaced_by_a_live_process(owned, monkeypatch):
    host, _ = owned
    host.start()
    monkeypatch.setattr(host, '_json', lambda *_: {'ready': False})
    try:
        with pytest.raises(runtime_host.HostProbeFailure, match='readiness-deadline'):
            host.wait_services(timeout=.001)
        with pytest.raises(runtime_host.HostProbeFailure, match='unprepared-index-deadline'):
            host.wait_unprepared_index(timeout=.001)
    finally:
        host.close()


def test_existing_private_roots_and_experimental_image_are_required(layout, monkeypatch):
    (layout.state_root/'synthetic-probe.json').unlink()
    with pytest.raises(RuntimeError, match='synthetic roots'): runtime_host.FrozenProbeHost(layout)
    monkeypatch.setattr(runtime_host, 'sys', SimpleNamespace(platform='darwin'))
    with pytest.raises(runtime_host.HostProbeFailure, match='experimental-windows-image-required'):
        runtime_host.FrozenProbeHost(layout)


def test_frozen_entry_uses_fixed_host_probe_without_new_child_target(layout, monkeypatch):
    modules = []
    monkeypatch.setattr(bundle_entry, 'discover_layout', lambda: layout)
    def module(name):
        modules.append(name)
        return SimpleNamespace(main=lambda kind, current: 7 if kind == 'host' and current is layout else 99)
    monkeypatch.setattr(bundle_entry, 'import_module', module)
    assert bundle_entry.main(['--runtime-probe', 'host']) == 7
    assert modules == ['backend.runtime_host']
    assert 'host' not in bundle_entry.CHILD_TARGETS


def test_foreign_ready_listener_is_refused_while_own_bootstraps_are_alive(owned, monkeypatch):
    host, calls = owned
    host.start()
    def foreign(_handle, _job, result):
        result._obj.value = False
        return True
    monkeypatch.setattr(host.tree.kernel, 'IsProcessInJob', foreign)
    monkeypatch.setattr(host, '_json', lambda *_: pytest.fail('Foreign readiness must never be consulted'))
    try:
        assert all(process.poll() is None for process in host.processes.values())
        with pytest.raises(runtime_host.HostProbeFailure, match='foreign-canonical-listener'):
            host.wait_services(timeout=.01)
    finally:
        host.close()
    assert calls.count(('kill-bootstrap', 'frontend')) == 1
    assert calls.count(('kill-bootstrap', 'api')) == 1


def test_listener_identity_is_rechecked_before_readiness_is_accepted(owned, monkeypatch):
    host, _ = owned
    host.start()
    observations = iter([{3000: {102}, 8766: {104}}, {3000: {999}, 8766: {104}}])
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: next(observations))
    monkeypatch.setattr(host, '_json', lambda *_: {'ready': True})
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'x'
    monkeypatch.setattr(runtime_host, 'urlopen', lambda *_a, **_k: Response())
    try:
        with pytest.raises(runtime_host.HostProbeFailure, match='listener-ownership-changed'):
            host.wait_services(timeout=.01)
    finally:
        host.close()


def test_native_listener_table_uses_fixed_windows_rows_and_only_canonical_addresses(monkeypatch):
    import ctypes
    import socket
    import struct
    rows = [(2, 0x0100007f, socket.htons(3000), 0, 0, 102),
            (2, 0, socket.htons(8766), 0, 0, 104),
            (2, 0x0200007f, socket.htons(3000), 0, 0, 999),
            (2, 0x0100007f, socket.htons(8000), 0, 0, 998)]
    data = struct.pack('<I', len(rows)) + b''.join(struct.pack('<6I', *row) for row in rows)
    class Query:
        def __call__(self, buffer, size, _ordered, family, table, _reserved):
            assert family == 2 and table == 3
            size._obj.value = len(data)
            if buffer is None: return 122
            ctypes.memmove(buffer, data, len(data))
            return 0
    monkeypatch.setattr(runtime_host.ctypes, 'WinDLL', lambda *_a, **_k: SimpleNamespace(GetExtendedTcpTable=Query()), raising=False)
    assert ctypes.sizeof(runtime_host._TcpRow) == 24
    assert runtime_host.listener_processes() == {3000: {102}, 8766: {104}}


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell observer identity categories')
def test_observer_diagnostics_are_fixed_categories_and_do_not_weaken_identity(tmp_path):
    # Extract only the pure classifier. Do not execute the candidate probe,
    # create real processes, inspect the desktop or access an account.
    source = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-runtime.ps1'
    script = tmp_path/'observer-fixture.ps1'
    script.write_text(r'''param([string]$ProbeScript)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($ProbeScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Owned host probe PowerShell parsing failed.' }
$definition = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-HostObserverIdentityCategory'}, $true)
if (-not $definition) { throw 'Missing fixed host observer classifier.' }
. ([scriptblock]::Create($definition.Extent.Text))
$roleDefinition = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-HostObserverRole'}, $true)
if (-not $roleDefinition) { throw 'Missing fixed host observer role classifier.' }
. ([scriptblock]::Create($roleDefinition.Extent.Text))
$expected = 'C:\authored-runtime\ProxyTranscriptRuntime.exe'
$owner = [pscustomobject]@{StartTime=[DateTime]'2020-01-01T00:00:00Z'}
function New-Observer([string]$Image=$expected, [bool]$Exited=$false, [int]$Offset=1) {
    return [pscustomobject]@{HasExited=$Exited; StartTime=$owner.StartTime.AddSeconds($Offset); MainModule=[pscustomobject]@{FileName=$Image}}
}
function Assert-Category($Observer, [string]$ExpectedCategory) {
    $category = Get-HostObserverIdentityCategory $Observer $owner $expected
    $allowed = @('verified-runtime', 'process-exited', 'process-state-unavailable',
        'creation-time-unavailable', 'process-predates-owner', 'image-unavailable',
        'process-exited-during-identity', 'runtime-image-prefix-spelling-mismatch',
        'runtime-image-other-path', 'windows-console-host-image', 'unexpected-image')
    if ($category -ne $ExpectedCategory) {
        $safeActual = if ($category -in $allowed) {$category} else {'unrecognized-category'}
        $safeExpected = if ($ExpectedCategory -in $allowed) {$ExpectedCategory} else {'unrecognized-category'}
        [Console]::Out.WriteLine('host-observer-mismatch expected=' + $safeExpected + ' actual=' + $safeActual)
        [Console]::Out.Flush()
        throw 'Fixed host observer classification failed.'
    }
    if ($category -match 'PRIVATE|authored-runtime|secret-user|^[A-Z]:') { throw 'Observer diagnostics exposed fixture identity.' }
}
Assert-Category (New-Observer) 'verified-runtime'
Assert-Category (New-Observer -Exited $true) 'process-exited'
Assert-Category (New-Observer -Offset -1) 'process-predates-owner'
Assert-Category (New-Observer -Image '') 'image-unavailable'
Assert-Category (New-Observer -Image 'C:\Windows\System32\conhost.exe') 'windows-console-host-image'
Assert-Category (New-Observer -Image 'C:\other-runtime\ProxyTranscriptRuntime.exe') 'runtime-image-other-path'
Assert-Category (New-Observer -Image '\\?\C:\authored-runtime\ProxyTranscriptRuntime.exe') 'runtime-image-prefix-spelling-mismatch'
Assert-Category (New-Observer -Image 'C:\secret-user\private-program.exe') 'unexpected-image'
$unreadable = New-Observer
$unreadable | Add-Member -MemberType ScriptProperty -Name HasExited -Value {throw 'PRIVATE fixture state failure'} -Force
Assert-Category $unreadable 'process-state-unavailable'
$unreadable = New-Observer
$unreadable | Add-Member -MemberType ScriptProperty -Name StartTime -Value {throw 'PRIVATE fixture time failure'} -Force
Assert-Category $unreadable 'creation-time-unavailable'
$unreadable = New-Observer
$unreadable | Add-Member -MemberType ScriptProperty -Name MainModule -Value {throw 'PRIVATE fixture image failure'} -Force
Assert-Category $unreadable 'image-unavailable'
$script:exitReads = 0
$exiting = New-Observer
$exiting | Add-Member -MemberType ScriptProperty -Name HasExited -Value {$script:exitReads++; return $script:exitReads -ge 2} -Force
Assert-Category $exiting 'process-exited-during-identity'
function Assert-Role($Observer, [string]$ExpectedRole) {
    $role = Get-HostObserverRole $Observer $owner $expected 'C:\Windows\System32\conhost.exe'
    $allowed = @('runtime', 'windows-console-host', 'system-console-image-unverified',
        'process-exited', 'process-predates-owner', 'process-state-unavailable',
        'image-unavailable', 'unexpected-image')
    if ($role -ne $ExpectedRole) {
        $safeActual = if ($role -in $allowed) {$role} else {'unrecognized-category'}
        $safeExpected = if ($ExpectedRole -in $allowed) {$ExpectedRole} else {'unrecognized-category'}
        [Console]::Out.WriteLine('host-observer-mismatch expected=' + $safeExpected + ' actual=' + $safeActual)
        [Console]::Out.Flush()
        throw 'Fixed host observer role classification failed.'
    }
}
Assert-Role (New-Observer) 'runtime'
Assert-Role (New-Observer -Image 'C:\Windows\System32\conhost.exe') 'windows-console-host'
Assert-Role (New-Observer -Image 'C:\authored-cwd\conhost.exe') 'system-console-image-unverified'
Assert-Role (New-Observer -Image 'C:\Windows\System32\other.exe') 'unexpected-image'
Assert-Role (New-Observer -Image 'C:\Windows\System32\conhost.exe' -Exited $true) 'process-exited'
Assert-Role (New-Observer -Image 'C:\Windows\System32\conhost.exe' -Offset -1) 'process-predates-owner'
$unknownConsole = New-Observer -Image 'C:\Windows\System32\conhost.exe'
$unknownConsole.HasExited = $null
Assert-Role $unknownConsole 'process-state-unavailable'
Assert-Role (New-Observer -Image '') 'image-unavailable'
Write-Output 'host-observer-categories-passed'
''', encoding='utf-8')
    shell = shutil.which('pwsh')
    assert shell, 'Hosted Windows observer tests require the workflow PowerShell runtime'
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(script),
        '-ProbeScript', str(source)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        categories = {'verified-runtime', 'process-exited', 'process-state-unavailable',
            'creation-time-unavailable', 'process-predates-owner', 'image-unavailable',
            'process-exited-during-identity', 'runtime-image-prefix-spelling-mismatch',
            'runtime-image-other-path', 'windows-console-host-image', 'unexpected-image',
            'unrecognized-category', 'runtime', 'windows-console-host', 'system-console-image-unverified'}
        safe = 'no-safe-category-result'
        for line in result.stdout.splitlines():
            parts = line.split()
            if (len(parts) == 3 and parts[0] == 'host-observer-mismatch'
                    and parts[1].startswith('expected=') and parts[2].startswith('actual=')
                    and parts[1][9:] in categories and parts[2][7:] in categories):
                safe = ' '.join(parts[1:])
        pytest.fail('Fixed observer classifier failed: ' + safe, pytrace=False)
    if result.stdout.strip() != 'host-observer-categories-passed':
        pytest.fail('Observer classifier returned an unexpected control result', pytrace=False)
    if 'PRIVATE' in result.stderr or 'secret-user' in result.stderr:
        pytest.fail('Observer diagnostics exposed private fixture detail', pytrace=False)
