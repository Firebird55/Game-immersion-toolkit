"""Acquire pinned RE PAK numerical format metadata in the private tool cache.

The reader is toolkit-owned Python. Downloaded source is parsed only as a
bounded data document; it is never compiled, imported, executed or shipped.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .preparation_errors import PreparationFailure
from .re_pak import CipherParameters

REVISION = 'd22c15314e84eecd31480acfe692092c48043ac0'
BASE = f'https://raw.githubusercontent.com/Ekey/REE.PAK.Tool/{REVISION}/REE.Unpacker/REE.Unpacker/FileSystem/Encryption/'
SOURCES = {
    'table': ('PakCipher.cs', '164508d88275ba2be279dd758308f040cebc5c46e11c393418af3cef3e84c0de', (129, 4)),
    'resource': ('ResourceCipher.cs', '1588ef6e6fe10250b3bf1c847e1c0ec943c5a05bd683ae8123609383457fe2ef', (33, 33)),
}


def _parse(data: bytes, sizes: tuple[int, int]) -> CipherParameters:
    text = data.decode('utf-8-sig')
    numbers = []
    for field, size in zip(('lpModulus', 'lpExponent'), sizes):
        matches = re.findall(r'Byte\[\]\s+' + field + r'\s*=\s*\{([^}]+)\}', text, re.S)
        if len(matches) != 1 or not re.fullmatch(r'(?:\s|,|0x[0-9a-fA-F]{2})+', matches[0]):
            raise ValueError('Unsupported PAK format metadata structure')
        octets = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]{2})', matches[0]))
        if len(octets) != size:
            raise ValueError('Unsupported PAK format metadata size')
        numbers.append(int.from_bytes(octets, 'little', signed=True))
    return CipherParameters(*numbers)


def parameters(tools: Path, kind: str) -> CipherParameters:
    if kind not in SOURCES:
        raise ValueError('Unknown PAK format metadata')
    filename, digest, sizes = SOURCES[kind]
    target = tools / 'format-metadata/re-pak-v1' / filename
    try:
        data = target.read_bytes()
    except FileNotFoundError:
        data = b''
    if len(data) > 16384 or hashlib.sha256(data).hexdigest() != digest:
        from .game_tools import download, _atomic_file
        data = download(BASE + filename, limit=16384)
        if hashlib.sha256(data).hexdigest() != digest:
            raise PreparationFailure('reader_checksum', 'The archive format metadata failed verification. No cached metadata was replaced. Retry preparation after checking the connection.')
        result = _parse(data, sizes)
        _atomic_file(target, data)
        return result
    return _parse(data, sizes)


def prepare(tools: Path) -> None:
    for kind in SOURCES:
        parameters(tools, kind)
