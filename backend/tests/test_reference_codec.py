"""Source-kit trust failures are separate from frozen codec runtime checks."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('reference_codec_test', ROOT / 'scripts/reference-codec.py')
codec = importlib.util.module_from_spec(spec); spec.loader.exec_module(codec)


class SourceTrustTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def archive(self, extra=None, notice=b'authored notice'):
        path = self.root / 'source.tar.xz'
        with tarfile.open(path, 'w:xz') as tar:
            for name, data in [('flac-1.5.0/COPYING.GPL', notice),
                               ('flac-1.5.0/src/owned.c', b'/* Copyright authored fixture */\n#include <stdio.h>')]:
                entry = tarfile.TarInfo(name); entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data))
            if extra is not None: tar.addfile(extra)
        pin = {'version': '1.5.0', 'source': {'filename': path.name, 'sha256': codec.digest(path.read_bytes())},
               'notices': {'COPYING.GPL': codec.digest(b'authored notice')}}
        for name in codec.INPUTS:
            p = self.root / 'recipe' / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(pin) if name.endswith('.json') else 'authored recipe fixture')
        return path, self.root / 'recipe'

    def test_valid_source_kit_retains_exact_archive_recipes_and_notices(self):
        archive, recipe = self.archive()
        output = self.root / 'build'
        with patch.object(codec, 'ROOT', recipe): source = codec.prepare(archive, output)
        self.assertEqual((source / 'COPYING.GPL').read_bytes(), b'authored notice')
        self.assertEqual((output / 'source-kit/inputs/source.tar.xz').read_bytes(), archive.read_bytes())
        self.assertEqual(set(codec.inventory(output / 'source-kit')), {'inputs/source.tar.xz', *codec.INPUTS})
        self.assertIn('Copyright authored fixture', (output / 'candidate/notices/SOURCE-COPYRIGHTS.txt').read_text())

    def test_archive_traversal_links_aliases_and_devices_fail_before_writes(self):
        for kind in ['traversal', 'symlink', 'hardlink', 'case-alias', 'device']:
            with self.subTest(kind=kind):
                extra = tarfile.TarInfo('../external' if kind == 'traversal' else 'flac-1.5.0/other')
                if kind == 'symlink': extra.type, extra.linkname = tarfile.SYMTYPE, '../../external'
                if kind == 'hardlink': extra.type, extra.linkname = tarfile.LNKTYPE, '../../external'
                if kind == 'case-alias': extra.name = 'flac-1.5.0/copying.gpl'
                if kind == 'device': extra.type = tarfile.CHRTYPE
                archive, recipe = self.archive(extra)
                output = self.root / ('build-' + kind)
                with patch.object(codec, 'ROOT', recipe), self.assertRaises(ValueError):
                    codec.prepare(archive, output)
                self.assertFalse(output.exists())

    def test_changed_notice_and_archive_or_existing_destination_are_preserved(self):
        archive, recipe = self.archive(notice=b'changed notice')
        output = self.root / 'build'
        with patch.object(codec, 'ROOT', recipe), self.assertRaises(ValueError):
            codec.prepare(archive, output)
        self.assertFalse(output.exists())
        archive, recipe = self.archive()
        archive.write_bytes(b'changed archive')
        with patch.object(codec, 'ROOT', recipe), self.assertRaises(ValueError):
            codec.prepare(archive, output)
        output.mkdir(); (output / 'unrelated').write_bytes(b'keep')
        with patch.object(codec, 'ROOT', recipe), self.assertRaises(ValueError):
            codec.prepare(archive, output)
        self.assertEqual((output / 'unrelated').read_bytes(), b'keep')

    def test_linked_destination_never_changes_external_tree(self):
        archive, recipe = self.archive()
        external = self.root / 'external'; external.mkdir(); (external / 'keep').write_bytes(b'keep')
        link = self.root / 'link'
        try: link.symlink_to(external, target_is_directory=True)
        except OSError: self.skipTest('Symlink creation unavailable; archive trust failures still run.')
        with patch.object(codec, 'ROOT', recipe), self.assertRaises(ValueError):
            codec.prepare(archive, link / 'candidate')
        self.assertEqual(list(external.iterdir()), [external / 'keep'])


if __name__ == '__main__':
    unittest.main()
