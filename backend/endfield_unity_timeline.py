"""Read embedded v22 Unity type trees used by released Endfield cinematic assets."""
from dataclasses import dataclass, field
import struct


# Offsets in Unity's common type-tree string buffer used by this reader.
# Other common names can remain numeric when traversing an unrelated field.
COMMON = {49: 'Array', 76: 'bool', 81: 'char', 106: 'data', 117: 'double', 155: 'first',
          161: 'float', 222: 'int', 231: 'long long', 349: 'm_Enabled', 374: 'm_GameObject',
          427: 'm_Name', 490: 'm_Script', 543: 'pair', 778: 'second', 789: 'short', 795: 'size',
          800: 'SInt16', 807: 'SInt32', 814: 'SInt64', 821: 'SInt8', 840: 'string',
          894: 'TypelessData', 907: 'UInt16', 914: 'UInt32', 921: 'UInt64', 928: 'UInt8',
          934: 'unsigned int', 947: 'unsigned long long', 966: 'unsigned short', 1152: 'FileSize'}
PRIMITIVES = {'bool': '?', 'char': 'B', 'UInt8': 'B', 'SInt8': 'b', 'UInt16': 'H', 'SInt16': 'h',
              'short': 'h', 'unsigned short': 'H', 'int': 'i', 'SInt32': 'i', 'unsigned int': 'I',
              'UInt32': 'I', 'SInt64': 'q', 'long long': 'q', 'UInt64': 'Q', 'unsigned long long': 'Q',
              'FileSize': 'Q', 'float': 'f', 'double': 'd'}
NODE = struct.Struct('<hBBIIiiiQ')


def _require(condition):
    if not condition:
        raise ValueError('Unsupported or incomplete Endfield cinematic serialized file.')


class _Reader:
    def __init__(self, raw, start, end):
        self.raw, self.pos, self.end = raw, start, end
        self.budget = 1_000_000
        self.managed_depth = 0
        self.reference_types = {}

    def take(self, n):
        start = self.pos
        _require(0 <= n <= self.end - start)
        self.pos += n
        return start

    def value(self, fmt):
        spec = struct.Struct('<' + fmt)
        return spec.unpack_from(self.raw, self.take(spec.size))

    def count(self, limit):
        n, = self.value('i')
        _require(0 <= n <= limit)
        return n

    def align(self):
        self.take(-self.pos % 4)

    def cstring(self):
        end = self.raw.find(b'\0', self.pos, min(self.end, self.pos + 4096))
        _require(end >= self.pos)
        start = self.take(end + 1 - self.pos)
        return self.raw[start:end].decode('utf-8')


@dataclass
class _Node:
    kind: str | int
    name: str | int
    size: int
    flags: int
    children: list = field(default_factory=list)


def _schema(reader, selected):
    count = reader.count(32_768)
    size = reader.count(2 * 1024**2)
    start = reader.take(count * NODE.size)
    table = reader.take(size)
    if not selected:
        return None
    strings = {}

    def name(index):
        if index >= 0x80000000:
            offset = index & 0x7fffffff
            return COMMON.get(offset, offset)
        if index not in strings:
            _require(index < size)
            end = reader.raw.find(b'\0', table + index, min(table + size, table + index + 4096))
            _require(end >= 0)
            strings[index] = reader.raw[table + index:end].decode('utf-8')
        return strings[index]

    stack = []
    for i in range(count):
        _, level, _, kind, key, width, _, flags, _ = NODE.unpack_from(reader.raw, start + i * NODE.size)
        _require(level <= len(stack) and level < 64 and (level != 0 or i == 0))
        node = _Node(name(kind), name(key), width, flags)
        del stack[level:]
        if stack:
            stack[-1].children.append(node)
        stack.append(node)
    _require(stack)
    return stack[0]


def _field(reader, node):
    reader.budget -= 1
    _require(reader.budget >= 0)
    children = node.children
    if node.kind == 'string':
        size = reader.count(2 * 1024**2)
        start = reader.take(size)
        value = reader.raw[start:start + size].decode('utf-8')
        reader.align()
    elif node.kind in PRIMITIVES:
        fmt = PRIMITIVES[node.kind]
        _require(node.size == struct.calcsize('<' + fmt))
        value, = reader.value(fmt)
    elif len(children) == 1 and children[0].kind == 'Array':
        array = children[0]
        _require(len(array.children) == 2 and array.children[0].kind == 'int')
        count = reader.count(min(reader.budget, 100_000))
        value = [_field(reader, array.children[1]) for _ in range(count)]
        if array.flags & 0x4000:
            reader.align()
    elif children:
        value = {}
        for child in children:
            _require(child.name not in value)
            if child.kind == 'ReferencedObjectData':
                ref = value.get('type', {})
                key = tuple(ref.get(k) for k in ('class', 'ns', 'asm'))
                if key == ('', '', '') and value.get('rid') in (-1, -2):
                    value[child.name] = None
                else:
                    _require(key in reader.reference_types and reader.managed_depth < 8)
                    reader.managed_depth += 1
                    value[child.name] = _field(reader, reader.reference_types[key])
                    reader.managed_depth -= 1
            else:
                value[child.name] = _field(reader, child)
    else:
        # Unknown fixed-width leaves cannot supply a binding.
        reader.take(node.size)
        value = None
    if node.flags & 0x4000:
        reader.align()
    return value


def timeline_objects(raw, *, classes=(114,)):
    """Read selected object classes, AssetBundle roots and ordered external file paths."""
    _require(isinstance(raw, bytes) and 48 < len(raw) <= 32 * 1024**2)
    _, _, version, _, endian, metadata, length, data, _ = struct.unpack_from('>4I4sIqqq', raw)
    _require(version == 22 and endian == b'\0' * 4 and length == len(raw) and
             48 + metadata <= data <= length)
    reader = _Reader(raw, 48, 48 + metadata)
    reader.cstring()
    _, trees = reader.value('iB')
    _require(trees == 1)
    types = []
    for _ in range(reader.count(1024)):
        kind, _, _ = reader.value('iBh')
        reader.take(32 if kind == 114 else 16)
        root = _schema(reader, kind == 142 or kind in classes)
        reader.take(4 * reader.count(4096))
        types.append((kind, root))
    selected = []
    seen = set()
    for _ in range(reader.count(16_384)):
        reader.align()
        identity, offset, size, index = reader.value('qqIi')
        _require(0 <= index < len(types) and 0 <= offset <= length - data - size and identity not in seen)
        seen.add(identity)
        kind, root = types[index]
        if root is not None:
            selected.append((identity, kind, root, offset, size))
    for _ in range(reader.count(16_384)):
        reader.take(4)
        reader.align()
        reader.take(8)
    externals = []
    for _ in range(reader.count(4096)):
        reader.cstring()
        reader.take(20)
        externals.append(reader.cstring())
    reference_types = {}
    for _ in range(reader.count(1024)):
        kind, _, index = reader.value('iBh')
        reader.take(32 if index >= 0 or kind == 114 else 16)
        root = _schema(reader, True)
        key = (reader.cstring(), reader.cstring(), reader.cstring())
        _require(key not in reference_types)
        reference_types[key] = root
    reader.cstring()
    _require(reader.pos == reader.end)
    objects, containers = {}, {}
    remaining = reader.budget
    for identity, kind, root, offset, size in selected:
        body = _Reader(raw, data + offset, data + offset + size)
        body.budget = remaining
        body.reference_types = reference_types
        value = _field(body, root)
        remaining = body.budget
        _require(body.pos == body.end)
        (containers if kind == 142 else objects)[identity] = value
    return objects, containers, tuple(externals)
