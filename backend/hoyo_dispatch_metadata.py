"""Read public launcher bootstrap data without executing downloaded code.

Collapse's RSA wrapping is a public data format, not publisher authentication.
Keys stay in memory; decoded bootstrap material is never written to a snapshot.
"""
import base64
import binascii
import json
import struct
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

import brotli
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA


ROOT = 'https://raw.githubusercontent.com/CollapseLauncher/CollapseLauncher-ReleaseRepo/main/metadata/v3/stable/'
CONFIGS = {('genshin', 'global'): 'config_GIGlb.json', ('genshin', 'cn'): 'config_GICN.json',
           ('zzz', 'global'): 'config_ZZZGlb.json', ('zzz', 'cn'): 'config_ZZZCN.json'}
LIMIT = 1024 * 1024


def check(condition):
    if not condition:
        raise ValueError('Unsupported public launcher bootstrap data.')


def fetch(url, *, limit=LIMIT, headers=None):
    """Fetch an already allowlisted URL; redirects cannot change its source."""
    request = Request(url, headers={'Accept-Encoding': 'identity',
                                    'User-Agent': 'GameImmersionToolkit/1', **(headers or {})})
    with urlopen(request, timeout=45) as response:
        check(response.status == 200 and response.geturl() == url)
        raw = response.read(limit + 1)
        length = response.headers.get('Content-Length')
        check(len(raw) <= limit and (length is None or length.isdecimal() and int(length) == len(raw)))
    return raw


def _base64(value):
    check(isinstance(value, str) and len(value) <= 2 * LIMIT)
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError('Unsupported public launcher bootstrap encoding.') from error
    check(len(raw) <= LIMIT)
    return raw


def _expand(raw, size):
    decoder = brotli.Decompressor()
    result = bytearray()
    try:
        result.extend(decoder.process(raw, output_buffer_limit=size + 1))
        while not decoder.can_accept_more_data() and len(result) <= size:
            result.extend(decoder.process(b'', output_buffer_limit=size + 1 - len(result)))
        check(len(result) == size and decoder.is_finished())
    except brotli.error as error:
        raise ValueError('Unsupported public launcher bootstrap compression.') from error
    return bytes(result)


class Decoder:
    def __init__(self, master):
        check(isinstance(master, dict) and type(master.get('BitSize')) is int
              and 64 <= master['BitSize'] <= 512)
        self.master = master
        self._key = None

    def decode(self, value):
        return self._unpack(_base64(value), 0)

    def text(self, value):
        return self.decode(value).decode('utf-8')

    def _unpack(self, raw, depth):
        check(depth <= 4 and len(raw) <= LIMIT)
        if not raw.startswith(b'Collapse'):
            return raw
        check(len(raw) >= 32)
        attributes, packed, expanded = struct.unpack_from('<QQQ', raw, 8)
        compression, encrypted = attributes & 255, attributes >> 8 & 255
        check(attributes >> 16 == 0 and compression in (0, 1) and encrypted in (0, 1)
              and packed <= LIMIT and expanded <= LIMIT)
        raw = raw[32:]
        if encrypted:
            if self._key is None:
                # The master itself must be readable before any RSA-wrapped value.
                check(depth == 0)
                key = self._unpack(_base64(self.master['Key']), depth + 1)
                self._key = RSA.import_key(key)
                check(self._key.has_private() and self._key.size_in_bytes() == self.master['BitSize'])
            width = self.master['BitSize']
            check(raw and len(raw) % width == 0)
            cipher = PKCS1_v1_5.new(self._key)
            blocks = [cipher.decrypt(raw[i:i + width], None) for i in range(0, len(raw), width)]
            check(all(isinstance(block, bytes) and block for block in blocks))
            raw = b''.join(blocks)
        check(len(raw) == packed)
        if compression:
            return _expand(raw, expanded)
        check(len(raw) == expanded)
        return raw


def load(game, region):
    """Return (configuration, decoder) for one fixed public launcher edition."""
    filename = CONFIGS[game, region]
    with ThreadPoolExecutor(max_workers=2) as pool:
        bodies = list(pool.map(lambda name: fetch(ROOT + name), ('config_master.json', filename)))
    master, config = (json.loads(raw) for raw in bodies)
    check(isinstance(config, dict))
    return config, Decoder(master)
