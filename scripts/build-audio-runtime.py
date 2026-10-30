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
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.native_codecs import PREFIX, SCHEMA, host_target
from backend.runtime_bundle import relative_resource

PIN_FILE = ROOT / 'packaging/codecs/audio-runtime.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def acquire(pin, cache):
    path = cache / pin['archive']
    if not path.exists():
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1', 'Accept': 'application/octet-stream'})
        with urllib.request.urlopen(request, timeout=90) as response, path.open('xb') as target:
            shutil.copyfileobj(response, target)
    if digest(path) != pin['sha256']:
        raise ValueError('Source archive checksum differs: ' + pin['archive'])
    return path


def run(args, cwd, env, log):
    with log.open('ab') as output:
        subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


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
    for variable in ('CFLAGS', 'CPPFLAGS', 'CXXFLAGS', 'LDFLAGS', 'CPATH', 'LIBRARY_PATH', 'PKG_CONFIG_LIBDIR', 'PKG_CONFIG_PATH', 'PATH_SEPARATOR'):
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
    run([shell, './configure', *flags], ffmpeg, env, work / 'ffmpeg-build.log')
    run([make, f'-j{jobs}', 'SHELL=' + make_shell], ffmpeg, env, work / 'ffmpeg-build.log')
    binary = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'
    shutil.copy2(ffmpeg / binary, root / binary)
    tools = {'ffmpeg': binary}
    shutil.copyfile(lame / 'COPYING', root / 'LAME-COPYING.txt')
    shutil.copyfile(lame / 'LICENSE', root / 'LAME-LICENSE.txt')
    shutil.copyfile(ffmpeg / 'COPYING.LGPLv2.1', root / 'FFmpeg-COPYING.txt')
    shutil.copyfile(ffmpeg / 'LICENSE.md', root / 'FFmpeg-LICENSE.md')
    if toolchain:
        shutil.copyfile(toolchain / 'COPYING.MinGW-w64-runtime.txt', root / 'MinGW-runtime-COPYING.txt')
    # The currently published macOS binary depends on Homebrew absolute paths;
    # Linux's static binary has an additional GPL closure. Neither is mislabeled
    # as a portable BSD-only package. Supply a native reviewed build later.
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
        components.append({'name': 'vgmstream', **pin})
        tools['vgmstream'] = 'vgmstream-cli.exe'
    shutil.copyfile(__file__, sources / 'build-audio-runtime.py')
    shutil.copyfile(PIN_FILE, sources / 'audio-runtime.json')
    (root / 'NOTICE.txt').write_text('Maintained audio tools for Game Immersion Toolkit.\n'
        'FFmpeg 9.0.2: LGPL-2.1-or-later; LAME 4.0: LGPL-2.0-or-later.\n'
        'Unmodified source archives, exact source hashes and build recipe are in sources/.\n'
        'Audio-only FFmpeg disables network, autodetection and GPL/nonfree options.\n'
        'The application communicates with separate codec processes.\n'
        'Optional vgmstream carries its component notices. Its complete binary dependency source review is pending.\n', encoding='utf-8')
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
