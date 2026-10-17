import json

from pathlib import Path
import pytest

from backend import cyberpunk_assets as assets


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_only_requested_official_text_and_matching_original_voice_are_extracted(tmp_path, monkeypatch, locale):
    root = tmp_path / 'game'
    content = root / 'archive/pc/content'
    content.mkdir(parents=True)
    for code in assets.TEXT_LOCALES.values():
        (content / f'lang_{code}_text.archive').touch()
        (content / f'lang_{code}_voice.archive').touch()
    calls = []
    monkeypatch.setattr(assets, 'ensure_wolvenkit', lambda _: Path('verified-tool'))
    def run(_executable, *args):
        if args[0] == 'unbundle':
            archive = Path(args[1]); calls.append(archive.name)
            output = Path(args[args.index('-o') + 1]); output.mkdir(parents=True, exist_ok=True)
            name = 'voiceovermap.json.json' if '_voice.' in archive.name else 'subtitles.json.json'
            (output / name).write_text('{}')
    monkeypatch.setattr(assets, 'run_wolvenkit', run)
    def entries(path):
        code = path.parent.name.removeprefix('lang_').removesuffix('_text').removesuffix('_voice')
        if '_voice' in path.parent.name:
            return [{'stringId': 123, 'femaleResPath': {'DepotPath': {'$value': code + '/spoken.wem'}}}]
        return [{'stringId': 123, 'femaleVariant': 'Official ' + code + ' dialogue.'}]
    monkeypatch.setattr(assets, 'json_entries', entries)
    target = 'fr' if locale != 'fr' else 'zh-hans'
    payload = assets.index_language(root, tmp_path / 'cache', locale, [target])
    row = payload['records'][0]
    assert row['source_locale'] == locale and row['audio_locale'] == locale
    assert row['audio']['archive'].endswith(f'lang_{assets.TEXT_LOCALES[locale]}_voice.archive')
    assert row['audio']['depot'] == assets.TEXT_LOCALES[locale] + '/spoken.wem'
    assert len(calls) == 3
    assert all('_voice.' not in call or call == f'lang_{assets.TEXT_LOCALES[locale]}_voice.archive' for call in calls)
    assert len(row['texts']) == 2


def test_wrong_language_audio_reference_is_rejected_before_extraction(tmp_path):
    with pytest.raises(ValueError, match='locale'):
        assets.extract_voice(tmp_path, {'archive': 'archive/pc/content/lang_en_voice.archive',
            'depot': 'voice.wem', 'locale': 'ko'}, Path('tool'), tmp_path)

def test_source_voice_pack_missing_never_uses_another_locale(tmp_path, monkeypatch):
    content = tmp_path / 'game/archive/pc/content'
    content.mkdir(parents=True)
    (content / 'lang_ko_text.archive').touch()
    (content / 'lang_en_voice.archive').touch()
    monkeypatch.setattr(assets, 'ensure_wolvenkit', lambda _: Path('tool'))
    def run(_tool, *args):
        if args[0] == 'unbundle':
            assert 'lang_en_voice' not in str(args[1])
            output = Path(args[args.index('-o') + 1]); output.mkdir(parents=True, exist_ok=True)
            (output / 'subtitles.json.json').write_text('{}')
    monkeypatch.setattr(assets, 'run_wolvenkit', run)
    monkeypatch.setattr(assets, 'json_entries', lambda _: [{'stringId': 1, 'femaleVariant': '공식 대사입니다.'}])
    result = assets.index_language(tmp_path / 'game', tmp_path / 'cache', 'ko', ['nl'])
    assert result['records'] and not any(r['audio'] for r in result['records'])
    assert result['missing_translation_locales'] == ['nl']
