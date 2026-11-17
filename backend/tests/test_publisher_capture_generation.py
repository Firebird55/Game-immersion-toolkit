"""A same-ID update must not reuse or erase another original recording."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.models import TextMatch
from backend.storage import TranscriptStore
from backend.tests.test_audio_omission import index, record, TEXT


def match(locale='en', **patch):
    source = TEXT if locale == 'en' else '沿着河流前往那座桥。'
    values = dict(game='nte', text_id='authored:same-id', english=TEXT, chinese='沿着河流前往那座桥。',
        source_ocr=source, source_locale=locale, source_language='en' if locale == 'en' else 'zh',
        source_text=source, texts={locale: source}, score=100, kind='exact', voice_status='voiced',
        publisher_generation='authored-original-A', publisher_request_sha256='a' * 64)
    values.update(patch)
    return TextMatch(**values)


@pytest.mark.parametrize('locale', ['en', 'zh-Hans'])
@pytest.mark.parametrize('change', [
    {'publisher_generation': 'authored-original-B'},
    {'publisher_request_sha256': 'b' * 64},
    {'publisher_occurrence_sha256': 'c' * 64},
    {'audio_omitted_by_request': True, 'text_capture_verified': True},
])
def test_same_id_new_generation_selection_or_omission_cannot_suppress_new_capture(tmp_path, locale, change):
    store = TranscriptStore(tmp_path / 'history.db')
    now = datetime.now(timezone.utc)
    original = match(locale)
    old, upgraded = store.add_or_upgrade_recent(original, 'same-session', created_at=now)
    assert old and not upgraded
    store.update_audio(old.id, 'official-original-A.wav', True)
    assert store.add_or_upgrade_recent(original, 'another-session', created_at=now)[0] is None
    new, upgraded = store.add_or_upgrade_recent(original.model_copy(update=change), 'same-session', created_at=now + timedelta(seconds=1))
    assert new and new.id != old.id and not upgraded
    assert store.audio_path(old.id) == 'official-original-A.wav'
    assert store.get(old.id).publisher_generation == 'authored-original-A'
    assert not store.get(old.id).audio_omitted_by_request
    assert not new.has_audio


@pytest.mark.parametrize('same_generation', [True, False])
def test_chinese_prefix_upgrade_only_reuses_a_row_from_its_own_publisher_generation(tmp_path, same_generation):
    store = TranscriptStore(tmp_path / 'history.db')
    now = datetime.now(timezone.utc)
    short = match('zh-Hans', english='This is the beginning', text_id='authored:short')
    old, _ = store.add_or_upgrade_recent(short, 'same-session', created_at=now)
    store.update_audio(old.id, 'official-original-A.wav', True)
    full = short.model_copy(update={'english': 'This is the beginning of the complete authored caption.',
        'text_id': 'authored:complete', 'publisher_generation': 'authored-original-A' if same_generation else 'authored-original-B'})
    current, upgraded = store.add_or_upgrade_recent(full, 'same-session', created_at=now + timedelta(seconds=1))
    assert current and upgraded is same_generation
    assert (current.id == old.id) is same_generation
    assert current.publisher_generation == full.publisher_generation
    assert current.publisher_request_sha256 == full.publisher_request_sha256
    if not same_generation:
        assert store.audio_path(old.id) == 'official-original-A.wav'


def test_host_capture_context_reaches_matches_without_changing_original_rows(tmp_path):
    reader = index(tmp_path, [record()])
    original = reader._records[0].copy()
    assert reader.match_lines([TEXT]).publisher_generation is None
    reader.publisher_generation, reader.publisher_request_sha256 = 'authored-original-A', 'a' * 64
    hit = reader.match_lines([TEXT])
    assert hit.publisher_generation == reader.publisher_generation
    assert hit.publisher_request_sha256 == reader.publisher_request_sha256
    assert reader._records[0] == original and 'publisher_generation' not in original


def test_same_id_body_player_switch_has_its_own_original_occurrence(tmp_path):
    male, female = record(player_voice='male'), record(player_voice='female')
    male['source_voice_binding']['file_id'] = 'authored:male'
    female['source_voice_binding']['file_id'] = 'authored:female'
    reader = index(tmp_path / 'source', [male, female])
    reader.publisher_generation, reader.publisher_request_sha256 = 'authored-original-A', 'a' * 64
    store = TranscriptStore(tmp_path / 'history.db')
    hits = []
    for player in ('male', 'female'):
        reader.player_voice = player
        hit = reader.match_lines([TEXT]); assert hit
        hits.append(hit)
        line, upgraded = store.add_or_upgrade_recent(hit, 'same-session')
        assert line and not upgraded
    assert hits[0].text_id == hits[1].text_id and hits[0].source_text == hits[1].source_text
    assert hits[0].publisher_occurrence_sha256 != hits[1].publisher_occurrence_sha256
