"""Authored trust/publication fixtures; not actual FFmpeg/Windows acceptance."""
import importlib.util
import io
import json
from pathlib import Path
import struct
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


if __name__ == '__main__': unittest.main()
