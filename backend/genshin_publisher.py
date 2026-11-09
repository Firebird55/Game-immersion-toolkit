"""Installation-free Genshin text and voice from the same released PC build."""
from functools import lru_cache
import re
import time

from . import sophon_assets as sophon
from .dialogue_catalog import DialogueCatalog, matching_release_commit
from .game_tools import _atomic_file
from . import hoyo_publisher_voice as voices

# This catalog publishes CNRELWin data. Its publisher channel must match.
CHANNEL = 'genshin-cn'
MARKERS = ('res_revision', 'silence_revision', 'data_revision')


@lru_cache(maxsize=2)
def _poll(_period):
    return voices.descriptor(sophon.release(CHANNEL))[0]


def fingerprint():
    return _poll(int(time.monotonic() // 30))


def current(stamp):
    return voices.descriptor(sophon.release(CHANNEL))[0] == stamp


def prepare(data_dir):
    build = sophon.release(CHANNEL)
    stamp, raw = voices.descriptor(build)
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
    catalog = DialogueCatalog('genshin', data_dir, revision=matching_release_commit('genshin', title))
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog, build['version']


def inventory(data_dir, stamp, locale):
    return voices.inventory(data_dir, stamp, locale, 'genshin')


def extract(audio, tools):
    return voices.extract(audio, tools, 'genshin')
