"""Original Global Star Rail voice packages and their compatible text generation."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import struct
import json
import re
import time
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from . import hoyo_publisher_voice as voices, sophon_assets as sophon, starrail_hotfix as hotfix
from .dialogue_catalog import DialogueCatalog, matching_release_commit
from .game_tools import _atomic_file, download
from .hoyo_dialogue import voice_namespace

CHANNEL = voices.CHANNELS['starrail']
MARKERS = ('DesignData/Windows/M_DesignV.bytes', 'Asb/Windows/M_AsbV.bytes',
           'Lua/Windows/M_LuaV.bytes', 'Audio/AudioPackage/Windows/M_AudioV.bytes')
# The four published regular dub manifests match all 692 regular PCKs in
# this Global hotfix's AudioV. Two optional chapter PCKs per dub are separate.
VERIFIED_46 = 'sophon-d537972971037f62101f8850b9746a235899822335a397e50e4d69ce2c095723'
VERIFIED_46_TEXT = 'OSPRODWin4.6.0_D16854589_A16781679_L16781679'

# File sizes and checksums from the active Global 4.6 AudioV. These five
# optional files also occur unchanged in immutable public launcher manifests.
CHAPTER_PACKAGES = {
    'English': [(0, 114534158, '2976a5b39d03f8969f9a1175bbe92c72'), (1, 108221498, '9ad5d1fce777c34bbb86f625e06688c5')],
    'Chinese(PRC)': [(0, 81861322, '252ad846524e23056e5682609c81a8d2'), (1, 77872045, '01e12c4ef1bcde86b06fb5e4f4a632bb')],
    'Korean': [(0, 88310184, '79e92c0cdfba607d50ed27364ad41541')],
}
CHAPTER_MANIFESTS = {
    'en-us': ('4ea0efd4ec903433', '17e27e86e8c125fe5fdf0654cfe9d913', 1042647, 1982948),
    'zh-cn': ('d661cb6b87d9177d', '538657f961efa5766813f93b24963fb4', 857061, 1640633),
    'ko-kr': ('c0431fe18031980c', '841f5ca2186abebbcf3bd8854a9af42b', 869489, 1662850),
}


@lru_cache(maxsize=8)
def optional_files(directory, stamp, locale):
    field = sophon.VOICE_FIELDS[locale]
    if stamp != VERIFIED_46 or field not in CHAPTER_MANIFESTS:
        return {}
    language = voice_namespace('starrail', locale)
    prefix = 'StarRail_Data/Persistent/Audio/AudioPackage/Windows/' + language + '/'
    published = {prefix + f'External_del_4.6_chapter5_{i}.pck': (size, md5)
                 for i, size, md5 in CHAPTER_PACKAGES[language]}
    root = 'https://autopatchos.starrails.com/client/sophon/'
    build = '/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD'
    token, digest, compressed, size = CHAPTER_MANIFESTS[field]
    spec = (root + 'manifests' + build, f'manifest_{token}_{digest}', compressed, size, digest, root + 'chunks' + build)
    selected = sophon.manifest(directory, CHANNEL, spec, tuple(published))
    if {name: (asset.size, asset.digest) for name, asset in selected.items()} != published:
        raise ValueError('Optional Star Rail chapter packages differ from the released hotfix manifest.')
    return selected


@lru_cache(maxsize=2)
def _poll(region, period):
    return voices.descriptor(_release(region))[0]


def _release(region):
    channel = {'global': 'starrail-global', 'cn': 'starrail-cn'}[region]
    return hotfix.discover(sophon.release(channel))


def fingerprint(region='global'):
    return _poll(region, int(time.monotonic() // 30))


def current(stamp, region='global'):
    return voices.descriptor(_release(region))[0] == stamp


def revision_marker(raw):
    if len(raw) != 66 or raw[:8] != b'SRMI\x00\x03\x00\x01' or struct.unpack_from('<I', raw, 8)[0] != len(raw):
        raise ValueError('Unsupported Star Rail publisher revision marker.')
    revision, = struct.unpack_from('<I', raw, 24)
    if not revision:
        raise ValueError('Missing Star Rail publisher resource revision.')
    return revision


def release_revisions(directory, files):
    revisions = []
    for suffix in MARKERS:
        prefix, marker_name = ('StarRail_Data/StreamingAssets/' + suffix).rsplit('/', 1)
        marker = files[prefix + '/' + marker_name]
        if marker.size != 66:
            raise ValueError('Unsupported Star Rail publisher revision marker.')
        raw = marker.read(directory, 0, marker.size)
        revisions.append(revision_marker(raw))
        # SRMI stores the index MD5 as four little-endian words. The actual
        # index is a separately checksummed file in the same launcher build.
        digest = ''.join(f'{word:08x}' for word in struct.unpack_from('<4I', raw, 28))
        size, = struct.unpack_from('<Q', raw, 44)
        index_name = marker_name.removeprefix('M_').removesuffix('.bytes') + '_' + digest + '.bytes'
        index = files.get(prefix + '/' + index_name)
        if not size or index is None or (index.digest, index.size) != (digest, size):
            raise ValueError('The Star Rail resource index does not match its publisher revision marker.')
    return tuple(revisions)


def release_title(stamp, version, revisions):
    design, assets, lua, audio = revisions
    if stamp == VERIFIED_46 and version == '4.6.0' and revisions == (16566615, 16566615, 16566587, 16566615):
        return VERIFIED_46_TEXT
    if audio != assets:
        raise ValueError('The separate Star Rail audio revision has no verified text binding yet.')
    return f'OSPRODWin{version}_D{design}_A{assets}_L{lua}'


def _text_commit(title):
    try:
        return matching_release_commit('starrail', title)
    except HTTPError as error:
        if error.code not in (403, 429, 500, 502, 503, 504):
            raise
    except (TimeoutError, ConnectionError, URLError):
        pass
    for page in range(1, 6):
        url = f'https://api.github.com/repos/DimbreathBot/TurnBasedGameData/commits?sha=main&per_page=50&page={page}'
        try:
            rows = json.loads(download(url, limit=2 * 1024**2))
        except HTTPError as error:
            if error.code not in (403, 429):
                raise
            feed = download('https://github.com/DimbreathBot/TurnBasedGameData/commits/main.atom', limit=256 * 1024)
            for entry in ET.fromstring(feed).findall('{http://www.w3.org/2005/Atom}entry'):
                label = entry.findtext('{http://www.w3.org/2005/Atom}title', '').strip()
                ident = entry.findtext('{http://www.w3.org/2005/Atom}id', '')
                match = re.fullmatch('tag:github.com,2008:Grit::Commit/([0-9a-f]{40})', ident)
                if match and label == title:
                    return match[1]
            break
        for row in rows:
            if row['commit']['message'].splitlines()[0] == title and re.fullmatch('[0-9a-f]{40}', row['sha']):
                return row['sha']
        if len(rows) < 50:
            break
    raise ValueError('The matching Star Rail translation snapshot is unavailable. Retry after the catalog updates.')


class ReleasedCatalog(DialogueCatalog):
    """Use the author's mirror of the same Git commit if the primary host is busy."""
    def raw_file(self, relative):
        try:
            return super().raw_file(relative)
        except HTTPError as error:
            if error.code not in (403, 429, 500, 502, 503, 504):
                raise
        except (TimeoutError, ConnectionError, URLError):
            pass
        url = f'https://raw.githubusercontent.com/DimbreathBot/TurnBasedGameData/{self.revision}/{relative}'
        return self._bytes(relative, url)

    def caption_scripts(self):
        relative = 'Config/CutSceneCaption'
        try:
            return list(self.directory_json(relative, with_names=True))
        except HTTPError as error:
            if error.code not in (403, 429, 500, 502, 503, 504):
                raise
        except (TimeoutError, ConnectionError, URLError):
            pass
        # Walk immediate trees at the identical commit. Recursive tree and
        # contents listings can silently omit files in large repositories.
        repo = 'DimbreathBot/TurnBasedGameData'
        try:
            return self._caption_tree(repo, relative)
        except HTTPError as error:
            if error.code not in (403, 429, 500, 502, 503, 504):
                raise
        except (TimeoutError, ConnectionError, URLError):
            pass
        # GitHub's ordinary directory page carries an independent complete
        # listing, including its commit, path and total number of children.
        url = f'https://github.com/{repo}/tree/{self.revision}/{relative}'
        html = self._bytes('caption-directory/html', url, 8 * 1024**2)
        blocks = re.findall(rb'<script\b[^>]*data-target="react-app\.embeddedData"[^>]*>(.*?)</script>', html, re.S)
        hotfix.check(len(blocks) == 1)
        payload = json.loads(blocks[0])['payload']
        route = payload['codeViewTreeRoute']
        source = payload['codeViewLayoutRoute']['repo']
        hotfix.check(source['ownerLogin'] + '/' + source['name'] == repo and route['path'] == relative
                     and route['refInfo']['currentOid'] == self.revision and route['refInfo']['name'] == self.revision)
        items = route['tree']['items']
        hotfix.check(isinstance(items, list) and 0 < len(items) == route['tree']['totalCount'] <= 10000)
        names = [item['name'] for item in items if item['name'].endswith('.json')]
        hotfix.check(len(set(names)) == len(names) and names)
        for item in items:
            if item['name'].endswith('.json'):
                hotfix.check(re.fullmatch(r'[A-Za-z0-9_-]+_Caption\.json', item['name'])
                             and item['contentType'] == 'file' and item['path'] == relative + '/' + item['name'])
        def read(name):
            path = relative + '/' + name
            url = f'https://raw.githubusercontent.com/{repo}/{self.revision}/{path}'
            data = self._bytes(path, url, 2 * 1024**2)
            return name, data
        with ThreadPoolExecutor(max_workers=6) as pool:
            result, size = [], 0
            for name, data in pool.map(read, names):
                size += len(data)
                hotfix.check(size <= 32 * 1024**2)
                result.append((name, json.loads(data)))
        return result

    def _caption_tree(self, repo, relative):
        tree = self.revision
        for component in (*relative.split('/'), None):
            url = f'https://api.github.com/repos/{repo}/git/trees/{tree}'
            listing = json.loads(self._bytes('caption-directory/' + tree, url, 4 * 1024**2))
            hotfix.check(listing.get('truncated') is False)
            if component is not None:
                child, = (r for r in listing['tree'] if r['path'] == component and r['type'] == 'tree')
                tree = child['sha']
                hotfix.check(re.fullmatch('[0-9a-f]{40}', tree))
        items = [r for r in listing['tree'] if r['path'].endswith('.json')]
        hotfix.check(0 < len(items) <= 10000 and sum(r['size'] for r in items) <= 32 * 1024**2)
        def read(item):
            name, digest, size = item['path'], item['sha'], item['size']
            hotfix.check(re.fullmatch(r'[A-Za-z0-9_-]+_Caption\.json', name)
                         and re.fullmatch('[0-9a-f]{40}', digest) and 0 < size <= 2 * 1024**2
                         and item['type'] == 'blob' and item['mode'] == '100644')
            path = relative + '/' + name
            raw = self._bytes(path, f'https://raw.githubusercontent.com/{repo}/{self.revision}/{path}', size)
            hotfix.check(len(raw) == size and hashlib.sha1(f'blob {size}\0'.encode() + raw).hexdigest() == digest)
            return name, json.loads(raw)
        with ThreadPoolExecutor(max_workers=6) as pool:
            return list(pool.map(read, items))


def prepare(data_dir, region='global'):
    build = _release(region)
    stamp, raw = voices.descriptor(build)
    directory = data_dir / 'tools' / 'sophon'
    # Check all actual index bodies against this release before publishing
    # the translation and audio selection. Reuse unchanged index digests.
    for name in hotfix.INDEXES:
        hotfix.index(directory, build, name)
    revisions = tuple(build['hotfix']['indexes'][name][0] for name in hotfix.INDEXES)
    title = release_title(stamp, build['version'], revisions)
    catalog = ReleasedCatalog('starrail', data_dir, revision=_text_commit(title))
    catalog.revision_title = title
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog
