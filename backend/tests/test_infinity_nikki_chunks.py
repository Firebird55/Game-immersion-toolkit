"""Authored BuildPatch data; no original package bytes or publisher hashes."""
from dataclasses import replace
import hashlib
import json
import struct
import unittest
import zlib

from backend.infinity_nikki_chunks import (
    WINDOW, decode_chunk, manifest_sources, parse_manifest, read_file_range, read_small_file,
)


ROOT = 'https://x6oversea-client.infoldgames.com/authoredtest/Rel_2.8/PaperHotUpdate/Protected'
URL = ROOT + '/HttpChunkInstall/Windows/3400/CloudDir/PaperHttpChunkInstall.manifest'
A, B = '0' * 31 + 'A', '0' * 31 + 'B'


def blob(raw):
    return ''.join(f'{byte:03d}' for byte in raw)


def number(value, width):
    return blob(value.to_bytes(width, 'little'))


def chunk(data, guid, rolling, compressed=True):
    payload = zlib.compress(data) if compressed else data
    raw = struct.pack('<4I', 0xb1fe3aa2, 2, 62, len(payload))
    raw += struct.pack('<4I', *(int(guid[i:i + 8], 16) for i in range(0, 32, 8)))
    raw += struct.pack('<QB', rolling, int(compressed)) + hashlib.sha1(data).digest() + bytes([3])
    return raw + payload


def fixture(*, revision=0, compressed=True):
    data = {A: (b'authored-a' + bytes([revision])).ljust(WINDOW, b'A'),
            B: (b'authored-b' + bytes([revision])).ljust(WINDOW, b'B')}
    rolls = {A: 0x0123456789abcdef + revision, B: 0xfedcba9876543210 - revision}
    carriers = {guid: chunk(value, guid, rolls[guid], compressed) for guid, value in data.items()}
    parts = [(A, 0, 512), (B, 0, 200)]
    selected = b''.join(data[guid][offset:offset + size] for guid, offset, size in parts)
    manifest = {'ManifestFileVersion': number(13, 4), 'bIsFileData': False,
        'AppNameString': 'PaperHttpChunkInstall', 'BuildVersionString': str(3400 + revision),
        'FileManifestList': [
            {'Filename': 'Framework.pak', 'FileHash': blob(hashlib.sha1(selected).digest()),
             'FileChunkParts': [{'Guid': g, 'Offset': number(o, 4), 'Size': number(n, 4)} for g, o, n in parts]},
            {'Filename': 'OtherBootstrapMovie.pak', 'FileHash': blob(hashlib.sha1(data[A][1024:1536]).digest()),
             'FileChunkParts': [{'Guid': A, 'Offset': number(1024, 4), 'Size': number(512, 4)}]},
            {'Filename': 'Empty.sig', 'FileHash': blob(hashlib.sha1(b'').digest()), 'FileChunkParts': []}],
        'ChunkHashList': {g: number(n, 8) for g, n in rolls.items()},
        'ChunkShaList': {g: hashlib.sha1(raw).hexdigest().upper() for g, raw in data.items()},
        'DataGroupList': {A: number(87, 1), B: number(3, 1)},
        'ChunkFilesizeList': {g: number(len(raw), 8) for g, raw in carriers.items()}}
    return manifest, carriers, data, selected


def parse(data, *, url=URL, version='3400'):
    raw = json.dumps(data, separators=(',', ':')).encode()
    return parse_manifest(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), manifest_url=url, expected_version=version)


