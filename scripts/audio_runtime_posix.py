"""Pinned POSIX codec construction; no system codec discovery or downloads by CMake.

These build-host helpers are not runtime dependencies. The complete upstream
sources and this adapter are retained so the static CLI can be rebuilt/relinked.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

FEATURES = ('MPEG', 'VORBIS', 'FFMPEG', 'G7221', 'G719', 'ATRAC9', 'CELT', 'SPEEX')
DEPENDENCIES = ('libogg-1.3.5', 'libvorbis-1.3.7', 'opus-1.6.1', 'mpg123-1.33.7',
                'speex-1.2.1', 'celt-0.6.1', 'celt-0.11.0')
CELT_OPUS_COLLISIONS = ('celt_encoder_get_size', 'celt_encoder_init')
OS_ELF_LIBRARIES = frozenset({'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2',
    'librt.so.1', 'libgcc_s.so.1', 'ld-linux-x86-64.so.2', 'ld-linux-aarch64.so.1'})


def extract(pin, work, cache, sources, acquire):
    archive = acquire(pin, cache)
    with tarfile.open(archive) as source:
        source.extractall(work, filter='data')
    shutil.copyfile(archive, sources / pin['archive'])
    result = work / pin['directory']
    if not result.is_dir():
        raise ValueError('Pinned codec archive has an unexpected source root')
    return result


def cmake_options(prefix):
    return ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_POLICY_VERSION_MINIMUM=3.5',
        '-DBUILD_SHARED_LIBS=OFF', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
        '-DCMAKE_INSTALL_LIBDIR=lib', '-DCMAKE_INSTALL_PREFIX=' + str(prefix),
        '-DCMAKE_PREFIX_PATH=' + str(prefix), '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF',
        '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']


def prepare_dependencies(pins, work, prefix, cache, sources, env, shell, jobs, acquire, run):
    pin = pins['vgmstream']
    dependencies = {item['directory']: item for item in pin['dependency_sources']}
    if set(dependencies) != set(DEPENDENCIES):
        raise ValueError('Review the changed vgmstream dependency closure before building')
    paths = {name: extract(dependencies[name], work, cache, sources, acquire) for name in DEPENDENCIES}
    vgmstream = extract(pin, work, cache, sources, acquire)
    env['PKG_CONFIG_LIBDIR'] = str(prefix / 'lib/pkgconfig')
    env['PKG_CONFIG_PATH'] = ''
    for name in ('libogg-1.3.5', 'libvorbis-1.3.7', 'opus-1.6.1'):
        destination = work / (name + '-build')
        options = cmake_options(prefix)
        if name.startswith('libogg'):
            options += ['-DINSTALL_DOCS=OFF', '-DBUILD_TESTING=OFF']
        elif name.startswith('libvorbis'):
            options += ['-DOGG_LIBRARY=' + str(prefix / 'lib/libogg.a'),
                        '-DOGG_INCLUDE_DIR=' + str(prefix / 'include')]
        else:
            options += ['-DOPUS_BUILD_PROGRAMS=OFF', '-DOPUS_BUILD_TESTING=OFF',
                        '-DOPUS_BUILD_SHARED_LIBRARY=OFF']
        log = work / (name + '-build.log')
        run(['cmake', '-S', paths[name], '-B', destination, *options], work, env, log)
        run(['cmake', '--build', destination, '--parallel', jobs], work, env, log)
        run(['cmake', '--install', destination], work, env, log)
    for name, options in (
        ('mpg123-1.33.7', ['--disable-components', '--enable-libmpg123', '--disable-modules']),
        ('speex-1.2.1', ['--disable-binaries']),
    ):
        log = work / (name + '-build.log')
        run([shell, './configure', '--prefix=' + str(prefix), '--libdir=' + str(prefix / 'lib'),
             '--disable-shared', '--enable-static', '--with-pic', *options], paths[name], env, log)
        run(['make', '-j' + str(jobs)], paths[name], env, log)
        run(['make', 'install'], paths[name], env, log)
    # Historical CELT bitstreams need both exact ABIs. Keep upstream's symbol
    # namespacing/ecintrin fix, and its retained config scripts for Apple arm64.
    for name in ('celt-0.6.1', 'celt-0.11.0'):
        for filename in ('config.guess', 'config.sub'):
            shutil.copyfile(vgmstream / 'cmake/autoconf' / filename, paths[name] / filename)
    return vgmstream, paths


def pinned_dependency_cmake():
    """No FindPackage fallback: all non-system link inputs are exact archives."""
    return '''# Toolkit adapter for the exact retained vgmstream source revision.
foreach(name mpg123 vorbisfile vorbis ogg avformat avcodec avutil swresample opus mp3lame speex)
  set(archive "${TOOLKIT_CODEC_PREFIX}/lib/lib${name}.a")
  if(NOT EXISTS "${archive}")
    message(FATAL_ERROR "Missing pinned static codec: ${name}")
  endif()
  add_library(${name} STATIC IMPORTED)
  set_target_properties(${name} PROPERTIES IMPORTED_LOCATION "${archive}")
endforeach()
set_target_properties(avformat PROPERTIES INTERFACE_LINK_LIBRARIES "avcodec;avutil")
set_target_properties(avcodec PROPERTIES INTERFACE_LINK_LIBRARIES "swresample;avutil;opus;mp3lame")
set_target_properties(swresample PROPERTIES INTERFACE_LINK_LIBRARIES "avutil")
set(MPG123_INCLUDE_DIR "${TOOLKIT_CODEC_PREFIX}/include")
set(VORBISFILE_INCLUDE_DIRS "${TOOLKIT_CODEC_PREFIX}/include")
set(FFMPEG_INCLUDE_DIRS "${TOOLKIT_CODEC_PREFIX}/include")
set(FFMPEG_COMPILE TRUE)
set(USE_FFMPEG_LIBOPUS ON)
foreach(name MPEG VORBIS FFMPEG SPEEX)
  set(${name}_SOURCE "(pinned static source)")
endforeach()
# Only CELT uses upstream's dependency build; acquisition is deliberately absent.
function(FetchDependency name)
  cmake_parse_arguments(ARGS "" "DIR" "" ${ARGN})
  if(NOT IS_DIRECTORY "${${name}_PATH}")
    message(FATAL_ERROR "Missing pinned CELT source: ${name}")
  endif()
  set(${name}_BIN "${VGM_BINARY_DIR}/dependencies/${ARGS_DIR}" PARENT_SCOPE)
  set(${name}_SOURCE "(pinned source)" PARENT_SCOPE)
endfunction()
include(dependencies/celt)
'''


def adapt_vgmstream(source):
    path = source / 'CMakeLists.txt'
    text = path.read_text()
    old = 'include(FetchDependency)\n\n' + '\n'.join('include(dependencies/' + name + ')'
        for name in ('ffmpeg', 'mpg123', 'ogg', 'vorbis', 'libao', 'celt', 'speex', 'audacious'))
    if text.count(old) != 1:
        raise ValueError('Pinned vgmstream build structure changed; review the dependency adapter')
    adapt_celt_symbols(source / 'cmake/dependencies/celt.cmake')
    path.write_text(text.replace(old, 'include(toolkit-pinned-codecs)'), encoding='utf-8')
    (source / 'cmake/toolkit-pinned-codecs.cmake').write_text(pinned_dependency_cmake(), encoding='utf-8')


def adapt_celt_symbols(path):
    """Keep historical CELT exports separate from the modern Opus implementation.

    Both native linkers reported these two real duplicate exports. Extend the
    existing upstream per-ABI renaming, rather than changing link order or codecs.
    """
    text = path.read_text(encoding='utf-8')
    anchor = '\t\t\tcelt_encoder_create\n'
    lists = re.findall(r'set\(CELT_CFLAGS\s+(.*?)\n\s*\)', text, re.DOTALL)
    if (len(lists) != 1 or text.count(anchor) != 1 or
            any(name in lists[0].split() for name in CELT_OPUS_COLLISIONS)):
        raise ValueError('Pinned CELT namespace structure changed; review the symbol adapter')
    text = text.replace(anchor, anchor + ''.join('\t\t\t' + name + '\n' for name in CELT_OPUS_COLLISIONS))
    path.write_text(text, encoding='utf-8')


def validate_celt_symbols(text):
    # Mach-O nm adds a leading underscore; ELF does not. Inspect defined global
    # exports, not compiler flags, to prove the colliding symbols were renamed.
    symbols = [line.split()[-1].removeprefix('_') for line in text.splitlines() if line.split()]
    expected = [name + '_0110' for name in CELT_OPUS_COLLISIONS]
    if any(name in symbols for name in CELT_OPUS_COLLISIONS) or any(symbols.count(name) != 1 for name in expected):
        raise ValueError('Historical CELT exports still collide with Opus or are missing')
    return expected


def inspect_celt_symbols(destination):
    archive = destination / 'dependencies/celt-0110/libcelt/.libs/libcelt0.a'
    flags = ['-gU'] if sys.platform == 'darwin' else ['-g', '--defined-only']
    result = subprocess.run(['nm', *flags, str(archive)], capture_output=True, text=True, check=True, timeout=30)
    return validate_celt_symbols(result.stdout)


def verify_features(commands):
    compiled = [entry for entry in commands if entry['file'].replace('\\', '/').endswith('/src/vgmstream.c')]
    if not compiled:
        raise ValueError('Missing vgmstream compile evidence')
    for entry in compiled:
        command = entry.get('command', ' '.join(entry.get('arguments', [])))
        if any(not re.search(r'(?<!\w)-DVGM_USE_' + name + r'(?:\s|=1(?:\s|$)|$)', command) for name in FEATURES):
            raise ValueError('vgmstream compiled with missing codec capabilities')
    return list(FEATURES)


def verify_ffmpeg_features(source, ffmpeg):
    required = {}
    upstream = (source / 'ext_libs/extra/ffmpeg_options.txt').read_text()
    config = '\n'.join(path.read_text() for path in (ffmpeg / 'config.h', ffmpeg / 'config_components.h'))
    for kind, names in re.findall(r'^--enable-(decoder|demuxer|parser)=([^\r\n]+)', upstream, re.MULTILINE):
        required[kind] = sorted(names.split(','))
        for name in required[kind]:
            macro = 'CONFIG_' + name.upper() + '_' + kind.upper()
            if not re.search(r'^#define ' + macro + r' 1\s*$', config, re.MULTILINE):
                raise ValueError('FFmpeg is missing upstream vgmstream capability: ' + macro)
    if set(required) != {'decoder', 'demuxer', 'parser'}:
        raise ValueError('Pinned upstream FFmpeg feature contract changed')
    for name in ('GPL', 'NONFREE', 'VERSION3'):
        if not re.search(r'^#define CONFIG_' + name + r' 0\s*$', config, re.MULTILINE):
            raise ValueError('Unexpected POSIX FFmpeg licensing configuration')
    return required


def inspect_dynamic_dependencies(binary, system=None):
    system = system or sys.platform
    command = ['otool', '-L', str(binary)] if system == 'darwin' else ['readelf', '-d', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
    return validate_dynamic_dependencies(result.stdout, system)


def validate_dynamic_dependencies(text, system):
    if system == 'darwin':
        dependencies = [line.strip().split(' (', 1)[0] for line in text.splitlines()[1:] if line.strip()]
        if not dependencies or any(not (name.startswith('/usr/lib/') or name.startswith('/System/Library/Frameworks/'))
                                   or '..' in Path(name).parts for name in dependencies):
            raise ValueError('Codec binary depends on an unbundled non-system macOS library')
    elif system == 'linux':
        dependencies = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', text)
        if not dependencies or set(dependencies) - OS_ELF_LIBRARIES or re.search(r'\((?:RPATH|RUNPATH)\)', text):
            raise ValueError('Codec binary depends on an unbundled library or build-host search path')
    else:
        raise ValueError('Unsupported POSIX codec target')
    return sorted(set(dependencies))


def build_vgmstream(source, paths, prefix, work, root, sources, env, jobs, run):
    adapt_vgmstream(source)
    destination = work / 'vgmstream-build'
    options = cmake_options(prefix) + ['-DBUILD_CLI=ON', '-DBUILD_V123=OFF', '-DBUILD_AUDACIOUS=OFF',
        '-DBUILD_STATIC=OFF', '-DTOOLKIT_CODEC_PREFIX=' + str(prefix),
        '-DCELT_0061_PATH=' + str(paths['celt-0.6.1']), '-DCELT_0110_PATH=' + str(paths['celt-0.11.0'])]
    options += ['-DUSE_' + name + '=ON' for name in FEATURES]
    log = work / 'vgmstream-build.log'
    run(['cmake', '-S', source, '-B', destination, *options], work, env, log)
    run(['cmake', '--build', destination, '--target', 'CELT_0110_MAKE', '--parallel', jobs], work, env, log)
    celt_symbols = inspect_celt_symbols(destination)
    run(['cmake', '--build', destination, '--target', 'vgmstream_cli', '--parallel', jobs], work, env, log)
    features = verify_features(json.loads((destination / 'compile_commands.json').read_text()))
    binary = root / 'vgmstream-cli'
    shutil.copy2(destination / 'cli/vgmstream-cli', binary)
    dependencies = {name: inspect_dynamic_dependencies(root / name) for name in ('ffmpeg', 'vgmstream-cli')}
    retained = {'schema': 'toolkit-posix-codec-build-v1', 'features': features,
                'celt_opus_separate_exports': celt_symbols,
                'linkage': 'static-codec-libraries-system-runtime-only', 'system_libraries': dependencies}
    (sources / 'vgmstream-native-configuration.json').write_text(json.dumps(retained, indent=2) + '\n', encoding='utf-8')
    shutil.copyfile(source / 'cmake/toolkit-pinned-codecs.cmake', sources / 'toolkit-pinned-codecs.cmake')
    shutil.copyfile(source / 'cmake/dependencies/celt.cmake', sources / 'toolkit-celt.cmake')
    shutil.copyfile(__file__, sources / 'audio_runtime_posix.py')
    (sources / 'POSIX-REBUILD.txt').write_text(
        'The complete unmodified source archives for the CLI and every codec are retained here.\n'
        'Use the Game Immersion Toolkit source revision identified by the enclosing distribution provenance.\n'
        'Place these archives in an empty cache directory and run scripts/build-audio-runtime.py with\n'
        '--work <fresh-directory-without-spaces> --output <fresh-directory> --cache <cache> --shell /bin/sh.\n'
        'The build host needs a C/C++ compiler, make, CMake and pkg-config; users of the output do not.\n'
        'build-audio-runtime.py and audio_runtime_posix.py here are the exact build recipes.\n'
        'The adapter changes dependency acquisition/linking and adds two missing CELT encoder symbol\n'
        'namespaces to avoid collisions with Opus. Both historical CELT ABIs and all\n'
        'upstream vgmstream audio features are retained. It copies the upstream config.guess/config.sub\n'
        'into the two CELT sources for current host detection. CELT symbol namespacing and ecintrin.h\n'
        'replacement are performed by the retained upstream cmake/dependencies/celt.cmake recipe.\n'
        'toolkit-celt.cmake is the exact patched recipe; the built CELT exports are checked with nm.\n'
        'All codec libraries link statically into the separate CLI, with only base OS libraries dynamic.\n'
        'To rebuild/relink with modified libraries, modify their sources and update the source hash pins\n'
        'in your source checkout. A modified local build is not the original verified distribution.\n', encoding='utf-8')
    for name in ('COPYING', 'README.md', 'USAGE.md'):
        shutil.copyfile(source / name, root / name)
    shutil.copytree(source / 'ext_libs/licenses', root / 'vgmstream-licenses')
    return retained
