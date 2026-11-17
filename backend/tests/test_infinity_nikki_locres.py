"""Authored stock-v3 resources; no original translations or package bytes."""
from dataclasses import replace
import struct
import unittest

from backend.infinity_nikki_locres import MAGIC, parse_locres, translation_index


def fstring(value, *, wide=False):
    wide = wide or any(ord(char) > 127 for char in value)
    raw = value.encode('utf-16-le' if wide else 'utf-8')
    count = -(len(raw) // 2 + 1) if wide else len(raw) + 1
    return struct.pack('<i', count) + raw + (b'\0\0' if wide else b'\0')


def resource(rows, *, wide=False, failure=None):
    groups, strings, references = [], [], []
    for namespace, key, source_hash, value in rows:
        if value not in strings:
            strings.append(value)
            references.append(0)
        index = strings.index(value)
        references[index] += 1
        if not groups or groups[-1][0] != namespace or failure == 'duplicate-namespace':
            groups.append((namespace, []))
        groups[-1][1].append((key, source_hash, index))
    table = bytearray()
    for namespace, entries in groups:
        table += struct.pack('<I', 0xffffffff) + fstring(namespace, wide=wide) + struct.pack('<i', len(entries))
        for key, source_hash, index in entries:
            table += struct.pack('<I', 0xfffffffe) + fstring(key, wide=wide)
            table += struct.pack('<Ii', source_hash, -1 if failure == 'bad-pool-index' else index)
    pool = bytearray(struct.pack('<i', len(strings)))
    for value, count in zip(strings, references):
        pool += fstring(value, wide=wide) + struct.pack('<i', -1 if failure == 'opaque-references' else count)
    raw = bytearray(MAGIC + struct.pack('<Bqii', 3, 33 + len(table), len(rows), len(groups)) + table + pool)
    if failure == 'wrong-entry-count':
        struct.pack_into('<i', raw, 25, len(rows) + 1)
    elif failure == 'bad-offset':
        struct.pack_into('<q', raw, 17, 32)
    elif failure == 'pool-offset-outside':
        struct.pack_into('<q', raw, 17, len(raw))
    elif failure == 'count-limit':
        struct.pack_into('<i', raw, 25, 2**31 - 1)
    elif failure == 'namespace-limit':
        struct.pack_into('<i', raw, 29, 2**31 - 1)
    elif failure == 'bad-key-length':
        struct.pack_into('<i', raw, 37, -(2**31))
    elif failure == 'pool-trailing':
        raw += b'\0'
    return bytes(raw)


class OriginalLocresTests(unittest.TestCase):
    def test_identity_pool_reuse_unicode_and_empty_namespaces_are_preserved(self):
        rows = [('', 'caption', 0xffffffff, 'Authored text.'),
                ('', 'another-caption', 2, 'Authored text.'),
                ('場面', 'speaker', 3, '名前 😀'), ('場面', 'empty', 0, '')]
        for wide in (False, True):
            with self.subTest(wide=wide):
                parsed = parse_locres(resource(rows, wide=wide))
                self.assertEqual([(r.namespace, r.key, r.source_hash, r.value) for r in parsed], rows)
                self.assertEqual(parsed[0].identity, ('', 'caption', 0xffffffff))
                self.assertEqual(parsed[0].namespace_hash, 0xffffffff)
                self.assertEqual(parsed[0].key_hash, 0xfffffffe)
                self.assertNotIn('Authored text.', repr(parsed[0]))
                self.assertEqual(len(translation_index(parsed)), 4)

    def test_translation_join_uses_namespace_key_and_source_hash_not_display_text(self):
        source = parse_locres(resource([('', 'caption', 10, 'Same short sentence.'),
                                        ('', 'other-caption', 11, 'Same short sentence.')]))
        target = parse_locres(resource([('', 'caption', 10, '短い文。'), ('', 'other-caption', 11, '別の文。')]))
        index = translation_index(target)
        self.assertEqual(index[source[0].identity].value, '短い文。')
        self.assertEqual(index[source[1].identity].value, '別の文。')
        self.assertNotIn(replace(source[0], source_hash=99).identity, index)
        self.assertNotIn(replace(source[0], namespace='another').identity, index)

    def test_normal_new_resource_generation_uses_new_keys_and_changed_source_hashes(self):
        before = parse_locres(resource([('scene', 'old', 1, 'Old fixture.')]))
        after = parse_locres(resource([('scene', 'old', 2, 'Updated fixture.'),
                                       ('scene', 'new', 3, 'A new fixture.')]))
        index = translation_index(after)
        self.assertNotIn(before[0].identity, index)
        self.assertEqual(len(index), 2)

    def test_empty_resources_and_opaque_reference_counts_do_not_invent_dialogue(self):
        self.assertEqual(parse_locres(resource([])), ())
        parsed = parse_locres(resource([('', 'key', 0, '')], failure='opaque-references'))
        self.assertEqual(parsed[0].value, '')
        self.assertFalse(hasattr(parsed[0], 'voice_status'))
        self.assertFalse(hasattr(parsed[0], 'text_capture_verified'))

    def test_rejects_duplicate_namespace_keys_and_index_identity_collisions(self):
        with self.assertRaises(ValueError):
            parse_locres(resource([('', 'same', 1, 'First.'), ('', 'same', 2, 'Second.')]))
        with self.assertRaises(ValueError):
            parse_locres(resource([('', 'first', 1, 'First.'), ('', 'second', 2, 'Second.')], failure='duplicate-namespace'))
        parsed = parse_locres(resource([('', 'same', 1, 'First.')]))
        with self.assertRaises(ValueError):
            translation_index([parsed[0], replace(parsed[0], value='Another fixture.')])

    def test_rejects_malformed_counts_offsets_pool_indexes_and_trailing_bytes(self):
        rows = [('', 'key', 7, 'Fixture.')]
        for failure in ('wrong-entry-count', 'bad-offset', 'pool-offset-outside', 'count-limit',
                        'namespace-limit', 'bad-key-length', 'bad-pool-index', 'pool-trailing'):
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                parse_locres(resource(rows, failure=failure))
        original = resource(rows)
        for value in (original[:-1], original[:33], bytearray(original)):
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                parse_locres(value)
        for offset in (0, 16):
            changed = bytearray(original)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parse_locres(bytes(changed))

    def test_rejects_missing_terminators_invalid_unicode_and_embedded_key_nuls(self):
        for rows in [('', 'bad\0key', 1, 'Fixture.'), ('bad\0namespace', 'key', 1, 'Fixture.')]:
            with self.subTest(key=rows[1]), self.assertRaises(ValueError):
                parse_locres(resource([rows]))
        raw = bytearray(resource([('', 'key', 1, 'Fixture.')]))
        offset = struct.unpack_from('<q', raw, 17)[0]
        raw[-5] = 1  # String-pool terminator immediately precedes its reference count.
        with self.assertRaises(ValueError):
            parse_locres(bytes(raw))
        raw = bytearray(resource([('', 'key', 1, '字')]))
        offset = struct.unpack_from('<q', raw, 17)[0]
        struct.pack_into('<H', raw, offset + 8, 0xd800)
        with self.assertRaises(ValueError):
            parse_locres(bytes(raw))


if __name__ == '__main__':
    unittest.main()
