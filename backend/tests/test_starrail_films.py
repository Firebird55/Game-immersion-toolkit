"""Verify release-paired caption timing, locale and actor bindings."""
import hashlib
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_films as films
from backend.voice_assets import voice_hash


def track():
    data = bytearray(86)
    data[:4] = b'RIFF'
    data[8:16] = b'WAVEfmt '
    struct.pack_into('<IHHI', data, 16, 66, 0xffff, 2, 48000)
    struct.pack_into('<H', data, 36, 48)
    struct.pack_into('<I', data, 44, 96000)
    return bytes(data)


def test_authored_caption_uses_referenced_voice_and_actor_or_retains_text(tmp_path, monkeypatch):
    tools = tmp_path / 'tools'
    source = 'Japanese/voice/vo_movie_m.wem'
    entries = {voice_hash(source): {'publisher': 'release', 'package': 'chapter'}}
    def extract(audio, path, game):
        assert audio['source'] == source and audio['publisher'] == 'release' and audio['locale'] == 'ja'
        assert (path, game) == (tools, 'starrail')
        return track()
    monkeypatch.setattr(films.voices, 'extract', extract)
    script = {'CaptionList': [{'CaptionTextID': {'Hash': 100}, 'StartTime': 0.5, 'EndTime': 1.125},
                              {'CaptionTextID': {'Hash': 101}, 'EndTime': 2.5}]}
    configs = [{'CutSceneName': 'Movie', 'CaptionPath': 'Config/CutSceneCaption/Movie_Caption.json',
                'CutScenePath': 'timeline', 'VoiceID': 20}]
    voc = [{'VoiceID': 20, 'VoicePath': 'vo_movie', 'VoiceType': 'Cutscene', 'IsPlayerInvolved': True}]
    movie_configs = [{'VideoID': 30, 'VideoPath': 'Film.usm', 'IsPlayerInvolved': True,
                      'CaptionPath': 'Config/CutSceneCaption/Film_Caption.json'},
                     {'VideoID': 31, 'VideoPath': 'Alternate.usm',
                      'CaptionPath': 'Config/CutSceneCaption/Film_Caption.json'}]
    movie = SimpleNamespace(name='Film_m.usm', digest='a'*32, size=100)
    alternate = SimpleNamespace(name='Alternate.usm', digest='b'*32, size=120)
    raw = {'CutSceneConfig': configs, 'VoiceConfig': voc, 'VideoConfig': movie_configs}
    catalog = SimpleNamespace(file=lambda p: raw[p.split('/')[-1][:-5]],
                              movie_files={'film_m.usm': movie, 'alternate.usm': alternate},
                              caption_scripts=lambda: [('Movie_Caption.json', script), ('Film_Caption.json', script)])
    rows = films.caption_rows(tools, catalog, {'ja': {'100': 'a', '101': 'b'}}, 'ja', entries)
    male, female, *other = rows
    assert male['player_voice'] == 'male' and male['audio']['start_ms'] == 500 and male['audio']['end_ms'] == 1125
    assert female['player_voice'] == 'female'
    assert all(r['audio'] is None and r['voice_status'] == 'unavailable' for r in [female, *other])
    assert len(rows) == 8
    assert male['film_caption'] == {'scene': 'Movie', 'start_ms': 500, 'end_ms': 1125, 'movies': []}
    assert rows[-1]['film_caption'] == {'scene': 'Film', 'start_ms': 0, 'end_ms': 2500, 'movies': [
        {'video_id': 30, 'player_voice': 'male', 'path': 'Film_m.usm', 'size': 100, 'md5': 'a'*32},
        {'video_id': 31, 'player_voice': None, 'path': 'Alternate.usm', 'size': 120, 'md5': 'b'*32}]}
    configs[0]['CaptionPath'] = 'Config/CutSceneCaption/Another_Caption.json'
    with pytest.raises(ValueError):
        films.caption_rows(tools, catalog, {}, 'ja', entries)


def test_unrecognized_recording_format_has_no_authorized_clock():
    assert films._duration(track()) == 2000
    assert films._duration(bytes(86)) is None
    assert films._duration(track()[:70]) is None


