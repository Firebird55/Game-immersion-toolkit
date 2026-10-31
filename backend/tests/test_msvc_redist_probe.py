"""Authored metadata/query fixtures; no actual VS/CRT source acceptance."""
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path, PureWindowsPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load():
    path = Path(__file__).resolve().parents[2] / 'scripts/probe-msvc-redist.py'
    spec = importlib.util.spec_from_file_location('msvc_redist_census_fixture', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class CensusTests(unittest.TestCase):
    def setUp(self):
        self.module = load()
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve(); self.selected = self.base / 'PRIVATE-VS'; self.selected.mkdir()
        self.program = self.base / 'PRIVATE-program-files'; self.utility = self.program / 'Microsoft Visual Studio/Installer/vswhere.exe'
        self.utility.parent.mkdir(parents=True); self.utility.write_bytes(b'owned query fixture only')
        self.version = '18.11.12315.225'; self.source = 'a' * 40
        self.family('14.51.36231')

    def family(self, version, family='Microsoft.VC145.CRT'):
        root = self.selected / 'VC/Redist/MSVC' / version / 'x64' / family; root.mkdir(parents=True, exist_ok=True)
        for name in self.module.FILES: (root / name).write_bytes(b'PRIVATE candidate bytes never read')
        return root

    def query(self, *_args):
        return {'version': self.version, 'edition': 'build-tools', 'release_state': 'release'}

    def observe(self, **changes):
        arguments = {'selected_vs_root': self.selected, 'selected_vs_version': self.version,
            'vswhere': self.utility, 'source_commit': self.source, 'observation_id': 'authored-census',
            'program_files_provider': lambda: self.program, 'query': self.query}
        arguments.update(changes)
        return self.module.observe(**arguments)

    def unavailable(self, result, reason):
        self.assertEqual(result['schema'], 'proxy-r19-msvc-redist-census-v2')
        self.assertEqual((result['status'], result['reason']), ('unavailable', reason))
        self.assertEqual(result['versions'], []); self.assertFalse(result['metadata_snapshot_stable'])
        self.assertEqual((result['version_count'], result['family_count'], result['file_count']), (0, 0, 0))
        if reason == 'unknown-version-entry':
            self.assertIn(result['version_entry_refusal'], {'exact-v14-token', 'other-noncanonical-name', 'both'})
        else:
            self.assertIsNone(result['version_entry_refusal'])
        for key in ('source_delivery_approved', 'runtime_collection_allowed', 'production_execution_allowed',
                    'redistribution_approved', 'production_activation',
                    'r19_complete', 'vendor_file_content_read', 'vendor_file_hashes_observed',
                    'vendor_file_versions_observed', 'vendor_signatures_observed'):
            self.assertIs(result[key], False)
        self.assertNotIn('PRIVATE', json.dumps(result)); self.assertNotIn(str(self.base), json.dumps(result))

    def test_complete_census_lists_every_version_and_family_without_selecting_or_reading_vendor_content(self):
        self.family('14.50.1', 'Microsoft.VC143.CRT'); self.family('14.51.36231', 'Microsoft.VC144.CRT')
        original = Path.open
        def refuse_vendor(path, *args, **kwargs):
            if self.selected in path.parents: self.fail('Candidate CRT content must never be opened.')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', refuse_vendor): result = self.observe()
        self.assertEqual(result['schema'], 'proxy-r19-msvc-redist-census-v2')
        self.assertIsNone(result['version_entry_refusal'])
        self.assertEqual(result['status'], 'observed-not-approved'); self.assertEqual(result['selection'], 'none')
        self.assertEqual((result['version_count'], result['family_count'], result['file_count']), (2, 3, 12))
        self.assertEqual([x['version'] for x in result['versions']], ['14.50.1', '14.51.36231'])
        self.assertEqual({f['role'] for v in result['versions'] for f in v['families']}, {'vc143-crt', 'vc144-crt', 'vc145-crt'})
        self.assertEqual(result['source_binding'], 'unverified-caller-label'); self.assertEqual(result['source_commit_label'], self.source)
        self.assertEqual(result['entitlement_probe'], 'not-performed'); self.assertFalse(result['r19_complete'])
        self.assertEqual(result['license_eligibility'], 'unverified'); self.assertFalse(result['redistribution_approved'])
        self.assertNotIn('PRIVATE', json.dumps(result)); self.assertNotIn(str(self.base), json.dumps(result))

    def test_actual_full_count_caps_fit_output_and_one_more_version_refuses(self):
        shutil.rmtree(self.selected / 'VC')
        for version in range(16):
            for family in range(140, 146): self.family('14.51.' + str(version), 'Microsoft.VC' + str(family) + '.CRT')
        result = self.observe()
        self.assertEqual((result['version_count'], result['family_count'], result['file_count']), (16, 96, 384))
        self.assertLessEqual(len(self.module.serialized(result)), 64 * 1024)
        (self.selected / 'VC/Redist/MSVC/14.51.16').mkdir()
        self.unavailable(self.observe(), 'version-limit')

    def test_unknown_missing_alias_and_overbound_layouts_cannot_become_a_partial_census(self):
        version_root = self.selected / 'VC/Redist/MSVC/14.51.36231'; x64 = version_root / 'x64'
        for kind in ('unknown-version', 'alias-version', 'missing-x64', 'unknown-family', 'family-limit', 'missing-member', 'nonregular-member', 'empty-member', 'oversized-member'):
            with self.subTest(kind=kind):
                if kind == 'unknown-version': target = self.selected / 'VC/Redist/MSVC/PRIVATE'; target.mkdir()
                elif kind == 'alias-version': target = self.selected / 'VC/Redist/MSVC/v145'; target.mkdir()
                elif kind == 'missing-x64': target = x64; target.rename(version_root / 'saved')
                elif kind == 'unknown-family': target = x64 / 'PRIVATE-family'; target.mkdir()
                elif kind == 'family-limit':
                    added = [self.family('14.51.36231', 'Microsoft.VC' + str(i) + '.CRT') for i in range(140, 145)]
                    target = x64 / 'PRIVATE-seventh-family'; target.mkdir()
                else:
                    target = x64 / 'Microsoft.VC145.CRT/msvcp140.dll'; original = target.read_bytes()
                    if kind == 'missing-member': target.unlink()
                    elif kind == 'nonregular-member': target.unlink(); target.mkdir()
                    elif kind == 'empty-member': target.write_bytes(b'')
                    else:
                        with target.open('r+b') as stream: stream.truncate(self.module.VENDOR_FILE_BYTES + 1)
                expected = {'unknown-version': 'unknown-version-entry', 'alias-version': 'unknown-version-entry',
                    'missing-x64': 'missing-layout', 'unknown-family': 'unknown-family-entry', 'family-limit': 'family-limit',
                    'missing-member': 'required-file-unavailable', 'nonregular-member': 'required-file-unavailable',
                    'empty-member': 'member-size-limit', 'oversized-member': 'member-size-limit'}[kind]
                self.unavailable(self.observe(), expected)
                if kind == 'missing-x64': (version_root / 'saved').rename(x64)
                elif kind in ('unknown-version', 'alias-version', 'unknown-family'): target.rmdir()
                elif kind == 'family-limit':
                    target.rmdir()
                    for path in added: shutil.rmtree(path)
                else:
                    if target.is_dir(): target.rmdir()
                    target.write_bytes(original)

    def test_unknown_version_preflight_happens_before_descendant_metadata(self):
        target = self.selected / 'VC/Redist/MSVC'
        outside = self.base / 'PRIVATE-outside'; outside.write_bytes(b'owned bytes never inspected')
        originals = {'lstat': Path.lstat, 'stat': Path.stat, 'open': Path.open,
            'scandir': self.module.os.scandir, 'long': self.module.windows_long_spelling}
        def guarded(operation):
            def call(path, *args, **kwargs):
                if target in Path(path).parents:
                    self.fail('Root-name refusal must precede every child metadata/content/iteration call.')
                return originals[operation](path, *args, **kwargs)
            return call
        def observed():
            with patch.object(Path, 'lstat', guarded('lstat')), patch.object(Path, 'stat', guarded('stat')), \
                    patch.object(Path, 'open', guarded('open')), patch.object(self.module.os, 'scandir', guarded('scandir')), \
                    patch.object(self.module, 'windows_long_spelling', guarded('long')):
                return self.observe()
        cases = [
            ('literal-directory', [('v14', 'directory')], 'exact-v14-token'),
            ('literal-file', [('V14', 'file')], 'exact-v14-token'),
            ('literal-link', [('v14', 'link')], 'exact-v14-token'),
            ('other', [('PRIVATE-unknown', 'directory')], 'other-noncanonical-name'),
            ('noncanonical-number', [('14.051', 'file')], 'other-noncanonical-name'),
            ('mixed', [('v14', 'file'), ('PRIVATE-unknown', 'directory')], 'both'),
            ('unknown-only', [('v14', 'directory')], 'exact-v14-token')]
        for label, entries, expected in cases:
            with self.subTest(case=label):
                numeric, saved = target/'14.51.36231', self.base/'saved-numeric'
                if label == 'unknown-only': numeric.rename(saved)
                for name, kind in entries:
                    path = target/name
                    if kind == 'directory': path.mkdir()
                    elif kind == 'file': path.write_bytes(b'owned unknown bytes')
                    else: path.symlink_to(outside)
                try:
                    # The ordinary numeric sibling sorts before v14/private;
                    # even its metadata is forbidden once any name is unknown.
                    result = observed()
                    self.unavailable(result, 'unknown-version-entry')
                    self.assertEqual(result['version_entry_refusal'], expected)
                finally:
                    for name, kind in entries:
                        if kind == 'directory': (target/name).rmdir()
                        else: (target/name).unlink()
                    if label == 'unknown-only': saved.rename(numeric)
        class Entries:
            def __init__(self, values): self.values = values
            def __enter__(self): return iter(SimpleNamespace(name=name) for name in self.values)
            def __exit__(self, *_args): pass
        for values, reason in ((['v14', 'V14'], 'ambiguous-entry'),
                (['v14', *('PRIVATE-'+str(i) for i in range(16))], 'version-limit')):
            with self.subTest(refusal=reason):
                originals['scandir'] = lambda _path: Entries(values)
                self.unavailable(observed(), reason)

    def test_real_parent_link_and_windows_reparse_stop_before_leaf_metadata_or_reads(self):
        parent = self.selected / 'VC/Redist'; original = Path.lstat
        outside = self.base / 'outside'; parent.rename(outside); parent.symlink_to(outside, target_is_directory=True)
        def guard(path, *args, **kwargs):
            if parent in path.parents: self.fail('Linked descendants must not receive metadata.')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', guard): self.unavailable(self.observe(), 'linked-path')
        parent.unlink(); outside.rename(parent)
        def reparse(path, *args, **kwargs):
            if parent in path.parents: self.fail('Reparse descendants must not receive metadata.')
            value = original(path, *args, **kwargs)
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400) if path == parent else value
        with patch.object(Path, 'lstat', reparse): self.unavailable(self.observe(), 'linked-path')

    def test_raw_aliases_foreign_query_tool_and_changed_metadata_are_refused(self):
        self.unavailable(self.observe(selected_vs_root=str(self.selected / 'x/../y')), 'invalid-input')
        self.unavailable(self.observe(vswhere=self.base / 'PRIVATE-vswhere.exe'), 'vswhere-origin')
        actual = self.module.census; calls = 0
        def changed(root, budget):
            nonlocal calls
            calls += 1; result = actual(root, budget)
            if calls == 1: (self.selected / 'VC/Redist/MSVC/14.51.36231/x64/Microsoft.VC145.CRT/msvcp140.dll').write_bytes(b'changed-size')
            return result
        with patch.object(self.module, 'census', changed): self.unavailable(self.observe(), 'layout-changed')

    def test_portable_windows_raw_names_refuse_aliases_streams_devices_and_namespaces(self):
        valid = ('C:/Program Files/Visual Studio/report.json', r'C:\owned\中文\report.json',
            'C:/owned/.config/report.json', 'C:/owned/COM10.json')
        invalid = ('C:/owned/selected./report.json', 'C:/owned/selected /report.json',
            'C:/owned/report.json:stream', 'C:/owned/report.json::$DATA', 'C:/owned:stream/report.json',
            '//server/share/report.json', r'\\?\C:\owned\report.json', r'\\.\C:\owned\report.json',
            r'\??\C:\owned\report.json', 'C:owned/report.json', 'C:/owned/../report.json',
            'C:/owned/./report.json', 'C:/owned//report.json', 'C:/owned/report?.json',
            'C:/owned/report*.json', 'C:/owned/report|.json')
        invalid += tuple('C:/owned/' + name + '/report.json' for name in
            ('CON', 'con.txt', 'CON .txt', 'PRN', 'AUX.tar.gz', 'NUL.json', 'COM1.txt', 'LPT9',
             'COM¹.txt', 'COM²', 'COM³', 'LPT¹', 'LPT².txt', 'LPT³', 'CONIN$', 'CONOUT$'))
        # PureWindowsPath is intentional: POSIX Path rejects a Windows drive
        # even before these Windows-specific checks, which would hide this bug.
        with patch.object(self.module, 'Path', PureWindowsPath):
            for value in valid:
                with self.subTest(valid=value): self.assertEqual(self.module.canonical_path(value), PureWindowsPath(value))
            for value in invalid:
                with self.subTest(invalid=value), self.assertRaises(self.module.CensusError) as error:
                    self.module.canonical_path(value)
                self.assertEqual(error.exception.code, 'invalid-input')

    def test_long_name_query_follows_full_root_first_guard_and_refuses_non_tilde_alias(self):
        actual = Path.lstat; walked = []
        def tracked(path, *args, **kwargs):
            walked.append(path); return actual(path, *args, **kwargs)
        def long_name(path, _budget):
            self.assertEqual(walked, [*reversed(path.parents), path])
            return str(path.parent / 'different-long-spelling')
        with patch.object(Path, 'lstat', tracked), patch.object(self.module, 'windows_long_spelling', long_name):
            with self.assertRaises(self.module.CensusError) as error: self.module.directory(self.selected, self.module.Budget())
        self.assertEqual(error.exception.code, 'invalid-input')
        parent = self.selected / 'VC'; saved = self.base / 'saved-VC'; parent.rename(saved)
        parent.symlink_to(saved, target_is_directory=True)
        with patch.object(self.module, 'windows_long_spelling') as query:
            with self.assertRaises(self.module.CensusError) as error:
                self.module.info(parent / 'Redist', self.module.Budget())
        self.assertEqual(error.exception.code, 'linked-path'); query.assert_not_called()

    def test_short_spelling_refuses_before_utility_content_and_forbidden_sink_use(self):
        alias = self.base / 'PRIVATE-short'; alias.mkdir()
        def long_name(path, _budget):
            return str(self.selected) if path == alias else str(path)
        with patch.object(self.module, 'windows_long_spelling', long_name), patch.object(Path, 'open') as content:
            self.unavailable(self.observe(selected_vs_root=alias), 'invalid-input')
            with self.assertRaises(self.module.CensusError) as error:
                self.module.write_report(self.selected / 'must-not-exist.json', {}, forbidden_roots=(alias,))
        self.assertEqual(error.exception.code, 'invalid-input'); content.assert_not_called()
        self.assertFalse((self.selected / 'must-not-exist.json').exists())

    def test_missing_leaf_still_checks_existing_parent_long_spelling_before_return(self):
        alias = self.base / 'PRIVATE-short'; alias.mkdir(); seen = []
        def long_name(path, _budget):
            seen.append(path)
            return str(self.selected) if path == alias else str(path)
        with patch.object(self.module, 'windows_long_spelling', long_name), patch.object(Path, 'open') as content:
            with self.assertRaises(self.module.CensusError) as error:
                self.module.info(alias / 'missing' / 'report.json', self.module.Budget(), missing=True)
        self.assertEqual(error.exception.code, 'invalid-input'); self.assertEqual(seen, [alias]); content.assert_not_called()
        with patch.object(self.module, 'windows_long_spelling', side_effect=lambda path, _budget: str(path)) as query:
            self.assertIsNone(self.module.info(self.base / 'missing' / 'report.json', self.module.Budget(), missing=True))
        self.assertEqual(query.call_args.args[0], self.base)

    def test_windows_long_name_binding_is_bounded_and_fails_closed_without_retry(self):
        import ctypes
        from ctypes import wintypes
        value = 'C:\\owned\\Long Directory'
        for count in (len(value), 0, 32768):
            calls = []
            def function(path, buffer, capacity):
                calls.append((path, capacity)); buffer.value = value; return count
            with self.subTest(result=count), patch.object(self.module, 'os', SimpleNamespace(name='nt')), \
                    patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(GetLongPathNameW=function), create=True):
                if count == len(value):
                    self.assertEqual(self.module.windows_long_spelling(PureWindowsPath(value), self.module.Budget()), value)
                else:
                    with self.assertRaises(self.module.CensusError) as error:
                        self.module.windows_long_spelling(PureWindowsPath(value), self.module.Budget())
                    self.assertEqual(error.exception.code, 'metadata-unavailable')
            self.assertEqual(calls, [(value, 32768)])
            self.assertEqual(function.argtypes, (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD))
            self.assertIs(function.restype, wintypes.DWORD)

    def test_drive_multisz_accepts_only_current_complete_local_volume_with_bounded_history(self):
        current = r'\Device\HarddiskVolume12'
        for history in ([], [r'\??\C:\PRIVATE-prior'], ['old'] * 15):
            raw = '\0'.join([current, *history]) + '\0\0'
            with self.subTest(history_count=len(history)):
                self.assertEqual(self.module.parse_drive_mapping(raw), current.lower())
        invalid = [current, current+'\0', current+'\0\0\0', current+'\0\0extra\0\0',
            '\0\0', '\0'.join([current, *(['old']*16)])+'\0\0', 'x'*4097,
            r'\??\C:\PRIVATE-VS\nested'+'\0'+current+'\0\0']
        invalid += [name+'\0\0' for name in (r'\??\C:\PRIVATE-VS\nested',
            r'\Device\HarddiskVolume12\PRIVATE-VS\nested', r'\Device\HarddiskVolume12'+'\\',
            r'\Device\Mup\PRIVATE-share', r'\Device\LanmanRedirector\PRIVATE-share',
            r'\Device\HarddiskVolume01', r'\Device\HarddiskVolume12345678901',
            r'\Device\HarddiskVolume', r'\Device\UnknownVolume12', r'\Device\HarddiskVolume12x',
            r'\Devıce\HarddiskVolume12', r'\Device\HarddisKVolume12')]
        for raw in invalid:
            with self.subTest(case=invalid.index(raw)), self.assertRaises(self.module.CensusError) as error:
                self.module.parse_drive_mapping(raw)
            self.assertEqual(error.exception.code, 'metadata-unavailable'); self.assertNotIn('PRIVATE', str(error.exception))

    def test_windows_drive_query_uses_one_explicit_letter_fixed_buffer_and_no_retry(self):
        import ctypes
        from ctypes import wintypes
        raw = r'\Device\HarddiskVolume12'+'\0\0'
        for count in (len(raw), 0, 4097):
            calls = []
            def function(drive, buffer, capacity):
                calls.append((drive, capacity)); buffer[:len(raw)] = raw; return count
            with self.subTest(result=count), patch.object(self.module, 'os', SimpleNamespace(name='nt')), \
                    patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(QueryDosDeviceW=function), create=True):
                if count == len(raw):
                    self.assertEqual(self.module.windows_drive_mapping('C:', self.module.Budget()), raw[:-2].lower())
                else:
                    with self.assertRaises(self.module.CensusError) as error:
                        self.module.windows_drive_mapping('C:', self.module.Budget())
                    self.assertEqual(error.exception.code, 'metadata-unavailable')
            self.assertEqual(calls, [('C:', 4096)])
            self.assertEqual(function.argtypes, (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD))
            self.assertIs(function.restype, wintypes.DWORD)
        with patch.object(self.module, 'os', SimpleNamespace(name='nt')), patch.object(ctypes, 'WinDLL', create=True) as library:
            for drive in ('', None, 'C:\\', 'C:/PRIVATE', '*'):
                with self.subTest(invalid_drive=type(drive).__name__), self.assertRaises(self.module.CensusError):
                    self.module.windows_drive_mapping(drive, self.module.Budget())
            library.assert_not_called()

    def test_unknown_or_directory_drive_mapping_refuses_before_any_descendant_io(self):
        path = PureWindowsPath('X:/PRIVATE-output/report.json')
        for mapping in (r'\??\C:\PRIVATE-VS\nested', r'\Device\HarddiskVolume12\PRIVATE-VS\nested',
                r'\Device\Mup\PRIVATE-share', r'\Device\UnknownVolume'):
            with self.subTest(kind=mapping.split('\\')[1]), patch.object(self.module, 'windows_drive_mapping', return_value=mapping), \
                    patch.object(PureWindowsPath, 'lstat', create=True) as metadata, \
                    patch.object(self.module.os, 'scandir') as enumeration, \
                    patch.object(PureWindowsPath, 'open', create=True) as content:
                with self.assertRaises(self.module.CensusError) as error:
                    self.module.info(path, self.module.Budget(), missing=True)
            self.assertEqual(error.exception.code, 'metadata-unavailable')
            metadata.assert_not_called(); enumeration.assert_not_called(); content.assert_not_called()

    def test_drive_cache_is_capped_and_changed_or_missing_current_mapping_never_rebinds(self):
        current = r'\Device\HarddiskVolume12'; budget = self.module.Budget()
        with patch.object(self.module, 'windows_drive_mapping', return_value=current) as query:
            for drive in ('C:', 'D:', 'E:', 'F:'):
                self.module.path_identity(PureWindowsPath(drive+'/owned'), budget)
            with self.assertRaises(self.module.CensusError):
                self.module.path_identity(PureWindowsPath('G:/owned'), budget)
        self.assertEqual(query.call_count, 4); self.assertEqual(len(budget.drive_mappings), 4)
        for changed, reason in ((r'\Device\HarddiskVolume13', 'layout-changed'), (None, 'metadata-unavailable')):
            with self.subTest(reason=reason), patch.object(self.module, 'windows_drive_mapping', return_value=changed), \
                    patch.object(PureWindowsPath, 'lstat', create=True) as metadata:
                with self.assertRaises(self.module.CensusError) as error:
                    self.module.info(PureWindowsPath('C:/owned'), budget, missing=True)
            self.assertEqual(error.exception.code, reason); metadata.assert_not_called()
            self.assertEqual(set(budget.drive_mappings.values()), {current.lower()})

    def test_private_volume_components_catch_duplicate_letters_and_keep_distinct_volumes_separate(self):
        mappings = {'C:': r'\Device\HarddiskVolume12', 'X:': r'\Device\HarddiskVolume12', 'D:': r'\Device\HarddiskVolume13'}
        with patch.object(self.module, 'windows_drive_mapping', side_effect=lambda drive, _budget: mappings[drive]):
            budget = self.module.Budget(); root = PureWindowsPath('C:/PRIVATE-VS')
            self.assertNotIn(root, PureWindowsPath('X:/PRIVATE-VS/nested/report.json').parents)
            self.assertTrue(self.module.path_within(PureWindowsPath('X:/private-vs/nested/report.json'), root, budget))
            self.assertFalse(self.module.path_within(PureWindowsPath('X:/PRIVATE-VS-other/report.json'), root, budget))
            self.assertFalse(self.module.path_within(PureWindowsPath('D:/PRIVATE-VS/report.json'), root, budget))
            self.assertTrue(self.module.path_within(PureWindowsPath('X:/Installer/report.json'), PureWindowsPath('C:/Installer'), budget))

    def test_report_preflight_catches_duplicate_volume_and_subst_before_output_metadata_or_observation(self):
        arguments = ['observe', '--selected-vs-root', 'C:/PRIVATE-VS', '--selected-vs-version', self.version,
            '--vswhere', 'C:/Installer/vswhere.exe', '--source-commit', self.source, '--observation-id', 'authored-census']
        for mapping in (r'\Device\HarddiskVolume12', r'\??\C:\PRIVATE-VS\nested',
                r'\Device\HarddiskVolume12\PRIVATE-VS\nested'):
            walked = []
            def metadata(path):
                walked.append(path)
                if path.drive == 'X:': self.fail('Output alias must be refused before its metadata.')
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700)
            with self.subTest(mapping_kind=len(mapping)), patch.object(self.module, 'Path', PureWindowsPath), \
                    patch.object(self.module, 'windows_drive_mapping', side_effect=lambda drive, _budget: mapping if drive == 'X:' else r'\Device\HarddiskVolume12'), \
                    patch.object(self.module, 'windows_long_spelling', side_effect=lambda path, _budget: str(path)), \
                    patch.object(PureWindowsPath, 'lstat', metadata, create=True), \
                    patch.object(PureWindowsPath, 'open', create=True) as content, \
                    patch.object(self.module, 'observe') as observe, redirect_stderr(io.StringIO()) as error:
                self.assertEqual(self.module.main([*arguments, '--output', 'X:/PRIVATE-VS/nested/report.json']), 2)
            self.assertTrue(walked); content.assert_not_called(); observe.assert_not_called()
            self.assertNotIn('PRIVATE', error.getvalue()); self.assertNotIn('HarddiskVolume', error.getvalue())

    def test_drive_recheck_precedes_query_content_execution_and_report_create(self):
        for operation in ('content', 'query', 'report'):
            budget = self.module.Budget(); budget.drive_mappings['C:'] = r'\device\harddiskvolume12'
            with self.subTest(operation=operation), patch.object(self.module, 'windows_drive_mapping', return_value=r'\Device\HarddiskVolume13'), \
                    patch.object(Path, 'open') as content, patch.object(self.module.subprocess, 'Popen') as process:
                with self.assertRaises(self.module.CensusError) as error:
                    if operation == 'content': self.module.utility_identity(self.utility, budget)
                    elif operation == 'query': self.module.query_instance(self.utility, self.selected, self.version, budget)
                    else: self.module.write_report(self.base/'must-not-exist.json', {}, budget=budget)
            self.assertEqual(error.exception.code, 'layout-changed'); content.assert_not_called(); process.assert_not_called()
            self.assertFalse((self.base/'must-not-exist.json').exists())

    def test_cli_preserves_initial_drive_snapshot_from_preflight_through_create(self):
        budget = self.module.Budget(); current = r'\Device\HarddiskVolume12'
        def observe(*_args, **kwargs):
            self.assertIs(kwargs['budget'], budget)
            budget.drive_mappings['C:'] = current.lower()
            return {'status': 'unavailable', 'reason': 'layout-changed'}
        arguments = ['observe', '--selected-vs-root', str(self.selected), '--selected-vs-version', self.version,
            '--vswhere', str(self.utility), '--source-commit', self.source, '--observation-id', 'authored-census',
            '--output', str(self.base/'must-not-exist.json')]
        with patch.object(self.module, 'Budget', return_value=budget), patch.object(self.module, 'observe', side_effect=observe), \
                patch.object(self.module, 'windows_drive_mapping', return_value=r'\Device\HarddiskVolume13'), \
                patch.object(Path, 'open') as content, redirect_stderr(io.StringIO()) as error:
            self.assertEqual(self.module.main(arguments), 2)
        content.assert_not_called(); self.assertFalse((self.base/'must-not-exist.json').exists())
        self.assertNotIn('HarddiskVolume', error.getvalue())

    def test_cli_preflights_raw_sink_and_existing_aliases_before_observation(self):
        arguments = ['observe', '--selected-vs-root', str(self.selected), '--selected-vs-version', self.version,
            '--vswhere', str(self.utility), '--source-commit', self.source, '--observation-id', 'authored-census']
        for name in ('PRIVATE-selected./report.json', 'PRIVATE-selected /report.json', 'PRIVATE-report.json:stream',
                'CON.txt', 'LPT¹.json'):
            with self.subTest(kind=name), patch.object(self.module, 'observe') as observe, \
                    patch.object(Path, 'open') as content, redirect_stderr(io.StringIO()) as error:
                self.assertEqual(self.module.main([*arguments, '--output', str(self.base / name)]), 2)
            observe.assert_not_called(); content.assert_not_called(); self.assertNotIn('PRIVATE', error.getvalue())
        target = self.base / 'report.json'
        def long_name(path, _budget):
            return str(self.base / 'different-long-spelling') if path == self.selected else str(path)
        with patch.object(self.module, 'windows_long_spelling', long_name), patch.object(self.module, 'observe') as observe, \
                patch.object(Path, 'open') as content, redirect_stderr(io.StringIO()):
            self.assertEqual(self.module.main([*arguments, '--output', str(target)]), 2)
        observe.assert_not_called(); content.assert_not_called(); self.assertFalse(target.exists())

    def test_actual_query_tool_bytes_and_private_instance_projection_are_reverified(self):
        def changed_query(*_args): self.utility.write_bytes(b'changed-query'); return self.query()
        self.unavailable(self.observe(query=changed_query), 'vswhere-changed')
        for extra in ({'PRIVATE': str(self.base)}, {'edition': 'PRIVATE'}, {'release_state': ['PRIVATE']}):
            with self.subTest(extra=list(extra)):
                def malformed(*_args): return {**self.query(), **extra}
                self.unavailable(self.observe(query=malformed), 'instance-metadata-unavailable')

    def test_fixed_file_links_and_query_utility_parent_links_never_open_targets(self):
        member = self.selected / 'VC/Redist/MSVC/14.51.36231/x64/Microsoft.VC145.CRT/msvcp140.dll'
        saved = member.read_bytes(); member.unlink(); outside = self.base / 'PRIVATE-outside'; outside.write_bytes(saved)
        member.symlink_to(outside)
        actual = Path.open
        def guard(path, *args, **kwargs):
            if path in (member, outside): self.fail('A linked CRT member must not be opened.')
            return actual(path, *args, **kwargs)
        with patch.object(Path, 'open', guard): self.unavailable(self.observe(), 'linked-path')
        member.unlink(); member.write_bytes(saved)
        parent = self.utility.parent; relocated = self.base / 'PRIVATE-query-parent'; parent.rename(relocated)
        parent.symlink_to(relocated, target_is_directory=True)
        actual_lstat = Path.lstat
        def no_descendant(path, *args, **kwargs):
            if parent in path.parents: self.fail('A linked query parent must precede utility metadata/hash.')
            return actual_lstat(path, *args, **kwargs)
        with patch.object(Path, 'lstat', no_descendant): self.unavailable(self.observe(), 'linked-path')

    def test_query_malformed_json_and_unknown_error_fields_never_disclose_private_input(self):
        for raw in (b'{PRIVATE', b'[{"installationPath":"PRIVATE","installationPath":"PRIVATE"}]', b'[NaN]', b'\xff'):
            with self.subTest(raw_kind=len(raw)), patch.object(self.module, 'bounded_capture', return_value=raw):
                self.unavailable(self.observe(query=self.module.query_instance), 'query-unavailable')
        def arbitrary(*_args):
            error = self.module.CensusError('deadline'); error.code = 'PRIVATE ' + str(self.base); raise error
        self.unavailable(self.observe(query=arbitrary), 'observation-failed')
        class PrivateValue:
            def __str__(self): raise AssertionError('Private diagnostic attributes must not be formatted.')
        invalid = [None, True, ['exact-v14-token'], {'path': str(self.base)}, 'PRIVATE raw name',
            'a'*64, 'v14', PrivateValue()]
        for reason, values in (('unknown-version-entry', invalid),
                ('deadline', ['exact-v14-token', 'PRIVATE misplaced context'])):
            for value in values:
                with self.subTest(reason=reason, value_kind=type(value).__name__):
                    error = self.module.CensusError(reason)
                    error.version_entry_refusal = value
                    error.args = ('PRIVATE exception text must not be inspected',)
                    def malformed(*_args): raise error
                    with self.assertRaises(self.module.CensusError) as caught:
                        self.observe(query=malformed)
                    self.assertEqual(caught.exception.code, 'observation-failed')
                    self.assertNotIn('PRIVATE', str(caught.exception))
        # The real observe boundary must fail out before a standalone CLI can
        # write even a negative report with malformed refusal context.
        actual = self.module.observe
        def malformed_cli(*args, **kwargs):
            error = self.module.CensusError('unknown-version-entry')
            error.version_entry_refusal = 'PRIVATE'
            def query(*_args): raise error
            return actual(*args, **kwargs, program_files_provider=lambda: self.program, query=query)
        arguments = ['observe', '--selected-vs-root', str(self.selected), '--selected-vs-version', self.version,
            '--vswhere', str(self.utility), '--source-commit', self.source, '--observation-id', 'authored-census',
            '--output', str(self.base/'must-not-publish.json')]
        with patch.object(self.module, 'observe', malformed_cli), patch.object(self.module, 'write_report') as writer, \
                redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(self.module.main(arguments), 2)
        writer.assert_not_called(); self.assertFalse((self.base/'must-not-publish.json').exists())
        self.assertNotIn('PRIVATE', stderr.getvalue())

    def query_json(self, values):
        raw = json.dumps(values).encode()
        with patch.object(self.module, 'bounded_capture', return_value=raw) as call:
            result = self.module.query_instance(self.utility, self.selected, self.version, self.module.Budget())
        command = call.call_args.args[0]
        self.assertIn('-all', command); self.assertIn('-prerelease', command); self.assertNotIn('-latest', command)
        return result

    def instance(self, **extra):
        return {'installationPath': str(self.selected), 'installationVersion': self.version,
            'productId': 'Microsoft.VisualStudio.Product.Enterprise', 'isPrerelease': False,
            'isComplete': True, 'isLaunchable': True, 'displayName': str(self.base) + '/PRIVATE', **extra}

    def test_query_matches_only_exact_selected_instance_and_ignores_private_display_fields(self):
        other = self.instance(installationPath=str(self.base / 'PRIVATE-other'), installationVersion='18.99.1.1')
        self.assertEqual(self.query_json([other, self.instance()]), {'version': self.version, 'edition': 'enterprise', 'release_state': 'release'})
        self.assertEqual(self.query_json([self.instance(isPrerelease=True)])['release_state'], 'prerelease')

    def test_duplicate_wrong_missing_unknown_and_overbound_instance_metadata_refuse(self):
        for values, code in (([self.instance(), self.instance()], 'instance-ambiguous'),
                ([self.instance(installationVersion='18.1.1.1')], 'instance-version-mismatch'),
                ([], 'instance-unavailable'), ([self.instance(isPrerelease=None)], 'instance-metadata-unavailable'),
                ([self.instance(productId='PRIVATE-edition')], 'instance-metadata-unavailable'),
                ([self.instance()] * 33, 'instance-limit')):
            with self.subTest(code=code), self.assertRaises(self.module.CensusError) as error: self.query_json(values)
            self.assertEqual(error.exception.code, code); self.assertNotIn('PRIVATE', str(error.exception))

    def test_query_output_is_bounded_before_decode_and_owned_process_is_reaped(self):
        contexts = []; actual = subprocess.Popen
        def owned(*args, **kwargs):
            result = actual(*args, **kwargs); contexts.append(result); return result
        with patch.object(self.module.subprocess, 'Popen', owned), self.assertRaises(self.module.CensusError) as error:
            self.module.bounded_capture([sys.executable, '-c', 'import sys,time;sys.stdout.buffer.write(b"x"*1048577);sys.stdout.flush();time.sleep(30)'], self.module.Budget())
        self.assertEqual(error.exception.code, 'query-limit')
        self.assertIsNotNone(contexts[0].poll()); self.assertTrue(contexts[0].stdout.closed)

    def test_query_deadline_reaps_only_its_owned_process_and_stderr_is_not_returned(self):
        class ShortBudget:
            end = time.monotonic() + .1
            drive_mappings = {}
            def remaining(inner):
                value = inner.end - time.monotonic()
                if value <= 0: raise self.module.CensusError('deadline')
                return value
        actual = subprocess.Popen; contexts = []
        def owned(*args, **kwargs):
            result = actual(*args, **kwargs); contexts.append(result); return result
        with patch.object(self.module.subprocess, 'Popen', owned), self.assertRaises(self.module.CensusError) as error:
            self.module.bounded_capture([sys.executable, '-c', 'import sys,time;sys.stderr.write("PRIVATE");time.sleep(30)'], ShortBudget())
        self.assertEqual(error.exception.code, 'deadline'); self.assertIsNotNone(contexts[0].poll())
        self.assertTrue(contexts[0].stdout.closed)
        raw = self.module.bounded_capture([sys.executable, '-c', 'import sys;sys.stderr.write("PRIVATE");sys.stdout.write("[]")'], self.module.Budget())
        self.assertEqual(raw, b'[]')

    def test_new_report_only_guarded_sink_and_cli_errors_never_print_paths(self):
        report = self.observe(); target = self.base / 'report.json'; self.module.write_report(target, report)
        self.assertEqual(json.loads(target.read_bytes()), report)
        with self.assertRaises(self.module.CensusError): self.module.write_report(target, report)
        target.unlink(); outside = self.base / 'outside-report'; outside.write_bytes(b'preserved')
        target.symlink_to(outside)
        with self.assertRaises(self.module.CensusError): self.module.write_report(target, report)
        self.assertEqual(outside.read_bytes(), b'preserved')
        linked = self.base / 'PRIVATE-report-link'; linked.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(self.module.CensusError): self.module.write_report(linked / 'must-not-exist.json', report)
        self.assertFalse((self.base / 'must-not-exist.json').exists())
        for target in (self.selected / 'must-not-exist.json', self.utility.parent / 'must-not-exist.json'):
            with self.assertRaises(self.module.CensusError):
                self.module.write_report(target, report, forbidden_roots=(self.selected, self.utility.parent))
            self.assertFalse(target.exists())
        stderr = io.StringIO()
        with redirect_stderr(stderr): self.assertEqual(self.module.main(['PRIVATE-unrecognized-path']), 2)
        self.assertNotIn('PRIVATE', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
