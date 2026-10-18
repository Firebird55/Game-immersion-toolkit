import test from 'node:test';
import assert from 'node:assert/strict';
import {zipSync,strToU8} from 'fflate';
import {openZip,readCatalog,readVoice,validateVoices,validateRow,sha256,FORMAT,DialogueMatcher,ratio,subtitleRows,searchCatalog} from '../public/mobile-capture/library.mjs';
import {regions,candidates,cleanOcrBlocks} from '../public/mobile-capture/ocr-pipeline.mjs';
import {cacheBudget} from '../public/mobile-capture/storage.mjs';
const hex='a'.repeat(64), voiceHash=await sha256(new Uint8Array([1,2,3]));
const row={id:hex,textId:'dialogue-one',english:'The lantern is bright.',chinese:'灯笼很亮。',sourceVoice:hex,audio:voiceHash,channels:['dialogue','cinematic','gameplay']};
test('Traditional Chinese OCR and search resolve the original performance',()=>{
 const matcher=new DialogueMatcher([row]);
 const match=matcher.match('燈籠很亮。');
 assert.equal(match.score,100);assert.equal(match.row,row);assert.equal(match.row.chinese,'灯笼很亮。');
 assert.equal(searchCatalog([row],'燈籠').total,1);
 const collision={...row,id:'b'.repeat(64),sourceVoice:'b'.repeat(64),chinese:'燈籠很亮。'};
 assert.equal(new DialogueMatcher([row,collision]).match('燈籠很亮。').state,'ambiguous');
 assert.equal(new DialogueMatcher([{...row,textId:'nte:verified'}]).match('燈籠很亮。').state,'matched');
});
const bytes=strToU8(JSON.stringify(row)+'\n');
const manifest={format:FORMAT,kind:'catalog',game:'zzz',title:'Synthetic game',revision:hex,coverage:{dialogue:1},catalog:[{name:'catalog/00000.ndjson',size:bytes.length,sha256:await sha256(bytes)}],packs:[{id:hex,clips:[voiceHash]}]};
const make=(entries,level=0)=>new File([zipSync(Object.fromEntries(Object.entries(entries).map(([key,value])=>[key,typeof value==='object'&&!(value instanceof Uint8Array)?strToU8(JSON.stringify(value)):value])),{level})],'library.zip');
test('catalog checksum, metadata, Unicode and random-access reading',async()=>{const file=make({'manifest.json':manifest,'catalog/00000.ndjson':bytes}),zip=await openZip(file),result=await readCatalog(zip);assert.equal(result.rows[0].chinese,row.chinese);assert.equal(result.rows[0].id,hex);});
test('unknown metadata is discarded rather than retained in the browser catalog cache',async()=>{const extra={...manifest,accountData:{nested:{anything:'discard'}}};const result=await readCatalog(await openZip(make({'manifest.json':extra,'catalog/00000.ndjson':bytes})));assert.equal(result.manifest.accountData,undefined);assert.equal(result.manifest.coverage.exportedVoices,1);});
test('voice association and per-entry checksum',async()=>{const m={format:FORMAT,kind:'voices',game:'zzz',id:hex,clips:{[voiceHash]:{size:3,sha256:voiceHash}}},zip=await openZip(make({'manifest.json':m,['audio/'+voiceHash+'.mp3']:new Uint8Array([1,2,3])}));assert.deepEqual(validateVoices(zip,{manifest}),[voiceHash]);assert.equal((await readVoice(zip,voiceHash)).size,3);assert.throws(()=>validateVoices(zip,{manifest:{...manifest,game:'wuwa'}}),/belong/);});
test('unknown/compressed/path entries are rejected',async()=>{await assert.rejects(openZip(make({'manifest.json':manifest,'../private':bytes})),/unsafe/);await assert.rejects(openZip(make({'manifest.json':manifest,'catalog/00000.ndjson':bytes},6)),/unsafe/);});
test('truncated and oversized ZIPs rejected before reading',async()=>{const file=make({'manifest.json':manifest});await assert.rejects(openZip(new File([await file.slice(0,file.size-1).arrayBuffer()],'bad.zip')),/complete/);await assert.rejects(openZip({size:512*1024**2+1,slice:()=>assert.fail('must not read')}),/512/);});
test('corrupt catalog and duplicate rows are rejected',async()=>{const bad=new Uint8Array(bytes);bad[0]=91;await assert.rejects(readCatalog(await openZip(make({'manifest.json':manifest,'catalog/00000.ndjson':bad}))),/checksum/);const duplicate=strToU8(JSON.stringify(row)+'\n'+JSON.stringify(row)+'\n');const m={...manifest,coverage:{dialogue:2},catalog:[{name:'catalog/00000.ndjson',size:duplicate.length,sha256:await sha256(duplicate)}]};await assert.rejects(readCatalog(await openZip(make({'manifest.json':m,'catalog/00000.ndjson':duplicate}))),/Duplicate/);});
test('matching preserves anchors and requires unique original performances',()=>{const match=new DialogueMatcher([row]);assert.equal(match.match(row.chinese).row.id,hex);assert.equal(match.match('The lantern is bright').state,'matched');const ambiguous=new DialogueMatcher([row,{...row,id:'b'.repeat(64),sourceVoice:'b'.repeat(64)}]);assert.equal(ambiguous.match(row.english).state,'ambiguous');const player=new DialogueMatcher([{...row,playerVoice:'female'}]);assert.equal(player.match(row.english).state,'unmatched');assert.equal(player.match(row.english,'dialogue','female').state,'matched');});
test('candidate ranking prefers exact dialogue over a longer fuzzy OCR fragment',()=>{const second={...row,id:'b'.repeat(64),sourceVoice:'b'.repeat(64),english:'We can keep walking.'},matcher=new DialogueMatcher([row,second]);assert.equal(matcher.matchCandidates(['The lantern is really bright.','We can keep walking.']).row.id,second.id);});

