import {gunzipSync} from 'node:zlib';

// Recent ZZZ builds store the resource catalog as a Unity serialized object
// inside the untagged mhy1 bundle. Older installations use a standalone gzip.
// Read only the known metadata layout, never infer a catalog from text matches.
export function unityResourceCatalog(cab) {
  const data=Buffer.from(cab);
  if(data.length<40||data.length>128*1024*1024||data.readUInt32BE(8)!==21||data[16]!==0)return null;
  const dataStart=data.readUInt32BE(12),fileSize=data.readUInt32BE(4);
  if(fileSize!==data.length||dataStart<20||dataStart>data.length)throw Error('Invalid Unity catalog bounds');
  let p=data.indexOf(0,20)+1;
  if(p<=20||p>100)throw Error('Invalid Unity version');
  const need=n=>{if(p+n>dataStart)throw Error('Truncated Unity catalog metadata');};
  need(9);p+=4;const typeTree=data[p++];
  if(typeTree!==0)throw Error('Unsupported Unity catalog type tree');
  const count=data.readUInt32LE(p);p+=4;
  if(count>4096)throw Error('Invalid Unity type count');
  const types=[];
  for(let i=0;i<count;i++){
    need(7);const type=data.readInt32LE(p);p+=7;types.push(type);
    if(type===114){need(16);p+=16;}
    need(16);p+=16;
  }
  need(4);const objects=data.readUInt32LE(p);p+=4;
  if(objects>100000)throw Error('Invalid Unity object count');
  let result=null;
  for(let i=0;i<objects;i++){
    p=(p+3)&~3;need(20);
    const start=dataStart+data.readUInt32LE(p+8),size=data.readUInt32LE(p+12),type=data.readUInt32LE(p+16);p+=20;
    if(type>=types.length||start+size>data.length)throw Error('Invalid Unity object bounds');
    if(types[type]===6776977){
      if(result)throw Error('Ambiguous Unity resource catalog');
      result=serializedResourceCatalog(data.subarray(start,start+size));
    }
  }
  return result;
}

export function serializedResourceCatalog(data) {
  if(data.length<12||data.readUInt32LE(0)!==3||data.toString('ascii',4,7)!=='Res')throw Error('Unsupported resource catalog object');
  let p=8;
  const array=stride=>{
    // Unity aligns the next array after packed block records (nine bytes each).
    // A block count divisible by four can hide this boundary in hotfix catalogs.
    const aligned=(p+3)&~3;
    if(aligned>data.length||data.subarray(p,aligned).some(byte=>byte!==0))throw Error('Invalid resource catalog alignment padding');
    p=aligned;
    if(p+4>data.length)throw Error('Truncated resource catalog array');
    const count=data.readUInt32LE(p);p+=4;
    if(count>5_000_000||p+count*stride>data.length)throw Error('Invalid resource catalog array');
    const start=p;p+=count*stride;return{count,start};
  };
  const assets=array(12),bundles=array(44),blocks=array(9),dependencies=array(4);
  // Secondary references are part of the serialized layout, not voice links.
  const references=array(4);
  if(p!==data.length)throw Error('Unsupported resource catalog tail');
  const blocksStart=52+assets.count*12,bundlesStart=blocksStart+blocks.count*9,end=bundlesStart+bundles.count*28;
  let dependencyBytes=0;
  for(let i=0;i<bundles.count;i++){
    const offset=bundles.start+i*44,begin=data.readUInt32LE(offset+24),finish=data.readUInt32LE(offset+28);
    const refBegin=data.readUInt32LE(offset+32),refEnd=data.readUInt32LE(offset+36);
    if(begin>finish||finish>dependencies.count||refBegin>refEnd||refEnd>references.count)throw Error('Invalid catalog dependency slice');
    dependencyBytes+=4+(finish-begin)*4;
    if(end+dependencyBytes>128*1024*1024)throw Error('Resource catalog exceeds limit');
  }
  const bytes=Buffer.alloc(end+dependencyBytes);
  bytes.writeUInt32LE(assets.count,8);bytes.writeUInt32LE(blocks.count,12);bytes.writeUInt32LE(bundles.count,16);
  bytes.writeUInt32LE(52,20);bytes.writeBigUInt64LE(BigInt(blocksStart),28);bytes.writeBigUInt64LE(BigInt(bundlesStart),36);bytes.writeBigUInt64LE(BigInt(end),44);
  data.copy(bytes,52,assets.start,assets.start+assets.count*12);
  for(let i=0;i<blocks.count;i++){
    const offset=blocks.start+i*9;
    if(data.readUInt32LE(offset+4)!==0)throw Error('Unsupported resource block ID');
    bytes[blocksStart+i*9]=data[offset+8];data.copy(bytes,blocksStart+i*9+1,offset,offset+8);
  }
  let next=end;
  for(let i=0;i<bundles.count;i++){
    const offset=bundles.start+i*44,target=bundlesStart+i*28;
    if(data.readUInt32LE(offset)>=blocks.count)throw Error('Invalid catalog block index');
    data.copy(bytes,target,offset,offset+24);bytes.writeUInt32LE(data.readUInt32LE(offset+40),target+24);
    const begin=data.readUInt32LE(offset+24),finish=data.readUInt32LE(offset+28);
    bytes.writeUInt32LE(finish-begin,next);next+=4;
    data.copy(bytes,next,dependencies.start+begin*4,dependencies.start+finish*4);next+=(finish-begin)*4;
  }
  return bytes;
}

export function resourceCatalogBytes(bytes, unpackMhyFile) {
  if(bytes[0]===31&&bytes[1]===139)return gunzipSync(bytes,{maxOutputLength:128*1024*1024});
  if(bytes.toString('ascii',0,4)!=='mhy1')return null;
  if(bytes.length>128*1024*1024)throw Error('Resource catalog bundle exceeds limit');
  const unpacked=unpackMhyFile(bytes,0);
  if(unpacked.end!==bytes.length)throw Error('Unsupported resource catalog bundle sequence');
  const catalogs=unpacked.files.map(unityResourceCatalog).filter(Boolean);
  if(catalogs.length>1)throw Error('Ambiguous resource catalog bundle');
  return catalogs[0]??null;
}

export function sceneCatalog(bytes, raw=false) {
  const data=raw?bytes:gunzipSync(bytes,{maxOutputLength:128*1024*1024});
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
  const categories = {galgame: ['GalGame'], dialogue: ['GalGame', 'Chat', 'ChatAudio', 'ChatPlus', 'Bubble', 'BubbleStory', 'BubbleNpc']};
  if (category !== 'comic' && !categories[category]) throw new Error('Unknown scene category');
  const namespaces = category === 'comic' ? ['Data/ScriptConfig/Comic/'] :
    categories[category].map(name => 'Data/ScriptConfig/Perform/Data/' + name + '/');
  const paths = new Set();
  const visit = entry => {
    if (typeof entry === 'string') {
      if (!namespaces.some(namespace => entry.toLowerCase().startsWith(namespace.toLowerCase())) || !entry.toLowerCase().endsWith('.asset')) return;
      const segments = entry.split('/');
      if (segments.some(segment => !segment || segment === '.' || segment === '..' || !/^[A-Za-z0-9_.& -]+$/.test(segment))) return;
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
export function sceneBundleRangesFromCatalog(compressed, wantedHashes, raw=false) {
  const bytes = raw?compressed:gunzipSync(compressed, {maxOutputLength: 128 * 1024 * 1024});
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
