import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmCaptions} from '../public/mobile-capture/caption-confirmation.mjs';
test('one dropout retains independent captions but never confirms alone',()=>{
 let state=confirmCaptions(new Map(),['a'],0,true);
 state=confirmCaptions(state,['b'],250,true);
 assert.equal(state.get('a').count,1);
 state=confirmCaptions(state,['a','b'],500,true);
 assert.equal(state.get('a').count,2);assert.equal(state.get('b').count,2);
});
test('two missing scans or expired observations cannot combine',()=>{
 let state=confirmCaptions(new Map(),['a'],0,true);
 state=confirmCaptions(state,[],250,true);state=confirmCaptions(state,[],500,true);
 assert.equal(confirmCaptions(state,['a'],600,true).get('a').count,1);
 assert.equal(confirmCaptions(confirmCaptions(new Map(),['a'],0,true),['a'],751,true).get('a').count,1);
});
