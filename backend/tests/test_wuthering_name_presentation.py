"""Raw nickname presentation must leave stored source and original voice identity intact."""
from contextlib import closing
import json
import sqlite3

import pytest

from backend.models import TextMatch
from backend.multilingual_index import MultilingualTextIndex
from backend.storage import TranscriptStore


CANONICAL = 'Your journey continues beyond the bridge, {PlayerName}.'
CHINESE = '你的旅途还将继续，{PlayerName}。'


def match(**updates):
    return TextMatch(**dict(game='wuwa', text_id='native:caption:male', english=CANONICAL,
        chinese=CHINESE, source_text=CANONICAL, source_locale='en', source_language='en',
        translation_text=CHINESE, translation_locale='zh-Hans', audio_locale='en',
        texts={'en': CANONICAL, 'zh-Hans': CHINESE}, source_ocr=CANONICAL.replace('{PlayerName}', 'Pilot'),
        score=100, kind='exact', voice_status='voiced', dialogue_kind='cinematic',
        audio_scope='context') | updates)


def canonical_row(path):
    with closing(sqlite3.connect(path)) as database:
        return database.execute('SELECT english, chinese, source_ocr, text_id, language_context, '
                                'audio_path, voiced FROM transcript_lines').fetchone()


@pytest.mark.parametrize('name', ['Pilot', 'pILoT', 'Ｐｉｌｏｔ', 'Straße', '漂泊者', 'ローバー', '로버'])
def test_add_get_reopen_and_audio_updates_render_raw_name_without_persisting_it(tmp_path, name):
    store = TranscriptStore(tmp_path/'transcript.db')
    original = match(source_ocr=CANONICAL.replace('{PlayerName}', name))
    before_match = original.model_dump()
    created = store.add(original, 'session', channel='cinematic')
    assert original.model_dump() == before_match
    assert created.source_text == CANONICAL.replace('{PlayerName}', name)
    assert created.english == created.texts['en'] == created.source_text
    assert created.chinese == created.translation_text == created.texts['zh-Hans'] == CHINESE.replace('{PlayerName}', name)
    assert created.source_ocr == original.source_ocr
    assert created.text_id == original.text_id and created.audio_locale == 'en' and created.audio_scope == 'context'
    stored = canonical_row(store.path)
    assert stored[:4] == (CANONICAL, CHINESE, original.source_ocr, original.text_id)
    assert json.loads(stored[4])['texts'] == original.texts
    assert json.loads(stored[4])['source_text'] == CANONICAL
    database_before = store.path.read_bytes()
    assert store.get(created.id) == created and store.list() == [created]
    assert store.path.read_bytes() == database_before
    assert canonical_row(store.path) == stored
    assert TranscriptStore(store.path).get(created.id) == created
    voiced = store.update_audio(created.id, 'official-original-caption.mp3', voiced=True)
    assert voiced.source_text == created.source_text and voiced.has_audio and voiced.voiced
    assert store.audio_path(created.id) == 'official-original-caption.mp3'
    assert canonical_row(store.path)[:5] == stored[:5]
    duplicate, upgraded = store.add_or_upgrade_recent(original, 'session', channel='cinematic')
    assert duplicate is None and not upgraded and store.count() == 1


