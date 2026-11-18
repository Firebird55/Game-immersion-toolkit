"""Bounded auxiliary native descriptions for original voice-choice tables."""
from dataclasses import replace
import json
from pathlib import Path
import re

from . import starrail_metadata as metadata, starrail_native_tables as tables
from .starrail_native_index import NativeIndex
from .starrail_native_description import _writes
from .starrail_original_tables import _description
from .starrail_voice_choices import EXTRA_TABLES
from .game_tools import _atomic_file
from .runtime_bundle import discover_layout

SCHEMA = 'starrail-native-voice-choice-tables-v1'
MAX_CODE = 8192
MAX_RECEIPT = 128 * 1024
FIELDS = {'AllowedAudioLanguage': frozenset({'AudioLanguageKey', 'WwiseLanguageKey', 'AudioTrackIndex', 'ShowString'}),
          'AvatarCobrand': frozenset({'ID', 'AudioLanguage', 'StateGroupName', 'OffStateName', 'OnStateName'})}


def _logic():
    layout = discover_layout()
    return layout.source_commit if layout.mode == 'bundle' else metadata._identity({name: metadata._hash(Path(__file__).with_name(name))
        for name in ('starrail_native_voice_choices.py', 'starrail_native_tables.py', 'starrail_native_index.py',
                     'starrail_native_description.py', 'starrail_original_tables.py', 'starrail_voice_choices.py')})


def _owners(index):
    """Filter original metadata before reading any constructor instructions."""
    rows = {name: [] for name in EXTRA_TABLES}
    for owner, block in index.blocks.items():
        fields = set(re.findall(r'^    public .+ ([A-Za-z0-9_]+) // Offset:', block, re.M))
        if not re.search(r'^    public static void FromBinary\(', block, re.M):
            continue
        for name, required in FIELDS.items():
            if required <= fields:
                rows[name].append(owner)
    metadata._check(all(len(items) == 1 for items in rows.values()))
    wanted = {items[0]: name for name, items in rows.items()}
    candidates = {name: [] for name in EXTRA_TABLES}
    for owner, identity, block in index.all_blocks:
        row_types = set(re.findall(r'Dictionary<[^,>]+, ([A-Za-z0-9_.]+Row)>', block))
        if (len(row_types) != 1 or next(iter(row_types)) not in wanted
                or not re.search(r'^    private static void \.cctor\(\)', block, re.M)
                or not re.search(r'^    (?:private|public) static (?:readonly )?string\[\] ', block, re.M)):
            continue
        candidates[wanted[next(iter(row_types))]].append((owner, identity, block, next(iter(row_types))))
    metadata._check(all(len(items) == 1 for items in candidates.values()))
    blocks, permitted, loaders = [], {}, {}
    for name, items in candidates.items():
        owner, identity, block, row = items[0]
        blocks.append((owner, identity, block))
        addresses = [index.method(owner, r'private static void \.cctor\(\)'),
                     index.method(row, r'public static void FromBinary\([^\n]*\)')]
        strings = [int(value, 16) for value in re.findall(
            r'^    (?:public|private) static void [A-Za-z0-9_]+\(string\) \{\} // VA: 0x[0-9A-Fa-f]+, RVA: (0x[0-9A-Fa-f]+),', block, re.M)]
        metadata._check(len(strings) == 1)
        loaders[name] = strings[0]
        for address in addresses + strings:
            first, end = index.native_bounds(address)
            metadata._check(first == address and end > address and address not in permitted)
            permitted[address] = end
    regions = sorted(permitted.items())
    metadata._check(sum(end - start for start, end in regions) <= MAX_CODE
                    and all(first_end <= second for (_, first_end), (second, _) in zip(regions, regions[1:])))
    return blocks, permitted, loaders


def _loader(index, binding, address):
    """Require positive, unclobbered native prefix-flag evidence."""
    reader, = set(re.findall(r'public static void FromBinary\(([A-Za-z0-9_.]+),', binding['row_block']))
    instructions, _ = index.body(address)
    matches = []
    for position, (at, operation, operands) in enumerate(instructions):
        if operation != 'call' or re.fullmatch(r'0x[0-9a-f]+', operands) is None:
            continue
        target = int(operands, 16) - index.base
        signatures = [method for method in index.methods.get(target, []) if re.fullmatch(
            r'public static byte [A-Za-z0-9_]+\(string, System.Action<' + re.escape(reader) + r'>, bool, bool\)', method['signature'])]
        if not signatures:
            continue
        flags = [i for i in range(max(0, position - 6), position)
                 if instructions[i][1] == 'mov' and re.fullmatch(r'r8b, (?:0x1|1)', instructions[i][2])]
        metadata._check(len(signatures) == len(flags) == 1)
        flag = flags[0]
        metadata._check(all(not _writes(op, args, 'r8') and not op.split()[-1].startswith(('j', 'loop'))
                            and op.split()[-1] not in {'call', 'ret'} for _, op, args in instructions[flag + 1:position]))
        for source, op, args in instructions:
            if op.split()[-1].startswith(('j', 'loop')):
                metadata._check(re.fullmatch(r'0x[0-9a-f]+', args) is not None)
                destination = int(args, 16) - index.base
                metadata._check(not instructions[flag][0] < destination <= at)
        matches.append(target)
    metadata._check(len(matches) == 1)


def derive(index):
    blocks, permitted, loaders = _owners(index)
    # A private index is owned by this derivation. Every prefilter/disassembly
    # request is confined to the already measured unwind regions.
    index.all_blocks = blocks
    index.raw_extent = lambda address: permitted[address]
    index.extent = index.raw_extent
    index.bodies(list(permitted))
    bound = tables.bindings(index, EXTRA_TABLES)
    for name, address in loaders.items():
        _loader(index, bound[name], address)
    result = tables.descriptions(index, bound)
    metadata._check(set(result) == EXTRA_TABLES and all(row['hash_byte_prefix'] is True for row in result.values()))
    return result


def _validate(value, identity):
    metadata._check(isinstance(value, dict) and set(value) == {'schema', 'identity', 'tables'}
                    and value['schema'] == SCHEMA and value['identity'] == identity
                    and isinstance(value['tables'], dict) and set(value['tables']) == EXTRA_TABLES)
    for description in value['tables'].values():
        _description(description)
        metadata._check(description['hash_byte_prefix'] is True)
    return value


def augment(directory, generation):
    """Compose 21+2 descriptions while preserving the base descriptor cache."""
    directory = Path(directory).absolute()
    metadata._check(not EXTRA_TABLES & generation.tables.keys())
    decoder = generation.native.helper.identity
    metadata._check(isinstance(decoder, str) and re.fullmatch(r'[0-9a-f]{64}', decoder))
    identity = {'native': generation.native.receipt, 'base': generation.identity, 'decoder': decoder, 'logic': _logic()}
    path = directory / 'voice-choice-native-descriptions.json'
    metadata._no_links(path)
    value = None
    try:
        metadata._check(0 < path.stat().st_size <= MAX_RECEIPT)
        value = _validate(json.loads(path.read_bytes()), identity)
    except (OSError, ValueError, KeyError, TypeError):
        value = None
    if value is None:
        value = _validate({'schema': SCHEMA, 'identity': identity,
                           'tables': derive(NativeIndex(generation.native))}, identity)
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        metadata._check(len(encoded) <= MAX_RECEIPT)
        _atomic_file(path, encoded)
    return replace(generation, tables=generation.tables | value['tables'],
                   identity=metadata._identity({'base': generation.identity, 'voice_choice_tables': value}))
