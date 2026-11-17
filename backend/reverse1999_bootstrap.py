"""Bounded data-only reader for the publisher's evidenced Unity 22 bootstrap."""
from dataclasses import dataclass, field
import hashlib
import re
import struct

LIMIT = 64 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


class _Reader:
    def __init__(self, raw, position=0):
        self.raw, self.position = raw, position

    def take(self, count):
        _require(type(count) is int and 0 <= count <= len(self.raw) - self.position,
                 'Truncated original bootstrap asset.')
        value = self.raw[self.position:self.position + count]
        self.position += count
        return value

    def number(self, kind):
        return struct.unpack('<' + kind, self.take(struct.calcsize('<' + kind)))[0]

    def align(self):
        self.take((-self.position) % 4)

    def count(self, maximum=8192):
        value = self.number('i')
        _require(0 <= value <= maximum, 'Original bootstrap table exceeds its limit.')
        return value

    def terminated(self):
        end = self.raw.find(b'\0', self.position, self.position + 4097)
        _require(end >= self.position, 'Invalid original bootstrap string.')
        value = self.take(end - self.position).decode('utf-8')
        self.take(1)
        return value

    def string(self, limit=1024 * 1024):
        value = self.take(self.count(limit))
        self.align()
        return value


def _type(reader):
    class_id = reader.number('i')
    _require(reader.number('B') in (0, 1), 'Invalid bootstrap type flag.')
    script = reader.number('h')
    if class_id == 114:
        reader.take(16)
    reader.take(16)
    return class_id, script


def objects(raw):
    """Read Unity 22, little endian, stripped-type-tree data without game code."""
    _require(isinstance(raw, bytes) and 48 <= len(raw) <= LIMIT,
             'Original bootstrap asset exceeds its limit.')
    _require(int.from_bytes(raw[8:12], 'big') == 22 and raw[16:20] == b'\0' * 4,
             'Unsupported original bootstrap serialization; retain the previous catalog.')
    metadata_size, file_size, data_start = struct.unpack('>IQQ', raw[20:40])
    _require(file_size == len(raw) and 0 < metadata_size <= 2 * 1024 * 1024
             and 48 + metadata_size <= data_start <= len(raw),
             'Original bootstrap metadata boundaries disagree.')
    reader = _Reader(raw[:48 + metadata_size], 48)
    unity_version = reader.terminated()
    _require(re.fullmatch(r'[0-9]{4}\.[0-9]+\.[0-9]+[abfp][0-9]+', unity_version),
             'Unsupported original bootstrap Unity generation.')
    _require(reader.number('i') == 19 and reader.number('B') == 0,
             'Unsupported original bootstrap platform or type trees.')
    types = [_type(reader) for _ in range(reader.count(1024))]
    rows, identities, spans = [], set(), []
    for _ in range(reader.count()):
        reader.align()
        identity, offset = reader.number('q'), reader.number('q')
        size, index = reader.number('I'), reader.number('i')
        _require(identity not in identities and 0 <= index < len(types)
                 and 0 <= offset <= offset + size <= len(raw) - data_start,
                 'Invalid original bootstrap object ownership or boundaries.')
        identities.add(identity)
        spans.append((offset, offset + size))
        rows.append((types[index][0], raw[data_start + offset:data_start + offset + size]))
    spans.sort()
    _require(all(left[1] <= right[0] for left, right in zip(spans, spans[1:])),
             'Overlapping original bootstrap objects.')
    for _ in range(reader.count()):
        reader.number('i'); reader.align(); reader.number('q')
    for _ in range(reader.count(1024)):
        reader.terminated(); reader.take(16); reader.number('i'); reader.terminated()
    _require(reader.count(1024) == 0, 'Unsupported original bootstrap reference types.')
    reader.terminated()
    _require(reader.position == len(reader.raw), 'Unexpected original bootstrap metadata suffix.')
    return unity_version, tuple(rows)


@dataclass(frozen=True)
class Bootstrap:
    unity_version: str
    build_id: int
    voice_branch: int
    resource_revision: str
    publisher_app_version: str
    asset_sha256: str
    game_config_payload: bytes = field(repr=False)


def read(raw, *, expected_revision, expected_sha256):
    """Require an independently obtained original asset hash before consumption.

    A hash calculated solely from the downloaded bytes is not source authority.
    The publisher catalog/hash locator is separate and is not implemented here.
    The returned GameConfig byte array remains opaque; this never executes Lua,
    native game code, a client executable or a managed game assembly.
    """
    _require(isinstance(raw, bytes) and 48 <= len(raw) <= LIMIT,
             'Original bootstrap asset exceeds its limit.')
    _require(isinstance(expected_revision, str)
             and re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', expected_revision),
             'A verified original resource revision is required.')
    _require(isinstance(expected_sha256, str) and re.fullmatch('[a-f0-9]{64}', expected_sha256),
             'An independently verified original bootstrap SHA256 is required.')
    _require(isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == expected_sha256,
             'Original bootstrap hash mismatch; retain the previous catalog.')
    unity, rows = objects(raw)
    texts, configs = {}, []
    required = frozenset(('appbuildid', 'voicebranch', 'resversion', 'appversion'))
    for class_id, data in rows:
        if class_id == 49:
            reader = _Reader(data)
            name, content = reader.string(4096).decode('utf-8'), reader.string()
            _require(reader.position == len(data), 'Unsupported original TextAsset suffix.')
            if name in required:
                _require(name not in texts, 'Duplicate original bootstrap field.')
                texts[name] = content.decode('ascii')
        elif class_id == 114:
            reader = _Reader(data, 28)
            name = reader.string(4096).decode('utf-8')
            if name == 'bluepoch':
                payload = reader.take(reader.count(1024 * 1024))
                _require(reader.position == len(data) and payload, 'Unsupported publisher GameConfig payload.')
                configs.append(payload)
    _require(required == texts.keys() and len(configs) == 1, 'Publisher bootstrap fields or GameConfig are missing.')
    _require(all(re.fullmatch('[1-9][0-9]{0,8}', texts[name]) for name in ('appbuildid', 'voicebranch')),
             'Invalid original bootstrap build or voice branch.')
    _require(re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', texts['appversion'])
             and texts['resversion'] == expected_revision,
             'Original bootstrap resource identity differs from the selected release.')
    return Bootstrap(unity, int(texts['appbuildid']), int(texts['voicebranch']),
                     texts['resversion'], texts['appversion'], expected_sha256, configs[0])
