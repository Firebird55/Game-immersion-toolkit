"""Installation-free Genshin text and voice from the selected regional PC release."""
from functools import lru_cache
import hashlib
from http.client import IncompleteRead
import json
import re
import time
from subprocess import SubprocessError
from urllib.error import HTTPError, URLError
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from . import hoyo_publisher_voice as voices, sophon_assets as sophon, genshin_hotfix as hotfix
from .dialogue_catalog import DialogueCatalog, matching_release_commit
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

CHANNELS = {'global': 'genshin-global', 'cn': 'genshin-cn'}
ROOTS = {'genshin-global': 'GenshinImpact_Data/StreamingAssets/', 'genshin-cn': 'YuanShen_Data/StreamingAssets/'}
MARKERS = ('res_revision', 'silence_revision', 'data_revision')
INDEXES = ('data_versions_streaming', 'res_versions_streaming', 'silence_versions_streaming',
           'ctable_streaming.dat', 'svc_catalog')
NETWORK_ERRORS = (URLError, TimeoutError, ConnectionError, IncompleteRead)


class CatalogSelection(str):
    """Keep the immutable release-title acceptance separate from content rows."""
    def __new__(cls, revision, receipt):
        result = str.__new__(cls, revision)
        result.receipt = receipt
        return result


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

    def file(self, relative, *, optional=False):
        if relative.startswith('TextMap/') and getattr(self, 'official_source', None) is not None:
            return self.official_source.file(relative)
        return super().file(relative, optional=optional)

    def _bytes(self, name, url, limit=128 * 1024 * 1024):
        path = PurePosixPath(name)
        source = urlsplit(url)
        allowed = (source.scheme == 'https' and not source.query and source.netloc == 'raw.githubusercontent.com'
                   and source.path.startswith(f'/DimbreathBot/AnimeGameData/{self.revision}/')
                   or source.scheme == 'https' and source.netloc == 'gitlab.com'
                   and (source.path.startswith('/Dimbreath/animegamedata2/-/raw/' + self.revision + '/')
                        or source.path.startswith('/api/v4/projects/Dimbreath%2Fanimegamedata2/repository/archive.tar.gz')
                        and ('sha=' + self.revision) in source.query))
        if (not name or path.is_absolute() or path.as_posix() != name or '..' in path.parts or '\\' in name or ':' in name
                or source.fragment or not allowed):
            raise ValueError('The Genshin helper source is outside the allowlisted immutable catalog.')
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
    return voices.descriptor(_release(region))[0]


def _release(region):
    return hotfix.discover(sophon.release(CHANNELS[region]))


