import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import {gzipSync} from 'node:zlib';
import {AUTO_CONFIG_FIELDS, AUTO_META_CONFIG_ASSET} from '../scripts/zzz-presentation-config.mjs';

const cli = fileURLToPath(new URL('../scripts/zzz-publisher-dialogue.mjs', import.meta.url));
const u32 = value => { const data=Buffer.alloc(4); data.writeUInt32LE(value); return data; };
const u64 = value => { const data=Buffer.alloc(8); data.writeBigUInt64LE(BigInt(value)); return data; };
const align = bytes => Buffer.concat([bytes, Buffer.alloc((4 - bytes.length % 4) % 4)]);
const string = value => align(Buffer.concat([u32(Buffer.byteLength(value)), Buffer.from(value)]));
const odinString = value => Buffer.concat([Buffer.from([1]), u32(value.length), Buffer.from(value, 'utf16le')]);
const typed = (id, name) => Buffer.concat([Buffer.from([0x2f]), u32(id), odinString(name)]);
const named = (name, value) => Buffer.concat([Buffer.from([0x27]), odinString(name), odinString(value)]);

function unityCab(records) {
  const kinds = [...new Set(records.map(([, kind]) => kind))];
  const types = kinds.flatMap(kind => [u32(kind), Buffer.alloc(kind === 114 ? 35 : 19)]);
  const preface = align(Buffer.concat([Buffer.from('2019.4.40f1\0'), u32(19), Buffer.from([0]),
    u32(kinds.length), ...types, u32(records.length)]));
  let offset = 0;
  const table = records.map(([id, kind, bytes]) => {
    const row = Buffer.concat([u64(id), u32(offset), u32(bytes.length), u32(kinds.indexOf(kind))]);
    offset += bytes.length;
    return row;
  });
  const size = preface.length + table.length * 20;
  const header = Buffer.alloc(20);
  header.writeUInt32BE(size);
  header.writeUInt32BE(20 + size + offset, 4);
  header.writeUInt32BE(21, 8);
  header.writeUInt32BE(20 + size, 12);
  return Buffer.concat([header, preface, ...table, ...records.map(row => row[2])]);
}

function flatTable(rows) {
  const output = [u32(12), Buffer.from([6, 0, 8, 0, 4, 0, 0, 0]), u32(8), u32(4), u32(rows.length)];
  const pointers = Buffer.alloc(rows.length * 4);
  output.push(pointers);
  let offset = 24 + pointers.length;
  for (const [index, cells] of rows.entries()) {
    const vtable = align(Buffer.alloc(4 + cells.length * 2));
    const body = Buffer.alloc(4 + cells.length * 4);
    vtable.writeUInt16LE(4 + cells.length * 2);
    vtable.writeUInt16LE(body.length, 2);
    body.writeUInt32LE(vtable.length);
    pointers.writeUInt32LE(offset + vtable.length - (24 + 4 * index), 4 * index);
    offset += vtable.length + body.length;
    output.push(vtable, body);
    let stringOffset = body.length;
    for (const [column, value] of cells.entries()) {
      const cell = 4 + column * 4;
      vtable.writeUInt16LE(cell, 4 + column * 2);
      if (typeof value === 'number') {
        body.writeUInt32LE(value, cell);
      } else {
        const bytes = align(Buffer.concat([u32(Buffer.byteLength(value)), Buffer.from(value), Buffer.alloc(1)]));
        body.writeUInt32LE(stringOffset - cell, cell);
        stringOffset += bytes.length;
        offset += bytes.length;
        output.push(bytes);
      }
    }
  }
  return Buffer.concat(output);
}

