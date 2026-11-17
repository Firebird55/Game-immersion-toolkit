"""Bounded prefetch of registry-selected original IoStore dialogue blocks.

Only complete, uniquely overlaid package claims are eligible. Existing block
verification and atomic cache publication remain owned by Container. No archive
gap, unrelated package or full UCAS is fetched to join separate selected runs.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .nte_publisher_iostore import Container
from .nte_publisher_pak import TRANSFER
from .preparation_errors import PreparationFailure

MAX_PACKAGES = 8192
MAX_PACKAGE_BYTES = 128*1024**2
MAX_NEW_BYTES = 64*1024**2
MAX_BLOCKS = 250_000
MAX_WORKERS = 8


def _check(ok):
    if not ok:
        raise PreparationFailure('game_metadata_unavailable',
            'The original NTE dialogue package inventory could not be verified within the prefetch bounds. '
            'Retry preparation; the previous completed index is retained.')


@dataclass(frozen=True)
class Plan:
    package_count: int
    package_bytes: int
    selected: tuple
    runs: tuple
    new_bytes: int


def plan(containers, packages, *, max_new_bytes='default'):
    from .nte_publisher import _overlay
    if max_new_bytes == 'default':
        max_new_bytes = MAX_NEW_BYTES
    _check((max_new_bytes is None or type(max_new_bytes) is int and 0 <= max_new_bytes <= MAX_NEW_BYTES)
           and isinstance(containers, dict) and 0 < len(containers) <= 128
           and all(isinstance(source, Container) for source in containers.values())
           and isinstance(packages, dict) and 0 < len(packages) <= MAX_PACKAGES
           and all(isinstance(name, str) and type(size) is int and 0 < size <= 4*1024**2
                   for name, size in packages.items())
           and len({name.casefold() for name in packages}) == len(packages)
           and sum(packages.values()) <= MAX_PACKAGE_BYTES)
    overlay = _overlay(containers, lambda container: (row[0] for row in container.paths.values()))
    selected = {}
    for name, size in packages.items():
        claim = overlay.get(name.casefold())
        _check(claim is not None)
        _, source, actual = claim
        offset, length = source.locations[source.paths[actual.casefold()][1]]
        _check(length == size)
        first, stop = offset//source.block_size, (offset+length+source.block_size-1)//source.block_size
        selected.setdefault(source, set()).update(range(first, stop))
        _check(sum(map(len, selected.values())) <= MAX_BLOCKS)
    runs, new_bytes = [], 0
    for source, indices in selected.items():
        missing = [i for i in sorted(indices) if source._cached(i) is None]
        cursor = 0
        while cursor < len(missing):
            first = missing[cursor]; stop = first+1
            size = source.blocks[first].length
            cursor += 1
            while cursor < len(missing) and missing[cursor] == stop:
                previous, following = source.blocks[stop-1], source.blocks[stop]
                if previous.offset+previous.length != following.offset or size+following.length > TRANSFER:
                    break
                size += following.length; stop += 1; cursor += 1
            new_bytes += size
            _check(max_new_bytes is None or new_bytes <= max_new_bytes)
            runs.append((source, first, stop))
    return Plan(len(packages), sum(packages.values()),
                tuple((source, tuple(sorted(indices))) for source, indices in selected.items()), tuple(runs), new_bytes)


def prefetch(containers, packages, progress=lambda _: None):
    selected = plan(containers, packages)
    progress(f'Prefetching {selected.package_count:,} verified original NTE dialogue packages')
    def fetch(run):
        source, first, stop = run
        return len(source.stored_blocks(first, stop))
    if selected.runs:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(selected.runs))) as pool:
            # Exhaust every result: checksum, source or acquisition failure
            # must propagate, never become partial-inventory success.
            futures = [pool.submit(fetch, run) for run in selected.runs]
            percent = -1
            try:
                for done, future in enumerate(as_completed(futures), 1):
                    future.result()
                    complete = done*100//len(futures)
                    if complete != percent:
                        percent = complete
                        progress(f'Preparing original NTE dialogue data: {complete}%')
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
    _check(all(source._cached(index) is not None for source, indices in selected.selected for index in indices))
    return {'package_count': selected.package_count, 'package_bytes': selected.package_bytes,
            'selected_blocks': sum(len(indices) for _, indices in selected.selected),
            'new_compressed_bytes_upper_bound': selected.new_bytes, 'requests_upper_bound': len(selected.runs),
            'workers': min(MAX_WORKERS, len(selected.runs)), 'complete': True}
