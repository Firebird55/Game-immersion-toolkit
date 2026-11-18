import test from 'node:test';
import assert from 'node:assert/strict';
import {waitForOwnedOriginalAudio} from '../scripts/android-original-audio-readiness.mjs';

function row(overrides = {}) {
  return {context:{runtime_id:'authored-runtime',account_generation:7},status:{capture:{running:true,source_generation:12}},
    lines:[{id:4294967297,text_id:'authored:bridge',has_audio:false,original_audio_expected:true,audio_pending:true}],...overrides};
}
async function run(values) {
  let index=0, evidence;
  const until=async (read,label,...extra) => {
    assert.equal(extra.length,0,'Keep the existing overall deadline');
    assert.match(label,/OCR and original audio/);
    for (let n=0;n<values.length;n++) { const value=await read();if(value)return value; }
    throw Error('Existing deadline elapsed');
  };
  try {
    const snapshot=await waitForOwnedOriginalAudio(async()=>structuredClone(values[index++]),until,
      {accountGeneration:7,report:value=>{evidence=value;}});
    return {snapshot,evidence};
  } catch(error) {error.evidence=evidence;throw error;}
}
test('waits for the same first row recording after a genuine pending snapshot', async () => {
  const pending=row(), ready=row();ready.lines[0].has_audio=true;ready.lines[0].audio_pending=false;
  const result=await run([row({lines:[]}),pending,ready]);
  assert.equal(result.snapshot.lines[0].has_audio,true);
  assert.equal(result.evidence.pending_polls,1);assert.equal(result.evidence.line_id,4294967297);
  assert.equal(result.evidence.state,'ready');
});
test('an indefinitely pending recording is a timeout, never a successful OCR-only result',async()=>{
  await assert.rejects(run([row(),row()]),error=>error.evidence.state==='timeout' && error.evidence.pending_polls===2);
});
for (const [name,change,reason] of [
  ['row',value=>{value.lines[0].id++;value.lines[0].has_audio=true;},'first-row-replaced'],
  ['account',value=>{value.context.account_generation=8;},'account-changed'],
  ['source',value=>{value.status.capture.source_generation++;},'source-changed'],
  ['runtime',value=>{value.context.runtime_id='other';},'source-changed'],
  ['pause',value=>{value.status.capture.running=false;},'capture-stopped'],
  ['failure',value=>{value.lines[0].audio_pending=false;},'materialization-failed'],
  ['foreign-caption',value=>{value.lines[0].text_id='other';},'foreign-first-row'],
  ['unexpected-omission',value=>{value.lines[0].original_audio_expected=false;},'original-not-expected'],
]) test('rejects '+name+' without borrowing a newer original',async()=>{
  const second=row();change(second);
  await assert.rejects(run([row(),second]),error=>error.evidence.state==='failed' && error.evidence.reason===reason);
});
