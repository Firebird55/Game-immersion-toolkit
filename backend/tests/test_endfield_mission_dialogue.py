import json
from types import SimpleNamespace

from backend import endfield_mission_dialogue as mission
from backend.endfield_caption_context import EndfieldCaptionContext
from backend.multilingual_index import MultilingualTextIndex


def trunk(node, line, **options):
    return {'$id': node, '$type': 'Beyond.Gameplay.DialogTreeTrunkNode', '_actorNodeData': {
        '$type': 'Beyond.Gameplay.DTTrunkNodeData',
        'mfTrunkActionData': {'actionEnum': 307, '_trunkId': line, **options}}}


def graph(nodes, edges):
    return {'type': 'Beyond.Gameplay.DialogTree', 'nodes': nodes,
            'connections': [{'$type': 'Beyond.Gameplay.DialogTreeConnection',
                             '_sourceNode': {'$ref': a}, '_targetNode': {'$ref': b}} for a, b in edges]}


def test_direct_edges_exclude_choices_branches_merges_and_globally_reused_lines(tmp_path, monkeypatch):
    path = mission.assets.DIALOG_GRAPHS + 'mission/example.json'
    nodes = [trunk(str(i), f'line-{i}') for i in (3, 4, 1, 2, 5, 6, 7, 8)]
    nodes.extend([trunk('9', 'changed', customText='override'), {'$id': '10', '$type': 'Choice'}])
    data = graph(nodes, [('1', '3'), ('3', '2'), ('2', '4'), ('2', '5'), ('4', '6'), ('5', '6'),
                         ('6', '7'), ('7', '8'), ('8', '9'), ('9', '10')])
    sibling = mission.assets.DIALOG_GRAPHS + 'npc/other.json'
    source = SimpleNamespace(content_hashes=('', '0'*32))
    sources = {k: (None, source) for k in (path, sibling)}
    monkeypatch.setattr(mission.assets, '_files', lambda *args: sources)
    def asset(_tools, _source, relative, *, classes):
        obj = data if relative == path else graph([trunk('0', 'line-3')], [])
        return '', 3, {3: {'m_Script': json.dumps(obj)}}, []
    monkeypatch.setattr(mission.assets, '_asset', asset)
    assert mission.predecessors(tmp_path, 'one') == {'line-7': 'line-6', 'line-8': 'line-7'}
    # A normal game update removes a fork and changes its content digest.
    data['connections'].pop(3)
    sources[path] = None, SimpleNamespace(content_hashes=('', '1'*32))
    assert mission.predecessors(tmp_path, 'two')['line-4'] == 'line-2'


def test_short_anchor_only_selects_the_current_recording_after_a_stable_unique_pair(tmp_path):
    lines = [('a', 'Perlica!', None), ('b', 'Bro!', 'a'), ('c', "Endmin, Chen, I'm here.", 'b'),
             ('other', 'Perlica?', None), ('other2', 'Can you see where I am?', 'other'),
             ('third', 'Bro...', None)]
    def load(extra=()):
        rows = [{'text_id': key, 'source_locale': 'en', 'audio_locale': 'en', 'texts': {'en': text},
                 'source_text': text, 'audio': {'file_id': key}, 'dialogue_kind': 'conversation',
                 'channels': ['dialogue'], 'previous_text_id': parent} for key, text, parent in (*lines, *extra)]
        (tmp_path / 'textmap.json').write_text(json.dumps(
            {'format': 2, 'game': 'endfield', 'source_locale': 'en', 'records': rows}))
        return MultilingualTextIndex('endfield', tmp_path)
    index, tracker = load(), EndfieldCaptionContext()
    def scan(text, t, scope=1, kind='conversation'):
        return tracker.observe(index, [text], [index.match_lines([text])], channel='dialogue',
                               kind=kind, scope=scope, now=t, stable_frames=2)
    assert index.match_lines(['Bro!']) is None and scan('Bro!', 0) is None
    assert scan('Perlica!', 1) is None and scan('Bro!', 1.1) is None
    assert scan('Perlica!', 2) is None and scan('Perlica!', 2.1) is None
    hit = scan('Bro!', 3)
    assert hit.text_id == 'b'
    selected = next(row for row in index.voice_snapshot(index._signature)['records'] if row['text_id'] == hit.text_id)
    assert selected['audio'] == {'file_id': 'b'}
    assert scan('Bro!', 3.1).text_id == 'b'
    assert scan("Endmin, Chen, I'm here.", 4).text_id == 'c'
    for text, t in [('Perlica!', 5), ('Perlica!', 5.1)]:
        assert scan(text, t, scope=2) is None
    assert scan('Bro!', 6, scope=3) is None
    assert scan('Perlica!', 7, kind='radio') is None and scan('Perlica!', 7.1, kind='radio') is None
    assert scan('Bro!', 7.2) is None
    index, tracker = load([('fourth', 'Perlica!', None), ('other-bro', 'Bro?', 'fourth')]), EndfieldCaptionContext()
    assert scan('Perlica!', 0) is None and scan('Perlica!', .1) is None and scan('Bro!', .2) is None