test('a wrapped full caption takes precedence over its isolated exact phrase',()=>{
 const full={...row,id:'b'.repeat(64),textId:'beyond:full',sourceVoice:'b'.repeat(64),english:'Please get back to them immediately and STOP THEM!'},short={...row,id:'c'.repeat(64),textId:'beyond:short',sourceVoice:'c'.repeat(64),english:'STOP THEM!'};
 const values=['Please get back to them immediatly and STOP THEM!','STOP THEM!'];
 assert.equal(new DialogueMatcher([full,short]).matchCandidates(values).row.id,full.id);
 const another={...full,id:'d'.repeat(64),sourceVoice:'d'.repeat(64)};
 assert.equal(new DialogueMatcher([full,short,another]).matchCandidates(values).state,'ambiguous');
 assert.equal(new DialogueMatcher([full,short,another]).matchCandidates(['STOP THEM!']).row.id,short.id);
});

test('authored Dutch context resolves two exact Chinese captions and retains ambiguity otherwise',()=>{
 const first={...row,id:'b'.repeat(64),textId:'beyond:ONE:1',sourceVoice:'b'.repeat(64),sourceLanguage:'nl',sourceLocale:'nl',audioLocale:'nl',sourceText:'Goed.',translationLocale:'zh-Hans',translationText:'好的'},other={...first,id:'c'.repeat(64),textId:'beyond:OTHER:1',sourceVoice:'c'.repeat(64)};
 const context={...first,id:'d'.repeat(64),textId:'beyond:ONE:context-100-900',sourceVoice:'d'.repeat(64),sourceText:'Goed. We gaan naar huis.',translationText:'好的 我们回家吧。',anchorsSource:['We gaan naar huis.'],anchorsTranslation:['我们回家吧。'],memberTextIds:['beyond:ONE:1','beyond:ONE:2']};
 const collision={...other,sourceText:'Een andere tekst.',translationText:'我们回家吧。'};
 const matcher=new DialogueMatcher([first,other,context,collision]);
 assert.equal(matcher.matchCandidates(['好的']).state,'ambiguous');
 assert.equal(matcher.matchCandidates(['我们回家吧。']).state,'ambiguous');
 const previous=matcher.contextFragments(['好的']);
 assert.equal(matcher.matchContext(previous,['我们回家吧。']).row.id,context.id);
 assert.equal(matcher.matchContext([],['我们回家吧。']).state,'unmatched');
 assert.deepEqual(validateRow(context).memberTextIds,context.memberTextIds);
 assert.throws(()=>validateRow({...context,memberTextIds:['beyond:ONE:1','beyond:WRONG:2']}),/context members/);
});
test('fuzzy short text rejected; extra channels are exact only',()=>{const match=new DialogueMatcher([row]);assert.equal(match.match('The lantern is brlght.').state,'matched');assert.equal(match.match('The lantern is brlght.','gameplay').state,'unmatched');assert.equal(match.match('灯笼狠亮').state,'unmatched');assert.equal(ratio('abcd','abxd'),75);});
test('Honkai/NTE require authored exact anchors, not similar unsupported rewrites',()=>{for(const game of ['honkai3','nte']){const match=new DialogueMatcher([{...row,textId:game+':verified'}]);assert.equal(match.match(row.english).state,'matched');assert.equal(match.match('The lantern is brlght.').state,'unmatched');}});
test('comics use full utterances; authored anchors resolve one performance',()=>{const full={...row,english:'The lantern is bright. Let us continue walking.',anchorsEnglish:['Let us continue walking.']};const matcher=new DialogueMatcher([full]);assert.equal(matcher.match('Let us continue walking.').row.english,full.english);assert.equal(matcher.match('The lantern is bright','cinematic','unconfigured',true).row.english,full.english);});
test('Witcher square-bracket NPC captions retain their words while formatting tags are stripped',()=>{const matcher=new DialogueMatcher([row]);assert.equal(matcher.match('[The lantern is bright.]','gameplay').state,'matched');assert.equal(matcher.match('[color=white]The lantern is bright.[/color]','gameplay').state,'matched');});
test('response menus and peripheral interaction labels are filtered geometrically',()=>{const blocks=[{paragraphs:[{lines:[{text:'A response choice',bbox:{x0:600,x1:800,y0:20,y1:45}},{text:'A centered spoken subtitle',bbox:{x0:200,x1:600,y0:220,y1:245}},{text:'Jump',bbox:{x0:10,x1:50,y0:10,y1:30}}]}]}];const result=subtitleRows(blocks,[.12,.59,.76,.37],1000,300,'cyberpunk');assert.equal(result.menu,true);assert.deepEqual(result.lines,['A centered spoken subtitle']);});
test('extra crops stay bounded and preserve independently calibrated dialogue',()=>{const crop=[.2,.1,.6,.3],list=regions('cyberpunk',undefined,true,true,{overhead:crop});assert.deepEqual(list[0].crop,[.12,.59,.76,.37]);assert(list.slice(1).every(r=>r.crop[1]>=.1&&r.crop[1]+r.crop[3]<=.400001));});
test('OCR candidates trim surrounding noise, retain middle words and separate languages',()=>{const blocks=[{paragraphs:[{lines:[{text:'x The lantern is bright x',confidence:65,words:[{text:'x',confidence:10},...['The','lantern','is','bright'].map(text=>({text,confidence:95})),{text:'x',confidence:10}]}]}]}];assert.equal(cleanOcrBlocks(blocks)[0].paragraphs[0].lines[0].text,'The lantern is bright');const parsed=candidates({text:'Guide: The lantern is bright. ~ 灯笼很亮。',blocks:[]},{crop:[0,0,1,1],channel:'dialogue'},100,100,'zzz');assert(parsed.values.includes('The lantern is bright.'));assert(!parsed.values.some(v=>v.includes('bright')&&v.includes('灯笼')));});
test('a voiced character name in a Honkai nameplate cannot play an unrelated performance',()=>{const blocks=[{paragraphs:[{lines:[{text:'Kiana >',confidence:95,bbox:{x0:50,x1:120,y0:20,y1:40}},{text:'An unsupported dialogue rewrite continues here.',confidence:95,bbox:{x0:50,x1:850,y0:60,y1:80}}]}]}];const parsed=subtitleRows(blocks,[.04,.72,.96,.24],1000,250,'honkai3');assert.deepEqual(parsed.lines,['An unsupported dialogue rewrite continues here.']);});
test('noise trimmed from a Wuthering response choice cannot widen its bounds into the subtitle lane',()=>{const blocks=[{paragraphs:[{lines:[{text:'noise Someone is there.',confidence:70,bbox:{x0:10,x1:800,y0:10,y1:40},words:[{text:'noise',confidence:5,bbox:{x0:10,x1:100,y0:10,y1:40}},...['Someone','is','there.'].map((text,i)=>({text,confidence:95,bbox:{x0:720+i*25,x1:750+i*25,y0:20,y1:40}}))]}]}]}];const parsed=subtitleRows(cleanOcrBlocks(blocks),[.10,.64,.80,.32],1000,300,'wuwa');assert.deepEqual(parsed.lines,[]);assert.equal(parsed.menu,true);});

