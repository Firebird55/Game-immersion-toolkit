"""Build the isolated Wwise Vorbis C decoder with already authenticated software inputs."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links

SOURCE_POLICY = ROOT / 'packaging/codecs/audio-runtime.json'
OWNED = ROOT / 'packaging/android/zzz-wem'
NAME = 'libtoolkit_zzz_wem.so'
ABI_TARGETS = {'arm64-v8a': 'aarch64-linux-android24', 'x86_64': 'x86_64-linux-android24'}
VGM_FILES = ('coding/vorbis_custom_utils.c', 'coding/vorbis_custom_utils_wwise.c',
             'util/reader_put.c', 'util/vorbis_codebooks.c')
VORBIS_FILES = ('mdct', 'smallft', 'block', 'envelope', 'window', 'lsp', 'lpc', 'analysis', 'synthesis', 'psy',
                'info', 'floor1', 'floor0', 'res0', 'mapping0', 'registry', 'codebook', 'sharedbook', 'lookup', 'bitrate')


def digest(path):
    _no_links(path)
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location('zzz_wem_' + name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def inputs(source, output):
    policy = json.loads(SOURCE_POLICY.read_bytes())['vgmstream']
    wanted = ('libogg-1.3.5.tar.xz', 'libvorbis-1.3.7.tar.xz')
    records = {row['archive']: row for row in policy['dependency_sources'] if row['archive'] in wanted}
    if set(records) != set(wanted):
        raise ValueError('Missing reviewed Xiph source inputs')
    output.mkdir()
    identities = {}
    for row in (policy, *(records[name] for name in wanted)):
        archive = source / row['archive']
        _no_links(archive)
        size = archive.stat().st_size
        if not 0 < size <= 32 * 1024**2 or size != row.get('bytes', size):
            raise ValueError('A retained Wwise codec source archive differs from its pin')
        with archive.open('rb') as stream:
            raw = stream.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('A retained Wwise codec source archive differs from its pin')
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as tar:
            members = tar.getmembers()
            if (not 0 < len(members) <= 4096 or sum(member.size for member in members) > 128 * 1024**2
                    or len({member.name for member in members}) != len(members)
                    or any(member.name.split('/')[0] != row['directory']
                           or not (member.isfile() or member.isdir()) for member in members)):
                raise ValueError('Unexpected codec source archive inventory')
            tar.extractall(output, members, filter='data')
        identities[row['archive']] = row['sha256']
    vgm = output / policy['directory']
    ogg, vorbis = (output / records[name]['directory'] for name in wanted)
    return vgm, ogg, vorbis, identities


def configure_ogg(ogg, output):
    # Exact upstream config_types.h.in with the standard Android NDK widths.
    generated = output / 'include'
    target = generated / 'ogg/config_types.h'
    target.parent.mkdir(parents=True)
    raw = (ogg / 'include/ogg/config_types.h.in').read_text(encoding='utf8')
    values = {f'INCLUDE_{name}_H': '1' for name in ('INTTYPES', 'STDINT', 'SYS_TYPES')}
    for bits in (16, 32, 64):
        values[f'SIZE{bits}'] = f'int{bits}_t'
        values[f'USIZE{bits}'] = f'uint{bits}_t'
    for name, value in values.items():
        token = '@' + name + '@'
        if raw.count(token) != 1:
            raise ValueError('The reviewed libogg build template changed')
        raw = raw.replace(token, value)
    target.write_text(raw, encoding='utf8', newline='\n')
    return generated


def build(suppliers, ndk, ndk_archive, output):
    suppliers, ndk, ndk_archive, output = [Path(value).absolute() for value in (suppliers, ndk, ndk_archive, output)]
    for path in (suppliers, ndk, ndk_archive, output):
        _no_links(path)
    if output.exists():
        raise ValueError('Choose a fresh private Wwise codec build directory')
    toolchain = module('build-android-python-dependencies')
    pins = json.loads(toolchain.POLICY.read_bytes())
    ndk_inventory = toolchain.verify_ndk(ndk, ndk_archive, pins['ndk'])
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    suffix = '.exe' if os.name == 'nt' else ''
    tools = ndk / 'toolchains/llvm/prebuilt' / host / 'bin'
    clang, readelf = tools / ('clang' + suffix), tools / ('llvm-readelf' + suffix)
    audit = module('verify-android-apk')
    output.mkdir(parents=True)
    vgm, ogg, vorbis, source_sha256 = inputs(suppliers, output / 'source')
    generated = configure_ogg(ogg, output)
    names = [OWNED / 'zzz_wem.c', *(vgm / 'src' / name for name in VGM_FILES), ogg / 'src/bitwise.c',
             *(vorbis / 'lib' / (name + '.c') for name in VORBIS_FILES)]
    includes = ['-I' + str(path) for path in (generated, vgm / 'src', ogg / 'include', vorbis / 'include')]
    exports = {'zzz_wem_open', 'zzz_wem_read', 'zzz_wem_close'}
    owned = (OWNED / 'zzz_wem.h', OWNED / 'zzz_wem.c', Path(__file__))
    recipe = {path.name: digest(path) for path in owned}
    libraries = {}
    for abi, target in ABI_TARGETS.items():
        lib = output / 'jniLibs' / abi / NAME
        lib.parent.mkdir(parents=True)
        flags = ['--target=' + target, '-std=gnu11', '-DVGM_USE_VORBIS=1', '-O2', '-shared', '-fPIC',
                 '-fvisibility=hidden', '-ffunction-sections', '-fdata-sections', '-fno-ident',
                 '-Wl,--gc-sections', '-Wl,--as-needed', '-Wl,-z,defs', '-Wl,-z,max-page-size=16384',
                 '-Wl,-z,common-page-size=16384', '-Wl,-soname,' + NAME, '-ffile-prefix-map=' + str(ROOT) + '=/toolkit']
        subprocess.run([str(clang), *flags, *includes, *map(str, names), '-lm', '-o', str(lib)],
                       cwd=output, check=True, timeout=90)
        raw = lib.read_bytes()
        if not 0 < len(raw) <= 1024 * 1024:
            raise ValueError('The Wwise Vorbis library exceeds its packaged limit')
        contract = toolchain.elf_contract(raw, pins['targets'][abi]['elf_machine'], expected_dependencies=('libm.so', 'libc.so'))
        symbols = subprocess.run([str(readelf), '--dyn-syms', '--wide', str(lib)], check=True, capture_output=True,
                                 text=True, timeout=10).stdout
        actual = {line.split()[-1] for line in symbols.splitlines() if re.search(r'\bGLOBAL\s+DEFAULT\b', line)
                  and ' UND ' not in line}
        if actual != exports:
            raise ValueError('The Wwise Vorbis library exposes an unexpected API')
        libraries[abi] = {**audit.native(raw, abi), 'bytes':len(raw), 'needed':contract['needed'], 'exports':sorted(actual)}
    notices = {}
    for name, source in (('vgmstream', vgm), ('libogg', ogg), ('libvorbis', vorbis)):
        target = output / 'notices' / (name + '-COPYING')
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source / 'COPYING', target)
        notices[target.name] = digest(target)
    if recipe != {path.name: digest(path) for path in owned}:
        raise ValueError('The Wwise Vorbis recipe changed during compilation')
    receipt = {'schema':'toolkit-android-zzz-wem-link-v1', 'source_sha256':source_sha256, 'notices_sha256':notices,
               'owned_sha256':recipe,
               'ndk_inventory_sha256':ndk_inventory, 'compiler_sha256':digest(clang), 'libraries':libraries,
               'api':24, 'target_runtime_acceptance':'pending', 'apk_delivery':'pending'}
    (output / 'link-receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('suppliers', 'ndk', 'ndk-archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.suppliers, args.ndk, args.ndk_archive, args.output)
    print(json.dumps(result['libraries'], sort_keys=True))
