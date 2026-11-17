"""Parse original updater Lua bytecode as bounded metadata, without a Lua VM.

The source-owned chunk has a 0x53 version tag with the evidenced variable-integer
prototype framing. This reader does not rename that format to stock Lua 5.3,
execute instructions, or treat strings as trusted download targets.
"""
from dataclasses import dataclass, field
import struct


MAX_CHUNK = 4 * 1024**2
MAX_FUNCTIONS = 5000
HEADER = b'\x1bLua\x53\0\x19\x93\r\n\x1a\n\x04\x08\x08'


def _check(value):
    if not value:
        raise ValueError('Could not verify the current official Infinity Nikki updater metadata.')


@dataclass(frozen=True)
class Prototype:
    source: str | None = field(repr=False)
    first_line: int
    last_line: int
    parameters: int
    vararg: int
    stack: int
    instructions: tuple[int, ...] = field(repr=False)
    constants: tuple = field(repr=False)
    upvalues: tuple[bytes, ...] = field(repr=False)
    prototypes: tuple = field(repr=False)
    line_info: bytes = field(repr=False)
    absolute_lines: tuple[tuple[int, int], ...] = field(repr=False)
    locals: tuple = field(repr=False)
    upvalue_names: tuple = field(repr=False)


class _Reader:
    def __init__(self, raw):
        self.raw, self.at, self.functions = raw, 0, 0

    def take(self, count):
        _check(type(count) is int and 0 <= count <= len(self.raw) - self.at)
        value = self.raw[self.at:self.at + count]
        self.at += count
        return value

    def byte(self):
        return self.take(1)[0]

    def unsigned(self, limit=2**31 - 1):
        value = 0
        for _ in range(10):
            byte = self.byte()
            value = (value << 7) | (byte & 127)
            _check(value <= limit)
            if byte & 128:
                return value
        raise ValueError('The original updater integer has no bounded terminator.')

    def string_bytes(self):
        count = self.unsigned(65536)
        return self.take(count - 1) if count else None

    def string(self):
        value = self.string_bytes()
        return value.decode('utf-8') if value is not None else None

    def prototype(self, parent=None, depth=0):
        self.functions += 1
        _check(self.functions <= MAX_FUNCTIONS and depth <= 64)
        source = self.string()
        if source is None:
            source = parent
        first, last = self.unsigned(), self.unsigned()
        parameters, vararg, stack = self.byte(), self.byte(), self.byte()
        _check(parameters <= stack and vararg in (0, 1))
        count = self.unsigned(len(self.raw) // 4)
        code = tuple(item[0] for item in struct.iter_unpack('<I', self.take(count * 4)))
        constants = []
        for _ in range(self.unsigned(len(self.raw))):
            kind = self.byte()
            if kind == 0:
                value = None
            elif kind in (1, 17):
                value = kind == 17
            elif kind == 3:
                value = struct.unpack('<d', self.take(8))[0]
            elif kind == 19:
                value = struct.unpack('<q', self.take(8))[0]
            elif kind in (4, 20):
                value = self.string_bytes()
                _check(value is not None)
                # Lua constants can contain arbitrary bytes. Preserve those
                # opaquely; only valid UTF-8 is exposed to textual metadata
                # consumers. Source/debug names retain their text checks.
                try:
                    value = value.decode('utf-8')
                except UnicodeDecodeError:
                    pass
            else:
                raise ValueError('The original updater constant type is not supported.')
            constants.append(value)
        upvalues = tuple(self.take(3) for _ in range(self.unsigned(255)))
        children = tuple(self.prototype(source, depth + 1) for _ in range(self.unsigned(MAX_FUNCTIONS - self.functions)))
        lines = self.take(self.unsigned(len(code)))
        absolute = tuple((self.unsigned(len(code)), self.unsigned()) for _ in range(self.unsigned(len(code))))
        locals_ = []
        for _ in range(self.unsigned(len(self.raw))):
            name, start, end = self.string(), self.unsigned(len(code)), self.unsigned(len(code))
            _check(start <= end)
            locals_.append((name, start, end))
        names = self.unsigned(255)
        _check(names in (0, len(upvalues)))
        upvalue_names = tuple(self.string() for _ in range(names))
        return Prototype(source, first, last, parameters, vararg, stack, code, tuple(constants), upvalues,
                         children, lines, absolute, tuple(locals_), upvalue_names)


def parse_metadata(raw: bytes) -> Prototype:
    """Read one complete source-owned updater chunk, retaining no executable VM."""
    _check(isinstance(raw, bytes) and 32 <= len(raw) <= MAX_CHUNK)
    reader = _Reader(raw)
    _check(reader.take(15) == HEADER and struct.unpack('<q', reader.take(8))[0] == 0x5678 and
           struct.unpack('<d', reader.take(8))[0] == 370.5)
    upvalues = reader.byte()
    root = reader.prototype()
    _check(upvalues == len(root.upvalues) and reader.at == len(raw))
    return root
