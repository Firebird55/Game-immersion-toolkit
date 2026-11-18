"""Conservative direct speech edges from complete original NTE dialogue graphs.

No node is traversed or skipped. A repeated caption occurrence, choice label,
condition, event, media sequence or unlabeled order parameter prevents context.
StringTable namespaces are read from their original owners, never basenames.
"""
from collections import Counter
from pathlib import PurePosixPath
import re
import json

from .nte_native_schema import _check, _seed
from .nte_seeded_schema import _seed_shapes

MAX_GRAPHS = 8192
MAX_EXPORTS = 200_000
MAX_SOURCE_BYTES = 256*1024**2


def _numeric_guard(schema_usmap):
    """Withhold anonymous enum instances, including omitted scalar defaults."""
    body, names, _, _, start, count, _ = _seed(schema_usmap)
    definitions = _seed_shapes(body, names, start, count)
    defaults = {}
    def inline(shape, stack):
        if shape[0] == 26:
            return shape[2] is None
        if shape[0] == 9:
            return default_type(shape[1], stack)
        # A missing dynamic/optional container has no materialized elements.
        return False
    def default_type(name, stack=()):
        if name in defaults: return defaults[name]
        _check(name not in stack and len(stack) <= 64)
        row = definitions.get(name)
        result = bool(row and ((row[1] and default_type(row[1], (*stack, name)))
                      or any(inline(shape, (*stack, name)) for _, _, _, shape in row[3])))
        defaults[name] = result
        return result
    def wire(value, shape, depth):
        _check(depth <= 64)
        if value is None:
            return False
        kind = shape[0]
        if kind == 26:
            return shape[2] is None
        if kind == 9:
            return any(typed(item, shape[1], depth+1) for item in value) if isinstance(value, list) else typed(value, shape[1], depth+1)
        if kind in (8, 25):
            return isinstance(value, list) and any(wire(item, shape[1], depth+1) for item in value)
        if kind == 28:
            return wire(value, shape[1], depth+1)
        if kind == 24:
            if isinstance(value, list):
                return any(isinstance(item, dict) and (wire(item.get('Key'), shape[1], depth+1)
                           or wire(item.get('Value'), shape[2], depth+1)) for item in value)
            if isinstance(value, dict):
                return any(wire(key, shape[1], depth+1) or wire(item, shape[2], depth+1) for key, item in value.items())
        return False
    def typed(value, name, depth=0):
        _check(depth <= 64)
        if not isinstance(value, dict) or name not in definitions:
            return False
        if default_type(name):
            return True
        _, parent, _, fields = definitions[name]
        return (bool(parent) and typed(value, parent, depth+1)
                or any(field in value and wire(value[field], shape, depth+1) for _, field, _, shape in fields))
    return typed


def read_pairs(path, *, schema_usmap=None):
    _check(path.is_file() and 0 < path.stat().st_size <= MAX_SOURCE_BYTES)
    packet = json.loads(path.read_bytes())
    _check(isinstance(packet, dict) and set(packet) == {'schema', 'graph_count', 'graphs', 'namespaces'}
           and packet['schema'] == 'nte-original-dialogue-graphs-v1'
           and type(packet['graph_count']) is int and isinstance(packet['graphs'], list)
           and packet['graph_count'] == len(packet['graphs']))
    return direct_pairs(packet['graphs'], packet['namespaces'], schema_usmap=schema_usmap)


def _identity(reference, namespaces):
    if not isinstance(reference, dict) or not isinstance(reference.get('TableId'), str):
        return None
    namespace, key = namespaces.get(reference['TableId']), reference.get('Key')
    if not isinstance(namespace, str) or not isinstance(key, str) or not namespace or not key:
        return None
    if any(len(v) > 512 or ':' in v or any(c in v for c in '\r\n\0') for v in (namespace, key)):
        return None
    return f'nte:{namespace}:{key}'


