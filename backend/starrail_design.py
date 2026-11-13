"""Read published cinematic caption records from the regional DesignV directory."""
import math
import struct

from . import starrail_hotfix as hotfix


# These original resource IDs were checked against all cues in the named
# scripts. The directory supplies the current package, offset and size.
CAPTION_ANCHORS = {
    0xf5ea143b3b93e86b: 'CS_Chap00_Act220_Caption.json',
    0x7677ef7aa22242d5: 'CS_Chap01_Act3020_Caption.json',
    0x1eab6bb9b4906c60: 'CS_Chap04_Act781_2_Caption.json',
}
# The Mandarin lyric script for Ripples of Past Reverie is independently
# identified by the publisher's lyrics and the mission's default caption path.
NAMED_CAPTIONS = {0xb9cef1d1ff5c465b: 'CS_Chap04_Act781_1_Caption.json'}


def _packages(data):
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


def _caption(data):
    if data[:1] != b'\x01':
        return None
    try:
        count, offset = _uint(data, 1, 32)
        if count % 2 or not 0 < count // 2 <= len(data) // 7:
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


def _caption_run(directory, asset, entries, anchors):
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

    def probe(position):
        key, length, start = entries[position]
        if not length or read(start, 1) != b'\x01' or length > 2 * 1024**2:
            return None
        return _caption(read(start, length))

    for index, (key, _, _) in enumerate(entries):
        if key not in anchors or index in seen:
            continue
        anchor = probe(index)
        if not anchor or _signature(anchor) != anchors[key]:
            continue
        seen.add(index)
        yield key, anchor
        for step in (-1, 1):
            position = index + step
            while 0 <= position < len(entries) and position not in seen:
                caption = probe(position)
                if caption is None:
                    break
                seen.add(position)
                yield entries[position][0], caption
                position += step


def extra_captions(directory, build, published):
    known = {_signature(script) for script in published.values()}
    anchors = {key: _signature(published[name]) for key, name in CAPTION_ANCHORS.items() if name in published}
    local, alternate = hotfix.audio_roots(build)
    result = {}
    verified = False
    for digest, size, entries in _packages(hotfix.index(directory, build, 'design')):
        if not any(key in anchors for key, _, _ in entries):
            continue
        path = digest + '.bytes'
        asset = hotfix.AudioFile(path, size, digest, local['design'] + path,
                                 alternate['design'] + path if alternate else '')
        for key, caption in _caption_run(directory, asset, entries, anchors):
            sig = _signature(caption)
            if key in anchors and sig == anchors[key]:
                verified = True
            if sig in known:
                continue
            filename = NAMED_CAPTIONS.get(key, f'design_{key:016x}_Caption.json')
            hotfix.check(filename not in result and filename not in published)
            result[filename] = caption
            known.add(sig)
    hotfix.check(verified)
    return result
