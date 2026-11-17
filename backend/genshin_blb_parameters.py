"""Allowlisted immutable community codec descriptions, never community audio.

The frozen seed is retried first. A caller may explicitly request one live
refresh after an official payload rejects it. Nothing here accepts or activates
a game generation; publisher parsing and its acceptance receipt do that.
"""
import hashlib
import json
from pathlib import Path
import re

from .game_tools import _atomic_file
from .hoyo_dispatch_metadata import fetch as download
from .genshin_blb import parameter_data
from .prebuilt_readers import _no_links


REPOSITORY = 'Escartem/AnimeStudio'
RELATIVE = 'AnimeStudio/Crypto/CryptoHelper.cs'
SEED = {'revision': '76234e9f6f5a839504f41f9612719529fe2309a5',
        'sha256': '68d3169d9d0bce93c1a70b858ac0843136fb197a426cb040ab9e5f85f0b0688d'}
LIMIT = 1024 * 1024


def check(value):
    if not value:
        raise ValueError('The controlled Genshin codec description is unavailable or inconsistent.')


def load(directory, *, pinned=None, refresh=False):
    check(not (pinned is not None and refresh))
    directory = Path(directory).absolute(); _no_links(directory); directory.mkdir(parents=True, exist_ok=True)
    selected = dict(SEED) if pinned is None else dict(pinned)
    if refresh:
        raw = download(f'https://api.github.com/repos/{REPOSITORY}/commits/master', limit=2 * LIMIT)
        selected = {'revision': json.loads(raw)['sha']}
    revision = selected.get('revision')
    expected = selected.get('sha256')
    check(isinstance(revision, str) and re.fullmatch('[a-f0-9]{40}', revision)
          and (expected is None or isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected)))
    path = directory / (revision + '.private-source')
    receipt_path = directory / (revision + '.json')
    raw = None
    try:
        _no_links(path); _no_links(receipt_path)
        receipt = json.loads(receipt_path.read_bytes())
        candidate = path.read_bytes()
        digest = hashlib.sha256(candidate).hexdigest()
        if (0 < len(candidate) <= LIMIT and receipt == {'revision': revision, 'sha256': digest, 'bytes': len(candidate)}
                and (expected is None or digest == expected)):
            raw = candidate
    except (OSError, ValueError, TypeError):
        pass
    if raw is None:
        raw = download(f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{RELATIVE}', limit=LIMIT)
    digest = hashlib.sha256(raw).hexdigest()
    check(expected is None or digest == expected)
    parameters = parameter_data(raw)  # Strict bounded grammar before any cache publication.
    receipt = {'revision': revision, 'sha256': digest, 'bytes': len(raw)}
    _atomic_file(path, raw); _atomic_file(receipt_path, json.dumps(receipt, sort_keys=True).encode())
    target = directory / (hashlib.sha256(parameters).hexdigest() + '.private-parameters')
    _no_links(target); _atomic_file(target, parameters)
    return target, {'policy': 'controlled-community-codec-description-v1', 'repository': REPOSITORY,
                    'path': RELATIVE, **receipt, 'parameters_sha256': hashlib.sha256(parameters).hexdigest()}
