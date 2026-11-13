import test from 'node:test';
import assert from 'node:assert/strict';
import {authoredDialogueFromCab, uniqueDialogueLinks} from '../scripts/zzz-dialogue.mjs';
import {sceneAssetPaths} from '../scripts/scene-catalog.mjs';
import {clueIntervals, comicDependencyIds, ongoingRows, recordedMessages, tableStrings, tableVoice, tipRows} from '../scripts/zzz-publisher-dialogue.mjs';

test('publisher message inventory follows authored sources and suppresses conflicting rows', () => {
  const source = 'VO_Message/Actor/Message_Performance_75';
  const rows = [['new_body_23', source, ''], ['new_body_23', '', source], ['reply', '', ''],
    ['conflict', '', ''], ['conflict', source, ''], ['variant', source, source + 'B'],
    ['unknown', 'voiced_flag', ''], ['', source, '']];
  const {messages, unresolved} = recordedMessages(rows);
  assert.deepEqual([...messages.values()], [{id:'new_body_23', source, texts:{}}]);
  assert.equal(unresolved, 3);
});

test('publisher message and ongoing tables preserve their selected sentence and protagonist', () => {
  const messages = [['x', 'VO_Message/A/Message_A_01', 'VO_Message/A/Message_A_01']];
  assert.equal(tableVoice(messages, 'x', 'message'), messages[0][1]);
  assert.throws(() => tableVoice([['x', messages[0][1], 'VO_Message/B/Message_B_01']], 'x', 'message'));
  assert.throws(() => tableVoice([['x', 'Breath_01', '']], 'x', 'message'));
  const ongoing = [['x', 'OngoingLevel_Belle_01', 'OngoingLevel_Wise_01']];
  assert.equal(tableVoice(ongoing, 'x', 'ongoing', 'wise'), ongoing[0][2]);
  assert.equal(tableVoice(ongoing, 'x', 'ongoing', 'belle'), ongoing[0][1]);
  assert.throws(() => tableVoice(ongoing, 'x', 'ongoing'));
  assert.throws(() => tableVoice([...ongoing, ['x', 'other', 'different']], 'x', 'ongoing', 'wise'));
});

test('released design tables follow row offsets and reject truncated or nonterminated strings', () => {
  const bytes = Buffer.alloc(59);
  bytes.writeUInt32LE(12); // root, its vtable, and the row vector
  bytes.writeUInt16LE(6, 4); bytes.writeUInt16LE(8, 6); bytes.writeUInt16LE(4, 8);
  bytes.writeInt32LE(8, 12); bytes.writeUInt32LE(4, 16);
  bytes.writeUInt32LE(1, 20); bytes.writeUInt32LE(16, 24);
  bytes.writeUInt16LE(8, 32); bytes.writeUInt16LE(8, 34); bytes.writeUInt16LE(4, 36);
  bytes.writeInt32LE(8, 40); bytes.writeUInt32LE(8, 44);
  bytes.writeUInt32LE(2, 52); bytes.write('ok', 56);
  assert.deepEqual([...tableStrings(bytes, [0, 1])], [['ok', '']]);
  assert.throws(() => [...tableStrings(bytes.subarray(0, 58), [0])], /string/);
  bytes[58] = 4;
  assert.throws(() => [...tableStrings(bytes, [0])], /string/);
  bytes.writeUInt32LE(0, 24);
  assert.throws(() => [...tableStrings(bytes, [0])], /reference/);
});

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

test('publisher clues retain per-dub millisecond intervals and omit conflicting clocks', () => {
  const rows = [
    ['VO_Clue/X/Clue_X', 'English(EN)', 'Clue_Line', '00:00:01:33', '00:00:03:1'],
    ['VO_Clue/X/Clue_X', 'Japanese(JP)', 'Clue_Line', '00:01:02:0', '00:01:03:0'],
  ];
  assert.deepEqual(clueIntervals(rows, 'English(EN)'), [{text_id:'Clue_Line', source:'VO_Clue/X/Clue_X',
    start_ms:1033, end_ms:3001}]);
  assert.equal(clueIntervals(rows, 'Japanese(JP)')[0].start_ms, 62000);
  assert.deepEqual(clueIntervals([...rows, [...rows[0].slice(0, 4), '00:00:03:2']], 'English(EN)'), []);
  assert.throws(() => clueIntervals([[...rows[0].slice(0, 4), '00:00:00:0']], 'English(EN)'), /interval/);
});

