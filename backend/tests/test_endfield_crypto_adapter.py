"""Exact VFS stream position and bounds through the maintained primitive seam."""
import io

import pytest
from Crypto.Cipher import ChaCha20

from backend import endfield_vfs as vfs, publisher_crypto
from backend.tests.test_endfield_vfs import index, PARAMETERS


class TrackedCrypto(publisher_crypto.DesktopPublisherCrypto):
    def __init__(self): self.calls = []
    def chacha20(self, key, nonce, data, *, position=0):
        self.calls.append((position, len(data)))
        return super().chacha20(key, nonce, data, position=position)


@pytest.mark.parametrize('offset', [0,1,3,63,64,65,4097])
def test_seek_64_plus_original_unaligned_offset(offset):
    raw = bytes(range(256))*2; key=bytes(range(32)); nonce=bytes(range(12)); crypto=TrackedCrypto()
    reference=ChaCha20.new(key=key, nonce=nonce); reference.seek(64+offset)
    assert vfs.chacha(raw,key,nonce,offset,crypto=crypto) == reference.decrypt(raw)
    assert crypto.calls == [(64+offset,len(raw))]


def test_index_and_chunk_source_propagate_only_explicit_crypto():
    crypto=TrackedCrypto(); rows=vfs.parse_index(index(128), PARAMETERS, 102, crypto=crypto)
    assert len(rows)==1 and crypto.calls[0][0]==64
    file=rows[0]; key=PARAMETERS.key
    reference=ChaCha20.new(key=key,nonce=file.nonce); reference.seek(64)
    raw=bytes(range(128)); encrypted=reference.encrypt(raw)
    source=vfs.PackageSource(io.BytesIO(encrypted),file,PARAMETERS,crypto=crypto)
    assert source.read(7,93)==raw[7:100] and crypto.calls[-1]==(71,93)


def test_preserves_large_text_index_support_without_widening_primitive_call_limit(monkeypatch):
    # Force a small boundary to exercise every unaligned chunk position using
    # the real independent supplier, with the same production partition logic.
    monkeypatch.setattr(publisher_crypto,'MAX_BYTES',31)
    raw=bytes(range(251))*3;key=bytes(range(32));nonce=bytes(range(12));crypto=TrackedCrypto()
    reference=ChaCha20.new(key=key,nonce=nonce);reference.seek(64+17)
    assert vfs.chacha(raw,key,nonce,17,crypto=crypto)==reference.encrypt(raw)
    assert all(size<=31 for _,size in crypto.calls)
    assert [position for position,_ in crypto.calls]==[81+n for n in range(0,len(raw),31)]


@pytest.mark.parametrize('offset', [-1,True,1.5,publisher_crypto.CHACHA_LIMIT-63])
def test_invalid_seek_and_wrap_fail_before_primitive(offset):
    crypto=TrackedCrypto()
    with pytest.raises(vfs.FormatError):vfs.chacha(b'x',bytes(32),bytes(12),offset,crypto=crypto)
    assert not crypto.calls


def test_unknown_provider_or_non_ietf_nonce_never_falls_back_to_a_desktop_loader():
    with pytest.raises(vfs.FormatError):vfs.chacha(b'x',bytes(32),bytes(12),crypto=object())
    with pytest.raises(vfs.FormatError):vfs.chacha(b'x',bytes(32),bytes(8),crypto=TrackedCrypto())
