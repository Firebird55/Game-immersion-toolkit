"""Synthetic owned-contract updates and the ordinary publisher snapshot path."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct

import pytest

from backend import genshin_original_dialogue as original
from backend.voice_assets import voice_hash, wwise_short_id
from backend.local_voice import LocalVoiceAssetService


def encode(node, value):
    """Independent fixture writer; no original game bytes or parameters."""
    def word(spec, number):
        for operation, operand in reversed(spec.operations):
            number = number ^ operand if operation == 'xor' else number - operand if operation == 'add' else number + operand
            number &= (1 << spec.bits) - 1
        return number.to_bytes(spec.bits // 8, 'little')
    if isinstance(node, original.Word):
        if node.interpretation == 'float':
            value = struct.unpack('<I', struct.pack('<f', value))[0]
        elif node.interpretation == 'bool':
            value = node.false_value ^ 1 if value else node.false_value
        return word(node, value)
    if isinstance(node, original.Empty):
        assert value == {}
        return b''
    if isinstance(node, original.Tagged):
        return encode(node.tag, value['tag']) + encode(dict(node.cases)[value['tag']], value['value'])
    if isinstance(node, original.Text):
        text, result = value.encode('utf-8'), bytearray()
        for at in range(0, len(text), 8):
            chunk = text[at:at + 8]
            number = int.from_bytes(chunk, 'little')
            number = number ^ node.key if node.operation == 'xor' else (number - node.key) & ((1 << 64) - 1)
            result.extend(number.to_bytes(8, 'little')[:len(chunk)])
        return word(node.length, len(text)) + result
    if isinstance(node, original.Record):
        flag = sum(field.mask for field in node.fields if field.name in value)
        assert not any(field.raw_flag for field in node.fields)
        return ((word(node.flags, flag) if node.flags else b'')
                + b''.join(encode(field.value, value[field.name]) for field in node.fields if field.name in value))
    if isinstance(node, original.Array):
        return word(node.count, len(value)) + b''.join(encode(node.value, row) for row in value)
    return word(node.count, len(value)) + b''.join(encode(node.key, key) + encode(node.value, row) for key, row in value.items())


def profile(generation=0):
    w = original.Word(32, (('xor', 0x13579 + generation), ('add', 17 + generation)))
    text = original.Text(original.Word(16, (('xor', 0x1234 + generation),)),
                         0x8877665544332211 + generation, 'add' if generation else 'xor')
    fields = lambda *values: original.Record(tuple(original.Field(name, spec) for name, spec in values))
    conditional = lambda *values: original.Record(tuple(original.Field(name, spec, 1 << index)
        for index, (name, spec) in enumerate(values)), original.Word(8, (('xor', 0x36 + generation),)))
    inventory = original.Array(w, fields(('id', w), ('resource', text)))
    node = fields(('id', w), ('talkContentTextMapHash', w), ('nextDialogs', original.Array(w, w)))
    talk = fields(('id', w), ('dialogList', original.Array(w, node)))
    lut = original.Dictionary(w, w, fields(('argument', w), ('trigger', w), ('file_group', w)))
    source = conditional(('sourceFileName', text), ('gender', w))
    items = original.Dictionary(w, text, fields(('uuid', text), ('argument', w), ('trigger', text),
                                               ('sourceNames', original.Array(w, source))))
    return original.NativeDialogueProfile(inventory, talk, lut, items, 'Data/Voice/Lut',
        'Data/Voice/Items/', ((9 + generation, 'Dialog'),), tuple(str(n) * 64 for n in range(4)),
        '4' * 64, '5' * 64)


def fixture(generation=0, count=3, *, variants=False):
    spec = profile(generation)
    listing, objects, texts, lut = [], {}, {}, {}
    entries = {}
    stamp = 'sophon-' + str(generation) * 64

    def object(path, node, rows):
        payload = encode(node, rows)
        return original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())

    for number in range(count):
        identity, group = 100 + number, 800 + number
        path = f'Data/Talk/{identity}'
        listing.append({'id': identity, 'resource': path})
        dialog = 1000 + number
        objects[path] = object(path, spec.talk, {'id': identity, 'dialogList': [
            {'id': dialog, 'talkContentTextMapHash': dialog + 1000,
             'nextDialogs': [dialog + 1] if number + 1 < count else []}]})
        texts[str(dialog + 1000)] = f'Original sentence {number}.'
        # The final routing/choice row has no authored Lut recording.
        if number + 1 == count:
            continue
        uuid = f'fixture-uuid-{number}'
        lut[wwise_short_id(uuid)] = {'argument': dialog, 'trigger': 9 + generation, 'file_group': group}
        sources = [{'sourceFileName': f'Voice\\sample-{generation}-{number}.wem'}]
        if variants and not number:
            sources = [{'sourceFileName': 'Voice\\female.wem', 'gender': 1},
                       {'sourceFileName': 'Voice\\male.wem', 'gender': 2}]
        for source in sources:
            entries[voice_hash('Japanese\\' + source['sourceFileName'])] = {
                'publisher': stamp, 'package': 'Publisher/StreamingAssets/Japanese/fixture.pck'}
        objects[f'Data/Voice/Items/{group}'] = object(f'Data/Voice/Items/{group}', spec.items,
            {uuid: {'uuid': uuid, 'argument': dialog, 'trigger': 'Dialog', 'sourceNames': sources}})
    objects[spec.lut_path] = object(spec.lut_path, spec.lut, lut)
    inventory = object('Data/Inventory', spec.inventory, listing)
    tables = {'ja': texts, 'en': {key: value + ' Translation.' for key, value in texts.items()}}
    options = {'tables': tables, 'textmap_sha256': {'ja': 'a' * 64, 'en': 'b' * 64},
               'source_locale': 'ja', 'publisher_stamp': stamp, 'publisher_entries': entries,
               'current': lambda value: value == stamp}
    return spec, inventory, objects, options


def prepare(path, fixture_value):
    spec, inventory, objects, options = fixture_value
    return original.prepare_original_talk_snapshot(path, inventory, objects.__getitem__, spec, **options)


def routed_fixture(generation=0):
    """Whole native graph: direct Talk, one descriptor and a shared group."""
    spec, _, objects, options = fixture(generation, count=5)
    word = original.Word(32, (('xor', 0x3456 + generation),))
    wide = original.Word(64, (('add', 0x1122334455 + generation),))
    record = lambda *fields: original.Record(tuple(original.Field(name, value) for name, value in fields))
    descriptor = record(('id', word), ('assetIndex', wide), ('payloadKind', word))
    group = record(('id', word), ('talks', original.Array(word, descriptor)))
    inventory_contract = original.Array(word, record(('id', word), ('resourceKind', word), ('group', word)))
    spec = replace(spec, inventory=inventory_contract, descriptor=descriptor, descriptor_payload_kinds=(7,),
        inventory_routes=(original.InventoryRoute(0, 'Data/Talk/'),
                          original.InventoryRoute(1, 'Data/Descriptor/', representation='descriptor'),
                          original.InventoryRoute(2, 'Data/Group/', 'group', 'group', group)))
    assets, descriptors, listing = {}, {}, []
    for index in range(5):
        identity = 100 + index
        kind = 1 if index == 0 else 2 if index < 4 else 0
        listing.append({'id': identity, 'resourceKind': kind, 'group': 900})
        if not kind:
            continue
        # Same lower 40 bits, different full original identities. A shortened
        # catalog/container-name lookup must never silently pick another Talk.
        asset_index = ((index + 1) << 40) | 0x0102030405
        source = objects.pop(f'Data/Talk/{identity}')
        assets[asset_index] = original.OriginalAsset(asset_index, source.payload, source.sha256,
                                                    'c' * 64, options['publisher_stamp'])
        descriptors[identity] = {'id': identity, 'assetIndex': asset_index, 'payloadKind': 7}
    def object(path, contract, value):
        payload = encode(contract, value)
        return original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
    objects['Data/Descriptor/100'] = object('Data/Descriptor/100', descriptor, descriptors[100])
    objects['Data/Group/900'] = object('Data/Group/900', group,
                                     {'id': 900, 'talks': [descriptors[index] for index in (101, 102, 103)]})
    inventory = object('Data/Inventory', inventory_contract, listing)
    return (spec, inventory, objects, {**options, 'load_asset': assets.__getitem__}), assets, group, descriptors


def test_group_descriptors_follow_full_catalog_identity_and_ordinary_snapshot(tmp_path):
    value, assets, _, _ = routed_fixture()
    loaded = []
    options = value[3]
    options['load_asset'] = lambda identity: loaded.append(identity) or assets[identity]
    snapshot = prepare(tmp_path / 'graph.json', value)
    assert set(loaded) == set(assets) and len(loaded) == 4
    assert snapshot['original_dialogue']['inventory_rows'] == 5
    assert snapshot['original_dialogue']['talk_objects'] == 5
    assert len(snapshot['records']) == 5
    assert snapshot['records'][-1]['voice_status'] == 'unknown'
    assert snapshot['records'][0]['audio']['source'].endswith('sample-0-0.wem')
    assert snapshot['records'][2]['previous_text_id'] == 'genshin:1001'


@pytest.mark.parametrize('failure', ['missing', 'wrong_identity', 'stale', 'truncated',
                                    'unsupported_payload', 'duplicate_member', 'unknown_member', 'missing_member'])
def test_incomplete_native_resource_graph_retains_previous_snapshot(tmp_path, failure):
    path = tmp_path / 'graph.json'
    first, _, _, _ = routed_fixture()
    prepare(path, first)
    before = path.read_bytes()
    value, assets, group, descriptors = routed_fixture(1)
    spec, _, objects, options = value
    identity = next(iter(assets))
    source = assets[identity]
    if failure == 'missing':
        assets.pop(identity)
    elif failure == 'wrong_identity':
        assets[identity] = replace(source, asset_index=source.asset_index + 1)
    elif failure == 'stale':
        assets[identity] = replace(source, publisher_stamp='sophon-' + 'f' * 64)
    elif failure == 'truncated':
        payload = source.payload[:-1]
        assets[identity] = replace(source, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    else:
        members = [descriptors[index].copy() for index in (101, 102, 103)]
        if failure == 'unsupported_payload':
            members[0]['payloadKind'] = 99
        elif failure == 'duplicate_member':
            members.append(members[0])
        elif failure == 'unknown_member':
            members[0]['id'] = 999
        else:
            members.pop()
        payload = encode(group, {'id': 900, 'talks': members})
        objects['Data/Group/900'] = original.OriginalObject('Data/Group/900', payload,
                                                         hashlib.sha256(payload).hexdigest())
    with pytest.raises((ValueError, KeyError)):
        prepare(path, value)
    assert path.read_bytes() == before


def test_changed_original_graph_contract_and_catalog_identity_refresh_snapshot(tmp_path):
    path = tmp_path / 'graph.json'
    first, _, _, _ = routed_fixture()
    previous = prepare(path, first)
    second, assets, _, _ = routed_fixture(1)
    updated = prepare(path, second)
    assert updated['original_dialogue']['inventory_rows'] == 5
    assert updated['metadata_revision'] != previous['metadata_revision']
    assert updated['records'][0]['audio']['source'].endswith('sample-1-0.wem')
    for identity, source in assets.items():
        assets[identity] = replace(source, catalog_sha256='d' * 64)
    changed_catalog = prepare(path, second)
    assert changed_catalog['records'] == updated['records']
    assert changed_catalog['metadata_revision'] != updated['metadata_revision']


def indexed_fixture(generation=0):
    value, assets, group, descriptors = routed_fixture(generation)
    spec, inventory, objects, options = value
    word, wide = spec.inventory.count, spec.descriptor.fields[1].value
    index_contract = original.Dictionary(word, word, wide)
    indices = []
    for key, asset_index, source_path, representation, contract in (
            (900, (9 << 40) | 0x0102030405, 'Data/Group/900', 'group', group),
            (100, (8 << 40) | 0x0102030405, 'Data/Descriptor/100', 'descriptor', None)):
        source = objects.pop(source_path)
        assets[asset_index] = original.OriginalAsset(asset_index, source.payload, source.sha256,
                                                    'c' * 64, options['publisher_stamp'])
        path = f'Data/Index/{representation}'
        payload = encode(index_contract, {key: asset_index})
        objects[path] = original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
        indices.append(original.SourceIndex(path, index_contract, representation, contract))
    spec = replace(spec, source_indices=tuple(indices))
    return (spec, inventory, objects, options), assets, group, descriptors


def test_original_indices_enumerate_groups_and_descriptors_without_filename_probes(tmp_path):
    value, assets, _, _ = indexed_fixture()
    loaded = []
    options = value[3]
    options['load_asset'] = lambda identity: loaded.append(identity) or assets[identity]
    snapshot = prepare(tmp_path / 'indexed.json', value)
    assert len(loaded) == len(set(loaded)) == len(assets) == 6
    assert snapshot['original_dialogue']['source_indices'] == 2
    assert snapshot['original_dialogue']['inventory_rows'] == 5
    assert snapshot['original_dialogue']['talk_objects'] == 5
    assert {row['text_id'] for row in snapshot['records']} == {f'genshin:{1000 + n}' for n in range(5)}


@pytest.mark.parametrize('failure', ['missing_index_asset', 'wrong_group_id', 'truncated_index',
                                     'unknown_indexed_kind'])
def test_broken_publisher_resource_index_retains_previous_snapshot(tmp_path, failure):
    path = tmp_path / 'indexed.json'
    old, _, _, _ = indexed_fixture()
    prepare(path, old)
    before = path.read_bytes()
    value, assets, group, descriptors = indexed_fixture(1)
    spec, _, objects, _ = value
    asset_index = (9 << 40) | 0x0102030405
    if failure == 'missing_index_asset':
        assets.pop(asset_index)
    elif failure == 'wrong_group_id':
        payload = encode(group, {'id': 901, 'talks': [descriptors[n] for n in (101, 102, 103)]})
        source = assets[asset_index]
        assets[asset_index] = replace(source, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    elif failure == 'truncated_index':
        source = objects[spec.source_indices[0].path]
        payload = source.payload[:-1]
        objects[source.path] = original.OriginalObject(source.path, payload, hashlib.sha256(payload).hexdigest())
    else:
        rows = original.decode_original(value[1].payload, spec.inventory)
        rows[1]['resourceKind'] = 99
        payload = encode(spec.inventory, rows)
        inventory = original.OriginalObject(value[1].path, payload, hashlib.sha256(payload).hexdigest())
        value = spec, inventory, objects, value[3]
    with pytest.raises((ValueError, KeyError)):
        prepare(path, value)
    assert path.read_bytes() == before


def test_changed_native_index_and_routes_refresh_current_original_snapshot(tmp_path):
    path = tmp_path / 'indexed.json'
    first = prepare(path, indexed_fixture()[0])
    second = prepare(path, indexed_fixture(1)[0])
    assert first['original_dialogue']['profile_sha256'] != second['original_dialogue']['profile_sha256']
    assert first['metadata_revision'] != second['metadata_revision']
    assert first['fingerprint'] != second['fingerprint']
    assert {row['text_id'] for row in first['records']} == {row['text_id'] for row in second['records']}
    assert second['records'][0]['audio']['source'].endswith('sample-1-0.wem')
    assert json.loads(path.read_text(encoding='utf-8')) == second


def test_source_index_group_keys_do_not_replace_talk_inventory_ids(tmp_path):
    value, _, _, _ = indexed_fixture()
    spec, inventory, objects, options = value
    contract = original.Dictionary(spec.inventory.count, spec.inventory.count,
                                   spec.descriptor.fields[1].value)
    # NPC/cutscene index identities have their own namespace. A matching number
    # must not bypass the inventory's actual Talk binding.
    payload = encode(contract, {101: (7 << 40) | 0x0102030405})
    path = 'Data/Index/other'
    objects[path] = original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
    talk = encode(spec.talk, {'id': 101, 'dialogList': [
        {'id': 7000, 'talkContentTextMapHash': 8000, 'nextDialogs': []}]})
    assets = dict(options['load_asset'].__self__)
    asset_index = (7 << 40) | 0x0102030405
    assets[asset_index] = original.OriginalAsset(asset_index, talk, hashlib.sha256(talk).hexdigest(),
                                               'c' * 64, options['publisher_stamp'])
    options['load_asset'] = assets.__getitem__
    for table in options['tables'].values():
        table['8000'] = 'Other authored caption.'
    spec = replace(spec, source_indices=(*spec.source_indices, original.SourceIndex(path, contract)))
    snapshot = prepare(tmp_path / 'namespaces.json', (spec, inventory, objects, options))
    assert {row['text_id'] for row in snapshot['records']} == {
        *[f'genshin:{1000 + n}' for n in range(5)], 'genshin:7000'}
    assert next(row for row in snapshot['records'] if row['text_id'] == 'genshin:7000')['voice_status'] == 'unknown'


def test_compound_group_route_keeps_both_authored_ids_and_checks_group_root(tmp_path):
    value, assets, old_group, descriptors = routed_fixture()
    spec, _, objects, options = value
    word = spec.inventory.count
    group = original.Record((original.Field('id', word), original.Field('id2', word),
                             old_group.fields[1]))
    listing = [{'id': 100 + n, 'resourceKind': 1 if not n else 2 if n < 4 else 0,
                'pair': [900, 1234]} for n in range(5)]
    inventory_contract = original.Array(word, original.Record((original.Field('id', word),
        original.Field('resourceKind', word), original.Field('pair', original.Array(word, word)))))
    payload = encode(inventory_contract, listing)
    inventory = original.OriginalObject('Data/Inventory', payload, hashlib.sha256(payload).hexdigest())
    route = original.InventoryRoute(2, 'Data/Gadget/', 'pair', 'group', group, (0, 1))
    spec = replace(spec, inventory=inventory_contract,
                   inventory_routes=tuple(route if item.kind == 2 else item for item in spec.inventory_routes))
    objects.pop('Data/Group/900')
    group_path = 'Data/Gadget/900_1234'
    payload = encode(group, {'id': 900, 'id2': 1234, 'talks': [descriptors[n] for n in (101, 102, 103)]})
    objects[group_path] = original.OriginalObject(group_path, payload, hashlib.sha256(payload).hexdigest())
    path = tmp_path / 'compound.json'
    snapshot = prepare(path, (spec, inventory, objects, options))
    assert len(snapshot['records']) == 5
    before = path.read_bytes()
    wrong = encode(group, {'id': 900, 'id2': 4321, 'talks': [descriptors[n] for n in (101, 102, 103)]})
    objects[group_path] = original.OriginalObject(group_path, wrong, hashlib.sha256(wrong).hexdigest())
    with pytest.raises(ValueError):
        prepare(path, (spec, inventory, objects, options))
    assert path.read_bytes() == before


def test_authored_empty_talk_array_is_no_caption_and_never_unvoiced(tmp_path):
    spec, inventory, objects, options = fixture(count=5)
    old_contract = spec.talk
    talk = original.Record((old_contract.fields[0], replace(old_contract.fields[1], mask=1)), original.Word(8))
    for identity in range(100, 105):
        source = objects[f'Data/Talk/{identity}']
        decoded = original.decode_original(source.payload, old_contract)
        if identity == 104:
            decoded.pop('dialogList')
        payload = encode(talk, decoded)
        objects[source.path] = original.OriginalObject(source.path, payload, hashlib.sha256(payload).hexdigest())
    snapshot = prepare(tmp_path / 'empty.json', (replace(spec, talk=talk), inventory, objects, options))
    assert snapshot['original_dialogue']['talk_objects'] == 5
    assert len(snapshot['records']) == 4
    assert all(row['voice_status'] != 'unvoiced' for row in snapshot['records'])
    assert 'genshin:1004' not in {row['text_id'] for row in snapshot['records']}


def projected_fixture(generation=0, suffix=b'unused synthetic gameplay fields'):
    value, assets, group, descriptors = indexed_fixture(generation)
    spec, inventory, objects, options = value
    word = spec.inventory.count
    text = original.Text(original.Word(16, (('add', 3 + generation),)),
                         0x1122334455667788 + generation)
    nested = original.Record((original.Field('label', text, 1),
                              original.Field('numbers', original.Array(word, word), 4)),
                             original.Word(8, (('xor', 5 + generation),)))
    tagged = original.Tagged(original.Word(8, (('xor', 0x21 + generation),)),
                              ((2, original.Empty()), (9, nested)))
    record = original.Record((original.Field('prelude', original.Array(word, tagged)), group.fields[1]))
    prefix = {'prelude': [{'tag': 2, 'value': {}},
                          {'tag': 9, 'value': {'label': '前置🙂', 'numbers': [7, 11]}}],
              'talks': [descriptors[n] for n in (101, 102, 103)]}
    identity = (9 << 40) | 0x0102030405
    raw = encode(record, prefix) + suffix
    assets[identity] = replace(assets[identity], payload=raw, sha256=hashlib.sha256(raw).hexdigest())
    projection = original.IndexedGroupPrefix(record)
    source = replace(spec.source_indices[0], group_contract=projection)
    spec = replace(spec, source_indices=(source, *spec.source_indices[1:]))
    return (spec, inventory, objects, options), assets, prefix


def test_native_index_owned_prefix_retains_whole_digest_and_exact_consumption(tmp_path):
    value, assets, prefix = projected_fixture()
    snapshot = prepare(tmp_path / 'prefix.json', value)
    identity = (9 << 40) | 0x0102030405
    contract = value[0].source_indices[0].group_contract
    source = assets[identity]
    proof, = snapshot['original_dialogue']['prefix_projections']
    assert proof == {'asset_index': identity, 'sha256': source.sha256,
                     'catalog_sha256': source.catalog_sha256, 'kind': 'index-owned-group-prefix',
                     'consumed_bytes': len(encode(contract.record, prefix)),
                     'whole_payload_bytes': len(source.payload)}
    assert proof['consumed_bytes'] < proof['whole_payload_bytes']
    assert len(snapshot['records']) == 5 and snapshot['original_dialogue']['inventory_rows'] == 5
    with pytest.raises(ValueError):
        original.decode_original(source.payload, contract.record)
    with pytest.raises(ValueError):
        original.decode_original(source.payload, contract)
    with pytest.raises(ValueError):
        original.InventoryRoute(2, 'Data/Group/', 'id', 'group', contract)


def test_changed_prefix_operands_and_unused_tail_preserve_authored_caption_identity(tmp_path):
    path = tmp_path / 'prefix.json'
    first = prepare(path, projected_fixture()[0])
    changed_tail = prepare(path, projected_fixture(suffix=b'changed unused native gameplay fields')[0])
    assert first['records'] == changed_tail['records']
    assert first['metadata_revision'] != changed_tail['metadata_revision']
    assert first['original_dialogue']['prefix_projections'] != changed_tail['original_dialogue']['prefix_projections']
    refreshed = prepare(path, projected_fixture(1)[0])
    assert refreshed['fingerprint'] != changed_tail['fingerprint']
    assert refreshed['original_dialogue']['profile_sha256'] != changed_tail['original_dialogue']['profile_sha256']
    assert {row['text_id'] for row in refreshed['records']} == {row['text_id'] for row in first['records']}
    assert refreshed['records'][0]['audio']['source'].endswith('sample-1-0.wem')


@pytest.mark.parametrize('failure', ['unknown_tag', 'truncated_prefix', 'unknown_member'])
def test_incomplete_native_prefix_cannot_replace_snapshot(tmp_path, failure):
    path = tmp_path / 'prefix.json'
    prepare(path, projected_fixture()[0])
    before = path.read_bytes()
    value, assets, prefix = projected_fixture(1)
    identity = (9 << 40) | 0x0102030405
    record = value[0].source_indices[0].group_contract.record
    payload = encode(record, prefix)
    if failure == 'unknown_tag':
        # The first collection item has an explicit tag. No arbitrary skip,
        # null interpretation or alternate factory reader may consume it.
        tag = record.fields[0].value.value.tag
        payload = payload[:4] + encode(tag, 99) + payload[5:]
    elif failure == 'truncated_prefix':
        payload = payload[:-1]
    else:
        prefix['talks'][0]['id'] = 999
        payload = encode(record, prefix)
    assets[identity] = replace(assets[identity], payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(ValueError):
        prepare(path, value)
    assert path.read_bytes() == before


def test_tagged_native_factory_requires_unique_known_tags_and_strict_eof():
    contract = original.Tagged(original.Word(8), ((0, original.Empty()),
        (3, original.Record((original.Field('number', original.Word(16)),)))))
    assert original.decode_original(b'\0', contract) == {'tag': 0, 'value': {}}
    assert original.decode_original(b'\x03\x34\x12', contract) == {'tag': 3, 'value': {'number': 0x1234}}
    for payload in (b'\x02', b'\x03\x34', b'\x00\x12'):
        with pytest.raises(ValueError):
            original.decode_original(payload, contract)
    with pytest.raises(ValueError):
        original.decode_original(b'\0', replace(contract, cases=((0, original.Empty()), (0, original.Empty()))))
    with pytest.raises(ValueError):
        original.IndexedGroupPrefix(original.Record((original.Field('unknown', original.Word()),)))


def test_complete_authored_inventory_and_ordinary_voice_service(tmp_path, monkeypatch):
    value = fixture(count=137, variants=True)
    path = tmp_path / 'textmap.json'
    snapshot = prepare(path, value)
    assert snapshot['original_dialogue']['inventory_rows'] == 137
    assert snapshot['original_dialogue']['talk_objects'] == 137
    assert len(snapshot['records']) == 138
    assert snapshot['records'][-1]['voice_status'] == 'unknown'
    assert not any(row['voice_status'] == 'unvoiced' for row in snapshot['records'])
    first = {row['player_voice']: row for row in snapshot['records'] if row['text_id'].startswith('genshin:1000:')}
    assert set(first) == {'female', 'male'}
    assert first['female']['audio']['source'] == 'Japanese\\Voice\\female.wem'
    assert snapshot['records'][2]['previous_text_id'] == 'genshin:1000'
    assert json.loads(path.read_text(encoding='utf-8')) == snapshot
    # The actual service reopens the produced snapshot and delegates extraction
    # to the existing publisher adapter, without looking for an installation.
    import backend.local_voice as local
    monkeypatch.setattr(local, 'ffmpeg_executable', lambda: tmp_path / 'ffmpeg')
    monkeypatch.setattr(local, 'asset_adapter', lambda game: (type('Adapter', (), {
        'publisher_snapshot_available': staticmethod(lambda tools, stamp: stamp == value[3]['publisher_stamp'])})(), ''))
    decoder = tmp_path / 'decoder'
    decoder.write_bytes(b'fixture tool marker; never executed')
    service = LocalVoiceAssetService('genshin', tmp_path, decoder, tmp_path / 'playback')
    try:
        assert service.ready and service.has_variant('genshin:1000:female')
        assert service._install is None
        assert service._entries['genshin:1001']['publisher'] == snapshot['fingerprint']
    finally:
        service.close()


def test_changed_native_parameters_and_new_inventory_are_refreshable(tmp_path):
    path = tmp_path / 'textmap.json'
    first, second = prepare(path, fixture()), prepare(path, fixture(1, count=5))
    assert first['original_dialogue']['profile_sha256'] != second['original_dialogue']['profile_sha256']
    assert second['original_dialogue']['inventory_rows'] == 5
    assert second['fingerprint'] == 'sophon-' + '1' * 64
    assert second['metadata_revision'] != first['metadata_revision']
    assert second['records'][0]['audio']['source'].endswith('sample-1-0.wem')


@pytest.mark.parametrize('failure', ['missing', 'truncated', 'changed_release', 'wrong_path', 'interrupted_write'])
def test_failed_update_retains_previous_then_retries(tmp_path, monkeypatch, failure):
    path = tmp_path / 'textmap.json'
    prepare(path, fixture())
    previous = path.read_bytes()
    spec, inventory, objects, options = updated = fixture(1)
    loader = objects.__getitem__
    if failure == 'missing':
        loader = lambda key: (_ for _ in ()).throw(FileNotFoundError(key))
    elif failure == 'truncated':
        obj = objects['Data/Talk/100']
        raw = obj.payload[:-1]
        objects[obj.path] = original.OriginalObject(obj.path, raw, hashlib.sha256(raw).hexdigest())
    elif failure == 'changed_release':
        options['current'] = lambda stamp: False
    elif failure == 'wrong_path':
        loader = lambda key: replace(objects[key], path='Data/Wrong')
    else:
        saved = Path.replace
        monkeypatch.setattr(Path, 'replace', lambda *_: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises((ValueError, FileNotFoundError, OSError)):
        original.prepare_original_talk_snapshot(path, inventory, loader, spec, **options)
    assert path.read_bytes() == previous
    if failure == 'interrupted_write':
        monkeypatch.setattr(Path, 'replace', saved)
    assert prepare(path, fixture(1))['fingerprint'] != json.loads(previous)['fingerprint']


@pytest.mark.parametrize('ambiguity', ['missing_uuid', 'duplicate_event', 'uuid_hash_collision', 'wrong_argument'])
def test_unresolved_original_voice_never_falls_back_to_another_recording(tmp_path, ambiguity):
    spec, inventory, objects, options = value = fixture()
    path = 'Data/Voice/Items/800'
    items = original.decode_original(objects[path].payload, spec.items)
    if ambiguity == 'missing_uuid':
        items = {}
    elif ambiguity == 'wrong_argument':
        next(iter(items.values()))['argument'] = 99999
    elif ambiguity == 'uuid_hash_collision':
        uuid, row = next(iter(items.items()))
        items[uuid.upper()] = {**row, 'uuid': uuid.upper()}
    else:
        lut = original.decode_original(objects[spec.lut_path].payload, spec.lut)
        key, row = next(iter(lut.items()))
        lut[key + 1] = row
        payload = encode(spec.lut, lut)
        objects[spec.lut_path] = original.OriginalObject(spec.lut_path, payload, hashlib.sha256(payload).hexdigest())
    payload = encode(spec.items, items)
    objects[path] = original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
    snapshot = prepare(tmp_path / 'textmap.json', value)
    first = next(row for row in snapshot['records'] if row['text_id'] == 'genshin:1000')
    assert first['audio'] is None and first['voice_status'] == 'unavailable'
    assert next(row for row in snapshot['records'] if row['text_id'] == 'genshin:1002')['voice_status'] == 'unknown'


def test_word_text_flags_aliases_and_strict_input_limits(monkeypatch):
    word = original.Word(16, (('add', 7), ('xor', 0x1234)))
    string = original.Text(word, 0xfedcba9876543210, 'add')
    for text in ('', 'a', '字幕🙂', 'x' * 23):
        payload = encode(string, text)
        assert original.decode_original(payload, string) == text
        with pytest.raises(ValueError):
            original.decode_original(payload + b'\0', string)
    flag = original.Record((original.Field('raw', original.Word(8), 1, True),
                            original.Field('decoded', original.Word(8), 2)), original.Word(8, (('xor', 2),)))
    assert original.decode_original(bytes([1, 8, 9]), flag) == {'raw': 8, 'decoded': 9}
    with pytest.raises(ValueError):
        original.decode_original(bytes([1, 8]), flag)
    inverse = original.Record((original.Field('selected', original.Word(8), 1,
        present_when_set=False, default=0),), original.Word(8))
    assert original.decode_original(bytes([0, 7]), inverse) == {'selected': 7}
    assert original.decode_original(bytes([1]), inverse) == {'selected': 0}
    dictionary = original.Dictionary(original.Word(8), original.Word(8), original.Word(8))
    with pytest.raises(ValueError):
        original.decode_original(bytes([2, 1, 8, 1, 9]), dictionary)
    with pytest.raises(UnicodeDecodeError):
        original.decode_original(b'\x01\x00\xff', original.Text(original.Word(16), 0))
    with pytest.raises(ValueError):
        original.Word(8, (('execute', 1),))
    with pytest.raises(ValueError):
        original.decode_original(encode(original.Word(), 99), original.Array(original.Word(), original.Word()))
    with pytest.raises(ValueError):
        original.decode_original(b'\0\0\x80\x7f', original.Word(32, interpretation='float'))
    with pytest.raises(ValueError):
        original.OriginalObject('Data/../escape', b'x', hashlib.sha256(b'x').hexdigest())
    monkeypatch.setattr(original, 'MAX_VALUES', 2)
    with pytest.raises(ValueError):
        original.decode_original(encode(original.Array(original.Word(), original.Word()), [1, 2]),
                                 original.Array(original.Word(), original.Word()))


def test_complete_large_nested_inventory_fits_the_bounded_reader():
    # An authored table can have modest row/byte counts but millions of nested
    # values. This exceeds the earlier cap without any individual huge array.
    count, width = 51_000, 100
    payload = struct.pack('<I', count) + (bytes([width]) + bytes(width)) * count
    contract = original.Array(original.Word(), original.Array(original.Word(8), original.Word(8)))
    rows = original.decode_original(payload, contract)
    assert len(rows) == count and all(len(row) == width for row in rows)
    assert rows[0] == rows[-1] == [0] * width


def test_missing_pack_is_unavailable_and_other_translations_stay_exact(tmp_path):
    spec, inventory, objects, options = value = fixture(variants=True)
    options['publisher_entries'] = {}
    snapshot = prepare(tmp_path / 'textmap.json', value)
    records = {row['text_id']: row for row in snapshot['records']}
    assert records['genshin:1000:female']['voice_status'] == 'unavailable'
    assert records['genshin:1000:male']['voice_status'] == 'unavailable'
    assert records['genshin:1002']['voice_status'] == 'unknown'
    assert records['genshin:1001']['texts']['en'] == 'Original sentence 1. Translation.'
    assert not any(row['audio'] or row['voice_status'] == 'unvoiced' for row in records.values())


def test_incomplete_inventory_and_input_budget_cannot_replace_cache(tmp_path, monkeypatch):
    destination = tmp_path / 'textmap.json'
    prepare(destination, fixture())
    previous = destination.read_bytes()
    spec, inventory, objects, options = value = fixture(1)
    raw = encode(spec.inventory, [{'id': 999, 'resource': 'Data/Talk/100'}])
    inventory = original.OriginalObject(inventory.path, raw, hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):
        original.prepare_original_talk_snapshot(destination, inventory, objects.__getitem__, spec, **options)
    assert destination.read_bytes() == previous
    monkeypatch.setattr(original, 'MAX_TOTAL', len(value[1].payload))
    with pytest.raises(ValueError):
        prepare(destination, value)
    assert destination.read_bytes() == previous


def test_native_inventory_routes_use_typed_identity_and_reject_unknown_routes(tmp_path):
    spec, inventory, objects, options = fixture()
    word = original.Word(32, (('xor', 0x12345678),))
    contract = original.Array(word, original.Record((original.Field('id', word),
        original.Field('resourceKind', word), original.Field('resourceId', word))))
    route = original.InventoryRoute(17, 'Data/Talk/', 'resourceId')
    spec = replace(spec, inventory=contract, inventory_routes=(route,))
    listing = [{'id': 5000 + n, 'resourceKind': 17, 'resourceId': 100 + n} for n in range(3)]
    # Several inventory records can explicitly refer to one original object.
    listing.append({'id': 9000, 'resourceKind': 17, 'resourceId': 101})
    raw = encode(contract, listing)
    inventory = original.OriginalObject(inventory.path, raw, hashlib.sha256(raw).hexdigest())
    loaded = []

    def load(path):
        loaded.append(path)
        return objects[path]

    destination = tmp_path / 'textmap.json'
    snapshot = original.prepare_original_talk_snapshot(destination, inventory, load, spec, **options)
    assert snapshot['original_dialogue']['inventory_rows'] == 4
    assert snapshot['original_dialogue']['talk_objects'] == 3
    assert loaded.count('Data/Talk/101') == 1
    previous = destination.read_bytes()
    listing[0]['resourceKind'] = 18
    raw = encode(contract, listing)
    inventory = original.OriginalObject(inventory.path, raw, hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):
        original.prepare_original_talk_snapshot(destination, inventory, load, spec, **options)
    assert destination.read_bytes() == previous


def test_actual_parsed_translation_content_contributes_to_identity(tmp_path):
    destination = tmp_path / 'textmap.json'
    value = fixture()
    first = prepare(destination, value)
    value[3]['tables']['en']['2000'] = 'Changed original translation.'
    second = prepare(destination, value)
    assert first['metadata_revision'] != second['metadata_revision']
    assert second['records'][0]['texts']['en'] == 'Changed original translation.'


@pytest.mark.parametrize('missing', ['uuid', 'choice'])
def test_authored_missing_voice_text_survives_into_explicit_index_capture(tmp_path, missing):
    from backend.multilingual_index import MultilingualTextIndex
    spec, inventory, objects, options = value = fixture()
    identity = '1000' if missing == 'uuid' else '1002'
    expected = 'unavailable' if missing == 'uuid' else 'unknown'
    text = 'これは正式な会話の字幕です。対応する録音の調査はまだ終わっていません。'
    options['tables']['ja'][str(int(identity) + 1000)] = text
    unrelated = 'この画面全般の説明は、会話に紐付けられていない翻訳です。'
    options['tables']['ja']['999999'] = unrelated
    if missing == 'uuid':
        path = 'Data/Voice/Items/800'
        payload = encode(spec.items, {})
        objects[path] = original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
    snapshot = prepare(tmp_path / 'textmap.json', value)
    row = next(row for row in snapshot['records'] if row['text_id'] == 'genshin:' + identity)
    assert row['text_capture_verified'] and row['voice_status'] == expected and row['audio'] is None
    assert unrelated not in {row['source_text'] for row in snapshot['records']}
    index = MultilingualTextIndex('genshin', tmp_path)
    assert index.ready, index.message
    assert index.match_text(text) is None
    index.capture_unvoiced = True
    assert index.match_text(text) is None
    index.capture_missing_audio = True
    hit = index.match_text(text)
    assert hit and hit.text_id == row['text_id'] and hit.text_capture_verified
    assert hit.is_verified_missing_audio and hit.voice_status == expected
    assert index.match_text(text.split('。')[0] + '。') is None
    assert index.match_text(text.replace('正式', '正確')) is None
    assert index.match_text('別の説明です。' + text) is None
    assert index.match_text(unrelated) is None


def test_ambiguous_authored_talk_captions_stay_excluded_with_missing_audio_enabled(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    spec, inventory, objects, options = value = fixture()
    text = 'これは同じ字幕ですが、二つの正式な会話で翻訳と音声の状態が異なります。'
    options['tables']['ja']['2000'] = options['tables']['ja']['2002'] = text
    path = 'Data/Voice/Items/800'
    payload = encode(spec.items, {})
    objects[path] = original.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
    snapshot = prepare(tmp_path / 'textmap.json', value)
    captions = [row for row in snapshot['records'] if row['source_text'] == text]
    assert len(captions) == 2 and all(row['text_capture_verified'] for row in captions)
    assert {row['voice_status'] for row in captions} == {'unknown', 'unavailable'}
    index = MultilingualTextIndex('genshin', tmp_path)
    assert index.ready, index.message
    index.capture_missing_audio = True
    assert index.match_text(text) is None


def test_unresolved_original_source_template_never_gains_capture_provenance(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    value = fixture()
    text = '#{M#Resolved}{F#Unclosed'
    value[3]['tables']['ja']['2000'] = text
    snapshot = prepare(tmp_path / 'textmap.json', value)
    unresolved = [row for row in snapshot['records'] if row.get('text_binding_unresolved')]
    assert unresolved and all(row['text_capture_verified'] is False for row in unresolved)
    index = MultilingualTextIndex('genshin', tmp_path)
    assert index.ready, index.message
    index.capture_missing_audio = True
    index.capture_unvoiced = True
    assert index.match_text(text) is None