def fingerprint(region='global'):
    return _poll(region, int(time.monotonic() // 30))


def current(stamp, region='global'):
    return voices.descriptor(_release(region))[0] == stamp


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
    if 'hotfix' in build:
        revisions = build['hotfix']['revisions']
        markers = tuple(str(revisions[name][0]) for name in ('res', 'silence', 'design'))
    revision = build['version'] + '_R%s_S%s_D%s' % markers
    mirror = None
    repository = 'Dimbreath/animegamedata2'
    reference_inventory = None

    def selected(title, commit):
        if not isinstance(commit, str) or not re.fullmatch('[a-f0-9]{40}', commit):
            raise ValueError('Invalid immutable Genshin helper revision.')
        narrative = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return CatalogSelection(commit, {'schema': 'genshin-binding-selection-v1', 'game': 'genshin',
            'publisher': voices.descriptor(build)[0], 'region': region, 'version': build['version'],
            'markers': dict(zip(('res', 'silence', 'design'), markers)), 'narrative_sha256': narrative,
            'repository': repository, 'revision': commit, 'title': title,
            'source_region': 'global' if title.startswith('OSRELWin') else 'cn',
            'reference_narrative_sha256': reference_inventory})

    def find(title):
        nonlocal mirror, repository
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
            repository = 'DimbreathBot/AnimeGameData'
            return mirror[title]
        raise PreparationFailure('publisher_unavailable',
            'The Genshin metadata mirror has no unique translation snapshot for the requested regional release.')

    if region == 'global':
        try:
            title = 'OSRELWin' + revision
            return selected(title, find(title))
        except PreparationFailure as error:
            if error.code != 'publisher_unavailable':
                raise
        reference = _release('cn') if 'hotfix' in build else sophon.release(CHANNELS['cn'])
        reference_payload = _narrative_payload(directory, reference)
        if (reference['version'] != build['version']
                or reference_payload != _narrative_payload(directory, build)
                or 'hotfix' in build and reference['hotfix'] != build['hotfix']):
            raise PreparationFailure('publisher_unavailable',
                'A matching Global Genshin translation snapshot is unavailable. Retry after the catalog updates.')
        reference_inventory = hashlib.sha256(json.dumps(reference_payload[1], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    title = 'CNRELWin' + revision
    return selected(title, find(title))


def prepare(data_dir, region='global', *, original_text=False):
    build = _release(region)
    stamp, raw = voices.descriptor(build)
    directory = data_dir / 'tools' / 'sophon'
    for name in hotfix.INDEXES:
        hotfix.index(directory, build, name)
    selection = _catalog(directory, build, region)
    catalog = ReleaseCatalog('genshin', data_dir, revision=selection)
    catalog.selection_receipt = selection.receipt
    catalog.bootstrap_receipt = getattr(build, 'helper_provenance', None)
    if original_text:
        from .genshin_official_source import prepare as prepare_original
        catalog.official_source = prepare_original(data_dir / 'tools' / 'genshin-original-text', build)
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog, build['version']


def preflight(data_dir, region='global', *, study_locales, target_locales=(), catalog=None, catalog_publisher=None):
    """Read only official discovery/manifests/indexes before large game data.

    The optional catalog must already be authenticated for this exact publisher
    generation. Without it the quote explicitly bounds all design packages.
    """
    from .genshin_download_plan import plan, VOICES
    from .hoyo_dialogue import voice_namespaces
    if region not in CHANNELS or not study_locales or any(locale not in VOICES for locale in study_locales):
        raise ValueError('Choose a supported Genshin publisher edition and study language.')
    build = _release(region)
    directory = data_dir / 'tools' / 'sophon'
    native_name = 'GenshinImpact.exe' if region == 'global' else 'YuanShen.exe'
    game_files = sophon.manifest(directory, build['channel'], tuple(build['manifests']['game']), ('.exe',))
    if native_name not in game_files:
        raise ValueError('The official Genshin native metadata input is missing.')
    localized = {}
    data_name = ROOTS[build['channel']].split('/')[0]
    for locale in set(study_locales):
        files = sophon.manifest(directory, build['channel'], tuple(build['manifests'][sophon.VOICE_FIELDS[locale]]), ('.pck',))
        allowed = set(voice_namespaces('genshin', locale))
        regular = {name: item for name, item in files.items()
                   if len(PurePosixPath(name).parts) == 5 and PurePosixPath(name).parts[0] == data_name
                   and PurePosixPath(name).parts[1] in {'StreamingAssets', 'Persistent'}
                   and PurePosixPath(name).parts[2] == 'AudioAssets' and PurePosixPath(name).parts[3] in allowed}
        localized[locale] = hotfix.files(directory, build, locale, regular)
    designs = {}
    for line in hotfix.index(directory, build, 'design').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        name = row['remoteName']
        if name in designs:
            raise ValueError('The official Genshin design manifest has duplicate identities.')
        designs[name] = row
    return plan(build, game_files[native_name], localized, designs, study_locales=study_locales,
                target_locales=target_locales, catalog=catalog, catalog_publisher=catalog_publisher)


def inventory(data_dir, stamp, locale, *, unavailable_duplicates=None):
    return voices.inventory(data_dir, stamp, locale, 'genshin', unavailable_duplicates=unavailable_duplicates)


def movie_assets(tools, stamp):
    from pathlib import PurePosixPath
    directory = tools / 'sophon'
    if not voices.snapshot_available(tools, stamp, 'genshin'):
        raise ValueError('The Genshin movie release is unavailable.')
    build = json.loads((directory / 'releases' / stamp).read_bytes())
    channel = build['channel']
    parent = PurePosixPath(ROOTS[channel]) / 'VideoAssets' / 'StandaloneWindows64'
    regular = {name: asset for name, asset in sophon.manifest(directory, channel, tuple(build['manifests']['game']), ('.usm',)).items()
               if PurePosixPath(name).parent == parent}
    if 'hotfix' in build:
        return hotfix.movie_files(directory, build, regular)
    return {PurePosixPath(name).stem: asset for name, asset in regular.items()}


def extract(audio, tools):
    if 'movie' in audio:
        from . import genshin_opening_soundtrack as opening
        interval = (audio.get('start_ms'), audio.get('end_ms'))
        if (audio.get('movie') != opening.MOVIE or audio.get('locale') != 'ja'
                or audio.get('track_sha256') not in opening.TRACKS.values()
                or interval not in {row[:2] for row in opening.JAPANESE_LINES.values()}):
            raise ValueError('Invalid Japanese Genshin opening performance.')
        asset = movie_assets(tools, audio['publisher']).get(opening.MOVIE)
        if asset is None:
            raise ValueError('The selected release lacks the Genshin opening movie.')
        return opening.verified_track(asset, tools / 'sophon', audio['track_sha256'])[1]
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
