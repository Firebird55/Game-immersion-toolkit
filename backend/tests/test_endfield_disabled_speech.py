"""A retained recording is not spoken by a caller that explicitly disables it."""
import json
from types import SimpleNamespace

import pytest

from backend import endfield_assets as assets, endfield_mission_dialogue as mission
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_audit import Catalog, ref
from backend.tests.test_endfield_mission_dialogue import graph, trunk
from backend.voice_assets import voice_hash


def test_disabled_speech_requires_one_original_simple_caller_and_tracks_changed_content(tmp_path, monkeypatch):
    path = mission.assets.DIALOG_GRAPHS + 'npc/future/chapter.json'
    data = graph([trunk('a', 'muted', disablePlayVoice=True),
                  trunk('b', 'normal'), trunk('c', 'shared', disablePlayVoice=True), trunk('d', 'shared'),
                  trunk('e', 'scripted', disablePlayVoice=True),
                  trunk('f', 'alternate', disablePlayVoice=True, enableEmotionVoice=True),
                  trunk('g', 'invalid_flag', disablePlayVoice=1)], [])
    data['nodes'][4]['_actorNodeData']['actions'] = [{'actionEnum': 999}]
    source = SimpleNamespace(content_hashes=('', '0' * 32))
    monkeypatch.setattr(mission.assets, '_files', lambda *_: {path: (None, source)})
    monkeypatch.setattr(mission.assets, '_asset', lambda *args, **kwargs:
        ('', 1, {1: {'m_Script': json.dumps(data)}}, []))
    assert mission.disabled_dialogues(tmp_path, 'first') == {'muted'}
    source.content_hashes = '', '1' * 32
    data['nodes'][0]['_actorNodeData']['mfTrunkActionData'].pop('disablePlayVoice')
    data['nodes'].append(trunk('h', 'new_muted', disablePlayVoice=True))
    assert mission.disabled_dialogues(tmp_path, 'second') == {'new_muted'}


@pytest.mark.parametrize('locale', ['en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'])
def test_disabled_source_suppresses_a_retained_recording_without_relabeling_missing_audio(tmp_path, locale):
    catalog = Catalog({'DialogTextTable': {
        'muted': {'dialogText': ref(1), 'audioOverride': 'retained_take'},
        'normal': {'dialogText': ref(2), 'audioOverride': 'ordinary_take'},
        'missing': {'dialogText': ref(3), 'audioOverride': 'absent_take'}}})
    catalog.disabled_dialogues = lambda: {'muted'}
    paths = {'retained_take': 'chapter/retained.wem', 'ordinary_take': 'chapter/ordinary.wem'}
    entries = {f'{voice_hash("voice/" + assets.VOICE_LOCALES[locale] + "/" + path):016x}': {'file_id': path}
               for path in paths.values()}
    tables = {language: {'1': 'This written caption has explicitly disabled speech.',
                        '2': 'This other caption retains its original sentence recording.',
                        '3': 'A missing source is still unavailable rather than silent.'}
              for language in ['en', 'zh-Hans', 'zh-Hant', 'ja', 'ko']}
    raw = assets.authored_dialogues(catalog)
    rows = assets.dialogue_records(raw, paths, tables, locale, entries)
    by_id = {r['text_id']: r for r in rows}
    assert by_id['endfield:muted']['voice_status'] == 'unvoiced'
    assert by_id['endfield:muted']['audio'] is None
    assert by_id['endfield:normal']['voice_status'] == 'voiced'
    assert by_id['endfield:normal']['audio']['source'].endswith('/chapter/ordinary.wem')
    assert by_id['endfield:missing']['voice_status'] == 'unavailable'
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': locale, 'records': rows}), encoding='utf8')
    index = MultilingualTextIndex('endfield', tmp_path)
    assert index.ready
    caption = by_id['endfield:muted']['source_text']
    assert not index.match_unvoiced_lines([caption])
    index.capture_unvoiced = True
    assert [h.text_id for h in index.match_unvoiced_lines([caption])] == ['endfield:muted']
