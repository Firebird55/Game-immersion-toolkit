"""Check an actual candidate APK as data, including nested Python native modules."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile


def native(data, abi):
    if data[:6] != b'\x7fELF\x02\x01' or len(data) < 64:
        raise ValueError('Not an Android ELF64 library')
    machine = struct.unpack_from('<H', data, 18)[0]
    if machine != {'arm64-v8a': 183, 'x86_64': 62}[abi]:
        raise ValueError('Wrong Android ABI')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or not 0 < count <= 64 or offset + size * count > len(data):
        raise ValueError('Invalid ELF program headers')
    loads = [struct.unpack_from('<Q', data, offset + size * i + 48)[0] for i in range(count)
             if struct.unpack_from('<I', data, offset + size * i)[0] == 1]
    if not loads or min(loads) < 16384:
        raise ValueError('The native library does not support 16-KiB pages')
    return {'machine': machine, 'minimum_load_alignment': min(loads), 'sha256': hashlib.sha256(data).hexdigest()}


def verify(path):
    result, abis, python_abis = {}, set(), set()
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None or len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError('Corrupt or duplicate APK members')
        for required in ('AndroidManifest.xml', 'classes.dex', 'assets/core-source-manifest.json', 'assets/reader.bundle'):
            if required not in archive.namelist():
                raise ValueError('Incomplete native/shared-reader APK')
        for name in archive.namelist():
            if name.startswith('lib/') and name.endswith('.so'):
                abi = name.split('/')[1];abis.add(abi)
                result[name] = native(archive.read(name), abi)
            if name.startswith('assets/chaquopy/requirements-') and name.endswith('.imy'):
                abi = name.removeprefix('assets/chaquopy/requirements-').removesuffix('.imy')
                if abi not in {'arm64-v8a', 'x86_64'}:
                    continue
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as requirements:
                    for member in requirements.namelist():
                        if member.endswith('.so'):
                            result[name + '/' + member] = native(requirements.read(member), abi)
                            if '/_pydantic_core' in member:
                                python_abis.add(abi)
        if abis != {'arm64-v8a', 'x86_64'} or python_abis != abis:
            raise ValueError('Both full Android core ABIs are required')
        core = json.loads(archive.read('assets/core-source-manifest.json'))
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/reader.bundle'))) as reader:
            frontend = json.loads(reader.read('desktop-manifest.json'))
            actual_web = {name for name in reader.namelist() if name != 'desktop-manifest.json'}
            if len(reader.namelist()) != len(actual_web) + 1 or actual_web != set(frontend['files']):
                raise ValueError('The APK reader inventory differs from the shared frontend')
            for name, expected in frontend['files'].items():
                value = reader.read(name)
                if len(value) != expected['bytes'] or hashlib.sha256(value).hexdigest() != expected['sha256']:
                    raise ValueError('A packaged shared reader resource changed')
    return {'schema': 'toolkit-android-apk-audit-v1', 'apk_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'apk_bytes': Path(path).stat().st_size, 'abis': sorted(abis), 'native_files': result,
        'core_sources': core, 'frontend_build_id': frontend['build_id'],
        'target_runtime_acceptance': 'not-established-by-archive-validation', 'release_eligibility': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verify(args.apk), sort_keys=True, indent=2) + '\n', encoding='utf8')
