"""Read published cinematic caption records from the regional DesignV directory."""
import math
import re
import struct

from . import starrail_hotfix as hotfix
from .xxhash64 import xxhash64


# This previously named entry already used a scene-based identity. This is
# compatibility for saved IDs only; resource resolution never uses this set.
_LEGACY_NAMED_IDENTITIES = frozenset({'CS_Chap04_Act781_1_Caption.json'})


def caption_resource_id(path):
    # Native JsonToBinaryPath preserves case, replaces the last extension and
    # prepends BakedConfig/ to the complete authored Config/... path.
    hotfix.check(isinstance(path, str) and re.fullmatch(
        r'Config/(?:CutSceneCaption/[A-Za-z0-9_-]+_Caption|BattleCollegeCaption/[A-Za-z0-9_-]+)\.json', path))
    return xxhash64(('BakedConfig/' + path[:-5] + '.bytes').encode('utf-8'))


def caption_filename(path):
    caption_resource_id(path)
    # Tutorial captions have a distinct authored root and no _Caption suffix.
    # Retain that namespace even if a future tutorial shares a cinematic name.
    return path.removeprefix('Config/') if path.startswith('Config/BattleCollegeCaption/') else path.rsplit('/', 1)[1]


def _packages(data, *, with_folder=False):
    header = struct.Struct('>Q16sQI')
    member = struct.Struct('>QII')
    hotfix.check(len(data) >= 16)
    magic, version, packages, total = struct.unpack_from('>4I', data)
    hotfix.check((magic, version) == (255, 4))
    offset, count = 16, 0
    for _ in range(packages):
        hotfix.check(offset + header.size <= len(data))
        first, digest, size, number = header.unpack_from(data, offset)
        offset += header.size
        end = offset + number * member.size
        hotfix.check(number and end + 3 <= len(data))
        entries = list(member.iter_unpack(memoryview(data)[offset:end]))
        tail, = struct.unpack_from('>H', data, end)
        offset = end + tail + 3
        hotfix.check(offset <= len(data) and data[offset - 1] == 0x80 and entries[0][0] == first
                     and len({key for key, _, _ in entries}) == number
                     and all(start + length <= size for _, length, start in entries))
        count += number
        if with_folder:
            # Native DesignV keeps language packages in a relative folder.
            # Caption callers need only the original three-field interface.
            folder = data[end + 2:end + 2 + tail].decode('ascii')
            hotfix.check(not folder or re.fullmatch(r'[a-z]{2,8}(?:-[a-z]{2,8})?', folder))
            yield digest.hex(), size, entries, folder
        else:
            yield digest.hex(), size, entries
    hotfix.check(count == total and offset == len(data))


def _uint(data, offset, bits):
    value = 0
    for shift in range(0, bits, 7):
        if offset == len(data):
            break
        digit = data[offset]
        offset += 1
        value |= (digit & 127) << shift
        if digit < 128 and value < 1 << bits and (not shift or digit):
            return value, offset
    raise ValueError('Invalid design integer.')


