from types import SimpleNamespace
from dataclasses import fields
import json

import pytest

from backend import genshin_original_dialogue as o
from backend.genshin_native_dialogue import NativeDialogue, canonical_contracts, trigger_names
from backend.voice_assets import wwise_short_id


def contracts(offsets=(24, 40)):
    child = o.Record((o.Field('storedText', o.Word()), o.Field('storedId', o.Word())))
    parent = o.Record((o.Field('nodes', o.Array(o.Word(), child)),))
    rows = {
        7: [{'name': '_storedText', 'authored_offset_word': offsets[0]},
            {'name': '_storedId', 'authored_offset_word': offsets[1]}],
        8: [{'name': '_nodes', 'authored_offset_word': 16}],
    }
    view = SimpleNamespace(field_offsets=rows.__getitem__)
    return SimpleNamespace(view=view, records={(7, 100): child, (8, 200): parent}), parent, child


@pytest.mark.parametrize('offsets', [(24, 40), (88, 12)])
def test_semantic_fields_follow_derived_offsets_not_serialization_order(offsets):
    native, original, child = contracts(offsets)
    rename = canonical_contracts(native, {(7, offsets[0]): 'textHash', (7, offsets[1]): 'id',
                                           (8, 16): 'dialogList'})
    result = rename(original)
    payload = b'\x01\0\0\0\x42\0\0\0\x37\0\0\0'
    assert o.decode_original(payload, result) == {'dialogList': [{'textHash': 66, 'id': 55}]}
    assert result.fields[0].value.value is rename(child)
    assert original.fields[0].name == 'nodes'
    assert child.fields[0].name == 'storedText'
    with pytest.raises(ValueError):
        o.decode_original(payload[:-1], result)
    with pytest.raises(ValueError):
        o.decode_original(payload + b'\0', result)


@pytest.mark.parametrize('roles', [{(7, 24): 'storedId'}, {(7, 99): 'id'}, {(7, 24): 'invalid-name'}])
def test_missing_ambiguous_or_invalid_native_roles_reject(roles):
    native, _, _ = contracts()
    with pytest.raises(ValueError):
        canonical_contracts(native, roles)


def row(uuid, argument=9, trigger='Dialog'):
    return {'uuid': uuid, 'argument': argument, 'trigger': trigger, 'sourceNames': []}


def lut(uuid, argument=9, trigger=91, group=7):
    return wwise_short_id(uuid), {'argument': argument, 'trigger': trigger, 'file_group': group}


@pytest.mark.parametrize('enum', [2, 19, 0xffffffff])
def test_trigger_names_come_from_exact_current_uuid_and_argument(enum):
    identity, entry = lut('current-uuid', trigger=enum)
    values = {identity: entry}
    originals = {7: {'current-uuid': row('current-uuid')}}
    assert trigger_names(values, originals) == ((enum, 'Dialog'),)


def test_missing_original_uuid_does_not_vote_or_turn_into_unvoiced():
    positive_id, positive = lut('positive')
    missing_id, missing = lut('missing', argument=8)
    sources = {7: {'positive': row('positive')}}
    assert trigger_names({positive_id: positive, missing_id: missing}, sources) == ((91, 'Dialog'),)
    assert 'missing' not in sources[7]
    assert missing == {'argument': 8, 'trigger': 91, 'file_group': 7}
    with pytest.raises(ValueError):
        trigger_names({missing_id: missing}, sources)


def test_event_only_match_cannot_supply_enum_name():
    identity, entry = lut('absent')
    with pytest.raises(ValueError):
        trigger_names({identity: entry}, {7: {'another': row('another')}})
    with pytest.raises(ValueError):
        trigger_names({identity: entry}, {7: {'absent': row('absent', argument=10)}})


def test_conflicting_enum_strings_and_duplicate_names_reject():
    one, first = lut('first')
    two, second = lut('second')
    with pytest.raises(ValueError):
        trigger_names({one: first, two: second}, {7: {'first': row('first'), 'second': row('second', trigger='Other')}})
    second['trigger'] = 92
    with pytest.raises(ValueError):
        trigger_names({one: first, two: second}, {7: {'first': row('first'), 'second': row('second')}})


