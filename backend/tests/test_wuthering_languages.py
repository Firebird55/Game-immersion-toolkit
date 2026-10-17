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
