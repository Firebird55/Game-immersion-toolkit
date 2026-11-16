import {readFileSync, writeFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {resourceCatalogBytes, sceneAssetPaths, sceneBundleRangesFromCatalog, sceneCatalog, unityObjectsOfType} from './scene-catalog.mjs';
import {comicVoicePairs, uniqueComicLinks} from './comic-links.mjs';
import {authoredDialogueFromCab, uniqueDialogueLinks} from './zzz-dialogue.mjs';
import {AUTO_META_CONFIG_ASSET, autoPresentationConfig, typedPresentationObjects, presentationDictionary, timelineOwners} from './zzz-presentation-config.mjs';

const utf8 = new TextDecoder('utf-8', {fatal: true});
const tags = {'zh-Hans':'', 'zh-Hant':'_CHT', en:'_EN', ja:'_JA', ko:'_KO', de:'_DE',
  fr:'_FR', 'es-ES':'_ES', 'pt-BR':'_PT', th:'_TH', ru:'_RU', vi:'_VI', id:'_ID'};

// Design tables have a root object with a vector of row objects in field zero.
export function* tableStrings(data, columns, {vectors = [], integers = [], maxColumns} = {}) {
  function field(table, index) {
    const vtable = table - data.readInt32LE(table);
    const bytes = data.readUInt16LE(vtable), width = data.readUInt16LE(vtable + 2);
    if (bytes < 4 || bytes % 2 || vtable + bytes > data.length || table + width > data.length) {
      throw Error('Invalid ZZZ table bounds');
    }
    const at = 4 + 2 * index;
    const offset = at < bytes ? data.readUInt16LE(vtable + at) : 0;
    if (offset && (offset < 4 || offset + 4 > width)) throw Error('Invalid ZZZ row field');
    return offset ? table + offset : null;
  }
  function indirect(at) {
    const offset = data.readUInt32LE(at);
    if (!offset || at + offset + 4 > data.length) throw Error('Invalid ZZZ table reference');
    return at + offset;
  }
  function string(at) {
    const start = indirect(at), end = start + 4 + data.readUInt32LE(start);
    if (end >= data.length || data[end] !== 0) throw Error('Invalid ZZZ table string');
    return utf8.decode(data.subarray(start + 4, end));
  }
  const first = field(indirect(0), 0);
  if (first === null) throw Error('Missing ZZZ row vector');
  const vector = indirect(first), count = data.readUInt32LE(vector);
  if (count > 2000000 || vector + 4 + 4 * count > data.length) throw Error('Invalid ZZZ row count');
  for (let i = 0; i < count; i++) {
    const row = indirect(vector + 4 + 4 * i);
    if (maxColumns && data.readUInt16LE(row - data.readInt32LE(row)) > 4 + 2 * maxColumns) {
      throw Error('Unsupported released ZZZ row schema');
    }
    yield columns.map(index => {
      const at = field(row, index);
      if (integers.includes(index)) return at === null ? 0 : data.readUInt32LE(at);
      if (!vectors.includes(index)) return at === null ? '' : string(at);
      if (at === null) return [];
      const vector = indirect(at), count = data.readUInt32LE(vector);
      if (count > 65536 || vector + 4 + count * 4 > data.length) throw Error('Invalid ZZZ string vector');
      return Array.from({length:count}, (_, i) => string(vector + 4 + i * 4));
    });
  }
}

export function performPresentationInventory(rows) {
  // The original Perform table also configures movies and timeline keys. They
  // must not disappear from coverage merely because sceneAssetPaths only
  // acquires conversation/comic assets. A configured row is not proof of a
  // reachable current scene, a subtitle, a player branch, or an audio binding.
  const ids = new Set(), typeCounts = new Map();
  const families = {movie: {perform_type:5, ids:[], source_keys:new Set()},
    timeline: {perform_type:6, ids:[], source_keys:new Set()}};
  for (const row of rows) {
    if (!Array.isArray(row) || row.length !== 4) throw Error('Invalid released ZZZ Perform row');
    const [id, type, first, alternate] = row;
    if (!Number.isInteger(id) || id <= 0 || id > 0xffffffff || ids.has(id)
        || !Number.isInteger(type) || type < 0 || type > 0xffffffff
        || [first, alternate].some(value => typeof value !== 'string' || value.length > 1024)) {
      throw Error('Invalid or duplicate released ZZZ Perform identity');
    }
    ids.add(id);
    typeCounts.set(type, (typeCounts.get(type) || 0) + 1);
    for (const family of Object.values(families)) if (type === family.perform_type) {
      family.ids.push(id);
      for (const key of [first, alternate]) if (key) family.source_keys.add(key);
    }
  }
  return {source:'original PerformTemplateTb', configured_rows:ids.size,
    type_counts:Object.fromEntries([...typeCounts].sort(([a],[b]) => a-b)),
    unacquired_presentations:Object.fromEntries(Object.entries(families).map(([kind, family]) =>
      [kind, {perform_type:family.perform_type, configured_rows:family.ids.length,
        distinct_source_keys:family.source_keys.size, perform_ids:family.ids.sort((a,b) => a-b),
        acquisition:'not-implemented', current_use:'unclassified'}]))};
}

function designTables(files, work, wanted, unpack) {
  const tables = new Map();
  for (const file of files) {
    const data = readFileSync(join(work, file));
    if (data.toString('ascii', 0, 3) === 'BBL') continue;
    if (data[0] === 31 && data[1] === 139) {
      // Older design manifests include their gzip resource index alongside
      // the TextAsset bundles. Verify the catalog format before skipping it.
      sceneCatalog(data);
      continue;
    }
    for (let pos = 0; pos < data.length;) {
      const bundle = unpack(data, pos);
      if (bundle.end <= pos || bundle.end > data.length) throw Error('Invalid ZZZ design bundle');
      pos = bundle.end;
      for (const cab of bundle.files) for (const object of unityObjectsOfType(cab, 49)) {
        const length = object.readUInt32LE(0);
        if (4 + length > object.length) throw Error('Invalid Unity TextAsset name');
        const name = object.toString('utf8', 4, 4 + length);
        if (!wanted.has(name)) continue;
        const start = Math.ceil((4 + length) / 4) * 4 + 4;
        const end = start + object.readUInt32LE(start - 4);
        if (end > object.length || tables.has(name)) throw Error('Incomplete or ambiguous ZZZ design table');
        tables.set(name, object.subarray(start, end));
      }
    }
  }
  return tables;
}

export function tableVoice(rows, id, kind, protagonist) {
  const candidates = new Set();
  for (const [textId, first, second] of rows) {
    if (textId !== id) continue;
    if (kind === 'message') {
      if (first && second && first !== second) throw Error('Conflicting ZZZ message voice sources');
      const source = first || second;
      if (!/^VO_Message\/[A-Za-z0-9_-]+\/Message_[A-Za-z0-9_-]+$/i.test(source)) throw Error('Message has no verified sentence source');
      candidates.add(source);
    } else if (kind === 'ongoing') {
      // In the authored ongoing table the first column is the default (Belle)
      // performance. An explicit second column overrides it for Wise.
      if (second && first !== second && !protagonist) throw Error('Missing or unselected ZZZ ongoing performance');
      const source = protagonist === 'wise' && second ? second : first;
      if (!source) throw Error('Missing or unselected ZZZ ongoing performance');
      candidates.add(source);
    } else {
      throw Error('Unknown ZZZ table voice presentation');
    }
  }
  if (candidates.size !== 1) throw Error('No unique authored sentence source in the requested ZZZ table');
  return [...candidates][0];
}

export function recordedMessages(rows) {
  const sources = new Map(), unresolved = new Set();
  for (const [id, first, second] of rows) {
    if (!id || !/^[A-Za-z0-9_-]{1,240}$/.test(id)) continue;
    const source = first || second;
    if ((first && second && first !== second) ||
        (source && !/^VO_Message\/[A-Za-z0-9_-]+\/Message_[A-Za-z0-9_-]+$/i.test(source)) ||
        (sources.has(id) && sources.get(id) !== source)) unresolved.add(id);
    sources.set(id, source);
  }
  const messages = new Map([...sources].filter(([id, source]) => source && !unresolved.has(id))
    .map(([id, source]) => [id, {id, source, texts:{}}]));
  return {messages, unresolved:unresolved.size};
}

function plan(work, input, reader) {
  const key = name => String(reader.xxHash64(name.toLowerCase()));
  const names = Object.values(tags).flatMap(tag => ['TemplateTb', 'OverwriteTemplateTb'].map(s => key('TextMap' + tag + s)));
  const kind = input.kind || 'scene';
  const tableName = {scene:'PerformTemplateTb', message:'MessageConfigTemplateTb', ongoing:'OngoingTipsConfigTemplateTb'}[kind];
  if (!tableName) throw Error('Unknown released ZZZ dialogue presentation');
  const bindingTable = key(tableName);
  const tables = designTables(input.design, work, new Set([...names, bindingTable]), reader.unpackMhyFile);
  if (!tables.has(bindingTable)) throw Error('The released ZZZ binding table is missing');
  const texts = {};
  for (const [locale, tag] of Object.entries(tags)) {
    for (const suffix of ['TemplateTb', 'OverwriteTemplateTb']) {
      const table = tables.get(key('TextMap' + tag + suffix));
      if (!table && suffix === 'TemplateTb') throw Error('Released ZZZ locale table is missing');
      if (!table) continue;
      let found = false;
      for (const [id, value] of tableStrings(table, [0, 1])) if (id === input.id) {
        if (found) throw Error('Ambiguous subtitle in a ZZZ locale table');
        found = true;
        texts[locale] = value;
      }
    }
  }
  if (!Object.values(texts).some(text => text.trim())) throw Error('Subtitle is absent from the released tables');
  if (kind !== 'scene') {
    const columns = kind === 'message' ? [7, 3, 5] : [6, 7, 8];
    const source = tableVoice(tableStrings(tables.get(bindingTable), columns), input.id, kind, input.protagonist);
    return {texts, source};
  }
  const paths = sceneAssetPaths([...tableStrings(tables.get(bindingTable), [2, 3])], 'dialogue');
  return {texts, ...releasedRanges(work, input.catalogs, paths, reader)};
}

function releasedRanges(work, catalogs, paths, reader, category = 'dialogue') {
  const wanted = new Set(paths.map(path => reader.xxHash64(path)));
  const result = catalogRanges(work, catalogs, wanted, reader, category === 'dialogue');
  if (category === 'dialogue' && !result.ranges.length) throw Error('No released dialogue scene ranges');
  const unmatched = {};
  for (const path of paths) if (!result.matched.has(reader.xxHash64(path))) {
    const presentation = category === 'comic' ? 'comic' : path.split('/perform/data/')[1].split('/')[0];
    unmatched[presentation] = (unmatched[presentation] || 0) + 1;
  }
  return {ranges:result.ranges, scenePaths:{total:paths.length, matched:result.matched.size, unmatched}};
}

function catalogRanges(work, catalogs, wanted, reader, includeDependencies) {
  const matched = new Set();
  const ranges = new Map();
  for (const candidate of catalogs) {
    const catalog = resourceCatalogBytes(readFileSync(join(work, candidate)), reader.unpackMhyFile);
    if (!catalog) continue;
    const result = sceneBundleRangesFromCatalog(catalog, wanted, true, includeDependencies);
    for (const hash of result.matchedHashes) matched.add(hash);
    for (const r of result.ranges) {
      const id = r.block + '/' + r.offset;
      if (ranges.has(id) && ranges.get(id).size !== r.size) throw Error('Conflicting released scene range');
      ranges.set(id, r);
    }
  }
  return {ranges:[...ranges.values()], matched};
}

function* sceneCabs(work, blocks, reader) {
  for (const name of blocks) {
    const data = readFileSync(join(work, name));
    for (let pos = 0; pos < data.length;) {
      const size = data.readUInt32LE(pos);
      pos += 4;
      if (!size || pos + size > data.length) throw Error('Incomplete staged ZZZ scene');
      const bundle = reader.unpackMhyFile(data.subarray(pos, pos + size), 0);
      if (bundle.end !== size) throw Error('Invalid ZZZ scene boundary');
      pos += size;
      yield* bundle.files;
    }
  }
}

function bindings(work, input, reader) {
  const sources = new Set();
  for (const cab of sceneCabs(work, input.blocks, reader)) {
    for (const row of authoredDialogueFromCab(cab, {})) if (row.text_id === input.id) sources.add(row.source);
  }
  if (sources.size !== 1 || ![...sources][0]) throw Error('No unique authored sentence recording for the requested subtitle');
  return {source: [...sources][0]};
}

function checkNames(names, pattern) {
  if (!Array.isArray(names) || !names.length || names.some(name => typeof name !== 'string' || !pattern.test(name))) {
    throw Error('Invalid released ZZZ inputs');
  }
}

function scenePlan(work, input, reader) {
  checkNames(input.design, /^design-\d+\.blk$/);
  checkNames(input.catalogs, /^catalog-\d+\.blk$/);
  const key = String(reader.xxHash64('performtemplatetb'));
  const tables = designTables(input.design, work, new Set([key]), reader.unpackMhyFile);
  if (!tables.has(key)) throw Error('Released ZZZ Perform table is missing');
  const rows = [...tableStrings(tables.get(key), [0, 1, 2, 3], {integers:[0, 1]})];
  const scenes = rows.map(row => row.slice(2));
  const dialogue = releasedRanges(work, input.catalogs, sceneAssetPaths(scenes, 'dialogue'), reader);
  const comics = releasedRanges(work, input.catalogs, sceneAssetPaths(scenes, 'comic'), reader, 'comic');
  const voiceDirectory = catalogRanges(work, input.catalogs,
    new Set([reader.xxHash64('assets/napresources/data/audio/voicedata.json')]), reader, false);
  return {...dialogue, comics, voiceDirectory:voiceDirectory.ranges,
    performPresentations:performPresentationInventory(rows),
    timelineKeys:[...new Set(rows.filter(row => row[1] === 6).flatMap(row => row.slice(2)).filter(Boolean))],
    presentationConfigRoots:catalogRanges(work, input.catalogs, new Set([AUTO_META_CONFIG_ASSET]), reader, false).ranges};
}

function presentationConfigPlan(work, input, reader) {
  checkNames(input.catalogs, /^catalog-\d+\.blk$/);
  checkNames(input.roots, /^\d+\.blk\.presentation-roots$/);
  const roots = [...sceneCabs(work, input.roots, reader)].flatMap(cab => typedPresentationObjects(cab, new Set(['NewAutoConfigMetaConfig'])));
  if (roots.length !== 1) throw Error('Missing or ambiguous original ZZZ presentation root');
  const fields = autoPresentationConfig(roots[0].bytes), wanted = new Set();
  for (const name of ['timelineDataPathes', 'languageVideoDataPaths']) for (const path of fields[name]) {
    if (!/^[1-9]\d{0,19}$/.test(path.hash) || BigInt(path.hash) > 0xffffffffffffffffn) throw Error('Invalid ZZZ presentation resource identity');
    wanted.add(BigInt(path.hash));
  }
  const result = catalogRanges(work, input.catalogs, wanted, reader, false);
  if (result.matched.size !== wanted.size) throw Error('Original ZZZ presentation config is absent from the selected publisher');
  return {ranges:result.ranges, timelineConfigs:fields.timelineDataPathes.length,
    videoConfigs:fields.languageVideoDataPaths.length,
    extraConfigs:fields.timelineDataExtraPathes.length};
}

function presentationOwners(work, input, reader) {
  checkNames(input.catalogs, /^catalog-\d+\.blk$/);
  checkNames(input.blocks, /^\d+\.blk\.presentation-configs$/);
  if (!Array.isArray(input.keys) || input.keys.length > 100000 || input.keys.some(key => typeof key !== 'string' || !key || key.length > 2048)) throw Error('Invalid ZZZ configured timeline selection');
  let timelineConfigs = 0, videoConfigs = 0; const entries = [], videos = [];
  for (const cab of sceneCabs(work, input.blocks, reader)) for (const object of typedPresentationObjects(cab, new Set(['ConfigTimelineData', 'ConfigLanguageVideo']))) {
    const timeline = object.type === 'ConfigTimelineData';
    const result = presentationDictionary(object.bytes, timeline ? 'timeline' : 'video');
    if (timeline) { timelineConfigs++; entries.push(...result.entries); }
    else { videoConfigs++; videos.push(...result.entries); }
  }
  if (timelineConfigs !== input.timelineConfigs || videoConfigs !== input.videoConfigs) throw Error('Incomplete original ZZZ presentation configurations');
  const result = timelineOwners(entries, input.keys);
  const all = timelineOwners(entries, [...new Set(entries.map(row => row.key).filter(Boolean))]);
  const paths = new Set(all.owners.flatMap(owner => Object.values(owner.paths)).filter(Boolean));
  const catalog = catalogRanges(work, input.catalogs, new Set([...paths].map(path => reader.xxHash64(path.toLowerCase()))), reader, false);
  return {owners:all.owners, videoKeys:videos.map(row => row.key), coverage:{...result.coverage,
    timeline_configs:timelineConfigs, video_configs:videoConfigs, configured_timeline_records:entries.length,
    all_original_owners:all.owners.length,
    all_ambiguous_equal_priority_keys:all.coverage.ambiguous_equal_priority_keys,
    configured_video_keys:videos.length, authored_source_paths:paths.size,
    catalogue_matched_source_paths:catalog.matched.size,
    subtitle_audio_acquisition:'not-implemented'}};
}

// Unity v21 AssetBundle (class 142): preloads, container and main asset, runtime
// compatibility, bundle name, and direct dependency bundle names. These names
// are actual catalogue asset IDs. Transitive textures and meshes are unnecessary.
export function comicDependencyIds(object) {
  let pos = 0;
  const take = length => {
    if (length > object.length - pos) throw Error('Truncated ZZZ comic bundle manifest');
    const start = pos;
    pos += length;
    return start;
  };
  const integer = () => object.readUInt32LE(take(4));
  const name = () => {
    const length = integer();
    if (length > 128) throw Error('Invalid ZZZ comic bundle name');
    const start = take(length);
    take((4 - length % 4) % 4);
    return object.toString('ascii', start, start + length);
  };
  const bundle = name();
  if (!/^\d{1,20}\.bundle$/.test(bundle)) throw Error('Unsupported ZZZ comic bundle identity');
  take(integer() * 12);
  const containers = integer();
  for (let i = 0; i < containers; i++) {
    name();
    take(20);
  }
  take(24);
  if (name() !== bundle) throw Error('Inconsistent ZZZ comic bundle names');
  const count = integer();
  const ids = [];
  for (let i = 0; i < count; i++) {
    const member = /^(\d{1,20})\.bundle$/.exec(name());
    if (!member) throw Error('Unsupported ZZZ comic dependency');
    ids.push(BigInt(member[1]));
  }
  return ids;
}

function comicPlan(work, input, reader) {
  checkNames(input.catalogs, /^catalog-\d+\.blk$/);
  checkNames(input.roots, /^\d+\.blk\.comic-roots$/);
  const ids = new Set();
  let manifests = 0;
  for (const cab of sceneCabs(work, input.roots, reader)) {
    for (const object of unityObjectsOfType(cab, 142)) {
      for (const id of comicDependencyIds(object)) ids.add(id);
      manifests++;
    }
  }
  if (manifests !== input.rootCount) throw Error('Incomplete ZZZ comic bundle manifests');
  const result = catalogRanges(work, input.catalogs, ids, reader, false);
  if (result.matched.size !== ids.size) throw Error('Unresolved ZZZ comic dependency');
  return {ranges: result.ranges};
}

// VoiceData is a Unity TextAsset containing JSON with line comments and trailing
// commas. The numeric voidBlocks array carries its associations without comments.
export function voiceDirectoryObject(object) {
  const length = object.readUInt32LE(0);
  if (length !== 9 || object.toString('ascii', 4, 4 + length) !== 'VoiceData') return null;
  const sizeAt = Math.ceil((4 + length) / 4) * 4, start = sizeAt + 4;
  const size = object.readUInt32LE(sizeAt);
  if (size > 32 * 1024 * 1024 || start + size > object.length) throw Error('Invalid ZZZ voice directory bounds');
  const document = utf8.decode(object.subarray(start, start + size)).replace(
    /"(?:\\.|[^"\\])*"|\/\/[^\r\n]*|,\s*(?=[}\]])/g, token => token.startsWith('"') ? token : '');
  const {allPrefixes, voidBlocks} = JSON.parse(document);
  if (!Array.isArray(allPrefixes) || !allPrefixes.length || allPrefixes.length > 65536 ||
      !Array.isArray(voidBlocks) || !voidBlocks.length || voidBlocks.length > 2000000) throw Error('Invalid ZZZ voice directory format');
  return {prefixes:allPrefixes, blocks:voidBlocks};
}

