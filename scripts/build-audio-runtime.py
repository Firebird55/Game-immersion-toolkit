"""Build maintained audio-only FFmpeg and collect verified native codec resources.

Run dev:doctor before preparing the build environment. The build host needs a C
compiler, make, pkg-config and a POSIX shell. These never go into the application.
Windows uses the separately verified w64devkit and Git's build shell. Source
archives and this recipe are retained alongside the output for redistribution
review; construction does not mark the enclosing application release approved.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.native_codecs import PREFIX, SCHEMA, host_target
from backend.runtime_bundle import relative_resource
from scripts.audio_runtime_posix import prepare_dependencies, build_vgmstream, verify_ffmpeg_features

PIN_FILE = ROOT / 'packaging/codecs/audio-runtime.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def acquire(pin, cache):
    path = cache / pin['archive']
    if path.exists():
        if digest(path) != pin['sha256']:
            raise ValueError('Source archive checksum differs: ' + pin['archive'])
        return path
    for attempt in range(3):
        temporary = cache / (pin['archive'] + '.partial-' + uuid.uuid4().hex)
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1', 'Accept': 'application/octet-stream'})
        try:
            print(f"Downloading {pin['archive']} (attempt {attempt + 1}/3)", flush=True)
            with urllib.request.urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=60) as response, temporary.open('xb') as target:
                shutil.copyfileobj(response, target)
            if digest(temporary) != pin['sha256']:
                raise ValueError('Source archive checksum differs: ' + pin['archive'])
            temporary.replace(path)
            return path
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (urllib.error.URLError, OSError, http.client.IncompleteRead):
            if attempt == 2:
                raise
        finally:
            temporary.unlink(missing_ok=True)
        time.sleep(2 ** attempt)


def run(args, cwd, env, log):
    try:
        with log.open('ab') as output:
            subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
    except subprocess.CalledProcessError as error:
        # Hosted build work directories are ephemeral. Surface the actual compiler
        # failure while keeping local checkout/profile prefixes out of public logs.
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 32768))
            tail = stream.read().decode('utf-8', errors='replace')
        prefixes = {str(ROOT), str(log.parent), str(cwd), *[value for name, value in os.environ.items()
            if name.lower() in {'home', 'userprofile', 'temp', 'tmp', 'runner_workspace', 'github_workspace'} and value]}
        for prefix in sorted(prefixes, key=len, reverse=True):
            tail = tail.replace(prefix, '<build>').replace(prefix.replace('\\', '/'), '<build>')
        tail = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', tail)
        tail = '\n'.join(tail.splitlines()[-80:])[-12000:]
        print(f'Codec build failed ({log.name}, exit {error.returncode}):\n{tail}', file=sys.stderr, flush=True)
        raise RuntimeError(f'Codec build failed in {log.name}; see the sanitized compiler output above') from None


def short_windows_path(path):
    import ctypes
    value = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), value, len(value)):
        raise ValueError('Build shell needs a path without spaces')
    return value.value.replace('\\', '/')


def build(work, output, cache, shell, toolchain=None, windows_vgmstream=False, jobs=4):
    if work.exists() or output.exists():
        raise ValueError('Choose fresh build and resource output directories')
    for path in (work, output, cache):
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() or (ancestor.exists() and getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('Build directories cannot traverse links')
    if any(c.isspace() for c in str(work)):
        raise ValueError('The upstream codec build tools need a scratch path without spaces')
    work.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=True)
    root = output / PREFIX
    root.mkdir(parents=True)
    sources = root / 'sources'
    sources.mkdir()
    pins = json.loads(PIN_FILE.read_text())
    env = dict(os.environ)
    if toolchain:
        env['PATH'] = str(shell.parent) + os.pathsep + str(toolchain / 'bin') + os.pathsep + env.get('PATH', '')
    for variable in ('CFLAGS', 'CPPFLAGS', 'CXXFLAGS', 'LDFLAGS', 'CPATH', 'LIBRARY_PATH', 'PKG_CONFIG_LIBDIR', 'PKG_CONFIG_PATH', 'PATH_SEPARATOR', 'CMAKE_PREFIX_PATH', 'CMAKE_MODULE_PATH'):
        env.pop(variable, None)
    env['CONFIG_SHELL'] = '/usr/bin/sh' if sys.platform == 'win32' else str(shell)
    make = str(toolchain / 'bin/make.exe') if toolchain else 'make'
    make_shell = short_windows_path(shell) if sys.platform == 'win32' else str(shell)
    components = []
    for name in ('lame', 'ffmpeg'):
        pin = pins[name]
        archive = acquire(pin, cache)
        with tarfile.open(archive) as source:
            source.extractall(work, filter='data')
        shutil.copyfile(archive, sources / pin['archive'])
        components.append({'name': name, **pin})
    lame = work / pins['lame']['directory']
    ffmpeg = work / pins['ffmpeg']['directory']
    prefix = work / 'prefix'
    (prefix / 'include/lame').mkdir(parents=True)
    (prefix / 'lib').mkdir()
    posix = sys.platform in {'linux', 'darwin'}
    if posix:
        vgmstream, dependency_paths = prepare_dependencies(pins, work, prefix, cache, sources,
            env, shell, jobs, acquire, run)
    lame_options = ['--prefix=/toolkit-codecs', '--disable-shared', '--enable-static', '--disable-decoder',
                    '--disable-frontend', '--disable-gtktest', '--disable-nasm', 'CFLAGS=-O2 -fPIC']
    if sys.platform == 'win32': lame_options += ['--host=x86_64-w64-mingw32']
    run([shell, './configure', *lame_options], lame, env, work / 'lame-build.log')
    run([make, f'-j{jobs}', 'SHELL=' + make_shell], lame, env, work / 'lame-build.log')
    shutil.copyfile(lame / 'libmp3lame/.libs/libmp3lame.a', prefix / 'lib/libmp3lame.a')
    shutil.copyfile(lame / 'include/lame.h', prefix / 'include/lame/lame.h')
    flags = ['--prefix=../prefix', '--disable-debug', '--disable-doc', '--disable-autodetect', '--disable-everything',
        '--disable-network', '--disable-avdevice', '--disable-swscale', '--disable-ffplay', '--disable-ffprobe',
        '--disable-x86asm', '--enable-static', '--disable-shared', '--enable-ffmpeg', '--enable-libmp3lame',
        '--enable-protocol=file,pipe', '--enable-encoder=libmp3lame,pcm_s16le,flac', '--enable-muxer=mp3,wav,pcm_s16le,flac',
        '--enable-demuxer=wav,flac,mp3,ogg,aac,mov,asf,xwma,oma,ac3,eac3,smacker,bink,caf,mpc,mpc8,tak,ape,flv,voc,pcm_s16le',
        '--enable-decoder=pcm*,adpcm*,flac,vorbis,opus,mp3*,mp2*,aac*,ac3,eac3,wmapro,wmav1,wmav2,xma1,xma2,atrac3,atrac3p,smackaud,binkaudio_dct,binkaudio_rdft,mpc7,mpc8,alac,tak,ape',
        '--enable-parser=ac3,mpegaudio,xma,vorbis,opus,aac,flac',
        '--enable-filter=aformat,anull,aresample,atrim,asetpts,concat,amix,volume,adelay,afade,atempo,apad',
        '--extra-cflags=-I../prefix/include', '--extra-ldflags=-L../prefix/lib' + (' -static-libgcc' if sys.platform == 'win32' else '')]
    if sys.platform == 'win32': flags += ['--target-os=mingw32', '--arch=x86_64']
    if posix:
        # All vgmstream upstream audio formats remain enabled, including its
        # libopus implementation. Prefix discovery is restricted to our pins.
        flags += ['--prefix=' + str(prefix), '--enable-pic', '--pkg-config-flags=--static',
                  '--enable-libopus', '--enable-decoder=libopus', '--enable-encoder=libopus',
                  '--enable-muxer=ogg', '--enable-demuxer=spdif,xmv']
    run([shell, './configure', *flags], ffmpeg, env, work / 'ffmpeg-build.log')
    if posix:
        ffmpeg_capabilities = verify_ffmpeg_features(vgmstream, ffmpeg)
    run([make, f'-j{jobs}', 'SHELL=' + make_shell], ffmpeg, env, work / 'ffmpeg-build.log')
    if posix:
        run([make, 'install'], ffmpeg, env, work / 'ffmpeg-build.log')
    binary = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'
    shutil.copy2(ffmpeg / binary, root / binary)
    tools = {'ffmpeg': binary}
    shutil.copyfile(lame / 'COPYING', root / 'LAME-COPYING.txt')
    shutil.copyfile(lame / 'LICENSE', root / 'LAME-LICENSE.txt')
    shutil.copyfile(ffmpeg / 'COPYING.LGPLv2.1', root / 'FFmpeg-COPYING.txt')
    shutil.copyfile(ffmpeg / 'LICENSE.md', root / 'FFmpeg-LICENSE.md')
    if toolchain:
        shutil.copyfile(toolchain / 'COPYING.MinGW-w64-runtime.txt', root / 'MinGW-runtime-COPYING.txt')
    if posix:
        native_configuration = build_vgmstream(vgmstream, dependency_paths, prefix, work, root,
            sources, env, jobs, run)
        native_configuration['ffmpeg_capabilities'] = ffmpeg_capabilities
        (sources / 'vgmstream-native-configuration.json').write_text(json.dumps(native_configuration, indent=2) + '\n')
        components.append({'name': 'vgmstream', **pins['vgmstream'],
                           'build_method': 'native-pinned-sources', 'codec_linkage': 'static'})
        tools['vgmstream'] = 'vgmstream-cli'
    if windows_vgmstream:
        if host_target() != 'windows-x64': raise ValueError('This upstream artifact is Windows x64 only')
        pin = pins['vgmstream']
        archive = acquire(pin['windows_artifact'], cache)
        with zipfile.ZipFile(archive) as value:
            for item in value.infolist():
                name = relative_resource(item.filename)
                if '/' in name or item.is_dir(): raise ValueError('Unexpected vgmstream archive layout')
                if name == 'vgmstream-cli.exe' or name.endswith('.dll') or name in {'COPYING', 'README.md', 'USAGE.md'}:
                    (root / name).write_bytes(value.read(item))
        source = acquire(pin, cache)
        shutil.copyfile(source, sources / pin['archive'])
        with tarfile.open(source) as value:
            for member in value.getmembers():
                marker = '/ext_libs/licenses/'
                if member.isfile() and marker in member.name:
                    destination = root / 'vgmstream-licenses' / relative_resource(member.name.split(marker, 1)[1])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(value.extractfile(member).read())
        # The release's exact dependency versions are named by its retained
        # notices. Keep their complete sources, including LGPL libraries, with
        # the upstream build instructions and patches already in this archive.
        for dependency in pin['dependency_sources']:
            dependency_archive = acquire(dependency, cache)
            shutil.copyfile(dependency_archive, sources / dependency['archive'])
        import ctypes
        observed = {}
        with os.add_dll_directory(str(root.resolve())):
            for filename, api in [('avcodec-vgmstream-63.dll', 'avcodec'), ('avformat-vgmstream-63.dll', 'avformat'),
                                  ('avutil-vgmstream-61.dll', 'avutil'), ('swresample-vgmstream-7.dll', 'swresample')]:
                library = ctypes.CDLL(str((root / filename).resolve()))
                config = getattr(library, api + '_configuration'); config.restype = ctypes.c_char_p
                license = getattr(library, api + '_license'); license.restype = ctypes.c_char_p
                configuration, licensing = config().decode(), license().decode()
                if licensing != 'LGPL version 2.1 or later' or '--enable-gpl' in configuration or '--enable-nonfree' in configuration:
                    raise ValueError('Unexpected vgmstream FFmpeg build licensing or configuration')
                observed[filename] = {'configuration': configuration, 'license': licensing, 'sha256': digest(root / filename)}
        (sources / 'vgmstream-native-configuration.json').write_text(json.dumps(observed, indent=2) + '\n')
        components.append({'name': 'vgmstream', **pin})
        tools['vgmstream'] = 'vgmstream-cli.exe'
    shutil.copyfile(__file__, sources / 'build-audio-runtime.py')
    shutil.copyfile(ROOT / 'scripts/audio_runtime_posix.py', sources / 'audio_runtime_posix.py')
    shutil.copyfile(PIN_FILE, sources / 'audio-runtime.json')
    (root / 'NOTICE.txt').write_text('Maintained audio tools for Game Immersion Toolkit.\n'
        'FFmpeg 9.0.2: LGPL-2.1-or-later; LAME 4.0: LGPL-2.0-or-later.\n'
        'Unmodified source archives, exact source hashes and build recipe are in sources/.\n'
        'Audio-only FFmpeg disables network, autodetection and GPL/nonfree options.\n'
        'The application communicates with separate codec processes.\n'
        'vgmstream carries exact dependency sources, notices and rebuild instructions.\n'
        'Windows keeps replaceable LGPL DLLs beside the CLI. POSIX statically links the retained\n'
        'codec sources; all CLI/library sources and the adapter are provided for rebuilding/relinking.\n'
        'Reverse engineering for debugging modifications is permitted.\n', encoding='utf-8')
    files = {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob('*')) if p.is_file()}
    manifest = {'schema': SCHEMA, 'target': host_target(), 'tools': tools, 'files': files, 'components': components,
                'build_recipe_sha256': digest(__file__), 'native_decode_acceptance': 'not-run', 'redistribution_review': 'pending-exact-output'}
    (root / 'runtime.json').write_text(json.dumps(manifest, indent=2) + '\n')
    inventory = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)}
        for p in sorted(output.rglob('*')) if p.is_file()]
    (output / 'resource-manifest.json').write_text(json.dumps({'schema': 'toolkit-native-resources-v1',
        'components': components, 'build_recipe_sha256': digest(__file__), 'files': inventory}, indent=2) + '\n')
    print(json.dumps({'target': host_target(), 'tools': sorted(tools), 'release_eligible': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--shell', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--windows-vgmstream', action='store_true')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    build(args.work.absolute(), args.output.absolute(), args.cache.absolute(), args.shell.absolute(), args.toolchain, args.windows_vgmstream, min(16, max(1, args.jobs)))


if __name__ == '__main__': main()
