# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned structural candidates for Star Rail catalogue discovery."""

import re

from . import starrail_declaration_census as census
from . import starrail_portable_metadata as metadata


_SCHEMA = 'proxy-starrail-table-candidates-v1'
_MAX_ROOTS = 16
_MAX_METHODS = 512
_MAX_FIELDS = 64
_FIELD_NAME = re.compile(r'[A-Za-z0-9_]+')
_ROW_NAME = re.compile(r'[A-Za-z0-9_.]+Row')
_DICTIONARY_KEY = re.compile(r'[^,>]+')
_ACCESS = 0x07
_PRIVATE, _PUBLIC = 0x01, 0x06
_STATIC, _LITERAL, _INTERFACE = 0x10, 0x40, 0x20
_FINAL, _VIRTUAL, _NEW_SLOT, _ABSTRACT, _PINVOKE = 0x20, 0x40, 0x100, 0x400, 0x2000


def _constructor(method, types):
    flags = method['flags']
    if (method['name'] != '.cctor' or method['parameters'] or method['generic_container'] != -1
            or (flags & _ACCESS) != _PRIVATE or not flags & _STATIC or flags & (_ABSTRACT | _PINVOKE)):
        return False
    # Mirror the pinned formatter's final/virtual modifier precedence.
    if (flags & _FINAL and not flags & _NEW_SLOT) or (flags & _VIRTUAL and not flags & _FINAL):
        return False
    result = types.row(types.type_rva(method['return_type']))
    return result['tag'] == 0x01 and not (result['by_reference'] or result['pinned'])


def _dictionary_row(runtime, types):
    if runtime['tag'] != 0x15:
        return None
    _, class_index = runtime['target']
    definition, instance = types.generic_definition(class_index)
    stem = types.qualified_name(types.definition(definition)).split('`', 1)[0]
    if instance == -1 or not stem.endswith('Dictionary'):
        return None
    arguments = types.generic_arguments(instance)
    if len(arguments) != 2:
        return None
    key, value = arguments
    value_row = types.row(value)
    if value_row['tag'] not in metadata._TYPE_DEFINITION_TAGS or value_row['by_reference'] or value_row['pinned']:
        return None
    _, definition = value_row['target']
    declaration = types.definition(definition)
    name = types.qualified_name(declaration)
    if _ROW_NAME.fullmatch(name) and _DICTIONARY_KEY.fullmatch(types.named(key)[0]):
        return {'definition': definition, 'image': declaration['image_index'], 'name': name}
    return None


def _candidate(records, scope):
    owner = census._image_owner_path(records, scope)[0]
    if owner['field_count'] < 2 or owner['method_count'] == 0 or owner['flags'] & _INTERFACE:
        return None
    owner_index = scope.definitions[0]
    census._limit('table candidate methods per root', owner['method_count'], _MAX_METHODS)
    methods = census._owned_methods(records, owner_index, owner, None)
    _, stride = records.runtime_layout(records.cancelled)
    types = metadata._TypeProjection(records, stride, {}, {owner_index: owner}, records.cancelled)
    constructors = [index for index, method in methods.items() if _constructor(method, types)]
    if not constructors:
        return None

    census._limit('table candidate fields per root', owner['field_count'], _MAX_FIELDS)
    records.prove_field_extent()
    first = owner['field_start']
    arrays, rows = [], {}
    for index in range(first, first + owner['field_count']):
        metadata._check_cancelled(records.cancelled)
        field = records.field(index, owner_index, owner)
        field_type = types.type_rva(field['type'])
        runtime = types.row(field_type)
        attributes = runtime['attributes']
        if (not _FIELD_NAME.fullmatch(field['name']) or runtime['by_reference'] or runtime['pinned']
                or attributes & _LITERAL):
            continue
        if (attributes & _STATIC and (attributes & _ACCESS) in {_PRIVATE, _PUBLIC}
                and runtime['tag'] in {0x14, 0x1d} and types.named(field_type)[0] == 'string[]'):
            arrays.append({'field': index, 'name': field['name'], 'offset': field['offset']})
        row = _dictionary_row(runtime, types)
        if row is not None:
            rows[row['definition']] = row

    if not arrays or len({row['name'] for row in rows.values()}) != 1:
        return None
    if len(constructors) != 1 or len(rows) != 1 or len(arrays) != len({field['name'] for field in arrays}):
        raise census.CensusUnresolved('table candidate declaration ambiguity')
    if len(arrays) != len({field['offset'] for field in arrays}):
        raise census.CensusUnresolved('table candidate static field offsets')
    return {'definition': owner_index, 'image': scope.image_index, 'name': types.qualified_name(owner),
            'constructor': constructors[0], 'arrays': tuple(arrays), 'row': next(iter(rows.values()))}


def read_table_candidates(inputs, scopes, *, cancelled=None):
    """Check authenticated, explicitly selected image roots for catalogue shapes."""
    metadata._require(isinstance(scopes, (tuple, list)) and scopes, 'table candidate scopes')
    census._limit('table candidate image roots', len(scopes), _MAX_ROOTS)
    scopes = tuple(scopes)
    for scope in scopes:
        census._validate_image_scope(scope)
        metadata._require(len(scope.definitions) == 1, 'table candidate image root')
    metadata._require(len(set(scopes)) == len(scopes), 'table candidate scopes')
    with metadata.open_records(inputs, cancelled=cancelled) as (records, identity):
        candidates = []
        for scope in scopes:
            metadata._check_cancelled(cancelled)
            candidate = _candidate(records, scope)
            if candidate is not None:
                candidates.append(candidate)
        return {'schema': _SCHEMA, 'sha256': dict(identity), 'candidates': tuple(candidates)}
