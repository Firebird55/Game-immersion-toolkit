"""Original DesignV table reader; not yet the production catalog provider.

Descriptions below come from the publisher's native FromBinary methods, not
mirror rows. Neither table paths nor row IDs depend on a game version. Callers
may supply newly derived descriptions; automatic native description extraction
and autonomous hotfix-route discovery are separate unfinished work.
"""
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re
import struct

from . import starrail_design as design, starrail_hotfix as hotfix
from .game_tools import _atomic_file
from .xxhash64 import xxhash64


# Serialization order differs from managed field order. TextID stores the
# legacy signed hash followed by the current unsigned 64-bit hash.
SCHEMAS = {
    'TalkSentenceConfig': (
        ('TalkSentenceID', 'u32'), ('VoiceID', 'u32'),
        ('TextmapTalkSentenceName', 'textid'), ('TalkSentenceText', 'textid')),
    'VoiceConfig': (
        ('VoiceID', 'u32'), ('IsPlayerInvolved', 'bool'),
        ('VoicePath', 'string'), ('VoiceType', 's32')),
    'Textmap': (('ID', 'textid'), ('Text', 'string'), ('HasParam', 'bool')),
}
TEXT_CODES = {'CHS': 'cn', 'CHT': 'cht', **{code: code.lower() for code in (
    'EN', 'JP', 'KR', 'DE', 'FR', 'ES', 'PT', 'RU', 'TH', 'VI', 'ID')}}
VOICE_TYPES = dict(enumerate(('Story', 'Cutscene')))
VOICE_TYPES.update(dict(zip(range(3, 19), (
    'NPC_Near', 'NPC_Normal', 'NPC_Far', 'Archive', 'MissionTalk_3d',
    'BroadcastNear', 'BroadcastNormal', 'BroadcastFar', 'BroadcastUltraFar1',
    'BroadcastUltraFar2', 'BroadcastUltraFar3', 'StoryNew', 'NPC_Near_NoDuck',
    'NPC_Normal_NoDuck', 'NPC_Far_NoDuck', 'SystemReverb1'))))
VOICE_TYPES[99] = 'NoVoice'
KINDS = {'u32', 's32', 'textid', 'bool', 'string', 'f32', 'u32[]', 'string[]', 'f32[]'}


