"""Verify equivalent raw publisher recordings without replacing authored refs."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256
import json
import re

from . import endfield_film_update as assets
from .game_tools import _atomic_file
from .local_game import original_recording_context
from .voice_assets import voice_hash


def _references(value):
    if isinstance(value, list):
        for child in value:
            yield from _references(child)
    elif isinstance(value, dict):
        for key in ('_trunkId', 'trunkId'):
            if isinstance(value.get(key), str) and value[key]:
                yield value[key]
        for child in value.values():
            yield from _references(child)


def _ship_trunk(node):
    actor = node.get('_actorNodeData', {})
    action = actor.get('mfTrunkActionData', {})
    if (node.get('$type') != 'Beyond.Gameplay.DialogTreeTrunkNode'
            or actor.get('$type') != 'Beyond.Gameplay.DTTrunkNodeData'
            or type(actor.get('_actorIndex')) is not int or actor['_actorIndex'] != 0
            or action.get('actionEnum') != 307 or action.get('actorIndex') not in (None, 0)
            or action.get('customText') or action.get('isOverrideActorNameId')):
        return None
    return action


def _speaker_summary(tools, path, source):
    identity = (path + '\0' + source[1].content_hashes[1]).encode()
    destination = tools / 'endfield-releases' / 'dialogue-source-speakers-v2' / sha256(identity).hexdigest()
    if destination.is_file() and destination.stat().st_size <= 4 * 1024**2:
        checksum, _, body = destination.read_bytes().partition(b'\n')
        if checksum == sha256(identity + body).hexdigest().encode():
            return json.loads(body)
    _, root, objects, _ = assets._asset(tools, source, path, classes=(49,))
    graph = json.loads(objects[root]['m_Script'])
    references, bindings = list(_references(graph)), []
    data = graph.get('derivedData', {})
    character = data.get('spaceshipCharId')
    actors = data.get('actors', [])
    if (graph.get('type') == 'Beyond.Gameplay.DialogTree' and data.get('isSpaceshipDialog') is True
            and isinstance(character, str) and re.fullmatch(r'chr_[A-Za-z0-9_]+', character)
            and isinstance(actors, list) and actors and actors[0].get('actorType') == 256
            and actors[0].get('useNpcProxy') is True and actors[0].get('actorId') and actors[0].get('npcProxyId')):
        nodes = {node.get('$id'): node for node in graph['nodes']}
        assets._check(None not in nodes and len(nodes) == len(graph['nodes']))
        for node in graph['nodes']:
            action = _ship_trunk(node)
            if action and action.get('_trunkId'):
                bindings.append((action['_trunkId'], character))
            if node.get('$type') != 'Beyond.Gameplay.DialogTreeExTrunkReplaceNode':
                continue
            # ExTrunkReplace is an extension attached FROM its owning trunk.
            # It is not a later main-flow line or a preceding-caption guess.
            links = [link for link in graph['connections'] if link.get('_targetNode', {}).get('$ref') == node.get('$id')]
            if (len(links) != 1 or set(links[0]) != {'$type', '_sourceNode', '_targetNode'}
                    or links[0]['$type'] != 'Beyond.Gameplay.DialogTreeConnection'):
                continue
            target = _ship_trunk(nodes.get(links[0]['_sourceNode']['$ref'], {}))
            if target is None or target.get('_trunkId'):
                continue
            for item in node.get('_trunkReplaceData', {}).get('replaceItems', []):
                condition = item.get('activeCondition', {})
                if (isinstance(item.get('trunkId'), str) and item['trunkId']
                        and condition.get('$type') == 'Beyond.Gameplay.CharFriendshipLevel'
                        and condition.get('_charId', {}).get('constValue') == character):
                    bindings.append((item['trunkId'], character))
    summary = references, bindings
    body = json.dumps(summary, separators=(',', ':')).encode()
    _atomic_file(destination, sha256(identity + body).hexdigest().encode() + b'\n' + body)
    return summary


@lru_cache(maxsize=4)
def character_speakers(tools, stamp):
    files = assets._files(tools, stamp)
    paths = [path for path in files if path.startswith(assets.DIALOG_GRAPHS) and path.endswith('.json')]
    assets._check(paths)
    references, count, speakers = Counter(), Counter(), defaultdict(set)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for refs, bindings in pool.map(lambda path: _speaker_summary(tools, path, files[path]), paths):
            references.update(refs)
            for identity, character in bindings:
                count[identity] += 1
                speakers[identity].add(character)
    return {identity: next(iter(values)) for identity, values in speakers.items()
            if len(values) == 1 and references[identity] == count[identity]}


def _recording_digest(tools, stamp, dub, identity, found):
    from . import endfield_release as release
    _, file, entry = found
    key = json.dumps({'dub': dub, 'package': file.name, 'package_md5': file.content_hashes[1],
        'file_id': identity, 'offset': entry.offset, 'size': entry.size,
        'bank_seed': entry.bank_seed, 'bank_offset': entry.bank_offset}, sort_keys=True).encode()
    destination = tools / 'endfield-releases' / 'original-recording-identities-v1' / sha256(key).hexdigest()
    if destination.is_file() and destination.stat().st_size <= 256:
        checksum, _, digest = destination.read_bytes().partition(b'\n')
        if re.fullmatch(b'[0-9a-f]{64}', digest) and checksum == sha256(key + digest).hexdigest().encode():
            return digest.decode()
    raw = release.media(tools, stamp, dub, int(identity, 16))
    assets._check(len(raw) == entry.size)
    digest = sha256(raw).hexdigest().encode()
    _atomic_file(destination, sha256(key + digest).hexdigest().encode() + b'\n' + digest)
    return digest.decode()


def annotate(catalog, rows, dub, progress=lambda _message: None):
    """Hash only compatible cross-presentation collisions in current sources."""
    from . import endfield_release as release
    effects = catalog.file('TableCfg/DialogTextTable.json')
    groups = defaultdict(list)
    for row in rows:
        audio = row.get('audio')
        if (row.get('voice_status') != 'voiced' or row.get('dialogue_kind') not in {'conversation', 'operator_voice'}
                or not row.get('original_speaker_id') or row.get('audio_scope', 'line') != 'line'
                or not audio or set(audio) != {'publisher', 'file_id', 'source', 'locale'}):
            continue
        if row['dialogue_kind'] == 'conversation' and effects.get(row['text_id'].removeprefix('endfield:'), {}).get('audioEffect') != 0:
            continue
        key = original_recording_context({**row, 'original_recording_sha256': '0' * 64})
        groups[key].append(row)
    candidates = [group for group in groups.values()
                  if {row['dialogue_kind'] for row in group} == {'conversation', 'operator_voice'}
                  and len({row['audio']['file_id'] for row in group}) > 1]
    if not candidates:
        return
    inventory = release.inventory(catalog.tools, catalog.stamp, dub)
    selected, compatible = {}, []
    for group in candidates:
        found = {row['audio']['file_id']: inventory[int(row['audio']['file_id'], 16)] for row in group}
        if len({value[2].size for value in found.values()}) != 1:
            continue
        for row in group:
            audio = row['audio']
            assets._check(audio['publisher'] == catalog.stamp and audio['source'].startswith('voice/' + dub + '/')
                          and voice_hash(audio['source']) == int(audio['file_id'], 16))
        selected.update(found)
        compatible.append(group)
    progress('Verifying equivalent original voice recordings')
    with ThreadPoolExecutor(max_workers=6) as pool:
        hashes = dict(pool.map(lambda pair: (pair[0], _recording_digest(catalog.tools, catalog.stamp, dub, *pair)), selected.items()))
    for group in compatible:
        values = {hashes[row['audio']['file_id']] for row in group}
        if len(values) == 1:
            for row in group:
                row['original_recording_sha256'] = next(iter(values))
