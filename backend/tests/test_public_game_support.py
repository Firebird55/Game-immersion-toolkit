"""Public capability claims must stay within the released asset readers."""
import json
from pathlib import Path

from backend import beyond_assets, cyberpunk_assets, heavy_rain_assets, nte_assets
from backend import pragmata_assets, witcher_assets, wuthering_assets, zzz_assets
from backend import starrail_assets, genshin_assets, endfield_assets
from backend.languages import GAME_LOCALES, audio_locale


def test_public_game_support_matches_readers():
    data = json.loads((Path(__file__).parents[2] / 'public/mobile-capture/games-data.json').read_text(encoding='utf-8'))
    readers = dict(zip(('beyond', 'cyberpunk', 'heavyrain', 'nte', 'pragmata', 'witcher3', 'wuwa', 'zzz'),
                       (beyond_assets, cyberpunk_assets, heavy_rain_assets, nte_assets,
                        pragmata_assets, witcher_assets, wuthering_assets, zzz_assets)))
    readers.update(starrail=starrail_assets, genshin=genshin_assets, endfield=endfield_assets)
    assert {game['id'] for game in data['games']} == set(GAME_LOCALES)
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
        reader = readers[game['id']]
        assert set(game['study']) == set(reader.SUPPORTED_LOCALES) == set(GAME_LOCALES[game['id']])
        assert set(game['audio']) == {audio_locale(code) for code in game['study']}
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
