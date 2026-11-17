"""Ordinary table joins also run in a minimal package without desktop code."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys

from backend import wuthering_assets as assets, wuthering_tables as tables
from backend.tests.test_wuthering import plot_blob


def test_ordinary_reader_reexports_the_same_parser_and_native_table_selection():
    from backend import wuthering_music
    for name in ('_field','_string','_boolean','_rows','_text_table','_narrative_refs','build_records','build_language_records'):
        assert getattr(assets,name) is getattr(tables,name)
    assert wuthering_music.TABLE == tables.MUSIC_SUBTITLE_TABLE
    expected={'db_plot_audio.db','db_MusicSubTitle.db',*assets.NARRATIVE_TABLES}
    for locale in assets.SUPPORTED_LOCALES:
        expected.update((locale+'/lang_multi_text.db',locale+'/lang_multi_text_1sthalf.db'))
    assert tables.required_tables(assets.SUPPORTED_LOCALES) == expected


def test_actual_isolated_parser_retains_five_language_dub_gender_and_shard_bindings(tmp_path):
    database=tmp_path/'tables';database.mkdir()
    values={'en':'<b>English</b> &amp; original','zh-Hans':'简体原文','zh-Hant':'繁體原文','ja':'日本語の原文','ko':'한국어 원문','fr':'Traduction officielle.'}
    for locale,value in values.items():
        path=database/locale/'lang_multi_text.db';path.parent.mkdir()
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT, RedirectDbIndex INTEGER)')
            db.execute('INSERT INTO MultiText VALUES (?,?,?)',('spoken','wrong shard placeholder' if locale=='ja' else value,1 if locale=='ja' else 0))
        if locale=='ja':
            with sqlite3.connect(path.with_name('lang_multi_text_1sthalf.db')) as db:
                db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)');db.execute('INSERT INTO MultiText VALUES (?,?)',('spoken',value))
    blob=bytearray(plot_blob('spoken','vo_spoken'))
    for slot in (4,5,6,7):struct.pack_into('<H',blob,8+slot*2,4+slot*4);blob[32+4+slot*4]=1
    with sqlite3.connect(database/'db_plot_audio.db') as db:
        db.execute('CREATE TABLE plotaudio (Id TEXT, BinData BLOB)');db.execute('INSERT INTO plotaudio VALUES (?,?)',('spoken',bytes(blob)))
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in database.rglob('*.db')}
    package=tmp_path/'package'/'backend';package.mkdir(parents=True);(package/'__init__.py').write_text('',encoding='utf8')
    for name in ('wuthering_tables','wuthering_locales','text_display','languages','language_contracts','preparation_errors'):
        module=importlib.import_module('backend.'+name);shutil.copyfile(module.__file__,package/(name+'.py'))
    program=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
blocked={'backend.game_tools','backend.wuthering_assets','backend.wuthering_release','backend.textmaps','backend.models','backend.steam_games','backend.runtime_bundle','backend.runtime_paths','backend.wuthering_metadata'}
class Denied:
 def find_spec(self,fullname,*args):
  if fullname in blocked or fullname.split('.')[0] in ('Crypto','rapidfuzz','pydantic'):raise AssertionError('Nonportable parser import: '+fullname)
sys.meta_path.insert(0,Denied())
def audit(event,args):
 if event in ('socket.connect','subprocess.Popen','winreg.OpenKey','winreg.SetValue'):raise AssertionError('Unexpected parser operation: '+event)
sys.addaudithook(audit)
from backend import wuthering_tables as tables
root=Path(sys.argv[2]);result={}
for locale in tables.SUPPORTED_LOCALES:
 code,slot=tables.VOICE_LOCALES[locale]
 files=[tables.EXTERNAL_ROOT+code+'_vo_spoken_'+gender+'.wem' for gender in ('F','M')]
 rows=tables.build_language_records(root,files,locale,['fr'])
 assert len(rows)==2 and {r['player_voice'] for r in rows}=={'female','male'}
 assert all(r['audio']['depot'] in files and r['texts']['fr']=='Traduction officielle.' and r['voice_status']=='voiced' for r in rows)
 assert all(r['audio_locale']==('zh-Hans' if locale=='zh-Hant' else locale) for r in rows)
 assert all(r['audio'] is None and r['voice_status']=='unavailable' for r in tables.build_language_records(root,[],locale,['fr']))
 result[locale]=rows[0]['source_text']
assert not (blocked&set(sys.modules))
print(json.dumps(result))
'''
    result=subprocess.run([sys.executable,'-B','-I','-c',program,str(package.parent),str(database)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    expected={k:v for k,v in values.items() if k!='fr'};expected['en']='English & original'
    assert json.loads(result.stdout)==expected
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
