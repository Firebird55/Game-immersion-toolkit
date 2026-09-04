import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createVoiceActivityFollower } from '../lib/voice-activity.ts';

test('refresh restores the last recognized voice tab even before another line plays', () => {
  const tabs=[];
  const follow=createVoiceActivityFollower(tab=>tabs.push(tab));
  follow({kind:'agents',occurred_at:100});
  follow({kind:'agents',occurred_at:100});
  assert.deepEqual(tabs,['agents']);
});

test('new agent and story voices switch tabs, not duplicate polls or old snapshots', () => {
  const tabs=[];
  const follow=createVoiceActivityFollower(tab=>tabs.push(tab),100);
  follow(null);
  follow({kind:'agents',occurred_at:99});
  follow({kind:'agents',occurred_at:101});
  follow({kind:'agents',occurred_at:101});
  follow({kind:'history',occurred_at:102});
  follow({kind:'agents',occurred_at:101});
  assert.deepEqual(tabs,['agents','history']);
});

test('row updates, favorite changes, and invalid events cannot switch tabs', () => {
  const tabs=[];
  const follow=createVoiceActivityFollower(tab=>tabs.push(tab),100);
  follow({kind:'favorites',occurred_at:101});
  follow({kind:'history',occurred_at:NaN});
  follow({type:'agent_line',line:{}});
  assert.deepEqual(tabs,[]);
});
