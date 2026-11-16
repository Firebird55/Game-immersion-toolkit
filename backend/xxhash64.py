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
    accumulators = [(p1 + p2) & mask, p2, 0, -p1 & mask]
    for chunk in chunks:
        data = memoryview(chunk).cast('B')
        length += len(data)
        position = 0
        if pending:
            needed = 32 - len(pending)
            if len(data) < needed:
                pending += bytes(data)
                continue
            values = struct.unpack('<4Q', pending + bytes(data[:needed]))
            accumulators = [lane(acc, value) for acc, value in zip(accumulators, values)]
            position, pending = needed, b''
        while position <= len(data) - 32:
            values = struct.unpack_from('<4Q', data, position)
            accumulators = [lane(acc, value) for acc, value in zip(accumulators, values)]
            position += 32
        pending = bytes(data[position:])
    if length >= 32:
        value = sum(rotate(acc, bits) for acc, bits in zip(accumulators, (1, 7, 12, 18))) & mask
        for acc in accumulators:
            value = ((value ^ lane(0, acc)) * p1 + p4) & mask
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

