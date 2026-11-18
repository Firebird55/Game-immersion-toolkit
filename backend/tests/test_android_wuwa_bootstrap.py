"""Authored closed provider behavior on host; target JNI acceptance is separate."""
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from backend.android_probe import run_wuwa_bootstrap
from backend.publisher_crypto import DesktopPublisherCrypto, SOURCE_SHA256, MAX_BYTES

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def fixture(tmp_path_factory):
    spec=importlib.util.spec_from_file_location('authored_wuwa_generator',ROOT/'scripts/prepare-android-wuwa-probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=tmp_path_factory.mktemp('authored-wuwa')/'fixture.json'
    receipt=module.generate(output)
    assert receipt['original_game_bytes'] is False and 1024<receipt['apk_bytes']<32768
    return output.read_text()


def test_actual_service_signed_apk_member_mmap_and_scope_with_explicit_host_java_simulation(tmp_path,fixture,monkeypatch):
    reference=DesktopPublisherCrypto();operations=[]
    class AuthoredJava:
        def proof(self):
            return json.dumps({'schema':'toolkit-publisher-crypto-v1','abi':'arm64-v8a','source_sha256':SOURCE_SHA256,
                'platform_primitives':'JCA','apk_entry_verified':True,'licenses_verified':True,'system_fallback':False,
                'original_client_execution':False,'account_keys_reused':False,'pointer_bits':64,
                'library_sha256':'a'*64,'manifest_sha256':'b'*64,'key_bytes':32,'nonce_bytes':12,'max_bytes':MAX_BYTES})
        def rsaVerifySha256(self,public,data,signature):
            operations.append(True)
            return reference.rsa_verify_sha256(public,data,signature)
    native=AuthoredJava()
    monkeypatch.setitem(sys.modules,'java',SimpleNamespace(jclass=lambda name:AuthoredJava))
    report=json.loads(run_wuwa_bootstrap(tmp_path,SimpleNamespace(publisherCrypto=lambda:native),fixture))
    assert report['passed'] and report['snapshot_ready'] is False and operations
    assert [row['case'] for row in report['cases']]==['text','text-audio','corrupt','cancel']
    for row in report['cases'][:2]:
        assert row['full_apk_verified'] and row['mmap_data_parser'] and row['offline_restart']
        assert row['snapshot_activated'] is False
    assert all(row['rejected'] and row['retained_data'] for row in report['cases'][2:])
    assert report['actual_network'] is False and report['original_game_bytes'] is False
    assert 'apk_base64' not in json.dumps(report) and 'parameter' not in json.dumps(report)


@pytest.mark.parametrize('fault',['oversize','truncated','changed-carrier','wrong-schema'])
def test_authored_envelope_failure_precedes_native_or_transport(tmp_path,fixture,fault):
    value=json.loads(fixture)
    if fault=='oversize':raw='x'*65537
    elif fault=='truncated':raw=fixture[:-10]
    elif fault=='wrong-schema':value['schema']='other';raw=json.dumps(value)
    else:value['apk_sha256']='0'*64;raw=json.dumps(value)
    class ForbiddenNative:
        def publisherCrypto(self):pytest.fail('A malformed authored envelope reached native code')
    with pytest.raises(ValueError):run_wuwa_bootstrap(tmp_path,ForbiddenNative(),raw)


@pytest.mark.parametrize('fault',[None,'missing','changed-apk','changed-source','extra-source','bad-size'])
def test_actual_packaged_fixture_audit_binds_generation_to_reviewed_source(fixture,fault):
    spec=importlib.util.spec_from_file_location('wuwa_fixture_audit',ROOT/'scripts/verify-android-apk.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    value=json.loads(fixture)
    if fault=='changed-apk':value['apk_sha256']='0'*64
    elif fault=='changed-source':value['fixture_sources']['backend/tests/test_publisher_apk.py']='0'*64
    elif fault=='extra-source':value['fixture_sources']['other']='0'*64
    elif fault=='bad-size':value['module_bytes']=14337
    buffer=io.BytesIO()
    with ZipFile(buffer,'w') as archive:
        if fault!='missing':archive.writestr('assets/wuwa-authored-bootstrap.json',json.dumps(value))
    with ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        if fault:
            with pytest.raises((KeyError,ValueError)):audit.verify_wuwa_fixture(archive,ROOT)
        else:
            result=audit.verify_wuwa_fixture(archive,ROOT)
            assert result['apk_bytes']==value['apk_bytes'] and result['module_sha256']==value['module_sha256']
            assert result['original_game_bytes'] is False