test('manual search finds unvoiced text, fragments and both languages without choosing an ambiguous performance',()=>{
 const quiet={...row,sourceVoice:null,audio:null},variant={...row,id:'b'.repeat(64),playerVoice:'male'};
 assert.deepEqual(searchCatalog([quiet],'lantern').rows,[quiet]);
 assert.equal(searchCatalog([quiet],row.english+'\n'+row.chinese).total,1);
 assert.equal(searchCatalog([row,variant],row.english).total,2);
 assert.equal(searchCatalog([quiet],'<img src=x>').total,0);
});

test('USB opening uses a bounded number of reads independent of voice entry count',async()=>{
 const clips={},entries={};for(let i=0;i<1000;i++){const id=i.toString(16).padStart(64,'0');clips[id]={size:3,sha256:id};entries['audio/'+id+'.mp3']=new Uint8Array([1,2,3]);}
 const file=make({'manifest.json':{format:FORMAT,kind:'voices',game:'zzz',id:hex,clips},...entries});let reads=0,readBytes=0;
 const provider={size:file.size,slice(a,b){reads++;readBytes+=b-a;return file.slice(a,b);}};
 const zip=await openZip(provider);assert.equal(reads,4);assert(readBytes<512*1024);
 const before=reads;assert.equal((await zip.read('audio/'+'0'.repeat(64)+'.mp3')).length,3);assert.equal(reads-before,2);
});

