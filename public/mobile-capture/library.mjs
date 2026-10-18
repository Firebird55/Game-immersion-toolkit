// Files remain in the user's file provider. Only selected entries are read.
import {Converter} from './ocr/opencc.mjs';
const simplify = Converter({from:'tw',to:'cn'});
export const FORMAT = 'proxy-mobile-library-v1';
export const LIMIT = 512 * 1024 * 1024;
export const GAMES = ['zzz','wuwa','pragmata','cyberpunk','witcher3','nte','beyond','heavyrain','hito'];
const hex = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const decoder = new TextDecoder('utf-8', {fatal:true});
export const sha256 = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)), x => x.toString(16).padStart(2,'0')).join('');
const table = new Uint32Array(256);
for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;table[n]=c>>>0;}
export function crc32(bytes){let c=0xffffffff;for(const byte of bytes)c=table[(c^byte)&255]^(c>>>8);return (c^0xffffffff)>>>0;}
const fail = message => {throw new Error(message);};
export async function openZip(file,{timeoutMs=20000}={}){
 if(!file || !Number.isSafeInteger(file.size) || file.size<22 || file.size>LIMIT)fail('Choose an exported ZIP of at most 512 MiB.');
 async function range(start,end){
  let timer;
  try{
   const bytes=await Promise.race([file.slice(start,end).arrayBuffer(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('File read timed out. Keep the USB connected and unlocked, then retry. You can also copy the ZIPs into On My iPhone.')),timeoutMs);})]);
   if(bytes.byteLength!==end-start)fail('The selected file is incomplete or no longer accessible. Reselect it from Files.');
   return bytes;
  }finally{clearTimeout(timer);}
 }
 const tail=new Uint8Array(await range(Math.max(0,file.size-65557),file.size)), view=new DataView(tail.buffer);
 let end=-1;
 for(let i=tail.length-22;i>=0;i--)if(view.getUint32(i,true)===0x06054b50&&i+22+view.getUint16(i+20,true)===tail.length){end=i;break;}
 if(end<0)fail('Not a complete mobile ZIP.');
 const count=view.getUint16(end+10,true), size=view.getUint32(end+12,true), offset=view.getUint32(end+16,true);
 if(view.getUint16(end+4,true)||view.getUint16(end+6,true)||view.getUint16(end+8,true)!==count||count===65535||size>16*1024*1024||offset+size!==file.size-tail.length+end)fail('Unsupported ZIP layout.');
 const data=new Uint8Array(await range(offset,offset+size)), central=new DataView(data.buffer), entries=new Map();
 let pos=0;
 for(let n=0;n<count;n++){
  if(pos+46>data.length||central.getUint32(pos,true)!==0x02014b50)fail('Invalid ZIP directory.');
  const flags=central.getUint16(pos+8,true), method=central.getUint16(pos+10,true), crc=central.getUint32(pos+16,true), compressed=central.getUint32(pos+20,true), length=central.getUint32(pos+24,true);
  const nameSize=central.getUint16(pos+28,true), extra=central.getUint16(pos+30,true), comment=central.getUint16(pos+32,true), start=central.getUint32(pos+42,true);
  if(pos+46+nameSize+extra+comment>data.length||!nameSize||nameSize>128)fail('Invalid ZIP entry.');
  const name=decoder.decode(data.slice(pos+46,pos+46+nameSize));
  if(!/^(manifest\.json|catalog\/[0-9]{5}\.ndjson|audio\/[a-f0-9]{64}\.mp3)$/.test(name)||entries.has(name)||method!==0||flags&~0x800||compressed!==length||start+30+nameSize+length>offset||central.getUint16(pos+34,true)!==0)fail('Unsupported or unsafe mobile ZIP entry.');
  if(length>(name==='manifest.json'?8*1024*1024:name.startsWith('catalog/')?4*1024*1024+16384:64*1024*1024))fail('Mobile ZIP entry is too large.');
  entries.set(name,{name,nameSize,flags,size:length,crc,start,limit:offset});pos+=46+nameSize+extra+comment;
 }
 if(pos!==data.length||!entries.has('manifest.json'))fail('Missing mobile manifest.');
 const ordered=[...entries.values()].sort((a,b)=>a.start-b.start);
 for(let i=0;i<ordered.length;i++){
  const entry=ordered[i];entry.limit=ordered[i+1]?.start??offset;
  if(entry.start+30+entry.nameSize+entry.size>entry.limit)fail('Overlapping ZIP entries.');
 }
 // USB providers make each File.slice expensive. Validate the complete directory
 // now, then verify a local header, bounds and CRC before reading that entry.
 async function read(name){
  const e=entries.get(name);if(!e)fail('Missing mobile ZIP entry.');
  if(e.offset==null){
   const bytes=await range(e.start,e.start+30+e.nameSize),head=new DataView(bytes);
   if(head.getUint32(0,true)!==0x04034b50||head.getUint16(6,true)!==e.flags||head.getUint16(8,true)!==0||head.getUint32(14,true)!==e.crc||head.getUint32(18,true)!==e.size||head.getUint32(22,true)!==e.size||head.getUint16(26,true)!==e.nameSize)fail('ZIP headers disagree.');
   const localName=decoder.decode(new Uint8Array(bytes,30,e.nameSize)),dataOffset=e.start+30+e.nameSize+head.getUint16(28,true);
   if(localName!==name||dataOffset+e.size>e.limit)fail('Invalid ZIP entry bounds.');
   e.offset=dataOffset;
  }
  const bytes=new Uint8Array(await range(e.offset,e.offset+e.size));if(crc32(bytes)!==e.crc)fail('Corrupt mobile ZIP entry.');return bytes;
 }
 const manifest=JSON.parse(decoder.decode(await read('manifest.json')));
 if(manifest?.format!==FORMAT||!GAMES.includes(manifest.game)||!['catalog','voices'].includes(manifest.kind))fail('Unsupported mobile library version or game.');
 return {file,entries,read,manifest};
}
const locale=value=>typeof value==='string'&&/^[a-zA-Z][a-zA-Z0-9-]{0,23}$/.test(value);
export function validateRow(row){
 const tagged=row?.sourceText!=null;
 if(tagged&&(!locale(row.sourceLanguage)||!locale(row.sourceLocale)||!locale(row.audioLocale)||!locale(row.translationLocale)||typeof row.sourceText!=='string'||!row.sourceText.trim()||row.sourceText.length>8000||typeof row.translationText!=='string'||row.translationText.length>8000))fail('Invalid dialogue language context.');
 if(!row||!hex(row.id)||typeof row.textId!=='string'||row.textId.length>512||typeof row.english!=='string'||typeof row.chinese!=='string'||!tagged&&(!row.english.trim()||!row.chinese.trim())||row.english.length>8000||row.chinese.length>8000||row.audio!==null&&!hex(row.audio)||row.sourceVoice!=null&&!hex(row.sourceVoice))fail('Invalid dialogue record.');
 if(row.audio&&!hex(row.sourceVoice))fail('Missing original voice binding.');
 for(const field of ['anchorsEnglish','anchorsChinese','anchorsSource','anchorsTranslation'])if(row[field]!=null&&(!Array.isArray(row[field])||row[field].length>100||row[field].some(v=>typeof v!=='string'||v.length>8000)))fail('Invalid authored OCR anchors.');
 if(row.memberTextIds!=null&&(!row.textId.includes(':context-')||!Array.isArray(row.memberTextIds)||row.memberTextIds.length!==2||row.memberTextIds.some(v=>typeof v!=='string'||v.length>512||!v.startsWith(row.textId.split(':context-')[0]+':'))||new Set(row.memberTextIds).size!==2))fail('Invalid authored context members.');
 if(row.playerVoice!=null&&!['male','female'].includes(row.playerVoice))fail('Unsupported player voice.');
 if(!Array.isArray(row.channels)||row.channels.some(c=>!['dialogue','cinematic','gameplay','tip'].includes(c)))fail('Invalid dialogue channels.');
 for(const field of ['speakerEnglish','speakerChinese'])if(row[field]!=null&&(typeof row[field]!=='string'||row[field].length>512))fail('Invalid speaker.');
 return Object.fromEntries(['id','textId','english','chinese','audio','sourceVoice','speakerEnglish','speakerChinese','playerVoice','anchorsEnglish','anchorsChinese','channels','sourceText','sourceLanguage','sourceLocale','translationText','translationLocale','audioLocale','anchorsSource','anchorsTranslation','memberTextIds'].filter(k=>Object.hasOwn(row,k)).map(k=>[k,row[k]]));
}
export async function readCatalog(zip, progress=()=>{}){
 const m=zip.manifest;
 if(m.kind!=='catalog'||!hex(m.revision)||typeof m.title!=='string'||m.title.length>120||!Array.isArray(m.catalog)||!m.catalog.length||m.catalog.length>32||m.catalog.reduce((n,p)=>n+(Number.isSafeInteger(p.size)?p.size:Infinity),0)>128*1024*1024||!Array.isArray(m.packs)||m.packs.length>10000||!Number.isSafeInteger(m.coverage?.dialogue)||m.coverage.dialogue>250000)fail('Invalid or oversized catalog manifest.');
 const expected=new Set(['manifest.json']), rows=[], ids=new Set(), audio=new Set(), packIds=new Set(),packedAudio=new Set();
 for(const part of m.catalog){
  if(!/^catalog\/[0-9]{5}\.ndjson$/.test(part.name)||expected.has(part.name)||!hex(part.sha256)||zip.entries.get(part.name)?.size!==part.size)fail('Invalid catalog segment.');
  expected.add(part.name);
  const bytes=await zip.read(part.name);if(await sha256(bytes)!==part.sha256)fail('Catalog checksum failed.');
  for(const line of decoder.decode(bytes).split('\n'))if(line){const row=validateRow(JSON.parse(line));if(ids.has(row.id)||rows.length>=250000)fail('Duplicate dialogue identity or oversized catalog.');ids.add(row.id);rows.push(row);if(row.audio)audio.add(row.audio);}
  progress(rows.length);
 }
 if(rows.length!==m.coverage.dialogue||expected.size!==zip.entries.size)fail('Catalog coverage or contents disagree.');
 for(const pack of m.packs){if(!hex(pack.id)||packIds.has(pack.id)||!Array.isArray(pack.clips)||pack.clips.length>65530||pack.clips.some(sha=>!hex(sha)||!audio.has(sha)||packedAudio.has(sha)||(packedAudio.add(sha),false)))fail('Invalid or duplicate voice pack reference.');packIds.add(pack.id);}
 if(audio.size!==new Set(m.packs.flatMap(p=>p.clips)).size)fail('Missing voice pack references.');
 if(m.languages!=null&&(!Array.isArray(m.languages)||!m.languages.length||m.languages.length>40||!m.languages.every(locale)))fail('Unsupported catalog languages.');
 // Do not retain arbitrary, deeply nested metadata from a selected file.
 const manifest={format:m.format,kind:m.kind,game:m.game,title:m.title,revision:m.revision,languages:m.languages??['zh-Hans','en'],coverage:{dialogue:rows.length,mappedVoices:rows.filter(r=>r.sourceVoice).length,exportedVoices:rows.filter(r=>r.audio).length,partial:m.coverage.partial===true},catalog:m.catalog.map(p=>({name:p.name,size:p.size,sha256:p.sha256})),packs:m.packs.map(p=>({id:p.id,clips:p.clips}))};
 return {manifest,rows};
}
export function validateVoices(zip,catalog){
 const m=zip.manifest, pack=catalog.manifest.packs.find(p=>p.id===m.id);
 if(m.kind!=='voices'||m.game!==catalog.manifest.game||!pack||!m.clips||typeof m.clips!=='object'||Array.isArray(m.clips))fail('Voice pack does not belong to this library.');
 if(Object.keys(m.clips).length!==pack.clips.length||zip.entries.size!==pack.clips.length+1)fail('Voice pack contents disagree.');
 for(const sha of pack.clips){const info=m.clips[sha], entry=zip.entries.get('audio/'+sha+'.mp3');if(!info||info.sha256!==sha||!entry||entry.size!==info.size)fail('Invalid voice clip reference.');}
 return pack.clips;
}
export async function readVoice(zip,sha){const bytes=await zip.read('audio/'+sha+'.mp3');if(await sha256(bytes)!==sha)fail('Voice checksum failed. Reselect an intact export.');return new Blob([bytes],{type:'audio/mpeg'});}