function releasedCatalog(hashes) {
  const assetEnd = 52 + hashes.length * 12, blockEnd = assetEnd + 9;
  const bundleEnd = blockEnd + hashes.length * 28;
  const header = Buffer.alloc(52);
  header.writeUInt32LE(hashes.length, 8);
  header.writeUInt32LE(1, 12);
  header.writeUInt32LE(hashes.length, 16);
  header.writeUInt32LE(52, 20);
  header.writeBigUInt64LE(BigInt(assetEnd), 28);
  header.writeBigUInt64LE(BigInt(blockEnd), 36);
  header.writeBigUInt64LE(BigInt(bundleEnd), 44);
  const bundles = hashes.map((_, index) => Buffer.concat([Buffer.alloc(20), u32(index * 8), u32(1)]));
  return gzipSync(Buffer.concat([header, ...hashes.map((hash, index) => Buffer.concat([u32(index), u64(hash)])),
    Buffer.alloc(1), u64(1), ...bundles, Buffer.alloc(hashes.length * 4)]));
}

const monoScript = (name, namespace = 'MoleMole') => Buffer.concat([string(name), Buffer.alloc(20),
  string(name), string(namespace), string(namespace === 'UnityEngine.Timeline' ? 'Unity.Timeline.dll' : 'Logic.dll')]);
const behaviour = (script, name, body) => Buffer.concat([Buffer.alloc(20), u64(script), string(name), body]);
const component = (name, body) => unityCab([[1, 115, monoScript(name)], [2, 114, behaviour(1, name, body)]]);
const textAsset = (name, data) => Buffer.concat([string(name), u32(data.length), data]);

function cinemaCab() {
  const f64 = value => { const data=Buffer.alloc(8); data.writeDoubleLE(value); return data; };
  const pointer = id => Buffer.concat([u32(0), u64(id)]);
  const clip = (asset, owner) => Buffer.concat([u32(1), f64(1), f64(0), pointer(asset), f64(2), f64(1), pointer(owner),
    Buffer.alloc(116), string('Owned clip')]);
  const track = (owner, asset, tail) => Buffer.concat([u32(3), Buffer.alloc(36), pointer(10),
    u32(0), string('a'.repeat(32)), u32(1), clip(asset, owner), u32(0), tail]);
  return unityCab([
    [1, 115, monoScript('TimelineAsset', 'UnityEngine.Timeline')],
    ...['SubtitleTrack', 'SubtitleClip', 'WwiseAudioTrack', 'WwiseAudioClip'].map((name, index) =>
      [index + 2, 115, monoScript(name, 'MoleMole.Timeline')]),
    [10, 114, behaviour(1, 'SyntheticTimeline', Buffer.concat([u32(0), u32(2), pointer(20), pointer(40)]))],
    [20, 114, behaviour(2, 'Subtitles', track(20, 30, u32(3)))],
    [30, 114, behaviour(3, 'Caption', Buffer.concat([string('OwnedFilmCaption'), u32(3), u32(0)]))],
    [40, 114, behaviour(4, 'Voice', track(40, 50, Buffer.alloc(12)))],
    [50, 114, behaviour(5, 'Audio', Buffer.concat([string('Play_vo_OwnedFilm'), Buffer.alloc(64)]))],
  ]);
}

