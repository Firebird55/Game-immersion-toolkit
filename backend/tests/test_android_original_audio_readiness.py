"""Actual delayed production recording, consumed by the native probe's waiter."""
import json
from pathlib import Path
import subprocess
import threading

from backend.tests.test_direct_game_session import rig, capture, wait_audio
from backend.tests.test_game_data import download, finish

ROOT=Path(__file__).resolve().parents[2]


def test_real_owned_row_is_published_before_delayed_original_without_false_probe_failure(tmp_path):
    service,session,_owner,voice,raw=rig(tmp_path)
    voice.release=threading.Event()
    try:
        download(service);assert finish(service)['state']=='ready'
        identity=capture(session);assert voice.entered.wait(2)
        pending=session.snapshot();first=pending['lines'][0]
        assert first['id']==identity and first['has_audio'] is False
        assert first['original_audio_expected'] is True and first['audio_pending'] is True
        voice.release.set()
        assert wait_audio(session,identity).read_bytes()==raw
        ready=session.snapshot();assert ready['lines'][0]['id']==identity and ready['lines'][0]['has_audio'] is True
        assert pending['context']['account_generation']==ready['context']['account_generation']
        assert pending['status']['capture']['source_generation']==ready['status']['capture']['source_generation']
        payload=tmp_path/'snapshots.json';payload.write_text(json.dumps([pending,ready]))
        code="""
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {waitForOwnedOriginalAudio} from './scripts/android-original-audio-readiness.mjs';
const values=JSON.parse(readFileSync(process.argv[1],'utf8'));let index=0,evidence;
const result=await waitForOwnedOriginalAudio(async()=>values[index++],async read=>{
 for(let n=0;n<values.length;n++){const value=await read();if(value)return value;}throw Error('Bounded fixture ended');
},{accountGeneration:0,report:value=>{evidence=value;}});
assert.equal(result.lines[0].id,values[0].lines[0].id);assert.equal(result.lines[0].has_audio,true);
assert.equal(evidence.pending_polls,1);assert.equal(evidence.state,'ready');
console.log(JSON.stringify({same_owned_row:true,pending_observed:true,original_materialized:true}));
"""
        result=subprocess.run(['node','--input-type=module','-e',code,str(payload)],cwd=ROOT,
            capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stdout+result.stderr
        assert json.loads(result.stdout)=={'same_owned_row':True,'pending_observed':True,'original_materialized':True}
    finally:
        voice.release.set();service.close();session.stop()
