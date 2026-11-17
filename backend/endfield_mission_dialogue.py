"""Use direct, unbranched game-graph edges to identify a spoken mission subtitle."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256
import json

from . import endfield_film_update as assets
from .game_tools import _atomic_file


def _references(value):
    if isinstance(value, list):
        for child in value:
            yield from _references(child)
    elif isinstance(value, dict):
        reference = value.get('_trunkId')
        if isinstance(reference, str) and reference:
            yield reference
        for child in value.values():
            yield from _references(child)


def _spoken_trunk(node, *, top=False):
    if node.get('$type') != 'Beyond.Gameplay.DialogTreeTrunkNode':
        return None
    actor = node.get('_actorNodeData', {})
    action = actor.get('mfTrunkActionData', {})
    if (actor.get('$type') != 'Beyond.Gameplay.DTTrunkNodeData' or action.get('actionEnum') != 307
            or actor.get('actions') or actor.get('actionGroups') or action.get('voiceConfig')
            or action.get('customText') or action.get('disablePlayVoice')
            or (action.get('_showAtTop') is not True if top else action.get('_showAtTop'))
            or action.get('exUIDescriptor', {}).get('useRadio') or (action.get('enableEmotionVoice') and not top)
            or action.get('isOverrideEmotionVoiceId') or action.get('overrideEmotionVoiceId')):
        return None
    return action.get('_trunkId')


def graph_summary(path, graph, *, top=False):
    references = list(_references(graph))
    prefix = assets.DIALOG_GRAPHS if top else assets.DIALOG_GRAPHS + 'mission/'
    if not path.startswith(prefix) or graph.get('type') != 'Beyond.Gameplay.DialogTree':
        return references, []
    trunks = {}
    for node in graph['nodes']:
        key = node.get('$id')
        if key is None:
            continue
        if key in trunks:
            return references, []
        trunks[key] = _spoken_trunk(node, top=top)
    outgoing, incoming = Counter(), Counter()
    edges = []
    for link in graph['connections']:
        a, b = link['_sourceNode']['$ref'], link['_targetNode']['$ref']
        outgoing[a] += 1
        incoming[b] += 1
        if (set(link) == {'$type', '_sourceNode', '_targetNode'}
                and link['$type'] == 'Beyond.Gameplay.DialogTreeConnection' and a != b
                and trunks.get(a) and trunks.get(b)):
            edges.append((a, b))
    return references, [(trunks[b], trunks[a]) for a, b in edges if incoming[b] == outgoing[a] == 1]


def _summary(tools, path, source):
    digest = source[1].content_hashes[1]
    identity = (path + '\0' + digest).encode()
    # Unchanged graphs can be reused when thousands of files are repackaged.
    # Both the declared asset path and content hash identify the original.
    destination = tools / 'endfield-releases' / 'dialogue-edges-v1' / sha256(identity).hexdigest()
    if destination.is_file() and destination.stat().st_size <= 4 * 1024**2:
        checksum, _, body = destination.read_bytes().partition(b'\n')
        if checksum == sha256(identity + body).hexdigest().encode():
            return json.loads(body)
    _, root, objects, _ = assets._asset(tools, source, path, classes=(49,))
    summary = graph_summary(path, json.loads(objects[root]['m_Script']))
    body = json.dumps(summary, separators=(',', ':')).encode()
    _atomic_file(destination, sha256(identity + body).hexdigest().encode() + b'\n' + body)
    return summary


@lru_cache(maxsize=4)
def predecessors(tools, stamp):
    files = assets._files(tools, stamp)
    paths = [path for path in files if path.startswith(assets.DIALOG_GRAPHS) and path.endswith('.json')]
    assets._check(paths)
    occurrences, candidates = Counter(), []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for references, edges in pool.map(lambda path: _summary(tools, path, files[path]), paths):
            occurrences.update(references)
            candidates.extend(edges)
    return {child: parent for child, parent in candidates if occurrences[child] == occurrences[parent] == 1}


def _top_summary(tools, path, source):
    identity = (path + '\0' + source[1].content_hashes[1]).encode()
    destination = tools / 'endfield-releases' / 'dialogue-top-layouts-v2' / sha256(identity).hexdigest()
    if destination.is_file() and destination.stat().st_size <= 4 * 1024**2:
        checksum, _, body = destination.read_bytes().partition(b'\n')
        if checksum == sha256(identity + body).hexdigest().encode():
            return json.loads(body)
    _, root, objects, _ = assets._asset(tools, source, path, classes=(49,))
    graph = json.loads(objects[root]['m_Script'])
    references, edges = graph_summary(path, graph, top=True)
    top_ids = ([_spoken_trunk(node, top=True) for node in graph['nodes']]
               if graph.get('type') == 'Beyond.Gameplay.DialogTree' else [])
    summary = references, [identity for identity in top_ids if identity], edges
    body = json.dumps(summary, separators=(',', ':')).encode()
    _atomic_file(destination, sha256(identity + body).hexdigest().encode() + b'\n' + body)
    return summary


@lru_cache(maxsize=4)
def top_dialogues(tools, stamp):
    """Original top-caption declarations and unbranched same-layout ordering."""
    files = assets._files(tools, stamp)
    paths = [path for path in files if path.startswith(assets.DIALOG_GRAPHS) and path.endswith('.json')]
    assets._check(paths)
    occurrences, top_ids, candidates = Counter(), set(), []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for references, ids, edges in pool.map(lambda path: _top_summary(tools, path, files[path]), paths):
            occurrences.update(references)
            top_ids.update(ids)
            candidates.extend(edges)
    result = {identity: None for identity in top_ids if occurrences[identity] == 1}
    for child, parent in candidates:
        if child in result and parent in result:
            result[child] = parent
    return result


def _disabled_trunk(node):
    if node.get('$type') != 'Beyond.Gameplay.DialogTreeTrunkNode':
        return None
    actor = node.get('_actorNodeData', {})
    action = actor.get('mfTrunkActionData', {})
    if (actor.get('$type') != 'Beyond.Gameplay.DTTrunkNodeData' or action.get('actionEnum') != 307
            or action.get('disablePlayVoice') is not True or action.get('customText')
            or actor.get('actions') or actor.get('actionGroups') or action.get('voiceConfig')
            or action.get('exUIDescriptor', {}).get('useRadio') or action.get('enableEmotionVoice')
            or action.get('isOverrideEmotionVoiceId') or action.get('overrideEmotionVoiceId')):
        return None
    return action.get('_trunkId')


def _disabled_summary(tools, path, source):
    identity = (path + '\0' + source[1].content_hashes[1]).encode()
    destination = tools / 'endfield-releases' / 'dialogue-disabled-speech-v1' / sha256(identity).hexdigest()
    if destination.is_file() and destination.stat().st_size <= 4 * 1024**2:
        checksum, _, body = destination.read_bytes().partition(b'\n')
        if checksum == sha256(identity + body).hexdigest().encode():
            return json.loads(body)
    _, root, objects, _ = assets._asset(tools, source, path, classes=(49,))
    graph = json.loads(objects[root]['m_Script'])
    candidates = ([_disabled_trunk(node) for node in graph['nodes']]
                  if graph.get('type') == 'Beyond.Gameplay.DialogTree' else [])
    summary = list(_references(graph)), [value for value in candidates if value]
    body = json.dumps(summary, separators=(',', ':')).encode()
    _atomic_file(destination, sha256(identity + body).hexdigest().encode() + b'\n' + body)
    return summary


@lru_cache(maxsize=4)
def disabled_dialogues(tools, stamp):
    """The original voice controller skips playback for these unique callers."""
    files = assets._files(tools, stamp)
    paths = [path for path in files if path.startswith(assets.DIALOG_GRAPHS) and path.endswith('.json')]
    assets._check(paths)
    occurrences, candidates = Counter(), set()
    with ThreadPoolExecutor(max_workers=6) as pool:
        for references, ids in pool.map(lambda path: _disabled_summary(tools, path, files[path]), paths):
            occurrences.update(references)
            candidates.update(ids)
    return frozenset(identity for identity in candidates if occurrences[identity] == 1)