def test_resolved_caption_names_keep_resource_ids_and_scope_new_player_branches(tmp_path):
    filename, identity = 'New_Episode-2_Caption.json', 'design_54c6a61d50e11224'
    script = {'CaptionList': [{'CaptionTextID': {'Hash': 69}, 'StartTime': .5, 'EndTime': 1.5}]}
    video = {'VideoID': 9001, 'VideoPath': 'OwnedMovie.usm',
             'CaptionPath': 'Config/CutSceneCaption/' + filename}
    sources = {'ExcelOutput/CutSceneConfig.json': [], 'ExcelOutput/VoiceConfig.json': [],
               'ExcelOutput/VideoConfig.json': [video]}
    movie = SimpleNamespace(name='OwnedMovie.usm', digest='a' * 32, size=99)
    catalog = SimpleNamespace(file=sources.__getitem__, movie_files={'ownedmovie.usm': movie},
                              caption_scripts=lambda: [(filename, script)], caption_identities={filename: identity})
    def prepare():
        return films.caption_rows(tmp_path, catalog, {'en': {'69': 'Owned fixture caption'}}, 'en', {})
    row, = prepare()
    assert row['text_id'] == 'starrail:film-' + identity + '-0'
    assert row['film_caption']['scene'] == 'New_Episode-2'
    assert row['film_caption']['movies'][0]['video_id'] == 9001
    # Discovering an actual movie and display clocks alone cannot authorize a
    # spoken cut. Newly evidenced player alternatives remain separate.
    assert row['audio'] is None and row['voice_status'] == 'unavailable'
    video['IsPlayerInvolved'] = True
    catalog.movie_files = {'ownedmovie_m.usm': SimpleNamespace(name='OwnedMovie_m.usm', digest='b' * 32, size=100)}
    male, female = prepare()
    assert [(r['text_id'], r['player_voice']) for r in [male, female]] == [
        ('starrail:film-' + identity + '-0_m', 'male'), ('starrail:film-' + identity + '-0_f', 'female')]
    assert all(r['audio'] is None and r['voice_status'] == 'unavailable' for r in [male, female])
    catalog.caption_identities[filename] = '../invalid'
    with pytest.raises(ValueError):
        prepare()


def test_mission_selects_caption_track_by_spoken_language_after_normal_updates(tmp_path):
    prefix = 'Config/CutSceneCaption/'
    primary, alternate = prefix + 'Song_1_Caption.json', prefix + 'Song_2_Caption.json'
    path = 'Config/Level/Mission/123/Act/Act12301.json'
    task = {'$type': 'RPG.GameCore.PlayVideo', 'VideoID': 34}
    rule = {'$type': 'RPG.GameCore.PredicateTaskList',
            'Predicate': {'$type': 'RPG.GameCore.ByCurrentAudioLanguage', 'AudioLanguage': 'CN'},
            'SuccessTaskList': [task], 'FailedTaskList': [task | {'OverrideCaptionPath': alternate}]}
    source = {'ExcelOutput/VideoConfig.json': [{'VideoID': 34, 'VideoPath': 'Song.usm', 'CaptionPath': primary}],
              'ExcelOutput/PerformanceVideo.json': [{'PerformanceID': 12301, 'PerformancePath': path}],
              'ExcelOutput/CutSceneConfig.json': [], 'ExcelOutput/VoiceConfig.json': [],
              path: {'OnStartSequece': [{'TaskList': [rule]}]}}
    file = SimpleNamespace(name='Song.usm', digest='a'*32, size=99, task_ids=(123,))
    scripts = [(name, {'CaptionList': [{'CaptionTextID': {'Hash': key}, 'EndTime': end}]})
               for name, key, end in [('Song_1_Caption.json', 11, .5), ('Song_2_Caption.json', 22, 1.)]]
    catalog = SimpleNamespace(file=source.__getitem__, movie_files={'song.usm': file}, caption_scripts=lambda: scripts)
    for locale, scene in [('en', 'Song_2'), ('ja', 'Song_2'), ('ko', 'Song_2'),
                          ('zh-Hans', 'Song_1'), ('zh-Hant', 'Song_1')]:
        row, = films.caption_rows(tmp_path, catalog, {locale: {'11': 'A', '22': 'B'}}, locale, {})
        assert row['film_caption']['scene'] == scene
        assert row['film_caption']['movies'][0]['video_id'] == 34 and row['audio'] is None
    rule['Predicate']['AudioLanguage'] = 'JP'
    routes, suppressed = films._movie_sources(catalog, scripts, 'ja')
    assert set(routes) == {'Song_1'} and suppressed == {'Song_2'}
    rule['Predicate']['$type'] = 'RPG.GameCore.OtherCondition'
    routes, suppressed = films._movie_sources(catalog, scripts, 'ja')
    assert set(routes) == {'Song_1'} and not suppressed
    file.task_ids = (567,)
    assert films._movie_sources(catalog, scripts, 'ja') == (routes, set())


