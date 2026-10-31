"""Authored PATH contracts; Windows cases use lookup only, never load a DLL."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'packaging/runtime-bundle'))
    # Load shared source guards before the pure fixture changes sys.platform.
    importlib.import_module('record_runtime')
    return importlib.import_module('build_environment')


@pytest.fixture
def authored(module, tmp_path, monkeypatch):
    root = tmp_path.resolve()
    prefix = root/'authored environment'; prefix.mkdir()
    scripts = prefix/'Scripts'; scripts.mkdir()
    executable = prefix/'python.exe'; executable.write_bytes(b'authored non-executable placeholder')
    base = root/'authored base 漢字🧪'; base.mkdir()
    windows = root/'authoritative Windows'; windows.mkdir()
    system = windows/'System32'; system.mkdir()
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'executable', str(executable))
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(sys, 'base_prefix', str(base))
    def query(selected=executable):
        return module.runtime_build_environment(selected,
            system_directory_provider=lambda: system, windows_directory_provider=lambda: windows)
    return SimpleNamespace(module=module, root=root, prefix=prefix, scripts=scripts, executable=executable,
        base=base, windows=windows, system=system, query=query)


def test_exact_roots_exclude_foreign_environment_and_do_not_mutate_it(authored, monkeypatch):
    case = authored
    foreign = case.root/'private-ambient'; foreign.mkdir()
    monkeypatch.setenv('PATH', str(foreign))
    monkeypatch.setenv('WINDIR', str(foreign)); monkeypatch.setenv('SystemRoot', str(foreign))
    before = dict(os.environ)
    value = case.query()
    assert value == {'schema': case.module.SCHEMA, 'path': ';'.join(map(str,
        (case.prefix, case.scripts, case.base, case.system, case.windows)))}
    assert str(foreign) not in value['path'] and dict(os.environ) == before
    # Functional directory lookup: an ambient same-name file cannot be selected
    # from the returned search set. No native file is opened or loaded.
    (foreign/'authored-foreign.dll').write_bytes(b'authored foreign bytes')
    matches = [Path(root)/'authored-foreign.dll' for root in value['path'].split(';')
        if (Path(root)/'authored-foreign.dll').is_file()]
    assert matches == [] and (foreign/'authored-foreign.dll').is_file()


def test_matching_base_prefix_is_deduplicated_without_another_python_fallback(authored, monkeypatch):
    monkeypatch.setattr(sys, 'base_prefix', str(authored.prefix))
    assert authored.query()['path'].split(';') == list(map(str,
        (authored.prefix, authored.scripts, authored.system, authored.windows)))


@pytest.mark.parametrize('change', ['missing-scripts', 'missing-base', 'missing-system', 'inconsistent-windows',
    'different-python', 'outside-prefix', 'relative', 'separator', 'oversized', 'provider-failure'])
def test_unavailable_noncanonical_or_unselected_roots_refuse_without_environment_fallback(authored, monkeypatch, change):
    case = authored; selected = case.executable
    if change == 'missing-scripts': case.scripts.rmdir()
    elif change == 'missing-base': case.base.rmdir()
    elif change == 'missing-system': case.system.rmdir()
    elif change == 'inconsistent-windows':
        other = case.root/'other Windows'; other.mkdir(); case.windows = other
    elif change == 'different-python':
        selected = case.prefix/'other-python.exe'; selected.write_bytes(b'authored different executable')
    elif change == 'outside-prefix':
        selected = case.root/'outside-python.exe'; selected.write_bytes(b'authored outside executable')
        monkeypatch.setattr(sys, 'executable', str(selected))
    elif change == 'relative': selected = Path('python.exe')
    elif change == 'separator': selected = str(case.executable)+';private-bait'
    elif change == 'oversized': selected = '/'+'x'*case.module.MAX_PATH_UNITS
    def system():
        if change == 'provider-failure': raise OSError('private-provider-sentinel '+str(case.root))
        return case.system
    monkeypatch.setenv('PATH', str(case.prefix)); monkeypatch.setenv('WINDIR', str(case.windows))
    before = dict(os.environ)
    with pytest.raises(case.module.BuildEnvironmentError) as error:
        case.module.runtime_build_environment(selected, system_directory_provider=system,
            windows_directory_provider=lambda: case.windows)
    assert str(error.value) == 'Experimental build PATH query refused.' and dict(os.environ) == before


def test_linked_root_is_refused_before_following_its_native_leaf(authored, monkeypatch):
    case = authored
    link = case.root/'private-linked-environment'
    try: link.symlink_to(case.prefix, target_is_directory=True)
    except OSError:
        assert os.name == 'nt', 'This authored link must be creatable or fail explicitly on this host'
        cmd = shutil.which('cmd.exe'); assert cmd
        result = subprocess.run([cmd, '/d', '/c', 'mklink', '/J', str(link), str(case.prefix)],
            capture_output=True, timeout=10)
        assert result.returncode == 0, 'Windows link/junction fixture must be available'
    selected = link/'python.exe'
    monkeypatch.setattr(sys, 'executable', str(selected)); monkeypatch.setattr(sys, 'prefix', str(link))
    seen = []
    actual = os.lstat
    def guarded(path, *args, **kwargs):
        if os.path.normcase(os.fspath(path)) == os.path.normcase(str(selected)):
            seen.append(True); pytest.fail('Linked root must be refused before native leaf metadata')
        return actual(path, *args, **kwargs)
    monkeypatch.setattr(os, 'lstat', guarded)
    with pytest.raises(case.module.BuildEnvironmentError): case.query(selected)
    assert seen == []


def test_utf16_combined_path_bound_is_exact_and_refuses_overflow(authored, monkeypatch):
    case = authored
    path = case.query()['path']
    units = len(path.encode('utf-16-le'))//2
    assert units > len(path), 'The authored astral character must exercise UTF-16 counting'
    monkeypatch.setattr(case.module, 'MAX_PATH_UNITS', units)
    assert case.query()['path'] == path
    monkeypatch.setattr(case.module, 'MAX_PATH_UNITS', units-1)
    with pytest.raises(case.module.BuildEnvironmentError): case.query()


def test_wrong_platform_refuses_without_querying_windows(module, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    with pytest.raises(module.BuildEnvironmentError):
        module.runtime_build_environment(tmp_path/'private-python',
            system_directory_provider=lambda: pytest.fail('Unsupported platform cannot query a root'))


def test_private_query_failure_emits_no_raw_selected_path_or_environment(tmp_path):
    sentinel = tmp_path/'private-selected-path-sentinel.exe'
    before = dict(os.environ)
    result = subprocess.run([sys.executable, '-B', str(ROOT/'packaging/runtime-bundle/build_environment.py'),
        '--selected-python', str(sentinel)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and result.stdout == ''
    assert result.stderr.strip() == 'Experimental build PATH query refused.'
    assert str(sentinel) not in result.stderr and dict(os.environ) == before


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows PyInstaller lookup/OS roots are unavailable on this host.')
def test_windows_actual_selected_python_query_and_pyinstaller_lookup_exclude_foreign_path(module, tmp_path):
    from backend.tests.test_native_images import authored_pe
    foreign = tmp_path/'private ambient'; foreign.mkdir()
    name = 'r19_authored_foreign_lookup.dll'
    (foreign/name).write_bytes(authored_pe())  # Header inspection only; never load this file.
    query = subprocess.run([sys.executable, '-B', str(ROOT/'packaging/runtime-bundle/build_environment.py'),
        '--selected-python', sys.executable], capture_output=True, text=True, timeout=30)
    assert query.returncode == 0, 'Selected Windows Python must produce the bounded private query'
    value = json.loads(query.stdout)
    assert set(value) == {'schema', 'path'} and value['schema'] == module.SCHEMA
    script = ('import json,sys;from PyInstaller.depend.bindepend import resolve_library_path;'
        'print(json.dumps({"resolved":resolve_library_path(sys.argv[1]) is not None}))')
    before = dict(os.environ)
    for search_path, expected in ((str(foreign)+';'+os.environ.get('PATH', ''), True), (value['path'], False)):
        env = dict(os.environ); env['PATH'] = search_path
        probe = subprocess.run([sys.executable, '-B', '-c', script, name], env=env,
            capture_output=True, text=True, timeout=30)
        assert probe.returncode == 0, 'Exact installed PyInstaller must execute the authored lookup contract'
        assert json.loads(probe.stdout) == {'resolved': expected}
    assert dict(os.environ) == before


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual PowerShell child PATH/restore contract requires Windows.')
@pytest.mark.parametrize('parent_state', ['populated', 'empty', 'absent'])
@pytest.mark.parametrize('child_exit', [0, 17])
def test_windows_actual_freezer_function_restores_parent_path_after_child_result(module, tmp_path, parent_state, child_exit):
    pwsh = shutil.which('pwsh'); assert pwsh, 'Hosted Windows contract requires PowerShell'
    selected = tmp_path/'authored-selected.cmd'
    selected.write_text('@echo off\nif "%~2"=="private-query" goto query\n'
        'if not "%~2"=="-m" exit /b 91\n'
        '"%R19_REAL_PYTHON%" -B -c "import os,pathlib;pathlib.Path(os.environ[\'R19_CAPTURE\']).write_text(os.environ[\'PATH\'],encoding=\'utf-8\')"\n'
        'if errorlevel 1 exit /b 92\nexit /b %R19_CHILD_EXIT%\n:query\n'
        '"%R19_REAL_PYTHON%" -B -c "import os;print(os.environ[\'R19_QUERY_JSON\'])"\n', encoding='ascii')
    capture = tmp_path/'private-child-path.txt'
    permitted = tmp_path/'authored permitted'; permitted.mkdir()
    env = dict(os.environ)
    env.update(R19_SOURCE_SCRIPT=str(ROOT/'scripts/build-runtime-bundle.ps1'), R19_SELECTED=str(selected),
        R19_REAL_PYTHON=sys.executable, R19_CAPTURE=str(capture), R19_CHILD_EXIT=str(child_exit),
        R19_PARENT_STATE=parent_state, R19_QUERY_JSON=json.dumps({'schema': module.SCHEMA, 'path': str(permitted)}))
    contract = r'''
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:R19_SOURCE_SCRIPT, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Actual freezer script parse failed.' }
$definition = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-RuntimeExperimentFreezer'
}, $true)
if ($null -eq $definition) { throw 'Actual freezer function unavailable.' }
Invoke-Expression $definition.Extent.Text
if ($env:R19_PARENT_STATE -eq 'absent') { Remove-Item Env:PATH -ErrorAction SilentlyContinue }
elseif ($env:R19_PARENT_STATE -eq 'empty') { $env:PATH = '' }
else { $env:PATH = 'PRIVATE_AMBIENT_SENTINEL;'+$env:PATH }
$beforePresent = Test-Path Env:PATH
$beforeValue = $env:PATH
if ($env:R19_PARENT_STATE -eq 'empty' -and (-not $beforePresent -or $beforeValue -cne '')) { throw 'Empty parent PATH fixture unavailable.' }
$failed = $false
try { Invoke-RuntimeExperimentFreezer -SelectedPython $env:R19_SELECTED -EnvironmentHelper private-query -FreezerArguments @('--noconfirm') }
catch { $failed = $true }
if ($failed -ne ([int]$env:R19_CHILD_EXIT -ne 0)) { throw 'Unexpected child result.' }
if ((Test-Path Env:PATH) -ne $beforePresent -or $env:PATH -cne $beforeValue) { throw 'Parent PATH was not exactly restored.' }
'fixed-freezer-contract-passed'
'''
    result = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-Command', contract], env=env,
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == 'fixed-freezer-contract-passed', 'Actual freezer restoration contract failed'
    assert capture.read_text(encoding='utf-8') == str(permitted)
