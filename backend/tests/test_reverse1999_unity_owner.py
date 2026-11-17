"""Owned Unity script-owner references, no game bytecode/assets/key literals."""
import struct

import pytest

from backend.reverse1999_unity_owner import inspect_game_config
from backend.tests.test_reverse1999_bootstrap import integer, string


def asset(rows, *, references=(), externals=()):
    types = list(dict.fromkeys((cid, script_index) for _pid, cid, script_index, _data in rows))
    metadata = b'2022.3.62f2\0' + integer(19) + b'\0' + integer(len(types))
    for cid, index in types:
        metadata += integer(cid) + b'\0' + struct.pack('<h', index)
        metadata += b'\0' * (32 if cid == 114 else 16)
    metadata += integer(len(rows))
    payload = b''
    for pid, cid, index, data in rows:
        metadata += b'\0' * (-(48 + len(metadata)) % 4)
        metadata += struct.pack('<qqIi', pid, len(payload), len(data), types.index((cid, index)))
        payload += data
    metadata += integer(len(references))
    for file_id, path_id in references:
        metadata += integer(file_id) + b'\0' * (-(48 + len(metadata) + 4) % 4) + struct.pack('<q', path_id)
    metadata += integer(len(externals))
    for path in externals:
        metadata += b'\0' + b'\0' * 16 + integer(0) + path.encode() + b'\0'
    metadata += integer(0) + b'\0'
    data_start = 48 + len(metadata)
    header = b'\0' * 8 + struct.pack('>I', 22) + b'\0' * 8
    header += struct.pack('>IQQQ', len(metadata), data_start + len(payload), data_start, 0)
    return header + metadata + payload


def fixture(*, instance='renamed-publisher-settings', config_id=81, script_id=901,
            namespace='SLFramework', class_name='GameConfigAsset', assembly='Assembly-CSharp',
            table_id=None, script_index=0, duplicate=False, script_type=115, external='globalgamemanagers.assets'):
    owner = string('independent-script-object-name') + integer(0) + b'\0' * 16
    owner += string(class_name) + string(namespace) + string(assembly)
    fields = integer(16) + b'opaque config001'
    data = b'\0' * 16 + struct.pack('<iq', 1, script_id) + string(instance) + fields
    rows = [(config_id, 114, script_index, data)]
    if duplicate:
        rows.append((config_id + 1, 114, script_index, data))
    raw = asset(rows, references=[(1, script_id if table_id is None else table_id)], externals=[external])
    dependency = asset([(script_id, script_type, -1, owner)])
    return raw, {external: dependency}


def test_exact_script_pointer_and_serialized_type_table_establish_authored_class_owner():
    raw, dependencies = fixture()
    source = inspect_game_config(raw, dependencies=dependencies)
    assert source.owner.instance_name == 'renamed-publisher-settings'
    assert (source.owner.namespace, source.owner.class_name, source.owner.assembly) == (
        'SLFramework', 'GameConfigAsset', 'Assembly-CSharp')
    assert source.owner.script_asset == 'globalgamemanagers.assets'
    assert source.encrypted_payload == b'opaque config001'
    assert 'opaque config001' not in repr(source)


def test_normal_object_ids_instance_name_and_declared_assembly_changes_are_data_driven():
    raw, dependencies = fixture(instance='new-region-settings', config_id=9031, script_id=70007,
                                assembly='Publisher.Framework')
    source = inspect_game_config(raw, dependencies=dependencies)
    assert source.owner.object_id == 9031 and source.owner.script_object_id == 70007
    assert source.owner.assembly == 'Publisher.Framework'


def test_same_file_script_ownership_uses_its_authored_local_reference():
    script = string('config') + integer(0) + b'\0' * 16
    script += string('GameConfigAsset') + string('SLFramework') + string('Publisher.Framework')
    component = b'\0' * 16 + struct.pack('<iq', 0, 67) + string('settings')
    component += integer(3) + b'abc'
    raw = asset([(8, 114, 0, component), (67, 115, -1, script)], references=[(0, 67)])
    source = inspect_game_config(raw, dependencies={})
    assert source.owner.script_asset == 'resources.assets'
    assert source.encrypted_payload == b'abc'


def test_incomplete_config_byte_array_never_becomes_a_decoded_configuration():
    script = string('config') + integer(0) + b'\0' * 16
    script += string('GameConfigAsset') + string('SLFramework') + string('Publisher.Framework')
    component = b'\0' * 16 + struct.pack('<iq', 0, 67) + string('settings')
    component += integer(8) + b'abc'
    raw = asset([(8, 114, 0, component), (67, 115, -1, script)], references=[(0, 67)])
    with pytest.raises(ValueError, match='Truncated'):
        inspect_game_config(raw, dependencies={})


@pytest.mark.parametrize('options,match', [
    ({'table_id': 902}, 'ownership disagree'),
    ({'script_index': -1}, 'ownership disagree'),
    ({'namespace': 'Unrelated', 'instance': 'bluepoch'}, 'owner is missing'),
    ({'class_name': 'Unrelated', 'instance': 'bluepoch'}, 'owner is missing'),
    ({'duplicate': True}, 'ambiguous'),
    ({'script_type': 49}, 'does not resolve to a MonoScript'),
    ({'external': '../untrusted.assets'}, 'identity'),
    ({'external': '/untrusted.assets'}, 'identity'),
])
def test_names_or_raw_pointer_bytes_cannot_override_authored_owner_checks(options, match):
    raw, dependencies = fixture(**options)
    with pytest.raises(ValueError, match=match):
        inspect_game_config(raw, dependencies=dependencies)


def test_missing_owner_is_actionable_and_never_resolved_against_the_host_filesystem():
    raw, _dependencies = fixture()
    with pytest.raises(ValueError, match='dependency is missing'):
        inspect_game_config(raw, dependencies={})


def test_source_alias_collision_and_unbounded_dependency_count_are_refused():
    raw, dependencies = fixture()
    with pytest.raises(ValueError, match='Duplicate'):
        inspect_game_config(raw, dependencies={**dependencies, 'resources.assets': raw})
    with pytest.raises(ValueError, match='limit'):
        inspect_game_config(raw, dependencies={f'{i}.assets': raw for i in range(16)})
