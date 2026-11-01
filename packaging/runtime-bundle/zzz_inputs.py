"""Exact ZZZ build inputs and retained preferred source; never executes suppliers."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
POLICY = 'packaging/zzz-reader/production-inputs.json'
PREFIX = 'toolchains/zzz/'
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024


def no_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('ZZZ input paths cannot traverse links or reparse points.')


def read_pins(path: Path | None = None) -> dict:
    pins = json.loads((path or ROOT / POLICY).read_text(encoding='utf-8'))
    if pins.get('schema') != 'toolkit-zzz-inputs-v1':
        raise ValueError('Unknown ZZZ input policy.')
    names = [p['name'] for p in pins['archives']]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZZZ archive identity.')
    return pins


def verified(path: Path, pin: dict) -> bytes:
    no_links(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('ZZZ supplier archive must be a bounded regular file.')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('ZZZ supplier archive differs: ' + pin['name'])
    integrity = pin.get('integrity')
    if integrity and integrity != 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode():
        raise ValueError('ZZZ supplier npm integrity differs: ' + pin['name'])
    return data


def acquire_inputs(cache: Path, pins: dict | None = None) -> dict[str, Path]:
    """Acquire hash-locked archives with bounded retry and atomic cache writes."""
    pins = pins or read_pins()
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    no_links(cache)
    result = {}
    for pin in pins['archives']:
        filename = pin['archive']
        if PurePosixPath(filename).name != filename or '\\' in filename:
            raise ValueError('Unsafe ZZZ archive name.')
        path = cache / filename
        if not path.exists():
            partial = path.with_name(path.name + '.partial')
            if partial.exists() or partial.is_symlink():
                raise ValueError('ZZZ download staging file already exists.')
            for attempt in range(3):
                try:
                    request = urllib.request.Request(pin['url'], headers={'User-Agent': 'Game-Immersion-Toolkit-build'})
                    with urllib.request.urlopen(request, timeout=60) as response, partial.open('xb') as stream:
                        total = 0
                        while block := response.read(1024 * 1024):
                            total += len(block)
                            if total > MAX_ARCHIVE:
                                raise ValueError('ZZZ supplier download exceeds its limit.')
                            stream.write(block)
                    verified(partial, pin)
                    partial.replace(path)
                    break
                except (OSError, urllib.error.URLError):
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
                finally:
                    if partial.exists():
                        partial.unlink()
        verified(path, pin)
        result[pin['name']] = path
    return result


def archive_members(path: Path, pin: dict) -> dict[str, bytes]:
    """Read ordinary tar members without extracting paths, links, or devices."""
    verified(path, pin)
    result, seen, expanded = {}, set(), 0
    with tarfile.open(path, 'r:gz') as archive:
        for item in archive:
            name = item.name.rstrip('/')
            parts = PurePosixPath(name).parts
            if not name or name.startswith('/') or '\\' in name or any(p in {'.', '..'} or ':' in p for p in parts):
                raise ValueError('Unsafe ZZZ archive member.')
            if name in seen:
                raise ValueError('Duplicate ZZZ archive member.')
            seen.add(name)
            if item.isdir():
                continue
            if not item.isfile():
                raise ValueError('ZZZ archives cannot contain links or special files.')
            expanded += item.size
            if item.size < 0 or expanded > MAX_EXPANDED:
                raise ValueError('ZZZ expanded archive exceeds its limit.')
            result[name] = archive.extractfile(item).read()
    for expected in pin.get('files', []) + pin.get('notices', []):
        if hashlib.sha256(result.get(expected['member'], b'')).hexdigest() != expected['sha256']:
            raise ValueError('ZZZ archive member differs: ' + expected['member'])
    return result


def retained_members(pins: dict, archives: dict[str, Path]) -> dict[str, bytes]:
    """Return exact runtime dependencies and source/terms, with no build compiler."""
    result, sources = {}, {}
    for pin in pins['archives']:
        members = archive_members(archives[pin['name']], pin)
        sources[pin['name']] = members
        if pin['role'] == 'build-only':
            continue
        if pin['role'] == 'source':
            result[PREFIX + 'sources/' + pin['archive']] = verified(archives[pin['name']], pin)
        if pin['role'] == 'runtime':
            folder = {'ooz-wasm': 'ooz', 'xxhash-wasm': 'xxhash'}[pin['name']]
            for item in pin['files']:
                result[PREFIX + 'dependencies/' + folder + '/' + item['member'].removeprefix('package/')] = members[item['member']]
        else:
            for index, item in enumerate(pin['notices'], 1):
                result[PREFIX + 'notices/' + pin['name'] + f'-{index:02d}.txt'] = members[item['member']]
    by_name = {p['name']: p for p in pins['archives']}
    upstream = pins['upstream']
    reader = sources['reader-source']
    reader_prefix = by_name['reader-source']['prefix']
    for source_name, expected, target in ((upstream['path'], upstream['sha256'], 'galgame-perform.ts'),
            (upstream['license_path'], upstream['license_sha256'], 'LICENSE')):
        data = reader[reader_prefix + source_name]
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('ZZZ preferred reader source or license differs.')
        result[PREFIX + 'upstream/' + target] = data
    # These comparisons establish source-member correspondence, not a claim
    # that the generated WASM was independently reproduced.
    for source, package, names in (('ooz-source', 'ooz-wasm', ('package.json', 'index.js', 'LICENSE')),
                                  ('xxhash-source', 'xxhash-wasm', ('package.json', 'LICENSE.md'))):
        prefix = by_name[source]['prefix']
        for name in names:
            if sources[source][prefix + name] != sources[package]['package/' + name]:
                raise ValueError('ZZZ npm/source member identity differs: ' + name)
    result[PREFIX + 'notices/INPUTS.json'] = (json.dumps(pins, indent=2) + '\n').encode()
    return result
