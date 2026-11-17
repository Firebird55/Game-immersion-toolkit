"""Original config decoding preserves authored types/defaults and strict bounds."""
from types import SimpleNamespace

import pytest

from backend import starrail_original_configs as configs
from backend.starrail_native_configs import _defaults
from backend.xxhash64 import xxhash64


def uint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128); number >>= 7
    return bytes(result + bytes([number]))


def text(value):
    value = value.encode('utf-8')
    return uint(len(value)) + value


class Descriptions:
    def __init__(self, number=37):
        self.registries = {'TaskBase': {number: 'AuthoredVideo'}}
        self.schemas = {
            'Root': {'fields': [('OnStart', 'Sequence[]')], 'defaults': {}},
            'Sequence': {'fields': [('Tasks', 'TaskBase[]')], 'defaults': {}},
            'AuthoredVideo': {'fields': [('VideoID', 'uint'), ('Caption', 'string'), ('Enabled', 'bool')],
                              'defaults': {'VideoID': 91, 'Caption': None, 'Enabled': True}}}

    def enum(self, kind):
        return None

    def description(self, name):
        if name not in self.schemas:
            raise ValueError('No original schema for this type')
        return self.schemas[name]

    def polymorphic(self, base, number):
        if number not in self.registries[base] or self.registries[base][number] is None:
            raise ValueError('No original factory binding for this type')
        return self.registries[base][number]


def body(number=37):
    return b'\x01\x02\x01\x02' + uint(number) + b'\x02' + text('Config/Caption.json')


@pytest.mark.parametrize('number', [37, 1042])
def test_changed_original_factory_ids_preserve_native_constructor_defaults_and_authored_caption(number):
    result = configs.decode(body(number), Descriptions(number), root='Root')
    assert result == {'OnStart': [{'Tasks': [{'$type': 'AuthoredVideo', 'VideoID': 91,
                                            'Enabled': True, 'Caption': 'Config/Caption.json'}]}]}


@pytest.mark.parametrize('change', ['unknown-factory', 'empty-factory', 'unknown-mask', 'truncated', 'trailing',
                                   'unknown-schema-field', 'wrong-default-type', 'negative-array', 'missing-child-schema'])
def test_bad_config_or_unproved_native_description_cannot_become_an_empty_success(change):
    descriptions = Descriptions(); data = body()
    if change == 'unknown-factory':
        data = body(38)
    elif change == 'empty-factory':
        descriptions.registries['TaskBase'][37] = None
    elif change == 'unknown-mask':
        data = data[:5] + b'\x08' + data[6:]
    elif change == 'truncated':
        data = data[:-1]
    elif change == 'trailing':
        data += b'\x00'
    elif change == 'unknown-schema-field':
        descriptions.schemas['AuthoredVideo']['ignored'] = True
    elif change == 'wrong-default-type':
        descriptions.schemas['AuthoredVideo']['defaults']['VideoID'] = '91'
    elif change == 'negative-array':
        data = b'\x01\x01'
    elif change == 'missing-child-schema':
        descriptions.schemas.pop('AuthoredVideo')
    with pytest.raises(ValueError):
        configs.decode(data, descriptions, root='Root')


def test_work_budget_counts_default_fields_as_well_as_encoded_values(monkeypatch):
    descriptions = Descriptions()
    descriptions.schemas['AuthoredVideo']['fields'] += [(f'Flag{i}', 'bool') for i in range(20)]
    descriptions.schemas['AuthoredVideo']['defaults'] |= {f'Flag{i}': False for i in range(20)}
    monkeypatch.setattr(configs, 'MAX_VALUES', 20)
    with pytest.raises(ValueError):
        configs.decode(body(), descriptions, root='Root')


def test_recursive_description_has_an_independent_depth_bound():
    descriptions = Descriptions()
    descriptions.schemas['Branch'] = {'fields': [('Child', 'Branch')], 'defaults': {}}
    with pytest.raises(ValueError):
        configs.decode(b'\x01' * 66 + b'\x00', descriptions, root='Branch')


def test_literal_combined_bool_store_and_float_bits_use_original_field_offsets():
    fields = [{'name': 'First', 'type': 'bool', 'offset': 0x10},
              {'name': 'Second', 'type': 'bool', 'offset': 0x11},
              {'name': 'VideoID', 'type': 'uint', 'offset': 0x18},
              {'name': 'Time', 'type': 'float', 'offset': 0x20}]
    stores = [(0x10, 'word', 0x101), (0x18, 'dword', 91), (0x20, 'dword', 0x3f800000)]
    assert _defaults(fields, stores, lambda kind: None) == {'First': True, 'Second': True, 'VideoID': 91, 'Time': 1.0}
    stores.append((0x10, 'byte', 0))
    assert _defaults(fields, stores, lambda kind: None)['Second'] is True
    stores.append((0x11, 'byte', 2))
    with pytest.raises(ValueError):
        _defaults(fields, stores, lambda kind: None)


@pytest.mark.parametrize('relative,root', [
    ('Config/Level/Mission/123/Act/Act456.json', configs.ROOT),
    ('Config/CutSceneCaption/Future_Caption.json', 'RPG.GameCore.VideoCaptionConfig'),
    ('Config/BattleCollegeCaption/FutureLesson.json', 'RPG.GameCore.VideoCaptionConfig')])
def test_original_file_uses_native_path_and_authenticated_package_before_decoding(relative, root):
    descriptions = Descriptions()
    descriptions.schemas[root] = {'fields': [('Enabled', 'bool')], 'defaults': {'Enabled': True}}
    descriptions.binary_path = lambda path: 'ChangedOriginal/' + path[:-5] + '.bin'
    asset = SimpleNamespace(size=5)
    key = xxhash64(('ChangedOriginal/' + relative[:-5] + '.bin').encode())
    calls = []
    tables = SimpleNamespace(resources={key: (asset, 2, 1)},
        _package=lambda selected: calls.append(selected) or b'xx\x00yy')
    assert configs.OriginalConfigs(tables, descriptions).file(relative) == {'Enabled': True}
    assert calls == [asset]
    tables.resources[key] = (asset, 4, 2)
    with pytest.raises(ValueError):
        configs.OriginalConfigs(tables, descriptions).file(relative)
    assert calls == [asset]


@pytest.mark.parametrize('path', ['../Config/Level/Mission/1/Act/Act1.json',
    'Config/Level/Mission/1/Act/Act1.lua', 'Config/CutSceneCaption/../Other_Caption.json',
    'Config/Unproved/Future.json'])
def test_original_file_rejects_unowned_or_unsafe_paths_before_package_access(path):
    with pytest.raises(ValueError):
        configs.OriginalConfigs(None, None).file(path)
