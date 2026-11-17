"""Original masked configuration data, using native-owned type descriptions."""
import math
import re

from .starrail_metadata import _check
from .starrail_original_tables import Reader

PRIMITIVES = {'uint': 'u32', 'int': 's32', 'bool': 'bool', 'string': 'string', 'float': 'f32',
              'RPG.Client.TextID': 'textid'}
ROOT = 'RPG.GameCore.LevelGraphConfig'
MAX_VALUES = 1_000_000


def _description(value):
    _check(isinstance(value, dict) and set(value) == {'fields', 'defaults'}
           and isinstance(value['fields'], (list, tuple)) and 0 < len(value['fields']) <= 64
           and isinstance(value['defaults'], dict))
    fields = []
    for field in value['fields']:
        _check(isinstance(field, (list, tuple)) and len(field) == 2
               and isinstance(field[0], str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', field[0])
               and isinstance(field[1], str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*(?:\[\])?', field[1]))
        fields.append(tuple(field))
    _check(len({name for name, _ in fields}) == len(fields) and set(value['defaults']) <= {name for name, _ in fields})
    for key, default in value['defaults'].items():
        _check(default is None or type(default) in {int, bool, str, float})
        _check(not isinstance(default, float) or math.isfinite(default))
        _check(not isinstance(default, str) or len(default) <= 1024**2)
    return tuple(fields), value['defaults']


def decode(data, descriptions, *, root=ROOT):
    """Decode every present field and require complete input consumption.

    A descriptor provider supplies fixed types, enum labels and the original
    factory table. A missing schema/type cannot become an empty successful
    configuration. This reads data; no Lua or client callback is evaluated.
    """
    _check(isinstance(data, bytes) and 0 < len(data) <= 16 * 1024**2)
    reader = Reader(data)
    nodes = 0
    enums = {}

    def enum(kind):
        if kind not in enums:
            mapping = descriptions.enum(kind)
            _check(mapping is None or isinstance(mapping, dict) and 0 < len(mapping) <= 65536
                   and all(type(number) is int and -(1 << 31) <= number < 1 << 31
                           and isinstance(label, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', label)
                           for number, label in mapping.items()))
            enums[kind] = mapping
        return enums[kind]

    def value(kind, depth):
        nonlocal nodes
        nodes += 1
        _check(depth <= 64 and nodes <= MAX_VALUES)
        if kind.endswith('[]'):
            count = reader.sint()
            _check(0 <= count <= min(MAX_VALUES - nodes, len(data) - reader.at))
            return [value(kind[:-2], depth + 1) for _ in range(count)]
        if kind in PRIMITIVES:
            return reader.value(PRIMITIVES[kind])
        labels = enum(kind)
        if labels is not None:
            number = reader.sint()
            return labels.get(number, number)
        if kind in descriptions.registries:
            selected = descriptions.polymorphic(kind, reader.uint(32))
            return {'$type': selected, **record(selected, depth + 1)}
        return record(kind, depth + 1)

    def record(name, depth):
        nonlocal nodes
        _check(depth <= 64)
        fields, defaults = _description(descriptions.description(name))
        nodes += 1 + len(fields)
        _check(nodes <= MAX_VALUES)
        kinds = dict(fields)
        for key, default in defaults.items():
            kind = kinds[key]
            if kind == 'uint':
                _check(type(default) is int and 0 <= default < 1 << 32)
            elif kind == 'int':
                _check(type(default) is int and -(1 << 31) <= default < 1 << 31)
            elif kind == 'bool':
                _check(type(default) is bool)
            elif kind == 'float':
                _check(type(default) is float and math.isfinite(default))
            elif kind == 'string':
                _check(default is None or isinstance(default, str))
            elif enum(kind) is not None:
                _check(type(default) is int and -(1 << 31) <= default < 1 << 31
                       or isinstance(default, str) and default in enum(kind).values())
            else:
                _check(default is None)
        mask = reader.uint()
        _check(mask >> len(fields) == 0)
        result = {key: default for key, default in defaults.items() if default is not None}
        for bit, (key, kind) in enumerate(fields):
            if mask & (1 << bit):
                result[key] = value(kind, depth + 1)
        return result

    result = record(root, 0)
    _check(reader.at == len(data))
    return result


class OriginalConfigs:
    """ReleaseCatalog-compatible files from whole authenticated packages."""
    def __init__(self, tables, descriptions):
        self.tables, self.descriptions = tables, descriptions

    def file(self, relative):
        from .xxhash64 import xxhash64
        _check(isinstance(relative, str))
        mission = re.fullmatch(r'Config/Level/Mission/[0-9]{1,20}/Act/Act[0-9]{1,20}\.json', relative)
        caption = re.fullmatch(r'Config/(?:CutSceneCaption/[A-Za-z0-9_-]+_Caption|BattleCollegeCaption/[A-Za-z0-9_-]+)\.json', relative)
        _check(mission or caption)
        path = self.descriptions.binary_path(relative)
        entry = self.tables.resources.get(xxhash64(path.encode('utf-8')))
        _check(entry is not None)
        asset, start, length = entry
        _check(type(start) is int and type(length) is int and 0 <= start < start + length <= asset.size
               and length <= 16 * 1024**2)
        package = self.tables._package(asset)
        _check(len(package) == asset.size)
        return decode(package[start:start + length], self.descriptions,
                      root=ROOT if mission else 'RPG.GameCore.VideoCaptionConfig')
