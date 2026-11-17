"""Original-input native bootstrap connected to the explicit preparation API.

This route derives all current Talk/Lut/Items read operands and semantic aliases
from the supplied original native inputs. Source-group/index routing remains an
explicit caller-owned contract until that separate bootstrap is supported. It
does not select the default provider, authenticate downloads, or execute client
code. Only the pinned instruction decoder executes native software.
"""
from dataclasses import replace
import hashlib
import re

from . import genshin_original_dialogue as o
from .genshin_native_x64 import Image, _check
from .genshin_native_registration import Bindings
from .genshin_native_view import View
from .genshin_native_usage import table_reader, dispatcher, usage_profile, Usages, slot_arrays
from .genshin_native_literals import literal_profile, Literals, path_callers
from .genshin_native_contracts import Contracts, alias
from .genshin_native_talk import root_owner, exact_reader, dialogue_roles
from .genshin_native_sources import index_reader, index_caches, cache_getters, indexed_roots
from .genshin_native_voice import (
    source_manager, path_hashes, lut_wrapper, dictionary_decoder,
    dictionary_value, lut_event_roles, lut_group_cache, items_prefix_field,
    group_filename, items_callback, items_event_roles, items_source_roles,
    item_uuid_role,
)
from .voice_assets import wwise_short_id


