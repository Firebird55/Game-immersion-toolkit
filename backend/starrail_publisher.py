"""Original Global Star Rail voice packages and their compatible text generation."""
from functools import lru_cache
import struct
import time

from . import hoyo_publisher_voice as voices, sophon_assets as sophon
from .dialogue_catalog import DialogueCatalog, matching_release_commit
from .game_tools import _atomic_file

CHANNEL = voices.CHANNELS['starrail']
MARKERS = ('DesignData/Windows/M_DesignV.bytes', 'Asb/Windows/M_AsbV.bytes',
           'Lua/Windows/M_LuaV.bytes', 'Audio/AudioPackage/Windows/M_AudioV.bytes')
# The four published regular dub manifests match all 692 regular PCKs in
# this Global hotfix's AudioV. Two optional chapter PCKs per dub are separate.
VERIFIED_46 = 'sophon-d537972971037f62101f8850b9746a235899822335a397e50e4d69ce2c095723'
VERIFIED_46_TEXT = 'OSPRODWin4.6.0_D16854589_A16781679_L16781679'


@lru_cache(maxsize=2)
def _poll(period):
    return voices.descriptor(sophon.release(CHANNEL))[0]


def fingerprint():
    return _poll(int(time.monotonic() // 30))


def current(stamp):
    return voices.descriptor(sophon.release(CHANNEL))[0] == stamp


def revision_marker(raw):
    if len(raw) != 66 or raw[:8] != b'SRMI\x00\x03\x00\x01' or struct.unpack_from('<I', raw, 8)[0] != len(raw):
        raise ValueError('Unsupported Star Rail publisher revision marker.')
    revision, = struct.unpack_from('<I', raw, 24)
    if not revision:
        raise ValueError('Missing Star Rail publisher resource revision.')
    return revision


def release_title(stamp, version, revisions):
    design, assets, lua, audio = revisions
    if stamp == VERIFIED_46 and version == '4.6.0' and revisions == (16566615, 16566615, 16566587, 16566615):
        return VERIFIED_46_TEXT
    if audio != assets:
        raise ValueError('The separate Star Rail audio revision has no verified text binding yet.')
    return f'OSPRODWin{version}_D{design}_A{assets}_L{lua}'


def prepare(data_dir):
    build = sophon.release(CHANNEL)
    stamp, raw = voices.descriptor(build)
    directory = data_dir / 'tools' / 'sophon'
    files = sophon.manifest(directory, CHANNEL, tuple(build['manifests']['game']), MARKERS)
    revisions = []
    for suffix in MARKERS:
        marker = files['StarRail_Data/StreamingAssets/' + suffix]
        if marker.size != 66:
            raise ValueError('Unsupported Star Rail publisher revision marker.')
        revisions.append(revision_marker(marker.read(directory, 0, marker.size)))
    title = release_title(stamp, build['version'], tuple(revisions))
    catalog = DialogueCatalog('starrail', data_dir, revision=matching_release_commit('starrail', title))
    catalog.revision_title = title
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog
