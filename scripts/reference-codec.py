"""Build-host-only source kit and exact output verification for Xiph FLAC.

Self-contained stdlib code: the delivered kit can rebuild without this repo.
Never installs tools, downloads a binary, or changes runtime codec dispatch.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('packaging/codecs/flac-reference.json', 'scripts/build-reference-codec.ps1',
          'scripts/reference-codec.py', 'LICENSE', 'packaging/codecs/FLAC-BUILD-RECIPES-LICENSE.txt')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('Links and reparse points are not allowed.')
        if item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse points are not allowed.')


def safe_name(name):
    if (not name or '\\' in name or ':' in name or PurePosixPath(name).is_absolute()
            or any(part in {'', '.', '..'} or part.endswith((' ', '.')) for part in name.split('/'))
            or any(ord(c) < 32 for c in name)):
        raise ValueError('Non-canonical archive path.')
    return name


def policy():
    return json.loads((ROOT / INPUTS[0]).read_text(encoding='utf-8'))


def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        no_links(p)
        if p.is_file():
            result[p.relative_to(root).as_posix()] = {'bytes': p.stat().st_size, 'sha256': digest(p.read_bytes())}
        elif not p.is_dir():
            raise ValueError('Non-regular artifact.')
    return result


def prepare(archive, output):
    pin = policy()
    archive, output = Path(archive).absolute(), Path(output).absolute()
    no_links(archive); no_links(output)
    if output.exists() or digest(archive.read_bytes()) != pin['source']['sha256']:
        raise ValueError('Need the exact upstream source archive and a fresh output root.')
    # Validate the entire tar before any output write; no symlink/hardlink,
    # duplicate/case alias, device or traversal may precede rejection.
    with tarfile.open(archive, 'r:xz') as tar:
        members, seen = tar.getmembers(), set()
        if len(members) > 4096 or sum(m.size for m in members) > 64 * 1024 * 1024:
            raise ValueError('Source archive exceeds its bounded inventory.')
        for m in members:
            name = safe_name(m.name.rstrip('/'))
            if (not (m.isfile() or m.isdir()) or name.casefold() in seen
                    or name.split('/')[0] != 'flac-' + pin['version']
                    or m.size > 16 * 1024 * 1024):
                raise ValueError('Source archive contains unsupported entries.')
            seen.add(name.casefold())
        for name, sha in pin['notices'].items():
            if digest(tar.extractfile('flac-' + pin['version'] + '/' + name).read()) != sha:
                raise ValueError('Upstream notice differs.')
        output.mkdir(parents=True)
        tar.extractall(output / 'upstream', members=members, filter='data')
    kit = output / 'source-kit'; (kit / 'inputs').mkdir(parents=True)
    shutil.copyfile(archive, kit / 'inputs' / pin['source']['filename'])
    for name in INPUTS:
        target = kit / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    source = output / 'upstream' / ('flac-' + pin['version'])
    notices = output / 'candidate/notices'; notices.mkdir(parents=True)
    for name in pin['notices']:
        shutil.copyfile(source / name, notices / name)
    (output / 'PREPARED-SOURCE.json').write_text(json.dumps(inventory(source)), encoding='utf-8')
    # Retain the original file-level headers, including contributors' notices.
    # Full original files (and all build systems) remain in the exact source tar.
    copyrights = []
    for p in sorted(source.rglob('*')):
        if p.suffix.lower() not in {'.c', '.h', '.cpp', '.s'} or not p.is_file():
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        end = text.find('\n#include')
        prefix = text[:end] if end >= 0 else text
        if 'Copyright' in prefix or 'copyright' in prefix:
            copyrights.append(p.relative_to(source).as_posix() + '\n' + prefix)
    (notices / 'SOURCE-COPYRIGHTS.txt').write_text('\n\n'.join(copyrights), encoding='utf-8')
    return source


def pe_imports(data):
    """Normal/delay PE imports; runtime LoadLibrary dependencies remain a gate."""
    u16 = lambda p: struct.unpack_from('<H', data, p)[0]
    u32 = lambda p: struct.unpack_from('<I', data, p)[0]
    u64 = lambda p: struct.unpack_from('<Q', data, p)[0]
    pe = u32(60); opt = pe + 24
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0' or u16(pe+4) != 0x8664 or u16(opt) != 0x20b:
        raise ValueError('Expected an x64 PE32+ artifact.')
    sections = []
    for n in range(u16(pe+6)):
        p = opt + u16(pe+20) + n * 40
        sections.append((u32(p+12), max(u32(p+8), u32(p+16)), u32(p+20)))
    def offset(rva):
        for va, size, raw in sections:
            if va <= rva < va + size: return raw + rva - va
        raise ValueError('Unmapped PE address.')
    result = {}
    for label, index, stride in [('imports', 1, 20), ('delay_imports', 13, 32)]:
        rva, size = struct.unpack_from('<II', data, opt+112+index*8)
        names = []
        if rva:
            for n in range(min(size // stride, 256)):
                p = offset(rva) + n * stride
                if not any(data[p:p+stride]): break
                addr = u32(p+12) if index == 1 else u32(p+4) - (0 if u32(p)&1 else u64(opt+24))
                start = offset(addr); end = data.index(0, start, start+256)
                names.append(data[start:end].decode('ascii'))
        result[label] = sorted(names, key=str.casefold)
    return result


def finish(output, compiler, cmake):
    output = Path(output).absolute(); no_links(output)
    pin = policy()
    source = output / 'upstream' / ('flac-' + pin['version'])
    if inventory(source) != json.loads((output / 'PREPARED-SOURCE.json').read_text()):
        raise ValueError('Build changed the verified upstream sources.')
    cache = {}
    for line in (output / 'build/CMakeCache.txt').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith(('#', '//')) or '=' not in line: continue
        name, value = line.split('=', 1); cache[name.split(':')[0]] = value
    if any(cache.get(name) != value for name, value in pin['cmake'].items()):
        raise ValueError('Actual CMake configuration differs from the source-closure policy.')
    compiler_files = list((output / 'build/CMakeFiles').glob('*/CMakeCCompiler.cmake'))
    if (len(compiler_files) != 1 or 'set(CMAKE_C_COMPILER_ID "MSVC")' not in compiler_files[0].read_text()
            or cache.get('CMAKE_MSVC_RUNTIME_LIBRARY') != 'MultiThreadedDLL'):
        raise ValueError('Unexpected compiler family.')
    for name in ('flac.exe', 'FLAC.dll'):
        src = output / 'build/objs/Release' / name
        no_links(src); pe_imports(src.read_bytes())
        shutil.copyfile(src, output / 'candidate' / name)
    files = inventory(output / 'candidate')
    imports = {name: pe_imports((output / 'candidate' / name).read_bytes()) for name in ('flac.exe', 'FLAC.dll')}
    allowed = {'kernel32.dll', 'advapi32.dll', 'msvcrt.dll', 'ucrtbase.dll',
               'vcruntime140.dll', 'vcruntime140_1.dll', 'flac.dll'}
    for item in imports.values():
        for name in item['imports'] + item['delay_imports']:
            if name.lower() not in allowed and not name.lower().startswith('api-ms-win-crt-'):
                raise ValueError('Unclassified native import: ' + name)
    kit = output / 'source-kit'
    # No host paths, compiler logs, binaries or unreviewed tree in source delivery.
    expected = {'inputs/' + pin['source']['filename'], *INPUTS}
    if set(inventory(kit)) != expected:
        raise ValueError('Source kit differs from its exact allowlist.')
    if (digest((kit / 'inputs' / pin['source']['filename']).read_bytes()) != pin['source']['sha256']
            or any((kit / name).read_bytes() != (ROOT / name).read_bytes() for name in INPUTS)):
        raise ValueError('Delivered source/recipe differs from this build.')
    source_files = inventory(kit)
    with zipfile.ZipFile(output / 'codec-sources.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(source_files):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); entry.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(entry, (kit / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip() if (ROOT / '.git').exists() else 'source-kit-rebuild'
    result = {'schema': 'proxy-r19-reference-codec-v1', 'source_commit': commit,
        'upstream_source_sha256': pin['source']['sha256'], 'upstream_commit': pin['source']['commit'],
        'version': pin['version'], 'platform': pin['platform'], 'configuration': pin['cmake'],
        'generator': cache.get('CMAKE_GENERATOR'), 'compiler_family': 'MSVC',
        'files': files, 'pe': imports, 'source_files': source_files,
        'source_archive_sha256': digest((output / 'codec-sources.zip').read_bytes()),
        'compiler_version': compiler, 'cmake_version': cmake, 'source_patches': [],
        'source_delivery': 'complete-covered-source-and-recipe-prepared; not-published-with-a-production-binary',
        'system_prerequisites': 'MSVC/UCRT system DLLs; no redistributable CRT is collected',
        'production_execution_allowed': False, 'runtime_collection_allowed': False,
        'native_windows_11_acceptance': 'unavailable', 'installer': 'not-built', 'r19_complete': False}
    (output / 'CODEC-CANDIDATE.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['prepare', 'finish'])
    p.add_argument('--output', type=Path, required=True); p.add_argument('--archive', type=Path)
    p.add_argument('--compiler-version'); p.add_argument('--cmake-version')
    a = p.parse_args()
    if a.action == 'prepare': prepare(a.archive, a.output)
    else: finish(a.output, a.compiler_version, a.cmake_version)
