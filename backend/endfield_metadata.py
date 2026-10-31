"""Pinned, private numerical metadata for the owned Endfield voice reader.

Downloaded documents are data inputs, never executable dependencies. They stay
outside the application/release image and are neither imported nor compiled.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import re

from .endfield_vfs import Parameters
from .preparation_errors import PreparationFailure

REVISION = '48c40a5e6a931b08223384077b74b41b484a540f'
BASE = f'https://raw.githubusercontent.com/EIHRTeam/EndfieldStudio/{REVISION}/AnimeStudio.Endfield/'
SOURCES = {
    'Keys.cs': '07aea4fdd6b5c5d21269e0dc4ea1117d0ea1beac275061556715c563f79d1d9e',
    'BlockHashes.cs': '55e3ac8617e68b3178d8982a1278451790c467e27dd520a7371a7f433e268d39',
    'Processors/AkpkCrypto.cs': '9f8a84a43b8f36902783695986813782f8a65780f9f9193efb888a361e3ea4ff',
}
BLOCKS = {'InitialAudio': 1, 'HotfixAudio': 21, 'AudioChinese': 101,
          'AudioEnglish': 102, 'AudioJapanese': 103, 'AudioKorean': 104}
LIMIT = 16 * 1024


def _one(pattern, text):
    values = re.findall(pattern, text, re.S)
    if len(values) != 1:
        raise ValueError('Unsupported Endfield format metadata structure')
    return values[0]


def _parse(documents: dict[str, bytes]) -> Parameters:
    keys, blocks, crypto = (documents[name].decode('utf-8-sig') for name in SOURCES)
    key = base64.b64decode(_one(r'ChaCha20Key\s*=\s*Convert\.FromBase64String\("([A-Za-z0-9+/=]+)"\)', keys), validate=True)
    protocol = int(_one(r'\bVfsProtoVersion\s*=\s*(\d+)\s*;', keys))
    directories = {value: _one(r'\[BlockType\.' + name + r'\]\s*=\s*"([0-9A-F]{8})"', blocks)
                   for name, value in BLOCKS.items()}
    numbers = [int(_one(r'\b' + field + r'\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)u\s*;', crypto), 0)
               for field in ('MulConst', 'XorConst')]
    return Parameters(key, directories, *numbers, protocol=protocol)


def cache_root(tools: Path) -> Path:
    return tools / 'format-metadata/endfield-v1'


def ready(tools: Path) -> bool:
    try:
        return all((path := cache_root(tools) / name).stat().st_size <= LIMIT and
                   hashlib.sha256(path.read_bytes()).hexdigest() == digest for name, digest in SOURCES.items())
    except OSError:
        return False


def parameters(tools: Path) -> Parameters:
    from .game_tools import download, _atomic_file
    documents, replacements = {}, {}
    for name, digest in SOURCES.items():
        path = cache_root(tools) / name
        try:
            with path.open('rb') as stream:
                data = stream.read(LIMIT + 1)
        except FileNotFoundError:
            data = b''
        if len(data) > LIMIT or hashlib.sha256(data).hexdigest() != digest:
            data = download(BASE + name, limit=LIMIT)
            if hashlib.sha256(data).hexdigest() != digest:
                raise PreparationFailure('reader_checksum', 'Archive format metadata failed verification. No cached metadata was replaced. Retry preparation after checking the connection.')
            replacements[path] = data
        documents[name] = data
    result = _parse(documents)
    for path, data in replacements.items():
        _atomic_file(path, data)
    return result
