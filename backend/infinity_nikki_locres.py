"""Read the original stock-v3 localization resources as identity-preserving data.

The outer publisher/chunk/PAK reader owns source integrity. A localization entry
alone proves neither a displayed caption nor an original voice binding. Source
hashes describe the authored source string, not the translated display value.
"""
from dataclasses import dataclass, field
import struct


MAGIC = bytes.fromhex('0e147475674a03fc4a15909dc3377f1b')
MAX_RESOURCE = 64 * 1024**2
MAX_TEXT = 2 * 1024**2
MAX_ENTRIES = 2_000_000


def _check(value):
    if not value:
        raise ValueError('Could not verify the original Infinity Nikki localization resource.')


class _Reader:
    def __init__(self, raw, start=0, end=None):
        self.raw, self.at, self.end = raw, start, len(raw) if end is None else end

    def take(self, count):
        _check(type(count) is int and 0 <= count <= self.end - self.at)
        result = self.raw[self.at:self.at + count]
        self.at += count
        return result

    def number(self, kind='i'):
        return struct.unpack('<' + kind, self.take(struct.calcsize('<' + kind)))[0]

    def count(self, maximum, minimum):
        value = self.number()
        _check(0 <= value <= min(maximum, (self.end - self.at) // minimum))
        return value

    def string(self, limit):
        count = self.number()
        if not count:
            return ''
        width = 1 if count > 0 else 2
        _check(abs(count) * width <= limit)
        raw = self.take(abs(count) * width)
        _check(raw[-width:] == bytes(width))
        return raw[:-width].decode('utf-8' if width == 1 else 'utf-16-le')

    def finish(self):
        _check(self.at == self.end)


@dataclass(frozen=True)
class LocalizedEntry:
    namespace: str
    key: str
    source_hash: int
    value: str = field(repr=False)
    namespace_hash: int
    key_hash: int

    @property
    def identity(self):
        return self.namespace, self.key, self.source_hash


def parse_locres(raw: bytes) -> tuple[LocalizedEntry, ...]:
    """Validate both key-table and string-pool bounds and exact end positions.

    Namespace/key hashes and serialized pool reference counts are read without
    being promoted to source authentication or voice state. Lookups retain the
    full authored namespace, key and source hash, including empty namespaces.
    """
    _check(isinstance(raw, bytes) and 37 <= len(raw) <= MAX_RESOURCE)
    try:
        header = _Reader(raw)
        _check(header.take(16) == MAGIC and header.number('B') == 3)
        offset, count, namespaces = header.number('q'), header.number(), header.number()
        _check(33 <= offset <= len(raw) - 4 and 0 <= count <= MAX_ENTRIES and
               count <= (offset - 33) // 16 and 0 <= namespaces <= min(200_000, (offset - 33) // 12))
        keys, namespace_names = [], set()
        reader = _Reader(raw, 33, offset)
        for _ in range(namespaces):
            namespace_hash, namespace = reader.number('I'), reader.string(8192)
            _check('\0' not in namespace and namespace not in namespace_names)
            namespace_names.add(namespace)
            seen = set()
            for _ in range(reader.count(count - len(keys), 16)):
                key_hash, key = reader.number('I'), reader.string(8192)
                source_hash, index = reader.number('I'), reader.number()
                _check('\0' not in key and key not in seen)
                seen.add(key)
                keys.append((namespace, key, source_hash, index, namespace_hash, key_hash))
        _check(len(keys) == count)
        reader.finish()
        pool = _Reader(raw, offset)
        strings = []
        for _ in range(pool.count(MAX_ENTRIES, 8)):
            strings.append(pool.string(MAX_TEXT))
            pool.number()  # Original reference count; lookup uses the key table.
        pool.finish()
        _check(all(0 <= row[3] < len(strings) for row in keys))
        return tuple(LocalizedEntry(ns, key, source_hash, strings[index], ns_hash, key_hash)
                     for ns, key, source_hash, index, ns_hash, key_hash in keys)
    except (UnicodeError, struct.error) as error:
        raise ValueError('Could not read the original Infinity Nikki localization strings or fields.') from error


def translation_index(entries) -> dict[tuple[str, str, int], LocalizedEntry]:
    """Index one resolved resource without merging namespaces or stale sources.

    The caller establishes file/overlay priority before this step. No fallback
    to equal display text or a matching key with a different source hash occurs.
    """
    _check(isinstance(entries, (tuple, list)) and len(entries) <= MAX_ENTRIES)
    result = {}
    for entry in entries:
        _check(isinstance(entry, LocalizedEntry) and entry.identity not in result)
        result[entry.identity] = entry
    return result
