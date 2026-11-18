"""The Python adapter never falls back to unprotected credentials on failure."""
import base64

import pytest

from backend.android_protected_storage import AndroidProtectedBlobs, AndroidProtectedStorageError


def test_account_protection_delegates_exact_bytes_and_operation_to_native():
    class Native:
        def protect(self, value, decrypt):
            assert base64.b64decode(value) == b'authored input' and decrypt is True
            return base64.b64encode(b'authored native result').decode()
    assert AndroidProtectedBlobs(Native()).protect(b'authored input', decrypt=True) == b'authored native result'


@pytest.mark.parametrize('result', [None, 'bad base64', 'A' * 1400001], ids=['absent', 'invalid', 'oversized'])
def test_invalid_native_result_never_returns_the_input_plaintext(result):
    class Native:
        def protect(self, *args):
            return result
    with pytest.raises(AndroidProtectedStorageError):
        AndroidProtectedBlobs(Native()).protect(b'authored input')


def test_unavailable_native_keystore_has_safe_error_without_provider_details():
    class Native:
        def protect(self, *args):
            raise RuntimeError('authored sensitive provider diagnostics')
    with pytest.raises(AndroidProtectedStorageError) as captured:
        AndroidProtectedBlobs(Native()).protect(b'authored input')
    assert 'sensitive' not in str(captured.value) and captured.value.__suppress_context__


@pytest.mark.parametrize('value,decrypt', [(bytearray(b'authored'), False), (b'authored', 1), (b'a' * (1024**2 + 65), False)], ids=['mutable', 'nonboolean', 'oversized'])
def test_invalid_blob_shape_is_rejected_before_any_native_operation(value, decrypt):
    with pytest.raises(AndroidProtectedStorageError):
        AndroidProtectedBlobs(None).protect(value, decrypt=decrypt)
