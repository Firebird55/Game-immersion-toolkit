"""Read the complete serialized body of a bounded, decoded BLB3 container."""
import struct

from .raw_lz4 import decompress


def _check(condition):
    if not condition:
        raise ValueError('Unsupported or incomplete original Genshin container preparation.')


def unpack(decoded, destination, *, max_package, max_body):
    """Decompress one exact bounded body into a new file."""
    _check(decoded.is_file() and not destination.exists())
    with decoded.open('rb') as stream:
        length = decoded.stat().st_size
        _check(84 <= length <= max_package)
        prefix = stream.read(28)
        _check(len(prefix) == 28 and prefix[:4] == b'Blb\x03')
        size = struct.unpack_from('<I', prefix, 4)[0]
        _check(56 <= size <= min(1024**2, length - 28))
        head = stream.read(size)
        _check(len(head) == size)

        blocks, nodes = struct.unpack_from('<ii', head, 24)
        last = struct.unpack_from('<I', head, 4)[0]
        shift = head[21]
        _check(0 < shift <= 23)
        step = 1 << shift
        body_size = (blocks - 1) * step + last
        _check(nodes == 1 and 0 < blocks <= 8192 and 0 < last <= step and body_size <= max_body)
        node = 40 + struct.unpack_from('<q', head, 40)[0]
        _check(56 <= node <= len(head) - 8)
        node_offset, node_size = struct.unpack_from('<ii', head, node)
        _check(node_offset == 0 and node_size == body_size)
        at = 32 + struct.unpack_from('<q', head, 32)[0]
        _check(56 <= at <= len(head) - blocks * 4)
        _check(at + blocks * 4 <= node or node + 8 <= at)
        ends = struct.unpack_from('<' + 'I' * blocks, head, at)
        _check(ends[-1] == length - 28 - size)

        previous = 0
        output = destination.open('xb')
        try:
            with output:
                for number, end in enumerate(ends):
                    _check(previous < end <= ends[-1])
                    compressed = stream.read(end - previous)
                    _check(len(compressed) == end - previous)
                    expected = last if number == blocks - 1 else step
                    raw = compressed if len(compressed) == expected else decompress(compressed, expected)
                    output.write(raw)
                    previous = end
                _check(not stream.read(1))
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