def test_uuid_hash_collision_is_not_positive_evidence(monkeypatch):
    monkeypatch.setattr('backend.genshin_native_dialogue.wwise_short_id', lambda _: 17)
    with pytest.raises(ValueError):
        trigger_names({17: {'trigger': 8, 'argument': 9, 'file_group': 7}},
                      {7: {'first': row('first'), 'second': row('second')}})


@pytest.mark.parametrize('values', [{}, {7: {'other': row('different')}}, {7: {'invalid/uuid': row('invalid/uuid')}}])
def test_incomplete_or_invalid_group_inventory_rejects(values):
    identity, entry = lut('original')
    with pytest.raises(ValueError):
        trigger_names({identity: entry}, values)


def native_for_profile(profile):
    native = NativeDialogue.__new__(NativeDialogue)
    for field in fields(profile):
        setattr(native, field.name, getattr(profile, field.name))
    native.source_index = {'paths': (), 'contract': None}
    return native


def test_bootstrap_contracts_use_actual_preparation_and_one_original_read_per_path(tmp_path):
    from backend.tests.test_genshin_original_dialogue import fixture
    spec, inventory, originals, options = fixture()
    native = native_for_profile(spec)
    reads = []

    def read(path):
        reads.append(path)
        return originals[path]

    destination = tmp_path / 'original-snapshot.json'
    snapshot = native.prepare(destination, inventory, read, **options)
    assert len(reads) == len(set(reads)) == len(originals)
    assert json.loads(destination.read_text(encoding='utf-8')) == snapshot
    assert len(snapshot['records']) == 3
    assert sum(row['voice_status'] == 'voiced' for row in snapshot['records']) == 2
    assert snapshot['records'][-1]['voice_status'] == 'unknown'


def test_changed_native_contract_preparation_and_failed_update_retain_last_generation(tmp_path):
    from backend.tests.test_genshin_original_dialogue import fixture
    spec, inventory, originals, options = fixture()
    destination = tmp_path / 'original-snapshot.json'
    native_for_profile(spec).prepare(destination, inventory, originals.__getitem__, **options)
    previous = destination.read_bytes()
    changed, next_inventory, next_originals, next_options = fixture(1)
    # The same old read schema cannot silently accept a new native encoding.
    with pytest.raises(ValueError):
        native_for_profile(spec).prepare(destination, next_inventory, next_originals.__getitem__, **next_options)
    assert destination.read_bytes() == previous
    prepared = native_for_profile(changed).prepare(destination, next_inventory, next_originals.__getitem__, **next_options)
    assert prepared['fingerprint'] == next_options['publisher_stamp']
    assert destination.read_bytes() != previous
    previous = destination.read_bytes()
    generation_reads = 0

    def current(stamp):
        nonlocal generation_reads
        generation_reads += 1
        return generation_reads == 1

    with pytest.raises(ValueError):
        native_for_profile(changed).prepare(destination, next_inventory, next_originals.__getitem__,
                                            **{**next_options, 'current': current})
    assert destination.read_bytes() == previous


def test_bootstrap_preparation_keeps_missing_uuid_unavailable_and_missing_groups_fail_retention(tmp_path):
    from backend.tests.test_genshin_original_dialogue import fixture, encode
    import hashlib
    spec, inventory, originals, options = fixture()
    native = native_for_profile(spec)
    destination = tmp_path / 'original-snapshot.json'
    path = spec.items_prefix + '801'
    payload = encode(spec.items, {})
    originals[path] = o.OriginalObject(path, payload, hashlib.sha256(payload).hexdigest())
    prepared = native.prepare(destination, inventory, originals.__getitem__, **options)
    assert sum(row['voice_status'] == 'voiced' for row in prepared['records']) == 1
    assert sum(row['voice_status'] == 'unavailable' for row in prepared['records']) == 1
    assert sum(row['voice_status'] == 'unknown' for row in prepared['records']) == 1
    previous = destination.read_bytes()
    del originals[path]
    with pytest.raises(KeyError):
        native.prepare(destination, inventory, originals.__getitem__, **options)
    assert destination.read_bytes() == previous
