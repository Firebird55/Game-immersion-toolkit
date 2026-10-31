"""Authored trust/publication fixtures; not actual FFmpeg/Windows acceptance."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('game_codec_replay', ROOT / 'scripts/replay-game-codec.py')
replay = importlib.util.module_from_spec(spec); spec.loader.exec_module(replay)


class ReplayTrustTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.inputs = self.root / 'inputs'; self.inputs.mkdir()
        self.project = self.root / 'project'; self.project.mkdir()
        for name in replay.PROJECT_INPUTS:
            path = self.project / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('authored project fixture')

    def fixture(self, extra=None, source_bytes=b'authored source', notice=b'original authored notice'):
        archive = self.inputs / 'owned.tar.xz'
        with tarfile.open(archive, 'w:xz') as tar:
            for name, raw in [('owned-1/COPYING', notice), ('owned-1/own.c', source_bytes)]:
                entry = tarfile.TarInfo(name); entry.size = len(raw); tar.addfile(entry, io.BytesIO(raw))
            if extra: tar.addfile(extra)
        options = b'# Original authored options\n--disable-everything\n--enable-libopus\n'
        (self.inputs / 'vgmstream-ffmpeg_options.txt').write_bytes(options)
        pin = {'sources': [{'component': 'owned', 'root': 'owned-1', 'filename': archive.name,
                           'sha256': replay.digest(archive.read_bytes())}],
            'original_recipes': [{'filename': 'vgmstream-ffmpeg_options.txt', 'path': 'options',
                                  'download': 'https://example.invalid/original', 'sha256': replay.digest(options)}],
            'notices': [{'component': 'owned', 'path': 'COPYING', 'sha256': replay.digest(b'original authored notice')}],
            'build_tools': [], 'adaptations': ['authored fixture only'], 'licensing_boundary': {'approved': False}}
        return pin

    def prepare(self, pin, output):
        with patch.object(replay, 'policy', return_value=pin), patch.object(replay, 'ROOT', self.project):
            replay.prepare(self.inputs, output)

    def test_exact_originals_and_notices_retained_without_binary_or_source_approval(self):
        pin = self.fixture(); output = self.root / 'experiment'; self.prepare(pin, output)
        self.assertEqual((output / 'upstream/owned-1/own.c').read_bytes(), b'authored source')
        self.assertEqual((output / 'source-review/original-inputs/owned.tar.xz').read_bytes(),
                         (self.inputs / 'owned.tar.xz').read_bytes())
        boundary = json.loads((output / 'source-review/BOUNDARY.json').read_text())
        self.assertFalse(boundary['source_delivery_approved']); self.assertFalse(boundary['runtime_collection_allowed'])
        self.assertEqual(json.loads((output / 'ORIGINAL-OPTIONS.json').read_text()),
                         ['--disable-everything', '--enable-libopus'])
        replay.verify_sources(output)
        (output / 'upstream/owned-1/own.c').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed the original'): replay.verify_sources(output)

    def test_changed_input_notice_or_existing_output_never_overwritten(self):
        for changed in ('hash', 'notice', 'existing'):
            with self.subTest(changed=changed):
                pin = self.fixture(notice=b'damaged' if changed == 'notice' else b'original authored notice')
                output = self.root / ('experiment-' + changed)
                if changed == 'hash': (self.inputs / 'owned.tar.xz').write_bytes(b'wrong')
                if changed == 'existing': output.mkdir(); (output / 'prior').write_bytes(b'preserved')
                with self.assertRaises(ValueError): self.prepare(pin, output)
                if changed == 'existing': self.assertEqual((output / 'prior').read_bytes(), b'preserved')
                else: self.assertFalse(output.exists())

    def test_links_traversal_native_aliases_and_devices_reject_before_output(self):
        for kind in ('traversal', 'symlink', 'hardlink', 'alias', 'native', 'device'):
            with self.subTest(kind=kind):
                entry = tarfile.TarInfo({'traversal': '../outside', 'alias': 'owned-1/copying',
                    'native': 'owned-1/prebuilt.dll'}.get(kind, 'owned-1/other'))
                if kind in ('symlink', 'hardlink'):
                    entry.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                    entry.linkname = '../../outside'
                if kind == 'device': entry.type = tarfile.CHRTYPE
                pin = self.fixture(extra=entry); output = self.root / ('experiment-' + kind)
                with self.assertRaises(ValueError): self.prepare(pin, output)
                self.assertFalse(output.exists())

    def test_no_unreviewed_licensing_or_protocol_configuration_changes(self):
        output = self.root / 'experiment'; self.prepare(self.fixture(), output)
        exact = '--disable-everything --enable-libopus --target-os=win64 --toolchain=msvc --arch=x86_64 --prefix=/c/r19-game-codec-replay/out/ffmpeg-vs-64'
        replay.validate_configuration(output, exact)
        for change in (' --enable-gpl', ' --enable-protocol=file', ' --enable-ffmpeg', ' --enable-version3'):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay.validate_configuration(output, exact + change)
        with self.assertRaises(ValueError): replay.original_options(b'--enable-libopus\n--enable-gpl')
        with self.assertRaises(ValueError): replay.original_options(b'--enable-libopus; touch injected')

    def test_decode_failure_partial_pcm_and_deadline_retain_previous_output_and_cleanup(self):
        output = self.root / 'complete.pcm'; output.write_bytes(b'previous')
        def failed(pending): pending.write_bytes(b'partial'); return SimpleNamespace(returncode=1)
        def wrong(pending): pending.write_bytes(b'partial'); return SimpleNamespace(returncode=0)
        def timeout(pending):
            pending.write_bytes(b'partial')
            raise replay.subprocess.TimeoutExpired('authored-child', 1)
        for run, exception in ((failed, ValueError), (wrong, ValueError), (timeout, replay.subprocess.TimeoutExpired)):
            with self.subTest(run=run.__name__), self.assertRaises(exception):
                replay.publish_attempt(run, self.root, output, b'complete')
            self.assertEqual(output.read_bytes(), b'previous')
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['complete.pcm', 'inputs', 'project'])
        def success(pending): pending.write_bytes(b'complete'); return SimpleNamespace(returncode=0)
        replay.publish_attempt(success, self.root, output, b'complete')
        self.assertEqual(output.read_bytes(), b'complete')

    def test_module_observation_rejects_foreign_and_ambiguous_paths_without_leaking_them(self):
        candidate = self.root / 'candidate'; candidate.mkdir()
        lines = []
        for name in replay.DLLS:
            (candidate / name).write_bytes(b'owned DLL fixture')
            lines.append('module\t' + name + '\t' + str(candidate / name))
        result = replay.sanitized_modules(lines, candidate)
        self.assertEqual(set(result), set(replay.DLLS))
        self.assertNotIn(str(self.root), json.dumps(result))
        for bad in (lines[:-1], lines + lines[:1], [lines[0].replace(str(candidate), str(self.root / 'private-profile'))] + lines[1:]):
            with self.assertRaises(ValueError) as error: replay.sanitized_modules(bad, candidate)
            self.assertNotIn(str(self.root), str(error.exception))

    def test_authored_pe_normal_and_delay_imports_and_malformed_inputs(self):
        raw = bytearray(2048); raw[:2] = b'MZ'; struct.pack_into('<I', raw, 60, 128)
        raw[128:132] = b'PE\0\0'; struct.pack_into('<HH', raw, 132, 0x8664, 1)
        struct.pack_into('<H', raw, 148, 240); struct.pack_into('<H', raw, 152, 0x20b)
        struct.pack_into('<IIII', raw, 152+240+8, 1024, 4096, 1024, 512)
        struct.pack_into('<II', raw, 152+112+8, 4096, 40)
        struct.pack_into('<II', raw, 152+112+13*8, 4160, 64)
        struct.pack_into('<IIIII', raw, 512, 1, 0, 0, 4296, 0)
        struct.pack_into('<IIIIIIII', raw, 576, 1, 4328, 0, 0, 0, 0, 0, 0)
        raw[712:725] = b'KERNEL32.dll\0'; raw[744:756] = b'fixture.dll\0'
        self.assertEqual(replay.pe_imports(bytes(raw)), {'imports': ['KERNEL32.dll'], 'delay_imports': ['fixture.dll']})
        for damaged in (b'not PE', bytes(raw[:520]), bytes(raw[:152])+b'\0\0'+bytes(raw[154:])):
            with self.assertRaises(ValueError): replay.pe_imports(damaged)

    def test_failure_receipt_exposes_only_allowlisted_codes_categories_and_numeric_exit(self):
        log = self.root / 'private.log'
        private = str(self.root / 'private-user' / 'credentials-fixture')
        log.write_text(private + '\nauthored-secret-never-publish\ncompiler command --private-argument\n'
            'own.c(5): fatal error C1083: private include file ' + private + '\n'
            'LINK : error LNK2019: private symbol\nproject : error MSB8020: private toolset\n'
            'error C9999: unapproved numeric token\nwarning C2065: non-error warning\n'
            'CMake Error at ' + private + '\nCould not find a package configuration file provided by private package\n')
        with patch.dict(replay.os.environ, {'GITHUB_SHA': 'a'*40}):
            report = replay.failure(self.root, 'build-opus', -1073741515, log, 0)
        self.assertEqual(report['exit_code'], -1073741515)
        self.assertEqual(report['diagnostic_codes'], ['C1083', 'LNK2019', 'MSB8020'])
        self.assertEqual(report['diagnostic_categories'], ['cmake-error', 'cmake-package-discovery',
                         'compiler-error', 'linker-error', 'msbuild-error'])
        serialized = json.dumps(report)
        for marker in (private, str(self.root), 'authored-secret', '--private-argument', 'C9999', 'C2065'):
            self.assertNotIn(marker, serialized)
        self.assertEqual(json.loads((self.root / 'FAILED-STAGE.json').read_text()), report)
        self.assertEqual(report['status'], 'failed'); self.assertFalse(report['r19_complete'])
        self.assertFalse(report['runtime_collection_allowed']); self.assertFalse(report['source_delivery_approved'])
        self.assertFalse(report['production_execution_allowed']); self.assertFalse(report['raw_log_published'])
        self.assertFalse((self.root / 'REPLAY-RECEIPT.json').exists())

    def test_failure_diagnosis_excludes_prior_successful_command_and_bounds_private_log(self):
        log = self.root / 'private.log'
        earlier = b'CMake Error at earlier private path\nfatal error C1083: earlier successful try-compile\n'
        log.write_bytes(earlier + b'error lnk2019: current private symbol\n')
        report = replay.failure(self.root, 'compile-probe', 1, log, len(earlier))
        self.assertEqual(report['diagnostic_codes'], ['LNK2019'])
        self.assertEqual(report['diagnostic_categories'], ['linker-error'])
        self.assertFalse(report['log_truncated'])
        log.write_bytes(earlier + b'private padding\n'*100 + b'error C2143: current private symbol\n')
        with patch.object(replay, 'FAILURE_LOG_LIMIT', 100):
            report = replay.failure(self.root, 'compile-probe', 2, log, len(earlier))
        self.assertTrue(report['log_truncated'])
        self.assertEqual(report['diagnostic_codes'], ['C2143'])
        self.assertEqual(report['diagnostic_categories'], ['compiler-error'])

    def test_unknown_failure_is_fixed_category_and_invalid_stage_or_exit_never_writes(self):
        log = self.root / 'private.log'; log.write_text(
            'private-secret-marker error C9999: unknown code\ncould NOT find private-tool-without-CMake-error\n')
        with patch.dict(replay.os.environ, {'GITHUB_SHA': 'private-invalid-commit'}):
            report = replay.failure(self.root, 'check-shell', 4294967295, log, 0)
        self.assertIsNone(report['source_commit']); self.assertEqual(report['exit_code'], 4294967295)
        self.assertEqual(report['diagnostic_codes'], [])
        self.assertEqual(report['diagnostic_categories'], ['unclassified-command-failure'])
        (self.root / 'FAILED-STAGE.json').unlink()
        for phase, code, offset in [('private-phase', 1, 0), ('build-opus', 0, 0),
                ('build-opus', True, 0), ('build-opus', 2**32, 0), ('build-opus', 1, -1),
                ('build-opus', 1, 10000)]:
            with self.subTest(phase=phase, code=code, offset=offset), self.assertRaises(ValueError):
                replay.failure(self.root, phase, code, log, offset)
            self.assertFalse((self.root / 'FAILED-STAGE.json').exists())
        self.assertFalse((self.root / 'REPLAY-RECEIPT.json').exists())

    def test_preflight_mismatch_binds_numeric_resources_source_manifest_and_both_tool_bytes(self):
        output = self.root / 'preflight'; observed = {
            'cmake': {'version': '4.4.4', 'bytes': 1234567, 'sha256': 'a'*64},
            'cl': {'file_version': '14.51.36260.0', 'product_version': '19.51.36260.0',
                   'bytes': 987654, 'sha256': 'b'*64}}
        with patch.dict(replay.os.environ, {'GITHUB_SHA': 'c'*40}):
            report = replay.preflight_failure(output, observed)
        self.assertEqual(report['schema'], 'proxy-r19-game-codec-replay-preflight-failure-v1')
        self.assertEqual(report['status'], 'failed'); self.assertEqual(report['phase'], 'preflight-tool-version')
        self.assertEqual(report['source_commit'], 'c'*40)
        self.assertEqual(report['input_manifest']['sha256'], replay.digest(replay.PIN.read_bytes()))
        self.assertEqual(report['input_manifest']['bytes'], len(replay.PIN.read_bytes()))
        self.assertEqual(report['expected_versions'], {'cmake': '4.4.5', 'compiler': '19.51.36260.0'})
        self.assertEqual(report['observed_tools'], observed)
        self.assertEqual(report['mismatch_fields'], ['cmake-version', 'cl-file-resource-version'])
        self.assertNotIn(str(self.root), json.dumps(report))
        for gate in ('raw_log_published', 'native_codec_built', 'native_codec_executed', 'runtime_collection_allowed',
                     'production_execution_allowed', 'source_delivery_approved', 'r19_complete'):
            self.assertFalse(report[gate])
        self.assertEqual(json.loads((output / 'FAILED-STAGE.json').read_text()), report)
        self.assertEqual(sorted(p.name for p in output.iterdir()), ['FAILED-STAGE.json'])

    def test_preflight_never_overwrites_or_creates_output_without_numeric_source_bound_mismatch(self):
        base = {'cmake': {'version': '4.4.5', 'bytes': 100, 'sha256': 'a'*64},
                'cl': {'file_version': '19.51.36260.0', 'product_version': '14.51.36260.0',
                       'bytes': 200, 'sha256': 'b'*64}}
        for case in ('matching', 'raw-version', 'raw-product-version', 'extra-path', 'boolean-bytes', 'bad-hash', 'invalid-source'):
            with self.subTest(case=case):
                observed = json.loads(json.dumps(base)); output = self.root / case
                if case != 'matching': observed['cmake']['version'] = '4.4.4'
                if case == 'raw-version': observed['cmake']['version'] = '4.4.4 private-marker'
                if case == 'raw-product-version': observed['cl']['product_version'] = 'private-marker'
                if case == 'extra-path': observed['cmake']['path'] = 'private-marker'
                if case == 'boolean-bytes': observed['cl']['bytes'] = True
                if case == 'bad-hash': observed['cl']['sha256'] = 'private-marker'
                with patch.dict(replay.os.environ, {'GITHUB_SHA': 'private-marker' if case == 'invalid-source' else 'c'*40}), self.assertRaises(ValueError):
                    replay.preflight_failure(output, observed)
                self.assertFalse(output.exists())
        output = self.root / 'existing'; output.mkdir(); (output / 'prior').write_bytes(b'preserved')
        with self.assertRaises(ValueError): replay.preflight_failure(output, base)
        self.assertEqual((output / 'prior').read_bytes(), b'preserved')
        self.assertFalse((output / 'FAILED-STAGE.json').exists())

    def test_preflight_native_data_reader_rejects_duplicate_keys_and_oversized_input(self):
        self.assertEqual(replay.read_preflight_observation(io.BytesIO(b'{"cmake": {}, "cl": {}}')),
                         {'cmake': {}, 'cl': {}})
        for raw in (b'{"cmake": {}, "cmake": {}}', b' '*8193):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                replay.read_preflight_observation(io.BytesIO(raw))

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell path-selection contract requires pwsh')
    def test_explicit_tool_selection_ignores_competing_path_matches_and_rejects_ambient_python(self):
        pinned_root = self.root / 'pinned-cmake'
        canonical = pinned_root / 'cmake-4.4.5-windows-x86_64/bin/cmake.exe'
        selected_python = self.root / 'selected-python/python.exe'
        for path in (canonical, selected_python, self.root / 'competing/cmake.exe',
                     self.root / 'competing/python.exe'):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'authored non-executed tool fixture')
        contract = self.root / 'selection-contract.ps1'
        contract.write_text('''param($SourcePath, $PinnedCMakeRoot, $SelectedPython, $ExpectedCMake)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Build script has parse errors.' }
$definition = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-ReplayExecutables'}, $true)
if (-not $definition) { throw 'Explicit executable selector is unavailable.' }
. ([ScriptBlock]::Create($definition.Extent.Text))
function Get-Command { throw 'Ambient tool discovery must never execute.' }
$value = Get-ReplayExecutables -PinnedCMakeRoot $PinnedCMakeRoot -PythonPath $SelectedPython
if ($value.CMake -ne $ExpectedCMake -or $value.Python -ne $SelectedPython -or
    $value.CMake -isnot [string] -or $value.Python -isnot [string]) { throw 'Explicit tool selection differed.' }
foreach ($bad in @('python', 'relative/python.exe', (Join-Path $PinnedCMakeRoot 'missing.exe'), $PinnedCMakeRoot)) {
    $rejected = $false
    try { Get-ReplayExecutables -PinnedCMakeRoot $PinnedCMakeRoot -PythonPath $bad | Out-Null }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Invalid explicit Python path was accepted.' }
}
$value | ConvertTo-Json -Compress
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1'), str(pinned_root),
            str(selected_python), str(canonical)], check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout), {'CMake': str(canonical), 'Python': str(selected_python)})

    @unittest.skipUnless(shutil.which('pwsh') and shutil.which('cmd.exe'),
                         'Compiler activation quoting contract requires Windows pwsh/cmd')
    def test_compiler_activation_handles_spaced_batch_paths_and_never_exports_failed_or_foreign_values(self):
        tools = self.root / 'authored VC tools with spaces'; tools.mkdir()
        success = tools / 'vcvarsall.bat'
        success.write_text('''@echo off
if not "%~1"=="x64" exit /b 61
if not "%~2"=="10.0.26100.0" exit /b 62
if not "%~3"=="-vcvars_ver=14.51.36231" exit /b 63
set "INCLUDE=authored include"
set "LIB=authored lib"
set "VCToolsInstallDir=authored toolset"
set "WindowsSdkDir=authored SDK"
set "WindowsSDKVersion=10.0.26100.0"
set "FOREIGN_PRIVATE_FIXTURE=private-stdout-marker"
exit /b 0
''', encoding='utf-8')
        failed = tools / 'failing vcvarsall.bat'
        failed.write_text('@echo off\nset "INCLUDE=partial value"\necho private-stdout-marker\nexit /b 7\n', encoding='utf-8')
        contract = self.root / 'activation-contract.ps1'
        contract.write_text('''param($SourcePath, $SuccessBatch, $FailedBatch, $ProfileParent)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Build script has parse errors.' }
$definition = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-CompilerEnvironment'}, $true)
if (-not $definition) { throw 'Compiler environment activation function unavailable.' }
. ([ScriptBlock]::Create($definition.Extent.Text))
$beforeInclude = $env:INCLUDE
$profile = Join-Path $ProfileParent 'profile with spaces'
$failedProfile = Join-Path $ProfileParent 'failed profile with spaces'
New-Item -ItemType Directory -Path $profile, $failedProfile | Out-Null
$value = Get-CompilerEnvironment -ActivationRoot $profile -VcvarsPath $SuccessBatch -SdkVersion '10.0.26100.0' -ToolsetVersion '14.51.36231'
if ($value.Count -ne 5 -or $value.INCLUDE -ne 'authored include' -or $value.LIB -ne 'authored lib' -or
    $value.VCToolsInstallDir -ne 'authored toolset' -or $value.WindowsSdkDir -ne 'authored SDK' -or
    $value.WindowsSDKVersion -ne '10.0.26100.0') { throw 'Authored activation arguments or allowlist differed.' }
$failedAsExpected = $false
try { Get-CompilerEnvironment -ActivationRoot $failedProfile -VcvarsPath $FailedBatch -SdkVersion '10.0.26100.0' -ToolsetVersion '14.51.36231' | Out-Null }
catch { if ($_.Exception.Message -eq 'Exact compiler/SDK activation failed; exit code 7.') { $failedAsExpected = $true } }
if (-not $failedAsExpected -or $env:INCLUDE -ne $beforeInclude) { throw 'Failed activation exported partial environment.' }
$value | ConvertTo-Json -Compress
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1'), str(success), str(failed), str(self.root)],
            check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout), {'INCLUDE': 'authored include', 'LIB': 'authored lib',
            'VCToolsInstallDir': 'authored toolset', 'WindowsSdkDir': 'authored SDK', 'WindowsSDKVersion': '10.0.26100.0'})
        self.assertNotIn('private-stdout-marker', result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
