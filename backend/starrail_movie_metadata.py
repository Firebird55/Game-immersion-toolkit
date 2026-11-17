"""Private, data-only parameters for publisher movie audio, pinned per snapshot."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from .game_tools import _atomic_file
from .publisher_http import download

REPOSITORY = 'Furina1027/hoyo-files'
FILES = ('hkrpg_history.json', 'hkrpg_keys.json', 'hkrpg_keys_versions.json')
LIMIT = 8 * 1024**2
SOURCE_LIMITS = dict(zip(FILES, (2 * 1024**2, 384 * 1024, 384 * 1024)))
SOURCE_SCHEMA = 'proxy-starrail-movie-description-source-v1'
_ROOTS = {}


class MovieFormatUnavailable(ValueError):
    pass


def check(value):
    if not value:
        raise MovieFormatUnavailable('Matching Star Rail movie format metadata is unavailable. Refresh game data and retry.')


def latest_revision():
    try:
        raw = download(f'https://api.github.com/repos/{REPOSITORY}/commits/main', limit=512 * 1024)
        value = json.loads(raw)
        revision = value['sha']
        tree = value['commit']['tree']['sha']
        check(re.fullmatch('[0-9a-f]{40}', revision) and re.fullmatch('[0-9a-f]{40}', tree))
        _ROOTS.clear()
        _ROOTS[revision] = tree
    except (HTTPError, URLError, TimeoutError, ConnectionError):
        raw = download(f'https://github.com/{REPOSITORY}/commits/main.atom', limit=512 * 1024)
        root = ET.fromstring(raw)
        ident = root.findtext('{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}id', '')
        match = re.fullmatch(r'tag:github.com,2008:Grit::Commit/([0-9a-f]{40})', ident)
        check(match)
        revision = match[1]
    check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision))
    return revision


def _tree(rows, expected):
    """Authenticate a nonrecursive Git tree before following any child."""
    check(isinstance(rows, list) and 0 < len(rows) <= 2048)
    encoded, names = [], set()
    for row in rows:
        check(isinstance(row, dict))
        name, mode, kind, digest = (row.get(key) for key in ('path', 'mode', 'type', 'sha'))
        check(isinstance(name, str) and name not in {'', '.', '..'} and name not in names
              and not any(c in name for c in '/\\\0') and len(name.encode('utf-8')) <= 255
              and (mode, kind) in {('040000', 'tree'), ('100644', 'blob'), ('100755', 'blob'), ('160000', 'commit')}
              and isinstance(digest, str) and re.fullmatch('[0-9a-f]{40}', digest))
        names.add(name)
        key = name.encode('utf-8') + (b'/' if kind == 'tree' else b'')
        body = mode.lstrip('0').encode() + b' ' + name.encode('utf-8') + b'\0' + bytes.fromhex(digest)
        encoded.append((key, body))
    raw = b''.join(body for _, body in sorted(encoded))
    check(hashlib.sha1(f'tree {len(raw)}\0'.encode() + raw).hexdigest() == expected)
    return {row['path']: row for row in rows}


def _source_files(value, revision):
    check(isinstance(value, dict) and set(value) == {'schema', 'repository', 'revision', 'root_tree', 'trees'}
          and value['schema'] == SOURCE_SCHEMA and value['repository'] == REPOSITORY and value['revision'] == revision
          and isinstance(value['root_tree'], str) and re.fullmatch('[0-9a-f]{40}', value['root_tree'])
          and isinstance(value['trees'], list) and len(value['trees']) == 3)
    expected = value['root_tree']
    for record, component in zip(value['trees'], ('pkg_version', 'usm', None)):
        check(isinstance(record, dict) and set(record) == {'sha', 'tree'} and record['sha'] == expected)
        listing = _tree(record['tree'], expected)
        if component:
            child = listing.get(component, {})
            check(child.get('type') == 'tree' and child.get('mode') == '040000')
            expected = child['sha']
    selected = {}
    for name, limit in SOURCE_LIMITS.items():
        item = listing.get(name, {})
        check(item.get('mode') == '100644' and item.get('type') == 'blob'
              and type(item.get('size')) is int and 0 < item['size'] <= limit)
        selected[name] = item
    return selected


def _source(revision):
    tree = _ROOTS.get(revision)
    if tree is None:
        value = json.loads(download(f'https://api.github.com/repos/{REPOSITORY}/commits/{revision}', limit=512 * 1024))
        check(value.get('sha') == revision)
        tree = value['commit']['tree']['sha']
        check(isinstance(tree, str) and re.fullmatch('[0-9a-f]{40}', tree))
    result = {'schema': SOURCE_SCHEMA, 'repository': REPOSITORY, 'revision': revision, 'root_tree': tree, 'trees': []}
    for component in ('pkg_version', 'usm', None):
        value = json.loads(download(f'https://api.github.com/repos/{REPOSITORY}/git/trees/{tree}', limit=256 * 1024))
        check(value.get('sha') == tree and value.get('truncated') is False)
        listing = _tree(value.get('tree'), tree)
        # URLs from a response are never followed. Only fixed paths in this
        # allowlisted repository and exact authenticated child hashes are used.
        rows = [{key: row[key] for key in ('path', 'mode', 'type', 'sha', 'size') if key in row}
                for row in value['tree']]
        result['trees'].append({'sha': tree, 'tree': rows})
        if component:
            item = listing.get(component, {})
            check(item.get('type') == 'tree' and item.get('mode') == '040000')
            tree = item['sha']
    _source_files(result, revision)
    return result


def check_latest(directory=None):
    """An optional format service must not disable otherwise usable dialogue."""
    pointer = directory / 'starrail-movie-formats' / 'current.json' if directory else None
    try:
        revision = latest_revision()
    except (HTTPError, URLError, TimeoutError, ConnectionError, ValueError, KeyError, TypeError, ET.ParseError):
        try:
            check(pointer is not None and pointer.stat().st_size <= 1024)
            revision = json.loads(pointer.read_bytes())['revision']
            check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision))
            return revision, True
        except (OSError, ValueError, KeyError, TypeError):
            return None, True
    if pointer is not None:
        _atomic_file(pointer, json.dumps({'revision': revision}).encode())
    return revision, False


def _version(value):
    check(isinstance(value, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value))
    return tuple(map(int, value.split('.')))


@dataclass(frozen=True)
class Catalog:
    revision: str
    digest: str
    history: dict
    keys: dict
    variants: dict

    def key_for(self, asset):
        name = PurePosixPath(asset.name).name
        check(re.fullmatch(r'[A-Za-z0-9_-]+\.usm', name))
        stem = name[:-4]
        rows = []
        for path, item in self.history.items():
            if isinstance(path, str) and PurePosixPath(path).name == name:
                check(isinstance(item, dict) and isinstance(item.get('versions'), list))
                for row in item['versions']:
                    check(isinstance(row, dict))
                    rows.append((_version(row.get('version')), row.get('md5'), row.get('size')))
        matched = [version for version, digest, size in rows if (digest, size) == (asset.digest, asset.size)]
        check(matched)
        candidates = set()
        variants = self.variants.get(stem)
        if variants is None:
            check(max(version for version, _, _ in rows) in matched)
            matched = [max(matched)]
        for version in matched:
            if variants is not None:
                check(isinstance(variants, dict))
                eligible = [(_version(label), value) for label, value in variants.items() if _version(label) <= version]
                check(eligible)
                selected = max(eligible, key=lambda row: row[0])[1]
            else:
                # A default names the latest known generation. An older body
                # needs an explicit version entry; filenames alone cannot bind it.
                selected = self.keys.get(stem)
            if isinstance(selected, dict):
                selected = selected.get('audio')  # Video AES parameters are unused.
            check(isinstance(selected, str) and re.fullmatch('[0-9a-fA-F]{16}', selected))
            candidates.add(int(selected, 16))
        check(len(candidates) == 1)
        return candidates.pop()


def load(directory, revision=None, digest=None):
    revision = revision or latest_revision()
    check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision))
    check(digest is None or isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest))
    root = directory / 'starrail-movie-formats' / revision
    try:
        check((root / 'receipt.json').stat().st_size <= 4096)
        receipt = json.loads((root / 'receipt.json').read_bytes())
        bodies = {name: (root / name).read_bytes() for name in FILES
                  if (root / name).stat().st_size <= LIMIT}
        check(set(bodies) == set(FILES) and receipt == {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()})
    except (OSError, ValueError, TypeError):
        bodies = None
    source = None
    try:
        check((root / 'source.json').stat().st_size <= 1024**2)
        source = json.loads((root / 'source.json').read_bytes())
        _source_files(source, revision)
    except (OSError, ValueError, KeyError, TypeError):
        # Historical records already bind the complete decoded SHA256 set.
        # They may reuse a legacy cache offline; new candidates need provenance.
        if bodies is None or digest is None:
            source = _source(revision)
        else:
            source = None
    if source is not None:
        files = _source_files(source, revision)
    if bodies is None:
        bodies = {name: download(f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/pkg_version/usm/{name}',
                                limit=files[name]['size']) for name in FILES}
        receipt = {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()}
    if source is not None:
        for name, body in bodies.items():
            size = files[name]['size']
            check(len(body) == size and hashlib.sha1(f'blob {size}\0'.encode() + body).hexdigest() == files[name]['sha'])
    identity = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    check(digest is None or identity == digest)
    documents = [json.loads(bodies[name]) for name in FILES]
    check(all(isinstance(document, dict) and len(document) <= 100_000 for document in documents))
    catalog = Catalog(revision, identity, *documents)
    # Only data files are stored, after the complete source generation parses.
    for name, body in bodies.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != receipt[name]:
            _atomic_file(path, body)
    _atomic_file(root / 'receipt.json', json.dumps(receipt, sort_keys=True).encode())
    if source is not None:
        _atomic_file(root / 'source.json', json.dumps(source, sort_keys=True, separators=(',', ':')).encode())
    return catalog