function fixtures() {
  const names = ['performtemplatetb', 'messageconfigtemplatetb', 'ongoingtipsconfigtemplatetb',
    'subtitleconfigtemplatetb', 'tipsconfigtemplatetb', 'textmap_jatemplatetb', 'textmap_entemplatetb',
    'textmap_jaoverwritetemplatetb', 'assets/napresources/data/scriptconfig/perform/data/galgame/synthetic.asset',
    'assets/napresources/data/scriptconfig/comic/synthetic.asset', 'assets/napresources/cinema/synthetic.playable',
    'assets/napresources/data/audio/voicedata.json', 'textmap_enoverwritetemplatetb'];
  const hashes = Object.fromEntries(names.map((name, index) => [name, index + 200]));
  const [, , , , , , , , storyPath, comicPath, cinemaPath, voicePath] = names;
  const bindingTables = [flatTable([
    [1, 3, 'Data/ScriptConfig/Perform/Data/GalGame/Synthetic.asset', 'Data/ScriptConfig/Comic/Synthetic.asset'],
    [2, 6, 'SyntheticTimeline', ''],
  ]), ...Array.from({length:4}, () => flatTable([])),
  flatTable([['OwnedLine', '台詞'], ['OwnedFilmCaption', '映画の台詞']]),
  flatTable([['OwnedLine', 'Owned dialogue'], ['OwnedFilmCaption', 'Owned film caption']]),
  flatTable([['OwnedLine', '更新された台詞']])];
  const registry = Buffer.from([19, 23, 37]);
  const design = unityCab([...bindingTables.map((data, index) => [index + 1, 49, textAsset(String(hashes[names[index]]), data)]),
    [9, 49, textAsset('AudioResourceData', registry)]]);
  const scalarNames = new Set(['abilityRegistryConfigPath', 'graphRegistryConfigPath', 'levelGroupRegistryConfigPath', 'voSeqRegistryConfigPath']);
  const root = component('NewAutoConfigMetaConfig', Buffer.concat([Buffer.alloc(40), ...AUTO_CONFIG_FIELDS.map(name =>
    scalarNames.has(name) ? Buffer.concat([string(''), u64(0)]) :
      name === 'timelineDataPathes' ? Buffer.concat([u32(1), string(''), u64(101)]) : u32(0))]));
  const dictionary = Buffer.concat([Buffer.from([1]), odinString('timelineDatas'), typed(0,
    'System.Collections.Generic.Dictionary`2[[System.String, mscorlib],[MoleMole.TimelineData, Logic]], mscorlib'), u32(0),
  Buffer.from([6]), u64(1), Buffer.from([4, 0x2e]), named('$k', 'SyntheticTimeline'),
  Buffer.from([1]), odinString('$v'), typed(1, 'MoleMole.TimelineData, Logic'), u32(1),
  ...['_resPath', '_audioResPath', 'timelineResPathFemale'].map(name => named(name, '')),
  named('timelineResPath', cinemaPath), Buffer.from([5, 5, 7, 5])]);
  const configuration = component('ConfigTimelineData',
    Buffer.concat([u32(0), u32(dictionary.length), align(dictionary), Buffer.alloc(36)]));
  const story = Buffer.concat([Buffer.from([1]), odinString('storySections'), typed(0,
    'System.Collections.Generic.List`1[[MoleMole.GalGame.GalPlayableNodeBase, Logic]], mscorlib'), u32(0),
  Buffer.from([6]), u64(1), Buffer.from([2]), typed(1, 'MoleMole.GalGame.GalPlayStoryNode, Logic'),
  u32(1), named('dialogueKey', 'OwnedLine'), named('externalVoiceKey', 'GalGame_Owned_01'), Buffer.from([5, 7, 5])]);
  const comic = unityCab([[1, 142, Buffer.concat([string('103.bundle'), Buffer.alloc(32),
    string('103.bundle'), u32(1), string('104.bundle')])]]);
  const directory = unityCab([[1, 49, textAsset('VoiceData', Buffer.from('{"allPrefixes":["Owned/"],"voidBlocks":[41]}'))]]);
  const cinema = cinemaCab();
  const cabs = {d:design, r:root, t:configuration, s:story, c:comic, m:cinema, v:directory};
  const frame = token => Buffer.concat([u32(1), Buffer.from(token)]);
  const files = {'design-1.blk':Buffer.from('d'), 'catalog-1.blk':releasedCatalog([
    hashes[storyPath], hashes[comicPath], AUTO_META_CONFIG_ASSET, 101, 104, hashes[cinemaPath], hashes[voicePath],
  ]), '1.blk.presentation-roots':frame('r'), '1.blk.presentation-configs':frame('t'), '1.blk.comic-roots':frame('c'),
  '1.blk.scenes':frame('s'), '1.blk.comics':frame('c'), '1.blk.cinema-timelines':frame('m'), '1.blk.voice-directory':frame('v')};
  const designInputs = ['design-1.blk'], catalogs = ['catalog-1.blk'];
  const catalogue = {design:designInputs, locales:['en','ja'], namespace:'Japanese(JP)', blocks:['1.blk.scenes'],
    comics:['1.blk.comics'], cinemaTimelines:['1.blk.cinema-timelines'], knownTimelineKeys:['SyntheticTimeline']};
  const stages = [
    ['scene-plan', {design:designInputs, catalogs}],
    ['presentation-config-plan', {catalogs, roots:['1.blk.presentation-roots']}],
    ['presentation-owners', {catalogs, blocks:['1.blk.presentation-configs'], keys:['SyntheticTimeline'], timelineConfigs:1, videoConfigs:0}],
    ['comic-plan', {catalogs, roots:['1.blk.comic-roots'], rootCount:1}],
    ['catalogue', {...catalogue, includeAudio:false, voiceDirectory:[]}],
    ['catalogue', {...catalogue, includeAudio:true, voiceDirectory:['1.blk.voice-directory']}],
  ];
  const b64 = values => Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value.toString('base64')]));
  const reader = 'const hashes=' + JSON.stringify(hashes) + ', cabs=' + JSON.stringify(b64(cabs)) + ';\n' +
    'export function xxHash64(name){ if(!Object.hasOwn(hashes,name)) throw Error("Unknown authored hash input"); return BigInt(hashes[name]); }\n' +
    'export function unpackMhyFile(bytes, offset){ const key=bytes.toString("ascii",offset,offset+1); ' +
    'return {end:offset+1, files:[Buffer.from(cabs[key],"base64")]}; }';
  return {files, stagedFiles:b64(files), stages, reader, registry, hashes, cabs:b64(cabs),
    cinemaDigest:createHash('sha256').update(cinema).digest('hex'), b64};
}

