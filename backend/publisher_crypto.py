"""Explicit bounded publisher-data primitives, never a Crypto namespace shim.

Consumers retain original source/key/padding and transport decisions. The host
injects a verified Android object or uses the locked desktop implementation.
No account keys, downloaded executable, environment loader or global provider
registration is used here.
"""
from dataclasses import dataclass, field
import json
import math
import re

MAX_BYTES = 64 * 1024**2
MAX_KEY_BYTES = 8192
CHACHA_LIMIT = (2**32 - 1) * 64  # Exact original core rejects its wrapping block.
SOURCE_SHA256 = '3f9e74444c0ecbec7af232a95d282c74b114d53212ce075ed17b7fd7dca32bb3'


def _check(value):
    if not value: raise ValueError('Unsupported publisher cryptography input or runtime.')


def _bytes(value, maximum=MAX_BYTES):
    _check(type(value) is bytes and len(value) <= maximum)
    return value


def _block(algorithm, mode, key, data, iv, decrypt):
    _check(algorithm in ('AES','DES') and mode in ('ECB','CBC') and type(decrypt) is bool)
    _bytes(key,32);_bytes(data)
    size = 16 if algorithm == 'AES' else 8
    _check(len(key) in ((16,24,32) if algorithm == 'AES' else (8,)) and len(data) % size == 0)
    if mode == 'CBC': _check(type(iv) is bytes and len(iv) == size)
    else: _check(iv is None)


def _chacha(key, nonce, data, position):
    _bytes(key,32);_bytes(nonce,12);_bytes(data)
    _check(len(key) == 32 and len(nonce) == 12 and type(position) is int
        and 0 <= position <= CHACHA_LIMIT and len(data) <= CHACHA_LIMIT - position)


@dataclass(frozen=True, repr=False)
class RsaPrivateNumbers:
    n: int = field(repr=False)
    e: int = field(repr=False)
    d: int = field(repr=False)
    p: int = field(repr=False)
    q: int = field(repr=False)

    def __post_init__(self):
        _check(all(type(value) is int and value > 0 for value in (self.n,self.e,self.d,self.p,self.q)))
        _check(1024 <= self.n.bit_length() <= 4096 and 3 <= self.e <= 2**32-1 and self.e % 2 == 1
            and 1 < self.d < self.n and 1 < self.p < self.n and 1 < self.q < self.n
            and self.p != self.q and self.p % 2 == self.q % 2 == 1 and self.p*self.q == self.n)
        _check((self.d*self.e) % math.lcm(self.p-1,self.q-1) == 1)


