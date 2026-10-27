"""Private, immutable data snapshots for authored dialogue and localization.

Only fixed upstream data sources are read. No downloaded code is executed.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.parse import quote

from .game_tools import download, _atomic_file

SOURCES = {
    'genshin': ('gitlab', 'Dimbreath/animegamedata2', 'main'),
    'starrail': ('gitlab', 'Dimbreath/turnbasedgamedata', 'main'),
    'endfield': ('github', 'rmxlinux/EndfieldData', 'main'),
}


class DialogueCatalog:
    def __init__(self, game, directory):
        self.host, self.repository, branch = SOURCES[game]
        self.directory = Path(directory) / 'dialogue-catalog'
        if self.host == 'gitlab':
            api = f'https://gitlab.com/api/v4/projects/{quote(self.repository, safe="")}/repository'
            self.api = api
            metadata = json.loads(download(api + '/branches/' + branch))
            self.revision = metadata['commit']['id']
            self.revision_title = metadata['commit'].get('title') or metadata['commit'].get('message', '').split('\n', 1)[0]
        else:
            metadata = json.loads(download(f'https://api.github.com/repos/{self.repository}/commits/{branch}'))
            self.revision = metadata['sha']
            self.revision_title = metadata.get('commit', {}).get('message', '').split('\n', 1)[0]
        if not re.fullmatch('[a-f0-9]{40}', self.revision):
            raise ValueError('Official dialogue catalog revision is unavailable.')
        self.root = self.directory / self.revision

    def _bytes(self, name, url, limit=128 * 1024 * 1024):
        # Cache identity includes the immutable revision and content digest.
        path = self.root / name
        receipt = path.with_name(path.name + '.sha256')
        if path.is_file() and receipt.is_file():
            data = path.read_bytes()
            if len(data) <= limit and hashlib.sha256(data).hexdigest() == receipt.read_text():
                return data
        data = download(url, limit=limit)
        _atomic_file(path, data)
        _atomic_file(receipt, hashlib.sha256(data).hexdigest().encode())
        return data

    def file(self, relative, *, optional=False):
        from urllib.error import HTTPError
        if self.host == 'gitlab':
            url = f'https://gitlab.com/{self.repository}/-/raw/{self.revision}/{relative}'
        else:
            url = f'https://raw.githubusercontent.com/{self.repository}/{self.revision}/{relative}'
        try:
            return json.loads(self._bytes(relative, url))
        except HTTPError as error:
            if optional and error.code == 404:
                return {}
            raise

    def directory_json(self, relative):
        if self.host != 'gitlab':
            raise ValueError('Directory snapshots are supported only for fixed GitLab catalogs.')
        name = relative.replace('/', '-') + '.tar.gz'
        url = self.api + '/archive.tar.gz?sha=' + self.revision + '&path=' + quote(relative)
        data = self._bytes(name, url)
        total = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for item in archive:
                path = PurePosixPath(item.name)
                if path.is_absolute() or '..' in path.parts or item.issym() or item.islnk():
                    raise ValueError('Unsafe dialogue catalog archive.')
                if not item.isfile() or not item.name.endswith('.json'):
                    continue
                total += item.size
                if item.size > 128 * 1024 * 1024 or total > 512 * 1024 * 1024:
                    raise ValueError('Dialogue catalog expands beyond its size limit.')
                # Parse in memory; never extract upstream file paths to the host.
                yield json.load(archive.extractfile(item))

    def directory_text(self, relative, suffix='.txt'):
        """Read bounded UTF-8 assets without extracting untrusted archive paths."""
        directory = PurePosixPath(relative)
        if (self.host != 'gitlab' or directory.is_absolute() or '..' in directory.parts
                or not relative or '\\' in relative or ':' in relative
                or suffix not in {'.txt', '.srt'}):
            raise ValueError('Unsupported dialogue text directory.')
        name = relative.replace('/', '-') + '-text.tar.gz'
        url = self.api + '/archive.tar.gz?sha=' + self.revision + '&path=' + quote(relative)
        data = self._bytes(name, url)
        total, count, seen = 0, 0, set()
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for item in archive:
                path = PurePosixPath(item.name)
                if (path.is_absolute() or '..' in path.parts or '\\' in item.name
                        or ':' in item.name or item.issym() or item.islnk()):
                    raise ValueError('Unsafe dialogue catalog archive.')
                if not item.isfile():
                    continue
                total += item.size
                count += 1
                if item.size > 4 * 1024 * 1024 or total > 128 * 1024 * 1024 or count > 50000:
                    raise ValueError('Dialogue text archive expands beyond its size limit.')
                # GitLab prefixes one repository/revision directory. Require the
                # requested path beneath it; never join an arbitrary basename.
                parts = path.parts[1:]
                if tuple(parts[:len(directory.parts)]) != directory.parts:
                    raise ValueError('Dialogue text archive crosses its requested directory.')
                identity = PurePosixPath(*parts[len(directory.parts):]).as_posix()
                if not item.name.endswith(suffix):
                    continue
                if identity in seen:
                    raise ValueError('Duplicate dialogue text identity in archive.')
                seen.add(identity)
                yield identity, archive.extractfile(item).read().decode('utf-8-sig')


def selected_tables(catalog, mapping, source, targets, *, medium=False, prefix='TextMap/TextMap'):
    from .languages import resolve_locale
    selected = {source, *(code for target in targets if (code := resolve_locale(target, mapping)))}
    tables = {}
    for locale in sorted(selected):
        codes = mapping[locale]
        if isinstance(codes, str):
            codes = (codes,)
        values = {}
        # Newer Genshin dialogue also lives in its separate Medium hash space.
        for stem in ([prefix.replace('/TextMap', '/TextMap_Medium', 1)] if medium else []) + [prefix]:
            for code in codes:
                values.update(catalog.file(stem + code + '.json', optional=medium and stem != prefix))
        if not values or not all(isinstance(value, str) for value in values.values()):
            raise ValueError('The selected official subtitle table is empty or unsupported.')
        tables[locale] = values
    return tables
