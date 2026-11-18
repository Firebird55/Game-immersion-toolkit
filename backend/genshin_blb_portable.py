"""Bounded, inert BLB3 transformation; not a provider or authenticity check.

Format port of the MIT BlbUtils.cs software pinned by
packaging/genshin-reader/inputs.json (AnimeStudio, revision 76234e9).
Its license remains in packaging/genshin-reader/AnimeStudio-LICENSE.txt.
No original CryptoHelper or game-specific parameter values are included.

The caller authenticates the complete original input and owns the nine supplied
arrays. This module preserves the managed helper's custom algorithm, including
its intentionally AES-like Encrypt step; ordinary AES is not interchangeable.
Decoded output still needs the existing bounded decompressor, complete object
map/typed readers, source receipt and generation acceptance. No runtime/factory
is enabled by this module. Only the standard library is imported.
"""
import base64
import hashlib
import importlib.util
import json
import marshal
from pathlib import Path
import struct
import sys
from types import CodeType, FunctionType


PARAMETERS = {'GF256Exp': 256, 'GF256Log': 256, 'Blb3AESSBox': 256,
              'Blb3AESShift': 16, 'Blb3RC4Key': 256, 'Blb3SBox': 1024,
              'Blb3ShiftRow': 48, 'Blb3Key': 8, 'Blb3Mul': 8}
MAX_PACKAGE = 160 * 1024**2
MAX_HEADER = 1024**2
MAX_BLOCKS = 8192
MAX_TRANSFORMS = MAX_BLOCKS + 1
_SHIFT = (0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11)
_RCON = (1, 2, 4, 8, 16, 32, 64, 128, 27, 54)
SOFTWARE = 'toolkit-portable-blb3-v1'


def _check(value):
    if not value:
        raise ValueError('Unsupported or incomplete original BLB3 container.')


def _unique(items):
    result = {}
    for name, value in items:
        _check(name not in result)
        result[name] = value
    return result


def parse_parameters(raw):
    """Read fixed-length Base64 byte arrays, never code or implicit defaults."""
    _check(isinstance(raw, bytes) and 0 < len(raw) <= 32 * 1024)
    try:
        rows = json.loads(raw, object_pairs_hook=_unique)
        _check(isinstance(rows, dict) and rows.keys() == PARAMETERS.keys())
        result = {}
        for name, size in PARAMETERS.items():
            _check(isinstance(rows[name], str))
            value = base64.b64decode(rows[name], validate=True)
            _check(len(value) == size)
            result[name] = value
        _check(all(index < 16 for index in result['Blb3AESShift']))
        return result
    except (UnicodeError, TypeError, ValueError) as error:
        raise ValueError('Unsupported or incomplete BLB3 parameter data.') from error


def _expand(key, p):
    box = p['Blb3AESSBox']
    keys = bytearray(176)
    keys[:16] = bytes(key[i] for i in p['Blb3AESShift'])
    offset = 31
    for power in _RCON:
        a = box[keys[offset - 20]]
        b = box[keys[offset - 16]]
        c = box[keys[offset - 24]] ^ keys[offset - 24] ^ power ^ keys[offset - 31]
        d = box[keys[offset - 28]]
        keys[offset - 15] = c
        temp = a ^ keys[offset - 20] ^ keys[offset - 27]
        keys[offset - 11] = temp
        a = b ^ keys[offset - 16] ^ keys[offset - 23]
        keys[offset - 7] = a
        b = d ^ keys[offset - 28] ^ keys[offset - 19]
        keys[offset - 3] = b
        c ^= keys[offset - 30]; keys[offset - 14] = c
        temp ^= keys[offset - 26]; keys[offset - 10] = temp
        a ^= keys[offset - 22]; keys[offset - 6] = a
        b ^= keys[offset - 18]; keys[offset - 2] = b
        c ^= keys[offset - 29]; keys[offset - 13] = c
        temp ^= keys[offset - 25]; keys[offset - 9] = temp
        a ^= keys[offset - 21]; keys[offset - 5] = a
        b ^= keys[offset - 17]; keys[offset - 1] = b
        keys[offset - 12] = c ^ keys[offset - 28]
        keys[offset - 8] = temp ^ keys[offset - 24]
        keys[offset - 4] = a ^ keys[offset - 20]
        keys[offset] = b ^ keys[offset - 16]
        offset += 16
    return keys


def _xtime(value):
    return ((value << 1) ^ (0x11b if value & 128 else 0)) & 255


def _encrypt(state, expanded, box):
    def round_key(number):
        for i in range(4):
            for j in range(4):
                state[i * 4 + j] ^= expanded[i + j * 4 + number * 16]

    round_key(0)
    for number in range(1, 11):
        # The custom substitution XORs its lookup into the original byte.
        state[:] = bytes(value ^ box[value] for value in state)
        previous = bytes(state)
        state[:] = bytes(previous[index] for index in _SHIFT)
        if number != 10:
            for off in range(0, 16, 4):
                a, b, c, d = state[off:off + 4]
                common = a ^ b ^ c ^ d
                state[off:off + 4] = bytes((a ^ common ^ _xtime(a ^ b),
                    b ^ common ^ _xtime(b ^ c), c ^ common ^ _xtime(c ^ d),
                    d ^ common ^ _xtime(d ^ a)))
        round_key(number)


class _Codec:
    def __init__(self, parameters, key):
        self.p = parameters
        self.key = key
        self.expanded = _expand(key, parameters)

    def prefix(self, raw):
        """Transform at most 128 bytes, restarting all state for each block."""
        _check(isinstance(raw, bytes) and len(raw) <= 128)
        buf = bytearray(raw)
        for i in range(min(16, len(buf))):
            buf[i] ^= self.key[i]
        if len(buf) < 16:
            return bytes(buf)
        first = buf[:16]
        _encrypt(first, self.expanded, self.p['Blb3AESSBox'])
        buf[:16] = first
        if len(buf) > 16:
            s = bytearray(self.p['Blb3RC4Key'])
            j = 0
            for i in range(256):
                # Even i & 6 and odd i & 7 equal i & 7.
                j = (j + s[i] + buf[i & 7]) & 255
                s[i], s[j] = s[j], s[i]
            i = j = 0
            for at in range(16, len(buf)):
                i = (i + 1) & 255
                j = (j + s[i]) & 255
                s[i], s[j] = s[j], s[i]
                value = s[(s[j] + s[i]) & 255]
                mode = buf[(i % 8) + 8] % 3
                if mode == 0:
                    buf[at] ^= value
                elif mode == 1:
                    buf[at] = (buf[at] - value) & 255
                else:
                    buf[at] = (buf[at] + value) & 255
        for number in range(3):
            vector = bytearray(16)
            for j in range(16):
                a = self.p['Blb3Mul'][j % 8]
                b = buf[self.p['Blb3ShiftRow'][(2 - number) * 16 + j] % 16]
                product = (self.p['GF256Exp'][(self.p['GF256Log'][a]
                    + self.p['GF256Log'][b]) % 255] if a and b else 0)
                vector[j] = (self.p['Blb3Key'][j % 8]
                    ^ self.p['Blb3SBox'][(j % 4) * 256 + product])
            buf[:16] = vector
        return bytes(buf)


