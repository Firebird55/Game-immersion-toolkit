"""Mainland NTE localization exports matched to the publisher's current Windows manifest."""
from collections import Counter
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


def _dialogue_events(catalog, namespace, selected, localization):
    if not isinstance(namespace, str) or not re.fullmatch(r'ST_[A-Za-z0-9_]+', namespace):
        raise ValueError('Select an exact NTE dialogue StringTable namespace for voice events.')
    tables = catalog.file('Text/Dialogue/' + namespace + '.json')
    if (not isinstance(tables, list) or len(tables) != 1 or not isinstance(tables[0], dict)
            or tables[0].get('Type') != 'StringTable'
            or tables[0].get('Name') != namespace):
        raise ValueError('Unsupported mainland NTE dialogue StringTable.')
    table = tables[0].get('StringTable') or {}
    if not isinstance(table, dict) or table.get('TableNamespace') != namespace or table.get('KeysToEntries') != localization[namespace]:
        raise ValueError('NTE dialogue StringTable does not match the release localization.')
    sounds = catalog.file('DataTable/DialogSoundTable.json')
    if (not isinstance(sounds, list) or len(sounds) != 1 or not isinstance(sounds[0], dict)
            or sounds[0].get('Name') != 'DialogSoundTable'
            or sounds[0].get('Type') != 'DataTable' or not isinstance(sounds[0].get('Rows'), dict)):
        raise ValueError('Unsupported mainland NTE dialogue event declarations.')
    # Sound rows use a bare key. A key present in multiple namespaces has no
    # unique localization identity, even when their displayed text is identical.
    counts = Counter(key for namespace_rows in localization.values() for key in namespace_rows)
    events = {}
    for key in selected:
        row = sounds[0]['Rows'].get(key)
        if not row or counts[key] != 1:
            continue
        if not isinstance(row, dict):
            raise ValueError('Unsupported NTE dialogue event row.')
        event = row.get('DialogSoundEvent') or {}
        if not isinstance(event, dict):
            raise ValueError('Unsupported NTE dialogue event reference.')
        path = event.get('AssetPathName')
        if not path or path == 'None':
            continue
        if (not isinstance(path, str) or event.get('SubPathString') or not re.fullmatch(
                r'/Game/WwiseAudio/Events/Voice/[A-Za-z0-9_/]+/([A-Za-z0-9_]+)\.\1', path)):
            raise ValueError('Unsupported NTE dialogue event object path.')
        events[key] = path
    return events


def snapshot(cache, *, namespace=None, keys=(), voice_events=False):
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
    extra = {}
    if voice_events and namespace is None:
        raise ValueError('Select a dialogue namespace for NTE voice events.')
    if namespace is not None:
        if namespace not in loc:
            raise ValueError('Unknown NTE localization namespace.')
        values = loc[namespace]
        if any(key not in values for key in keys):
            raise ValueError('Unknown key in the selected NTE localization namespace.')
        selection = {key: values[key] for key in keys} if keys else values
        if voice_events:
            extra['voice_events'] = {namespace: _dialogue_events(catalog, namespace, selection, loc)}
        loc = {namespace: selection}
    elif keys:
        raise ValueError('Selecting NTE text keys requires a namespace.')
    if publisher_identity() != identity:
        raise ValueError('The mainland NTE release changed during text acquisition. Retry.')
    return {'region': 'nte-cn', 'branch': branch, 'version': version, 'list_md5': digest,
            'metadata_commit': catalog.revision, 'logic_version': logic.decode('ascii'),
            'locale': 'zh-CN', 'texts': loc, **extra}
