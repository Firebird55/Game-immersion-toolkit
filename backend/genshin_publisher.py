"""Installation-free Genshin text and voice from the selected regional PC release."""
from functools import lru_cache
import json
import re
import time

from . import hoyo_publisher_voice as voices, sophon_assets as sophon
from .dialogue_catalog import DialogueCatalog, matching_release_commit
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

CHANNELS = {'global': 'genshin-global', 'cn': 'genshin-cn'}
ROOTS = {'genshin-global': 'GenshinImpact_Data/StreamingAssets/', 'genshin-cn': 'YuanShen_Data/StreamingAssets/'}
MARKERS = ('res_revision', 'silence_revision', 'data_revision')
INDEXES = ('data_versions_streaming', 'res_versions_streaming', 'silence_versions_streaming',
           'ctable_streaming.dat', 'svc_catalog')


@lru_cache(maxsize=4)
def _poll(region, _period):
    return voices.descriptor(sophon.release(CHANNELS[region]))[0]


def fingerprint(region='global'):
    return _poll(region, int(time.monotonic() // 30))


def current(stamp, region='global'):
    return voices.descriptor(sophon.release(CHANNELS[region]))[0] == stamp


def _narrative_payload(directory, build):
    channel = build['channel']
    root = ROOTS[channel]
    files = sophon.manifest(directory, channel, tuple(build['manifests']['game']), ('',))
    payload = {}
    for name, asset in files.items():
        if name.startswith(root):
            relative = name[len(root):]
            if relative.startswith('AssetBundles/') or relative in INDEXES:
                payload[relative] = (asset.size, asset.digest)
    if not all(key in payload for key in INDEXES) or not any(k.startswith('AssetBundles/blocks/') for k in payload):
        raise ValueError('The Genshin launcher release lacks a complete narrative resource inventory.')
    numbers = []
    for name in MARKERS:
        asset = files[root + 'AssetBundles/' + name]
        if not 0 < asset.size <= 16:
            raise ValueError('Unsupported Genshin revision marker.')
        value = asset.read(directory, 0, asset.size).decode('ascii')
        if not re.fullmatch('[0-9]+', value):
            raise ValueError('Unsupported Genshin revision marker.')
        numbers.append(value)
    return tuple(numbers), payload


def _catalog(directory, build, region):
    markers, payload = _narrative_payload(directory, build)
    revision = build['version'] + '_R%s_S%s_D%s' % markers
    if region == 'global':
        try:
            return matching_release_commit('genshin', 'OSRELWin' + revision)
        except PreparationFailure as error:
            if error.code != 'publisher_unavailable':
                raise
        reference = sophon.release(CHANNELS['cn'])
        if reference['version'] != build['version'] or _narrative_payload(directory, reference) != (markers, payload):
            raise PreparationFailure('publisher_unavailable',
                'A matching Global Genshin translation snapshot is unavailable. Retry after the catalog updates.')
    return matching_release_commit('genshin', 'CNRELWin' + revision)


def prepare(data_dir, region='global'):
    build = sophon.release(CHANNELS[region])
    stamp, raw = voices.descriptor(build)
    directory = data_dir / 'tools' / 'sophon'
    catalog = DialogueCatalog('genshin', data_dir, revision=_catalog(directory, build, region))
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog, build['version']


def inventory(data_dir, stamp, locale, *, unavailable_duplicates=None):
    return voices.inventory(data_dir, stamp, locale, 'genshin', unavailable_duplicates=unavailable_duplicates)


def extract(audio, tools):
    if previous := audio.get('original_publisher'):
        channels = []
        for stamp in (audio['publisher'], previous):
            if not voices.snapshot_available(tools, stamp, 'genshin'):
                raise ValueError('The Genshin voice release is unavailable.')
            descriptor = json.loads((tools / 'sophon' / 'releases' / stamp).read_bytes())
            channels.append(descriptor['channel'])
        if channels[0] != channels[1]:
            raise ValueError('A historical Genshin voice must use the same publisher edition.')
        audio = audio | {'publisher': previous}
    return voices.extract(audio, tools, 'genshin')