const portableHost = String.raw`
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createContext, SourceTextModule} from 'node:vm';
import {gunzipSync} from 'node:zlib';
const {stagedFiles, stages, reader} = JSON.parse(readFileSync(0));
const source = pathToFileURL(process.argv[1]);
const directory = new URL('./', source).href;
const context = createContext({Buffer, TextDecoder}, {codeGeneration:{strings:false, wasm:false}});
const make = (text, identifier) => new SourceTextModule(text, {context, identifier});
const modules = new Map();
const load = url => {
  if (!modules.has(url)) modules.set(url, make(readFileSync(fileURLToPath(url), 'utf8'), url));
  return modules.get(url);
};
const main = load(source.href);
await main.link((specifier, parent) => {
  assert.match(specifier, /^\.\//);
  const dependency = new URL(specifier, parent.identifier).href;
  assert.ok(dependency.startsWith(directory));
  return load(dependency);
});
await main.evaluate();
const authored = make(reader, 'authored-reader');
await authored.link(() => assert.fail('Unexpected reader import'));
await authored.evaluate();
const run = main.namespace.runPublisherOperation;
const files = new Map(Object.entries(stagedFiles).map(([name, bytes]) => [name, Buffer.from(bytes, 'base64')]));
let hashes = 0;
let outputs = {};
const host = {
  read(name) { assert.ok(files.has(name)); return files.get(name); },
  write(name, bytes, {exclusive}) {
    assert.equal(exclusive, !name.endsWith('-output.json'));
    assert.ok(!Object.hasOwn(outputs, name));
    outputs[name] = bytes.toString('base64');
  },
  gunzip(bytes, options) {
    assert.equal(options.maxOutputLength, 128 * 1024 * 1024);
    return gunzipSync(bytes, options);
  },
  sha256(bytes) { hashes++; return createHash('sha256').update(bytes).digest('hex'); },
};
for (const name of ['../1.blk.scenes', 'NUL', '1.blk.scenes\n', 'subdir/1.blk.scenes']) {
  await assert.rejects(() => run('bindings', {blocks:[name]}, authored.namespace, host), /staged ZZZ filename/);
}
await assert.rejects(() => run('constructor', {}, authored.namespace, host), /Unsupported ZZZ publisher query/);
files.set('2.blk.scenes', Buffer.alloc(3));
await assert.rejects(() => run('bindings', {blocks:['2.blk.scenes']}, authored.namespace, host), /Incomplete staged ZZZ scene/);
const result = [];
for (const [mode, input] of stages) {
  outputs = {};
  const before = hashes;
  await run(mode, input, authored.namespace, host);
  assert.equal(hashes - before, input.includeAudio ? 1 : 0);
  result.push(outputs);
}
process.stdout.write(JSON.stringify(result));
`;

