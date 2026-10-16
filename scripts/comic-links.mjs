// Read the explicit GUID -> external-voice dictionary in comic CAB assets.
// Binary layout references (no upstream code is bundled here):
// https://github.com/TeamSirenix/odin-serializer/blob/master/OdinSerializer/Core/DataReaderWriters/Binary/BinaryDataWriter.cs
// https://github.com/TeamSirenix/odin-serializer/blob/master/OdinSerializer/Core/Formatters/DictionaryFormatter.cs
const FIELD = 'guidToData';
const TYPE = 'System.Collections.Generic.Dictionary`2[[System.String, mscorlib],[System.String, mscorlib]], mscorlib';
const VOICE = /^VO_Comic\/(?:[A-Za-z0-9_.-]+\/)*VO_[A-Za-z0-9]+\/Comic_[A-Za-z0-9_-]+$/i;
function voiceSource(value) {
  if (VOICE.test(value)) return true;
  const variants=[...value.matchAll(/\{([MF])#([^{}]+)\}/g)];
  return variants.length===2 && new Set(variants.map(match=>match[1])).size===2 &&
    variants.map(match=>match[0]).join('')===value && variants.every(match=>VOICE.test(match[2]));
}

function stringAt(bytes, offset) {
  if (offset + 5 > bytes.length || bytes[offset] > 1) throw new Error('Unsupported Odin string');
  const width = bytes[offset] + 1;
  const length = bytes.readUInt32LE(offset + 1);
  const end = offset + 5 + length * width;
  if (length > 4096 || end > bytes.length) throw new Error('Invalid Odin string bounds');
  return { value: bytes.toString(width === 2 ? 'utf16le' : 'latin1', offset + 5, end), end };
}

function namedString(bytes, offset, name) {
  if (bytes[offset] !== 0x27) throw new Error('Expected named string');
  const field = stringAt(bytes, offset + 1);
  if (field.value !== name) throw new Error('Unexpected dictionary field');
  return stringAt(bytes, field.end);
}

export function comicVoicePairs(bytes) {
  const pairs = [];
  for (let start = 0; start < bytes.length; start++) {
    if (bytes[start] !== 0x01) continue;
    try {
      const field = stringAt(bytes, start + 1);
      if (field.value !== FIELD || bytes[field.end] !== 0x2f) continue;
      const type = stringAt(bytes, field.end + 5); // type-name token, int32 type ID
      if (type.value !== TYPE) continue;
      // The comparer precedes the dictionary's array. Accept only a complete
      // string/string entry array with its own node and array terminators.
      for (let cursor = type.end + 4; cursor < Math.min(type.end + 2048, bytes.length - 9); cursor++) {
        if (bytes[cursor] !== 0x06) continue;
        const count = bytes.readBigUInt64LE(cursor + 1);
        if (count === 0n || count > 50000n || count * 20n > BigInt(bytes.length - cursor)) continue;
        let offset = cursor + 9;
        const dictionary = [];
        try {
          for (let index = 0; index < Number(count); index++) {
            if (bytes[offset] !== 0x04 || bytes[offset + 1] !== 0x2e) throw new Error('Expected dictionary entry node');
            const key = namedString(bytes, offset + 2, '$k');
            const value = namedString(bytes, key.end, '$v');
            if (bytes[value.end] !== 0x05) throw new Error('Unclosed dictionary entry');
            if (!/^[a-f0-9]{32}$/i.test(key.value)) throw new Error('Invalid comic GUID');
            if (voiceSource(value.value)) dictionary.push({ text_id: `Comic_${key.value}`, source: value.value });
            offset = value.end + 1;
          }
          if (bytes[offset] !== 0x07 || bytes[offset + 1] !== 0x05) throw new Error('Unclosed dictionary array');
          pairs.push(...dictionary);
          start = offset + 1;
          break;
        } catch { /* incompatible or incomplete array: never use partial pairs */ }
        break; // Never substitute a later array for a malformed dictionary.
      }
    } catch { /* unrelated CAB bytes */ }
  }
  return pairs;
}

export function uniqueComicLinks(pairs) {
  const byText = new Map();
  const bySource = new Map();
  for (const { text_id, source } of pairs) {
    const sources = byText.get(text_id) ?? new Map();
    sources.set(source.toLowerCase(), source);
    byText.set(text_id, sources);
    const texts = bySource.get(source.toLowerCase()) ?? new Set();
    texts.add(text_id);
    bySource.set(source.toLowerCase(), texts);
  }
  return [...byText].filter(([, sources]) => sources.size === 1).flatMap(([text_id, sources]) => {
    const [key, source] = [...sources][0];
    return bySource.get(key).size === 1 ? [{ text_id, source }] : [];
  });
}