def _rsa_input(key, data):
    _check(type(key) is RsaPrivateNumbers);_bytes(data,512)
    _check(len(data) == (key.n.bit_length()+7)//8 and int.from_bytes(data,'big') < key.n)


def _public_input(spki, data, signature):
    _bytes(spki,MAX_KEY_BYTES);_bytes(data);_bytes(signature,512)
    _check(len(spki) > 0)


def _supplier():
    import Crypto
    _check(Crypto.__version__ == '3.24.1')


class DesktopPublisherCrypto:
    """Maintained reference; imported only when an explicit operation is used."""
    def block_cipher(self, algorithm, mode, key, data, *, iv=None, decrypt=True):
        _block(algorithm,mode,key,data,iv,decrypt);_supplier()
        from Crypto.Cipher import AES, DES
        selected = AES if algorithm == 'AES' else DES
        cipher = selected.new(key,selected.MODE_CBC,iv) if mode == 'CBC' else selected.new(key,selected.MODE_ECB)
        return cipher.decrypt(data) if decrypt else cipher.encrypt(data)

    def rsa_verify_sha256(self, spki, data, signature):
        _public_input(spki,data,signature);_supplier()
        from Crypto.PublicKey import RSA
        from Crypto.Hash import SHA256
        from Crypto.Signature import pkcs1_15
        from Crypto.Util.asn1 import DerSequence
        structure = DerSequence().decode(spki,strict=True)
        _check(len(structure) == 2 and all(type(value) is bytes for value in structure)
            and structure[0].startswith(b'\x30') and structure[1].startswith(b'\x03'))
        public = RSA.import_key(spki)
        _check(not public.has_private() and 1024 <= public.size_in_bits() <= 4096
            and 3 <= public.e <= 2**32-1 and public.e % 2 == 1)
        try: pkcs1_15.new(public).verify(SHA256.new(data),signature)
        except (ValueError,TypeError): return False
        return True

    def rsa_decrypt_pkcs1(self, key, data):
        _rsa_input(key,data);_supplier()
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5
        private = RSA.construct((key.n,key.e,key.d,key.p,key.q),consistency_check=True)
        # A k-byte sentinel cannot be a valid v1.5 plaintext (at most k-11).
        # The pinned native decoder can return b'' for a non-byte None sentinel.
        result = PKCS1_v1_5.new(private).decrypt(data,bytes(len(data)))
        return None if len(result) > len(data)-11 else result

    def chacha20(self, key, nonce, data, *, position=0):
        _chacha(key,nonce,data,position);_supplier()
        if not data: return b''
        from Crypto.Cipher import ChaCha20
        cipher = ChaCha20.new(key=key,nonce=nonce);cipher.seek(position)
        return cipher.decrypt(data)


class AndroidPublisherCrypto:
    """A concrete private native host capability; no arbitrary callback/plugin."""
    def __init__(self, native, proof):
        self._native,self._proof = native,proof

    @classmethod
    def from_native(cls, native):
        try:
            from java import jclass
            _check(isinstance(native,jclass('io.github.firebird55.gameimmersiontoolkit.PublisherCrypto')))
            raw = str(native.proof());_check(len(raw) <= 65536)
            value = json.loads(raw)
            _check(value.get('schema') == 'toolkit-publisher-crypto-v1' and value.get('abi') in ('arm64-v8a','x86_64')
                and value.get('source_sha256') == SOURCE_SHA256 and value.get('platform_primitives') == 'JCA'
                and value.get('apk_entry_verified') is True and value.get('licenses_verified') is True
                and value.get('system_fallback') is False and value.get('original_client_execution') is False
                and value.get('account_keys_reused') is False and value.get('pointer_bits') == 64
                and value.get('key_bytes') == 32 and value.get('nonce_bytes') == 12 and value.get('max_bytes') == MAX_BYTES)
            for name in ('library_sha256','manifest_sha256'):
                _check(isinstance(value.get(name),str) and re.fullmatch('[0-9a-f]{64}',value[name]))
            return cls(native,value)
        except Exception:
            raise ValueError('The protected Android publisher cryptography runtime is unavailable.') from None

    def _call(self, name, *args):
        try:return getattr(self._native,name)(*args)
        except Exception:raise ValueError('Unsupported publisher cryptography input or runtime.') from None

    def _result(self, value, length):
        try: raw = bytes(value)
        except ValueError: raw = bytes(int(item) & 255 for item in value)
        _check(len(raw) == length);return raw

    def block_cipher(self, algorithm, mode, key, data, *, iv=None, decrypt=True):
        _block(algorithm,mode,key,data,iv,decrypt)
        return self._result(self._call('blockCipher',algorithm,mode,key,iv,data,decrypt),len(data))

    def rsa_verify_sha256(self, spki, data, signature):
        _public_input(spki,data,signature)
        return bool(self._call('rsaVerifySha256',spki,data,signature))

    def rsa_decrypt_pkcs1(self, key, data):
        _rsa_input(key,data)
        unsigned = lambda value:value.to_bytes((value.bit_length()+7)//8,'big')
        result = self._call('rsaDecryptPkcs1',*(unsigned(value) for value in (key.n,key.e,key.d,key.p,key.q)),data)
        if result is None: return None
        raw = self._result(result,len(result));_check(len(raw) <= len(data)-11);return raw

    def chacha20(self, key, nonce, data, *, position=0):
        _chacha(key,nonce,data,position)
        return self._result(self._call('chacha20',key,nonce,data,position),len(data))


def create_publisher_crypto(*, platform, native=None):
    if platform == 'android': return AndroidPublisherCrypto.from_native(native)
    _check(platform in ('windows','linux','macos'))
    return DesktopPublisherCrypto()
