"""Mainland NTE localization exports matched to the publisher's current Windows manifest."""
import hashlib
import json
import re
from xml.etree import ElementTree

from .dialogue_catalog import DialogueCatalog, SOURCES
from .game_tools import download
from .nte_release import release_config


def publisher_identity():
    branch, version, _, cfg = release_config('nte-cn')
    digest = cfg.findtext('Extra/listHash', '')
    if not re.fullmatch('[0-9a-f]{32}', digest):
        raise ValueError('The mainland NTE launcher has no valid resource-list checksum.')
    return branch, version, digest


def matches(catalog, version, digest):
    raw = catalog.raw_file('ResList.xml')
    if hashlib.md5(raw).hexdigest() != digest:
        return False
    root = ElementTree.fromstring(raw)
    return root.tag == 'ResList' and root.get('tag') == 'baseTag' and root.get('version') == version


def matching_catalog(cache, version, digest):
    latest = DialogueCatalog('nte-cn', cache)
    if matches(latest, version, digest):
        return latest
    _, repo, branch = SOURCES['nte-cn']
    url = f'https://api.github.com/repos/{repo}/commits?sha={branch}&path=ResList.xml&per_page=100'
    commits = json.loads(download(url, limit=4 * 1024**2))
    candidates = {item['sha'] for item in commits
                  if item['commit']['message'].split('|', 1)[0].strip() == version and item['sha'] != latest.revision}
    found = []
    for revision in sorted(candidates):
        catalog = DialogueCatalog('nte-cn', cache, revision=revision)
        if matches(catalog, version, digest):
            found.append(catalog)
    if len(found) != 1:
        raise ValueError('No unique localization snapshot matches the mainland NTE publisher manifest. Retry after the source updates.')
    return found[0]


def snapshot(cache, *, namespace=None, keys=()):
    identity = publisher_identity()
    branch, version, digest = identity
    catalog = matching_catalog(cache, version, digest)
    logic = catalog.raw_file('GameVersion/LogicVersion.h').strip()
    if not re.fullmatch(rb'[0-9]{1,16}', logic):
        raise ValueError('Invalid NTE localization snapshot build number.')
    loc = catalog.file('Localization/Game/zh-CN/game.json')
    if (not isinstance(loc, dict) or not loc or any(not isinstance(rows, dict) or not rows or
            any(not key or not isinstance(text, str) for key, text in rows.items()) for rows in loc.values())):
        raise ValueError('Unsupported mainland NTE localization format.')
    if namespace is not None:
        if namespace not in loc:
            raise ValueError('Unknown NTE localization namespace.')
        values = loc[namespace]
        if any(key not in values for key in keys):
            raise ValueError('Unknown key in the selected NTE localization namespace.')
        loc = {namespace: {key: values[key] for key in keys} if keys else values}
    elif keys:
        raise ValueError('Selecting NTE text keys requires a namespace.')
    if publisher_identity() != identity:
        raise ValueError('The mainland NTE release changed during text acquisition. Retry.')
    return {'region': 'nte-cn', 'branch': branch, 'version': version, 'list_md5': digest,
            'metadata_commit': catalog.revision, 'logic_version': logic.decode('ascii'),
            'locale': 'zh-CN', 'texts': loc}