test('ongoing rows retain the conditional missing performance and the authored default', () => {
  const result = ongoingRows([['Example', '', 'Wise'], ['Other','Belle','Wise'], ['One','Shared','']]);
  assert.deepEqual(result.map(row => [row.text_id, row.gender, row.source, row.voice_status]), [
    ['Example','F','','unknown'], ['Example','M','Wise','unavailable'],
    ['Other','F','Belle','unavailable'], ['Other','M','Wise','unavailable'], ['One',undefined,'Shared','unavailable']]);
});

test('comic manifest selects only direct released bundle IDs including 64-bit values', () => {
  const u32 = value => { const b = Buffer.alloc(4); b.writeUInt32LE(value); return b; };
  const string = name => {
    const value = Buffer.from(name);
    return Buffer.concat([u32(value.length), value, Buffer.alloc((4 - value.length % 4) % 4)]);
  };
  const manifest = member => Buffer.concat([
    string('930.bundle'), u32(1), Buffer.alloc(12), u32(1), string('930'), Buffer.alloc(20),
    Buffer.alloc(24), string('930.bundle'), u32(2), string('19.bundle'), string(member), Buffer.alloc(16),
  ]);
  assert.deepEqual(comicDependencyIds(manifest('16232649768801158562.bundle')), [19n, 16232649768801158562n]);
  assert.throws(() => comicDependencyIds(manifest('other/32.bundle')), /dependency/);
  assert.throws(() => comicDependencyIds(manifest('32.bundle').subarray(0, 60)), /Truncated/);
});

test('released tips distinguish reactions, events, secondary references and authored silence', () => {
  const sample = (id, source='', alt='', reaction='', events=[], ref='') => [id, source, alt, reaction, events, ref, '', '', ''];
  const rows = tipRows([sample('silent'), sample('reaction','','','Accompany_Astra_Smile'),
    sample('event','','','',['Play_UI_Accompany_Buy']), sample('next','','','',[],'30070020'),
    sample('other','VO_Future/clip'), sample('voice','VO_Tips/Actor/Tips_23'),
    sample('story','GalGame_Example_Actor_02')]);
  assert.deepEqual(rows.map(row => row.voice_status), ['unvoiced','unknown','unknown','unknown','unavailable','unavailable','unavailable']);
  assert.deepEqual(rows.filter(row => row.source).map(row => row.text_id), ['voice','story']);
});

test('released tip recordings use explicit matching protagonist suffixes', () => {
  const row = (id, first, second) => [id, first, second, '', [], '', '', '', ''];
  const rows = tipRows([
    row('paired', 'Level_Actor_02_M', 'Level_Actor_02_F'),
    row('numbered', 'Level_Actor_02', 'Level_Actor_03'),
    row('other', 'Level_Actor_02_F', 'Level_Actor_03_M'),
    row('unsafe', '../Other_M', '../Other_F'),
  ]);
  assert.deepEqual(rows.map(r => [r.text_id, r.gender, r.source]), [
    ['paired', 'M', 'Level_Actor_02_M'], ['paired', 'F', 'Level_Actor_02_F'],
    ['numbered', undefined, ''], ['other', undefined, ''], ['unsafe', undefined, ''],
  ]);
});

test('released string vector respects entry offsets, defaults and additional schema fields', () => {
  const bytes = Buffer.alloc(80);
  bytes.writeUInt32LE(12); bytes.writeUInt16LE(6,4); bytes.writeUInt16LE(8,6); bytes.writeUInt16LE(4,8);
  bytes.writeInt32LE(8,12); bytes.writeUInt32LE(4,16); bytes.writeUInt32LE(1,20); bytes.writeUInt32LE(16,24);
  bytes.writeUInt16LE(8,32); bytes.writeUInt16LE(8,34); bytes.writeUInt16LE(4,36);
  bytes.writeInt32LE(8,40); bytes.writeUInt32LE(8,44); bytes.writeUInt32LE(1,52); bytes.writeUInt32LE(8,56);
  bytes.writeUInt32LE(2,64); bytes.write('ok',68);
  assert.deepEqual([...tableStrings(bytes,[0,1],{vectors:[0,1], maxColumns:2})], [[['ok'],[]]]);
  assert.throws(() => [...tableStrings(bytes,[0],{vectors:[0],maxColumns:1})], /schema/);
  bytes.writeUInt32LE(400,52);
  assert.throws(() => [...tableStrings(bytes,[0],{vectors:[0]})], /vector/);
});