def canonical_contracts(contracts, aliases):
    """Apply native-owned physical field roles without positional row fitting."""
    _check(isinstance(aliases, dict))
    fields, known = {}, set()
    for (definition, _rva), record in contracts.records.items():
        mapping = {}
        for field in contracts.view.field_offsets(definition):
            key = definition, field['authored_offset_word']
            known.add(key)
            original = alias(field['name'])
            canonical = aliases.get(key, original)
            _check(isinstance(canonical, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', canonical))
            _check(original not in mapping)
            mapping[original] = canonical
        names = [mapping[f.name] for f in record.fields]
        _check(len(names) == len(set(names)), 'Native semantic aliases collide.')
        if id(record) in fields:
            _check(fields[id(record)] == mapping, 'A shared original record has conflicting native roles.')
        fields[id(record)] = mapping
    _check(set(aliases) <= known, 'A native semantic role has no owned original field.')
    completed = {}

    def rename(node):
        identity = id(node)
        if identity in completed:
            return completed[identity]
        if isinstance(node, o.Record):
            _check(id(node) in fields)
            node = replace(node, fields=tuple(replace(f, name=fields[id(node)][f.name], value=rename(f.value))
                                             for f in node.fields))
        elif isinstance(node, (o.Array, o.Dictionary)):
            node = replace(node, value=rename(node.value))
        elif isinstance(node, o.Tagged):
            node = replace(node, cases=tuple((tag, rename(value)) for tag, value in node.cases))
        completed[identity] = node
        return node

    return rename


def trigger_names(lut, items_by_group):
    """Prove enum/string correspondence through exact original UUID bindings.

    Missing/colliding UUIDs cannot vote. They remain unknown at the preparation
    join. A new enum with no positive exact binding fails closed. No enum values
    or current trigger table are built into this software.
    """
    _check(isinstance(lut, dict) and isinstance(items_by_group, dict) and lut)
    index = {}
    for group, items in items_by_group.items():
        _check(type(group) is int and 0 <= group <= 0xffffffff and isinstance(items, dict))
        values = {}
        for uuid, item in items.items():
            _check(isinstance(uuid, str) and re.fullmatch('[A-Za-z0-9-]{1,128}', uuid)
                   and isinstance(item, dict) and item.get('uuid') == uuid)
            values.setdefault(wwise_short_id(uuid), []).append(item)
        index[group] = values
    names, required = {}, set()
    for identity, row in lut.items():
        _check(type(identity) is int and 0 < identity <= 0xffffffff and isinstance(row, dict)
               and all(type(row.get(key)) is int and 0 <= row[key] <= 0xffffffff
                       for key in ('argument', 'trigger', 'file_group')))
        trigger = row['trigger']; required.add(trigger)
        _check(row['file_group'] in index, 'An original Lut group is missing.')
        candidates = index[row['file_group']].get(identity, [])
        if len(candidates) != 1 or candidates[0].get('argument') != row['argument']:
            continue
        name = candidates[0].get('trigger')
        _check(isinstance(name, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', name))
        _check(trigger not in names or names[trigger] == name,
               'Exact original UUID bindings disagree on a trigger enum.')
        names[trigger] = name
    _check(set(names) == required and len(names) <= 64 and len(set(names.values())) == len(names),
           'An original trigger enum has no unique positive UUID binding.')
    return tuple(sorted(names.items()))


class NativeDialogue:
    """One bounded current-source bootstrap; inputs must be publisher verified."""

    def __init__(self, executable, metadata):
        _check(isinstance(executable, bytes) and isinstance(metadata, bytes))
        self.executable_sha256 = hashlib.sha256(executable).hexdigest()
        self.metadata_sha256 = hashlib.sha256(metadata).hexdigest()
        self.view = View(Bindings(Image(executable), metadata))
        self.table = table_reader(self.view, 'MoleMole.Config', 'TalkExcelConfig')
        self.dispatch = dispatcher(self.view, self.table)
        self.usages = Usages(self.view, usage_profile(self.view, self.dispatch))
        self.arrays = slot_arrays(self.view, self.dispatch, self.usages)
        self.literals = Literals(self.view, self.usages, literal_profile(self.view, self.dispatch))
        self.paths = path_callers(self.view, self.literals, self.arrays, roles=(
            '_BinOutput/Voice/', '_BinOutput/Talk/', '_BinOutput/IndexDic/', 'Config_TextMap', 'TalkExcelConfigData'))
        self._derive()
        self.source_index = index_reader(self.view, self.paths, self.table['stream'])
        self.source_caches = index_caches(self.view, self.paths, self.source_index)
        getters = cache_getters(self.view, self.source_caches, self.resource_definition)
        self.indexed_roots = indexed_roots(self.view, getters, self.resource_definition, self.table['stream'],
                                          self.allocator, self.usages, self.arrays)

    def _derive(self):
        view, stream, usages, arrays = self.view, self.table['stream'], self.usages, self.arrays
        contracts = Contracts(view, stream, usages=usages, arrays=arrays)
        inventory = contracts.inventory(self.table)
        owner = root_owner(view, self.table, usages, arrays, self.paths)
        managers = view.methods_at(owner['loader_rva'])
        _check(len(managers) == 1)
        self.resource_definition, self.allocator = managers[0]['owner']['definition'], owner['allocator_rva']
        reader = exact_reader(view, self.table, self.dispatch, owner)
        roles = dialogue_roles(view, owner, stream, usages, arrays)
        talk = contracts.record(owner['type']['definition'], reader['reader']['rva'])
        root_fields = view.field_offsets(owner['type']['definition'])
        primitives, _setters = contracts.wrappers(root_fields)
        identity_fields = [f for f in root_fields if primitives.get(f['type'].get('definition')) == 9]
        _check(len(identity_fields) == 1, 'The original Talk root identity is ambiguous.')
        aliases = {
            (owner['type']['definition'], identity_fields[0]['authored_offset_word']): 'id',
            (owner['type']['definition'], roles['root_array_offset']): 'dialogList',
            (roles['node_definition'], roles['node_identity']['offset']): 'id',
            (roles['node_definition'], roles['text_key_offset']): 'talkContentTextMapHash',
            (roles['node_definition'], roles['next_dialogues_offset']): 'nextDialogs',
            (roles['node_definition'], roles['role_offset']): 'role',
        }
        role_fields = view.field_offsets(roles['role_definition'])
        for name, canonical in (('_id', 'roleId'), ('_type', 'roleType')):
            fields = [f for f in role_fields if f['name'] == name]
            _check(len(fields) == 1)
            aliases[roles['role_definition'], fields[0]['authored_offset_word']] = canonical
        manager = source_manager(view, self.paths)
        hashes = path_hashes(view, manager, self.paths)
        wrapper = lut_wrapper(view, manager, hashes, usages, arrays, stream)
        decoder = dictionary_decoder(view, wrapper['wrapper'])
        value = dictionary_value(view, decoder, stream, usages, arrays)
        events = lut_event_roles(view, manager, wrapper, value)
        group = lut_group_cache(view, manager, events)
        prefix = items_prefix_field(view, manager, self.paths)
        self.filename_owner = group_filename(view, manager, group, prefix)
        self.items_prefix = prefix['prefix']
        context = contracts.context(decoder); reads = context.reads(4)
        _check(len(reads) == 2)
        lut = o.Dictionary(o.Word(32, context.operations(reads[0].address - view.image.base, 32, 'length')),
                           o.Word(32, context.operations(reads[1].address - view.image.base, 32, 'count')),
                           contracts.record(value['type']['definition'], value['reader']['rva']))
        for offset, canonical in ((events['argument'], 'argument'), (events['trigger'], 'trigger'),
                                  (group['field_offset'], 'file_group')):
            aliases[value['type']['definition'], offset] = canonical
        callback = items_callback(view, manager, stream, usages, arrays)
        item = dictionary_value(view, callback['decoder_rva'], stream, usages, arrays)
        item_events = items_event_roles(view, manager, item)
        sources = items_source_roles(view, manager, item)
        uuid = item_uuid_role(view, item, sources, usages, arrays)
        context = contracts.context(callback['decoder_rva']); reads = context.reads()
        string_reads = [i for i in reads[1:] if any(op.size == 2 for op in i.operands if op.type == 3)]
        _check(string_reads)
        cipher, operation = context.cipher(set(context.by_address))
        items = o.Dictionary(o.Word(32, context.operations(reads[0].address - view.image.base, 32, 'length')),
                             o.Text(o.Word(16, context.operations(string_reads[0].address - view.image.base, 16, 'length')),
                                    cipher, operation),
                             contracts.record(item['type']['definition'], item['reader']['rva']))
        for offset, canonical in ((item_events['fields']['argument']['field_offset'], 'argument'),
                                  (item_events['fields']['trigger']['field_offset'], 'trigger'),
                                  (sources['source_array_offset'], 'sourceNames'), (uuid['uuid_offset'], 'uuid')):
            aliases[item['type']['definition'], offset] = canonical
        aliases[sources['source_definition'], sources['source_filename_offset']] = 'sourceFileName'
        rename = canonical_contracts(contracts, aliases)
        self.inventory, self.talk, self.lut, self.items = map(rename, (inventory, talk, lut, items))
        self.lut_path = 'Data/_BinOutput/Voice/Lut/Lut'
        _check(self.lut_path in hashes, 'The native Lut path is missing.')
        self.contexts = tuple(sorted(contracts.contexts))
        self.method_sha256 = tuple(hashlib.sha256(view.image.window(rva)).hexdigest() for rva in self.contexts)
        _check(4 <= len(self.method_sha256) <= 64)

    def profile(self, lut, items_by_group, *, inventory_routes=(), descriptor=None,
                descriptor_payload_kinds=(), source_indices=()):
        """Connect native readers to the existing explicit preparation contract.

        The separate routing inputs must have their own original native source
        ownership. Supplying them is not autonomous source discovery acceptance.
        """
        result = o.NativeDialogueProfile(
            self.inventory, self.talk, self.lut, self.items, self.lut_path, self.items_prefix,
            trigger_names(lut, items_by_group), self.method_sha256,
            self.executable_sha256, self.metadata_sha256, inventory_routes, descriptor,
            descriptor_payload_kinds, source_indices,
        )
        for source in source_indices:
            _check(isinstance(source, o.SourceIndex) and source.path in self.source_index['paths']
                   and source.contract == self.source_index['contract'],
                   'An explicit source index differs from its actual native path/reader ownership.')
        result.fingerprint()
        return result

    def prepare(self, destination, inventory, load_object, *, inventory_routes=(), descriptor=None,
                descriptor_payload_kinds=(), source_indices=(), **options):
        """Use the canonical bootstrap in the existing atomic preparation path.

        Each original object is acquired once. The same authenticated Lut/Items
        bytes establish trigger correspondence and feed the final snapshot;
        another release cannot be substituted between those reads. Source-group
        contracts are still explicitly supplied, rather than guessed here.
        """
        stamp, current = options.get('publisher_stamp'), options.get('current')
        _check(isinstance(stamp, str) and re.fullmatch('sophon-[0-9a-f]{64}', stamp)
               and callable(current) and callable(load_object) and current(stamp),
               'Original publisher inputs changed; the previous snapshot is retained.')
        objects, total = {}, 0

        def read(path):
            nonlocal total
            if path not in objects:
                _check(len(objects) < o.MAX_OBJECTS)
                value = load_object(path)
                _check(isinstance(value, o.OriginalObject) and value.path == path)
                total += len(value.payload)
                _check(total <= o.MAX_TOTAL)
                objects[path] = value
            return objects[path]

        lut = o.decode_original(read(self.lut_path).payload, self.lut)
        _check(isinstance(lut, dict) and lut)
        group_ids = set()
        for row in lut.values():
            _check(isinstance(row, dict) and type(row.get('file_group')) is int
                   and 0 <= row['file_group'] <= 0xffffffff)
            group_ids.add(row['file_group'])
        groups = {group: o.decode_original(read(self.items_prefix + str(group)).payload, self.items)
                  for group in sorted(group_ids)}
        profile = self.profile(lut, groups, inventory_routes=inventory_routes, descriptor=descriptor,
                               descriptor_payload_kinds=descriptor_payload_kinds, source_indices=source_indices)
        return o.prepare_original_talk_snapshot(destination, inventory, read, profile, **options)
