"""Closed software/ABI negatives using authored ELF, never target execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import pytest

from backend.tests.test_android_python_dependencies import authored_elf

ROOT=Path(__file__).resolve().parents[2]


def builder():
    spec=importlib.util.spec_from_file_location('owned_publisher_crypto',ROOT/'scripts/build-android-publisher-crypto.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def crypto_elf(machine):
    raw=bytearray(authored_elf(machine=machine))
    libc=raw.index(b'libc.so\0',768)-768
    for index,pair in enumerate(((1,libc),(5,768),(10,64),(0,0))):
        struct.pack_into('<qQ',raw,512+index*16,*pair)
    return bytes(raw)


@pytest.fixture
def bundle(tmp_path):
    owned=builder();policy=json.loads((ROOT/'packaging/android/publisher-crypto-native.json').read_text())
    pins=json.loads((ROOT/'packaging/android/python-dependencies.json').read_text())
    audit=owned.script('verify-android-apk');libraries={}
    for abi,pin in pins['targets'].items():
        raw=crypto_elf(pin['elf_machine']);path=tmp_path/'jniLibs'/abi/policy['library'];path.parent.mkdir(parents=True);path.write_bytes(raw)
        libraries[abi]={**audit.native(raw,abi),'bytes':len(raw),'needed':['libc.so'],
            'entry':'lib/'+abi+'/'+policy['library']}
    names={'publisher-crypto-licenses/LICENSE.rst',
        *('publisher-crypto-licenses/'+Path(name).name+'.notice' for name in policy['source']['notice_sources'])}
    licenses={}
    for name in names:
        path=tmp_path/'assets'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'authored complete notice')
        licenses[name]={'bytes':path.stat().st_size,'sha256':owned.sha(path)}
    value={'schema':'toolkit-android-publisher-crypto-bundle-v1','contract':policy['contract'],
        'source':policy['source']['source'],'source_sha256':policy['source']['sha256'],'version':policy['source']['version'],
        'recipe':owned.recipe(policy),'source_members':policy['source']['members'],'ndk':policy['ndk'],'api':policy['api'],
        'ndk_archive_sha256':pins['ndk']['sha256'],'ndk_inventory_sha256':'a'*64,'compiler_sha256':'b'*64,
        'library':policy['library'],'libraries':libraries,'licenses':licenses,'platform_primitives':'JCA',
        'original_client_execution':False,'account_keys_reused':False}
    def publish():(tmp_path/'assets/publisher-crypto-manifest.json').write_text(json.dumps(value))
    publish();return owned,tmp_path,value,publish


def test_actual_closed_inventory_and_both_authored_abi_headers_are_required(bundle):
    owned,path,_,_=bundle
    assert set(owned.verify_bundle(path)['libraries'])=={'arm64-v8a','x86_64'}


@pytest.mark.parametrize('change',['missing_abi','source','recipe','ndk','compiler','account','license','extra','changed_native'])
def test_changed_software_or_namespace_is_rejected_before_a_loader_can_use_it(bundle,change):
    owned,path,value,publish=bundle
    if change=='missing_abi':value['libraries'].pop('x86_64')
    elif change=='source':value['source_sha256']='0'*64
    elif change=='recipe':value['recipe']['transport_sha256']='0'*64
    elif change=='ndk':value['ndk_archive_sha256']='0'*64
    elif change=='compiler':value['compiler_sha256']='wrong'
    elif change=='account':value['account_keys_reused']=True
    elif change=='license':next((path/'assets/publisher-crypto-licenses').iterdir()).write_bytes(b'changed')
    elif change=='extra':(path/'assets/unreviewed.so').write_bytes(b'unreviewed')
    else:(path/'jniLibs/arm64-v8a'/value['library']).write_bytes(b'changed')
    publish()
    with pytest.raises(ValueError):owned.verify_bundle(path)


@pytest.mark.parametrize('abi,machine',[('arm64-v8a',183),('x86_64',62)])
def test_forged_receipt_cannot_hide_an_actual_extra_dependency(bundle,abi,machine):
    owned,path,value,publish=bundle
    # Even after all byte hashes are refreshed, the actual ELF dependency parser
    # refuses libpython/libm/libdl instead of trusting the claimed libc-only list.
    raw=authored_elf(machine=machine);target=path/'jniLibs'/abi/value['library'];target.write_bytes(raw)
    value['libraries'][abi].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    publish()
    with pytest.raises(ValueError,match='dependency'):owned.verify_bundle(path)


def test_wrong_original_source_stops_before_compiler_or_supplier_execution(tmp_path,monkeypatch):
    owned=builder();source=tmp_path/'source.tar.gz';source.write_bytes(b'not the original software')
    monkeypatch.setattr(owned.subprocess,'run',lambda *a,**k:pytest.fail('Compiler ran before source authentication'))
    with pytest.raises(ValueError,match='pinned receipt'):
        owned.build(tmp_path/'work',source,tmp_path/'ndk',tmp_path/'ndk.zip')
    assert not (tmp_path/'work/assets/publisher-crypto-manifest.json').exists()
