"""Receipt, ABI and lock failures; authored bytes are never Android execution."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.tests.test_android_python_dependencies import authored_elf

ROOT = Path(__file__).resolve().parents[2]


def module(script):
    spec = importlib.util.spec_from_file_location('test_' + script, ROOT / 'scripts' / (script + '.py'))
    result = importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def digest(raw): return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    owned = module('prepare-android-runtime-wheels')
    extension, original_pins = owned.policy();pins = copy.deepcopy(original_pins)
    pins['wheels'] = {'base.whl':{'sha256':digest(b'authored base wheel')}}
    pins['runtime_requirements'] = ['authored-base==1']
    wheel = extension['flatbuffers']['wheel']
    wheel['sha256'] = digest(b'authored flatbuffers wheel')
    (tmp_path / wheel['source'].rsplit('/', 1)[-1]).write_bytes(b'authored flatbuffers wheel')
    extension['flatbuffers']['license_sha256'] = digest(b'authored flatbuffers license')
    (tmp_path / 'flatbuffers-LICENSE').write_bytes(b'authored flatbuffers license')
    monkeypatch.setattr(owned, 'policy', lambda:(extension,pins))
    base = {'schema':'toolkit-android-python-wheels-v1', 'policy_sha256':owned.sha(ROOT / extension['base_policy']),
        'python':pins['python'], 'ndk_revision':pins['ndk_revision'], 'native':{abi:{'python_target_sha256':pin['sha256']} for abi,pin in pins['targets'].items()},
        'ndk_compiler_inventory_sha256':'f' * 64,
        'rapidfuzz_native':dict.fromkeys(pins['targets'], {}),'files':{'base.whl':digest(b'authored base wheel')}}
    (tmp_path / 'base.whl').write_bytes(b'authored base wheel')
    (tmp_path / 'python-base-wheels-receipt.json').write_text(json.dumps(base))
    native_policy = owned.read(ROOT / 'packaging/android/zstandard-native.json')
    native = {'schema':'toolkit-android-zstandard-build-v1','version':'0.25.0','backend':'cext',
        'ndk_archive_sha256':pins['ndk']['sha256'],'ndk_inventory_sha256':'f' * 64,'abis':{},
        **dict.fromkeys(('system_zstd','cffi','rust','original_game_code'),False),
        'recipe':{'policy_sha256':owned.sha(ROOT / 'packaging/android/zstandard-native.json'),
            'builder_sha256':owned.sha(ROOT / 'scripts/build-android-zstandard.py'),
            'source_sha256':native_policy['sha256'], 'python_input_policy_sha256':owned.sha(ROOT / extension['base_policy']),
            'supplier_helper_sha256':owned.sha(ROOT / 'scripts/build-android-python-dependencies.py'),
            'source_helper_sha256':owned.sha(ROOT / 'scripts/build-android-data-decoders.py')}}
    checker = owned.load('build-android-python-dependencies')
    for abi, pin in pins['targets'].items():
        raw = authored_elf(machine=pin['elf_machine'])
        name = 'zstandard-0.25.0-cp312-cp312-android_24_' + abi.replace('-','_') + '.whl'
        with ZipFile(tmp_path / name, 'w') as wheel: wheel.writestr(native_policy['native_member'],raw)
        notices = {key:{'sha256':digest(key.encode()),'bytes':len(key)}
            for key in [*native_policy['licenses'],'embedded-original-notices.txt']}
        native['abis'][abi] = {'wheel':name,'wheel_sha256':owned.sha(tmp_path / name),'wheel_bytes':(tmp_path / name).stat().st_size,
            'native_sha256':digest(raw),'native_bytes':len(raw),'elf':checker.elf_contract(raw,pin['elf_machine']),
            'python_target_sha256':pin['sha256'],'notices':notices}
    def publish():
        (tmp_path / 'zstandard-build-receipt.json').write_text(json.dumps(native))
        combined = {'schema':'toolkit-android-runtime-wheels-v2','policy_sha256':owned.sha(ROOT / extension['base_policy']),
            'extension_policy_sha256':owned.sha(ROOT / 'packaging/android/python-runtime-extensions.json'),
            'base_receipt_sha256':owned.sha(tmp_path / 'python-base-wheels-receipt.json'),
            'zstandard_receipt_sha256':owned.sha(tmp_path / 'zstandard-build-receipt.json'),
            'files':{path.name:owned.sha(path) for path in tmp_path.glob('*.whl')}}
        (tmp_path / 'python-wheels-receipt.json').write_text(json.dumps(combined))
    (tmp_path / 'requirements-android.lock.txt').write_bytes(('\n'.join(pins['runtime_requirements'] + extension['requirements']) + '\n').encode())
    publish()
    return owned,tmp_path,native,pins,publish


def test_independent_receipts_bind_exact_native_abis_and_complete_runtime_lock(cohort):
    owned,path,_,_,_ = cohort
    original = (path / 'python-base-wheels-receipt.json').read_bytes()
    assert owned.verify(path)['schema'] == 'toolkit-android-runtime-wheels-v2'
    assert (path / 'python-base-wheels-receipt.json').read_bytes() == original
    (path / 'requirements-android.lock.txt').write_bytes(b'authored-base==1\n')
    with pytest.raises(ValueError,match='lock'): owned.verify(path)


@pytest.mark.parametrize('change', ['missing_abi','target','source','builder','notices','system','compiler','changed_binary','unknown_wheel'])
def test_changed_compiler_contract_or_wheel_never_becomes_an_offline_runtime(cohort, change):
    owned,path,native,_,publish = cohort
    row = native['abis']['arm64-v8a']
    if change == 'missing_abi': native['abis'].pop('x86_64')
    elif change == 'target': row['python_target_sha256'] = '0' * 64
    elif change in {'source','builder'}: native['recipe'][change + '_sha256'] = '0' * 64
    elif change == 'notices': row['notices'].pop('embedded-original-notices.txt')
    elif change == 'system': native['system_zstd'] = True
    elif change == 'compiler': native['ndk_inventory_sha256'] = '0' * 64
    elif change == 'changed_binary':
        with (path / row['wheel']).open('ab') as stream: stream.write(b'changed')
    else: (path / 'unreviewed.whl').write_bytes(b'unreviewed')
    publish()
    with pytest.raises(ValueError): owned.verify(path)


@pytest.mark.parametrize('machine,alignment', [(62,16384),(183,4096)])
def test_rewritten_receipt_cannot_hide_wrong_android_abi_or_4k_alignment(cohort,machine,alignment):
    owned,path,native,_,publish = cohort
    row = native['abis']['arm64-v8a'];raw = authored_elf(machine=machine,alignment=alignment)
    with ZipFile(path / row['wheel'],'w') as wheel: wheel.writestr('zstandard/backend_c.cpython-312.so',raw)
    row.update(wheel_sha256=owned.sha(path / row['wheel']),wheel_bytes=(path / row['wheel']).stat().st_size,
        native_sha256=digest(raw),native_bytes=len(raw))
    publish()
    with pytest.raises(ValueError): owned.verify(path)


def test_existing_cohort_is_not_overwritten_before_original_software_checks(tmp_path):
    owned = module('prepare-android-runtime-wheels')
    output = tmp_path / 'reviewed';output.mkdir();(output / 'keep').write_bytes(b'unchanged')
    with pytest.raises(ValueError,match='never overwrite'):
        owned.compose(tmp_path / 'base',tmp_path / 'zstd',tmp_path / 'source.tar.gz',output)
    assert (output / 'keep').read_bytes() == b'unchanged'


@pytest.mark.parametrize('changed', [None,'missing_native','changed_native','changed_notice','changed_policy'])
def test_packaged_abi_and_original_notice_receipts_reject_apk_changes(cohort,changed):
    _,_,receipt,_,_ = cohort
    checker = module('verify-android-apk');files = {}
    common = io.BytesIO()
    with ZipFile(common,'w') as result:
        for name in receipt['abis']['arm64-v8a']['notices']:
            result.writestr('zstandard-0.25.0.dist-info/licenses/' + name,
                b'changed' if changed == 'changed_notice' and name == 'LICENSE' else name.encode())
    for abi,row in receipt['abis'].items():
        files['assets/chaquopy/requirements-' + abi + '.imy/zstandard/backend_c.cpython-312.so'] = {'sha256':row['native_sha256']}
    key = next(iter(files))
    if changed == 'missing_native':files.pop(key)
    if changed == 'changed_native':files[key]['sha256'] = '0' * 64
    stream = io.BytesIO()
    with ZipFile(stream,'w') as result:
        policy = (ROOT / 'packaging/android/python-runtime-extensions.json').read_bytes()
        result.writestr('assets/python-runtime-extensions.json',policy + b'changed' if changed == 'changed_policy' else policy)
        result.writestr('assets/zstandard-build-receipt.json',json.dumps(receipt))
        result.writestr('assets/zstandard-authored-vectors.json',(ROOT / 'packaging/android/zstandard-authored-vectors.json').read_bytes())
        result.writestr('assets/chaquopy/requirements-common.imy',common.getvalue())
    with ZipFile(io.BytesIO(stream.getvalue())) as archive:
        if changed:
            with pytest.raises(ValueError): checker.verify_zstandard_package(archive,files,ROOT)
        else: assert checker.verify_zstandard_package(archive,files,ROOT)['version'] == '0.25.0'


def test_actual_native_reference_runs_all_vectors_and_shared_context_cache(tmp_path):
    from backend.android_probe import run_zstandard
    value = json.loads(run_zstandard(tmp_path / 'cache',(ROOT / 'packaging/android/zstandard-authored-vectors.json').read_text()))
    assert value['backend'] == 'cext' and value['version'] == '0.25.0'
    assert len(value['cases']) == 9 and value['sophon_context_and_offline_cache']
    assert value['publisher_requests'] == 0
    repeated = json.loads(run_zstandard(tmp_path / 'cache',(ROOT / 'packaging/android/zstandard-authored-vectors.json').read_text()))
    assert repeated == value