def test_tutorial_uses_authored_movie_owner_and_missing_text_cannot_invent_audio(tmp_path):
    filename, identity = 'BattleCollegeCaption/Future_Lesson.json', 'design_0123456789abcdef'
    script = {'CaptionList': [{'CaptionTextID': {'Hash': 69}, 'StartTime': .5, 'EndTime': 1.5},
                              {'CaptionTextID': {'Hash': 70}, 'EndTime': 2.5}]}
    video = {'VideoID': 40001, 'VideoPath': 'DifferentLesson.usm',
             'CaptionPath': 'Config/' + filename}
    source = {'ExcelOutput/CutSceneConfig.json': [], 'ExcelOutput/VoiceConfig.json': [],
              'ExcelOutput/VideoConfig.json': [], 'ExcelOutput/LoopCGConfig.json': [video]}
    catalog = SimpleNamespace(file=source.__getitem__, caption_scripts=lambda: [(filename, script)],
                              caption_identities={filename: identity}, movie_files={
        'differentlesson.usm': SimpleNamespace(name='DifferentLesson.usm', digest='a' * 32, size=99),
        'future_lesson.usm': SimpleNamespace(name='Future_Lesson.usm', digest='b' * 32, size=100)})
    def prepare():
        return films.caption_rows(tmp_path, catalog, {'en': {'69': 'A fixture tutorial caption'}}, 'en', {})
    row, = prepare()
    assert row['text_id'] == 'starrail:film-' + identity + '-0'
    assert row['film_caption'] == {'scene': 'BattleCollegeCaption/Future_Lesson', 'start_ms': 500,
                                   'end_ms': 1500, 'movies': [{'video_id': 40001, 'player_voice': None,
                                        'path': 'DifferentLesson.usm', 'size': 99, 'md5': 'a' * 32}]}
    assert row['audio'] is None and row['voice_status'] == 'unavailable'
    # New lesson names/IDs and actual protagonist files follow the authored
    # table. A movie with a matching caption basename never supplies audio.
    video['IsPlayerInvolved'] = True
    catalog.movie_files = {'differentlesson_m.usm': SimpleNamespace(name='DifferentLesson_m.usm', digest='c' * 32, size=101)}
    male, female = prepare()
    assert [r['player_voice'] for r in (male, female)] == ['male', 'female']
    assert all(r['audio'] is None and r['voice_status'] == 'unavailable' for r in (male, female))
    assert male['film_caption']['movies'] == female['film_caption']['movies']
    assert len(male['film_caption']['movies']) == 1
    video['CaptionPath'] = 'Config/CutSceneCaption/Future_Lesson_Caption.json'
    with pytest.raises(ValueError):
        prepare()


def test_reviewed_take_survives_repackaging_but_requires_the_same_movie_voice_and_caption(tmp_path, monkeypatch):
    raw = b'independently matched recording'
    checksum = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(films, 'REVIEWED_MOVIES', {('Film', 24, 'a'*32): {77: (12, {'zh-Hans': checksum})}})
    movie = {'video_id': 24, 'md5': 'a'*32, 'player_voice': None}
    bind = {'locale': 'zh-Hans', 'source': 'Chinese(PRC)/voice/line.wem', 'publisher': 'new-package-generation'}
    row = {'text_id': 'starrail:12', 'audio': bind}
    sources = films._reviewed_sources([row])
    monkeypatch.setattr(films.voices, 'extract', lambda *args: raw)
    def take(movies, caption=77, locale='zh-Hant', index=sources):
        return films._reviewed_take(tmp_path, 'Film', movies, caption, locale, index)
    assert take([movie]) == bind
    assert take([movie], caption=78) is None
    assert take([movie], locale='ja') is None
    assert take([movie | {'md5': 'b'*32}]) is None
    assert take([movie | {'video_id': 25}]) is None
    assert take([movie, movie]) is None
    assert take([movie], index=films._reviewed_sources([row, row])) is None
    monkeypatch.setattr(films.voices, 'extract', lambda *args: b'new take')
    assert take([movie]) is None
