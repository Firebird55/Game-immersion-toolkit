"""Public data envelopes must not execute code, expand without bounds or follow redirects."""
import base64
import io
import json
import struct

import brotli
import pytest
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from backend import hoyo_dispatch_metadata as metadata


@pytest.fixture(scope='module')
def key():
    return RSA.generate(1024)


def envelope(raw, *, key=None, compression=True, expanded=None):
    packed = brotli.compress(raw) if compression else raw
    payload = packed
    if key is not None:
        cipher = PKCS1_v1_5.new(key.public_key())
        width = key.size_in_bytes() - 11
        payload = b''.join(cipher.encrypt(packed[i:i + width]) for i in range(0, len(packed), width))
    attributes = int(compression) | (256 if key else 0)
    return b'Collapse' + struct.pack('<QQQ', attributes, len(packed), len(raw) if expanded is None else expanded) + payload


def encoded(raw):
    return base64.b64encode(raw).decode()


def decoder(key):
    return metadata.Decoder({'Key': encoded(envelope(key.export_key(format='DER'))),
                             'BitSize': key.size_in_bytes()})


def test_public_wrapping_decodes_plain_compressed_multiblock_and_nested_data(key):
    d = decoder(key)
    text = '更新 metadata ' * 40
    assert d.text(encoded(text.encode())) == text
    assert d.text(encoded(envelope(text.encode(), key=key, compression=False))) == text
    inner = encoded(envelope(text.encode(), key=key))
    assert d.text(encoded(envelope(inner.encode(), key=key))) == inner
    assert d.text(inner) == text
    assert d.decode(encoded(envelope(b''))) == b''


@pytest.mark.parametrize('change', ['expanded-short', 'expanded-long', 'packed', 'attributes', 'truncated', 'rsa'])
def test_public_envelope_rejects_bad_size_encoding_and_crypto(key, change):
    raw = bytearray(envelope(b'payload', key=key))
    if change.startswith('expanded'):
        struct.pack_into('<Q', raw, 24, 6 if change.endswith('short') else 8)
    elif change == 'packed':
        struct.pack_into('<Q', raw, 16, 1)
    elif change == 'attributes':
        struct.pack_into('<Q', raw, 8, 65537)
    elif change == 'truncated':
        raw = raw[:20]
    elif change == 'rsa':
        raw[-1] ^= 1
    with pytest.raises(ValueError):
        decoder(key).decode(encoded(raw))


def test_public_envelope_bounds_expansion_and_rejects_recursive_master(key, monkeypatch):
    monkeypatch.setattr(metadata, 'LIMIT', 2048)
    with pytest.raises(ValueError):
        decoder(key).decode(encoded(envelope(b'x' * 4000)))
    # A forged small declaration must not let a compressed body allocate its full expansion.
    with pytest.raises(ValueError):
        decoder(key).decode(encoded(envelope(b'x' * 1000000, expanded=8)))
    recursive = {'Key': encoded(envelope(b'not a key', key=key)), 'BitSize': key.size_in_bytes()}
    with pytest.raises(ValueError):
        metadata.Decoder(recursive).decode(encoded(envelope(b'payload', key=key)))
    for value in ['!invalid!', encoded(b'x' * 2049)]:
        with pytest.raises(ValueError):
            decoder(key).decode(value)


def test_fixed_launcher_editions_load_only_two_public_metadata_documents(monkeypatch, key):
    requests = []
    master = {'Key': encoded(envelope(key.export_key(format='DER'))), 'BitSize': key.size_in_bytes()}
    def fetch(url):
        requests.append(url)
        return json.dumps(master if url.endswith('/config_master.json') else {'Name': 'public config'}).encode()
    monkeypatch.setattr(metadata, 'fetch', fetch)
    config, d = metadata.load('genshin', 'global')
    assert config == {'Name': 'public config'} and isinstance(d, metadata.Decoder)
    assert set(requests) == {metadata.ROOT + 'config_master.json', metadata.ROOT + 'config_GIGlb.json'}
    with pytest.raises(KeyError):
        metadata.load('genshin', 'https://untrusted.example/')


def test_metadata_fetch_rejects_redirects_and_incomplete_or_oversized_bodies(monkeypatch):
    url = metadata.ROOT + 'config_master.json'
    class Response(io.BytesIO):
        status = 200
        headers = {'Content-Length': '3'}
        destination = url
        def geturl(self):
            return self.destination
    monkeypatch.setattr(metadata, 'urlopen', lambda request, timeout: Response(b'abc'))
    assert metadata.fetch(url, limit=3) == b'abc'
    Response.destination = 'http://untrusted.example/'
    with pytest.raises(ValueError):
        metadata.fetch(url, limit=3)
    Response.destination = url
    Response.headers = {'Content-Length': '4'}
    with pytest.raises(ValueError):
        metadata.fetch(url, limit=3)
    Response.headers = {}
    with pytest.raises(ValueError):
        metadata.fetch(url, limit=2)
