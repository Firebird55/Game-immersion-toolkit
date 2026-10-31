"""Authored ZIP fixtures; no real Windows executable is extracted or run."""
import builtins
from contextlib import ExitStack
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pinned_cmake_test', ROOT / 'scripts/pinned-build-cmake.py')
cmake = importlib.util.module_from_spec(spec); spec.loader.exec_module(cmake)
UPSTREAM = 'cmake-4.4.5-windows-x86_64'


class PinnedCMakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def fixture(self, extra=(), notice=b'authored notice'):
        path = self.root / 'fixture.zip'
        entries = [(UPSTREAM + '/bin/cmake.exe', b'authored invalid-PE tool fixture', stat.S_IFREG, 0),
                   (UPSTREAM + '/doc/LICENSE.rst', notice, stat.S_IFREG, 0)]
        entries.extend(extra)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as z:
                for name, raw, kind, dos in entries:
                    info = zipfile.ZipInfo(name); info.external_attr = ((kind | 0o644) << 16) | dos
                    # The constructor sanitizes on the writer's host. These
                    # malicious fixtures must retain their actual raw names.
                    info.filename = name
                    z.writestr(info, raw)
        pin = {'version': '4.4.5', 'platform': 'win-x64',
            'archive': {'filename': 'fixture.zip', 'root': UPSTREAM, 'entries': len(entries),
                'regular_files': sum(not name.endswith('/') for name, *_ in entries),
                'bytes': path.stat().st_size, 'sha256': cmake.digest(path.read_bytes()),
                'expanded_bytes': sum(len(raw) for _, raw, *_ in entries)},
            'executable': {'path': entries[0][0], 'bytes': len(entries[0][1]), 'sha256': cmake.digest(entries[0][1])},
            'notices': [{'path': UPSTREAM + '/doc/LICENSE.rst', 'bytes': len(b'authored notice'),
                         'sha256': cmake.digest(b'authored notice')}]}
        return path, pin

    def test_exact_original_zip_notice_and_closed_tree_are_retained(self):
        archive, pin = self.fixture(extra=[(UPSTREAM + '/empty/', b'', stat.S_IFDIR, 0)])
        output = self.root / 'fresh-parent/prepared'
        with patch.object(cmake, 'policy', return_value=pin):
            prepared = cmake.prepare(archive, output); verified = cmake.verify(output)
            self.assertEqual(cmake.payload_root(output), output / UPSTREAM)
        self.assertEqual((output / 'inputs/fixture.zip').read_bytes(), archive.read_bytes())
        self.assertEqual((output / UPSTREAM / 'doc/LICENSE.rst').read_bytes(), b'authored notice')
        self.assertEqual(prepared['tree_sha256'], verified['tree_sha256'])
        self.assertEqual(verified['operation'], 'verified')
        for gate in ('runtime_collection_allowed', 'production_execution_allowed', 'source_delivery_approved',
                     'native_payload_in_source_review', 'r19_complete'):
            self.assertFalse(verified[gate])
        self.assertNotIn(str(self.root), json.dumps(verified))

    def test_untrusted_archive_names_links_reparse_aliases_and_devices_fail_before_output(self):
        malformed = [('../outside', b'x', stat.S_IFREG, 0),
            ('/' + UPSTREAM + '/abs', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin\\other', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin/other\0hidden', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin/other:stream', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin/other.', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin/CON.txt', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/BIN/other', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin/cmake.exe', b'x', stat.S_IFREG, 0),
            (UPSTREAM + '/bin/link', b'target', stat.S_IFLNK, 0),
            (UPSTREAM + '/bin/reparse', b'x', stat.S_IFREG, 0x400),
            (UPSTREAM + '/bin/device', b'', stat.S_IFCHR, 0)]
        for index, entry in enumerate(malformed):
            with self.subTest(name=entry[0]):
                archive, pin = self.fixture(extra=[entry]); output = self.root / ('bad-' + str(index))
                with patch.object(cmake, 'policy', return_value=pin), self.assertRaises(ValueError):
                    cmake.prepare(archive, output)
                self.assertFalse(output.exists())

    def test_wrong_hash_notice_bounds_crc_and_existing_output_are_preserved(self):
        for case in ('hash', 'notice', 'bounds', 'crc', 'existing'):
            with self.subTest(case=case):
                archive, pin = self.fixture(notice=b'changed notice' if case == 'notice' else b'authored notice')
                output = self.root / ('bad-' + case)
                if case == 'hash': archive.write_bytes(b'changed')
                if case == 'bounds': pin['archive']['expanded_bytes'] = cmake.MAX_EXPANDED + 1
                if case == 'crc':
                    raw = archive.read_bytes().replace(b'authored invalid-PE', b'broken!! invalid-PE', 1)
                    archive.write_bytes(raw); pin['archive']['sha256'] = cmake.digest(raw)
                if case == 'existing': output.mkdir(); (output / 'prior').write_bytes(b'keep')
                with patch.object(cmake, 'policy', return_value=pin), self.assertRaises((ValueError, zipfile.BadZipFile)):
                    cmake.prepare(archive, output)
                if case == 'existing': self.assertEqual((output / 'prior').read_bytes(), b'keep')
                else: self.assertFalse(output.exists())

    def test_prepared_tree_or_retained_zip_or_receipt_changes_cannot_self_authorize(self):
        for case in ('executable', 'notice', 'extra-file', 'extra-directory', 'missing', 'archive', 'receipt'):
            with self.subTest(case=case):
                archive, pin = self.fixture(); output = self.root / ('changed-' + case)
                with patch.object(cmake, 'policy', return_value=pin):
                    cmake.prepare(archive, output)
                    if case == 'executable': (output / UPSTREAM / 'bin/cmake.exe').write_bytes(b'changed')
                    if case == 'notice': (output / UPSTREAM / 'doc/LICENSE.rst').write_bytes(b'changed')
                    if case == 'extra-file': (output / 'extra').write_bytes(b'new')
                    if case == 'extra-directory': (output / 'unexpected-empty').mkdir()
                    if case == 'missing': (output / UPSTREAM / 'doc/LICENSE.rst').unlink()
                    if case == 'archive': (output / 'inputs/fixture.zip').write_bytes(b'changed')
                    if case == 'receipt':
                        receipt = output / cmake.RECEIPT
                        receipt.write_bytes(receipt.read_bytes() + b' ')
                    with self.assertRaises(ValueError): cmake.verify(output)

    def test_publisher_checksum_and_acquisition_require_exact_bytes_before_writes(self):
        archive, pin = self.fixture(); raw = archive.read_bytes()
        checksum = (pin['archive']['sha256'] + '  fixture.zip\n').encode()
        pin['archive']['url'] = 'https://github.com/Kitware/CMake/releases/download/v4.4.5/fixture.zip'
        pin['publisher_checksums'] = {'filename': 'checksums.txt', 'bytes': len(checksum),
            'sha256': cmake.digest(checksum),
            'url': 'https://github.com/Kitware/CMake/releases/download/v4.4.5/checksums.txt'}
        destination = self.root / 'fresh-parent/inputs'
        with patch.object(cmake, 'policy', return_value=pin), patch.object(cmake.urllib.request, 'urlopen',
                side_effect=[io.BytesIO(raw), io.BytesIO(checksum)]):
            cmake.acquire(destination)
        self.assertEqual((destination / 'fixture.zip').read_bytes(), raw)
        self.assertEqual((destination / 'checksums.txt').read_bytes(), checksum)
        with self.assertRaises(ValueError): cmake.checksum_matches(checksum.replace(b'fixture.zip', b'other.zip'), pin)
        output = self.root / 'rejected-inputs'
        with patch.object(cmake, 'policy', return_value=pin), patch.object(cmake.urllib.request, 'urlopen',
                return_value=io.BytesIO(b'wrong')), self.assertRaises(ValueError):
            cmake.acquire(output)
        self.assertFalse(output.exists())

    def test_raw_local_and_central_names_survive_windows_normalization_and_are_rejected(self):
        for suffix in ('bin\\other', 'bin/other\0hidden'):
            with self.subTest(suffix=suffix):
                raw_name = UPSTREAM + '/' + suffix
                # Simulate the Windows constructor on either test host; file
                # operations still use the host's normal pathlib flavour.
                with patch.object(zipfile.os, 'sep', '\\'), patch.object(zipfile.os, 'altsep', '/'):
                    archive, pin = self.fixture(extra=[(raw_name, b'x', stat.S_IFREG, 0)])
                    raw = archive.read_bytes()
                    with zipfile.ZipFile(archive) as zipped:
                        infos = zipped.infolist(); item = infos[-1]
                        self.assertEqual(item.orig_filename, raw_name)
                        self.assertNotEqual(item.filename, raw_name)
                        local_name_size, = struct.unpack_from('<H', raw, item.header_offset + 26)
                        local_name = raw[item.header_offset + 30:item.header_offset + 30 + local_name_size]
                        position = zipped.start_dir
                        central_names = []
                        for _ in infos:
                            self.assertEqual(raw[position:position+4], b'PK\x01\x02')
                            name_size, extra_size, comment_size = struct.unpack_from('<HHH', raw, position + 28)
                            central_names.append(raw[position+46:position+46+name_size])
                            position += 46 + name_size + extra_size + comment_size
                    self.assertEqual(local_name, raw_name.encode('ascii'))
                    self.assertEqual(central_names[-1], raw_name.encode('ascii'))
                    output = self.root / ('raw-nul' if '\0' in suffix else 'raw-backslash')
                    with patch.object(cmake, 'policy', return_value=pin), self.assertRaises(ValueError):
                        cmake.prepare(archive, output)
                    self.assertFalse(output.exists())

    def test_archive_and_prepared_tree_links_are_not_accepted_as_byte_aliases(self):
        archive, pin = self.fixture(); linked = self.root / 'linked.zip'
        try: linked.symlink_to(archive)
        except OSError: self.skipTest('This host cannot create an authored symlink fixture.')
        with patch.object(cmake, 'policy', return_value=pin):
            with self.assertRaises(ValueError): cmake.prepare(linked, self.root / 'linked-output')
            output = self.root / 'prepared'; cmake.prepare(archive, output)
            executable = output / UPSTREAM / 'bin/cmake.exe'
            outside = self.root / 'same-authored-bytes'; outside.write_bytes(executable.read_bytes())
            executable.unlink(); executable.symlink_to(outside)
            with self.assertRaises(ValueError): cmake.verify(output)

    def test_parent_directory_link_refuses_before_descendant_metadata_open_or_enumeration(self):
        archive, pin = self.fixture()
        outside = self.root / 'owned-outside'; (outside / 'nested').mkdir(parents=True)
        copied = outside / 'nested/fixture.zip'; shutil.copyfile(archive, copied)
        preserved = copied.read_bytes()
        link = self.root / 'linked-parent'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            # Junctions provide the real Windows reparse fixture without the
            # optional symbolic-link privilege. No native tool payload is run.
            command = shutil.which('cmd.exe') if os.name == 'nt' else None
            if not command or any(c in str(link) + str(outside) for c in '&|<>^%!"\r\n'):
                self.skipTest('This host cannot create the owned directory-link fixture.')
            created = subprocess.run([command, '/d', '/c', f'mklink /J "{link}" "{outside}"'],
                capture_output=True, timeout=10)
            if created.returncode:
                self.skipTest('This host cannot create owned directory links or junctions.')
        blocked = [link / 'nested', link / 'fresh-output', link / 'fresh-input', outside / 'nested']
        accesses = []
        def selected(path):
            try: value = Path(os.fsdecode(os.fspath(path)))
            except TypeError: return False
            return any(value == parent or parent in value.parents for parent in blocked)
        def guard(label, original):
            def call(path, *args, **kwargs):
                if selected(path):
                    accesses.append(label)
                    raise AssertionError('Descendant access preceded parent-link refusal')
                return original(path, *args, **kwargs)
            return call
        operations = [lambda: cmake.no_links(link / 'nested/fixture.zip'),
            lambda: cmake.checked_file(link / 'nested/fixture.zip', pin['archive'], cmake.MAX_ARCHIVE),
            lambda: cmake.inspect_archive(link / 'nested/fixture.zip', pin),
            lambda: cmake.tree(link / 'nested'), lambda: cmake.verify(link / 'nested'),
            lambda: cmake.prepare(archive, link / 'fresh-output'), lambda: cmake.acquire(link / 'fresh-input')]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cmake, 'policy', return_value=pin))
            network = stack.enter_context(patch.object(cmake.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected network')))
            for target, name in [(os, 'stat'), (os, 'lstat'), (builtins, 'open'), (io, 'open'), (Path, 'iterdir')]:
                stack.enter_context(patch.object(target, name, guard(name, getattr(target, name))))
            for index, operation in enumerate(operations):
                with self.subTest(operation=index), self.assertRaises(ValueError) as failure:
                    operation()
                self.assertNotIn(str(self.root), str(failure.exception))
            network.assert_not_called()
        self.assertEqual(accesses, [], 'The ancestor guard must refuse before any descendant observer')
        self.assertEqual(copied.read_bytes(), preserved)
        self.assertTrue(set(outside.iterdir()) == {outside / 'nested'}, 'The unrelated owned tree changed')

    def test_windows_reparse_attribute_refuses_before_leaf_metadata_or_open(self):
        archive, pin = self.fixture()
        parent = self.root / 'owned-reparse-parent'; parent.mkdir()
        leaf = parent / 'fixture.zip'; shutil.copyfile(archive, leaf)
        accesses = []; original_lstat = os.lstat
        def is_leaf(path):
            try: return Path(os.fsdecode(os.fspath(path))) == leaf
            except TypeError: return False
        def guarded(label, original):
            def call(path, *args, **kwargs):
                if is_leaf(path):
                    accesses.append(label); raise AssertionError('Leaf accessed before reparse refusal')
                result = original(path, *args, **kwargs)
                # pathlib.lstat delegates to os.stat(follow_symlinks=False)
                # on CPython 3.12; cover both native wrapper spellings.
                if label in ('stat', 'lstat') and Path(path) == parent:
                    return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
                return result
            return call
        with ExitStack() as stack:
            for target, name in [(os, 'stat'), (os, 'lstat'), (builtins, 'open'), (io, 'open')]:
                original = original_lstat if name == 'lstat' else getattr(target, name)
                stack.enter_context(patch.object(target, name, guarded(name, original)))
            with self.assertRaises(ValueError): cmake.checked_file(leaf, pin['archive'], cmake.MAX_ARCHIVE)
        self.assertEqual(accesses, [])

    def test_missing_ancestors_stop_metadata_walk_and_regular_file_ancestors_refuse(self):
        missing = self.root / 'missing-parent'
        deeper = missing / 'nested/leaf'
        observed = []; original = Path.lstat; forbidden = {deeper}
        def lstat(path):
            path = Path(path)
            if path in forbidden or missing in path.parents:
                observed.append('below-missing'); raise AssertionError('Missing ancestor was traversed')
            return original(path)
        with patch.object(Path, 'lstat', lstat): cmake.no_links(deeper)
        self.assertEqual(observed, [])
        ordinary = self.root / 'ordinary-file'; ordinary.write_bytes(b'owned regular file')
        forbidden.add(ordinary / 'child')
        with patch.object(Path, 'lstat', lstat):
            with self.assertRaises(ValueError): cmake.no_links(ordinary / 'child')
        self.assertEqual(observed, [])
        with self.assertRaises(ValueError): cmake.no_links(missing / '..' / 'ordinary-file')

    def test_nonregular_leaf_is_not_opened_and_metadata_errors_are_fixed(self):
        leaf = self.root / 'authored-leaf'; leaf.write_bytes(b'owned bytes')
        original = Path.lstat
        def lstat(path):
            if path == leaf: return SimpleNamespace(st_mode=stat.S_IFIFO, st_file_attributes=0)
            return original(path)
        with patch.object(Path, 'lstat', lstat), patch.object(io, 'open', side_effect=AssertionError('Unexpected open')):
            with self.assertRaises(ValueError): cmake.no_links(leaf)
        def unavailable(path):
            if path == leaf: raise PermissionError('PRIVATE metadata ' + str(path))
            return original(path)
        with patch.object(Path, 'lstat', unavailable), self.assertRaises(ValueError) as failure:
            cmake.no_links(leaf)
        self.assertNotIn('PRIVATE', str(failure.exception))
        self.assertNotIn(str(self.root), str(failure.exception))


if __name__ == '__main__': unittest.main()
