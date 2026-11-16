"""Original branch selection uses owned synthetic banks, never game assets."""
import json
from types import SimpleNamespace

import pytest

from backend import nte_assets as assets
from backend.multilingual_index import MultilingualTextIndex
from backend.nte_cinematics import SRT_ROOT
from backend.tests.test_nte_cinematics import synthetic_switch


TEXT = {'en': 'A synthetic response from the chosen protagonist.',
        'zh-Hans': '这是所选主角的一句合成测试台词。', 'zh-Hant': '這是所選主角的一句合成測試台詞。',
        'ja': '選んだ主人公の合成テスト用の台詞です。', 'ko': '선택한 주인공의 합성 테스트 대사입니다.'}
EVENT = 'Play_Vo_Fixture_Player_021'


def full_frame(value, text, monkeypatch):
    # Exercise the common floating-dialogue path without claiming NTE's
    # remaining presentation audit is complete or changing its product setup.
    from backend.steam_games import STEAM_GAMES
    with monkeypatch.context() as patch:
        patch.setitem(STEAM_GAMES, 'nte', SimpleNamespace(floating_dialogue=True))
        return value.match_full_frame_voice_lines([text])


def cache(root, locale='en', missing=(), **conditions):
    (root / 'banks').mkdir()
    row = {'ns': 'ST_Legend_Celebration', 'key': 'Fixture_Key', 'value': TEXT[locale]}
    (root / 'localization.json').write_text(json.dumps({assets.TEXT_LOCALES[locale]: [row],
        'fr': [{**row, 'value': 'Une réplique de test du personnage choisi.'}]}), encoding='utf-8')
    (root / 'dialogue-events.json').write_text(json.dumps({'fixture_key': [EVENT.lower()]}))
    media = [f'HT/Content/WwiseAudio/Media/{assets.VOICE_LOCALES[locale]}/{value}.wem'
             for value in (123, 456) if value not in missing]
    (root / 'media.json').write_text(json.dumps(media))
    synthetic_switch(root / 'banks' / (EVENT + '.bnk'), event_name=EVENT,
                     language=assets.VOICE_LOCALES[locale], **conditions)


def index(root, records, locale='en'):
    (root / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte',
        'source_locale': locale, 'records': records}), encoding='utf-8')
    result = MultilingualTextIndex('nte', root)
    assert result.ready, result.message
    return result


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_ordinary_dialogue_follows_both_authored_player_branches_in_every_dub(tmp_path, locale, monkeypatch):
    cache(tmp_path, locale)
    records = assets.build_records(tmp_path, source_locale=locale, target_locales=['fr'])
    assert len(records) == 2
    for row, gender, media in zip(records, ['female', 'male'], [123, 456]):
        assert row['text_id'] == f'nte:ST_Legend_Celebration:Fixture_Key:{gender}'
        assert row['player_voice'] == gender and row['voice_status'] == 'voiced'
        assert row['audio']['depot'].endswith(f'/{media}.wem')
        assert row['audio']['gain_db'] == -6 and row['audio']['event'] == EVENT
        assert row['source_text'] == row['texts'][locale] == TEXT[locale]
        assert row['texts']['fr'] == 'Une réplique de test du personnage choisi.'
        assert row['dialogue_kind'] == 'conversation'
    value = index(tmp_path, records, locale)
    assert value.match_lines([TEXT[locale]], exact_only=True) is None
    for gender in ['female', 'male']:
        value.player_voice = gender
        hit = value.match_lines([TEXT[locale]], exact_only=True)
        assert hit and hit.text_id.endswith(':' + gender)
        assert full_frame(value, TEXT[locale], monkeypatch)[0].text_id == hit.text_id


@pytest.mark.parametrize('missing,available', [(123, 'male'), (456, 'female')])
def test_missing_other_player_recording_does_not_veto_the_available_player(tmp_path, missing, available, monkeypatch):
    cache(tmp_path, missing=[missing])
    records = assets.build_records(tmp_path, source_locale='en', target_locales=['fr'])
    assert {r['voice_status'] for r in records} == {'voiced', 'unavailable'}
    value = index(tmp_path, records)
    value.capture_unvoiced = True
    assert value.match_lines([TEXT['en']], exact_only=True) is None
    value.player_voice = available
    assert value.match_lines([TEXT['en']], exact_only=True).text_id.endswith(':' + available)
    assert full_frame(value, TEXT['en'], monkeypatch)[0].text_id.endswith(':' + available)
    value.player_voice = 'female' if available == 'male' else 'male'
    assert value.match_lines([TEXT['en']], exact_only=True) is None
    assert full_frame(value, TEXT['en'], monkeypatch) == []
    # A genuine independent prompt remains ambiguous for either protagonist.
    records.append({**records[0], 'text_id': 'nte:prompt', 'audio': None,
                    'player_voice': None, 'voice_status': 'unvoiced'})
    value = index(tmp_path, records)
    value.player_voice = available
    assert value.match_lines([TEXT['en']], exact_only=True) is None


@pytest.mark.parametrize('conditions', [{'group': 'Other'}, {'continuous': True}, {'fade': True}])
def test_unverified_switches_never_get_a_default_ordinary_recording(tmp_path, conditions):
    cache(tmp_path, **conditions)
    records = assets.build_records(tmp_path, source_locale='en')
    assert all(not r['audio'] and r['voice_status'] == 'unavailable' for r in records)
    value = index(tmp_path, records)
    value.player_voice = 'female'
    value.capture_unvoiced = True
    assert value.match_lines([TEXT['en']], exact_only=True) is None


@pytest.mark.parametrize('gain', [float('nan'), float('inf'), -61, 25])
def test_unsupported_authored_gain_does_not_advertise_a_playable_player_recording(tmp_path, gain):
    cache(tmp_path, gain=gain)
    records = assets.build_records(tmp_path, source_locale='en')
    assert len(records) == 2
    assert all(r['voice_status'] == 'unavailable' and not r['audio'] for r in records)


def test_ordinary_alias_cannot_assign_both_player_voices_to_another_namespace(tmp_path):
    cache(tmp_path)
    path = tmp_path / 'localization.json'
    text = json.loads(path.read_text())
    text['en'].append({**text['en'][0], 'ns': 'ST_Other'})
    path.write_text(json.dumps(text))
    assert all(not r['audio'] for r in assets.build_records(tmp_path, source_locale='en'))


@pytest.mark.parametrize('ambiguous', [False, True])
def test_owned_movie_caption_uses_verified_cuts_instead_of_ordinary_whole_mix(tmp_path, ambiguous):
    cache(tmp_path)
    binding = {'subtitle': SRT_ROOT + 'Fixture.srt', 'event': EVENT, 'namespace': 'ST_Legend_Celebration'}
    text = '1\n00:00:01,000 --> 00:00:02,000\nFixture_Key\n'
    if ambiguous:
        text += '\n2\n00:00:03,000 --> 00:00:04,000\nFixture_Key\n'
    (tmp_path / 'cinema-subtitles.json').write_text(json.dumps({binding['subtitle']: text}))
    records = assets.build_records(tmp_path, [binding], source_locale='en')
    assert len(records) == 2 and {r['player_voice'] for r in records} == {'female', 'male'}
    for row in records:
        assert row['dialogue_kind'] == 'cinematic'
        if ambiguous:
            assert not row['audio'] and row['voice_status'] == 'unavailable'
        else:
            assert row['audio']['start_ms'] == 1000 and row['audio']['end_ms'] == 2000
