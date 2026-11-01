"""Development-only, reproducible native/source closure for the fixed reader.

Installed runtimes never invoke this builder. The output hash is pinned by the
runtime module; a compiler/cache marker cannot authorize substituted code.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import zipfile

KRAKEN_REVISION = 'f75df7ab817d9ffb43ea8ad84a698ad3df9ba4c1'
KRAKEN_SOURCE = {
    'url': 'https://codeload.github.com/WolvenKit/kraken/tar.gz/' + KRAKEN_REVISION,
    'sha256': '1d115035aa1254e57ab69e2d057240c616bed07c03b0702ec1b271494557bd17',
}
COMPILER_SHA256 = '315c23bc298aba9eaf2aece174fa7fcb0e404247176663e6a4c7707a60f8e444'
COMPILER_VERSION = '2.11.0'
SOURCES = ('compr_entropy.cpp', 'compr_kraken.cpp', 'compr_leviathan.cpp',
           'compr_match_finder.cpp', 'compr_multiarray.cpp', 'compr_tans.cpp',
           'compress.cpp', 'kraken.cpp')
SOURCE_PROJECTS = frozenset({'WolvenKit.CLI', 'WolvenKit.Common', 'WolvenKit.Core',
                            'WolvenKit.Modkit', 'WolvenKit.RED4'})
SOURCE_ROOT_FILES = frozenset({'Directory.Build.props', 'Directory.Packages.props',
    'WolvenKit.Console.sln', 'global.json', 'LICENSE', 'README.md', '.editorconfig'})
SOURCE_EXCLUDED_SUFFIXES = frozenset({'.dll', '.exe', '.so', '.dylib', '.pdb', '.lib', '.exp'})
# No compression feature is removed. These are MinGW header portability fixes:
# upstream explicitly comments that its _rotl substitute is disabled on MinGW.
HEADER_REPLACEMENTS = (
    ('#include <limits.h>', '#include <limits.h>\n#include <immintrin.h>'),
    ('\t\t#define __forceinline inline __attribute__((always_inline))',
     '\t\t#ifndef __forceinline\n\t\t#define __forceinline inline __attribute__((always_inline))\n\t\t#endif'),
    ('\tstatic inline uint32_t _rotl(uint32_t x, int n) {\n\t  return (((x) << (n)) | ((x) >> (32-(n))));\n\t}',
     '\t#if !defined(__MINGW32__)\n\tstatic inline uint32_t _rotl(uint32_t x, int n) {\n\t  return (((x) << (n)) | ((x) >> (32-(n))));\n\t}\n\t#endif'),
)


def patch_header(data: bytes) -> bytes:
    text = data.decode('utf-8').replace('\r\n', '\n')
    for old, new in HEADER_REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError('Kraken source differs from the reviewed portability patch')
        text = text.replace(old, new)
    return text.encode('utf-8')


def corresponding_source(archive: Path, destination: Path):
    """Retain the exact five shipped projects, excluding opaque binary copies.

Tests and the desktop editor are separate projects and contain game samples;
they are deliberately not redistributed. Every selected member is byte-identical
to the pinned upstream source. The selection/build adapter is retained alongside.
    """
    selected = {}
    names = set()
    with tarfile.open(archive) as source, zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_STORED) as output:
        for member in sorted(source.getmembers(), key=lambda item: item.name):
            path = PurePosixPath(member.name)
            if not path.parts or path.parts[0] != 'WolvenKit-9.0.1':
                raise ValueError('Unexpected upstream source root')
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts:
                continue
            if relative.parts[0] not in SOURCE_PROJECTS and relative.as_posix() not in SOURCE_ROOT_FILES:
                continue
            if member.isdir():
                continue
            if not member.isfile() or '..' in relative.parts or member.size > 32 * 1024 * 1024:
                raise ValueError('Unsafe upstream corresponding-source member')
            if relative.suffix.lower() in SOURCE_EXCLUDED_SUFFIXES:
                continue
            normalized = relative.as_posix().casefold()
            if normalized in names:
                raise ValueError('Duplicate corresponding-source member')
            names.add(normalized)
            data = source.extractfile(member).read()
            entry = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            output.writestr(entry, data)
            selected[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    return selected


def build_kraken(archive: Path, destination: Path, *, toolchain: Path | None = None):
    from .cyberpunk_toolchain import _sha, verify_archive, OWNED_FILES
    from .preparation_errors import PreparationFailure
    from .owned_process import OwnedProcess
    verify_archive(archive, KRAKEN_SOURCE)
    toolchain = toolchain or (Path(os.environ['PROXY_TRANSCRIPT_NATIVE_TOOLCHAIN'])
        if os.environ.get('PROXY_TRANSCRIPT_NATIVE_TOOLCHAIN') else None)
    if toolchain is None:
        raise PreparationFailure('source_compiler_missing', 'Source preparation needs the pinned w64devkit 2.11.0 build toolchain. The installer already includes this reader.')
    toolchain = toolchain.resolve()
    compiler = toolchain / 'bin/g++.exe'
    if not compiler.is_file() or _sha(compiler) != COMPILER_SHA256:
        raise ValueError('The native build compiler differs from pinned w64devkit 2.11.0')
    with tempfile.TemporaryDirectory(prefix='kraken-build-', dir=destination.parent) as temp:
        work = Path(temp)
        with tarfile.open(archive) as source:
            for member in source:
                path = PurePosixPath(member.name)
                if path.parts[0] != 'kraken-' + KRAKEN_REVISION or '..' in path.parts:
                    raise ValueError('Unexpected Kraken source member')
                # Only root source/header inputs enter the native compilation.
                if len(path.parts) != 2 or path.suffix not in {'.cpp', '.h'}:
                    continue
                if not member.isfile() or member.size > 4 * 1024 * 1024:
                    raise ValueError('Unsafe Kraken compiler input')
                (work / path.name).write_bytes(source.extractfile(member).read())
        header = work / 'kraken.h'
        header.write_bytes(patch_header(header.read_bytes()))
        exports = work / 'kraken.def'
        exports.write_text('LIBRARY kraken\nEXPORTS\nKraken_Decompress\nKraken_Compress\n', encoding='ascii', newline='\n')
        flags = ['-shared', '-O2', '-DNDEBUG', '-static', '-static-libgcc', '-static-libstdc++',
                 '-frandom-seed=toolkit-kraken-v1', '-ffile-prefix-map=' + str(work) + '=/_src',
                 '-Wl,--no-insert-timestamp,--exclude-all-symbols', '-o', 'kraken.dll', 'kraken.def', *SOURCES]
        env = {'PATH': str(compiler.parent), **{key: value for key, value in os.environ.items()
            if key.lower() in {'systemroot', 'windir', 'temp', 'tmp'}}}
        child = OwnedProcess([str(compiler), *flags], cwd=work, env=env)
        try:
            child.process.communicate(timeout=180)
            if child.process.returncode or not (work / 'kraken.dll').is_file():
                raise RuntimeError('Pinned Kraken native compilation failed')
        finally:
            child.stop()
            child.close_streams()
        if _sha(work / 'kraken.dll') != OWNED_FILES['reader/kraken.dll']:
            raise ValueError('Kraken build did not reproduce its pinned native hash')
        shutil.copyfile(work / 'kraken.dll', destination / 'reader/kraken.dll')
    shutil.copyfile(archive, destination / 'sources/kraken-source.tar.gz')
