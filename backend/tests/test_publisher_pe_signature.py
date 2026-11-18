"""Explicit PE publisher policy and unchanged Endfield compatibility."""
import sys

import pytest

from backend import publisher_pe_signature as signature
from backend import endfield_publisher_signature as endfield
from backend.tests.endfield_parameter_fixture import toy_pe


@pytest.mark.parametrize('publishers', [None, [], set(), {' '}, {'bad\nname'}, {'\x00'}, {42}, {'a'*257}, set(map(str, range(17)))])
def test_invalid_publisher_policy_refuses_before_file_or_native_access(monkeypatch, publishers):
    monkeypatch.setattr(signature, '_windows', lambda *a, **kw: pytest.fail('unreviewed publisher policy'))
    with pytest.raises(ValueError):
        signature.verify('must not be read', publishers=publishers, maximum_bytes=1024)


@pytest.mark.parametrize('maximum', [None, True, 0, 511, 64*1024**2+1, '1024'])
def test_invalid_explicit_file_bound_refuses_before_file_or_native_access(monkeypatch, maximum):
    monkeypatch.setattr(signature, '_windows', lambda *a, **kw: pytest.fail('unbounded original member'))
    with pytest.raises(ValueError):
        signature.verify('must not be read', publishers={'Authored Publisher'}, maximum_bytes=maximum)


def test_missing_host_capability_does_not_read_or_use_apk_crypto(monkeypatch):
    monkeypatch.setattr(signature.sys, 'platform', 'android')
    monkeypatch.setattr(signature, '_windows', lambda *a, **kw: pytest.fail('no PE verifier on this host'))
    with pytest.raises(signature.SignatureCapabilityUnavailable):
        signature.verify('must not be read', publishers={'Authored Publisher'}, maximum_bytes=1024)


def test_endfield_keeps_exact_publisher_size_policy_and_receipt(monkeypatch):
    receipt = {'sha256': 'a'*64, 'bytes': 1024, 'publisher': 'GRYPH FRONTIER PTE. LTD.',
               'verification': 'Windows offline Authenticode', 'online_revocation_freshness': False}
    observed = []
    def verify(path, *, publishers, maximum_bytes):
        observed.append((str(path), publishers, maximum_bytes))
        return receipt
    monkeypatch.setattr(endfield, 'source_runtime', lambda: None)
    monkeypatch.setattr(signature, 'verify', verify)
    assert endfield.verify('authored-original.bin') is receipt
    assert observed == [('authored-original.bin', frozenset({'GRYPH FRONTIER PTE. LTD.'}), 16*1024**2)]


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows offline signature API negatives')
def test_unsigned_original_and_size_policy_cannot_gain_publisher_acceptance(tmp_path):
    path = tmp_path/'authored-inert-pe.bin'
    raw = toy_pe()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='signature is not trusted offline'):
        signature.verify(path, publishers={'Authored Publisher'}, maximum_bytes=len(raw))
    with pytest.raises(ValueError):
        signature.verify(path, publishers={'Authored Publisher'}, maximum_bytes=512)
    assert path.read_bytes() == raw
