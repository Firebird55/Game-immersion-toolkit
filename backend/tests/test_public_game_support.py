"""Public capability claims must stay within the released asset readers."""
import json
from pathlib import Path

from backend.languages import GAME_LOCALES, audio_locale
from backend.game_assets import LOCAL_GAMES, asset_adapter
from backend.game_paths import GAMES
from backend.games import GAME_PROFILES
from backend.mobile_bundle import bundle_name


def test_public_game_support_matches_readers():
    data = json.loads((Path(__file__).parents[2] / 'public/mobile-capture/games-data.json').read_text(encoding='utf-8'))
    assert {game['id'] for game in data['games']} == set(GAME_LOCALES)
    assert set(GAME_LOCALES) == set(LOCAL_GAMES) | {'pragmata', 'zzz'} == set(GAMES) == set(GAME_PROFILES)
    for game in data['games']:
        assert set(game['targets']) <= set(game['officialText']) | set(game.get('readerOnlyText', [])) | ({'en'} if game['id'] == 'hito' else set())
        assert set(game['unverified']) == set(game['officialText']) - set(game['targets'])
        assert not set(game['unverified']) & set(game['targets'])
        assert game['coverage'] and game['source'].startswith('https://store.')
        for field in ('study', 'audio', 'officialText', 'targets'):
            assert len(game[field]) == len(set(game[field]))
            assert set(game[field]) <= set(data['languages'])
        if game['id'] == 'hito':
            assert game['textOnly'] and game['study'] == ['zh-Hans'] and game['targets'] == ['en']
            continue
        reader, _ = asset_adapter(game['id'])
        if hasattr(reader, 'CAPTURE_CAPABILITIES'):
            from backend.steam_games import STEAM_GAMES
            assert game['captureCapabilities'] == reader.CAPTURE_CAPABILITIES
            assert game['captureCapabilities']['voiced'] == STEAM_GAMES[game['id']].voiced_capture
        assert set(game['study']) == set(reader.SUPPORTED_LOCALES) == set(GAME_LOCALES[game['id']])
        assert set(game['audio']) == {audio_locale(code, game['id']) for code in game['study']}
        if {'zh-Hans', 'zh-Hant'} <= set(game['audio']):
            assert bundle_name(game['id'], ['zh-Hans']) != bundle_name(game['id'], ['zh-Hant'])
        assert set(game.get('officialAudio', [])) <= set(game['audio'])
        assert set(game.get('playbackVerified', [])) <= set(game['study'])
        assert set(game.get('formatOnly', [])) <= set(game['study'])
        assert not set(game.get('playbackVerified', [])) & set(game.get('formatOnly', []))
        assert set(game['targets']) <= set(reader.TEXT_LOCALES)
        # Storefront-only locales must be excluded explicitly, rather than disappear.
        assert set(game['officialText']) <= set(reader.TEXT_LOCALES) | set(game['unverified'])
    by_id = {game['id']: game for game in data['games']}
    for name in ('beyond', 'heavyrain'):
        assert 'nl' in by_id[name]['study']
        assert {'zh-Hans', 'zh-Hant'} <= set(by_id[name]['targets'])
        assert 'zh-Hans' not in by_id[name]['audio']
    assert 'pt-BR' not in by_id['heavyrain']['targets']
    assert {'pt-PT', 'pt-BR', 'es-ES', 'es-419'} <= set(by_id['beyond']['targets'])
    assert 'es-419' in by_id['zzz']['unverified']
