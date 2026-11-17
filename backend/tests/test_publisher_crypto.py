"""Actual host JCA versus locked desktop crypto; no Android execution claim."""
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from backend.publisher_crypto import (
    CHACHA_LIMIT, DesktopPublisherCrypto, RsaPrivateNumbers, create_publisher_crypto,
)

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = DesktopPublisherCrypto()


def text(value):
    raw = value.encode('ascii');return struct.pack('>H',len(raw)) + raw


def binary(value):
    return struct.pack('>i',-1 if value is None else len(value)) + (value or b'')


@pytest.fixture(scope='module')
def jca(tmp_path_factory):
    home = Path(os.environ.get('JAVA_HOME',''))
    suffix = '.exe' if os.name == 'nt' else ''
    javac = shutil.which('javac') or (str(home / 'bin' / ('javac'+suffix)) if (home / 'bin' / ('javac'+suffix)).is_file() else None)
    java = shutil.which('java') or (str(home / 'bin' / ('java'+suffix)) if (home / 'bin' / ('java'+suffix)).is_file() else None)
    if not javac or not java:pytest.skip('A real host JDK is required for JCA reference evidence')
    root = tmp_path_factory.mktemp('publisher-jca');classes = root / 'classes';classes.mkdir()
    source = ROOT / 'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/PublisherCryptoOperations.java'
    subprocess.run([javac,'--release','17','-d',str(classes),str(source),
        str(ROOT / 'packaging/android/test-support/PublisherCryptoProbe.java')],check=True,capture_output=True,timeout=60)
    count = 0
    def run(operation, values, *, algorithm='',mode='',decrypt=True):
        nonlocal count
        count += 1
        payload = text(operation)
        if operation == 'block':payload += text(algorithm)+text(mode)+bytes([decrypt])
        payload += b''.join(binary(value) for value in values)
        path = root / ('authored-' + str(count));path.write_bytes(payload)
        result = subprocess.run([java,'-cp',str(classes),'PublisherCryptoProbe',str(path)],check=True,capture_output=True,timeout=15)
        size = struct.unpack('>i',result.stdout[:4])[0]
        assert len(result.stdout) == 4 + max(size,0)
        if size == -2:raise ValueError('The actual JCA implementation rejected this input')
        return None if size == -1 else result.stdout[4:]
    return run


@pytest.mark.parametrize('algorithm,key_size',[('AES',16),('AES',24),('AES',32),('DES',8)])
@pytest.mark.parametrize('mode',['ECB','CBC'])
def test_actual_jca_matches_original_block_cipher_bytes_and_no_padding(jca,algorithm,key_size,mode):
    size = 16 if algorithm == 'AES' else 8
    key = bytes(range(key_size));iv = bytes(reversed(range(size))) if mode == 'CBC' else None
    for plain in (b'',bytes(range(size*3))):
        encoded = REFERENCE.block_cipher(algorithm,mode,key,plain,iv=iv,decrypt=False)
        assert jca('block',[key,iv,plain],algorithm=algorithm,mode=mode,decrypt=False) == encoded
        assert jca('block',[key,iv,encoded],algorithm=algorithm,mode=mode) == plain


@pytest.mark.parametrize('algorithm,mode,key,iv,data',[
    ('AES','CTR',bytes(32),None,bytes(16)),('DESede','ECB',bytes(24),None,bytes(16)),
    ('AES','ECB',bytes(15),None,bytes(16)),('AES','CBC',bytes(32),None,bytes(16)),
    ('DES','CBC',bytes(8),bytes(16),bytes(16)),('AES','ECB',bytes(32),bytes(16),bytes(16)),
    ('AES','ECB',bytes(32),None,bytes(15)),
])
def test_actual_jca_and_reference_reject_unsupported_shapes(jca,algorithm,mode,key,iv,data):
    with pytest.raises(ValueError):REFERENCE.block_cipher(algorithm,mode,key,data,iv=iv)
    with pytest.raises(ValueError):jca('block',[key,iv,data],algorithm=algorithm,mode=mode)


@pytest.fixture(scope='module')
def rsa():
    from Crypto.PublicKey import RSA
    # Fresh authored keys stay only inside this process and ignored test files.
    key = RSA.generate(1024)
    return key,RsaPrivateNumbers(key.n,key.e,key.d,key.p,key.q)


