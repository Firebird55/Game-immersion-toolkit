"""Owned protagonist-text fixtures, independent of publisher dialogue."""
import json

import pytest

from backend import nte_assets as assets
from backend.nte_text import localized_records, player_variants
from backend.tests.test_nte_player_voices import cache, index


TEMPLATES = {
    'en': '<male=>The fixture guest welcomes the gentleman.<male><female=>The fixture guest welcomes the lady.<female>',
    'zh-Hans': '合成测试欢迎这位{Gender}|gender(先生,女士)参加对话。',
    'zh-Hant': '合成測試歡迎這位{Gender}|gender(先生,女士)參加對話。',
    'ja': '<male=>合成テストの男性の方をお迎えします。<male><female=>合成テストの女性の方をお迎えします。<female>',
    'ko': '<male=>합성 테스트의 남성 방문자를 환영합니다.<male><female=>합성 테스트의 여성 방문자를 환영합니다.<female>',
}


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_source_translation_and_original_voice_choose_the_same_player(tmp_path, locale):
    cache(tmp_path, locale)
    target = 'zh-Hans' if locale == 'en' else 'en'
    path = tmp_path / 'localization.json'
    source = json.loads(path.read_text())
    row = source[assets.TEXT_LOCALES[locale]][0]
    source[assets.TEXT_LOCALES[locale]] = [{**row, 'value': TEMPLATES[locale]}]
    source[assets.TEXT_LOCALES[target]] = [{**row, 'value': TEMPLATES[target]}]
    path.write_text(json.dumps(source))
    records = assets.build_records(tmp_path, source_locale=locale, target_locales=[target])
    assert len(records) == 2
    expected_source, expected_target = player_variants(TEMPLATES[locale]), player_variants(TEMPLATES[target])
    value = index(tmp_path, records, locale)
    for record, gender, media in zip(records, ['female', 'male'], [123, 456]):
        assert record['source_text'] == record['texts'][locale] == expected_source[gender]
        assert record['texts'][target] == expected_target[gender]
        assert record['audio']['depot'].endswith('/' + str(media) + '.wem')
        value.player_voice = gender
        assert value.match_lines([expected_source[gender]], exact_only=True).text_id == record['text_id']
        other = 'male' if gender == 'female' else 'female'
        assert value.match_lines([expected_source[other]], exact_only=True) is None


def test_shared_voice_retains_distinct_authored_text_and_translation_conditions():
    record = {'text_id': 'nte:Owned:one', 'audio': {'depot': 'shared.wem'},
              'voice_status': 'voiced', 'dialogue_kind': 'conversation'}
    tables = {'en': {('Owned', 'one'): 'The fixture visitor speaks.'},
              'zh-Hans': {('Owned', 'one'): TEMPLATES['zh-Hans']}}
    rows = localized_records([record], tables, 'en')
    assert [r['player_voice'] for r in rows] == ['female', 'male']
    assert rows[0]['audio'] == rows[1]['audio'] == record['audio']
    assert rows[0]['source_text'] == rows[1]['source_text'] == tables['en']['Owned', 'one']
    assert rows[0]['texts']['zh-Hans'] != rows[1]['texts']['zh-Hans']
    assert 'player_voice' not in record


@pytest.mark.parametrize('bad', ['{Gender}|gender(one)', '{Gender}|gender(one,two,three)',
    '<male=>one', '<male=>one<female=>two<female><male>', '{Gender}|gender(one(nested),two)',
    '<female=>one<female><male=>two<male><female>', '{Gender}'])
def test_unknown_template_shapes_cannot_manufacture_a_spoken_variant(bad):
    with pytest.raises(ValueError):
        player_variants(bad)
    record = {'text_id': 'nte:Owned:one:female', 'player_voice': 'female',
              'audio': {'depot': 'female.wem'}, 'voice_status': 'voiced'}
    rows = localized_records([record], {'en': {('Owned', 'one'): bad}}, 'en')
    assert len(rows) == 1 and rows[0]['text_binding_unresolved']
    assert rows[0]['voice_status'] == 'unavailable' and rows[0]['audio'] is None
    assert 'unresolved protagonist text' in ' '.join(assets.coverage_warnings(rows))


def test_bad_target_does_not_replace_valid_source_or_borrow_opposite_gender():
    record = {'text_id': 'nte:Owned:one:male', 'player_voice': 'male',
              'audio': {'depot': 'male.wem'}, 'voice_status': 'voiced'}
    rows = localized_records([record], {'en': {('Owned', 'one'): TEMPLATES['en']},
                                      'ja': {('Owned', 'one'): '{Gender}|gender(unsupported)'}}, 'en')
    assert rows[0]['voice_status'] == 'voiced'
    assert rows[0]['texts'] == {'en': player_variants(TEMPLATES['en'])['male']}
    assert rows[0]['unresolved_text_locales'] == ['ja']
    assert 'translation variants could not be resolved' in ' '.join(assets.coverage_warnings(rows))


def test_identical_authored_text_arguments_do_not_require_a_player_setting():
    record = {'text_id': 'nte:Owned:one', 'audio': {'depot': 'shared.wem'}, 'voice_status': 'voiced'}
    rows = localized_records([record], {'en': {('Owned', 'one'): 'Welcome, {Gender}|gender(guest,guest).'}}, 'en')
    assert len(rows) == 1 and rows[0]['source_text'] == 'Welcome, guest.'
    assert 'player_voice' not in rows[0]


def test_conditional_fragments_preserve_common_text_and_display_markup():
    assert player_variants('Welcome <b><male=>sir<male><female=>madam<female></b>!') == {
        'female': 'Welcome madam!', 'male': 'Welcome sir!'}