test('deferred voice header and extended bounds are rejected before playback',async()=>{
 const id='0'.repeat(64),m={format:FORMAT,kind:'voices',game:'zzz',id:hex,clips:{[id]:{size:3,sha256:id}}};
 const good=make({'manifest.json':m,['audio/'+id+'.mp3']:new Uint8Array([1,2,3])}),zip=await openZip(good),entry=zip.entries.get('audio/'+id+'.mp3');
 for(const corrupt of [bytes=>bytes[entry.start]=0,bytes=>new DataView(bytes.buffer).setUint16(entry.start+28,65535,true)]){
  const bytes=new Uint8Array(await good.arrayBuffer());corrupt(bytes);const bad=await openZip(new File([bytes],'bad.zip'));
  await assert.rejects(bad.read('audio/'+id+'.mp3'),/headers|bounds/);
 }
});

test('disconnected or stalled file providers fail with recovery instructions',async()=>{
 await assert.rejects(openZip({size:100,slice:()=>({arrayBuffer:()=>new Promise(()=>{})})},{timeoutMs:10}),/timed out/);
 await assert.rejects(openZip({size:100,slice:()=>({arrayBuffer:async()=>new ArrayBuffer(0)})}),/no longer accessible/);
});

test('storage check compares catalog cache budget with browser quota, excluding multi-GB voice packs',()=>{
 const m={catalog:[{size:1024}],packs:[{size:4*1024**3}]};
 assert.equal(cacheBudget(m,{quota:100*1024**2,usage:0}).sufficient,true);
 assert.equal(cacheBudget(m,{quota:1024,usage:1024}).sufficient,false);
 assert.equal(cacheBudget(m,{quota:null,usage:null}).sufficient,null);
});


test('Dutch catalog matches authored source pages and keeps unavailable translation empty',()=>{
 for(const game of ['beyond','heavyrain']){
 const tagged={...row,game,textId:game+':test',english:'',chinese:'',sourceLanguage:'nl',sourceLocale:'nl',sourceText:'Een volledige synthetische zin.',translationText:'',translationLocale:'zh-Hans',audioLocale:'nl',anchorsSource:['Een volledige','synthetische zin.']};
 const clean=validateRow(tagged),matcher=new DialogueMatcher([clean]);
 assert.equal(matcher.match('synthetische zin.').row.sourceLanguage,'nl');
 assert.equal(clean.translationText,'');assert.deepEqual(regions(game,undefined,false,false)[0].crop,[.05,.70,.90,.28]);
 assert.deepEqual(regions(game,[.10,.70,.80,.28],false,false)[0].crop,[.10,.70,.80,.28]);
 assert.throws(()=>validateRow({...tagged,sourceLanguage:'../key'}));
 }
});