const androidHost = String.raw`
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {stagedFiles, stages, hashes, cabs} = JSON.parse(readFileSync(0));
const NodeBuffer = globalThis.Buffer;
const {CatalogueBytes} = await import(process.argv[2]);
const {executeStage, aes128EncryptBlock} = await import(process.argv[3]);
const {runPublisherOperation} = await import(process.argv[1]);
const file = name => NodeBuffer.from(stagedFiles[name], 'base64');
globalThis.Buffer = CatalogueBytes;
const reader = {
  xxHash64(name) { assert.ok(Object.hasOwn(hashes, name)); return BigInt(hashes[name]); },
  async unpackMhyFile(bytes, offset, check) {
    check();
    const key = bytes.toString('ascii', offset, offset + 1);
    assert.ok(Object.hasOwn(cabs, key));
    return {end:offset+1, files:[CatalogueBytes.from(NodeBuffer.from(cabs[key], 'base64'))]};
  },
};
const result = [];
for (const [mode, input] of stages) {
  const files = {};
  await executeStage({mode, input, operation:runPublisherOperation, reader, check() {},
    host: {
      async read(name) {
        if (input.includeAudio === false) assert.doesNotMatch(name, /voice-directory/);
        return file(name);
      },
      async write(name, bytes) { files[name] = NodeBuffer.from(bytes).toString('base64'); },
    }});
  result.push(files);
}
const [mode, input] = stages.at(-2);
await assert.rejects(executeStage({mode, input:{...input, voiceDirectory:['1.blk.voice-directory']},
  operation:runPublisherOperation, reader, check() {}, host:{}}), /cannot open voice data/);
let cancelled = false, writes = 0;
await assert.rejects(executeStage({mode, input, operation:runPublisherOperation, reader,
  check() { if (cancelled) throw Error('authored cancellation'); },
  host:{async read(name) { return file(name); }, async write() { writes++; cancelled = true; }}}), /authored cancellation/);
assert.equal(writes, 1);
const hex = value => CatalogueBytes.from(value, 'hex');
const encrypted = await aes128EncryptBlock(
  hex('000102030405060708090a0b0c0d0e0f'), hex('00112233445566778899aabbccddeeff'));
assert.equal(NodeBuffer.from(encrypted).toString('hex'), '69c4e0d86a7b0430d8cdb78070b4c55a');
await assert.rejects(aes128EncryptBlock(hex('00'), hex('00112233445566778899aabbccddeeff')), /Invalid ZZZ MHY AES block/);
process.stdout.write(JSON.stringify(result));
`;

