"""Bounded original Unity TextAssets used by publisher bootstrap configuration.

Only the metadata/object table and named TextAssets are read. No Unity runtime,
game code, scripts, textures, meshes or external streams are loaded.
"""
import struct


MAX_METADATA = 64 * 1024**2
MAX_TEXT = 1024 * 1024


def check(condition):
    if not condition:
        raise ValueError('Unsupported original publisher bootstrap TextAsset.')


class Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, count):
        start = self.position
        check(type(count) is int and 0 <= count <= len(self.data) - start)
        self.position += count
        return self.data[start:self.position]

    def number(self, kind):
        return struct.unpack('<' + kind, self.take(struct.calcsize('<' + kind)))[0]

    def align(self):
        self.take((-self.position) % 4)

    def cstring(self):
        end = self.data.find(b'\0', self.position, self.position + 128)
        check(end >= self.position)
        value = self.take(end - self.position).decode('utf-8')
        self.take(1)
        return value


def _range_reader(size, read):
    check(type(size) is int and 48 <= size <= 2**40)
    def exact(offset, length):
        check(type(offset) is int and type(length) is int and 0 <= offset <= size - length
              and 0 < length <= MAX_METADATA)
        data = read(offset, length)
        check(isinstance(data, bytes) and len(data) == length)
        return data
    return exact


def object_ranges(size, read):
    """Read bounded metadata into original class/path-ID/body ranges only."""
    exact = _range_reader(size, read)

    header = exact(0, 20)
    metadata_size, declared_size, version, data_start = struct.unpack_from('>4I', header)
    check(version in (17, 21, 22) and header[16:] == b'\0' * 4)
    start = 20
    if version == 22:
        metadata_size, declared_size, data_start, reserved = struct.unpack('>IQQQ', exact(20, 28))
        check(reserved == 0)
        start = 48
    check(declared_size == size and 0 < metadata_size <= MAX_METADATA
          and start + metadata_size <= data_start <= size)
    r = Reader(exact(start, metadata_size))
    unity_version = r.cstring()
    check(unity_version and len(unity_version) < 128)
    r.take(4)  # Original target platform; no platform executable is loaded.
    trees = r.number('B')
    check(trees in (0, 1))
    count = r.number('I')
    check(0 < count <= 100_000)
    types = []
    for _ in range(count):
        kind = r.number('i')
        types.append(kind)
        r.take(3 + (16 if kind == 114 else 0) + 16)
        if trees:
            nodes, strings = r.number('I'), r.number('I')
            check(nodes <= 100_000 and strings <= MAX_METADATA)
            r.take(nodes * (24 if version == 17 else 32) + strings)
            if version >= 21:
                dependencies = r.number('I')
                check(dependencies <= 100_000)
                r.take(dependencies * 4)
    count = r.number('I')
    check(count <= 2_000_000)
    objects, identities = [], set()
    for _ in range(count):
        r.align()
        identity = r.number('q')
        offset = data_start + r.number('Q' if version == 22 else 'I')
        length, index = r.number('I'), r.number('i')
        check(identity not in identities and 0 <= index < len(types)
              and data_start <= offset <= size - length)
        identities.add(identity)
        objects.append({'id': str(identity), 'kind': types[index], 'offset': offset, 'size': length})
    return objects


def text_assets(size, read, wanted):
    """Return exact named UTF-8 payloads and object provenance, using range I/O."""
    check(isinstance(wanted, frozenset) and 0 < len(wanted) <= 16
          and all(isinstance(n, str) and 0 < len(n) <= 128 for n in wanted))
    exact = _range_reader(size, read)
    result = {}
    for row in object_ranges(size, read):
        if row['kind'] != 49:
            continue
        identity, offset, length = row['id'], row['offset'], row['size']
        check(length >= 8)
        name_length = struct.unpack('<I', exact(offset, 4))[0]
        check(name_length <= 256 and 4 + name_length <= length)
        name = exact(offset + 4, name_length).decode('utf-8') if name_length else ''
        if name not in wanted:
            continue
        check(name not in result and length <= MAX_TEXT)
        body = exact(offset, length)
        at = (4 + name_length + 3) // 4 * 4
        check(at + 4 <= length)
        text_length = struct.unpack_from('<I', body, at)[0]
        end = at + 4 + text_length
        check(text_length <= MAX_TEXT and end <= length and (end + 3) // 4 * 4 == length
              and not any(body[end:]))
        payload = body[at + 4:end]
        payload.decode('utf-8')  # Reject replacement-decoded configuration.
        result[name] = {'payload': payload, 'id': str(identity), 'offset': offset, 'size': length}
    check(result.keys() == wanted)
    return result
