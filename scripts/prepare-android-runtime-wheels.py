"""Compose verified Android software cohorts without relabelling base receipts.

The existing matching/account wheelhouse remains immutable. This creates a new
offline wheelhouse, retaining the exact original receipts and an explicit lock.
It does not compile a dependency, construct an APK or execute Android binaries.
"""
import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links


def load(name):
    spec = importlib.util.spec_from_file_location('runtime_' + name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def sha(path):
    _no_links(path)
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    _no_links(path)
    if path.stat().st_size > 2 * 1024**2: raise ValueError('Software receipt exceeds its bound')
    return json.loads(path.read_text(encoding='utf8'))


def policy():
    extension = read(ROOT / 'packaging/android/python-runtime-extensions.json')
    if (extension.get('schema') != 'toolkit-android-runtime-extensions-v1'
            or extension.get('base_policy') != 'packaging/android/python-dependencies.json'
            or extension.get('requirements') != ['zstandard==0.25.0', 'flatbuffers==25.12.19']
            or extension.get('extensions') != {'zstandard': {'recipe': 'packaging/android/zstandard-native.json',
                'builder': 'scripts/build-android-zstandard.py', 'receipt': 'zstandard-build-receipt.json'}}):
        raise ValueError('Review the native runtime extension policy before adding software')
    return extension, read(ROOT / extension['base_policy'])


def flatbuffers_inputs(directory, pin, *, download):
    """Verify the original wheel and recover the license missing from it."""
    directory = Path(directory).absolute()
    _no_links(directory)
    directory.mkdir(parents=True, exist_ok=True)
    acquire = load('build-android-python-dependencies').acquire
    wheel = acquire(directory, pin['wheel'], download=download)
    policy = read(ROOT / 'packaging/desktop/native-notices.json')
    source, = [row for row in policy['components'] if row['name'] == 'flatbuffers' and row['version'] == '25.12.19']
    archive = acquire(directory, {'artifact': source['archive'], 'source': source['url'],
                                  'sha256': source['sha256']}, download=download)
    with tarfile.open(archive, 'r:gz') as supplier:
        license_entry = supplier.getmember(source['root'] + '/LICENSE')
        if not license_entry.isfile() or not 0 < license_entry.size <= 16 * 1024:
            raise ValueError('Invalid original FlatBuffers license')
        license_text = supplier.extractfile(license_entry).read()
    if hashlib.sha256(license_text).hexdigest() != pin['license_sha256']:
        raise ValueError('The original FlatBuffers license changed')
    return wheel, license_text


def check_files(directory, receipt):
    files = receipt.get('files')
    if (not isinstance(files, dict) or not files or len(files) > 64
            or set(files) != {path.name for path in directory.glob('*.whl')}):
        raise ValueError('The exact reviewed wheel inventory is required')
    for name, digest in files.items():
        if Path(name).name != name or not name.endswith('.whl') or sha(directory / name) != digest:
            raise ValueError('A reviewed software wheel changed')


def verify_base(directory, receipt, pins):
    if (receipt.get('schema') != 'toolkit-android-python-wheels-v1'
            or receipt.get('policy_sha256') != sha(ROOT / 'packaging/android/python-dependencies.json')
            or receipt.get('python') != pins['python'] or receipt.get('ndk_revision') != pins['ndk_revision']
            or set(receipt.get('native', {})) != set(pins['targets'])
            or set(receipt.get('rapidfuzz_native', {})) != set(pins['targets'])):
        raise ValueError('The original base software receipt does not match this source policy')
    for abi, pin in pins['targets'].items():
        if receipt['native'][abi].get('python_target_sha256') != pin['sha256']:
            raise ValueError('A base dependency targets another Android Python supplier')
    for name, pin in pins['wheels'].items():
        if receipt['files'].get(name) != pin['sha256']:
            raise ValueError('A maintained base dependency differs from the original supplier')
    for name, digest in receipt['files'].items():
        if Path(name).name != name or not name.endswith('.whl') or sha(directory / name) != digest:
            raise ValueError('A base dependency changed')


def validate_zstandard_receipt(receipt, pins):
    native_policy = read(ROOT / 'packaging/android/zstandard-native.json')
    recipe = receipt.get('recipe', {})
    expected = {'policy_sha256': sha(ROOT / 'packaging/android/zstandard-native.json'),
        'builder_sha256': sha(ROOT / 'scripts/build-android-zstandard.py'),
        'source_sha256': native_policy['sha256'],
        'python_input_policy_sha256': sha(ROOT / 'packaging/android/python-dependencies.json'),
        'supplier_helper_sha256': sha(ROOT / 'scripts/build-android-python-dependencies.py'),
        'source_helper_sha256': sha(ROOT / 'scripts/build-android-data-decoders.py')}
    if (receipt.get('schema') != 'toolkit-android-zstandard-build-v1'
            or receipt.get('version') != native_policy['version'] or receipt.get('backend') != 'cext'
            or receipt.get('ndk_archive_sha256') != pins['ndk']['sha256']
            or any(receipt.get(key) is not False for key in ('system_zstd', 'cffi', 'rust', 'original_game_code'))
            or any(recipe.get(key) != value for key, value in expected.items())
            or set(receipt.get('abis', {})) != set(pins['targets'])):
        raise ValueError('The actual native extension recipe differs from reviewed inputs')
    for abi, row in receipt['abis'].items():
        notices = row.get('notices', {})
        if (row.get('python_target_sha256') != pins['targets'][abi]['sha256']
                or set(notices) != {*native_policy['licenses'], 'embedded-original-notices.txt'}
                or any(not re.fullmatch('[0-9a-f]{64}', value.get('sha256', ''))
                    or type(value.get('bytes')) is not int or not 1 <= value['bytes'] <= 1024**2 for value in notices.values())):
            raise ValueError('The native extension target or complete original notices changed')
    return native_policy


def verify_zstandard(directory, receipt, pins):
    native_policy = validate_zstandard_receipt(receipt, pins)
    abi_checker = load('build-android-python-dependencies')
    for abi, row in receipt['abis'].items():
        name = 'zstandard-0.25.0-cp312-cp312-android_24_' + abi.replace('-', '_') + '.whl'
        path = directory / name
        if (row.get('wheel') != name or sha(path) != row['wheel_sha256'] or path.stat().st_size != row['wheel_bytes']
                or row.get('python_target_sha256') != pins['targets'][abi]['sha256']):
            raise ValueError('The native extension wheel/target differs from its build receipt')
        with zipfile.ZipFile(path) as wheel:
            member = wheel.getinfo(native_policy['native_member'])
            if member.file_size != row['native_bytes'] or not 1 <= member.file_size <= 2 * 1024**2:
                raise ValueError('The native extension exceeds its closed module bound')
            raw = wheel.read(member)
            if (hashlib.sha256(raw).hexdigest() != row['native_sha256'] or len(raw) != row['native_bytes']
                    or abi_checker.elf_contract(raw, pins['targets'][abi]['elf_machine']) != row['elf']):
                raise ValueError('The actual native extension ABI differs from its receipt')
    return receipt


def verify(directory):
    directory = Path(directory).absolute();_no_links(directory)
    extension, pins = policy()
    receipt = read(directory / 'python-wheels-receipt.json')
    if (receipt.get('schema') != 'toolkit-android-runtime-wheels-v2'
            or receipt.get('policy_sha256') != sha(ROOT / extension['base_policy'])
            or receipt.get('extension_policy_sha256') != sha(ROOT / 'packaging/android/python-runtime-extensions.json')
            or receipt.get('base_receipt_sha256') != sha(directory / 'python-base-wheels-receipt.json')
            or receipt.get('zstandard_receipt_sha256') != sha(directory / 'zstandard-build-receipt.json')):
        raise ValueError('A composed runtime requires its unchanged original software receipts')
    base = read(directory / 'python-base-wheels-receipt.json');verify_base(directory, base, pins)
    native = verify_zstandard(directory, read(directory / 'zstandard-build-receipt.json'), pins)
    if native.get('ndk_inventory_sha256') != base.get('ndk_compiler_inventory_sha256'):
        raise ValueError('The native cohorts used different original compiler inventories')
    flatbuffers = extension['flatbuffers']
    wheel = flatbuffers['wheel']['source'].rsplit('/', 1)[-1]
    if sha(directory / 'flatbuffers-LICENSE') != flatbuffers['license_sha256']:
        raise ValueError('The original FlatBuffers license changed')
    expected_files = {**base['files'], **{row['wheel']:row['wheel_sha256'] for row in native['abis'].values()},
                      wheel: flatbuffers['wheel']['sha256']}
    if receipt['files'] != expected_files: raise ValueError('The composed software inventory changed')
    check_files(directory, receipt)
    expected_lock = '\n'.join(pins['runtime_requirements'] + extension['requirements']) + '\n'
    lock = directory / 'requirements-android.lock.txt';_no_links(lock)
    if lock.read_bytes() != expected_lock.encode(): raise ValueError('The exact complete runtime lock is required')
    return receipt


def compose(base, zstandard_work, source_archive, output, *, flatbuffers_directory=None, download=False):
    base, zstandard_work, source_archive, output = (Path(p).absolute() for p in (base, zstandard_work, source_archive, output))
    for path in (base, zstandard_work, source_archive, output): _no_links(path)
    if output.exists(): raise ValueError('Choose a new runtime wheelhouse; never overwrite a reviewed cohort')
    extension, pins = policy()
    base_receipt = read(base / 'python-wheels-receipt.json');verify_base(base, base_receipt, pins);check_files(base, base_receipt)
    if (base / 'requirements-android.lock.txt').read_text(encoding='utf8') != '\n'.join(pins['runtime_requirements']) + '\n':
        raise ValueError('The unchanged base runtime lock is required')
    native = read(zstandard_work / 'wheelhouse/zstandard-build-receipt.json')
    verify_zstandard(zstandard_work / 'wheelhouse', native, pins)
    if native.get('ndk_inventory_sha256') != base_receipt.get('ndk_compiler_inventory_sha256'):
        raise ValueError('The native cohorts used different original compiler inventories')
    zstd = load('build-android-zstandard');unpacker = load('build-android-data-decoders')
    source = unpacker.source_tree(source_archive, zstandard_work / 'source', read(ROOT / 'packaging/android/zstandard-native.json'))
    zstd.verify_wheels(zstandard_work, source, native)
    wheel, license_text = flatbuffers_inputs(flatbuffers_directory or output.parent / 'android-flatbuffers-inputs',
                                             extension['flatbuffers'], download=download)
    output.mkdir(parents=True, exist_ok=False)
    # The output is new and private; a failed publication never touches either
    # original cohort. Re-run into another fresh directory after any failure.
    for name in base_receipt['files']: shutil.copyfile(base / name, output / name)
    for row in native['abis'].values(): shutil.copyfile(zstandard_work / 'wheelhouse' / row['wheel'], output / row['wheel'])
    shutil.copyfile(base / 'python-wheels-receipt.json', output / 'python-base-wheels-receipt.json')
    shutil.copyfile(zstandard_work / 'wheelhouse/zstandard-build-receipt.json', output / 'zstandard-build-receipt.json')
    shutil.copyfile(wheel, output / wheel.name)
    (output / 'flatbuffers-LICENSE').write_bytes(license_text)
    receipt = {'schema':'toolkit-android-runtime-wheels-v2', 'policy_sha256':sha(ROOT / extension['base_policy']),
        'extension_policy_sha256':sha(ROOT / 'packaging/android/python-runtime-extensions.json'),
        'base_receipt_sha256':sha(output / 'python-base-wheels-receipt.json'),
        'zstandard_receipt_sha256':sha(output / 'zstandard-build-receipt.json'),
        'files':{path.name:sha(path) for path in sorted(output.glob('*.whl'))},
        'target_runtime_acceptance':'not-established-by-wheel-composition'}
    (output / 'requirements-android.lock.txt').write_bytes(('\n'.join(pins['runtime_requirements'] + extension['requirements']) + '\n').encode())
    (output / 'python-wheels-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf8')
    return verify(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',type=Path)
    for name in ('base-wheelhouse','zstandard-work-dir','source-archive','output'):
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--flatbuffers-inputs', type=Path)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    if args.verify:
        result = verify(args.verify)
    elif all((args.base_wheelhouse,args.zstandard_work_dir,args.source_archive,args.output)):
        result = compose(args.base_wheelhouse, args.zstandard_work_dir, args.source_archive, args.output,
                         flatbuffers_directory=args.flatbuffers_inputs, download=args.download)
    else: parser.error('Supply --verify or all four original cohort/output arguments')
    print(json.dumps({'schema':result['schema'],'wheels':len(result['files']),
        'target_runtime_acceptance':result['target_runtime_acceptance']}))