def _caption(data, *, allow_empty=False):
    if data[:1] != b'\x01':
        return None
    try:
        count, offset = _uint(data, 1, 32)
        if count % 2 or count // 2 > len(data) // 7 or not count and not allow_empty:
            return None
        rows = []
        for _ in range(count // 2):
            mask, offset = _uint(data, offset, 32)
            if mask & ~63 or mask & 9 != 9:
                return None
            _, offset = _uint(data, offset, 32)  # Legacy localization ID.
            text, offset = _uint(data, offset, 64)
            if mask & 2:  # Screen position precedes the clock.
                _, offset = _uint(data, offset, 32)
            times = {}
            for bit, field in ((4, 'StartTime'), (8, 'EndTime'), (16, 'EaseIn'), (32, 'EaseOut')):
                if mask & bit:
                    value, = struct.unpack_from('<f', data, offset)
                    offset += 4
                    if not math.isfinite(value) or value < 0:
                        return None
                    times[field] = value
            if not text or times.get('StartTime', 0) >= times['EndTime']:
                return None
            rows.append({'CaptionTextID': {'Hash': text}, **times})
        if offset == len(data):
            return {'CaptionList': rows}
    except (ValueError, struct.error):
        pass
    return None


def _signature(script):
    return tuple((row['CaptionTextID']['Hash'], round(row.get('StartTime', 0) * 1000),
                  round(row['EndTime'] * 1000)) for row in script['CaptionList'])


def _caption_run(directory, asset, entries, anchors, wanted=()):
    entries = sorted(entries, key=lambda item: item[2])
    page_size = 64 * 1024
    pages, seen = {}, set()

    def read(start, size):
        parts = []
        while size > 0:
            page = start // page_size * page_size
            if page not in pages:
                pages[page] = asset.read(directory, page, min(page_size, asset.size - page))
            offset = start - page
            block = pages[page][offset:offset + size]
            parts.append(block)
            start += len(block)
            size -= len(block)
        return b''.join(parts)

    def probe(position, *, allow_empty=False):
        key, length, start = entries[position]
        if not length or read(start, 1) != b'\x01' or length > 2 * 1024**2:
            return None
        return _caption(read(start, length), allow_empty=allow_empty)

    for index, (key, _, _) in enumerate(entries):
        if key not in anchors and key not in wanted or index in seen:
            continue
        anchor = probe(index, allow_empty=True)
        if key in anchors:
            hotfix.check(anchor is not None and _signature(anchor) == anchors[key])
        if not anchor:
            continue
        seen.add(index)
        yield key, anchor
        if key not in anchors:
            continue
        for step in (-1, 1):
            position = index + step
            while 0 <= position < len(entries) and position not in seen:
                caption = probe(position)
                if caption is None:
                    break
                seen.add(position)
                yield entries[position][0], caption
                position += step


def extra_captions(directory, build, published, declared_paths=(), *, identities=None, unresolved=None):
    known = {_signature(script) for script in published.values()}
    anchors, names, paths = {}, {}, {}
    for filename, script in published.items():
        path = 'Config/' + filename if filename.startswith('BattleCollegeCaption/') else 'Config/CutSceneCaption/' + filename
        key = caption_resource_id(path)
        hotfix.check(key not in paths or paths[key] == path)
        paths[key], anchors[key] = path, _signature(script)
        if filename.startswith('BattleCollegeCaption/') and identities is not None:
            identities[filename] = f'design_{key:016x}'
    for path in declared_paths:
        key = caption_resource_id(path)
        hotfix.check(key not in paths or paths[key] == path)
        paths[key], names[key] = path, caption_filename(path)
    local, alternate = hotfix.audio_roots(build)
    result, found, indexed, candidates = {}, set(), set(), []
    verified = False
    for digest, size, entries in _packages(hotfix.index(directory, build, 'design')):
        relevant = {key for key, _, _ in entries if key in paths}
        hotfix.check(indexed.isdisjoint(relevant))
        indexed.update(relevant)
        if not relevant:
            continue
        path = digest + '.bytes'
        asset = hotfix.AudioFile(path, size, digest, local['design'] + path,
                                 alternate['design'] + path if alternate else '')
        for key, caption in _caption_run(directory, asset, entries, anchors, names):
            sig = _signature(caption)
            found.add(key)
            if key in anchors:
                hotfix.check(sig == anchors[key])
                verified = verified or bool(sig)
            candidates.append((key, caption))
    hotfix.check(verified)
    # Resolve declared paths before deduplicating unnamed neighbors. An alias
    # encountered earlier in a package cannot hide the actual authored name.
    for key, caption in sorted(candidates, key=lambda row: row[0] not in names):
        sig = _signature(caption)
        if key in anchors or key not in names and sig in known:
            continue
        filename = names.get(key, f'design_{key:016x}_Caption.json')
        hotfix.check(filename not in result and filename not in published)
        result[filename] = caption
        if identities is not None and key in names and filename not in _LEGACY_NAMED_IDENTITIES:
            identities[filename] = f'design_{key:016x}'
        known.add(sig)
    if unresolved is not None:
        unresolved.extend(sorted(paths[key] for key in names.keys() - found))
    return result
