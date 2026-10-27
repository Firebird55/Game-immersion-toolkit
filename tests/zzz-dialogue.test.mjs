import test from 'node:test';
import assert from 'node:assert/strict';
import {authoredDialogueFromCab, uniqueDialogueLinks} from '../scripts/zzz-dialogue.mjs';
import {sceneAssetPaths} from '../scripts/scene-catalog.mjs';

const uint = n => { const b = Buffer.alloc(4); b.writeUInt32LE(n); return b; };
const string = (s, width = 2) => Buffer.concat([Buffer.from([width - 1]), uint(s.length), Buffer.from(s, width === 2 ? 'utf16le' : 'latin1')]);
const text = (key, value) => Buffer.concat([Buffer.from([0x27]), string(key), string(value)]);
const nil = key => Buffer.concat([Buffer.from([0x2d]), string(key)]);
function object(type, fields, id) {
  return Buffer.concat([Buffer.from([2,0x2f]), uint(id), string('MoleMole.GalGame.' + type + ', Logic'), uint(id), ...fields, Buffer.from([5])]);
}
function cab(objects, width = 2) {
  const length = Buffer.alloc(8); length.writeBigUInt64LE(BigInt(objects.length));
  return Buffer.concat([Buffer.from('synthetic CAB prefix'), Buffer.from([1]), string('storySections', width), Buffer.from([0x2f]), uint(0),
    string('System.Collections.Generic.List`1[[MoleMole.GalGame.GalPlayableNodeBase, Logic]], mscorlib'), uint(0), Buffer.from([6]), length,
    ...objects, Buffer.from([7,5]), Buffer.from('unrelated trailing data')]);
}

test('typed story objects preserve silent lines and choices without borrowing adjacent audio', () => {
  const rows = authoredDialogueFromCab(cab([
    object('MainCityChatPlayStoryNode', [text('dialogueKey', 'Chat_Silent'), text('externalVoiceKey', '')], 1),
    object('GalPlayStoryNode', [text('dialogueKey', 'GalGame_Spoken'), text('externalVoiceKey', 'GalGame_Synthetic_01')], 2),
    object('MainCityChatTransitionDisplayItem', [text('textKey', 'Chat_Choice')], 3),
    object('UnrelatedConfiguration', [text('textKey', 'UI_Button'), text('dialogueKey', 'UI_Label')], 4),
    object('GalPlayStoryNode', [text('dialogueKey', 'GalGame_Unknown')], 5),
    object('GalPlayPictureStoryNode', [text('dialogueKey', 'Picture_Spoken'), text('externalVoiceKey', 'GalGame_Picture_01')], 6),
    object('GalPlayStoryMultiSpeakerNode', [text('dialogueKey', 'Group_Spoken'), text('externalVoiceKey', 'GalGame_Group_01')], 7),
  ]));
  assert.deepEqual(rows.map(r => [r.text_id, r.voice_status, r.dialogue_kind, r.source]), [
    ['Chat_Silent','unvoiced','conversation',''], ['GalGame_Spoken','unavailable','conversation','GalGame_Synthetic_01'],
    ['Chat_Choice','unknown','choice',''], ['GalGame_Unknown','unknown','conversation',''],
    ['Picture_Spoken','unavailable','conversation','GalGame_Picture_01'],
    ['Group_Spoken','unavailable','conversation','GalGame_Group_01'],
  ]);
  assert.equal(uniqueDialogueLinks([...rows, ...rows]).length, 6);
});

test('ambient reaction pools and breathing are not claimed as spoken sentences', () => {
  const rows = authoredDialogueFromCab(cab([
    object('GalBubbleStoryNode', [text('Text', 'Bubble_Empty'), nil('Voice')], 1),
    object('GalBubbleStoryNode', [text('Text', 'Bubble_Reaction'), text('Voice', 'Smile_01,Smile_02')], 2),
    object('GalBubbleStoryNode', [text('Text', 'Bubble_Unknown')], 3),
    object('GalPlayStoryNode', [text('dialogueKey', 'GalGame_Breath'), text('externalVoiceKey', 'Breath_Synthetic_01')], 4),
  ], 1));
  assert.deepEqual(rows.map(r => r.voice_status), ['unvoiced','unknown','unknown','unknown']);
  assert.ok(rows.every(r => !r.source));
});