test('five publisher stages preserve CLI bytes in an isolated host without external capabilities', () => {
  const fixture = fixtures();
  const {stagedFiles, stages, reader} = fixture;
  const isolated = spawnSync(process.execPath, ['--experimental-vm-modules', '--input-type=module', '-e', portableHost, cli],
    {input:JSON.stringify({stagedFiles, stages, reader}), encoding:'utf8'});
  assert.equal(isolated.status, 0, isolated.stderr || isolated.error?.message);
  const results = JSON.parse(isolated.stdout);
  const browserSource = name => new URL('../packaging/android/zzz-catalogue/' + name, import.meta.url).href;
  const android = spawnSync(process.execPath, ['--input-type=module', '-e', androidHost,
    new URL('../scripts/zzz-publisher-dialogue.mjs', import.meta.url).href, browserSource('catalogue-bytes.mjs'),
    browserSource('catalogue-runtime.mjs')],
  {input:JSON.stringify({stagedFiles, stages, hashes:fixture.hashes, cabs:fixture.cabs}), encoding:'utf8'});
  assert.equal(android.status, 0, android.stderr || android.error?.message);
  assert.deepEqual(JSON.parse(android.stdout), results);
  const json = (i, name) => JSON.parse(Buffer.from(results[i][name], 'base64'));
  assert.deepEqual(json(0, 'scene-plan-output.json').ranges, [{block:'Blocks/1.blk',offset:0,size:1}]);
  assert.equal(json(1, 'presentation-config-plan-output.json').timelineConfigs, 1);
  assert.deepEqual(json(2, 'presentation-owners-output.json').cinemaRanges, [{block:'Blocks/1.blk',offset:40,size:1}]);
  assert.deepEqual(json(3, 'comic-plan-output.json').ranges, [{block:'Blocks/1.blk',offset:32,size:1}]);
  assert.deepEqual(json(4, 'texts-ja.json'), {OwnedLine:'更新された台詞',OwnedFilmCaption:'映画の台詞'});
  assert.deepEqual(json(4, 'texts-en.json'), {OwnedLine:'Owned dialogue',OwnedFilmCaption:'Owned film caption'});
  assert.equal(json(4, 'links.json')[0].source, 'GalGame_Owned_01');
  assert.equal(json(4, 'links.json')[1].cinematic_event, 'Play_vo_OwnedFilm');
  assert.equal(json(4, 'voice-directory.json'), null);
  assert.equal(Object.hasOwn(results[4], 'audio-resource.flex'), false);
  assert.equal(Object.hasOwn(json(4, 'catalogue-output.json'), 'cinema_occurrences'), false);
  assert.deepEqual(json(5, 'voice-directory.json'), {prefixes:['Owned/'],blocks:[41]});
  assert.deepEqual(Buffer.from(results[5]['audio-resource.flex'], 'base64'), fixture.registry);
  assert.deepEqual(json(5, 'catalogue-output.json').cinema_occurrences, [{
    text_id:'OwnedFilmCaption', locale:'ja', start:1, duration:2, track:'20', clip:'30', subtitle_position:0,
    resource:fixture.cinemaDigest, timeline:'10', event:'Play_vo_OwnedFilm',
  }]);

  const scratch = fileURLToPath(new URL('../output/checks/', import.meta.url));
  mkdirSync(scratch, {recursive:true});
  const root = mkdtempSync(join(scratch, 'zzz-operations-'));
  try {
    const reader = join(root, 'authored-reader.mjs');
    writeFileSync(reader, fixture.reader);
    for (const [index, [mode, input]] of fixture.stages.entries()) {
      const work = join(root, String(index));
      mkdirSync(work);
      for (const [name, bytes] of Object.entries(fixture.files)) writeFileSync(join(work, name), bytes);
      writeFileSync(join(work, mode + '-input.json'), JSON.stringify(input));
      const result = spawnSync(process.execPath, [cli, mode, work, reader], {encoding:'utf8'});
      assert.equal(result.status, 0, result.stderr || result.error?.message);
      const files = Object.keys(results[index]);
      assert.deepEqual(fixture.b64(Object.fromEntries(files.map(name => [name, readFileSync(join(work, name))]))), results[index]);
    }
  } finally {
    assert.equal(dirname(realpathSync(root)), realpathSync(scratch));
    rmSync(root, {recursive:true, force:true});
  }
});