def decode_file(source, parameters, destination, *, transform_budget=MAX_TRANSFORMS,
                check_cancel=lambda: None):
    """Decode to a new file with bounded memory/work and failed-output cleanup.

    Parameters is a private JSON file, matching Helper.decode's data contract.
    No subprocess, .NET, network, native runtime or original code is invoked.
    Caller authentication/typed acceptance remains mandatory after this step.
    """
    _check(type(transform_budget) is int and 1 <= transform_budget <= MAX_TRANSFORMS)
    paths = [Path(value).absolute() for value in (source, parameters, destination)]
    _check(len(set(path.resolve() for path in paths)) == 3
           and not any(path.is_symlink() for path in paths) and not paths[2].exists())
    source, parameters, destination = paths
    with parameters.open('rb') as stream:
        p = parse_parameters(stream.read(32 * 1024 + 1))
    with source.open('rb') as stream:
        stream.seek(0, 2); total = stream.tell(); stream.seek(0)
        _check(84 <= total <= MAX_PACKAGE)
        prefix = stream.read(28)
        _check(prefix[:4] == b'Blb\x03')
        size = struct.unpack_from('<i', prefix, 4)[0]
        _check(56 <= size <= MAX_HEADER and size <= total - 28)
        codec = _Codec(p, prefix[12:28])
        check_cancel()
        header = bytearray(stream.read(size))
        _check(len(header) == size)
        n = min(128, size)
        header[:n] = codec.prefix(bytes(header[:n]))
        count = struct.unpack_from('<i', header, 24)[0]
        table = 32 + struct.unpack_from('<q', header, 32)[0]
        _check(struct.unpack_from('<i', header)[0] == total
               and 1 <= count <= MAX_BLOCKS and count + 1 <= transform_budget
               and 56 <= table <= size - count * 4)
        ends = struct.unpack_from('<' + 'i' * count, header, table)
        body = 28 + size
        previous = 0
        for end in ends:
            _check(previous < end <= total - body)
            previous = end
        _check(body + previous == total)
        created = False
        try:
            with destination.open('xb') as output:
                created = True
                output.write(prefix); output.write(header)
                previous = 0
                for end in ends:
                    check_cancel()
                    remaining = end - previous
                    n = min(128, remaining)
                    raw = stream.read(n); _check(len(raw) == n)
                    output.write(codec.prefix(raw)); remaining -= n
                    while remaining:
                        check_cancel()
                        raw = stream.read(min(64 * 1024, remaining))
                        _check(raw)
                        output.write(raw); remaining -= len(raw)
                    previous = end
                _check(not stream.read(1))
                check_cancel()
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise


def _normalise(code):
    # Installed Python loaders need not expose editable .py files. Bind their
    # complete code object without binding the caller's installation directory.
    return code.replace(co_filename='toolkit/genshin_blb_portable.py', co_consts=tuple(
        _normalise(value) if isinstance(value, CodeType) else value for value in code.co_consts))


def _software_identity():
    try:
        spec = importlib.util.find_spec(__name__)
        _check(spec is not None and hasattr(spec.loader, 'get_code'))
        code = spec.loader.get_code(__name__)
    except (ImportError, OSError, SyntaxError, TypeError) as error:
        raise ValueError('The owned portable BLB3 software is unavailable.') from error
    _check(isinstance(code, CodeType))
    declared = {}
    def visit(current):
        declared[current.co_qualname] = _normalise(current)
        for value in current.co_consts:
            if isinstance(value, CodeType):
                visit(value)
    visit(code)
    # Detect a stale on-disk/module-loader body beside already imported code;
    # recording the replacement's digest must not bless the old implementation.
    actual = []
    for value in vars(sys.modules[__name__]).values():
        if isinstance(value, FunctionType) and value.__module__ == __name__:
            actual.append(value.__code__)
        elif isinstance(value, type) and value.__module__ == __name__:
            for item in vars(value).values():
                if isinstance(item, FunctionType):
                    actual.append(item.__code__)
                elif isinstance(item, property) and item.fget is not None:
                    actual.append(item.fget.__code__)
    _check(actual and all(declared.get(item.co_qualname) == _normalise(item) for item in actual))
    contract = json.dumps({'software': SOFTWARE, 'parameters': PARAMETERS,
        'max_package': MAX_PACKAGE, 'max_header': MAX_HEADER, 'max_blocks': MAX_BLOCKS,
        'max_transforms': MAX_TRANSFORMS, 'shift': _SHIFT, 'rcon': _RCON}, sort_keys=True).encode()
    encoded = marshal.dumps(_normalise(code))
    _check(0 < len(encoded) <= 1024**2)
    return hashlib.sha256(contract + encoded).hexdigest()


class PortableHelper:
    """Owned software identity and the existing Helper.decode file contract.

    Code/contract changes invalidate previous receipts; parameters never enter
    software identity. Corrupt or unavailable loader evidence fails closed.
    This interface grants no Android capability or publisher-generation trust.
    """
    def __init__(self):
        self._identity = _software_identity()

    @property
    def identity(self):
        current = _software_identity()
        _check(current == self._identity)
        return current

    def decode(self, source, parameters, destination, *, work):
        _check(self.identity and Path(work).is_dir())
        decode_file(source, parameters, destination)