export function ongoingRows(rows) {
  const links = [];
  for (const [text_id, first, second] of rows) {
    if (!/^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(text_id)) continue;
    const channels = /ongoinglevel/i.test(text_id) ? ['gameplay'] : ['tip'];
    const link = {text_id, dialogue_kind:'ambient', channels};
    const take = (source, gender) => {
      const reaction = /(?:^|[_/])(?:cinema)?breath\d*(?:_|$)/i.test(source);
      return {...link, ...(gender ? {gender} : {}), source:reaction ? '' : source,
        voice_status:source && !reaction ? 'unavailable' : 'unknown'};
    };
    if (second && first !== second) {
      links.push(take(first, 'F'));
      links.push(take(second, 'M'));
    } else {
      // Empty sentence fields leave separate runtime sound/event fields unresolved.
      links.push(take(first));
    }
  }
  return links;
}

export function clueIntervals(rows, namespace) {
  function milliseconds(text) {
    const match = /^(\d{2}):([0-5]\d):([0-5]\d):(\d{1,3})$/.exec(text);
    if (!match) throw Error('Invalid released ZZZ clue timestamp');
    const [hours, minutes, seconds, ms] = match.slice(1).map(Number);
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + ms;
  }
  const intervals = new Map(), ambiguous = new Set();
  for (const [source, dub, text_id, start, end] of rows) {
    if (dub !== namespace || !/^Clue_[A-Za-z0-9_-]+$/.test(text_id) ||
        !/^VO_Clue\/(?:[A-Za-z0-9_-]+\/)+Clue_[A-Za-z0-9_-]+$/.test(source)) continue;
    const start_ms = milliseconds(start), end_ms = milliseconds(end);
    if (start_ms >= end_ms) throw Error('Invalid released ZZZ clue interval');
    const previous = intervals.get(text_id);
    if (previous && (previous.source !== source || previous.start_ms !== start_ms || previous.end_ms !== end_ms)) {
      ambiguous.add(text_id);
    }
    intervals.set(text_id, {text_id, source, start_ms, end_ms});
  }
  for (const id of ambiguous) intervals.delete(id);
  return [...intervals.values()];
}

