import sqlite3
import struct
from pathlib import Path
import pytest
from backend import wuthering_assets as assets
from backend.tests.test_wuthering import plot_blob

@pytest.mark.parametrize('locale',assets.SUPPORTED_LOCALES)
def test_language_specific_gender_flags_choose_exact_source(tmp_path,locale):
    code,slot=assets.VOICE_LOCALES[locale]
    for language in {locale,'fr'}:
        path=tmp_path/assets.TEXT_LOCALES[language]/'lang_multi_text.db';path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)')
            db.execute('INSERT INTO MultiText VALUES (?,?)',('spoken','Source dialogue.' if language==locale else 'Traduction officielle.'))
    blob=bytearray(plot_blob('spoken','vo_spoken'))
    struct.pack_into('<H',blob,8+slot*2,4+slot*4);blob[32+4+slot*4]=1
    with sqlite3.connect(tmp_path/'db_plot_audio.db') as db:
        db.execute('CREATE TABLE plotaudio (Id TEXT, BinData BLOB)')
        db.execute('INSERT INTO plotaudio VALUES (?,?)',('spoken',bytes(blob)))
    files=[assets.EXTERNAL_ROOT+f'{code}_vo_spoken_{gender}.wem' for gender in ('F','M')]
    rows=assets.build_language_records(tmp_path,files,locale,['fr'])
    assert len(rows)==2 and {r['player_voice'] for r in rows}=={'female','male'}
    assert all(r['audio']['depot'] in files and r['audio_locale']==('zh-Hans' if locale=='zh-Hant' else locale) for r in rows)
    assert all(r['texts'][locale]=='Source dialogue.' and r['texts']['fr']=='Traduction officielle.' for r in rows)
    assert all(r['audio'] is None for r in assets.build_language_records(tmp_path,[assets.EXTERNAL_ROOT+'gl_vo_spoken.wem'],locale,['fr']))


def test_other_language_voice_is_rejected_before_extraction(tmp_path):
    with pytest.raises(ValueError,match='locale'):
        assets.extract_voice(tmp_path,{'depot':assets.EXTERNAL_ROOT+'zh_voice.wem','locale':'ja'},Path('tool'),tmp_path)


def test_audio_batch_cannot_mix_learning_language_performances(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, 'run_extractor', lambda *_: pytest.fail('No extraction for a mixed language batch'))
    with pytest.raises(ValueError, match='crosses study/audio locales'):
        assets.extract_voices(tmp_path, [
            {'depot': assets.EXTERNAL_ROOT + 'en_voice.wem', 'locale': 'en'},
            {'depot': assets.EXTERNAL_ROOT + 'ja_voice.wem', 'locale': 'ja'},
        ], Path('tool'), tmp_path)
    assert assets.extract_voices(tmp_path, [], Path('tool'), tmp_path) == []


def test_missing_and_empty_source_tables_never_borrow_another_language(tmp_path):
    with pytest.raises(ValueError, match='selected official.*text pack'):
        assets.build_language_records(tmp_path, [], 'ja', [])
    path = tmp_path / 'ja/lang_multi_text.db'
    path.parent.mkdir()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)')
    with pytest.raises(ValueError, match='empty; no other language'):
        assets.build_language_records(tmp_path, [], 'ja', [])


def test_empty_official_translation_table_is_reported_unavailable(tmp_path, monkeypatch):
    import json
    cache = tmp_path / 'index-cache' / 'fixture'
    root = cache / 'Client/Content/Aki/ConfigDB'
    root.mkdir(parents=True)
    for locale in ('en', 'fr'):
        path = root / locale / 'lang_multi_text.db'
        path.parent.mkdir()
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)')
            if locale == 'en':
                db.execute('INSERT INTO MultiText VALUES (?,?)', ('spoken', 'Source dialogue.'))
    with sqlite3.connect(root / 'db_plot_audio.db') as db:
        db.execute('CREATE TABLE plotaudio (Id TEXT, BinData BLOB)')
        db.execute('INSERT INTO plotaudio VALUES (?,?)', ('spoken', plot_blob('spoken', 'vo_spoken')))
    (cache / 'complete.json').write_text(json.dumps([assets.EXTERNAL_ROOT + 'en_vo_spoken.wem']))
    for filename, table, key in [('db_flowState.db', 'flowstate', 'StateKey'),
                                  ('db_cgVedio.db', 'videocaption', 'Id'),
                                  ('db_infodisplay.db', 'infodisplay', 'Id')]:
        with sqlite3.connect(root / filename) as db:
            db.execute(f'CREATE TABLE {table} ({key} TEXT, BinData BLOB)')
    with sqlite3.connect(root / assets.FLOATING_SUBTITLES) as db:
        for table in ('floatingsubtitle2d', 'floatingsubtitle3d'):
            db.execute(f'CREATE TABLE {table} (BinData BLOB)')
    monkeypatch.setattr(assets, 'fingerprint', lambda _: 'fixture')
    monkeypatch.setattr(assets, 'ensure_extractor', lambda *_: Path('mock'))
    monkeypatch.setattr(assets, 'run_extractor', lambda *_: pytest.fail('Existing tables must not be re-extracted'))
    payload = assets.index_language(tmp_path, tmp_path, 'en', ['fr', 'nl'])
    assert payload['missing_translation_locales'] == ['fr', 'nl']
    row, = payload['records']
    assert row['texts'] == {'en': 'Source dialogue.'}
    assert row['audio']['locale'] == 'en'


