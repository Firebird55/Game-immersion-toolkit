"""Explicit text preparation must never trigger original audio acquisition."""
from types import SimpleNamespace

import pytest

from backend import starrail_assets as assets, starrail_films as films
from backend import hoyo_publisher_voice as voices, starrail_events as events, starrail_movie_metadata as movie_metadata
from backend.language_worker import write_payload
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex


class Catalog:
    text_locales = {'en': ('EN',), 'zh-Hans': ('CHS',)}
    revision, revision_title = 'original-generation', 'Original test generation'
    movie_files = {}

    def __init__(self):
        self.tables = {
            'TalkSentenceConfig': [
                {'TalkSentenceID': 1, 'TalkSentenceText': {'Hash': 101}, 'VoiceID': 10},
                {'TalkSentenceID': 2, 'TalkSentenceText': {'Hash': 102}, 'VoiceID': 20},
                {'TalkSentenceID': 3, 'TalkSentenceText': {'Hash': 103}}],
            'VoiceConfig': [{'VoiceID': 10, 'VoicePath': 'owned_dialogue'},
                {'VoiceID': 20, 'VoicePath': '', 'VoiceType': 'NoVoice'},
                {'VoiceID': 30, 'VoicePath': 'owned_film', 'VoiceType': 'Cutscene', 'IsPlayerInvolved': True}],
            'VoiceAtlas': [{'AvatarID': 100, 'VoiceID': 40, 'Voice_M': {'Hash': 104}, 'AudioEvent': 'Ev_owned_archive'}],
            'CutSceneConfig': [{'CutSceneName': 'OwnedFilm', 'CaptionPath': 'Config/CutSceneCaption/OwnedFilm_Caption.json',
                               'CutScenePath': 'owned_timeline', 'VoiceID': 30}],
        }

    def file(self, path, **kwargs):
        if path.startswith('TextMap/'):
            return {str(key): f'Original fixture sentence number {key}.' for key in range(101, 106)}
        return self.tables.get(path.removeprefix('ExcelOutput/').removesuffix('.json'), [])

    def caption_scripts(self):
        return [('OwnedFilm_Caption.json', {'CaptionList': [
            {'CaptionTextID': {'Hash': 105}, 'StartTime': 0, 'EndTime': 2}]})]


def test_text_only_retains_authored_status_and_branches_without_any_audio_work(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Text-only preparation attempted audio/header/bank/key work')
    for owner, names in [(voices, ('inventory', 'extract', '_table', '_archive')),
                         (events, ('bindings', 'extract')),
                         (films, ('_takes', '_take_duration', '_reviewed_take', '_movie_take', '_reviewed_sources')),
                         (movie_metadata, ('check_latest', 'load'))]:
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    payload = assets.index_text_catalog('sophon-' + 'a' * 64, Catalog(), 'en', ['zh-Hans'], tmp_path / 'tools')
    rows = {row['text_id']: row for row in payload['records']}
    assert rows['starrail:1']['voice_status'] == 'unavailable'
    assert rows['starrail:1']['source_voice_binding']['source'] == 'English/voice/owned_dialogue.wem'
    assert rows['starrail:2']['voice_status'] == 'unvoiced'
    assert rows['starrail:3']['voice_status'] == 'unknown'
    assert rows['starrail:voice-atlas-100-40']['source_voice_binding']['audio_event'] == 'Ev_owned_archive'
    captions = [row for key, row in rows.items() if key.startswith('starrail:film-')]
    assert {row['player_voice'] for row in captions} == {'male', 'female'}
    assert all(row['voice_status'] == 'unavailable' and row['audio_omitted_by_request'] for row in captions)
    assert all(LocalDialogue(**row).audio is None for row in rows.values())
    assert payload['content_mode'] == 'text' and 'install' not in payload['message']
    output = tmp_path / 'textmap.json'
    write_payload('starrail', payload, 'en', ['zh-Hans'], output)
    index = MultilingualTextIndex('starrail', tmp_path)
    assert index.ready and index.capture_text_only and index.audio_count == 0


def test_text_only_never_promotes_unrecognized_authoring_to_silence(tmp_path):
    catalog = Catalog()
    catalog.tables['VoiceConfig'][0]['VoiceType'] = 987654
    payload = assets.index_text_catalog('sophon-' + 'a' * 64, catalog, 'en', [], tmp_path)
    rows = {row['text_id']: row for row in payload['records']}
    assert rows['starrail:1']['voice_status'] == 'unavailable'
    assert rows['starrail:3']['voice_status'] == 'unknown'
    assert sum(row['voice_status'] == 'unvoiced' for row in rows.values()) == 1


def test_text_gender_conditions_do_not_require_audio_states_or_concatenate_branches(tmp_path):
    catalog = Catalog()
    file = catalog.file
    def localized(path, **kwargs):
        value = file(path, **kwargs)
        if path.startswith('TextMap/'):
            value['101'] = 'Follow {M#him}{F#her} to the bridge.'
        return value
    catalog.file = localized
    rows = {row['text_id']: row for row in assets.index_text_catalog(
        'sophon-' + 'a' * 64, catalog, 'en', ['zh-Hans'], tmp_path)['records']}
    male, female = rows['starrail:1-text-player-m'], rows['starrail:1-text-player-f']
    assert male['source_text'] == 'Follow him to the bridge.'
    assert female['source_text'] == 'Follow her to the bridge.'
    assert male['source_voice_binding']['source'] == female['source_voice_binding']['source'] == 'English/voice/owned_dialogue.wem'
    assert male['audio'] is female['audio'] is None
