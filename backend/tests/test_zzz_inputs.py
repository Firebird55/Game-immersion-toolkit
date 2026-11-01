import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('zzz_inputs', ROOT / 'packaging/runtime-bundle/zzz_inputs.py')
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)


class ZzzInputsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS returns /var/folders here; its trusted OS root is an alias of
        # /private/var. Normalize that root before adding supplier filenames.
        self.root = Path(self.temp.name).resolve()

    def archive(self, items):
        path = self.root / 'input.tgz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, value in items:
                item = tarfile.TarInfo(name)
                if value is None:
                    item.type, item.linkname = tarfile.SYMTYPE, 'outside'
                    archive.addfile(item)
                else:
                    item.size = len(value)
                    archive.addfile(item, io.BytesIO(value))
        return path, {'name': 'authored', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_members_are_verified_without_extracting(self):
        path, pin = self.archive([('package/LICENSE', b'full authored terms')])
        pin['files'] = [{'member': 'package/LICENSE', 'sha256': hashlib.sha256(b'full authored terms').hexdigest()}]
        self.assertEqual(inputs.archive_members(path, pin), {'package/LICENSE': b'full authored terms'})
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_archive_identity_and_member_identity_are_independent(self):
        path, pin = self.archive([('package/LICENSE', b'authored')])
        pin['files'] = [{'member': 'package/LICENSE', 'sha256': '0' * 64}]
        with self.assertRaisesRegex(ValueError, 'member differs'):
            inputs.archive_members(path, pin)
        pin.pop('files')
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'archive differs'):
            inputs.archive_members(path, pin)

    def test_rejects_unsafe_and_duplicate_members(self):
        for items in [[('../escape', b'a')], [('package/link', None)], [('package/a', b'a'), ('package/a', b'b')], [('C:/escape', b'a')], [('package\\escape', b'a')]]:
            with self.subTest(items=items):
                path, pin = self.archive(items)
                with self.assertRaises(ValueError):
                    inputs.archive_members(path, pin)

    def test_expansion_is_bounded(self):
        path, pin = self.archive([('package/a', b'12345')])
        with patch.object(inputs, 'MAX_EXPANDED', 4), self.assertRaisesRegex(ValueError, 'expanded archive'):
            inputs.archive_members(path, pin)

    def test_corrupted_cache_does_not_download_a_replacement(self):
        path, pin = self.archive([('package/a', b'a')])
        pin.update(archive=path.name, url='https://invalid.test/authored', sha256='0' * 64)
        with patch.object(inputs.urllib.request, 'urlopen') as download, self.assertRaisesRegex(ValueError, 'archive differs'):
            inputs.acquire_inputs(self.root, {'archives': [pin]})
        download.assert_not_called()

    def test_archive_or_internal_parent_link_is_not_canonicalized_away(self):
        path, pin = self.archive([('package/a', b'a')])
        for linked in (path, self.root):
            with self.subTest(linked=linked.name):
                with patch.object(Path, 'is_symlink', lambda candidate: candidate == linked), \
                        patch.object(Path, 'read_bytes') as read, \
                        self.assertRaisesRegex(ValueError, 'cannot traverse links'):
                    inputs.verified(path, pin)
                read.assert_not_called()

    def test_linked_cache_is_rejected_before_creating_directories(self):
        cache = self.root / 'redirected' / 'new-cache'
        with patch.object(Path, 'is_symlink', lambda candidate: candidate == cache.parent), \
                patch.object(Path, 'mkdir') as mkdir, \
                self.assertRaisesRegex(ValueError, 'cannot traverse links'):
            inputs.acquire_inputs(cache, {'archives': []})
        mkdir.assert_not_called()

    def test_pins_preserve_gpl_and_exact_runtime_terms(self):
        pins = inputs.read_pins()
        old = json.loads((ROOT / 'packaging/zzz-reader/inputs.json').read_text())
        by_name = {item['name']: item for item in pins['archives']}
        for name in ('ooz-wasm', 'xxhash-wasm', 'typescript'):
            self.assertEqual(by_name[name]['sha256'], old['npm'][name]['archive_sha256'])
        self.assertEqual(by_name['typescript']['role'], 'build-only')
        self.assertIn('package/LICENSE.md', [p['member'] for p in by_name['xxhash-wasm']['files']])
        self.assertEqual(pins['upstream']['sha256'], old['upstream_reader']['sha256'])


if __name__ == '__main__':
    unittest.main()
