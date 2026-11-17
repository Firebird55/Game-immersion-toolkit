import hashlib
import struct
import unittest

from backend.infinity_nikki_inventory import (MAX_EXPANDED, MAX_PACKED, build_version_urls, decode_inventory,
                                             inventory_envelope, inventory_sources, parse_inventory_payload)


def integer(value):
    return struct.pack('<i', value)


def string(value, *, wide=False):
    if wide:
        raw = value.encode('utf-16-le') + b'\0\0'
        return integer(-len(raw) // 2) + raw
    raw = value.encode('utf-8') + b'\0'
    return integer(len(raw)) + raw


def mapping(rows, binary):
    return integer(len(rows)) + b''.join((key if binary else string(key)) + string(value) for key, value in rows)


def record(name='Fixture_Text_10_P.pak', *, digest='a' * 32, mount='../../../X6Game/Content/',
           binary_a=(), text=(), binary_b=()):
    return (string(name) + string(digest) + string(mount) + mapping(binary_a, True) +
            mapping(text, False) + mapping(binary_b, True))


class InventoryTests(unittest.TestCase):
    def test_original_primary_backup_pointer_list_keeps_one_evidenced_generation(self):
        url = ('https://x6oversea-client.infoldgames.com/source_object_123/Rel_3.1/PaperHotUpdate/'
               'Protected/BuildVersion/Windows/BuildVersion_10.8.json')
        backup = url.replace('x6oversea-client.', 'x6oversea-client-backup.')
        self.assertEqual(build_version_urls(url + ';' + backup), (url, backup))
        self.assertTrue(inventory_sources(backup, {'DefaultVersion': '10', 'FastPatchVersion': '8'})[0].url.startswith(
            'https://x6oversea-client-backup.infoldgames.com/'))
        for pointer in (url + ';', url + ';' + url, url + ';' + backup.replace('10.8', '11.8'),
                        url + ';' + backup.replace('x6oversea-client-backup.infoldgames.com', 'unrelated.invalid')):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                build_version_urls(pointer)

    def test_current_sdk_source_templates_follow_normal_version_changes(self):
        for version, patch in [('10', '0'), ('12', '8'), ('1401', '128')]:
            url = ('https://x6oversea-client.infoldgames.com/source_object_123/Rel_3.1/PaperHotUpdate/'
                   f'Protected/BuildVersion/Windows/BuildVersion_{version}.{patch}.json')
            sources = inventory_sources(url, {'DefaultVersion': version, 'FastPatchVersion': patch})
            self.assertEqual([s.role for s in sources], ['base-json', 'base-binary', 'hotfix-binary', 'file-pak-map'])
            self.assertTrue(sources[2].url.endswith(f'HashFiles/Windows/{version}/PaperHashFiles_{version}.{patch}.bin'))
            self.assertEqual((sources[2].version, sources[2].fast_patch), (version, patch))

    def test_source_root_region_platform_and_generation_are_not_guessed(self):
        url = ('https://x6oversea-client.infoldgames.com/source_object_123/Rel_3.1/PaperHotUpdate/'
               'Protected/BuildVersion/Windows/BuildVersion_10.8.json')
        for bad in [url.replace('x6oversea-client.infoldgames.com', 'unrelated.invalid'),
                    url.replace('source_object_123', '..'), url.replace('/Windows/', '/Android/'),
                    url.replace('https:', 'http:'), url + '?account=example', url + '#fragment',
                    url.replace('source_object_123', 'source%2Fobject'),
                    url.replace('://', '://user@'), url.replace('BuildVersion_10', 'BuildVersion_11')]:
            with self.subTest(url=bad), self.assertRaises(ValueError):
                inventory_sources(bad, {'DefaultVersion': '10', 'FastPatchVersion': '8'})

    def test_envelope_quotes_full_transport_and_temporary_decode_before_payload(self):
        header = struct.pack('<IBI', 0x20240418, 1, 10000)
        plan = inventory_envelope(header, 1234)
        self.assertEqual((plan.packed_bytes, plan.expanded_bytes, plan.header_bytes), (1234, 10000, 9))
        for prefix, total in [(header[:8], 1234), (header, 8), (header, MAX_PACKED + 1),
                              (struct.pack('<IBI', 0, 1, 100), 1234),
                              (struct.pack('<IBI', 0x20240418, 0, 100), 1234),
                              (struct.pack('<IBI', 0x20240418, 1, MAX_EXPANDED + 1), 1234)]:
            with self.subTest(total=total), self.assertRaises(ValueError):
                inventory_envelope(prefix, total)

    def test_all_three_original_maps_remain_opaque_and_empty_values_survive(self):
        key_a, key_b = b'A' * 12, b'B' * 12
        raw = integer(2) + record(binary_a=[(key_a, 'b' * 40)], text=[('配置/example.bin', 'c' * 40)],
                                  binary_b=[(key_b, 'Original/Path/NotADigest')]) + record('Fixture_VOICE_TEST_11_P.pak')
        result = parse_inventory_payload(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].binary_map_a, ((key_a, 'b' * 40),))
        self.assertEqual(result[0].text_map, (('配置/example.bin', 'c' * 40),))
        self.assertEqual(result[0].binary_map_b, ((key_b, 'Original/Path/NotADigest'),))
        raw = integer(1) + record(binary_a=[(key_a, '')], text=[('name', '')], binary_b=[(key_b, '')])
        self.assertEqual(parse_inventory_payload(raw)[0].binary_map_b[0][1], '')

    def test_wide_original_mount_string_and_empty_inventory(self):
        raw = integer(1) + string('Fixture.pak') + string('0' * 32) + string('../../../示例/', wide=True) + integer(0) * 3
        self.assertEqual(parse_inventory_payload(raw)[0].mount, '../../../示例/')
        self.assertEqual(parse_inventory_payload(integer(0)), ())

    def test_duplicates_truncation_trailing_bytes_and_count_bombs_are_refused(self):
        key = b'A' * 12
        cases = [integer(2) + record() + record(), integer(2) + record() + record('fixture_text_10_p.pak'),
                 integer(1) + record(binary_a=[(key, 'a'), (key, 'b')]),
                 integer(1) + record(text=[('name', 'a'), ('name', 'b')]),
                 integer(1) + record(digest='not a hash'), integer(1) + record(name='../escape.pak'),
                 integer(1) + record()[:-1], integer(1) + record() + b'x',
                 integer(2**31 - 1), integer(-1), integer(1) + integer(-2**31)]
        for raw in cases:
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                parse_inventory_payload(raw)

    def test_source_hash_is_checked_before_decoder_and_only_payload_is_passed(self):
        payload = integer(1) + record()
        packed = struct.pack('<IBI', 0x20240418, 1, len(payload)) + b'authored compressed fixture'
        calls = []

        def decoder(raw, expected):
            calls.append((raw, expected))
            return payload

        with self.assertRaises(ValueError):
            decode_inventory(packed, expected_sha256='0' * 64, decompress=decoder)
        self.assertFalse(calls)
        result = decode_inventory(packed, expected_sha256=hashlib.sha256(packed).hexdigest(), decompress=decoder)
        self.assertEqual(result[0].name, 'Fixture_Text_10_P.pak')
        self.assertEqual(calls, [(b'authored compressed fixture', len(payload))])
        for bad in (payload[:-1], payload + b'x', bytearray(payload)):
            with self.assertRaises(ValueError):
                decode_inventory(packed, expected_sha256=hashlib.sha256(packed).hexdigest(), decompress=lambda *_: bad)


if __name__ == '__main__':
    unittest.main()
