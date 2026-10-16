import {gunzipSync} from 'node:zlib';

export function sceneCatalog(bytes) {
  const data=gunzipSync(bytes,{maxOutputLength:128*1024*1024});
  if(data.length<52)throw Error('Truncated scene catalog');
  const assets=data.readUInt32LE(8),blocks=data.readUInt32LE(12),bundles=data.readUInt32LE(16);
  const blocksStart=Number(data.readBigUInt64LE(28)),bundlesStart=Number(data.readBigUInt64LE(36)),end=Number(data.readBigUInt64LE(44));
  if(data.readUInt32LE(20)!==52||blocksStart!==52+assets*12||bundlesStart!==blocksStart+blocks*9||end!==bundlesStart+bundles*28||end>data.length||bundles>2_000_000)throw Error('Unsupported scene catalog layout');
  return{data,assets,blocks,bundles,blocksStart,bundlesStart,end};
}

export function cinematicBundleRanges(catalog) {
  const{data,blocks,bundles,blocksStart,bundlesStart}=catalog,ranges=[];
  for(let i=0;i<bundles;i++){
    const p=bundlesStart+i*28,size=data.readUInt32LE(p+24);
    // Timeline metadata is small; texture/movie payloads are never scanned.
    if(size<=512||size>256*1024)continue;
    const block=data.readUInt32LE(p);if(block>=blocks)throw Error('Scene block is outside catalog');
    ranges.push({block:`Blocks/${data.readUInt32LE(blocksStart+block*9+1)}.blk`,offset:data.readUInt32LE(p+20),size});
  }
  return ranges;
}

// Authored scene references, independent of version-specific table field names.
export function sceneAssetPaths(value, category) {
  if (!['galgame', 'comic'].includes(category)) throw new Error('Unknown scene category');
  const namespace = category === 'comic' ? 'Data/ScriptConfig/Comic/' : 'Data/ScriptConfig/Perform/Data/GalGame/';
  const paths = new Set();
  const visit = entry => {
    if (typeof entry === 'string') {
      if (!entry.toLowerCase().startsWith(namespace.toLowerCase()) || !entry.toLowerCase().endsWith('.asset')) return;
      const segments = entry.split('/');
      if (segments.some(segment => !segment || segment === '.' || segment === '..' || !/^[A-Za-z0-9_.-]+$/.test(segment))) return;
      paths.add(`assets/napresources/${entry}`.toLowerCase());
    } else if (Array.isArray(entry)) {
      entry.forEach(visit);
    } else if (entry && typeof entry === 'object') {
      Object.values(entry).forEach(visit);
    }
  };
  visit(value);
  return [...paths].sort();
}

// A scene's root bundle references separately packed voice dictionaries. Read
// the catalog's authored dependency graph and exact mhy1 byte ranges rather
// than assuming all dependencies share the root's block.
export function sceneBundleRangesFromCatalog(compressed, wantedHashes) {
  const bytes = gunzipSync(compressed, {maxOutputLength: 128 * 1024 * 1024});
  if (bytes.length < 52) throw Error('Truncated scene catalog');
  const assets = bytes.readUInt32LE(8), blocks = bytes.readUInt32LE(12), bundles = bytes.readUInt32LE(16);
  const assetsStart = bytes.readUInt32LE(20), blocksStart = Number(bytes.readBigUInt64LE(28));
  const bundlesStart = Number(bytes.readBigUInt64LE(36)), dependenciesStart = Number(bytes.readBigUInt64LE(44));
  if (assetsStart !== 52 || blocksStart !== assetsStart + assets * 12 ||
      bundlesStart !== blocksStart + blocks * 9 || dependenciesStart !== bundlesStart + bundles * 28 ||
      dependenciesStart > bytes.length || bundles > 2_000_000) throw Error('Unsupported scene catalog layout');
  const roots = [], matchedHashes = [];
  for (let i = 0; i < assets; i++) {
    const offset = assetsStart + i * 12, hash = bytes.readBigUInt64LE(offset + 4);
    if (!wantedHashes.has(hash)) continue;
    const bundle = bytes.readUInt32LE(offset);
    if (bundle >= bundles) throw Error('Scene bundle is outside catalog');
    roots.push(bundle); matchedHashes.push(hash);
  }
  if (!roots.length) return {ranges: [], matchedHashes};
  const dependencyOffsets = new Uint32Array(bundles);
  let position = dependenciesStart;
  for (let i = 0; i < bundles; i++) {
    if (position + 4 > bytes.length) throw Error('Truncated scene dependencies');
    dependencyOffsets[i] = position;
    const count = bytes.readUInt32LE(position); position += 4;
    if (count > bundles || position + count * 4 > bytes.length) throw Error('Invalid scene dependencies');
    position += count * 4;
  }
  const selected = new Set(), queue = [...roots];
  for (let next = 0; next < queue.length; next++) {
    const bundle = queue[next];
    if (selected.has(bundle)) continue;
    if (bundle >= bundles) throw Error('Scene dependency is outside catalog');
    selected.add(bundle);
    const offset = dependencyOffsets[bundle], count = bytes.readUInt32LE(offset);
    for (let i = 0; i < count; i++) queue.push(bytes.readUInt32LE(offset + 4 + i * 4));
    if (queue.length > 5_000_000) throw Error('Scene dependency graph exceeds limit');
  }
  const ranges = [...selected].map(bundle => {
    const offset = bundlesStart + bundle * 28, block = bytes.readUInt32LE(offset);
    if (block >= blocks) throw Error('Scene block is outside catalog');
    return {block: `Blocks/${bytes.readUInt32LE(blocksStart + block * 9 + 1)}.blk`,
      offset: bytes.readUInt32LE(offset + 20), size: bytes.readUInt32LE(offset + 24)};
  });
  return {ranges, matchedHashes};
}