def number(value):return value.to_bytes((value.bit_length()+7)//8,'big')


def test_actual_jca_signature_verification_and_invalid_public_encodings(jca,rsa):
    from Crypto.Signature import pkcs1_15
    from Crypto.Hash import SHA256
    from Crypto.Util.asn1 import DerSequence
    key,_ = rsa;payload = b'Authored publisher integrity metadata'
    spki = key.public_key().export_key(format='DER');signature = pkcs1_15.new(key).sign(SHA256.new(payload))
    for data,sig,expected in ((payload,signature,True),(payload+b'changed',signature,False),
        (payload,signature[:-1],False),(payload,b'',False),(payload,bytes(len(signature)),False)):
        assert REFERENCE.rsa_verify_sha256(spki,data,sig) is expected
        assert jca('verify',[spki,data,sig]) == bytes([expected])
    for invalid in (b'not DER',key.public_key().export_key(format='PEM'),DerSequence([key.n,key.e]).encode()):
        with pytest.raises(ValueError):REFERENCE.rsa_verify_sha256(invalid,payload,signature)
        with pytest.raises(ValueError):jca('verify',[invalid,payload,signature])


def test_actual_jca_crt_decrypt_invalid_padding_and_out_of_range(jca,rsa):
    from Crypto.Cipher import PKCS1_v1_5
    original,key = rsa;plain = b'Authored encrypted source metadata'
    encoded = PKCS1_v1_5.new(original.public_key()).encrypt(plain)
    numbers = [number(value) for value in (key.n,key.e,key.d,key.p,key.q)]
    assert REFERENCE.rsa_decrypt_pkcs1(key,encoded) == jca('decrypt',[*numbers,encoded]) == plain
    empty = PKCS1_v1_5.new(original.public_key()).encrypt(b'')
    assert REFERENCE.rsa_decrypt_pkcs1(key,empty) == jca('decrypt',[*numbers,empty]) == b''
    bad_padding = bytes(len(encoded))
    assert REFERENCE.rsa_decrypt_pkcs1(key,bad_padding) is None and jca('decrypt',[*numbers,bad_padding]) is None
    for invalid in (encoded[:-1],number(key.n)):
        with pytest.raises(ValueError):REFERENCE.rsa_decrypt_pkcs1(key,invalid)
        with pytest.raises(ValueError):jca('decrypt',[*numbers,invalid])
    corrupt = [*numbers];corrupt[2] = number(key.d+2)
    with pytest.raises(ValueError):jca('decrypt',[*corrupt,encoded])
    with pytest.raises(ValueError):RsaPrivateNumbers(key.n,key.e,key.d+2,key.p,key.q)
    # A mathematically self-consistent composite factor pair still fails the
    # actual providers' prime/CRT validation, not just the shared shape check.
    p,q = 2**512+1,2**512+3;e = 65537;d = pow(e,-1,math.lcm(p-1,q-1))
    composite = RsaPrivateNumbers(p*q,e,d,p,q);body = bytes((composite.n.bit_length()+7)//8)
    with pytest.raises(ValueError):REFERENCE.rsa_decrypt_pkcs1(composite,body)
    with pytest.raises(ValueError):jca('decrypt',[*(number(value) for value in (p*q,e,d,p,q)),body])


def test_chacha_reference_positions_chunks_counter_and_android_gates():
    key,nonce = bytes(range(32)),bytes(range(12));data = bytes(range(256))*2
    complete = REFERENCE.chacha20(key,nonce,data)
    for offset in (0,1,63,64,65,2**32+17):
        result = REFERENCE.chacha20(key,nonce,data,position=offset)
        assert result == REFERENCE.chacha20(key,nonce,data[:70],position=offset) + REFERENCE.chacha20(key,nonce,data[70:],position=offset+70)
        if offset < 65:assert result[:100] == REFERENCE.chacha20(key,nonce,bytes(offset)+data[:100])[offset:]
    assert len(complete) == len(data)
    for wrong_key,wrong_nonce,position,payload in ((bytes(31),nonce,0,b'x'),(key,bytes(8),0,b'x'),
        (key,nonce,-1,b'x'),(key,nonce,True,b'x'),(key,nonce,CHACHA_LIMIT,b'x')):
        with pytest.raises(ValueError):REFERENCE.chacha20(wrong_key,wrong_nonce,payload,position=position)
    assert REFERENCE.chacha20(key,nonce,b'',position=CHACHA_LIMIT) == b''
    with pytest.raises(ValueError):create_publisher_crypto(platform='android',native=object())
    assert type(create_publisher_crypto(platform='windows')) is DesktopPublisherCrypto
