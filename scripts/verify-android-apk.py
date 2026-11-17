"""Check an actual candidate APK as data, including nested Python native modules."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import re
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


def verify_decoder(archive, native_files, repository):
    decoder = json.loads(archive.read('assets/native-decoder-manifest.json'))
    decoder_policy = json.loads((repository / 'packaging/android/native-decoders.json').read_text())
    compiler_policy = json.loads((repository / 'packaging/android/python-dependencies.json').read_text())
    recipe = {'policy_sha256': hashlib.sha256((repository / 'packaging/android/native-decoders.json').read_bytes()).hexdigest(),
        'transport_sha256': hashlib.sha256((repository / 'packaging/android/app/src/main/cpp/x64_decoder.c').read_bytes()).hexdigest(),
        'builder_sha256': hashlib.sha256((repository / 'scripts/build-android-data-decoders.py').read_bytes()).hexdigest(),
        'source_sha256': decoder_policy['capstone']['sha256'],
        'ndk_policy_sha256': hashlib.sha256(json.dumps(compiler_policy['ndk'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()}
    if (decoder.get('schema') != 'toolkit-android-native-decoders-v1'
            or decoder.get('source_sha256') != decoder_policy['capstone']['sha256']
            or decoder.get('version') != decoder_policy['capstone']['version']
            or decoder.get('source') != decoder_policy['capstone']['source']
            or decoder.get('ndk') != decoder_policy['ndk'] or decoder.get('api') != decoder_policy['api']
            or decoder.get('ndk_archive_sha256') != compiler_policy['ndk']['sha256']
            or not isinstance(decoder.get('ndk_inventory_sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', decoder['ndk_inventory_sha256'])
            or decoder.get('original_client_execution') is not False
            or decoder.get('recipe') != recipe
            or set(decoder.get('libraries', {})) != set(decoder_policy['abis'])):
        raise ValueError('The APK data decoder does not match its pinned owned software recipe')
    for abi, receipt in decoder['libraries'].items():
        name = 'lib/' + abi + '/' + decoder_policy['library']
        entry = archive.getinfo(name)
        if (receipt['entry'] != name or entry.file_size != receipt['bytes'] or entry.compress_type != zipfile.ZIP_STORED
                or native_files[name]['sha256'] != receipt['sha256']):
            raise ValueError('Packaged decoder bytes differ from their compiled receipt')
    expected_licenses = {'native-decoder-licenses/' + str(index) + '-' + Path(name).name
        for index, name in enumerate(decoder_policy['capstone']['licenses'])}
    if set(decoder.get('licenses', {})) != expected_licenses:
        raise ValueError('The complete decoder notices are required')
    for name, receipt in decoder['licenses'].items():
        raw = archive.read('assets/' + name)
        if len(raw) != receipt['bytes'] or hashlib.sha256(raw).hexdigest() != receipt['sha256']:
            raise ValueError('An original decoder notice is absent or changed')
    return decoder


def verify_publisher_sources(archive, core, repository):
    policy = json.loads(archive.read('assets/publisher-source-policy.json'))
    expected = json.loads((repository / 'packaging/android/publisher-sources.json').read_text())
    if policy != expected or policy.get('schema') != 'toolkit-android-publisher-sources-v1' or policy.get('source_normalization') != 'utf8-lf':
        raise ValueError('The packaged publisher policy differs from the reviewed closure')
    declared = {'backend/' + name + '.py' for provider in policy['providers'].values() for name in provider['modules']}
    declared |= {'backend/' + name + '.py' for name in policy.get('context_modules', {})}
    if declared != set(policy['files']) or not declared <= set(core['files']):
        raise ValueError('An actual publisher dependency is missing from the APK core')
    for name, receipt in policy['files'].items():
        raw = (repository / name).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(raw).hexdigest() != receipt['sha256_lf']:
            raise ValueError('A publisher source changed without a closure review')
    return policy


def verify_zstandard_package(archive, native_files, repository):
    extension_raw = archive.read('assets/python-runtime-extensions.json')
    if extension_raw != (repository / 'packaging/android/python-runtime-extensions.json').read_bytes():
        raise ValueError('The native extension policy differs from reviewed source')
    spec = importlib.util.spec_from_file_location('apk_runtime_extensions', repository / 'scripts/prepare-android-runtime-wheels.py')
    software = importlib.util.module_from_spec(spec);spec.loader.exec_module(software)
    _, pins = software.policy()
    receipt = json.loads(archive.read('assets/zstandard-build-receipt.json'))
    policy = software.validate_zstandard_receipt(receipt, pins)
    if archive.read('assets/zstandard-authored-vectors.json') != (repository / 'packaging/android/zstandard-authored-vectors.json').read_bytes():
        raise ValueError('The authored native-extension vectors changed')
    with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/requirements-common.imy'))) as common:
        for abi, row in receipt['abis'].items():
            name = 'assets/chaquopy/requirements-' + abi + '.imy/' + policy['native_member']
            if name not in native_files or native_files[name]['sha256'] != row['native_sha256']:
                raise ValueError('The actual packaged native extension differs from its compiled ABI receipt')
            for member, expected in row['notices'].items():
                raw = common.read('zstandard-0.25.0.dist-info/licenses/' + member)
                if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
                    raise ValueError('The packaged complete original extension notices changed')
    return receipt


def verify(path):
    result, abis, python_abis, rapidfuzz_abis = {}, set(), set(), {}
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
                            if member.startswith('rapidfuzz/'):
                                rapidfuzz_abis.setdefault(abi, set()).add(member)
        if abis != {'arm64-v8a', 'x86_64'} or python_abis != abis:
            raise ValueError('Both full Android core ABIs are required')
        required = {'rapidfuzz/' + name + '.so' for name in ('utils_cpp', 'fuzz_cpp', 'process_cpp_impl',
            'distance/_initialize_cpp', 'distance/metrics_cpp')}
        if any(not required <= rapidfuzz_abis.get(abi, set()) for abi in abis):
            raise ValueError('Both actual native RapidFuzz ABIs are required')
        core = json.loads(archive.read('assets/core-source-manifest.json'))
        repository = Path(__file__).resolve().parents[1]
        decoder = verify_decoder(archive, result, repository)
        publishers = verify_publisher_sources(archive, core, repository)
        zstandard = verify_zstandard_package(archive, result, repository)
        notices = json.loads((repository / 'packaging/android/account-python-notices.json').read_text(encoding='utf8'))
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/requirements-common.imy'))) as common:
            for package in notices['packages'].values():
                for name, digest in package['included_notices'].items():
                    if hashlib.sha256(common.read(name)).hexdigest() != digest:
                        raise ValueError('A maintained account dependency notice is absent or changed')
        for name, digest in core['files'].items():
            if not re.fullmatch(r'backend/[a-z0-9_]+\.py', name) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('Invalid owned Python source receipt')
            if hashlib.sha256((repository / name).read_bytes()).hexdigest() != digest:
                raise ValueError('The packaged source receipt differs from the current maintained core')
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/app.imy'))) as owned:
            actual_python = {name for name in owned.namelist() if not name.endswith('/')}
            if actual_python != {name + 'c' for name in core['files']}:
                raise ValueError('The delivered Python namespace differs from its closed source manifest')
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
        'native_data_decoder': decoder, 'native_zstandard': zstandard,
        'publisher_source_policy': publishers,
        'target_runtime_acceptance': 'not-established-by-archive-validation', 'release_eligibility': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verify(args.apk), sort_keys=True, indent=2) + '\n', encoding='utf8')