test('truncated or unsupported recognized streams fail instead of returning partial dialogue', () => {
  const bytes = cab([object('GalPlayStoryNode', [text('dialogueKey', 'Synthetic'), text('externalVoiceKey', '')], 1)]);
  assert.throws(() => authoredDialogueFromCab(bytes.subarray(0, -30)), /Truncated|Unclosed/);
  const malformed = Buffer.from(bytes); const end = malformed.lastIndexOf(Buffer.from([7,5])); malformed[end] = 0x70;
  assert.throws(() => authoredDialogueFromCab(malformed), /Unclosed/);
  assert.deepEqual(authoredDialogueFromCab(Buffer.from('dialogueKey Synthetic externalVoiceKey')), []);
});

test('all supported dialogue families use authored paths, including ampersand chapter names', () => {
  const kinds = ['GalGame','Chat','ChatAudio','ChatPlus','Bubble','BubbleStory','BubbleNpc'];
  const paths = kinds.map(kind => 'Data/ScriptConfig/Perform/Data/' + kind + '/R&B/Synthetic.asset');
  assert.equal(sceneAssetPaths({rows: paths}, 'dialogue').length, 7);
  assert.deepEqual(sceneAssetPaths(['Data/ScriptConfig/Perform/Data/Chat/../Bad.asset'], 'dialogue'), []);
});

test('ChatPlus uses its authored capitalized fields and event-only audio remains unknown', () => {
  const rows = authoredDialogueFromCab(cab([
    object('PlayChatPlusStoryNode', [text('DialogueKey', 'ChatPlus_Synthetic'), text('ExternalVoiceKey', 'ChatPlus_Synthetic_01')], 1),
    object('MainCityChatPlayStoryNode', [text('dialogueKey', 'Event_Only'), text('externalVoiceKey', ''), text('soundEvent', 'Play_reaction')], 2),
    object('MainCityChatPlayStoryNode', [text('dialogueKey', 'Numeric_Event'), text('externalVoiceKey', ''),
      Buffer.concat([Buffer.from([0x17]), string('soundEvent'), uint(123)])], 3),
    object('MainCityChatPlayStoryNode', [text('dialogueKey', 'New_Voice_Field'), text('externalVoiceKey', ''), text('newVoicePath', 'new_format')], 4),
  ]));
  assert.equal(rows[0].source, 'ChatPlus_Synthetic_01');
  assert.equal(rows[0].voice_status, 'unavailable');
  assert.equal(rows[1].voice_status, 'unknown');
  assert.equal(rows[2].voice_status, 'unknown');
  assert.equal(rows[3].voice_status, 'unknown');
});

test('narration and in-level dialogue retain their types and future objects are reported', () => {
  const unsupported = {};
  const rows = authoredDialogueFromCab(cab([
    object('GalSubNarratorNode', [text('dialogueKey', 'Narration_Synthetic'), text('externalVoiceKey', '')], 1),
    object('MainCityChatInLevelPlayStoryNode', [text('dialogueKey', 'Gameplay_Synthetic'), text('externalVoiceKey', '')], 2),
    object('FutureStoryNode', [text('dialogueKey', 'Future_Synthetic'), text('externalVoiceKey', '')], 3),
  ]), unsupported);
  assert.equal(rows[0].dialogue_kind, 'narration');
  assert.equal(rows[0].voice_status, 'unvoiced');
  assert.ok(rows[1].channels.includes('gameplay'));
  assert.equal(rows.length, 2);
  assert.deepEqual(unsupported, {'MoleMole.GalGame.FutureStoryNode, Logic': 1});
});
