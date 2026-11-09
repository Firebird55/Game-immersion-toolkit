"""Resolve original in-language Wwise recordings in released HoYoPlay packages."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
from pathlib import PurePosixPath
import re
import struct

from . import sophon_assets as sophon
from .hoyo_dialogue import voice_namespaces
from .voice_assets import external_table, voice_hash

CHANNELS = {'genshin': 'genshin-cn', 'starrail': 'starrail-global', 'zzz': 'zzz-global'}


def descriptor(build):
    raw = json.dumps(build, sort_keys=True, separators=(',', ':')).encode()
    return 'sophon-' + hashlib.sha256(raw).hexdigest(), raw


def snapshot_available(tools, stamp, game):
    if not isinstance(stamp, str) or not re.fullmatch('sophon-[0-9a-f]{64}', stamp):
        return False
    path = tools / 'sophon' / 'releases' / stamp
    if not path.is_file() or path.stat().st_size > 64 * 1024:
        return False
    raw = path.read_bytes()
    return stamp == 'sophon-' + hashlib.sha256(raw).hexdigest() and json.loads(raw)['channel'] == CHANNELS[game]


@lru_cache(maxsize=12)
def _files(directory, stamp, locale, game):
    channel = CHANNELS[game]
    if locale not in sophon.VOICE_FIELDS or not re.fullmatch('sophon-[0-9a-f]{64}', stamp):
        raise ValueError('Invalid HoYoPlay publisher identity.')
    path = directory / 'releases' / stamp
    if path.stat().st_size > 64 * 1024:
        raise ValueError('Invalid HoYoPlay publisher descriptor.')
    raw = path.read_bytes()
    build = json.loads(raw)
    if 'sophon-' + hashlib.sha256(raw).hexdigest() != stamp or build['channel'] != channel:
        raise ValueError('HoYoPlay publisher descriptor has changed.')
    spec = tuple(build['manifests'][sophon.VOICE_FIELDS[locale]])
    files = sophon.manifest(directory, channel, spec, ('.pck',))
    allowed = set(voice_namespaces(game, locale))
    result = {}
    for name, asset in files.items():
        parts = PurePosixPath(name).parts
        if game == 'zzz':
            from .zzz_assets import VOICE_FOLDERS
            if parts[:-1] == ('ZenlessZoneZero_Data', 'StreamingAssets', 'Audio', 'Windows', 'Full', VOICE_FOLDERS[locale]):
                result[name] = asset
            continue
        if len(parts) < 4 or parts[1] not in ('Persistent', 'StreamingAssets') or parts[-2] not in allowed:
            continue
        if (game == 'genshin' and parts[0] == 'YuanShen_Data' and parts[2:-2] == ('AudioAssets',) or
                game == 'starrail' and parts[0] == 'StarRail_Data' and parts[2:-2] == ('Audio', 'AudioPackage', 'Windows')):
            result[name] = asset
    if not result:
        raise ValueError('The selected publisher voice packages are unavailable.')
    return result


def _optional_files(directory, stamp, locale, game):
    if game == 'starrail':
        from .starrail_publisher import optional_files
        return optional_files(directory, stamp, locale)
    return {}


def _archive(directory, stamp, locale, name, game):
    regular = _files(directory, stamp, locale, game)
    if name in regular:
        return regular[name]
    return _optional_files(directory, stamp, locale, game)[name]


@lru_cache(maxsize=256)
def _table(directory, stamp, locale, name, game):
    asset = _archive(directory, stamp, locale, name, game)
    return external_table(name, asset.size, lambda start, count: asset.read(directory, start, count))


def inventory(data_dir, stamp, locale, game, *, wanted=None):
    directory = data_dir / 'tools' / 'sophon'
    files = _files(directory, stamp, locale, game) | _optional_files(directory, stamp, locale, game)
    entries = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for layer in ('StreamingAssets', 'Persistent'):
            current, ambiguous = {}, set()
            paths = sorted(p for p in files if p.split('/')[1] == layer)
            for rows in pool.map(lambda name: _table(directory, stamp, locale, name, game), paths):
                for row in rows:
                    if wanted is not None and row.file_id not in wanted:
                        continue
                    if row.file_id in current:
                        ambiguous.add(row.file_id)
                    current[row.file_id] = {'publisher': stamp, 'package': row.package}
            entries.update(current)
            for identity in ambiguous:
                entries.pop(identity, None)
    if not entries:
        raise ValueError('The selected HoYoPlay publisher packages contain no external recordings.')
    return entries


def extract(audio, tools, game):
    source, locale, stamp = audio['source'], audio['locale'], audio['publisher']
    identity = voice_hash(source)
    if (locale not in sophon.VOICE_FIELDS or re.split(r'[/\\]', source, maxsplit=1)[0] not in voice_namespaces(game, locale)
            or f'{identity:016x}' != audio['file_id']):
        raise ValueError('HoYoPlay voice identity does not match the selected original language.')
    directory, name = tools / 'sophon', audio['package']
    entry, = [row for row in _table(directory, stamp, locale, name, game) if row.file_id == identity]
    data = _archive(directory, stamp, locale, name, game).read(directory, entry.offset, entry.size)
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE' or len(data) != struct.unpack_from('<I', data, 4)[0] + 8:
        raise ValueError('HoYoPlay publisher voice is incomplete.')
    return data
