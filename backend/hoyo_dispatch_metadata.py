"""Explicit official/client-data and provenance-bearing hybrid policies.

ZZZ obtains its bootstrap and gateway key data from official client objects.
Genshin may explicitly use a coherent immutable community snapshot; that is not
an official-source claim. Decoded keys never enter provenance or snapshots.
"""
import base64
import binascii
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

import brotli
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA


REPOSITORY = 'CollapseLauncher/CollapseLauncher-ReleaseRepo'
SEED_REVISION = '862de49744c5c3c4120fc932cf7260383b8b7c54'
ROOT = f'https://raw.githubusercontent.com/{REPOSITORY}/{SEED_REVISION}/metadata/v3/stable/'
CONFIGS = {('genshin', 'global'): 'config_GIGlb.json', ('genshin', 'cn'): 'config_GICN.json',
           ('zzz', 'global'): 'config_ZZZGlb.json', ('zzz', 'cn'): 'config_ZZZCN.json'}
# Content identities only. The frozen key/configuration payloads are not source
# literals; they are verified initial resources retained in the host cache.
SEEDS = {
    'config_master.json': (920, 'cde95c053d1ddd4eda35b99aa46f26831728bbb1aa233e4f7eba4ae309686568'),
    'config_ZZZGlb.json': (10559, '4bb447ed4ef769ce5f13a764fff50f977722752fbd8c7347c9cf0a037a2ec345'),
    'config_ZZZCN.json': (10025, 'e34de78ec8fd53492698a093a70fada0bdb3d5eba08af922d76d964c76585cdc'),
    'config_GIGlb.json': (13211, '68a894f37f0f48cae86dd525743672d190eda818566773baaeaad5f60d64835f'),
    'config_GICN.json': (12841, 'aa26d391edc1cfada984afeabae3bbc823ae17c6d1ac378b1116305403faa28c'),
}
LIMIT = 1024 * 1024
_PROVENANCE = '_hoyo_bootstrap_provenance'


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


class OfficialFields:
    """Plain original UTF-8 fields; no master, envelope or key-cache input."""
    def decode(self, value):
        return _base64(value)

    def text(self, value):
        return self.decode(value).decode('utf-8')


def _cache(cache_dir):
    if cache_dir is not None:
        return Path(cache_dir)
    from .runtime_bundle import discover_layout
    return discover_layout().cache_root / 'hoyo-bootstrap'


def _json(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            check(name not in result)
            result[name] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _snapshot(game, region, revision, hashes, cache_dir):
    filename = CONFIGS[game, region]
    names = ('config_master.json', filename)
    check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision))
    if hashes is not None:
        check(isinstance(hashes, dict) and set(hashes) == set(names)
              and all(re.fullmatch('[0-9a-f]{64}', str(value)) for value in hashes.values()))
    directory = _cache(cache_dir) / 'snapshots' / revision

    def body(name):
        from .game_tools import _atomic_file
        path = directory / name
        expected = hashes[name] if hashes is not None else None
        raw = path.read_bytes() if path.is_file() and path.stat().st_size <= LIMIT else b''
        if not raw or expected is None or hashlib.sha256(raw).hexdigest() != expected:
            # Unknown hybrid snapshots are fetched as one pinned revision, never
            # trusted solely because an unverified file exists in the cache.
            url = f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/metadata/v3/stable/{name}'
            raw = fetch(url)
            check(isinstance(raw, bytes) and 0 < len(raw) <= LIMIT
                  and (expected is None or hashlib.sha256(raw).hexdigest() == expected))
            check(isinstance(_json(raw), dict))
            _atomic_file(path, raw)
        return raw

    with ThreadPoolExecutor(max_workers=2) as pool:
        bodies = list(pool.map(body, names))
    master, config = (_json(raw) for raw in bodies)
    check(isinstance(config, dict))
    config[_PROVENANCE] = {'game': game, 'region': region, 'repository': REPOSITORY,
                           'revision': revision,
                           'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                                     for name, raw in zip(names, bodies)}}
    return config, Decoder(master)


def provenance(config):
    """Return only the owned source identity; never decoder/key configuration."""
    check(isinstance(config, dict) and isinstance(config.get(_PROVENANCE), dict))
    return copy.deepcopy(config[_PROVENANCE])


def initial_seed(game, region, *, cache_dir=None):
    """A content-pinned initial input, not a mutable per-update parameter feed."""
    filename = CONFIGS[game, region]
    names = ('config_master.json', filename)
    config, decoder = _snapshot(game, region, SEED_REVISION,
                                {name: SEEDS[name][1] for name in names}, cache_dir)
    check(all(config[_PROVENANCE]['files'][name]['bytes'] == SEEDS[name][0] for name in names))
    config[_PROVENANCE]['policy'] = 'frozen-initial-seed'
    return config, decoder


def load_pinned(game, region, revision, hashes, *, cache_dir=None):
    """Explicit hybrid replay; providers validate the official generation next."""
    check(game == 'genshin')  # ZZZ cannot opt into changing community parameters.
    config, decoder = _snapshot(game, region, revision, hashes, cache_dir)
    config[_PROVENANCE]['policy'] = 'immutable-community-hybrid'
    return config, decoder


def load(game, region, *, build=None, cache_dir=None):
    """Return one coherent source under the game's explicit bootstrap policy."""
    CONFIGS[game, region]  # Validate the edition before any I/O.
    if game == 'zzz':
        check(build is not None)
        from .hoyo_zzz_bootstrap import official
        config = official(build, region, _cache(cache_dir) / 'official' / ('zzz-' + region))
        # Official fields are ordinary Base64 UTF-8, without the community
        # envelope/master. Decoder performs no RSA import on this plain path.
        return config, OfficialFields()
    # A changing hybrid source is resolved once. Both documents then come from
    # that same immutable commit, avoiding a mixed master/config generation.
    raw = fetch(f'https://api.github.com/repos/{REPOSITORY}/commits/main', limit=64 * 1024)
    commit = _json(raw)
    check(isinstance(commit, dict) and re.fullmatch('[0-9a-f]{40}', str(commit.get('sha', ''))))
    config, decoder = _snapshot(game, region, commit['sha'], None, cache_dir)
    config[_PROVENANCE]['policy'] = 'immutable-community-hybrid'
    return config, decoder