class OriginalChunkTests(unittest.TestCase):
    def test_typed_ownership_exact_decimal_urls_sizes_and_shared_carrier_cost(self):
        data, carriers, plain, selected = fixture()
        manifest = parse(data)
        plan = manifest.plan(['Framework.pak'])
        self.assertEqual(plan.wire_bytes, sum(map(len, carriers.values())))
        self.assertEqual(plan.retained_file_bytes, len(selected))
        self.assertEqual(plan.temporary_decoded_bytes, WINDOW)
        self.assertEqual(plan.shared_carrier_guids, (A,))
        self.assertIn('/ChunksV3/87/0123456789ABCDEF_' + A + '.chunk', plan.chunks[0].url)
        self.assertIn('/ChunksV3/03/', plan.chunks[1].url)
        decoded = {owner.guid: decode_chunk(carriers[owner.guid], owner) for owner in plan.chunks}
        self.assertEqual(decoded, plain)
        self.assertEqual(read_small_file(plan.files[0], decoded.__getitem__), selected)
        self.assertEqual(read_file_range(plan.files[0], 500, 40, decoded.__getitem__), selected[500:540])
        empty = manifest.plan(['Empty.sig'])
        self.assertEqual((empty.wire_bytes, empty.retained_file_bytes, empty.temporary_decoded_bytes), (0, 0, 0))
        self.assertEqual(read_small_file(empty.files[0], decoded.__getitem__), b'')

    def test_new_normal_generation_changes_source_ownership_without_old_identity(self):
        data, carriers, _, selected = fixture(revision=1)
        manifest = parse(data, url=URL.replace('/3400/', '/3401/'), version='3401')
        plan = manifest.plan(['Framework.pak'])
        decoded = {owner.guid: decode_chunk(carriers[owner.guid], owner) for owner in plan.chunks}
        self.assertEqual(read_small_file(plan.files[0], decoded.__getitem__), selected)
        old = parse(fixture()[0])
        self.assertNotEqual(manifest.source_sha256, old.source_sha256)
        self.assertNotEqual(plan.chunks[0].url, old.chunks[0].url)
        build = {'DefaultVersion': '3401', 'FastPatchVersion': '28'}
        urls = manifest_sources(ROOT + '/BuildVersion/Windows/BuildVersion_3401.28.json', build)
        self.assertIn('/3401/CloudDir/', urls[0])
        self.assertIn('/3401/CloudFastPatchDir/28/', urls[1])

    def test_uncompressed_carriers_have_the_same_full_data_and_file_controls(self):
        data, carriers, _, selected = fixture(compressed=False)
        plan = parse(data).plan(['Framework.pak'])
        decoded = {owner.guid: decode_chunk(carriers[owner.guid], owner) for owner in plan.chunks}
        self.assertEqual(read_small_file(plan.files[0], decoded.__getitem__), selected)

    def test_rejects_unowned_sources_mismatched_generation_and_raw_identity(self):
        data = fixture()[0]
        for url, version in [(URL, '3401'),
                (URL.replace('x6oversea-client.infoldgames.com', 'untrusted.example'), '3400'),
                (URL + '?credential=no', '3400'), (URL.replace('/Windows/', '/Android/'), '3400')]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse(data, url=url, version=version)
        raw = json.dumps(data).encode()
        with self.assertRaises(ValueError):
            parse_manifest(raw, expected_sha256='0' * 64, manifest_url=URL, expected_version='3400')
        with self.assertRaises(ValueError):
            parse_manifest(b'{"duplicate":1,"duplicate":2}',
                expected_sha256=hashlib.sha256(b'{"duplicate":1,"duplicate":2}').hexdigest(),
                manifest_url=URL, expected_version='3400')

    def test_rejects_unknown_schemas_missing_owners_unsafe_names_and_unbounded_parts(self):
        mutations = [lambda d: d.update(ManifestFileVersion=number(15, 4)),
            lambda d: d.update(bIsFileData=True), lambda d: d['ChunkShaList'].pop(A),
            lambda d: d['DataGroupList'].update({A: number(100, 1)}),
            lambda d: d['ChunkHashList'].update({A: '999' * 8}),
            lambda d: d['FileManifestList'][0].update(Filename='../escape'),
            lambda d: d['FileManifestList'][1].update(Filename='FRAMEWORK.pak'),
            lambda d: d['FileManifestList'][0]['FileChunkParts'][0].update(Guid='F' * 32),
            lambda d: d['FileManifestList'][0]['FileChunkParts'][0].update(Offset=number(WINDOW, 4)),
            lambda d: d['FileManifestList'][0].update(FileHash='0' * 59)]
        for index, mutate in enumerate(mutations):
            data = fixture()[0]
            mutate(data)
            with self.subTest(case=index), self.assertRaises(ValueError):
                parse(data)

    def test_header_compression_integrity_and_full_window_are_enforced(self):
        data, carriers, _, _ = fixture()
        owner = parse(data).chunks[0]
        original = carriers[A]
        for offset in (0, 4, 8, 12, 16, 32, 40, 41, 61, 70, len(original) - 1):
            changed = bytearray(original)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode_chunk(bytes(changed), owner)
        for decoded in (b'too short', b'A' * (WINDOW + 1)):
            wrong = chunk(decoded, A, owner.rolling_hash)
            with self.subTest(size=len(decoded)), self.assertRaises(ValueError):
                decode_chunk(wrong, replace(owner, packed_bytes=len(wrong), sha1=hashlib.sha1(decoded).digest()))
        trailing = bytearray(original + b'trailing')
        struct.pack_into('<I', trailing, 12, len(trailing) - 62)
        with self.assertRaises(ValueError):
            decode_chunk(bytes(trailing), replace(owner, packed_bytes=len(trailing)))

    def test_file_ranges_and_final_hash_cannot_activate_wrong_or_missing_data(self):
        data, _, plain, _ = fixture()
        manifest = parse(data)
        file = manifest.plan(['Framework.pak']).files[0]
        for offset, size in [(-1, 2), (0, file.size + 1), (file.size, 1)]:
            with self.subTest(offset=offset, size=size), self.assertRaises(ValueError):
                read_file_range(file, offset, size, plain.__getitem__)
        for getter in [lambda _: b'', lambda _: b'X' * WINDOW]:
            with self.subTest(getter=getter), self.assertRaises(ValueError):
                read_small_file(file, getter)
        for names in ([], ['Framework.pak'] * 2, ['missing.pak'], [{}]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                manifest.plan(names)


if __name__ == '__main__':
    unittest.main()
