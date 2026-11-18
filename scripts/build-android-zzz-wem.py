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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links

SOURCE_POLICY = ROOT / 'packaging/codecs/audio-runtime.json'
OWNED = ROOT / 'packaging/android/zzz-wem'
NAME = 'libtoolkit_zzz_wem.so'
CONTRACT = 'toolkit-zzz-wem-pcm-v1'
MANIFEST = 'assets/zzz-wem-manifest.json'
LICENSE = 'assets/zzz-wem-licenses/'
ABI_TARGETS = {'arm64-v8a': 'aarch64-linux-android24', 'x86_64': 'x86_64-linux-android24'}
EXPORTS = {'zzz_wem_open', 'zzz_wem_read', 'zzz_wem_close',
           *('Java_io_github_firebird55_gameimmersiontoolkit_ZzzWemCodec_' + name
             for name in ('nativeProof', 'nativeOpen', 'nativeRead', 'nativeClose'))}
NOTICES = {
    'libogg-COPYING': 'd2ab5758336489da61c12cc5bb757da5339c4ae9001f9bb0562b4370249af814',
    'libvorbis-COPYING': 'ec1815db59fcd302846df949d7424876cb2e2dc5ed1606c5fb0b36787b1cf43a',
    'vgmstream-COPYING': 'fcc26d35c4c4365e31f21734f846e4ee362ff0b57ba696085605a7b4768d8763',
}
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


def source_policy():
    policy = json.loads(SOURCE_POLICY.read_bytes())['vgmstream']
    wanted = ('libogg-1.3.5.tar.xz', 'libvorbis-1.3.7.tar.xz')
    records = {row['archive']: row for row in policy['dependency_sources'] if row['archive'] in wanted}
    if set(records) != set(wanted):
        raise ValueError('Missing reviewed Xiph source inputs')
    return (policy, *(records[name] for name in wanted))


def recipe():
    names = ('zzz_wem.h', 'zzz_wem.c', 'zzz_wem_jni.c')
    sources = [*(OWNED / name for name in names), Path(__file__),
               ROOT / 'backend/android_zzz_wem.py', ROOT / 'backend/zzz_wav_codec.py',
               ROOT / 'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/ZzzWemCodec.java']
    return {path.name: hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for path in sources}


def inputs(source, output):
    policies = source_policy()
    output.mkdir()
    identities = {}
    for row in policies:
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
    vgm, ogg, vorbis = (output / row['directory'] for row in policies)
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
    names = [OWNED / 'zzz_wem.c', OWNED / 'zzz_wem_jni.c', *(vgm / 'src' / name for name in VGM_FILES), ogg / 'src/bitwise.c',
             *(vorbis / 'lib' / (name + '.c') for name in VORBIS_FILES)]
    includes = ['-I' + str(path) for path in (generated, vgm / 'src', ogg / 'include', vorbis / 'include')]
    owned = recipe()
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
        if actual != EXPORTS:
            raise ValueError('The Wwise Vorbis library exposes an unexpected API')
        libraries[abi] = {**audit.native(raw, abi), 'bytes':len(raw), 'needed':contract['needed'], 'exports':sorted(actual)}
    notices = {}
    for name, source in (('vgmstream', vgm), ('libogg', ogg), ('libvorbis', vorbis)):
        target = output / LICENSE / (name + '-COPYING')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / 'COPYING', target)
        notices[target.name] = digest(target)
    if owned != recipe() or notices != NOTICES:
        raise ValueError('The Wwise Vorbis recipe changed during compilation')
    receipt = {'schema':'toolkit-android-zzz-wem-link-v2', 'contract':CONTRACT,
               'source_sha256':source_sha256, 'notices_sha256':notices, 'owned_sha256':owned,
               'ndk_inventory_sha256':ndk_inventory, 'compiler_sha256':digest(clang), 'libraries':libraries,
               'api':24, 'max_wem_bytes':64 * 1024**2, 'max_frames_per_read':4096}
    (output / MANIFEST).write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf8', newline='\n')
    verify_bundle(output)
    return receipt


