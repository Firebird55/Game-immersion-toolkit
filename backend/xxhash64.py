"""Standard seed-zero XXH64 for publisher checksums and resource paths."""
import struct


def xxhash64(data: bytes) -> int:
    """Seed-zero XXH64, using the public xxHash algorithm specification."""
    return xxhash64_stream((data,))


def xxhash64_stream(chunks) -> int:
    """Hash byte chunks without retaining the input; at most 31 bytes carry over."""
    mask = (1 << 64) - 1
    p1, p2, p3, p4, p5 = (0x9e3779b185ebca87, 0xc2b2ae3d27d4eb4f,
                           0x165667b19e3779f9, 0x85ebca77c2b2ae63, 0x27d4eb2f165667c5)
    def rotate(value, bits):
        value &= mask
        return ((value << bits) | (value >> (64 - bits))) & mask
    def lane(accumulator, value):
        return rotate(accumulator + value * p2, 31) * p1 & mask
    length, pending = 0, b''
    a, b, c, d = (p1 + p2) & mask, p2, 0, -p1 & mask
    for chunk in chunks:
        data = memoryview(chunk).cast('B')
        length += len(data)
        position = 0
        if pending:
            needed = 32 - len(pending)
            if len(data) < needed:
                pending += bytes(data)
                continue
            w, x, y, z = struct.unpack('<4Q', pending + bytes(data[:needed]))
            a, b, c, d = lane(a, w), lane(b, x), lane(c, y), lane(d, z)
            position = needed
        end = position + (len(data) - position) // 32 * 32
        for w, x, y, z in struct.iter_unpack('<4Q', data[position:end]):
            a, b, c, d = lane(a, w), lane(b, x), lane(c, y), lane(d, z)
        pending = bytes(data[end:])
    if length >= 32:
        value = (rotate(a, 1) + rotate(b, 7) + rotate(c, 12) + rotate(d, 18)) & mask
        for accumulator in (a, b, c, d):
            value = ((value ^ lane(0, accumulator)) * p1 + p4) & mask
    else:
        value = p5
    value = (value + length) & mask
    data, position = pending, 0
    while position <= len(data) - 8:
        value = (rotate(value ^ lane(0, struct.unpack_from('<Q', data, position)[0]), 27) * p1 + p4) & mask
        position += 8
    if position <= len(data) - 4:
        value = (rotate(value ^ (struct.unpack_from('<I', data, position)[0] * p1), 23) * p2 + p3) & mask
        position += 4
    for digit in data[position:]:
        value = rotate(value ^ digit * p5, 11) * p1 & mask
    value = (value ^ (value >> 33)) * p2 & mask
    value = (value ^ (value >> 29)) * p3 & mask
    return (value ^ (value >> 32)) & mask

