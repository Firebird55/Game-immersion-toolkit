// Read authored Odin story objects, including explicitly silent dialogue.
// Format specification: TeamSirenix/odin-serializer, BinaryEntryType and
// BinaryDataWriter. No game assets or upstream implementation are distributed.
const ROOT = 'storySections';
const ID = /^[A-Za-z0-9_][A-Za-z0-9_-]*$/;
const STORY = new Set(['GalPlayStoryNode', 'GalPlaySubStoryNode', 'GalPlayPictureStoryNode',
  'GalPlayStoryMultiSpeakerNode', 'GalPlayNoAvatarStoryNode', 'GalSubNarratorNode',
  'GalSwitchSceneNode', 'GalWhiteSwitchSceneNode', 'SwitchSceneConfig',
  'MainCityChatPlayStoryNode', 'MainCityChatInLevelPlayStoryNode', 'PlayChatPlusStoryNode']);
const CHOICE = new Set(['TransitionDisplayItem', 'MainCityChatTransitionDisplayItem']);
const emptyVoice = value => value === '' || value === null;
function sentenceSource(source) {
  const variants = [...source.matchAll(/\{[MF]#([^{}]+)\}/g)];
  if (variants.length) return variants.map(match => match[0]).join('') === source && variants.every(match => sentenceSource(match[1]));
  return /^[A-Za-z0-9_./-]+$/.test(source) && !/(?:^|\/)Breath_/i.test(source);
}

export function readOdinEntries(bytes, start, {numbers = false} = {}) {
  let p = start, entries = 0;
  const types = new Map(), references = new Map(), nodes = [];
  const need = n => { if (n < 0 || p + n > bytes.length) throw Error('Truncated ZZZ Odin story'); };
  const integer = () => { need(4); const n = bytes.readUInt32LE(p); p += 4; return n; };
  const string = () => {
    need(5); const width = bytes[p++] + 1, length = integer();
    if (width > 2 || length > 1024 * 1024) throw Error('Unsupported ZZZ Odin string');
    need(length * width); const value = bytes.toString(width === 2 ? 'utf16le' : 'latin1', p, p + length * width);
    p += length * width; return value;
  };
  const type = () => {
    need(1); const token = bytes[p++];
    if (token === 0x2e) return null;
    if (token !== 0x2f && token !== 0x30) throw Error('Unsupported ZZZ Odin type');
    const id = integer();
    if (token === 0x2f) { if (types.has(id)) throw Error('Duplicate ZZZ Odin type'); types.set(id, string()); }
    if (!types.has(id)) throw Error('Unknown ZZZ Odin type reference');
    return types.get(id);
  };
  function entry(depth = 0) {
    if (++entries > 1000000 || depth > 64) throw Error('ZZZ Odin story exceeds limits');
    need(1); const token = bytes[p++];
    const named = token <= 4 ? token % 2 === 1 : (token >= 9 && token <= 0x2d && token % 2 === 1) || token === 0x32;
    const name = named ? string() : null;
    if (token >= 1 && token <= 4) {
      const node = {name, type: type(), fields: Object.create(null)};
      if (token <= 2) {
        const id = integer();
        if (numbers) {
          if (references.has(id)) throw Error('Duplicate ZZZ Odin object identity');
          references.set(id, node);
        }
      }
      for (;;) {
        need(1); if (bytes[p] === 5) { p++; break; }
        const child = entry(depth + 1);
        if (child.name !== null) {
          if (Object.hasOwn(node.fields, child.name)) throw Error('Duplicate ZZZ Odin field');
          node.fields[child.name] = child.value;
        } else if (child.value?.arrayLength !== undefined) node.arrayLength = child.value.arrayLength;
      }
      nodes.push(node); return {name, value: node};
    }
    if (token === 6) {
      need(8); const count = bytes.readBigUInt64LE(p); p += 8;
      if (count > 1000000n) throw Error('ZZZ Odin array exceeds limits');
      for (let i = 0; i < Number(count); i++) entry(depth + 1);
      need(1); if (bytes[p++] !== 7) throw Error('Unclosed ZZZ Odin array');
      return {name, value: {arrayLength: Number(count)}};
    }
    if (token === 8) {
      const count = integer(), width = integer();
      if (![1,2,4,8,16].includes(width) || count > 1000000) throw Error('Invalid ZZZ Odin primitive array');
      need(count * width); p += count * width; return {name, value: null};
    }
    if ([0x27, 0x28, 0x32, 0x33].includes(token)) return {name, value: string()};
    if (token === 0x2d || token === 0x2e) return {name, value: null};
    if (numbers && [9,10].includes(token)) {
      const id = integer();
      if (!references.has(id)) throw Error('Unknown ZZZ Odin object reference');
      return {name, value:references.get(id)};
    }
    const widths = {9:4,10:4,11:4,12:4,13:16,14:16,15:1,16:1,17:1,18:1,
      19:2,20:2,21:2,22:2,23:4,24:4,25:4,26:4,27:8,28:8,29:8,30:8,
      31:4,32:4,33:8,34:8,35:16,36:16,37:2,38:2,41:16,42:16,43:1,44:1};
    if (!widths[token]) throw Error('Unsupported ZZZ Odin entry');
    need(widths[token]);
    // We only need presence for non-string sound-event fields; retain a
    // nonzero marker rather than treating an authored event ID as absent.
    let value = bytes.subarray(p, p + widths[token]).some(byte => byte !== 0) ? 1 : 0;
    if (numbers) {
      if ([15,16].includes(token)) value = bytes.readInt8(p);
      else if ([17,18,43,44].includes(token)) value = bytes.readUInt8(p);
      else if ([19,20].includes(token)) value = bytes.readInt16LE(p);
      else if ([21,22,37,38].includes(token)) value = bytes.readUInt16LE(p);
      else if ([23,24].includes(token)) value = bytes.readInt32LE(p);
      else if ([9,10,11,12,25,26].includes(token)) value = bytes.readUInt32LE(p);
      else if ([27,28,29,30].includes(token)) {
        const integer = token <= 28 ? bytes.readBigInt64LE(p) : bytes.readBigUInt64LE(p);
        value = integer >= BigInt(Number.MIN_SAFE_INTEGER) && integer <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(integer) : {integer:integer.toString()};
      }
      else if ([31,32].includes(token)) value = bytes.readFloatLE(p);
      else if ([33,34].includes(token)) value = bytes.readDoubleLE(p);
      if (typeof value === 'number' && !Number.isFinite(value)) throw Error('Non-finite ZZZ Odin value');
    }
    p += widths[token]; return {name, value};
  }
  const root = entry().value;
  return {root, nodes, end: p};
}

function readStory(bytes, start) {
  const {root, nodes, end} = readOdinEntries(bytes, start);
  if (root?.name !== ROOT || !root.type?.includes('MoleMole.GalGame.')) throw Error('Unsupported ZZZ story root');
  return {nodes, end};
}

export function authoredDialogueFromCab(bytes, unsupported = {}, timelineKeys) {
  const links = [];
  // Locate only the serialized named root, not arbitrary dialogue-like strings.
  for (const width of [1, 2]) {
    const name = Buffer.from(ROOT, width === 2 ? 'utf16le' : 'latin1');
    const signature = Buffer.alloc(6 + name.length); signature[0] = 1; signature[1] = width - 1;
    signature.writeUInt32LE(ROOT.length, 2); name.copy(signature, 6);
    for (let offset = bytes.indexOf(signature); offset >= 0; offset = bytes.indexOf(signature, offset)) {
      const {nodes, end} = readStory(bytes, offset); offset = end;
      for (const node of nodes) {
        const type = /^MoleMole\.GalGame\.([A-Za-z0-9_]+), Logic$/.exec(node.type ?? '')?.[1];
        const f = node.fields;
        if (['MainCityChatPlayTimelineNode', 'TimelinePair'].includes(type) &&
            typeof f.TimelineKey === 'string' && f.TimelineKey && f.TimelineKey.length <= 2048) timelineKeys?.add(f.TimelineKey);
        const dialogue = type === 'PlayChatPlusStoryNode' ? f.DialogueKey : f.dialogueKey;
        if (!STORY.has(type) && typeof dialogue === 'string' && ID.test(dialogue)) {
          const label = node.type ?? 'untyped'; unsupported[label] = (unsupported[label] ?? 0) + 1;
        }
        if (STORY.has(type) && typeof dialogue === 'string' && ID.test(dialogue)) {
          const voiceFields = ['externalVoiceKey', 'voiceKey', 'ExternalVoiceKey'].filter(key => Object.hasOwn(f, key));
          const sources = voiceFields.map(key => f[key]).filter(value => typeof value === 'string' && value);
          const source = sources.length === 1 && sentenceSource(sources[0]) ? sources[0] : '';
          const otherAudio = ['soundEvent', 'SoundEvent', 'soundKey', 'audioKey'].some(key => Boolean(f[key])) ||
            ['audioEventItems', 'AudioEventItems'].some(key => f[key]?.arrayLength > 0) ||
            Object.keys(f).some(key => /voice/i.test(key) && !voiceFields.includes(key) && Boolean(f[key]));
          links.push({text_id: dialogue, source, dialogue_kind: /Narrator|SwitchScene/.test(type) ? 'narration' : 'conversation',
            voice_status: source ? 'unavailable' : !otherAudio && voiceFields.length && voiceFields.every(key => emptyVoice(f[key])) ? 'unvoiced' : 'unknown',
            channels: type === 'MainCityChatInLevelPlayStoryNode' ? ['dialogue', 'gameplay'] : ['dialogue', 'cinematic']});
        } else if (CHOICE.has(type) && typeof f.textKey === 'string' && ID.test(f.textKey)) {
          // Choice objects contain displayed text, not a spoken-sentence binding.
          links.push({text_id: f.textKey, source: '', dialogue_kind: 'choice', voice_status: 'unknown', channels: ['dialogue', 'cinematic']});
        } else if (type === 'GalBubbleStoryNode' && typeof f.Text === 'string' && ID.test(f.Text)) {
          // Nonempty Voice can be a pool of short reactions, not this sentence.
          links.push({text_id: f.Text, source: '', dialogue_kind: 'ambient',
            voice_status: Object.hasOwn(f, 'Voice') && emptyVoice(f.Voice) ? 'unvoiced' : 'unknown', channels: ['tip', 'gameplay']});
        }
      }
    }
  }
  return links;
}

export function uniqueDialogueLinks(links) {
  const result = new Map();
  for (const link of links) {
    const key = [link.text_id, link.source, link.dialogue_kind, link.voice_status].join('\0');
    result.set(key, link);
  }
  return [...result.values()];
}