def verify_apk(archive):
    entries = [name for name in archive.namelist() if name == MANIFEST or name.startswith(LICENSE) and not name.endswith('/')
               or name.endswith('/' + NAME)]
    if not entries:
        return {'present': False}
    expected = {MANIFEST, *(LICENSE + name for name in NOTICES), *('lib/' + abi + '/' + NAME for abi in ABI_TARGETS)}
    if set(entries) != expected or len(entries) != len(expected):
        raise ValueError('The Android ZZZ WEM software namespace is incomplete')

    def read(name, limit):
        info = archive.getinfo(name)
        if not 0 < info.file_size <= limit:
            raise ValueError('A packaged Wwise Vorbis software member is outside its bound')
        return archive.read(info)

    raw = read(MANIFEST, 16384)
    receipt = json.loads(raw)
    trusted = {row['archive']: row['sha256'] for row in source_policy()}
    if (receipt.get('schema') != 'toolkit-android-zzz-wem-link-v2' or receipt.get('contract') != CONTRACT
            or receipt.get('api') != 24 or receipt.get('max_wem_bytes') != 64 * 1024**2
            or receipt.get('max_frames_per_read') != 4096 or receipt.get('source_sha256') != trusted
            or receipt.get('notices_sha256') != NOTICES or receipt.get('owned_sha256') != recipe()
            or any(not re.fullmatch('[0-9a-f]{64}', receipt.get(name, '')) for name in ('compiler_sha256', 'ndk_inventory_sha256'))
            or set(receipt.get('libraries', {})) != set(ABI_TARGETS)):
        raise ValueError('The packaged Android ZZZ WEM software receipt differs from the recipe')
    for name, expected_hash in NOTICES.items():
        if hashlib.sha256(read(LICENSE + name, 16384)).hexdigest() != expected_hash:
            raise ValueError('A packaged Wwise Vorbis notice changed')
    tools = module('build-android-python-dependencies')
    audit = module('verify-android-apk')
    for abi, machine in (('arm64-v8a', 183), ('x86_64', 62)):
        name = 'lib/' + abi + '/' + NAME
        artifact = read(name, 1024**2)
        native = audit.native(artifact, abi)
        linkage = tools.elf_contract(artifact, machine, expected_dependencies=('libc.so', 'libm.so'))
        if archive.getinfo(name).compress_type != zipfile.ZIP_STORED or receipt['libraries'][abi] != {
                **native, 'bytes':len(artifact), 'needed':linkage['needed'], 'exports':sorted(EXPORTS)}:
            raise ValueError('The Android ZZZ WEM ABI members differ from their receipt')
    return {'present': True, 'manifest_sha256':hashlib.sha256(raw).hexdigest(), 'libraries':receipt['libraries']}


def verify_bundle(output):
    output = Path(output).absolute()
    _no_links(output)
    expected = {MANIFEST, *(LICENSE + name for name in NOTICES), *('jniLibs/' + abi + '/' + NAME for abi in ABI_TARGETS)}
    actual = set()
    for folder in ('assets', 'jniLibs'):
        for path in (output / folder).rglob('*'):
            _no_links(path)
            if path.is_file():
                actual.add(path.relative_to(output).as_posix())
    if actual != expected:
        raise ValueError('The staged Wwise Vorbis APK namespace differs from the reviewed closure')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name in sorted(actual):
            item = output / name
            if not 0 < item.stat().st_size <= 1024**2:
                raise ValueError('A staged Wwise Vorbis asset is outside its bound')
            archive.writestr(name.replace('jniLibs/', 'lib/', 1), item.read_bytes())
    with zipfile.ZipFile(buffer) as archive:
        return verify_apk(archive)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('suppliers', 'ndk', 'ndk-archive', 'output', 'verify'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    if args.download:
        if not args.suppliers or args.verify:
            parser.error('Use --download with a private supplier directory')
        _no_links(args.suppliers.absolute())
        args.suppliers.mkdir(parents=True, exist_ok=True)
        acquire = module('build-audio-runtime').acquire
        for pin in source_policy():
            acquire(pin, args.suppliers)
        if not any((args.ndk, args.ndk_archive, args.output)):
            sys.exit(0)
    if args.verify and not any((args.suppliers, args.ndk, args.ndk_archive, args.output)):
        result = verify_bundle(args.verify)
    elif not args.verify and all((args.suppliers, args.ndk, args.ndk_archive, args.output)):
        result = build(args.suppliers, args.ndk, args.ndk_archive, args.output)
    else:
        parser.error('Pass --verify or all four native build paths')
    print(json.dumps(result['libraries'], sort_keys=True))
