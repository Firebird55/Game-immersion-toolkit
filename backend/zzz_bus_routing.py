"""Read original Wwise135 Init-bank bus parents without fetching bank DATA.

The native AudioAssembly bootstrap loads Init.bnk. Bus and effect/device IDs
have separate namespaces; this reader never treats these objects as voices.
"""
import struct

from .wwise_tables import wwise_short_id as wwise_hash


INITIAL_BANK_FILENAME = 'Init.bnk'


def _check(condition):
    if not condition:
        raise ValueError('Unsupported original ZZZ initialization bus graph.')


def bus_parents_from_reader(total, read, bank_id):
    _check(20 <= total <= 8 * 1024**2)
    header = read(0, 20)
    _check(len(header) == 20 and header[:4] == b'BKHD'
           and struct.unpack_from('<I', header, 4)[0] >= 12
           and struct.unpack_from('<III', header, 8) == (135, bank_id, wwise_hash('sfx')))
    cursor, hierarchy, seen_chunks = 0, None, set()
    while cursor < total:
        _check(cursor + 8 <= total)
        chunk = read(cursor, 8)
        _check(len(chunk) == 8)
        tag, size = struct.unpack('<4sI', chunk)
        cursor += 8
        _check(size <= total - cursor and tag not in seen_chunks)
        seen_chunks.add(tag)
        if tag == b'HIRC':
            hierarchy = read(cursor, size)
            _check(len(hierarchy) == size)
        cursor += size
    _check(hierarchy is not None and len(hierarchy) >= 4)
    count = struct.unpack_from('<I', hierarchy)[0]
    _check(0 < count <= 10000)
    position, identities, buses = 4, set(), {}
    for _ in range(count):
        _check(position + 5 <= len(hierarchy))
        kind, length = struct.unpack_from('<BI', hierarchy, position)
        position += 5
        _check(4 <= length <= len(hierarchy) - position)
        identity = struct.unpack_from('<I', hierarchy, position)[0]
        _check((kind, identity) not in identities)
        identities.add((kind, identity))
        if kind == 8:  # AudioBus: ID, OverrideBusId, then device/parameter data.
            _check(identity != 0 and length >= 12)
            buses[identity] = struct.unpack_from('<I', hierarchy, position + 4)[0]
        position += length
    _check(position == len(hierarchy) and buses)
    return buses


def separate_stop_buses(buses, voice_buses, stopped):
    """Only one explicit voice output; every affected branch must reach a root."""
    _check(buses is not None and len(voice_buses) == 1)

    def chain(current):
        result = set()
        while current:
            _check(current in buses and current not in result and len(result) < 128)
            result.add(current)
            current = buses[current]
        return result

    voice, = voice_buses
    ancestors = chain(voice)
    for target in stopped:
        chain(target)
        _check(target not in ancestors)
