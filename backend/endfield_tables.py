"""Read data-only SparkBuffer maps from Endfield's versioned TableCfg files."""
import math
import struct


BOOL, BYTE, INT, LONG, FLOAT, DOUBLE, ENUM, STRING, BEAN, ARRAY, MAP = range(11)
FORMATS = {BOOL: '<?', BYTE: '<B', INT: '<i', LONG: '<q', FLOAT: '<f', DOUBLE: '<d', ENUM: '<i'}


def _check(condition):
    if not condition:
        raise ValueError('Unsupported or incomplete Endfield narrative table.')


class Reader:
    def __init__(self, data):
        _check(12 <= len(data) <= 64 * 1024**2)
        self.data, self.pos = data, 0
        self.types = {}
        self.remaining = 12_000_000
        self.string_bytes = 256 * 1024**2

    def number(self, fmt):
        length = struct.calcsize(fmt)
        _check(0 <= self.pos <= len(self.data) - length)
        value, = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += length
        return value

    def align(self, width):
        self.pos = (self.pos + width - 1) // width * width

    def count(self, limit):
        count = self.number('<i')
        _check(0 <= count <= limit)
        return count

    def string(self):
        end = self.data.find(b'\0', self.pos, self.pos + 2 * 1024**2)
        _check(end >= self.pos >= 0)
        self.string_bytes -= end - self.pos
        _check(self.string_bytes >= 0)
        result = self.data[self.pos:end].decode('utf-8')
        self.pos = end + 1
        return result

    def kind(self):
        kind = self.number('<B')
        _check(BOOL <= kind <= MAP)
        return kind

    def subtype(self, kind):
        if kind in (ENUM, BEAN):
            self.align(4)
            return kind, self.number('<i')
        _check(kind not in (ARRAY, MAP))
        return (kind,)

    def schema(self, kind):
        if kind == ARRAY:
            return ARRAY, self.subtype(self.kind())
        if kind == MAP:
            key, item = self.kind(), self.kind()
            _check(key in (INT, LONG, STRING))
            return MAP, self.subtype(key), self.subtype(item)
        return self.subtype(kind)

    def definitions(self):
        for _ in range(self.count(4096)):
            kind = self.kind()
            self.align(4)
            identity = self.number('<i')
            self.string()
            self.align(4)
            _check(identity not in self.types and kind in (BEAN, ENUM))
            fields = {}
            for _ in range(self.count(16384)):
                name = self.string()
                _check(name not in fields)
                if kind == BEAN:
                    fields[name] = self.schema(self.kind())
                else:
                    self.align(4)
                    fields[name] = self.number('<i')
            self.types[identity] = (list(fields.items()) if kind == BEAN else
                                    {value: name for name, value in fields.items()})

    def value(self, schema, depth=0, *, direct=False, named_enum=False):
        self.remaining -= 1
        _check(self.remaining >= 0 and depth < 48)
        kind = schema[0]
        if kind in FORMATS:
            if kind in (LONG, DOUBLE):
                self.align(8)
            value = self.number(FORMATS[kind])
            if kind in (FLOAT, DOUBLE):
                _check(math.isfinite(value))
            if kind == ENUM and named_enum:
                return self.types[schema[1]].get(value, str(value))
            return value
        resume = None
        if not direct:
            offset = self.number('<i')
            if offset == -1:
                return '' if kind == STRING else None
            _check(0 <= offset < len(self.data))
            resume, self.pos = self.pos, offset
        if kind == STRING:
            result = self.string()
        elif kind == BEAN:
            result = {}
            fields = self.types[schema[1]]
            for index, (name, field) in enumerate(fields):
                result[name] = self.value(field, depth + 1)
                if field[0] == BOOL and index + 1 < len(fields) and fields[index + 1][1][0] != BOOL:
                    self.align(4)
        elif kind == ARRAY:
            result = [self.value(schema[1], depth + 1) for _ in range(self.count(1_000_000))]
        else:
            _check(kind == MAP)
            count = self.count(1_000_000)
            self.pos += count * 8
            _check(self.pos <= len(self.data))
            result = {}
            for _ in range(count):
                name = str(self.value(schema[1], depth + 1))
                _check(name not in result)
                result[name] = self.value(schema[2], depth + 1, named_enum=True)
                if schema[2][0] == BOOL:
                    self.align(4)
        if resume is not None:
            self.pos = resume
        return result


def read(data, expected_name):
    reader = Reader(data)
    types, root, values = struct.unpack_from('<3i', data)
    _check(12 <= types <= root < values < len(data))
    reader.pos = types
    reader.definitions()
    _check(reader.pos <= root)
    reader.pos = root
    kind = reader.kind()
    _check(kind in (MAP, BEAN) and reader.string() == expected_name)
    schema = reader.schema(kind)
    reader.pos = values
    return reader.value(schema, direct=True)
