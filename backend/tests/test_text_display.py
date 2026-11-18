"""The shared pure cleanup retains existing rich-text and locale behavior."""
import pytest

from backend import text_display, textmaps, languages


@pytest.mark.parametrize(('value','expected'), [
    (None,''), ('',''), (0,''),
    ('<b>Hello &amp; goodbye</b>','Hello & goodbye'),
    ('<color=#fff>你好</color> {PlayerName}\\n ようこそ','你好 {PlayerName} ようこそ'),
    ('A\r\nB\u00a0 C','A B C'),
    ('&lt;i&gt;안녕하세요&lt;/i&gt;','안녕하세요'),
    ('<ruby>漢字<rt>かんじ</rt></ruby>','漢字かんじ'),
    ('First<br/>second','Firstsecond'),
    ('Keep <unfinished','Keep <unfinished'),
])
def test_display_contract_preserves_official_text(value, expected):
    assert text_display.display_text(value) == expected
    assert textmaps.display_text is text_display.display_text
    assert textmaps.TAG_RE is text_display.TAG_RE


@pytest.mark.parametrize('locale',['en','zh-Hans','zh-Hant','ja','ko'])
def test_default_audio_identity_and_explicit_pack_identity(locale):
    from backend.steam_games import STEAM_GAMES
    assert languages.audio_locale(locale) == ('zh-Hans' if locale=='zh-Hant' else locale)
    for game in ('riseofthetombraider','shadowofthetombraider',next(iter(STEAM_GAMES))):
        assert languages.audio_locale(locale,game) == locale
    assert languages.audio_locale(locale,'wuwa') == ('zh-Hans' if locale=='zh-Hant' else locale)