def _schema(value):
    hotfix.check(isinstance(value, (list, tuple)) and 0 < len(value) <= 64)
    fields = []
    for item in value:
        hotfix.check(isinstance(item, (list, tuple)) and len(item) == 2
                     and isinstance(item[0], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', item[0])
                     and isinstance(item[1], str) and item[1] in KINDS)
        fields.append(tuple(item))
    hotfix.check(len({name for name, _ in fields}) == len(fields))
    return tuple(fields)


def _description(value):
    hotfix.check(isinstance(value, dict) and set(value) == {'fields', 'identity', 'hash_byte_prefix', 'enums'}
                 and type(value['hash_byte_prefix']) is bool and isinstance(value['enums'], dict))
    fields = _schema(value['fields'])
    identity = value['identity']
    hotfix.check(isinstance(identity, (list, tuple)) and len(identity) <= len(fields)
                 and all(isinstance(name, str) for name in identity)
                 and len(set(identity)) == len(identity)
                 and set(identity) <= {name for name, kind in fields if kind in {'u32', 's32', 'textid', 'string'}})
    enums = {}
    for name, mapping in value['enums'].items():
        hotfix.check(name in {key for key, kind in fields if kind in {'u32', 's32'}}
                     and isinstance(mapping, dict) and 0 < len(mapping) <= 65536)
        values = {}
        for number, label in mapping.items():
            hotfix.check(type(number) is int or isinstance(number, str) and re.fullmatch(r'-?(?:0|[1-9][0-9]*)', number))
            number = int(number)
            hotfix.check(-(1 << 31) <= number < 1 << 32 and number not in values
                         and isinstance(label, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', label))
            values[number] = label
        enums[name] = values
    return fields, tuple(identity), value['hash_byte_prefix'], enums


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def uint(self, bits=64):
        value, self.at = design._uint(self.data, self.at, bits)
        return value

    def sint(self):
        value = self.uint(32)
        return (value >> 1) ^ -(value & 1)

    def value(self, kind):
        if kind.endswith('[]'):
            count = self.sint()
            minimum = 4 if kind == 'f32[]' else 1
            hotfix.check(0 <= count <= min(2_000_000, (len(self.data) - self.at) // minimum))
            return [self.value(kind[:-2]) for _ in range(count)]
        if kind == 'u32':
            return self.uint(32)
        if kind == 's32':
            return self.sint()
        if kind == 'textid':
            self.sint()
            return {'Hash': self.uint()}
        if kind == 'bool':
            hotfix.check(self.at < len(self.data))
            value = self.data[self.at]
            self.at += 1
            hotfix.check(value in (0, 1))
            return bool(value)
        if kind == 'string':
            length = self.uint(32)
            hotfix.check(length <= len(self.data) - self.at)
            start, self.at = self.at, self.at + length
            return self.data[start:self.at].decode('utf-8')
        if kind == 'f32':
            hotfix.check(self.at + 4 <= len(self.data))
            value, = struct.unpack_from('<f', self.data, self.at)
            self.at += 4
            hotfix.check(math.isfinite(value))
            return value
        raise ValueError('Unknown original Star Rail field description.')


def decode_table(data, schema, identity=None, *, hash_byte_prefix=False):
    """Decode a native masked row array, rejecting ambiguous/truncated input."""
    schema = _schema(schema)
    identity = (identity,) if isinstance(identity, str) else (() if identity is None else identity)
    hotfix.check(isinstance(data, bytes) and type(hash_byte_prefix) is bool
                 and isinstance(identity, (tuple, list)) and len(identity) <= len(schema)
                 and all(isinstance(name, str) for name in identity) and len(set(identity)) == len(identity)
                 and set(identity) <= {name for name, kind in schema if kind in {'u32', 's32', 'textid', 'string'}})
    reader = Reader(data)
    if hash_byte_prefix:
        hotfix.check(len(data) > 0)
        reader.at += 1
    count = reader.sint()
    hotfix.check(0 <= count <= min(2_000_000, len(data) - reader.at))
    rows, identities = [], set()
    defaults = {'u32': 0, 's32': 0, 'bool': False, 'string': '', 'f32': 0.0}
    for _ in range(count):
        mask = reader.uint()
        if mask >> len(schema):
            raise ValueError('An original Star Rail row needs a new native field description.')
        row = {field: reader.value(kind) if mask & (1 << bit) else
               ({'Hash': 0} if kind == 'textid' else [] if kind.endswith('[]') else defaults[kind])
               for bit, (field, kind) in enumerate(schema)}
        if identity:
            key = tuple(row[name]['Hash'] if isinstance(row[name], dict) else row[name] for name in identity)
            hotfix.check(key not in identities)
            identities.add(key)
        rows.append(row)
    hotfix.check(reader.at == len(data))
    return rows


class OriginalTables:
    """A ``file(relative)`` source for supplied original catalog descriptions.

    Does not fall back to third-party data. A caller must retain its previous
    complete preparation until every required table/provider succeeds.
    """
    def __init__(self, directory, build, *, schemas=None, descriptions=None):
        self.directory = Path(directory)
        self.schemas = dict(SCHEMAS if schemas is None else schemas)
        if descriptions is None:
            hotfix.check({'TalkSentenceConfig', 'VoiceConfig'} <= self.schemas.keys())
            descriptions = {
                'TalkSentenceConfig': {'fields': self.schemas['TalkSentenceConfig'], 'identity': ['TalkSentenceID'],
                                      'hash_byte_prefix': False, 'enums': {}},
                'VoiceConfig': {'fields': self.schemas['VoiceConfig'], 'identity': ['VoiceID'],
                                'hash_byte_prefix': False, 'enums': {'VoiceType': VOICE_TYPES}}}
        hotfix.check(isinstance(descriptions, dict) and 0 < len(descriptions) <= 4096)
        self.descriptions = {}
        for name, description in descriptions.items():
            hotfix.check(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name))
            self.descriptions[name] = _description(description)
        roots, alternate = hotfix.audio_roots(build)
        self.resources = {}
        for digest, size, entries, folder in design._packages(
                hotfix.index(self.directory, build, 'design'), with_folder=True):
            hotfix.check(0 < size <= 256 * 1024**2)
            name = (folder + '/' if folder else '') + digest + '.bytes'
            asset = hotfix.AudioFile(name, size, digest, roots['design'] + name,
                alternate['design'] + name if alternate else '')
            for key, length, start in entries:
                hotfix.check(key not in self.resources and length > 0)
                self.resources[key] = asset, start, length

    @lru_cache(maxsize=2)
    def _package(self, asset):
        path = self.directory / 'starrail-design-packages' / (asset.digest + '.bytes')
        if path.is_file() and path.stat().st_size == asset.size:
            data = path.read_bytes()
            if hashlib.md5(data).hexdigest() == asset.digest:
                return data
        # Transport range receipts and ETags alone do not verify package MD5.
        # Publish this reusable package only after checking the complete body.
        step = 16 * 1024**2
        data = b''.join(asset.read(self.directory, start, min(step, asset.size - start))
                        for start in range(0, asset.size, step))
        hotfix.check(len(data) == asset.size and hashlib.md5(data).hexdigest() == asset.digest)
        _atomic_file(path, data)
        return data

    def resource(self, path):
        hotfix.check(isinstance(path, str) and re.fullmatch(
            r'BakedConfig/ExcelOutput/[A-Za-z][A-Za-z0-9_]*(?:\.binary_header)?\.bytes', path))
        entry = self.resources.get(xxhash64(path.encode('utf-8')))
        if entry is None:
            raise ValueError('The original Star Rail resource is absent from this publisher index.')
        asset, start, length = entry
        return self._package(asset)[start:start + length]

    def table(self, name):
        hotfix.check(isinstance(name, str) and name in self.descriptions)
        schema, identity, prefix, enums = self.descriptions[name]
        rows = decode_table(self.resource('BakedConfig/ExcelOutput/' + name + '.bytes'),
                            schema, identity, hash_byte_prefix=prefix)
        for row in rows:
            for field, values in enums.items():
                # Unknown native values retain their number, never NoVoice.
                row[field] = values.get(row[field], row[field])
        return rows

    def textmap(self, code, *, main=False):
        hotfix.check(code in TEXT_CODES)
        name = ('TextmapMain_' if main else 'Textmap_') + TEXT_CODES[code]
        rows = decode_table(self.resource('BakedConfig/ExcelOutput/' + name + '.bytes'),
                            self.schemas['Textmap'], 'ID')
        return {str(row['ID']['Hash']): row['Text'] for row in rows}

    def file(self, relative, *, optional=False):
        # Native Textmap is a single logical table; third-party KR/RU/TH JSON
        # transport splits are deliberately not invented as publisher resources.
        match = re.fullmatch(r'ExcelOutput/([A-Za-z][A-Za-z0-9_]*)\.json', relative)
        if match:
            return self.table(match[1])
        match = re.fullmatch(r'TextMap/TextMap(Main)?([A-Z]{2,3})\.json', relative)
        if match:
            return self.textmap(match[2], main=bool(match[1]))
        raise ValueError('This original Star Rail table has no evidenced reader yet.')
