"""Installation-free Genshin text and voice from the selected regional PC release."""
from functools import lru_cache
from http.client import IncompleteRead
import json
import re
import time
from subprocess import SubprocessError
from urllib.error import HTTPError, URLError

from . import hoyo_publisher_voice as voices, sophon_assets as sophon
from .dialogue_catalog import DialogueCatalog, matching_release_commit
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

CHANNELS = {'global': 'genshin-global', 'cn': 'genshin-cn'}
ROOTS = {'genshin-global': 'GenshinImpact_Data/StreamingAssets/', 'genshin-cn': 'YuanShen_Data/StreamingAssets/'}
MARKERS = ('res_revision', 'silence_revision', 'data_revision')
INDEXES = ('data_versions_streaming', 'res_versions_streaming', 'silence_versions_streaming',
           'ctable_streaming.dat', 'svc_catalog')
NETWORK_ERRORS = (URLError, TimeoutError, ConnectionError, IncompleteRead)


class ReleaseCatalog(DialogueCatalog):
    """Retry public Genshin metadata at the very same immutable Git commit."""
    def raw_file(self, relative):
        try:
            return super().raw_file(relative)
        except NETWORK_ERRORS as error:
            if isinstance(error, HTTPError) and error.code == 404:
                raise
            url = f'https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/{self.revision}/{relative}'
            return self._bytes(relative, url)

    def _bytes(self, name, url, limit=128 * 1024 * 1024):
        try:
            return super()._bytes(name, url, limit)
        except NETWORK_ERRORS:
            match = re.fullmatch(r'(BinOutput-(?:Talk|Voice|Avatar)|(Readable|Subtitle)-[A-Z]{2,3})(-text)?\.tar\.gz', name)
            if not match or bool(match[2]) != bool(match[3]):
                raise
            from .genshin_archive_mirror import fetch_trees
            try:
                fetch_trees(self, trees=(match[1].replace('-', '/'),))
            except (SubprocessError, ValueError, OSError) as error:
                raise PreparationFailure('publisher_unavailable',
                    'The primary Genshin catalog and its same-version mirror could not supply this directory. '
                    'Retry later, or install Git to enable the mirror and refresh.') from error
            return super()._bytes(name, url, limit)


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
    mirror = None

    def find(title):
        nonlocal mirror
        if mirror is None:
            try:
                return matching_release_commit('genshin', title)
            except NETWORK_ERRORS:
                from .genshin_archive_mirror import release_titles
                try:
                    mirror = release_titles()
                except (SubprocessError, ValueError, OSError) as error:
                    raise PreparationFailure('publisher_unavailable',
                        'The Genshin translation catalog and its release mirror are unavailable. '
                        'Retry later, or install Git to enable the mirror and refresh.') from error
        if title in mirror:
            return mirror[title]
        raise PreparationFailure('publisher_unavailable',
            'The Genshin metadata mirror has no unique translation snapshot for the requested regional release.')

    if region == 'global':
        try:
            return find('OSRELWin' + revision)
        except PreparationFailure as error:
            if error.code != 'publisher_unavailable':
                raise
        reference = sophon.release(CHANNELS['cn'])
        if reference['version'] != build['version'] or _narrative_payload(directory, reference) != (markers, payload):
            raise PreparationFailure('publisher_unavailable',
                'A matching Global Genshin translation snapshot is unavailable. Retry after the catalog updates.')
    return find('CNRELWin' + revision)


def prepare(data_dir, region='global'):
    build = sophon.release(CHANNELS[region])
    stamp, raw = voices.descriptor(build)
    directory = data_dir / 'tools' / 'sophon'
    catalog = ReleaseCatalog('genshin', data_dir, revision=_catalog(directory, build, region))
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog, build['version']


def inventory(data_dir, stamp, locale, *, unavailable_duplicates=None):
    return voices.inventory(data_dir, stamp, locale, 'genshin', unavailable_duplicates=unavailable_duplicates)


def movie_names(data_dir, stamp):
    from pathlib import PurePosixPath
    directory = data_dir / 'tools' / 'sophon'
    if not voices.snapshot_available(data_dir / 'tools', stamp, 'genshin'):
        raise ValueError('The Genshin movie release is unavailable.')
    build = json.loads((directory / 'releases' / stamp).read_bytes())
    channel = build['channel']
    parent = PurePosixPath(ROOTS[channel]) / 'VideoAssets' / 'StandaloneWindows64'
    return {p.stem for name in sophon.manifest(directory, channel, tuple(build['manifests']['game']), ('.usm',))
            if (p := PurePosixPath(name)).parent == parent}


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
