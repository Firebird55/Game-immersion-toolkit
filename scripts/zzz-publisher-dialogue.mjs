import {readFileSync, writeFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {resourceCatalogBytes, sceneAssetPaths, sceneBundleRangesFromCatalog, unityObjectsOfType} from './scene-catalog.mjs';
import {authoredDialogueFromCab} from './zzz-dialogue.mjs';

const utf8 = new TextDecoder('utf-8', {fatal: true});
const tags = {'zh-Hans':'', 'zh-Hant':'_CHT', en:'_EN', ja:'_JA', ko:'_KO', de:'_DE',
  fr:'_FR', 'es-ES':'_ES', 'pt-BR':'_PT', th:'_TH', ru:'_RU', vi:'_VI', id:'_ID'};

// Both tables have a root object with a vector of row objects in field zero.
// Only the two evidenced string fields in each row are interpreted.
export function* tableStrings(data, columns) {
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
  const first = field(indirect(0), 0);
  if (first === null) throw Error('Missing ZZZ row vector');
  const vector = indirect(first), count = data.readUInt32LE(vector);
  if (count > 2000000 || vector + 4 + 4 * count > data.length) throw Error('Invalid ZZZ row count');
  for (let i = 0; i < count; i++) {
    const row = indirect(vector + 4 + 4 * i);
    yield columns.map(index => {
      const at = field(row, index);
      if (at === null) return '';
      const start = indirect(at), end = start + 4 + data.readUInt32LE(start);
      if (end >= data.length || data[end] !== 0) throw Error('Invalid ZZZ table string');
      return utf8.decode(data.subarray(start + 4, end));
    });
  }
}

function designTables(files, work, wanted, unpack) {
  const tables = new Map();
  for (const file of files) {
    const data = readFileSync(join(work, file));
    if (data.toString('ascii', 0, 3) === 'BBL') continue;
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

function plan(work, input, reader) {
  const key = name => String(reader.xxHash64(name.toLowerCase()));
  const names = Object.values(tags).flatMap(tag => ['TemplateTb', 'OverwriteTemplateTb'].map(s => key('TextMap' + tag + s)));
  const perform = key('PerformTemplateTb');
  const tables = designTables(input.design, work, new Set([...names, perform]), reader.unpackMhyFile);
  if (!tables.has(perform)) throw Error('The released ZZZ Perform table is missing');
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
  const paths = sceneAssetPaths([...tableStrings(tables.get(perform), [2, 3])], 'dialogue');
  const wanted = new Set(paths.map(path => reader.xxHash64(path)));
  const ranges = new Map();
  for (const candidate of input.catalogs) {
    const catalog = resourceCatalogBytes(readFileSync(join(work, candidate)), reader.unpackMhyFile);
    if (!catalog) continue;
    const result = sceneBundleRangesFromCatalog(catalog, wanted, true);
    for (const r of result.ranges) {
      const id = r.block + '/' + r.offset;
      if (ranges.has(id) && ranges.get(id).size !== r.size) throw Error('Conflicting released scene range');
      ranges.set(id, r);
    }
  }
  if (!ranges.size) throw Error('No released dialogue scene ranges');
  return {texts, ranges: [...ranges.values()]};
}

function bindings(work, input, reader) {
  const sources = new Set();
  for (const name of input.blocks) {
    const data = readFileSync(join(work, name));
    for (let pos = 0; pos < data.length;) {
      const size = data.readUInt32LE(pos);
      pos += 4;
      if (!size || pos + size > data.length) throw Error('Incomplete staged ZZZ scene');
      const bundle = reader.unpackMhyFile(data.subarray(pos, pos + size), 0);
      if (bundle.end !== size) throw Error('Invalid ZZZ scene boundary');
      pos += size;
      for (const cab of bundle.files) for (const row of authoredDialogueFromCab(cab, {})) {
        if (row.text_id === input.id) sources.add(row.source);
      }
    }
  }
  if (sources.size !== 1 || ![...sources][0]) throw Error('No unique authored sentence recording for the requested subtitle');
  return {source: [...sources][0]};
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
    const run = {plan, bindings}[mode];
    if (!run) throw Error('Unsupported ZZZ publisher query');
    const reader = await import(pathToFileURL(resolve(readerPath)).href);
    const input = JSON.parse(readFileSync(join(work, mode + '-input.json')));
    writeFileSync(join(work, mode + '-output.json'), JSON.stringify(run(work, input, reader)));
  }
}