export function tipRows(rows) {
  const tips = [];
  for (const [text_id, primary, alternate, reaction, events, ...references] of rows) {
    if (!/^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(text_id)) continue;
    const supported = /^(?:VO_(?:Tips|Chessboard|Level|Monthlycard)\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+|(?:Accompany|GalGame|Level|Chessboard|Tips|OngoingMainCity)_[A-Za-z0-9_-]+)$/i;
    const link = {text_id, channels:['tip', 'gameplay'], dialogue_kind:'gameplay_tip'};
    if (primary && alternate && primary !== alternate && supported.test(primary) &&
        primary.slice(0, -1) === alternate.slice(0, -1) && /_[FM]$/.test(primary) && /_[FM]$/.test(alternate)) {
      for (const source of [primary, alternate]) {
        tips.push({...link, source, gender:source.at(-1), voice_status:'unavailable'});
      }
    } else {
      const source = (!alternate || primary === alternate) && supported.test(primary) ? primary : '';
      tips.push({...link, source, voice_status:primary || alternate ? 'unavailable' :
        reaction || events.length || references.some(Boolean) ? 'unknown' : 'unvoiced'});
    }
  }
  return tips;
}

function catalogue(work, input, reader) {
  checkNames(input.design, /^design-\d+\.blk$/);
  checkNames(input.blocks, /^\d+\.blk\.scenes$/);
  if (input.comics.length) checkNames(input.comics, /^\d+\.blk\.comics$/);
  const directoryBlocks = input.voiceDirectory || [];
  if (directoryBlocks.length) checkNames(directoryBlocks, /^\d+\.blk\.voice-directory$/);
  let directory = null;
  for (const cab of sceneCabs(work, directoryBlocks, reader)) {
    for (const object of unityObjectsOfType(cab, 49)) {
      const match = voiceDirectoryObject(object);
      if (!match) continue;
      if (directory) throw Error('Ambiguous ZZZ voice directory');
      directory = match;
    }
  }
  if (directoryBlocks.length && !directory) throw Error('Released ZZZ voice directory is missing');
  writeFileSync(join(work, 'voice-directory.json'), JSON.stringify(directory), {flag:'wx'});
  const locales = new Set(input.locales);
  if (!locales.size || [...locales].some(locale => !Object.hasOwn(tags, locale))) throw Error('Invalid ZZZ locales');
  const key = name => String(reader.xxHash64(name.toLowerCase()));
  const suffixes = ['TemplateTb', 'OverwriteTemplateTb'];
  const bindings = ['MessageConfigTemplateTb', 'OngoingTipsConfigTemplateTb', 'SubtitleConfigTemplateTb', 'TipsConfigTemplateTb'];
  const wanted = new Set(bindings.map(key));
  for (const locale of locales) for (const suffix of suffixes) wanted.add(key('TextMap' + tags[locale] + suffix));
  const tables = designTables(input.design, work, wanted, reader.unpackMhyFile);
  if (bindings.some(name => !tables.has(key(name)))) throw Error('Released ZZZ binding table is missing');
  const links = [];
  const unsupported = {}, timelineKeys = new Set();
  for (const cab of sceneCabs(work, input.blocks, reader)) {
    for (const link of authoredDialogueFromCab(cab, unsupported, timelineKeys)) links.push(link);
  }
  if (!links.length) throw Error('Released ZZZ scene selection contained no authored dialogue');
  const scenes = uniqueDialogueLinks(links);
  const comicPairs = [];
  for (const cab of sceneCabs(work, input.comics, reader)) {
    for (const pair of comicVoicePairs(cab)) comicPairs.push(pair);
  }
  const comics = uniqueComicLinks(comicPairs).map(link => ({...link, dialogue_kind:'comic', channels:['cinematic']}));

  const messages = tableStrings(tables.get(key(bindings[0])), [7, 3, 5, 12, 13, 15, 16]);
  const messageRows = [...messages];
  const recorded = recordedMessages(messageRows);
  const messageLinks = new Map();
  for (const [id, first, second, ...choices] of messageRows) {
    if (/^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(id)) {
      const source = recorded.messages.get(id)?.source || '';
      const previous = messageLinks.get(id);
      const voice_status = source || first || second || previous?.voice_status === 'unavailable' ? 'unavailable' : 'unvoiced';
      messageLinks.set(id, {text_id:id, source, dialogue_kind:'message', voice_status});
    }
    for (const choice of choices) if (/^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(choice)) {
      scenes.push({text_id:choice, source:'', dialogue_kind:'choice', voice_status:'unknown'});
    }
  }
  const ongoing = ongoingRows(tableStrings(tables.get(key(bindings[1])), [6, 7, 8]));
  const clips = clueIntervals(tableStrings(tables.get(key(bindings[2])), [1, 2, 3, 4, 5]), input.namespace);
  const tips = tipRows(tableStrings(tables.get(key(bindings[3])), [1, 11, 16, 14, 15, 3, 5, 6, 13],
    {vectors:[15], maxColumns:18}));
  const all = [...scenes, ...comics, ...messageLinks.values(), ...ongoing, ...tips,
    ...clips.map(clip => ({...clip, dialogue_kind:'narration', voice_status:'unavailable', channels:['dialogue', 'cinematic']}))];
  const ids = new Set(all.map(link => link.text_id));
  writeFileSync(join(work, 'links.json'), JSON.stringify(all), {flag:'wx'});
  for (const locale of locales) {
    const values = Object.create(null);
    for (const suffix of suffixes) {
      const table = tables.get(key('TextMap' + tags[locale] + suffix));
      if (!table && suffix === 'TemplateTb') throw Error('Released ZZZ locale table is missing');
      if (!table) continue;
      const seen = new Set();
      for (const [id, value] of tableStrings(table, [0, 1])) {
        if (!ids.has(id) && !/^Comic_[0-9a-f]{32}$/i.test(id)) continue;
        if (seen.has(id)) throw Error('Ambiguous subtitle in a ZZZ locale table');
        seen.add(id);
        values[id] = value;
      }
    }
    writeFileSync(join(work, 'texts-' + locale + '.json'), JSON.stringify(values), {flag:'wx'});
  }
  const knownTimelines = new Set(input.knownTimelineKeys || []);
  return {recorded_messages:recorded.messages.size, ambiguous_messages:recorded.unresolved,
    typed_timeline_callers:{keys:timelineKeys.size, original_owners:[...timelineKeys].filter(key => knownTimelines.has(key)).length,
      unresolved_keys:[...timelineKeys].filter(key => !knownTimelines.has(key)).sort(), current_use:'unclassified'},
    scene_records:links.length, comic_bindings:comics.length, ongoing_records:ongoing.length, tip_records:tips.length, clue_intervals:clips.length, unsupported_nodes:unsupported};
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [mode, work, readerPath] = process.argv.slice(2);
  if (mode === 'compile') {
    const {default: ts} = await import('typescript');
    if (ts.version !== '5.9.3') throw Error('Unexpected ZZZ reader compiler');
    const source = readFileSync(readerPath, 'utf8');
    const result = ts.transpileModule(source + '\nexport { unpackMhyFile };', {
      compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext}, reportDiagnostics: true,
    });
    if (result.diagnostics?.some(d => d.category === ts.DiagnosticCategory.Error)) throw Error('ZZZ reader compilation failed');
    let code = result.outputText;
    // The user's private cache can be outside the source checkout. Resolve
    // the same locked dependencies as the checkout's installed-game reader.
    for (const dependency of ['ooz-wasm', 'xxhash-wasm']) {
      const pattern = new RegExp(`from (['"])${dependency}\\1`, 'g');
      if ([...code.matchAll(pattern)].length !== 1) throw Error('Unexpected ZZZ reader imports');
      code = code.replace(pattern, () => 'from ' + JSON.stringify(import.meta.resolve(dependency)));
    }
    writeFileSync(join(work, 'galgame-perform.mjs'), code, {flag: 'wx'});
  } else {
    const run = {plan, bindings, 'scene-plan':scenePlan, 'comic-plan':comicPlan,
      'presentation-config-plan':presentationConfigPlan, 'presentation-owners':presentationOwners, catalogue}[mode];
    if (!run) throw Error('Unsupported ZZZ publisher query');
    const reader = await import(pathToFileURL(resolve(readerPath)).href);
    const input = JSON.parse(readFileSync(join(work, mode + '-input.json')));
    writeFileSync(join(work, mode + '-output.json'), JSON.stringify(run(work, input, reader)));
  }
}