export const normalize = text => simplify(String(text).normalize('NFKC')).toLowerCase().replace(/<[^>]*>|\{[^{}]*\}|\[\/?(?:b|i|u|color|size|font)(?:=[^\]]*)?\]/g,'').replace(/[^\p{L}\p{N}]/gu,'');
export function subtitleRows(blocks,crop,width,height,game){
 const rows=(blocks??[]).flatMap(block=>block.paragraphs??[]).flatMap(p=>p.lines??[]);
 if(!rows.length)return {lines:[],menu:false};
 const result=[], labels=new Set(['talk','open','close','back','continue','cancel','jump','skip','select','exit','map','inventory','attack','交谈','对话','继续','取消','确定','退出','跳跃','选择','返回','跳过','打开','关闭','地图','背包']);
 let menu=false;
 for(const row of rows){
  const box=row.bbox;if(!box)continue;
  const left=crop[0]+box.x0/width*crop[2],right=crop[0]+box.x1/width*crop[2],top=crop[1]+box.y0/height*crop[3],value=row.text.trim(),key=normalize(value);
  if(row.confidence!=null&&row.confidence<40)continue;
  const band=game==='witcher3'?[.80,.87]:game==='cyberpunk'?[.85,.96]:game==='honkai3'?[.72,.96]:[.79,.96];
  if(game==='heavyrain'&&(top<band[0]||top>band[1]))continue;
  const short=(value.match(/[a-z]+/gi)?.length===1&&key.length<12)||(/[\u3400-\u9fff]/.test(value)&&key.length<4);
  if(game==='honkai3'&&crop[0]<.2&&key.length<25&&top<.79&&!/[.!?。！？]$/.test(value))continue;
  if((short||labels.has(key))&&(top<band[0]||top>band[1]))continue;
  if(left>(game==='cyberpunk'?.52:.60)&&top<(game==='cyberpunk'?.84:.80)){if(key.length>=8&&(row.confidence??100)>=65&&(value.match(/[a-z]+/gi)?.length>=2||/[\u3400-\u9fff]{4}/.test(value)))menu=true;continue;}
  if((left+right)/2<.22||(left+right)/2>.78)continue;
  result.push(value);
 }
 if(['nte','honkai3'].includes(game)&&result.length>1){const first=result[0],second=result[1];if(!/[.!?。！？]$/.test(first)&&normalize(first).length<=24&&normalize(second).length>normalize(first).length+8&&(first.match(/[a-z]+/gi)?.length<=3||/^[\u3400-\u9fff\s>»-]{1,8}$/.test(first)))result.shift();}
 return {lines:result,menu};
}
export function ratio(a,b){if(!a.length||!b.length)return 0;const previous=new Uint16Array(b.length+1);for(let i=0;i<a.length;i++){let diagonal=0;for(let j=0;j<b.length;j++){const old=previous[j+1];previous[j+1]=a[i]===b[j]?diagonal+1:Math.max(previous[j+1],previous[j]);diagonal=old;}}return 200*previous[b.length]/(a.length+b.length);}
const grams = text => [...new Set(Array.from({length:Math.max(0,text.length-2)},(_,i)=>text.slice(i,i+3)))];
export class DialogueMatcher{
 constructor(rows){this.exact=new Map();this.grams=null;this.cache=new Map();this.hito=rows.some(r=>r.textId.startsWith('hito:'));this.exactOnly=rows.some(r=>/^(nte|honkai3):/.test(r.textId));for(const row of rows)for(const value of [row.sourceText??row.chinese,row.translationText??row.english,...row.anchorsSource??row.anchorsChinese??[],...row.anchorsTranslation??row.anchorsEnglish??[]]){const key=normalize(value);if(key.length<2||key.length>2000)continue;const list=this.exact.get(key)??[];if(!list.includes(row))list.push(row);this.exact.set(key,list);}
  this.contextPairs=new Map();this.contextFirsts=new Set();
  for(const row of rows)if(row.memberTextIds)for(const [full,anchors] of [[row.sourceText,row.anchorsSource],[row.translationText,row.anchorsTranslation]]){
   const whole=normalize(full??''),last=normalize(anchors?.[0]??'');
   if(last&&whole.endsWith(last)&&whole.length>last.length){const first=whole.slice(0,-last.length),key=JSON.stringify([first,last]);this.contextFirsts.add(first);const list=this.contextPairs.get(key)??[];list.push(row);this.contextPairs.set(key,list);}
  }
 }
 contextFragments(values){return [...new Set(values.slice(0,128).map(normalize).filter(key=>this.contextFirsts.has(key)))];}
 sceneMatches(values,groups=[]){
  const scene=row=>/^heavyrain:\d+:[a-f0-9]{8}$/.test(row.textId)?row.textId.slice(0,row.textId.lastIndexOf(':')):null;
  const allowed=new Set(groups.slice(0,16)),hits=new Map(),observed=new Set();
  for(const value of values.slice(0,128)){
   const key=normalize(value);let hit=this.match(value);
   if(hit.state==='matched'&&hit.score===100&&key.length>=8&&scene(hit.row))observed.add(scene(hit.row));
   if(hit.state==='ambiguous'&&allowed.size){
    const candidates=[...this.exact].filter(([text])=>text===key||key.length>=(/\p{Script=Han}/u.test(key)?12:24)&&text.includes(key)).flatMap(([,rows])=>rows).filter(row=>allowed.has(scene(row))&&row.channels.includes('dialogue'));
    if(new Set(candidates.map(row=>row.sourceVoice??row.id)).size===1)hit={state:'matched',row:candidates[0],score:100};
   }
   if(hit.state==='matched')hits.set(hit.row.id,hit);
  }
  return {matches:[...hits.values()],groups:[...observed]};
 }
 matchContext(previous,values,channel='dialogue',player='unconfigured'){
  const hits=new Map();
  for(const first of previous.slice(0,32))for(const value of values.slice(0,128)){
   const last=normalize(value),rows=this.contextPairs.get(JSON.stringify([first,last]));if(!rows)continue;
   const hit=this.match(first+last,channel,player,false,true);
   if(hit.state==='matched'&&rows.some(row=>row.id===hit.row.id))hits.set(hit.row.id,hit);
  }
  return hits.size===1?[...hits.values()][0]:{state:hits.size?'ambiguous':'unmatched'};
 }
 match(text,channel='dialogue',player='unconfigured',fragment=false,exactOnly=false){const cacheKey=JSON.stringify([normalize(text),channel,player,fragment,exactOnly]);if(this.cache.has(cacheKey))return this.cache.get(cacheKey);const result=this.lookup(text,channel,player,fragment,exactOnly);if(this.cache.size>=512)this.cache.clear();this.cache.set(cacheKey,result);return result;}
 matchCandidates(values,channel='dialogue',player='unconfigured',fragment=false){
  for(const exactOnly of [true,false]){
   const results=values.slice(0,128).map(value=>({...this.match(value,channel,player,fragment,exactOnly),key:normalize(value),length:normalize(value).length})),hits=results.filter(r=>r.state==='matched').sort((a,b)=>b.score-a.score||b.length-a.length);
   if(hits.length){let best=hits[0];if(!this.exactOnly){const more=values.slice(0,128).filter(value=>normalize(value).includes(best.key)&&normalize(value).length>=Math.max(best.length*1.5,best.length+8)).map(value=>({...this.match(value,channel,player,fragment,false),length:normalize(value).length})),longer=more.filter(hit=>hit.state==='matched'&&hit.score>=92).sort((a,b)=>b.length-a.length||b.score-a.score);results.push(...more);if(longer.length){hits.push(...longer);best=longer[0];}}if(results.some(r=>r.state==='ambiguous'&&r.length>=best.length)||hits.some(r=>r.score===best.score&&r.length===best.length&&r.row.sourceVoice!==best.row.sourceVoice))return {state:'ambiguous'};return best;}
   if(exactOnly&&results.some(r=>r.state==='ambiguous'))return {state:'ambiguous'};
  }
  return {state:'unmatched'};
 }
 lookup(text,channel='dialogue',player='unconfigured',fragment=false,exactOnly=false){
  const key=normalize(text);if(key.length<2||key.length>2000)return {state:'unmatched'};
  let keys=this.exact.has(key)?[[key,100]]:[];
  const paragraphPage=channel==='dialogue'&&key.length>=(/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u.test(key)?12:24);
  if(paragraphPage){const pages=[];for(const [candidate,records] of this.exact)if(candidate.includes(key)&&records.some(r=>r.textId.startsWith('heavyrain:')))pages.push([candidate,100]);if(pages.length)keys=pages;}
  if(!keys.length&&!exactOnly&&!this.exactOnly&&channel==='dialogue'&&key.length>=(/\p{Script=Han}/u.test(key)?6:8)){
   if(!this.grams){this.grams=new Map();for(const [candidate,records] of this.exact)if(records.some(r=>r.sourceVoice))for(const gram of grams(candidate)){const keys=this.grams.get(gram)??[];keys.push(candidate);this.grams.set(gram,keys);}}
   const counts=new Map();for(const gram of grams(key))for(const candidate of this.grams.get(gram)??[])if(Math.abs(candidate.length-key.length)<Math.max(6,key.length*.25))counts.set(candidate,(counts.get(candidate)??0)+1);
   keys=[...counts].sort((a,b)=>b[1]-a[1]).slice(0,128).filter(([candidate])=>!this.hito||key.length>=12&&Math.abs(candidate.length-key.length)<=2&&!candidate.startsWith(key)&&JSON.stringify(candidate.match(/\d+/g))===JSON.stringify(key.match(/\d+/g))&&['不','没','能','应该','正在','必须'].every(word=>candidate.includes(word)===key.includes(word))).map(([candidate])=>[candidate,ratio(key,candidate)]).filter(([,score])=>score>=(this.hito?94:88)).sort((a,b)=>b[1]-a[1]);
   if(keys.length>1&&keys[1][1]>=keys[0][1]-2)return {state:'ambiguous'};
  }
  if(!keys.length&&fragment&&key.length>=12){const matches=[];for(const [candidate,records] of this.exact)if(candidate.includes(key)&&records.some(r=>r.channels.includes('cinematic')))matches.push([candidate,100]);keys=matches;}
  const possible=keys.flatMap(([candidate,score])=>(this.exact.get(candidate)??[]).filter(r=>r.channels.includes(channel)&&(!r.playerVoice||r.playerVoice===player)).map(row=>({row,score})));
  if(!possible.length)return {state:'unmatched'};
  const best=Math.max(...possible.map(r=>r.score)), chosen=possible.filter(r=>r.score===best);
  if(new Set(chosen.map(r=>r.row.sourceVoice??r.row.id)).size!==1)return {state:'ambiguous'};
  return {state:'matched',...chosen[0]};
 }
}

export function searchCatalog(rows,text,limit=20){
 const queries=String(text).split(/\r?\n/).map(normalize).filter(Boolean);
 if(!queries.length||queries.some(q=>q.length<2)||String(text).length>2000)return {rows:[],total:0};
 const exact=[],partial=[];let total=0;
 for(const row of rows){
  const values=[row.sourceText??row.chinese,row.translationText??row.english,...row.anchorsSource??row.anchorsChinese??[],...row.anchorsTranslation??row.anchorsEnglish??[]].map(normalize);
  if(!queries.every(q=>values.some(v=>v.includes(q))))continue;
  total++;const target=queries.every(q=>values.includes(q))?exact:partial;
  if(target.length<limit)target.push(row);
 }
 return {rows:[...exact,...partial].slice(0,limit),total};
}