def test_publisher_language_worker_playback_and_batch_share_one_wuthering_release(tmp_path, monkeypatch):
    import json
    from backend import language_worker, local_voice, wuthering_release
    from backend.game_assets import preparation_fingerprint

    tools = tmp_path / 'tools'
    stamp = 'wuwa-' + 'a' * 64
    audio = {'depot': assets.EXTERNAL_ROOT + 'ja_vo_fixture.wem', 'locale': 'ja', 'publisher': stamp}
    row = {'text_id': 'wuthering:fixture', 'source_locale': 'ja', 'source_text': 'テスト用の台詞',
           'english': 'Test line', 'chinese': '', 'texts': {'ja': 'テスト用の台詞', 'en': 'Test line'},
           'audio_locale': 'ja', 'audio': audio}
    def build(directory, locale, targets, progress):
        assert directory == tools and locale == 'ja' and targets == ['en']
        return {'format': 2, 'game': 'wuwa', 'source_locale': locale, 'install': None,
                'fingerprint': stamp, 'source_mode': 'publisher', 'records': [row]}
    def extract(directory, reference, locale):
        assert directory == tools and reference == audio and locale == 'ja'
        return b'RIFF' + bytes(32)
    monkeypatch.setattr(wuthering_release, 'fingerprint', lambda directory: stamp if directory == tools else None)
    monkeypatch.setattr(wuthering_release, 'snapshot_available', lambda directory, revision: (directory, revision) == (tools, stamp))
    monkeypatch.setattr(wuthering_release, 'build_language', build)
    monkeypatch.setattr(wuthering_release, 'extract', extract)
    monkeypatch.setattr(assets, 'ensure_extractor', lambda *_: pytest.fail('Publisher mode needs no installed Unreal reader'))
    source = tmp_path / 'textmap.json'
    assert preparation_fingerprint(assets, None, tools) == stamp
    language_worker.build('wuwa', None, tmp_path, 'ja', ['en'], source)
    assert json.loads(source.read_bytes())['dialogue_inventory']['voice_counts']['voiced'] == 1

    decoder = tmp_path / 'decoder'
    decoder.touch()
    monkeypatch.setattr(local_voice, 'ffmpeg_executable', lambda: 'fake-encoder')
    def convert(args, **_):
        if str(args[0]) == str(decoder):
            inputs = [Path(args[-1])] if '-o' in args else [Path(arg) for arg in args[2:]]
            for path in inputs:
                assert path.read_bytes() == b'RIFF' + bytes(32)
                Path(args[args.index('-o') + 1] if '-o' in args else str(path) + '.wav').touch()
        else:
            Path(args[-1]).write_bytes(b'MP3' * 64)
    monkeypatch.setattr(local_voice.subprocess, 'run', convert)
    service = local_voice.LocalVoiceAssetService('wuwa', tmp_path, decoder, tmp_path / 'clips', tools_dir=tools)
    try:
        assert service.ready
        assert (service.output_dir / service.extract(row['text_id'], 1)).stat().st_size == 192
        name, = service.extract_batch([(row['text_id'], 2, '')])
        assert (service.output_dir / name).stat().st_size == 192
        service._entries[row['text_id']]['publisher'] = 'different-release'
        with pytest.raises(ValueError, match='another publisher release'):
            service.extract_batch([(row['text_id'], 3, '')])
    finally:
        service.close()