test('HEAVY RAIN runtime pages require exact unique paragraphs, while document rows are excluded',()=>{
 const a={...row,textId:'heavyrain:a',sourceText:'We vertrekken morgen samen vroeg. Neem de blauwe koffer mee naar het station.',sourceLanguage:'nl',sourceLocale:'nl',translationText:'这是第一个合成测试段落。',translationLocale:'zh-Hans',audioLocale:'nl'},
 b={...a,id:'b'.repeat(64),textId:'heavyrain:b',sourceVoice:'b'.repeat(64),sourceText:'We vertrekken morgen samen vroeg. Laat de groene koffer hier in de slaapkamer.'};
 const matcher=new DialogueMatcher([a,b]);
 assert.equal(matcher.match('Neem de blauwe koffer mee naar het station.').row,a);
 assert.equal(matcher.match('We vertrekken morgen samen vroeg.').state,'ambiguous');
 assert.equal(matcher.match('koffer mee').state,'unmatched');
 assert.equal(matcher.match('Neem de blauwe koffers mee naar het station.','dialogue','unconfigured',false,true).state,'unmatched');
 const document={text:a.sourceText,confidence:99,bbox:{x0:100,x1:800,y0:30,y1:50}},caption={...document,text:'Gesproken ondertitel onderaan.',bbox:{x0:100,x1:800,y0:160,y1:180}};
 assert.deepEqual(subtitleRows([{paragraphs:[{lines:[document,caption]}]}],[0,.70,1,.28],1000,280,'heavyrain').lines,[caption.text]);
});

test('HEAVY RAIN authored group narrows exact short captions without combining speakers',()=>{
 const child={...row,textId:'heavyrain:100:00000001',sourceText:'Pap!',sourceLanguage:'nl',sourceLocale:'nl',translationText:'爸爸！',translationLocale:'zh-Hans',audioLocale:'nl'},
 other={...child,id:'b'.repeat(64),sourceVoice:'b'.repeat(64),textId:'heavyrain:200:00000002'},
 father={...child,id:'c'.repeat(64),sourceVoice:'c'.repeat(64),textId:'heavyrain:100:00000003',sourceText:'Rustig aan, jullie rennen me nog omver!',translationText:'慢一点，你们差点把我撞倒！'};
 const matcher=new DialogueMatcher([child,other,father]),values=['Pap!',father.sourceText];
 const initial=matcher.sceneMatches(values);assert.equal(initial.matches.length,1);assert.deepEqual(initial.groups,['heavyrain:100']);
 const contextual=matcher.sceneMatches(values,initial.groups);assert.deepEqual(new Set(contextual.matches.map(hit=>hit.row.id)),new Set([child.id,father.id]));
 assert.equal(matcher.sceneMatches(['Pap!']).matches.length,0);
 assert.equal(matcher.sceneMatches(['Pap!'],['heavyrain:100','heavyrain:200']).matches.length,0);
 assert.equal(matcher.sceneMatches(['Papp!'],['heavyrain:100']).matches.length,0);
});

test('BEYOND overlapping voices stay independent while wrapped fragments and ambiguity stay excluded',()=>{
 const main={...row,textId:'beyond:main',english:'Welcome back to the laboratory.'},background={...row,id:'b'.repeat(64),textId:'beyond:background',sourceVoice:'b'.repeat(64),english:'I said it is almost ready!'},
 full={...row,id:'c'.repeat(64),textId:'beyond:wrapped',sourceVoice:'c'.repeat(64),english:'Please return and help us immediately!'},fragment={...row,id:'d'.repeat(64),textId:'beyond:fragment',sourceVoice:'d'.repeat(64),english:'help us immediately!'};
 const matcher=new DialogueMatcher([main,background,full,fragment]);
 assert.deepEqual(new Set(matcher.simultaneousMatches([main.english,background.english]).map(hit=>hit.row.id)),new Set([main.id,background.id]));
 assert.deepEqual(new Set(matcher.simultaneousMatches([full.english,fragment.english,background.english]).map(hit=>hit.row.id)),new Set([full.id,background.id]));
 const duplicate={...full,id:'e'.repeat(64),sourceVoice:'e'.repeat(64)};
 assert.deepEqual(new DialogueMatcher([full,fragment,background,duplicate]).simultaneousMatches([full.english,fragment.english,background.english]).map(hit=>hit.row.id),[background.id]);
 assert.deepEqual(matcher.simultaneousMatches(['7654','LOOK MOVE','O □ + ☆']),[]);
});
