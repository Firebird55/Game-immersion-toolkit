"""Real reference vectors and package boundaries, not Android execution."""
import importlib.util
import io
import json
from pathlib import Path
import struct
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED

import pytest

from backend.android_probe import _crypto_cases, run_crypto
from backend.publisher_crypto import DesktopPublisherCrypto
from backend.tests.test_android_publisher_crypto_bundle import bundle

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def vectors(tmp_path_factory):
    spec = importlib.util.spec_from_file_location('authored_crypto_vectors',ROOT/'scripts/prepare-publisher-crypto-probes.py')
    software = importlib.util.module_from_spec(spec);spec.loader.exec_module(software)
    work = tmp_path_factory.mktemp('authored-crypto-vectors')
    assert software.authored_vectors(work)['jca_cases'] == 41
    return (work/'authored-capi.bin').read_bytes(),(work/'authored-jca.bin').read_bytes()


def test_all_actual_pinned_reference_cases_keep_keys_and_plaintext_out_of_report(vectors):
    report = _crypto_cases(DesktopPublisherCrypto(),*vectors)
    assert report['passed'] and report['chacha_positive_cases'] == 8
    assert report['operations'] == {'block':31,'verify':5,'decrypt':5}
    assert report['publisher_requests'] == 0
    assert 'Authored publisher integrity' not in json.dumps(report)
    assert set(report['fixtures']) == {'capi','jca'}


@pytest.mark.parametrize('change',['truncated','extra','oversized','false-positive','wrong-count','unknown-operation'])
def test_fixture_corruption_is_not_a_passing_expected_rejection(vectors,change):
    capi,jca = vectors
    if change == 'truncated':jca = jca[:-1]
    elif change == 'extra':capi += b'extra'
    elif change == 'oversized':jca = b'x'*65537
    elif change == 'false-positive':
        capi = bytearray(capi);capi[8+32+32+12] ^= 1;capi = bytes(capi)
    elif change == 'wrong-count':capi = capi[:4]+struct.pack('<I',15)+capi[8:]
    else:jca = jca.replace(b'block',b'wrong',1)
    with pytest.raises(ValueError):_crypto_cases(DesktopPublisherCrypto(),capi,jca)


def test_debug_probe_does_not_accept_arbitrary_host_objects_or_unbounded_encoded_data():
    with pytest.raises(ValueError):run_crypto(object(),'','')
    with pytest.raises(ValueError):run_crypto(object(),'A'*90001,'')


def packaged(bundle,vectors,change=None):
    owned,path,value,_ = bundle
    output = io.BytesIO();natives = {}
    with ZipFile(output,'w') as archive:
        for source in sorted((path/'assets').rglob('*')):
            if source.is_file():archive.writestr('assets/'+source.relative_to(path/'assets').as_posix(),source.read_bytes())
        for abi,row in value['libraries'].items():
            raw = (path/'jniLibs'/abi/value['library']).read_bytes()
            if change == 'changed-native' and abi == 'arm64-v8a':raw += b'changed'
            archive.writestr(row['entry'],raw,compress_type=ZIP_DEFLATED if change == 'compressed-native' else ZIP_STORED)
            natives[row['entry']] = owned.script('verify-android-apk').native(raw,abi)
        for kind,raw in zip(('capi','jca'),vectors):
            if change == 'wrong-fixture' and kind == 'capi':raw = b'WRNG'+raw[4:]
            archive.writestr('assets/publisher-crypto-authored-'+kind+'.bin',raw)
    return ZipFile(io.BytesIO(output.getvalue())),natives


def test_actual_apk_audit_binds_manifest_both_abi_bytes_and_authored_fixtures(bundle,vectors):
    owned,_,_,_ = bundle
    archive,natives = packaged(bundle,vectors)
    with archive:
        result = owned.script('verify-android-apk').verify_publisher_crypto(archive,natives,ROOT)
        assert result['authored_fixtures']['capi']['cases'] == 16
        assert result['authored_fixtures']['jca']['cases'] == 41


@pytest.mark.parametrize('change',['changed-native','compressed-native','wrong-fixture'])
def test_apk_repackaging_or_changed_native_inputs_are_rejected(bundle,vectors,change):
    owned,_,_,_ = bundle
    archive,natives = packaged(bundle,vectors,change)
    with archive,pytest.raises(ValueError):owned.script('verify-android-apk').verify_publisher_crypto(archive,natives,ROOT)