def test_actual_index_to_store_keeps_canonical_index_file_and_original_audio_binding(tmp_path):
    record = {'text_id': 'native:caption:male', 'source_locale': 'en', 'source_text': CANONICAL,
        'english': CANONICAL, 'chinese': CHINESE, 'texts': {'en': CANONICAL, 'zh-Hans': CHINESE},
        'audio_locale': 'en', 'voice_status': 'voiced', 'audio': {'depot': 'native-package', 'entry': 'original.wem'},
        'dialogue_kind': 'cinematic', 'audio_scope': 'context', 'channels': ['cinematic'], 'player_voice': 'male'}
    file = tmp_path/'textmap.json'
    file.write_text(json.dumps({'format': 2, 'game': 'wuwa', 'source_locale': 'en', 'records': [record]}), encoding='utf-8')
    before = file.read_bytes()
    index = MultilingualTextIndex('wuwa', tmp_path)
    index.player_voice = 'male'
    signature = (file.stat().st_size, file.stat().st_mtime_ns)
    canonical_snapshot = json.dumps(index.voice_snapshot(signature), sort_keys=True)
    observed = CANONICAL.replace('{PlayerName}', 'pILoT')
    hit = index.match_lines([observed], channel='cinematic', exact_only=True)
    assert hit and hit.source_text == CANONICAL
    stored = TranscriptStore(tmp_path/'transcript.db').add(hit, 'session', channel='cinematic')
    assert stored.source_text.endswith('pILoT.')
    assert file.read_bytes() == before
    assert hit.source_text == CANONICAL and hit.text_id == record['text_id']
    assert json.dumps(index.voice_snapshot(signature), sort_keys=True) == canonical_snapshot
    assert index.voice_snapshot(signature)['records'][0]['audio'] == record['audio']


def test_literal_body_with_ocr_space_gaps_owns_only_raw_nickname(tmp_path):
    text = "{PlayerName}, this is our village's fight. We will stand together."
    observed = "Rayne,thisisourvillage'sfight.Wewillstand together."
    created = TranscriptStore(tmp_path/'transcript.db').add(match(source_text=text,
        english=text, texts={'en': text, 'zh-Hans': CHINESE}, source_ocr=observed), 'session')
    assert created.source_text == text.replace('{PlayerName}', 'Rayne')
    assert created.source_ocr == observed


@pytest.mark.parametrize('updates', [
    {'game': 'endfield'}, {'game': 'genshin'}, {'game': 'zzz'}, {'kind': 'fuzzy'}, {'ambiguous': True},
    {'source_ocr': CANONICAL},
    {'source_ocr': CANONICAL.replace('{PlayerName}', 'Al-ex')},
    {'source_ocr': CANONICAL.replace('{PlayerName}', 'A<b>lex')},
    {'source_ocr': CANONICAL.replace('{PlayerName}', 'A\u0301lex')},
    {'source_ocr': CANONICAL.replace('{PlayerName}', 'x'*33)},
    {'source_ocr': CANONICAL.replace('journey', 'ｊｏｕｒｎｅｙ').replace('{PlayerName}', 'Pilot')},
    {'source_ocr': CANONICAL.replace('beyond', 'under').replace('{PlayerName}', 'Pilot')},
])
def test_unowned_or_ambiguous_raw_slots_keep_original_template(tmp_path, updates):
    original = match(**updates)
    created = TranscriptStore(tmp_path/'transcript.db').add(original, 'session')
    assert created.source_text == original.source_text
    assert created.texts == original.texts


def test_different_official_templates_cannot_choose_different_raw_spans(tmp_path):
    text = '{PlayerName} waits patiently beside the bridge Bob'
    other = 'Alice waits patiently beside the bridge {PlayerName}'
    created = TranscriptStore(tmp_path/'transcript.db').add(match(source_text=text, english=text,
        texts={'en': text, 'zh-Hans': other}, source_ocr='Alice waits patiently beside the bridge Bob'), 'session')
    assert created.source_text == text and created.texts['zh-Hans'] == other


def test_other_grammar_or_repeated_slots_are_not_rendered_from_a_single_name(tmp_path):
    other = '{PlayerName}, {TA} will wait here.'
    created = TranscriptStore(tmp_path/'transcript.db').add(match(chinese=other,
        translation_text=other, texts={'en': CANONICAL, 'zh-Hans': other,
                                     'ja': '{PlayerName} and {PlayerName}'}), 'session')
    assert created.source_text == CANONICAL.replace('{PlayerName}', 'Pilot')
    assert created.chinese == created.translation_text == created.texts['zh-Hans'] == other
    assert created.texts['ja'] == '{PlayerName} and {PlayerName}'
