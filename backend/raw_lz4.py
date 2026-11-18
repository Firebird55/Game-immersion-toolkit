"""Bounded raw LZ4 blocks shared by the original-data parsers."""


def decompress(raw, expected):
    """Raw LZ4 blocks used by legacy bundles, with an explicit output bound."""
    out, position = bytearray(), 0
    def length(initial):
        nonlocal position
        result = initial
        if initial == 15:
            while True:
                if position >= len(raw):
                    raise ValueError('incomplete LZ4 length')
                value = raw[position]; position += 1; result += value
                if result > expected:
                    raise ValueError('oversized LZ4 sequence')
                if value != 255:
                    break
        return result
    while position < len(raw):
        token = raw[position]; position += 1
        literal = length(token >> 4)
        if position + literal > len(raw) or len(out) + literal > expected:
            raise ValueError('invalid LZ4 literal')
        out.extend(raw[position:position + literal]); position += literal
        if position == len(raw):
            break
        if position + 2 > len(raw):
            raise ValueError('incomplete LZ4 offset')
        distance = int.from_bytes(raw[position:position + 2], 'little'); position += 2
        count = length(token & 15) + 4
        if not 0 < distance <= len(out) or len(out) + count > expected:
            raise ValueError('invalid LZ4 match')
        for _ in range(count):
            out.append(out[-distance])
    if len(out) != expected:
        raise ValueError('incomplete LZ4 block')
    return bytes(out)
