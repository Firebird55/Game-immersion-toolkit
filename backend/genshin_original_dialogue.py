"""Explicit original Talk preparation with caller-owned native read contracts.

This does not discover native ownership or change the default catalog provider.
The caller verifies publisher packages and derives the typed contracts from the
corresponding original methods. Digests bind inputs; they do not authenticate an
untrusted contract. No client code executes, and no release parameters are pinned.
"""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
import struct

from .game_tools import _atomic_file
from . import genshin_assets as game, hoyo_dialogue as common
from .voice_assets import wwise_short_id


MAX_OBJECT = 64 * 1024**2
MAX_TOTAL = 512 * 1024**2
# The original TalkExcel inventory alone has over five million decoded scalar,
# record and collection values. Keep a bounded allowance for that whole table.
MAX_VALUES = 8_000_000
MAX_COUNT = 1_000_000
MAX_SCHEMA = 4096
MAX_DEPTH = 16
MAX_OBJECTS = 100_000


def _check(value):
    if not value:
        raise ValueError('Unsupported, ambiguous or incomplete original Genshin dialogue input')


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)


@dataclass(frozen=True)
class Word:
    """Native unsigned word arithmetic, before in-memory value protection."""
    bits: int = 32
    operations: tuple = ()
    interpretation: str = 'unsigned'
    false_value: int = 0

    def __post_init__(self):
        _check(self.bits in (8, 16, 32, 64) and type(self.bits) is int)
        _check(isinstance(self.operations, tuple) and len(self.operations) <= 8)
        for pair in self.operations:
            _check(isinstance(pair, tuple) and len(pair) == 2)
            operation, value = pair
            _check(operation in ('add', 'sub', 'xor') and type(value) is int
                   and 0 <= value < 1 << self.bits)
        _check(self.interpretation in ('unsigned', 'float', 'bool'))
        _check(self.interpretation != 'float' or self.bits == 32)
        _check(type(self.false_value) is int and 0 <= self.false_value < 1 << self.bits)

    def transform(self, value):
        for operation, operand in self.operations:
            value = value ^ operand if operation == 'xor' else value + operand if operation == 'add' else value - operand
            value &= (1 << self.bits) - 1
        return value


@dataclass(frozen=True)
class Text:
    length: Word
    key: int
    operation: str = 'xor'

    def __post_init__(self):
        _check(isinstance(self.length, Word) and self.length.bits == 16
               and self.length.interpretation == 'unsigned')
        _check(type(self.key) is int and 0 <= self.key < 1 << 64 and self.operation in ('add', 'xor'))


@dataclass(frozen=True)
class Field:
    name: str
    value: object
    mask: int = 0
    raw_flag: bool = False
    present_when_set: bool = True
    default: object = None

    def __post_init__(self):
        _check(isinstance(self.name, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', self.name))
        _check(type(self.mask) is int and 0 <= self.mask < 1 << 64 and type(self.raw_flag) is bool)
        _check(type(self.present_when_set) is bool and (self.mask or self.present_when_set))
        if self.default is not None:
            if isinstance(self.value, Text):
                _check(isinstance(self.default, str))
            else:
                _check(isinstance(self.value, Word))
                if self.value.interpretation == 'unsigned':
                    _check(type(self.default) is int and 0 <= self.default < 1 << self.value.bits)
                elif self.value.interpretation == 'bool':
                    _check(type(self.default) is bool)
                else:
                    _check(type(self.default) in (int, float) and self.default == self.default
                           and abs(self.default) != float('inf'))


@dataclass(frozen=True)
class Record:
    fields: tuple
    flags: Word | None = None


@dataclass(frozen=True)
class Array:
    count: Word
    value: object


@dataclass(frozen=True)
class Dictionary:
    count: Word
    key: object
    value: object


def _contract(node, active=None, budget=None, depth=0):
    active = set() if active is None else active
    budget = [0] if budget is None else budget
    budget[0] += 1
    _check(depth <= MAX_DEPTH and budget[0] <= MAX_SCHEMA and id(node) not in active)
    active.add(id(node))
    if isinstance(node, Word):
        result = ['word', node.bits, node.operations, node.interpretation, node.false_value]
    elif isinstance(node, Text):
        result = ['text', _contract(node.length, active, budget, depth + 1), node.key, node.operation]
    elif isinstance(node, Record):
        _check(isinstance(node.fields, tuple) and 0 < len(node.fields) <= 256
               and (node.flags is None or isinstance(node.flags, Word)
                    and node.flags.interpretation == 'unsigned'))
        names = set()
        fields = []
        for field in node.fields:
            _check(isinstance(field, Field) and field.name not in names
                   and (node.flags is not None or not field.mask)
                   and (node.flags is None or field.mask < 1 << node.flags.bits))
            names.add(field.name)
            fields.append([field.name, field.mask, field.raw_flag, field.present_when_set, field.default,
                           _contract(field.value, active, budget, depth + 1)])
        result = ['record', _contract(node.flags, active, budget, depth + 1) if node.flags else None, fields]
    elif isinstance(node, (Array, Dictionary)):
        _check(isinstance(node.count, Word) and node.count.interpretation == 'unsigned')
        result = ['dictionary' if isinstance(node, Dictionary) else 'array',
                  _contract(node.count, active, budget, depth + 1)]
        if isinstance(node, Dictionary):
            _check(isinstance(node.key, (Word, Text))
                   and (not isinstance(node.key, Word) or node.key.interpretation == 'unsigned'))
            result.append(_contract(node.key, active, budget, depth + 1))
        result.append(_contract(node.value, active, budget, depth + 1))
    else:
        raise ValueError('Unsupported original dialogue native contract')
    active.remove(id(node))
    return result


class _Reader:
    def __init__(self, payload):
        self.payload, self.at, self.values = payload, 0, 0

    def take(self, count):
        _check(type(count) is int and 0 <= count <= len(self.payload) - self.at)
        result = self.payload[self.at:self.at + count]
        self.at += count
        return result

    def word(self, node):
        raw = int.from_bytes(self.take(node.bits // 8), 'little')
        return raw, node.transform(raw)

    def read(self, node, depth=0):
        self.values += 1
        _check(self.values <= MAX_VALUES and depth <= MAX_DEPTH)
        if isinstance(node, Word):
            _, value = self.word(node)
            if node.interpretation == 'float':
                value = struct.unpack('<f', struct.pack('<I', value))[0]
                _check(value == value and abs(value) != float('inf'))
            elif node.interpretation == 'bool':
                value = value != node.false_value
            return value
        if isinstance(node, Text):
            _, count = self.word(node.length)
            raw = self.take(count)
            result = bytearray()
            for start in range(0, count, 8):
                chunk = raw[start:start + 8]
                value = int.from_bytes(chunk, 'little')
                value = value ^ node.key if node.operation == 'xor' else (value + node.key) & ((1 << 64) - 1)
                result.extend(value.to_bytes(8, 'little')[:len(chunk)])
            return result.decode('utf-8', errors='strict')
        if isinstance(node, Record):
            raw, flag = self.word(node.flags) if node.flags else (0, 0)
            result = {}
            for field in node.fields:
                present = not field.mask or bool((raw if field.raw_flag else flag) & field.mask) == field.present_when_set
                if present:
                    result[field.name] = self.read(field.value, depth + 1)
                elif field.default is not None:
                    result[field.name] = field.default
            return result
        _, count = self.word(node.count)
        _check(count <= min(MAX_COUNT, MAX_VALUES - self.values, len(self.payload) - self.at))
        if isinstance(node, Array):
            return [self.read(node.value, depth + 1) for _ in range(count)]
        result = {}
        for _ in range(count):
            key = self.read(node.key, depth + 1)
            _check(key not in result)
            result[key] = self.read(node.value, depth + 1)
        return result


def decode_original(payload, contract):
    """Strict UTF-8, finite scalars, bounded allocation, exact original EOF."""
    _check(isinstance(payload, bytes) and 0 < len(payload) <= MAX_OBJECT)
    _contract(contract)
    reader = _Reader(payload)
    value = reader.read(contract)
    _check(reader.at == len(payload))
    return value


@dataclass(frozen=True)
class OriginalObject:
    path: str
    payload: bytes
    sha256: str

    def __post_init__(self):
        _check(_path(self.path) and isinstance(self.payload, bytes) and 0 < len(self.payload) <= MAX_OBJECT
               and _digest(self.sha256) and hashlib.sha256(self.payload).hexdigest() == self.sha256)


@dataclass(frozen=True)
class OriginalAsset:
    """An exact native UInt64 reference resolved in a verified original catalog.

    Catalog lookup must preserve the full identity and bundle ownership. An
    object name shortened for a bundle container is not sufficient evidence.
    The caller verifies the catalog and its containing publisher packages.
    """
    asset_index: int
    payload: bytes
    sha256: str
    catalog_sha256: str
    publisher_stamp: str

    def __post_init__(self):
        _check(type(self.asset_index) is int and 0 < self.asset_index < 1 << 64
               and isinstance(self.payload, bytes) and 0 < len(self.payload) <= MAX_OBJECT
               and _digest(self.sha256) and hashlib.sha256(self.payload).hexdigest() == self.sha256
               and _digest(self.catalog_sha256) and isinstance(self.publisher_stamp, str)
               and re.fullmatch('sophon-[0-9a-f]{64}', self.publisher_stamp))


def _path(value):
    return (isinstance(value, str) and 0 < len(value) <= 512 and value.startswith('Data/')
            and '\\' not in value and ':' not in value and '..' not in value.split('/')
            and str(PurePosixPath(value)) == value and not value.endswith('/'))


@dataclass(frozen=True)
class InventoryRoute:
    """A native loader's resource prefix and exact typed filename identity.

    This describes a proven native string construction, not a dialogue-number
    heuristic. A missing route never falls back to a guessed prefix or ordinal.
    """
    kind: int
    prefix: str
    identity_field: str = 'id'
    representation: str = 'talk'
    group_contract: object = None

    def __post_init__(self):
        _check(type(self.kind) is int and 0 <= self.kind <= 0xffffffff
               and isinstance(self.prefix, str) and self.prefix.endswith('/')
               and _path(self.prefix.rstrip('/'))
               and isinstance(self.identity_field, str)
               and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', self.identity_field))
        _check(self.representation in ('talk', 'descriptor', 'group')
               and (self.group_contract is not None) == (self.representation == 'group'))
        if self.group_contract is not None:
            _contract(self.group_contract)


@dataclass(frozen=True)
class NativeDialogueProfile:
    """Canonical field aliases derived from the exact owned original readers.

    Inventory yields authored ``id, resource`` pairs, or ``id, resourceKind``
    and the exact typed ID selected by an InventoryRoute. Talk yields the
    existing ``id, dialogList`` schema. Lut maps VoiceID to ``argument, trigger,
    file_group``; Items maps UUID to ``uuid, trigger, argument, sourceNames``.
    The two prefixes and enum values must come from the same original owner.
    """
    inventory: object
    talk: object
    lut: object
    items: object
    lut_path: str
    items_prefix: str
    trigger_names: tuple
    method_sha256: tuple
    executable_sha256: str
    metadata_sha256: str
    inventory_routes: tuple = ()
    descriptor: object = None
    descriptor_payload_kinds: tuple = ()

    def fingerprint(self):
        _check(_path(self.lut_path) and _path(self.items_prefix.rstrip('/'))
               and self.items_prefix.endswith('/'))
        _check(isinstance(self.method_sha256, tuple) and 4 <= len(self.method_sha256) <= 64
               and all(_digest(value) for value in self.method_sha256)
               and _digest(self.executable_sha256) and _digest(self.metadata_sha256))
        _check(isinstance(self.trigger_names, tuple) and 1 <= len(self.trigger_names) <= 64)
        enums, names = set(), set()
        for value, name in self.trigger_names:
            _check(type(value) is int and 0 <= value <= 0xffffffff and isinstance(name, str)
                   and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', name)
                   and value not in enums and name not in names)
            enums.add(value)
            names.add(name)
        _check(isinstance(self.inventory_routes, tuple) and len(self.inventory_routes) <= 64)
        routes = {}
        for route in self.inventory_routes:
            _check(isinstance(route, InventoryRoute) and route.kind not in routes)
            routes[route.kind] = [route.prefix, route.identity_field, route.representation,
                                  _contract(route.group_contract) if route.group_contract else None]
        uses_descriptors = any(route.representation != 'talk' for route in self.inventory_routes)
        _check((self.descriptor is not None) == uses_descriptors
               and isinstance(self.descriptor_payload_kinds, tuple)
               and len(self.descriptor_payload_kinds) <= 64
               and bool(self.descriptor_payload_kinds) == uses_descriptors
               and len(set(self.descriptor_payload_kinds)) == len(self.descriptor_payload_kinds)
               and all(type(value) is int and 0 <= value <= 0xffffffff
                       for value in self.descriptor_payload_kinds))
        contracts = [_contract(value) for value in (self.inventory, self.talk, self.lut, self.items)]
        if self.descriptor is not None:
            contracts.append(_contract(self.descriptor))
        raw = json.dumps([contracts, self.lut_path, self.items_prefix, self.trigger_names,
                          self.method_sha256, self.executable_sha256, self.metadata_sha256, routes,
                          self.descriptor_payload_kinds],
                         sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(raw).hexdigest()


def prepare_original_talk_snapshot(destination, inventory, load_object, profile, *,
                                   tables, textmap_sha256, source_locale,
                                   publisher_stamp, publisher_entries, current, load_asset=None):
    """Prepare every inventory Talk through the ordinary snapshot/voice path.

    ``load_object(path)`` returns an OriginalObject from verified publisher
    packages. No rows may come from a mirror or inferred filename ordinals.
    Descriptor routes additionally use ``load_asset(full_uint64_identity)``;
    this returns an OriginalAsset from the exact catalog/bundle, never a guessed
    pathname. Groups yield ``id, talks``; descriptors yield ``id, assetIndex,
    payloadKind``. Every inventory member must appear in its authored group.
    A failure, interrupted write or changed release retains the previous cache.
    Missing/ambiguous voice entries stay unknown or unavailable, never unvoiced.
    This explicit API has Talk coverage; it does not claim other presentations.
    """
    _check(isinstance(profile, NativeDialogueProfile) and isinstance(inventory, OriginalObject))
    fingerprint = profile.fingerprint()
    _check(profile.descriptor is None or callable(load_asset))
    _check(isinstance(publisher_stamp, str) and re.fullmatch('sophon-[0-9a-f]{64}', publisher_stamp)
           and callable(load_object) and callable(current))
    _check(isinstance(tables, dict) and source_locale in tables and isinstance(textmap_sha256, dict)
           and set(tables) == set(textmap_sha256) and all(_digest(value) for value in textmap_sha256.values()))
    parsed_textmaps = {}
    for locale, table in tables.items():
        _check(isinstance(locale, str) and isinstance(table, dict) and all(
            isinstance(key, str) and key.isdecimal() and isinstance(value, str) for key, value in table.items()))
        digest = hashlib.sha256()
        for part in json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(',', ':')).iterencode(table):
            digest.update(part.encode('utf-8'))
        parsed_textmaps[locale] = digest.hexdigest()
    _check(isinstance(publisher_entries, dict) and all(type(identity) is int and 0 < identity < 1 << 64
           and isinstance(entry, dict) and entry.get('publisher') == publisher_stamp
           and isinstance(entry.get('package'), str) for identity, entry in publisher_entries.items()))
    objects, total = {inventory.path: inventory.sha256}, len(inventory.payload)

    def read(path, contract):
        nonlocal total
        _check(_path(path) and path not in objects and len(objects) < MAX_OBJECTS)
        value = load_object(path)
        _check(isinstance(value, OriginalObject) and value.path == path)
        total += len(value.payload)
        _check(total <= MAX_TOTAL)
        objects[path] = value.sha256
        return decode_original(value.payload, contract)

    listing = decode_original(inventory.payload, profile.inventory)
    _check(isinstance(listing, list) and 0 < len(listing) < MAX_OBJECTS)
    talks, identities, resources, assets = [], set(), {}, {}
    routes = {route.kind: route for route in profile.inventory_routes}
    for row in listing:
        _check(isinstance(row, dict) and type(row.get('id')) is int and row['id'] > 0
               and row['id'] not in identities)
        identities.add(row['id'])

    def bind_descriptor(descriptor):
        nonlocal total
        _check(isinstance(descriptor, dict) and type(descriptor.get('id')) is int
               and descriptor['id'] in identities and type(descriptor.get('assetIndex')) is int
               and 0 < descriptor['assetIndex'] < 1 << 64
               and type(descriptor.get('payloadKind')) is int
               and descriptor['payloadKind'] in profile.descriptor_payload_kinds)
        identity = descriptor['assetIndex']
        if identity not in assets:
            _check(len(objects) < MAX_OBJECTS)
            source = load_asset(identity)
            _check(isinstance(source, OriginalAsset) and source.asset_index == identity
                   and source.publisher_stamp == publisher_stamp)
            total += len(source.payload)
            _check(total <= MAX_TOTAL)
            objects[f'asset:{identity:016x}'] = {'sha256': source.sha256,
                                               'catalog_sha256': source.catalog_sha256}
            talk = decode_original(source.payload, profile.talk)
            _check(isinstance(talk, dict) and isinstance(talk.get('dialogList'), list))
            assets[identity] = talk
            talks.append(talk)
        _check(assets[identity].get('id') == descriptor['id'])

    for row in listing:
        if 'resource' in row:
            path, identity, representation, contract = row['resource'], row['id'], 'talk', profile.talk
        else:
            kind = row.get('resourceKind')
            _check(type(kind) is int and kind in routes)
            route = routes[kind]
            identity = row.get(route.identity_field)
            _check(type(identity) is int and 0 < identity <= 0xffffffff)
            path = route.prefix + str(identity)
            representation = route.representation
            contract = (profile.talk if representation == 'talk' else profile.descriptor
                        if representation == 'descriptor' else route.group_contract)
        _check(_path(path))
        if path in resources:
            previous_identity, previous_representation, previous_contract, members = resources[path]
            _check((previous_identity, previous_representation, previous_contract)
                   == (identity, representation, _contract(contract))
                   and (representation == 'talk' or row['id'] in members))
            continue
        source = read(path, contract)
        _check(isinstance(source, dict) and source.get('id') == identity)
        if representation == 'talk':
            _check(isinstance(source.get('dialogList'), list))
            talks.append(source)
            members = {identity}
        else:
            descriptors = source.get('talks') if representation == 'group' else [source]
            _check(isinstance(descriptors, list) and 0 < len(descriptors) < MAX_OBJECTS)
            members = set()
            for descriptor in descriptors:
                _check(isinstance(descriptor, dict) and type(descriptor.get('id')) is int
                       and descriptor['id'] not in members)
                bind_descriptor(descriptor)
                members.add(descriptor['id'])
            _check(row['id'] in members)
        resources[path] = (identity, representation, _contract(contract), members)
    lut = read(profile.lut_path, profile.lut)
    _check(isinstance(lut, dict))
    groups, events = {}, defaultdict(list)
    triggers = dict(profile.trigger_names)
    for identity, row in lut.items():
        _check(type(identity) is int and 0 < identity <= 0xffffffff and isinstance(row, dict)
               and all(type(row.get(key)) is int and 0 <= row[key] <= 0xffffffff
                       for key in ('argument', 'trigger', 'file_group')) and row['trigger'] in triggers)
        group = row['file_group']
        if group not in groups:
            values = read(profile.items_prefix + str(group), profile.items)
            _check(isinstance(values, dict))
            index = defaultdict(list)
            for uuid, item in values.items():
                _check(isinstance(uuid, str) and re.fullmatch('[A-Za-z0-9-]{1,128}', uuid)
                       and isinstance(item, dict) and item.get('uuid') == uuid)
                index[wwise_short_id(uuid)].append(item)
            groups[group] = index
        candidates = groups[group].get(identity, [])
        valid = (len(candidates) == 1 and candidates[0].get('argument') == row['argument']
                 and candidates[0].get('trigger') == triggers[row['trigger']])
        events[(triggers[row['trigger']], row['argument'])].append(candidates[0] if valid else None)
    warnings, authored, annotations = [], set(), {}
    hashes = game.dialogue_hashes(talks, warnings=warnings, annotations=annotations)
    canonical = {}
    for (trigger, argument), candidates in events.items():
        if trigger != 'Dialog' or str(argument) not in hashes:
            continue
        authored.add((trigger, str(argument)))
        if len(candidates) != 1 or candidates[0] is None:
            game._warn(warnings, 'Some original Genshin voice identities are missing or ambiguous.')
            continue
        item = candidates[0]
        canonical[str(argument)] = {'gameTrigger': trigger, 'gameTriggerArgs': argument,
                                   'sourceNames': item.get('sourceNames', [])}
    links = game.dialogue_links([canonical], hashes, source_locale, warnings=warnings, authored=authored)
    links = game._complete_links(links, {'Dialog': hashes}, authored, [])
    for link in links:
        link.update(annotations.get(link['id'].split(':')[0], {}))
        link.setdefault('dialogue_kind', 'conversation')
    templates = {}
    rows = game._render_player_text(common.records('genshin', links, tables, source_locale, publisher_entries),
                                   source_locale, authored_templates=templates)
    _check(rows and len({row['text_id'] for row in rows}) == len(rows))
    for row in rows:
        # These captions came from the complete authored Talk/text-hash join,
        # including choices without a proven recording. Keep that positive text
        # evidence after common.records/rendering; unresolved source templates
        # still veto missing-audio capture. Unreferenced TextMap/UI rows never
        # enter this preparation path.
        row['text_capture_verified'] = not bool(row.get('text_binding_unresolved'))
    game._exclude_conflicting_performances(rows, warnings, authored_templates=templates)
    game._bind_predecessors(rows, annotations)
    if len(rows) < len(links):
        game._warn(warnings, 'Some original Genshin Talk lines lack text in the selected language.')
    game._warn(warnings, 'Original Talk preparation does not establish coverage of other dialogue presentations.')
    provenance = {'profile': fingerprint, 'objects': objects, 'textmap_sources': textmap_sha256,
                  'parsed_textmaps': parsed_textmaps}
    revision = 'original-' + hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    snapshot = {'format': 2, 'game': 'genshin', 'source_locale': source_locale, 'install': None,
                'fingerprint': publisher_stamp, 'metadata_revision': revision, 'records': rows,
                'missing_translation_locales': sorted(set(tables) - {code for row in rows for code in row['texts']}),
                'coverage_warnings': warnings,
                'original_dialogue': {'profile_sha256': fingerprint, 'inventory_rows': len(listing),
                                      'talk_objects': len(talks), 'voice_groups': len(groups),
                                      'object_count': len(objects), 'input_bytes': total},
                'message': f'{len(rows):,} original {source_locale} Talk lines'}
    _check(current(publisher_stamp) is True)
    _atomic_file(destination, json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    return snapshot
