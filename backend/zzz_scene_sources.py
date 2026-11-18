"""Stage verified original ZZZ scene blocks for a publisher reader."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import re
import struct

from .zzz_hotfix import BASE


def stage_scenes(work, cache, files, ranges, *, extension='scenes'):
    grouped = defaultdict(list)
    for row in ranges:
        name = row['block']
        if not re.fullmatch(r'Blocks/\d+\.blk', name):
            raise ValueError('Invalid scene block identity.')
        grouped[name].append((row['offset'], row['size']))

    def stage(item):
        name, ranges = item
        asset = files[BASE + name]

        @lru_cache(maxsize=3)
        def chunk(position, length):
            return asset.read(cache, position, length)

        out = work / (name.split('/')[-1] + '.' + extension)
        with out.open('xb') as handle:
            for start, length in sorted(ranges):
                if not 0 < length <= 64 * 1024**2 or not 0 <= start <= asset.size - length:
                    raise ValueError('Scene exceeds its released package.')
                end = start + length
                handle.write(struct.pack('<I', length))
                begin = handle.tell()
                for offset, size, *_ in asset.chunks:
                    if offset >= end:
                        break
                    if offset + size > start:
                        handle.write(chunk(offset, size)[max(0, start - offset):min(size, end - offset)])
                if handle.tell() - begin != length:
                    raise ValueError('Incomplete staged scene.')
        return out.name

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(stage, sorted(grouped.items())))
