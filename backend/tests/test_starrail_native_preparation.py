"""Complete generation cache, invalidation and preservation without game data."""
from types import SimpleNamespace

import pytest

from backend import starrail_native_preparation as preparation


def fixture(monkeypatch):
    state = {'md5': 'a' * 32, 'logic': 'authored-logic', 'derivations': 0, 'malformed': False}
    def native(*args):
        return SimpleNamespace(receipt={'identity': {'files': {'native': {'md5': state['md5']}}}, 'outputs': {'dump.cs': 'b' * 64}})
    def routes(*args):
        return {'native_file_md5': state['md5'], 'bootstrap_files': {'config': 'moved/Client.bytes',
            'version': 'moved/Version.bytes', 'native': 'GameAssembly.dll'},
            'client_schema': [{'kind': 'string_array', 'semantic': 'GlobalDispatchUrlList'},
                              {'kind': 'u32', 'semantic': 'DefaultServerIndex'}],
            'version_schema': [{'kind': kind, 'semantic': name} for name, kind in (
                ('Branch', 'string'), ('MajorVersion', 'u32'), ('MinorVersion', 'u32'), ('PatchVersion', 'u32'),
                ('PakType', 'string'), ('DispatchSeed', 'string'))],
            'global_dispatch': {'region_list_field': 8, 'region_fields': {'name': 2, 'primary_gateway': 4, 'alternate_gateway': 6}},
            'routes': [{'route': name, 'wire_type': 2, 'field': number}
                       for name, number in zip(('design', 'asb', 'base', 'lua'), (23, 45, 67, 89))]}
    def tables(index, names):
        state['derivations'] += 1
        result = {name: {'fields': [['AddedField', 'u32']], 'identity': [], 'hash_byte_prefix': False, 'enums': {}} for name in names}
        if state['malformed']:
            result['NewTable']['unknown'] = True
        return result
    monkeypatch.setattr(preparation.metadata, 'prepare', native)
    monkeypatch.setattr(preparation, '_logic_identity', lambda: state['logic'])
    monkeypatch.setattr(preparation, 'NativeIndex', lambda native: object())
    monkeypatch.setattr(preparation.sophon, 'manifest', lambda *args: {})
    monkeypatch.setattr(preparation.routes, 'derive', routes)
    monkeypatch.setattr(preparation.tables, 'bindings', lambda index, names: names)
    monkeypatch.setattr(preparation.tables, 'descriptions', tables)
    build = {'channel': 'starrail-global', 'manifests': {'game': ('authored',)}}
    return state, build


def test_complete_descriptions_are_reused_until_native_or_logic_inputs_change(tmp_path, monkeypatch):
    state, build = fixture(monkeypatch)
    first = preparation.prepare(tmp_path, build, {'NewTable'})
    assert preparation.prepare(tmp_path, build, {'NewTable'}).identity == first.identity
    assert state['derivations'] == 1
    state['md5'] = 'c' * 32
    changed = preparation.prepare(tmp_path, build, {'NewTable'})
    assert changed.identity != first.identity and state['derivations'] == 2
    state['logic'] = 'authored-new-native-pattern'
    assert preparation.prepare(tmp_path, build, {'NewTable'}).identity != changed.identity
    assert state['derivations'] == 3


def test_malformed_new_descriptions_cannot_replace_a_working_generation(tmp_path, monkeypatch):
    state, build = fixture(monkeypatch)
    first = preparation.prepare(tmp_path, build, {'NewTable'})
    before = (tmp_path / 'native-descriptions.json').read_bytes()
    state.update(md5='d' * 32, malformed=True)
    with pytest.raises(ValueError):
        preparation.prepare(tmp_path, build, {'NewTable'})
    assert (tmp_path / 'native-descriptions.json').read_bytes() == before
    assert first.routes['native_file_md5'] == 'a' * 32
    state['malformed'] = False
    assert preparation.prepare(tmp_path, build, {'NewTable'}).routes['native_file_md5'] == 'd' * 32
