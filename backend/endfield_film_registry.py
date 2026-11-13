"""Resolve audited film asset paths in an independently versioned bundle registry."""
import re
import struct


def _check(value):
    if not value:
        raise ValueError('Unsupported Endfield cinematic asset registry.')


def inflate(raw, limit):
    import brotli
    decoder = brotli.Decompressor()
    output = bytearray()
    try:
        for start in range(0, len(raw), 256 * 1024):
            part = raw[start:start + 256 * 1024]
            while True:
                output.extend(decoder.process(part, min(4 * 1024**2, limit - len(output) + 1)))
                _check(len(output) <= limit)
                if decoder.can_accept_more_data():
                    break
                part = b''
        _check(decoder.is_finished())
    except brotli.error as error:
        raise ValueError('Invalid Endfield compressed asset registry.') from error
    return output


def bindings(data, *, path_hashes=None, bundle_indices=None, path_prefixes=None):
    """Resolve exact paths, or discover every released asset matching a path prefix."""
    _check(sum(value is not None for value in (path_hashes, bundle_indices, path_prefixes)) == 1)
    size = len(data)

    def integer(pos):
        _check(0 <= pos <= size - 4)
        return struct.unpack_from('<i', data, pos)[0]

    def after_name(pos):
        length = integer(pos)
        _check(0 <= length <= 256)
        return pos + 4 + length * 2

    _check(data[:4] == bytes.fromhex('11ff11ff'))
    second = after_name(4)
    _check(data[second:second + 4] == bytes.fromhex('f4f3f2f1'))
    header = after_name(after_name(second + 4))
    assets = header + 4
    asset_end = assets + integer(header)
    bundles = asset_end + 4 + integer(asset_end) + 4
    strings = bundles + integer(bundles - 4) + 4
    _check(assets < asset_end < bundles < strings <= size)
    first = assets + 4 + integer(assets) * 8
    _check(assets <= first <= asset_end and (asset_end - first) % 24 == 0)
    count = integer(bundles)
    _check(0 < count <= 1_000_000 and bundles + 4 + count * 48 <= strings)

    def string_at(offset, compressed):
        pos = strings + offset
        length = integer(pos)
        _check(offset >= 0 and 0 < length <= 16384 and pos + 4 + length <= size)
        raw = data[pos + 4:pos + 4 + length]
        return (inflate(raw, 8192) if compressed else raw).decode('utf-16le')

    found = []
    needed = set()
    for pos in range(first, asset_end, 24):
        head, path_offset, index = struct.unpack_from('<qii', data, pos)
        selected = path_prefixes is not None or (head in path_hashes if path_hashes is not None else index in bundle_indices)
        if selected:
            path = string_at(path_offset, True)
            if path_prefixes is not None and not path.startswith(path_prefixes):
                continue
            found.append((head, path, index))
            needed.add(index)
    names = {}
    for pos in range(bundles + 4, bundles + 4 + count * 48, 48):
        index, offset = struct.unpack_from('<ii', data, pos)
        if index in needed:
            _check(index not in names)
            name = string_at(offset, False)
            _check(re.fullmatch(r'(?:main|initial)/[0-9a-f]+\.ab', name))
            names[index] = name
    _check(needed == names.keys())
    return [(head, path, names[index]) for head, path, index in found]
