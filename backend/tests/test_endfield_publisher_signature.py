"""Signature capability failure and an actual unsigned data-file negative."""
import sys

import pytest

from backend import endfield_publisher_signature as signature
from backend.preparation_errors import PreparationFailure
from backend.tests.endfield_parameter_fixture import toy_pe


def test_non_windows_signature_capability_is_explicit_before_file_reads(monkeypatch):
    monkeypatch.setattr(signature.sys, 'platform', 'linux')
    monkeypatch.setattr(signature, '_windows', lambda _: pytest.fail('must not run a Windows fallback'))
    with pytest.raises(PreparationFailure) as error:
        signature.verify('not read')
    assert error.value.code == 'missing_toolkit_runtime'
    assert error.value.previous_snapshot_retained is True


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows offline signature API negative')
def test_unsigned_authored_pe_is_not_a_publisher_source(tmp_path):
    path = tmp_path / 'authored-inert-pe.bin'
    raw = toy_pe()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='signature is not trusted offline'):
        signature.verify(path)
    assert path.read_bytes() == raw
