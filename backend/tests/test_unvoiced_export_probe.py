"""Real isolated workers on owned GoldSrc bytes, without game/account data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend import halflife_assets, language_worker, local_voice, accounts
from backend.mobile_library import prepare_source
from backend.unvoiced_export_probe import authored_install, probe, read_export

ROOT = Path(__file__).resolve().parents[2]


def test_real_workers_export_only_confirmed_messages_and_mobile_reader_accepts_them(tmp_path):
    modules = {'game-index': 'game_index_worker', 'language': 'language_worker', 'mobile-export': 'mobile_export_worker'}
    calls = []
    environment = {**os.environ, 'LOCALAPPDATA': str(tmp_path / 'private-settings'),
        'PROXY_TRANSCRIPT_PROJECT_ROOT': str(ROOT)}
    def run_worker(kind, arguments, *, expected_status=0):
        completed = subprocess.run([sys.executable, '-m', 'backend.' + modules[kind], *arguments],
            cwd=ROOT, env=environment, capture_output=True, timeout=90)
        assert completed.returncode == expected_status, f'{kind} unexpected exit {completed.returncode}'
        calls.append((kind, expected_status))
        return completed
    layout = SimpleNamespace(work_root=tmp_path / 'private-work', default_export_root=tmp_path / 'exports')
    result = probe(layout, run_worker)
    assert result['mobile_export_worker'] == 'passed'
    assert result['missing_selected_pack'] == 'rejected'
    assert result['failed_export_previous_bundle'] == 'preserved'
    assert result['audio_decoder_used'] is False
    assert result['installed_game_voice_export'] == 'not-run'
    assert result['native_windows_11_acceptance'] == 'unavailable'
    assert result['r19_complete'] is False
    assert calls.count(('mobile-export', 0)) == 4
    assert ('language', 1) in calls and ('mobile-export', 1) in calls
    assert {case['source_locale'] for case in result['cases']} == {'en', 'zh-Hans'}
    assert len(halflife_assets.SUPPORTED_LOCALES) == 8 and 'de' in halflife_assets.SUPPORTED_LOCALES
    # The production mobile parser checks the actual child-produced ZIP,
    # including metadata, segment SHA, study text and absence of voice packs.
    if not shutil.which('node'):
        pytest.skip('Node is required for the additional mobile-reader interoperability assertion')
    script = r"""
import {openSync,readSync,fstatSync,closeSync} from 'node:fs';
import {openLibraryFiles,readCatalog,validateVoices} from './public/mobile-capture/library.mjs';
const fd=openSync(process.argv[1],'r'),size=fstatSync(fd).size;
const file={size,slice(start,end){const data=Buffer.alloc(end-start);let n=0;while(n<data.length){const got=readSync(fd,data,n,data.length-n,start+n);if(!got)throw Error('EOF');n+=got;}return new Blob([data]);}};
try{const opened=await openLibraryFiles([file]),catalog=await readCatalog(opened[0]);
console.log(JSON.stringify({rows:catalog.rows.map(row=>({id:row.textId,source:row.sourceLocale,target:row.translationLocale,audio:row.audio})),voices:opened.slice(1).reduce((count,zip)=>count+validateVoices(zip,catalog).length,0)}));}finally{closeSync(fd);}
"""
    for source, target in (('en', 'zh-Hans'), ('zh-Hans', 'en')):
        bundle = read_export(layout.default_export_root / 'authored-unvoiced' / source, source, target)
        parsed = subprocess.run(['node', '--input-type=module', '-e', script, str(bundle)], cwd=ROOT,
            check=True, capture_output=True, text=True, timeout=30)
        assert json.loads(parsed.stdout) == {'rows': [{'id': 'halflife:title:card', 'source': source,
            'target': target, 'audio': None}], 'voices': 0}


def test_confirmed_unvoiced_preparation_has_no_decoder_or_account_dependency(tmp_path, monkeypatch):
    install = authored_install(tmp_path / 'install')
    snapshot = tmp_path / 'textmap.json'
    language_worker.build('halflife', install, tmp_path, 'zh-Hans', ['en'], snapshot)
    def forbidden(*_args, **_options):
        pytest.fail('An unvoiced explicit export initialized a voice decoder or account store')
    monkeypatch.setattr(local_voice, 'LocalVoiceAssetService', forbidden)
    monkeypatch.setattr(accounts, 'AccountStore', forbidden)
    rows, _voice, check, service = prepare_source(tmp_path, 'halflife', tmp_path / 'decoded',
        source_path=snapshot, expected_source_locale='zh-Hans', translation_locale='en')
    assert service is None and len(rows) == 1
    assert rows[0]['textId'] == 'halflife:title:card' and rows[0]['sourceVoice'] is None
    check.force()
    (install / 'valve/titles.txt').write_text('changed owned title table', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        check.force()


@pytest.mark.parametrize('alteration', ['unknown', 'category', 'audio', 'voiced-capability', 'legacy'])
def test_stale_or_contradictory_half_life_snapshots_never_create_unvoiced_coverage(tmp_path, alteration):
    install = authored_install(tmp_path / 'install')
    snapshot = tmp_path / 'textmap.json'
    language_worker.build('halflife', install, tmp_path, 'en', ['zh-Hans'], snapshot)
    payload = json.loads(snapshot.read_text(encoding='utf-8'))
    card = next(row for row in payload['records'] if row['text_id'] == 'halflife:title:card')
    if alteration == 'unknown':
        card.pop('voice_status')
    elif alteration == 'category':
        card['dialogue_kind'] = 'title_localization'
    elif alteration == 'audio':
        card['audio'] = {'fixture': 'unapproved binding'}
    elif alteration == 'voiced-capability':
        payload['capture_capabilities']['voiced'] = True
    else:
        payload['format'] = 1
    snapshot.write_text(json.dumps(payload), encoding='utf-8')
    options = dict(source_path=snapshot, expected_source_locale='en', translation_locale='zh-Hans')
    if alteration in {'unknown', 'category'}:
        rows, _, _, service = prepare_source(tmp_path, 'halflife', tmp_path / 'decoded', **options)
        assert rows == [] and service is None
    else:
        with pytest.raises(ValueError):
            prepare_source(tmp_path, 'halflife', tmp_path / 'decoded', **options)
