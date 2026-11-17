"""Authored source-owned framing fixtures, parsed only as data."""
import struct
import math
import unittest

from backend.infinity_nikki_lua_metadata import HEADER, MAX_CHUNK, parse_metadata


def unsigned(value):
    result = bytearray([value & 127 | 128])
    value >>= 7
    while value:
        result.insert(0, value & 127)
        value >>= 7
    return bytes(result)


def string(value):
    if value is None:
        return b'\x80'
    raw = value.encode('utf-8')
    return unsigned(len(raw) + 1) + raw


def prototype(*, source='@Authored/Updater.lua', children=(), failure=None,
              constants=('normal revision',), revision=1):
    code = struct.pack('<II', 0x01020304, revision)
    result = string(source) + unsigned(128) + unsigned(512) + bytes([1, 1, 3]) + unsigned(2) + code
    values = [b'\0', b'\1', b'\x11', b'\3' + struct.pack('<d', 12.5),
              b'\x13' + struct.pack('<q', -123456789), b'\x14' + string('long form'),
              *(b'\4' + string(value) for value in constants)]
    if failure == 'constant-tag':
        values[0] = b'\xff'
    elif failure == 'null-constant':
        values[-1] = b'\4\x80'
    elif failure == 'nonfinite-number':
        values[3] = b'\3' + struct.pack('<d', float('nan'))
    result += unsigned(len(values)) + b''.join(values)
    result += unsigned(1) + bytes([1, 0, 0])
    result += unsigned(len(children)) + b''.join(children)
    result += unsigned(2) + bytes([0, 1])
    result += unsigned(1) + unsigned(0) + unsigned(128)
    result += unsigned(1) + string('local data') + unsigned(2 if failure == 'local-range' else 0) + unsigned(1)
    result += unsigned(2 if failure == 'upvalue-names' else 1) + string('_ENV')
    return result


def chunk(tree=None, *, failure=None):
    header = HEADER + struct.pack('<qd', 0x5678, 370.5) + bytes([2 if failure == 'root-upvalues' else 1])
    return header + (tree if tree is not None else prototype(failure=failure))


class UpdaterMetadataTests(unittest.TestCase):
    def test_all_actual_constant_kinds_source_inheritance_and_metadata(self):
        child = prototype(source=None, constants=('子元数据',))
        root = parse_metadata(chunk(prototype(children=(child,))))
        self.assertEqual(root.first_line, 128)
        self.assertEqual(root.last_line, 512)
        self.assertEqual(root.constants, (None, False, True, 12.5, -123456789, 'long form', 'normal revision'))
        self.assertEqual(root.prototypes[0].source, root.source)
        self.assertEqual(root.prototypes[0].constants[-1], '子元数据')
        self.assertEqual(root.instructions, (0x01020304, 1))
        self.assertEqual(root.absolute_lines, ((0, 128),))
        self.assertEqual(root.locals, (('local data', 0, 1),))
        self.assertEqual(root.upvalue_names, ('_ENV',))
        self.assertNotIn('Authored', repr(root))
        self.assertNotIn('normal revision', repr(root))
        empty = parse_metadata(chunk(prototype(children=(prototype(source=''),))))
        self.assertEqual(empty.prototypes[0].source, '')

    def test_new_source_generation_retains_authored_changes_without_running_it(self):
        old = parse_metadata(chunk())
        new = parse_metadata(chunk(prototype(source='@New/Updater.lua', revision=54,
                                            constants=('HashFiles/%s/%s/new_%s.bin',))))
        self.assertNotEqual(new.source, old.source)
        self.assertEqual(new.instructions[-1], 54)
        self.assertEqual(new.constants[-1], 'HashFiles/%s/%s/new_%s.bin')

    def test_rejects_unsupported_tags_invalid_framing_debug_counts_and_limits(self):
        for failure in ('constant-tag', 'null-constant', 'local-range',
                        'upvalue-names', 'root-upvalues'):
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                parse_metadata(chunk(failure=failure))
        original = chunk()
        for value in (original + b'\0', original[:-1], original[:31], b'\0' * (MAX_CHUNK + 1), bytearray(original)):
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                parse_metadata(value)
        for offset in (4, 12, 15, 23):
            changed = bytearray(original)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parse_metadata(bytes(changed))

    def test_original_number_bit_patterns_are_data_even_when_nonfinite(self):
        parsed = parse_metadata(chunk(failure='nonfinite-number'))
        self.assertTrue(math.isnan(parsed.constants[3]))

    def test_rejects_unterminated_or_oversized_integers_and_strings(self):
        for encoded in (bytes(10), unsigned(65537), unsigned(65536) + b'not a complete source'):
            with self.subTest(encoded=len(encoded)), self.assertRaises(ValueError):
                parse_metadata(chunk(encoded))

    def test_recursion_and_total_prototype_count_are_bounded(self):
        tree = prototype(source=None)
        for _ in range(65):
            tree = prototype(source=None, children=(tree,))
        with self.assertRaises(ValueError):
            parse_metadata(chunk(tree))
        # Declares too many children before allocating or visiting any of them.
        prefix = string(None) + unsigned(0) * 2 + bytes([0, 0, 1])
        prefix += unsigned(0) * 3 + unsigned(5000)
        with self.assertRaises(ValueError):
            parse_metadata(chunk(prefix))


if __name__ == '__main__':
    unittest.main()
