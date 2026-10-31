"""Authored ZIP fixtures; no real Windows executable is extracted or run."""
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
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
        output = self.root / 'prepared'
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
        destination = self.root / 'inputs'
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


if __name__ == '__main__': unittest.main()
