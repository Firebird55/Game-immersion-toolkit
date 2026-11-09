"""Installation-free Genshin text and voice from the same released PC build."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
from pathlib import PurePosixPath
import re
import struct
import time

from . import sophon_assets as sophon
from .dialogue_catalog import DialogueCatalog
from .game_tools import _atomic_file, download
from .hoyo_dialogue import voice_namespaces
from .preparation_errors import PreparationFailure
from .voice_assets import external_table, voice_hash

# This catalog publishes CNRELWin data. Its publisher channel must match.
CHANNEL = 'genshin-cn'
CATALOG_API = 'https://gitlab.com/api/v4/projects/Dimbreath%2Fanimegamedata2/repository'
MARKERS = ('res_revision', 'silence_revision', 'data_revision')


def _descriptor(build):
    raw = json.dumps(build, sort_keys=True, separators=(',', ':')).encode()
    return 'sophon-' + hashlib.sha256(raw).hexdigest(), raw


@lru_cache(maxsize=2)
def _poll(_period):
    return _descriptor(sophon.release(CHANNEL))[0]


def fingerprint():
    return _poll(int(time.monotonic() // 30))


def current(stamp):
    return _descriptor(sophon.release(CHANNEL))[0] == stamp


def matching_commit(title):
    for page in range(1, 6):
        commits = json.loads(download(CATALOG_API + f'/commits?ref_name=main&per_page=50&page={page}', limit=2 * 1024**2))
        for row in commits:
            if row['title'] == title and re.fullmatch('[0-9a-f]{40}', row['id']):
                return row['id']
        if len(commits) < 50:
            break
    raise PreparationFailure('publisher_unavailable',
        'The matching Genshin translation snapshot is unavailable. Retry after the catalog updates.')


def prepare(data_dir):
    build = sophon.release(CHANNEL)
    stamp, raw = _descriptor(build)
    directory = data_dir / 'tools' / 'sophon'
    files = sophon.manifest(directory, CHANNEL, tuple(build['manifests']['game']), MARKERS)
    numbers = []
    for name in MARKERS:
        asset = files['YuanShen_Data/StreamingAssets/AssetBundles/' + name]
        if not 0 < asset.size <= 16:
            raise ValueError('Unsupported Genshin revision marker.')
        value = asset.read(directory, 0, asset.size).decode('ascii')
        if not re.fullmatch('[0-9]+', value):
            raise ValueError('Unsupported Genshin revision marker.')
        numbers.append(value)
    title = 'CNRELWin' + build['version'] + '_R%s_S%s_D%s' % tuple(numbers)
    catalog = DialogueCatalog('genshin', data_dir, revision=matching_commit(title))
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog, build['version']


@lru_cache(maxsize=12)
def _files(directory, stamp, locale):
    if locale not in sophon.VOICE_FIELDS or not re.fullmatch('sophon-[0-9a-f]{64}', stamp):
        raise ValueError('Invalid Genshin publisher identity.')
    path = directory / 'releases' / stamp
    if path.stat().st_size > 64 * 1024:
        raise ValueError('Invalid Genshin publisher descriptor.')
    raw = path.read_bytes()
    build = json.loads(raw)
    if 'sophon-' + hashlib.sha256(raw).hexdigest() != stamp or build['channel'] != CHANNEL:
        raise ValueError('Genshin publisher descriptor has changed.')
    spec = tuple(build['manifests'][sophon.VOICE_FIELDS[locale]])
    files = sophon.manifest(directory, CHANNEL, spec, ('.pck',))
    allowed = set(voice_namespaces('genshin', locale))
    result = {}
    for name, asset in files.items():
        parts = PurePosixPath(name).parts
        if (len(parts) == 5 and parts[0] == 'YuanShen_Data' and parts[1] in ('Persistent', 'StreamingAssets')
                and parts[2] == 'AudioAssets' and parts[3] in allowed):
            result[name] = asset
    if not result:
        raise ValueError('The selected publisher voice packages are unavailable.')
    return result


@lru_cache(maxsize=256)
def _table(directory, stamp, locale, name):
    asset = _files(directory, stamp, locale)[name]
    return external_table(name, asset.size, lambda start, count: asset.read(directory, start, count))


def inventory(data_dir, stamp, locale):
    directory = data_dir / 'tools' / 'sophon'
    files = _files(directory, stamp, locale)
    entries = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for layer in ('StreamingAssets', 'Persistent'):
            current, ambiguous = {}, set()
            paths = sorted(p for p in files if p.split('/')[1] == layer)
            for rows in pool.map(lambda name: _table(directory, stamp, locale, name), paths):
                for row in rows:
                    if row.file_id in current:
                        ambiguous.add(row.file_id)
                    current[row.file_id] = {'publisher': stamp, 'package': row.package}
            entries.update(current)
            for identity in ambiguous:
                entries.pop(identity, None)
    if not entries:
        raise ValueError('The selected Genshin publisher packages contain no external recordings.')
    return entries


def extract(audio, tools):
    source, locale, stamp = audio['source'], audio['locale'], audio['publisher']
    identity = voice_hash(source)
    if (locale not in sophon.VOICE_FIELDS or re.split(r'[/\\]', source, maxsplit=1)[0] not in voice_namespaces('genshin', locale)
            or f'{identity:016x}' != audio['file_id']):
        raise ValueError('Genshin voice identity does not match the selected original language.')
    directory, name = tools / 'sophon', audio['package']
    entry, = [row for row in _table(directory, stamp, locale, name) if row.file_id == identity]
    data = _files(directory, stamp, locale)[name].read(directory, entry.offset, entry.size)
    if data[:4] != b'RIFF' or len(data) < 12 or len(data) != struct.unpack_from('<I', data, 4)[0] + 8:
        raise ValueError('Genshin publisher voice is incomplete.')
    return data
