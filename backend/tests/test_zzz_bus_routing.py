"""Owned fixtures for initialization-bank namespaces and affected bus ancestry."""
import struct

import pytest

from backend.nte_assets import wwise_hash
from backend.zzz_bus_routing import INITIAL_BANK_FILENAME, bus_parents_from_reader, separate_stop_buses


def init_bank(parents=None, *, version=135, namespace='sfx', extra=(), data=b''):
    parents = {66: 80, 70: 80, 80: 0} if parents is None else parents
    objects = [(8, struct.pack('<III', identity, parent, 0)) for identity, parent in parents.items()] + list(extra)
    hierarchy = struct.pack('<I', len(objects)) + b''.join(struct.pack('<BI', kind, len(payload)) + payload for kind, payload in objects)
    result = b'BKHD' + struct.pack('<4I', 12, version, wwise_hash(INITIAL_BANK_FILENAME[:-4]), wwise_hash(namespace))
    result += b'HIRC' + struct.pack('<I', len(hierarchy)) + hierarchy
    if data:
        result += b'DATA' + struct.pack('<I', len(data)) + data
    return result


def parse(data):
    return bus_parents_from_reader(len(data), lambda start, size: data[start:start + size], wwise_hash('Init'))


def test_bus_namespace_is_separate_from_devices_and_effects_and_data_is_never_read():
    data = init_bank(extra=[(21, struct.pack('<II', 66, 0))], data=b'never fetch media')
    reads = []
    def read(start, size):
        reads.append((start, size))
        return data[start:start + size]
    assert bus_parents_from_reader(len(data), read, wwise_hash('Init')) == {66: 80, 70: 80, 80: 0}
    assert all(start + size <= len(data) - len(b'never fetch media') for start, size in reads)


@pytest.mark.parametrize('data', [init_bank(version=136), init_bank(namespace='english(us)'),
    init_bank(extra=[(8, struct.pack('<III', 66, 80, 0))]), init_bank(extra=[(8, struct.pack('<II', 99, 0))]),
    init_bank()[:-1], init_bank() + b'unparsed', init_bank() + init_bank()])
def test_changed_truncated_and_ambiguous_initialization_formats_reject(data):
    with pytest.raises(ValueError):
        parse(data)


def test_complete_sibling_stop_branch_cannot_stop_the_original_voice_bus():
    separate_stop_buses(parse(init_bank()), [66], [70])


def test_other_object_kinds_cannot_fill_an_unresolved_voice_routing_edge():
    graph = parse(init_bank({66: 99, 70: 0}, extra=[(20, struct.pack('<III', 99, 0, 0))]))
    with pytest.raises(ValueError):
        separate_stop_buses(graph, [66], [70])


@pytest.mark.parametrize('graph, outputs, stopped', [
    (None, [66], [70]), ({66: 80, 80: 0}, [66], [70]),
    ({66: 70, 70: 0}, [66], [70]), ({66: 0}, [66], [66]),
    ({66: 80, 70: 80, 80: 0}, [66], [80]),
    ({66: 80, 70: 80, 80: 66}, [66], [70]),
    ({66: 0, 70: 99, 99: 70}, [66], [70]),
    ({66: 80, 70: 80, 80: 0}, [66, 70], [70]),
])
def test_missing_cyclic_ancestor_and_multiple_explicit_routes_stay_unknown(graph, outputs, stopped):
    with pytest.raises(ValueError):
        separate_stop_buses(graph, outputs, stopped)
