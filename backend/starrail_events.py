"""Join exact Star Rail archive events, Wwise Play actions and localized media."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import re
import struct
from urllib.parse import quote

from . import sophon_assets as sophon, starrail_hotfix as hotfix
from .hoyo_dialogue import audio_locale, voice_namespace
from .nte_assets import wwise_hash

LOOKUP = 'StarRail_Data/StreamingAssets/RawRes/Windows/RawConfig/SoundBankLookUp.dat'
check = hotfix.check


def _u32(data, pos):
    check(0 <= pos <= len(data) - 4)
    return struct.unpack_from('<I', data, pos)[0]


def _ids(raw, reference):
    if not reference:
        return ()
    count = _u32(raw, reference)
    check(count <= 1024 and reference + 4 + count * 4 <= len(raw))
    return struct.unpack_from(f'<{count}I', raw, reference + 4)


def _state_banks(raw, reference):
    groups = _ids(raw, reference)
    if len(groups) != 1:
        return None
    group = groups[0]
    if _u32(raw, group + 4) != 1:
        return None
    table = _u32(raw, group + 8)
    count = _u32(raw, table)
    check(count <= 1024 and table + 4 + 8 * count <= len(raw))
    states = {}
    for value, pointer in struct.iter_unpack('<II', raw[table+4:table+4+8*count]):
        check(value not in states and _u32(raw, pointer) == value)
        if _u32(raw, pointer + 8):
            return None
        states[value] = _ids(raw, _u32(raw, pointer + 4))
    return _u32(raw, group), states


def bank_lookup(raw, *, with_states=False):
    check(len(raw) >= 36 and raw[:4] == b'DBDC' and _u32(raw, 4) == 1
          and _u32(raw, 8) == len(raw) and _u32(raw, 16) == 24 and _u32(raw, 24) == 28)
    count, slots = struct.unpack_from('<II', raw, 28)
    records = 36 + slots * 16
    check(0 < count <= 250000 and 0 < slots <= 1024**2 and records + 8 * count <= len(raw))
    found, states = {}, {}
    for event, offset in struct.iter_unpack('<II', raw[records:records+8*count]):
        check(offset + 12 <= len(raw) and event not in found and _u32(raw, offset) == event)
        found[event] = _ids(raw, _u32(raw, offset + 4))
        if with_states and (pointer := _u32(raw, offset + 8)):
            states[event] = pointer
    return (found, states, raw) if with_states else found


@dataclass(frozen=True)
class Entry:
    asset: hotfix.AudioFile
    offset: int
    size: int


def _pck(directory, asset, language):
    header = asset.read(directory, 0, 28)
    total, version, langs, banks, sounds, external = struct.unpack_from('<6I', header, 4)
    check(header[:4] == b'AKPK' and version == 1 and 20 + langs + banks + sounds + external == total
          and 28 < total + 8 <= min(asset.size, 16 * 1024**2))
    raw = asset.read(directory, 0, total + 8)
    table = raw[28:28+langs]
    count = _u32(table, 0)
    check(count <= 128 and 4 + count * 8 <= langs)
    languages = {}
    for pos, identity in struct.iter_unpack('<II', table[4:4+8*count]):
        check(4+8*count <= pos < len(table) and pos % 2 == 0 and identity not in languages)
        languages[identity] = table[pos:].decode('utf-16-le').split('\0', 1)[0].lower()
    def section(pos, length):
        count = _u32(raw, pos)
        check(length == 4 + 20 * count and pos + length <= len(raw))
        items = {}
        for ident, block, size, sector, lang in struct.iter_unpack('<5I', raw[pos+4:pos+length]):
            check(lang in languages)
            if languages[lang] != language.lower():
                continue
            start = (block or 1) * sector
            check(ident not in items and size > 0 and total + 8 <= start <= asset.size - size)
            items[ident] = Entry(asset, start, size)
        return items
    return section(28 + langs, banks), section(28 + langs + banks, sounds)


def _bank(raw, identity, language):
    check(len(raw) >= 20 and raw[:4] == b'BKHD'
          and struct.unpack_from('<3I', raw, 8) == (135, identity, wwise_hash(language)))
    objects, media, sections = {}, {}, {}
    pos = 0
    while pos < len(raw):
        check(pos + 8 <= len(raw))
        tag, length = struct.unpack_from('<4sI', raw, pos)
        begin, end = pos + 8, pos + 8 + length
        check(end <= len(raw) and tag not in sections)
        sections[tag] = (begin, length)
        if tag == b'HIRC':
            count = _u32(raw, begin)
            cursor = begin + 4
            for _ in range(count):
                check(cursor + 9 <= end)
                kind, size = struct.unpack_from('<BI', raw, cursor)
                check(4 <= size <= end - cursor - 5)
                obj = raw[cursor+5:cursor+5+size]
                oid = _u32(obj, 0)
                check(oid not in objects)
                objects[oid] = (kind, obj)
                cursor += 5 + size
            check(cursor == end)
        pos = end
    if b'DIDX' in sections:
        start, size = sections[b'DIDX']
        data_start, data_size = sections.get(b'DATA', (0, 0))
        check(size % 12 == 0)
        for mid, offset, length in struct.iter_unpack('<III', raw[start:start+size]):
            check(mid not in media and length > 0 and offset + length <= data_size)
            media[mid] = (data_start + offset, length)
    return objects, media


def _target(objects, event):
    kind, obj = objects.get(event, (0, b''))
    if kind != 4 or len(obj) != 9 or obj[4] != 1:
        return None
    kind, action = objects.get(_u32(obj, 5), (0, b''))
    if kind == 3 and len(action) == 18 and action[4:6] == b'\x03\x04' and action[10:14] == b'\0\0\0\x04':
        return _u32(action, 14), _u32(action, 6)
    return None


def _sound(objects, target, parent=None, depth=0):
    kind, sound = objects.get(target, (0, b''))
    if depth > 12 or kind not in (2, 5):
        return None
    if parent is not None:
        pos = 25 if kind == 2 else 11
        if len(sound) < pos + 4 or _u32(sound, pos) != parent:
            return None
    if kind == 5:
        if len(sound) < 76:
            return None
        pos = 58 + sound[16] * 5
        if (len(sound) != pos + 18 or _u32(sound, pos) != 1 or sound[pos+8:pos+10] != b'\x01\0'
                or _u32(sound, pos + 4) != _u32(sound, pos + 10) or not _u32(sound, pos + 14)):
            return None
        return _sound(objects, _u32(sound, pos + 4), target, depth + 1)
    if len(sound) < 18 or _u32(sound, 4) != 0x40001 or not sound[17] & 1:
        return None
    return sound


def _media(objects, embedded, bank, target, streams, parent=None):
    sound = _sound(objects, target, parent)
    if not sound:
        return None
    mid, method = _u32(sound, 9), sound[8]
    if method == 0 and mid in embedded:
        pos, length = embedded[mid]
        return mid, Entry(bank.asset, bank.offset + pos, length)
    if method in (1, 2) and mid in streams:
        return mid, streams[mid]
    return None


def _switch(obj):
    if len(obj) < 48:
        return None
    pos = 34 + obj[16] * 5
    if pos + 14 > len(obj) or obj[pos] != 1 or obj[pos+9]:
        return None
    group, default = struct.unpack_from('<II', obj, pos + 1)
    children = _ids(obj, pos + 10)
    pos += 14 + len(children) * 4
    count = _u32(obj, pos)
    if not 1 <= count <= 1024 or len(children) != len(set(children)):
        return None
    pos += 4
    branches = {}
    for _ in range(count):
        value = _u32(obj, pos)
        nodes = _ids(obj, pos + 4)
        if value in branches or any(node not in children for node in nodes):
            return None
        branches[value] = nodes
        pos += 8 + 4 * len(nodes)
    count = _u32(obj, pos)
    pos += 4
    if (default not in branches or count != len(children) or pos + 14 * count != len(obj)
            or {_u32(obj, pos + 14 * n) for n in range(count)} != set(children)):
        return None
    return group, default, branches


def _selected_branches(name, default, branches, locale):
    player = {wwise_hash('state_' + gender): gender for gender in ('male', 'female')}
    none = wwise_hash('none')
    if player.keys() <= branches.keys() <= player.keys() | {none}:
        return player
    for token in re.findall('[a-z]+', name.lower()):
        native, japanese = (wwise_hash(token + suffix) for suffix in ('_default', '_japanese'))
        if default == native and set(branches) == {native, japanese, none} and branches[none] == branches[native]:
            return {japanese if locale == 'ja' else native: 'localized'}
    return {}


def _assets(directory, build, locale):
    language = voice_namespace('starrail', locale)
    roots = hotfix.roots(build)
    for row in map(json.loads, hotfix.index(directory, build, 'audio').splitlines()):
        name = row['Path']
        localized = re.fullmatch(re.escape(language) + r'/VoBanks[0-9]+\.pck', name)
        if not localized and not re.fullmatch(r'Banks[0-9]+\.pck', name):
            continue
        digest, size, patch = row['Md5'], row['Size'], row['Patch']
        check(re.fullmatch('[a-f0-9]{32}', digest) and type(size) is int and size > 28 and type(patch) is bool)
        source = roots['asb' if patch else 'base'] + 'AudioBlock/' + quote(name, safe='/()')
        yield hotfix.AudioFile(name, size, digest, source), language if localized else 'sfx'


def _unique(target, items):
    for key, val in items.items():
        target[key] = val if key not in target else None


def _bundle(directory, chosen, language):
    # Group neighbouring selected banks. A single download can contain many
    # small actor banks, while unrelated hundreds of megabytes stay online.
    groups = []
    for ident, entry in sorted(chosen.items(), key=lambda pair: (pair[1].asset.name, pair[1].offset)):
        end = entry.offset + entry.size
        check(0 < entry.size <= 32 * 1024**2)
        if (not groups or groups[-1][0].asset != entry.asset or entry.offset - groups[-1][1] > 64 * 1024
                or end - groups[-1][0].offset > 8 * 1024**2):
            groups.append([entry, end, []])
        groups[-1][1] = max(groups[-1][1], end)
        groups[-1][2].append((ident, entry))
    def read(group):
        first, end, entries = group
        raw = first.asset.read(directory, first.offset, end - first.offset)
        result = []
        for ident, entry in entries:
            start = entry.offset - first.offset
            result.append((ident, _bank(raw[start:start+entry.size], ident, language)))
        return result
    with ThreadPoolExecutor(max_workers=6) as pool:
        return {key: value for group in pool.map(read, groups) for key, value in group}


@lru_cache(maxsize=8)
def _release(directory, stamp):
    check(re.fullmatch('sophon-[0-9a-f]{64}', stamp))
    raw = (directory / 'releases' / stamp).read_bytes()
    check(len(raw) <= 64 * 1024 and 'sophon-' + hashlib.sha256(raw).hexdigest() == stamp)
    build = json.loads(raw)
    check(build['channel'] in ('starrail-global', 'starrail-cn'))
    return build


@lru_cache(maxsize=8)
def _lookup(directory, stamp):
    build = _release(directory, stamp)
    index = sophon.manifest(directory, build['channel'], tuple(build['manifests']['game']), (LOOKUP,))[LOOKUP]
    check(0 < index.size <= 32 * 1024**2)
    return bank_lookup(index.read(directory, 0, index.size), with_states=True)


@lru_cache(maxsize=5)
def _tables(directory, stamp, locale):
    language = voice_namespace('starrail', locale)
    assets = list(_assets(directory, _release(directory, stamp), locale))
    neutral, localized, streams = {}, {}, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        tables = pool.map(lambda pair: _pck(directory, *pair), assets)
        for (_, lang), (banks, sounds) in zip(assets, tables):
            _unique(neutral if lang == 'sfx' else localized, banks)
            if lang == language:
                _unique(streams, sounds)
    return neutral, localized, streams


@lru_cache(maxsize=8)
def _inventory(directory, stamp, locale, requested):
    language = voice_namespace('starrail', locale)
    lookup, state_refs, raw = _lookup(directory, stamp)
    neutral, localized, streams = _tables(directory, stamp, locale)
    by_event = {}
    for event, _ in requested:
        candidates = lookup.get(event, ())
        neutral_ids = [bid for bid in candidates if neutral.get(bid)]
        if len(neutral_ids) == 1:
            by_event[event] = neutral_ids[0]
    loaded = _bundle(directory, {bid: neutral[bid] for bid in set(by_event.values())}, 'sfx')
    targets = {}
    for event, bid in by_event.items():
        target = _target(loaded[bid][0], event)
        if target and target[0] in lookup[event] and localized.get(target[0]):
            targets[event] = target
    loaded = _bundle(directory, {bid: localized[bid] for bid, _ in targets.values()}, language)
    result, switches, dependencies = {}, [], set()
    names = dict(requested)
    for event, (bid, target) in targets.items():
        obj = loaded[bid][0].get(target)
        if obj and obj[0] == 6 and event in state_refs:
            switch = _switch(obj[1])
            state = _state_banks(raw, state_refs[event])
            if not switch or not state or switch[0] != state[0]:
                continue
            if {key for key, nodes in switch[2].items() if nodes} != {key for key, banks in state[1].items() if banks}:
                continue
            for value, variant in _selected_branches(names[event], switch[1], switch[2], locale).items():
                nodes, banks = switch[2][value], state[1].get(value, ())
                if len(nodes) == len(banks) == 1 and localized.get(banks[0]):
                    switches.append((event, variant, bid, target, nodes[0], banks[0]))
                    dependencies.add(banks[0])
            continue
        found = _media(*loaded[bid], localized[bid], target, streams)
        if found and found[1] is not None:
            result[event] = {None: found}
    extra = _bundle(directory, {bid: localized[bid] for bid in dependencies}, language)
    for event, variant, bid, parent, child, dependency in switches:
        found = _media(loaded[bid][0], extra[dependency][1], localized[dependency], child, streams, parent)
        if found and found[1]:
            result.setdefault(event, {})[variant] = found
    return result


def bindings(tools, stamp, locale, names):
    hashes = {}
    for name in names:
        check(isinstance(name, str) and re.fullmatch('[A-Za-z0-9_]+', name))
        hashes.setdefault(wwise_hash(name), set()).add(name.lower())
    unique = tuple(sorted((key, next(iter(variants))) for key, variants in hashes.items() if len(variants) == 1))
    if not unique:
        return {}
    rows = _inventory(tools / 'sophon', stamp, locale, unique)
    result = {}
    for name in names:
        for variant, (mid, entry) in rows.get(wwise_hash(name), {}).items():
            binding = {'publisher': stamp, 'locale': audio_locale(locale), 'audio_event': name,
                       'event_media': mid, 'bank_package': entry.asset.name, 'bank_digest': entry.asset.digest,
                       'bank_offset': entry.offset, 'bank_size': entry.size}
            if variant:
                binding['event_variant'] = variant
            result.setdefault(name, {})[variant] = binding
    return result


def extract(audio, tools):
    stamp, locale, event = audio['publisher'], audio['locale'], audio['audio_event']
    # Recheck the exact event on playback, keeping an immutable singleton entry
    # when the program restarts and the original indexing process is gone.
    variant = audio.get('event_variant')
    expected = bindings(tools, stamp, locale, (event,)).get(event, {}).get(variant)
    check(expected and all(audio.get(key) == value for key, value in expected.items()))
    directory = tools / 'sophon'
    key = wwise_hash(event)
    _, source = _inventory(directory, stamp, locale, ((key, event.lower()),))[key][variant]
    raw = source.asset.read(directory, source.offset, source.size)
    check(len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WAVE' and _u32(raw, 4) + 8 == len(raw))
    return raw
