"""Authored software capsules exercise the actual packaging audit, not Android."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from backend.tests.test_android_publisher_crypto_bundle import crypto_elf
from backend.tests.test_android_python_dependencies import authored_elf

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


@pytest.fixture
def capsule(tmp_path):
    # Keep original supplier notices out of test source. This isolated authored
    # repository pins its own notices; the production policy remains untouched.
    source = load(ROOT/'scripts/build-android-publisher-hash.py', 'hash_fixture_recipe')
    repository = tmp_path/'repository'
    for name in {*source.recipe(), 'scripts/verify-android-apk.py', 'packaging/android/python-dependencies.json'}:
        path = repository/name; path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, path)
    notices = {'xxhash-LICENSE':b'authored upstream notice', 'python-xxhash-LICENSE':b'authored binding notice'}
    policy_path = repository/'packaging/android/publisher-hash-native.json'
    policy = json.loads(policy_path.read_text())
    for name, member in [('xxhash-LICENSE', 'deps/xxhash/LICENSE'), ('python-xxhash-LICENSE', 'LICENSE')]:
        policy['source']['members'][member] = hashlib.sha256(notices[name]).hexdigest()
    policy_path.write_text(json.dumps(policy))
    owned = load(repository/'scripts/build-android-publisher-hash.py', 'hash_fixture_bundle')
    audit = owned.script('verify-android-apk'); pins = json.loads(owned.script('build-android-python-dependencies').POLICY.read_text())
    work = tmp_path/'bundle'; libraries = {}; assets = {}
    for abi, pin in pins['targets'].items():
        raw = crypto_elf(pin['elf_machine']); name = 'lib/'+abi+'/'+policy['library']
        path = work/'jniLibs'/abi/policy['library']; path.parent.mkdir(parents=True); path.write_bytes(raw)
        libraries[abi] = {**audit.native(raw, abi), 'bytes':len(raw), 'needed':['libc.so'], 'entry':name}
    licenses = {}
    for name, raw in notices.items():
        name = 'publisher-hash-licenses/'+name; assets[name] = raw
        licenses[name] = {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
    value = {'schema':'toolkit-android-publisher-hash-bundle-v1', 'contract':policy['contract'], 'recipe':owned.recipe(),
        'source':policy['source']['source'], 'source_sha256':policy['source']['sha256'],
        'header_sha256':policy['source']['members']['deps/xxhash/xxhash.h'], 'source_members':policy['source']['members'],
        'version':'0.8.4', 'library':policy['library'], 'ndk':policy['ndk'], 'api':policy['api'],
        'ndk_archive_sha256':pins['ndk']['sha256'], 'compiler_sha256':'a'*64, 'ndk_inventory_sha256':'b'*64,
        'max_bytes':4096, 'seed':0, 'custom_secret':False, 'original_client_execution':False,
        'libraries':libraries, 'licenses':licenses}
    def publish():
        for name, raw in {**assets, 'publisher-hash-manifest.json':json.dumps(value).encode()}.items():
            path=work/'assets'/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(raw)
    publish()
    return owned, audit, repository, work, policy, value, publish


def archive(capsule, *, fixture=None, compressed=False):
    owned, audit, repository, work, policy, value, _ = capsule
    payload = io.BytesIO(); native_files = {}
    with ZipFile(payload, 'w') as output:
        for path in (work/'assets').rglob('*'):
            if path.is_file(): output.writestr('assets/'+path.relative_to(work/'assets').as_posix(), path.read_bytes())
        output.writestr('assets/publisher-hash-authored-vectors.json',
            (repository/policy['authored_vectors']).read_bytes() if fixture is None else fixture)
        for abi in policy['abis']:
            name='lib/'+abi+'/'+policy['library']; raw=(work/'jniLibs'/abi/policy['library']).read_bytes()
            output.writestr(name, raw, compress_type=ZIP_DEFLATED if compressed else 0)
            native_files[name]=audit.native(raw, abi)
    return ZipFile(io.BytesIO(payload.getvalue())), native_files


def test_closed_bundle_and_actual_apk_bytes_agree_for_both_abi_headers(capsule):
    owned, audit, repository, work, _, _, _ = capsule
    assert set(owned.verify_bundle(work)['libraries']) == {'arm64-v8a', 'x86_64'}
    source, natives=archive(capsule)
    with source: result=audit.verify_publisher_hash(source, natives, repository)
    assert result['authored_fixture']['cases']==47


@pytest.mark.parametrize('change', ['missing-abi','source','header','recipe','compiler','ndk','seed','bool-seed','limit','secret','original-code','notice','extra','native'])
def test_changed_source_or_bundle_inventory_cannot_reach_the_loader(capsule,change):
    owned, _, _, work, policy, value, publish = capsule
    if change=='missing-abi': value['libraries'].pop('x86_64')
    elif change=='source': value['source_sha256']='0'*64
    elif change=='header': value['header_sha256']='0'*64
    elif change=='recipe': value['recipe']['backend/android_publisher_hash.py']='0'*64
    elif change=='compiler': value['compiler_sha256']='invalid'
    elif change=='ndk': value['ndk_archive_sha256']='0'*64
    elif change=='seed': value['seed']=1
    elif change=='bool-seed': value['seed']=False
    elif change=='limit': value['max_bytes']=8192
    elif change=='secret': value['custom_secret']=True
    elif change=='original-code': value['original_client_execution']=True
    elif change=='notice': value['licenses']['publisher-hash-licenses/xxhash-LICENSE']['sha256']='0'*64
    elif change=='extra': (work/'assets/unreviewed.so').write_bytes(b'not owned')
    else: (work/'jniLibs/arm64-v8a'/policy['library']).write_bytes(b'changed')
    publish()
    with pytest.raises(ValueError): owned.verify_bundle(work)


@pytest.mark.parametrize('abi,machine', [('arm64-v8a',183),('x86_64',62)])
def test_refreshed_hashes_cannot_hide_actual_extra_native_dependencies(capsule,abi,machine):
    owned, _, _, work, policy, value, publish = capsule
    raw=authored_elf(machine=machine);path=work/'jniLibs'/abi/policy['library'];path.write_bytes(raw)
    value['libraries'][abi].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest());publish()
    with pytest.raises(ValueError, match='dependency'): owned.verify_bundle(work)


@pytest.mark.parametrize('change', ['fixture','compressed','notice-bytes','extra-notice','extra-asset','receipt-abi'])
def test_packaged_assets_and_stored_abi_entries_are_checked_not_just_manifest_claims(capsule,change):
    _, audit, repository, work, _, value, publish=capsule
    if change=='notice-bytes': (work/'assets/publisher-hash-licenses/xxhash-LICENSE').write_bytes(b'changed')
    if change=='extra-notice': (work/'assets/publisher-hash-licenses/extra').write_bytes(b'extra')
    if change=='extra-asset': (work/'assets/publisher-hash-other.json').write_bytes(b'{}')
    if change=='receipt-abi': value['libraries']['x86_64']['machine']=183;publish()
    source, natives=archive(capsule,fixture=b'{}' if change=='fixture' else None,compressed=change=='compressed')
    with source, pytest.raises(ValueError): audit.verify_publisher_hash(source,natives,repository)