def _unsafe(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'PlaybackOrder':
                # Integer preservation supplies no authored ordering semantics.
                return True
            if (('Condition' in key or 'Event' in key or key in {
                    'TextArguments', 'EnterRestriction', 'SequenceInfo', 'SequenceActorConfigs',
                    'CartoonInfo', 'UIConfig', 'HideUI', 'SkipDesc', 'SkipOptionIndex'}) and child):
                return True
            if _unsafe(child):
                return True
    elif isinstance(value, list):
        return any(_unsafe(child) for child in value)
    return False


def direct_pairs(graphs, namespaces, *, schema_usmap=None):
    """Return pairs with a unique predecessor and directly owned target entry.

    The input must be the complete registry-selected inventory from one fully
    validated helper invocation. Unsupported presentation fields are withheld;
    broken references or incomplete graph packets fail the whole preparation.
    """
    _check(isinstance(graphs, list) and 0 < len(graphs) <= MAX_GRAPHS and isinstance(namespaces, dict))
    numeric = _numeric_guard(schema_usmap) if schema_usmap is not None else lambda *_: False
    assets, occurrences, candidates, total, unresolved_keys = set(), Counter(), [], 0, set()
    for packet in graphs:
        _check(isinstance(packet, dict) and set(packet) == {'asset', 'exports'})
        asset, exports = packet['asset'], packet['exports']
        _check(isinstance(asset, str) and asset.startswith('HT/Content/') and asset.endswith('.uasset')
               and asset == str(PurePosixPath(asset)) and '..' not in PurePosixPath(asset).parts
               and '\\' not in asset and asset not in assets
               and isinstance(exports, list) and 0 < len(exports) <= 4096)
        assets.add(asset); total += len(exports)
        _check(total <= MAX_EXPORTS and all(isinstance(row, dict) for row in exports))
        roots = [(i, row) for i, row in enumerate(exports) if row.get('Type') == 'DlgDialogue']
        _check(len(roots) == 1)
        root_index, root = roots[0]
        package = '/Game/' + asset[len('HT/Content/'):-len('.uasset')]
        _check(root.get('Package') == package and isinstance(root.get('Properties'), dict))
        props = root['Properties']
        slots, starts = props.get('Nodes', []), props.get('StartNodes', [])
        _check(isinstance(slots, list) and isinstance(starts, list) and len(slots) <= 4096)

        def linked(reference, start=False):
            _check(isinstance(reference, dict) and isinstance(reference.get('ObjectPath'), str))
            match = re.fullmatch(re.escape(package) + r'\.([0-9]+)', reference['ObjectPath'])
            _check(match is not None and int(match[1]) < len(exports))
            item = exports[int(match[1])]
            _check(isinstance(item.get('Properties', {}), dict) and isinstance(item.get('Name'), str)
                   and isinstance(item.get('Type'), str) and item['Type'].startswith('DlgNode_')
                   and reference.get('ObjectName') == f"{item['Type']}'{root['Name']}:{item['Name']}'"
                   and item.get('Outer', {}).get('ObjectPath') == f'{package}.{root_index}')
            if start:
                _check(item['Type'] == 'DlgNode_Start')
            return item

        nodes = [linked(ref) for ref in slots]
        start_nodes = [linked(ref, True) for ref in starts]
        _check(len({ref['ObjectPath'] for ref in slots}) == len(slots))
        incoming = Counter()
        for item in [*nodes, *start_nodes]:
            children = item.get('Properties', {}).get('Children', [])
            _check(isinstance(children, list) and len(children) <= 4096)
            for edge in children:
                _check(isinstance(edge, dict) and type(edge.get('TargetIndex')) is int
                       and 0 <= edge['TargetIndex'] < len(nodes))
                incoming[edge['TargetIndex']] += 1
        identities = [_identity(item.get('Properties', {}).get('Text'), namespaces)
                      if item['Type'] == 'DlgNode_Speech' else None for item in nodes]
        # Also count every nested FText occurrence, including choice labels and
        # sequence entries. Reuse outside this direct node prevents eligibility.
        def count(value):
            if isinstance(value, dict):
                identity = _identity(value, namespaces)
                if identity: occurrences[identity] += 1
                elif isinstance(value.get('TableId'), str) and isinstance(value.get('Key'), str):
                    unresolved_keys.add(value['Key'])
                for child in value.values(): count(child)
            elif isinstance(value, list):
                for child in value: count(child)
        count(exports)
        # ParticipantsData caches *names* used throughout the graph (Set<Name>
        # Conditions/Events); it does not execute those entries at this node.
        if props.get('bCanLoop') or numeric(props, root['Type']) or _unsafe({k: v for k, v in props.items()
                                           if k not in {'Nodes', 'StartNodes', 'ParticipantsData'}}):
            continue
        for position, item in enumerate(nodes):
            source = identities[position]
            source_props = item.get('Properties', {})
            children = source_props.get('Children', [])
            if (source is None or len(children) != 1 or numeric(source_props, item['Type'])
                    or _unsafe({k: v for k, v in source_props.items() if k != 'Children'})):
                continue
            edge = children[0]
            target_position = edge['TargetIndex']
            target = identities[target_position]
            label = edge.get('Text', {})
            if (target is None or source == target or incoming[target_position] != 1
                    or edge.get('EdgeIndex') != -1 or edge.get('Conditions') or edge.get('TextArguments')
                    or edge.get('EdgeData') is not None or edge.get('bForceShow')
                    or label.get('Namespace') != 'DlgSystem' or label.get('Key') != 'edge_next'
                    or 'TableId' in label or numeric(nodes[target_position].get('Properties', {}), nodes[target_position]['Type'])
                    or _unsafe({k: v for k, v in nodes[target_position].get('Properties', {}).items()
                                                    if k != 'Children'})):
                continue
            candidates.append((source, target))
    # The predecessor uniquely owns this occurrence. Reuse of the canonical
    # target elsewhere does not change the existing text/voice binding. Future
    # target child choices do not gate entry into the current speech node.
    return tuple(sorted({pair for pair in candidates if all((name != pair[0] or occurrences[name] == 1)
        and name.rsplit(':', 1)[-1] not in unresolved_keys for name in pair)}))


def annotate(records, pairs, *, text_mode=False):
    """Attach an owned predecessor to voiced or intentionally omitted dialogue."""
    if type(text_mode) is not bool:
        raise ValueError('Invalid NTE text-only graph selection')
    by_root = {}
    for row in records:
        identity = row['text_id']
        gender = row.get('player_voice')
        if gender: identity = identity.removesuffix(':' + gender)
        by_root.setdefault(identity, []).append(row)
    for source, target in pairs:
        sources, targets = by_root.get(source, []), by_root.get(target, [])
        if not sources or not targets:
            continue
        def eligible(row):
            binding = (row.get('voice_status') == 'voiced' and row.get('audio') or
                       text_mode and row.get('audio_omitted_by_request') is True and row.get('text_capture_verified') is True)
            return (binding
                    and row.get('dialogue_kind') == 'conversation' and not row.get('text_binding_unresolved'))
        if not all(eligible(row) for row in [*sources, *targets]):
            continue
        for row in targets:
            previous = [item for item in sources if not item.get('player_voice') or not row.get('player_voice')
                        or item['player_voice'] == row['player_voice']]
            if len(previous) == 1:
                row['previous_text_id'] = previous[0]['text_id']
    return records
