"""Synthetic BEYOND localization audit: no shipped game text or media."""
import struct

import pytest

from backend import quantic_assets as q


def integers(*values):
    return struct.pack('<' + 'I' * len(values), *values)


def string(value, unicode=False):
    encoded = value.encode('utf-16-le' if unicode else 'ascii')
    return integers(len(encoded)) + encoded


def table(pointer=b'\0', flag=0, dependency=True, repeated=False):
    dependencies = integers(4091, 42) + b'\1' if dependency else b''
    data = b'COM_CONT' + integers(4, int(dependency)) + dependencies
    data += b'LOADCONT' + integers(2) + b'LOCALIZ_' + integers(5) + b'\0' + integers(1)
    data += b'\1' + string('ENG') + integers(1) + string('TEST') + string('Synthetic text only.', True) + integers(flag)
    data += integers(2 if repeated else 1) + string('TEST') + pointer
    if repeated:
        data += string('TEST') + b'\1\1' + integers(4091, 999)
    return data


def test_localization_preserves_null_vs_unresolved_pointer_and_text_flags():
    null = q.localization(table(flag=7))['ENG']
    assert null['texts'] == {'TEST': 'Synthetic text only.'}
    assert null['bindings'] == {'TEST': None}
    assert null['binding_states'] == {'TEST': 'none'}
    assert null['text_flags'] == {'TEST': 7}
    unresolved = q.localization(table(b'\1\1' + integers(4091, 42), dependency=False))['ENG']
    assert unresolved['bindings'] == {'TEST': None}
    assert unresolved['binding_states'] == {'TEST': 'unresolved'}
    internal = q.localization(table(b'\1\0' + integers(4091, 42)))['ENG']
    assert internal['binding_states'] == {'TEST': 'internal'}
    resolved = q.localization(table(b'\1\1' + integers(4091, 42)))['ENG']
    assert resolved['bindings'] == {'TEST': (4091, 42)}
    assert resolved['binding_states'] == {'TEST': 'resolved'}


def test_localization_rejects_unsupported_scope_and_contradictory_null_pointer():
    with pytest.raises(ValueError, match='pointer scope'):
        q.localization(table(b'\1\2' + integers(4091, 42)))
    with pytest.raises(ValueError, match='pointer state'):
        q.localization(table(repeated=True))
