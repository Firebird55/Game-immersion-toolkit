
import assert from 'node:assert/strict';import {startPreview} from './e2e-preview.mjs';import {chromium,firefox,webkit} from 'playwright';
// Exercise the actual built Windows distribution, not the dev dependency optimizer.
const preview=await startPreview('browser');
let browser;
const region={left:.1,top:.6,width:.8,height:.25},settings={beyond_region:{left:.10,top:.70,width:.80,height:.28},nte_region:{left:.10,top:.70,width:.80,height:.28},nte_picture_area:'window',nte_player_voice:'unconfigured',honkai3_picture_area:'window',honkai3_region:{left:.04,top:.72,width:.96,height:.24},preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,pragmata_region:region,cyberpunk_region:{left:.12,top:.59,width:.76,height:.37},cyberpunk_tip_region:{left:.10,top:.12,width:.70,height:.62},cyberpunk_capture_chatter:true,cyberpunk_v_voice:'unconfigured',wuwa_region:{left:.1,top:.64,width:.8,height:.32},wuwa_tip_region:{left:.58,top:.05,width:.40,height:.32},wuwa_capture_chatter:false,wuwa_cinematic_region:{left:.12,top:.2,width:.76,height:.43},wuwa_capture_cinematic:true,wuwa_rover_voice:'unconfigured',witcher3_region:{left:.08,top:.63,width:.84,height:.34},witcher3_tip_region:{left:.08,top:0,width:.76,height:.74},witcher3_capture_chatter:true,hito_auto_regions:true,process_names:[],window_title_contains:[],scan_interval_ms:250,stable_frames:2,fuzzy_threshold:82,auto_start:false,save_unmatched:false};
const line={id:1,created_at:new Date().toISOString(),session_id:'fixture',game:'zzz',source_ocr:'Hello',english:'Hello',chinese:'你好',text_id:'fixture',score:100,match_kind:'exact',channel:'dialogue',voiced:true,has_audio:false,favorite:false};
const comicLine={...line,id:6,text_id:'Comic_'+'a'.repeat(32),channel:'cinematic',voiced:false,english:'Keep the gate closed until tomorrow.',chinese:'请把门关到明天。'};
let includeComic=false,includeZzzStudy=false,readerRows=null,readerUpdates=null;
let fixtureCapture={running:false,phase:'stopped',message:'Fixture capture',active_game:'zzz',visible_text_ids:['fixture']};
const cyberpunkLine={...line,id:2,game:'cyberpunk',english:'Cyberpunk dialogue fixture',text_id:'cyberpunk-fixture',has_audio:true,audio_source:'original'};
const witcherLine={...cyberpunkLine,id:3,game:'witcher3',english:'Witcher dialogue fixture',text_id:'witcher-fixture'};
const nteLine={...cyberpunkLine,id:4,game:'nte',english:'',text_id:'nte-fixture',source_text:'ここで少し待っていてください。',source_language:'ja',source_locale:'ja',audio_locale:'ja',translation_locale:'zh-Hans',translation_text:'请在这里稍等。',chinese:'请在这里稍等。'};
const beyondLine={...cyberpunkLine,id:7,game:'beyond',favorite:true,text_id:'beyond-fixture',source_text:'Een volledige testzin.',source_language:'nl',source_locale:'nl',audio_locale:'nl',translation_locale:'zh-Hans',translation_text:'合成测试句子。',english:'',chinese:'合成测试句子。'};
const heavyRainLine={...beyondLine,id:8,game:'heavyrain',text_id:'heavyrain-fixture'};
const pragmataLine={...beyondLine,id:9,game:'pragmata',text_id:'pragmata-fixture',source_text:'Attendez ici un instant.',source_language:'fr',source_locale:'fr',audio_locale:'fr'};
const wuwaLine={...nteLine,id:10,game:'wuwa',text_id:'wuwa-fixture'};
const cyberpunkStudyLine={...cyberpunkLine,english:'',source_text:'Restez près de moi.',source_language:'fr',source_locale:'fr',audio_locale:'fr',translation_locale:'zh-Hans',translation_text:'待在我身边。',chinese:'待在我身边。'};
const witcherStudyLine={...witcherLine,english:'',source_text:'Bleib in meiner Nähe.',source_language:'de',source_locale:'de',audio_locale:'de',translation_locale:'zh-Hans',translation_text:'待在我身边。',chinese:'待在我身边。'};
const zzzStudyLine={...nteLine,id:11,game:'zzz',text_id:'GalGame_Japanese_fixture'};
settings.heavyrain_region={left:.05,top:.70,width:.90,height:.28};
const newRpgs=[['starrail','Honkai: Star Rail','Trailblazer voice'],['genshin','Genshin Impact','Traveler voice'],['endfield','Arknights: Endfield','Endministrator voice']];
const newRpgLines=Object.fromEntries(newRpgs.map(([game],i)=>[game,{...nteLine,game,id:20+i,text_id:game+'-fixture'}]));
const honkaiLine={...cyberpunkLine,id:5,game:'honkai3',english:'Honkai dialogue fixture',text_id:'honkai-fixture'};
const hitoHistory={...line,id:30,game:'hito',session_id:'archived',english:'Archived Hito history fixture',text_id:'archived-history'};
const hitoFavorite={...hitoHistory,id:31,english:'Archived Hito favorite fixture',text_id:'archived-favorite',favorite:true};
const mapStatus={ready:true,state:'ready',message:'fixture',entry_count:1};
const account={languages:['zh'],native_lang:'en',global:{translationLanguage:'en',interfaceLanguage:null,disableWordPopups:false,wordPopupOpenMode:'click',useCustomProficiencyColors:false,customProficiencyColors:{known:'green'}},languageSettings:{zh:{readingAid:'pinyin',script:'simplified',fontSize:'md',wordPopup:{tabs:['context','translation','definition','components','examples','similar','words','notes','grammar'].map(id=>({id,enabled:['context','translation','definition'].includes(id)})),openOn:'first'}},nl:{fontSize:'md'}}};
const token={start:0,end:2,word:'你好',pinyin:'nǐ hǎo',zhuyin:'ㄋㄧˇ ㄏㄠˇ',tones:[3,3],proficiency:0,meaning:'hello',entryId:1};
account.languages.push('ja');account.languageSettings.ja={fontSize:'md',effectiveTranslationLanguage:'zh-hans'};
account.languages.push('fr');account.languageSettings.fr={fontSize:'md',effectiveTranslationLanguage:'zh-hans'};
account.languages.push('de');account.languageSettings.de={fontSize:'md',effectiveTranslationLanguage:'zh-hans'};
let stateRevision=0;
const stateContext=()=>({runtime_id:'browser-fixture',state_version:stateRevision,account_generation:0});
function response(path,query,method,body){
 if(readerRows!==null){
  if(path==='/api/lines')return query.get('game')==='zzz'?readerRows:[];
  if(/^\/api\/lines\/6[0-9]+\/reading$/.test(path))return {text:readerRows.find(row=>row.id===Number(path.split('/')[3]))?.chinese??'',tokens:[token],grammar:[]};
 }
 if(path==='/api/lines'&&newRpgLines[query.get('game')])return [newRpgLines[query.get('game')]];
 if(/^\/api\/lines\/2[012]\/reading$/.test(path))return {text:nteLine.source_text,tokens:[],grammar:[]};
 if(path==='/api/snapshot')return {context:stateContext(),status:response('/api/status',query,'GET',{}),lines:['zzz','pragmata','cyberpunk','wuwa','witcher3','nte','beyond','heavyrain','starrail','genshin','endfield','hito'].flatMap(game=>response('/api/lines',new URLSearchParams({game}),'GET',{})),lexirise:response('/api/lexirise',query,'GET',{})};
 if(path==='/api/lines'&&query.get('game')==='hito')return [hitoHistory,hitoFavorite];
 if(path==='/api/lines'&&query.get('game')==='zzz'&&includeZzzStudy)return [zzzStudyLine];
 if(path==='/api/lines/11/reading')return {text:zzzStudyLine.source_text,tokens:[{start:0,end:3,word:'ここで',meaning:'在这里',proficiency:0}],grammar:[]};
 if(path==='/api/lines'&&query.get('game')==='witcher3')return [witcherStudyLine];
 if(path==='/api/lines/3/reading')return {text:witcherStudyLine.source_text,tokens:[{start:0,end:5,word:'Bleib',meaning:'留下',proficiency:0}],grammar:[]};
 if(path==='/api/lines'&&query.get('game')==='cyberpunk')return [cyberpunkStudyLine];
 if(path==='/api/lines/2/reading')return {text:cyberpunkStudyLine.source_text,tokens:[{start:0,end:6,word:'Restez',meaning:'留在',proficiency:0}],grammar:[]};
 if(path==='/api/lines'&&query.get('game')==='wuwa')return [wuwaLine];
 if(path==='/api/lines/10/reading')return {text:wuwaLine.source_text,tokens:[{start:0,end:3,word:'ここで',meaning:'在这里',proficiency:0}],grammar:[]};
 if(path==='/api/lines'&&query.get('game')==='pragmata')return [pragmataLine];
 if(path==='/api/lines/9/reading')return {text:pragmataLine.source_text,tokens:[{start:0,end:8,word:'Attendez',meaning:'等一下',proficiency:0}],grammar:[]};
 if(path==='/api/lines/4/reading')return {text:nteLine.source_text,tokens:[{start:0,end:3,word:'ここで',meaning:'在这里',proficiency:0}],grammar:[]};
 if(path==='/api/lines'&&query.get('game')==='heavyrain')return [heavyRainLine];
 if(path==='/api/lines/8/reading')return {text:heavyRainLine.source_text,tokens:[{start:0,end:3,word:'Een',meaning:'一个',proficiency:0}],grammar:[]};
 if(path==='/api/status')return {updates:readerUpdates,capture:fixtureCapture,textmaps:mapStatus,game_textmaps:{starrail:mapStatus,genshin:mapStatus,endfield:mapStatus,beyond:mapStatus,nte:mapStatus,honkai3:{...mapStatus,message:'165 verified lines; limited to catalog 4.7 content'},zzz:mapStatus,pragmata:mapStatus,cyberpunk:mapStatus,witcher3:mapStatus,wuwa:{...mapStatus,ready:true,state:'missing_voice',message:'Download the Chinese voice pack in Wuthering Waves'}},audio:{ready:false,message:'fixture'},settings,session:{id:'fixture',line_count:1,total_line_count:3}};
 if(path==='/api/settings'&&method==='PATCH'){Object.assign(settings,body);return settings;}
 if(path==='/api/lexirise')return {configured:true,account:'legacy',decks:{},sent:{}};
 if(path==='/api/lines')return query.get('game')==='zzz'?(includeComic?[comicLine,line]:[line]):query.get('game')==='cyberpunk'?[cyberpunkLine]:query.get('game')==='witcher3'?[witcherLine]:query.get('game')==='nte'?[nteLine]:query.get('game')==='honkai3'?[honkaiLine]:query.get('game')==='beyond'?[beyondLine]:[];
 if(path==='/api/favorites')return [];
 if(path==='/api/lexirise/settings'){if(method==='PATCH'){Object.assign(account.global,body.global??{});for(const[l,changes]of Object.entries(body.languageSettings??{}))Object.assign(account.languageSettings[l]??={},changes);}return account;}
 if(path==='/api/lines/7/reading')return {text:beyondLine.source_text,tokens:[{start:0,end:3,word:'Een',meaning:'一个',proficiency:0}],grammar:[]};
 if(/^\/api\/lines\/[12345]\/reading$/.test(path))return {text:'你好',tokens:[token],grammar:[]};
 if(path.endsWith('/lookup'))return {translations:[{meaning:'hello',partOfSpeech:['greeting'],examples:[]}],examples:[],dictionaries:[],alternateReadings:[],components:[]};
 if(path.endsWith('/characters'))return {characters:[]};
 if(path.endsWith('/examples'))return {examples:[]};
 if(path.endsWith('/similar'))return {suggestions:[],generated:true};
 if(path.endsWith('/context'))return body.question==='Simulate busy AI'?{detail:'Lexirise returned no answer. Please ask again.'}:{meaning:method==='POST'?'The greeting is polite in this sentence.':'A greeting',conciseMeaning:'hello',reading:'nǐ hǎo'};
 return {};
}
try{
 for(const[name,engine]of [['chromium',chromium],['firefox',firefox],['webkit',webkit]]){browser=await preview.launchBrowser(engine,{headless:true});
 const sizes=process.argv.includes('--reading-settings')?[[1920,1080,1],[390,844,1],[320,568,1],[768,1024,1.25]]:process.argv.includes('--game-support')?[[320,568,1],[3840,2160,1],[3840,2160,1.5],[3840,2160,2]]:[[1920,1080,1],[1920,1080,1.25],[1280,720,1.5],[1280,720,2],[390,844,1],[320,568,1],[568,320,1],[900,720,1],[768,1024,1.25],[3840,2160,1],[3840,2160,1.5],[3840,2160,2]];
 for(const[pw,ph,zoom]of sizes){
 if(name==='webkit'&&!([390,320,768,568].includes(pw)))continue;
 const width=Math.floor(pw/zoom),height=Math.floor(ph/zoom),context=await browser.newContext({viewport:{width,height},deviceScaleFactor:zoom}),page=await context.newPage(),writes=[],localWrites=[];
 includeComic=false;includeZzzStudy=false;settings.zzz_proxy_voice='unconfigured';
 for(const[game]of newRpgs){settings[game+'_region']={left:.10,top:.70,width:.80,height:.28};settings[game+'_player_voice']='unconfigured';}
 fixtureCapture={running:false,phase:'stopped',message:'Fixture capture',active_game:'zzz',visible_text_ids:['fixture']};
 let fixtureSocket;
 await page.routeWebSocket('ws://127.0.0.1:8766/api/ws',socket=>{fixtureSocket=socket;});
 settings.cyberpunk_tip_region.left=.10; settings.wuwa_cinematic_region.left=.12;
 settings.nte_region.left=.10; settings.honkai3_region.left=.04;settings.nte_picture_area='window';settings.nte_player_voice='unconfigured';settings.honkai3_picture_area='window';
 settings.cyberpunk_v_voice='unconfigured';
 settings.wuwa_rover_voice='unconfigured';
 await page.addInitScript(()=>localStorage.setItem('proxy-transcript-reading-mode','lexirise'));
 await page.route('http://127.0.0.1:8766/**',async route=>{const req=route.request(),url=new URL(req.url());const body=req.postData()?JSON.parse(req.postData()):{};
 if(req.method()==='PATCH'&&url.pathname==='/api/lexirise/settings')writes.push(body);
 if(req.method()!=='GET'&&req.method()!=='OPTIONS')localWrites.push({path:url.pathname,body});
 await route.fulfill({status:body.question==='Simulate busy AI'?503:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type,X-Proxy-Transcript','Access-Control-Allow-Methods':'GET,POST,PATCH,OPTIONS'},body:JSON.stringify(response(url.pathname,url.searchParams,req.method(),body))});});
 if(!process.argv.includes('--game-support')&&!process.argv.includes('--reading-settings')){
  readerRows=Array.from({length:31},(_,i)=>({...line,id:6000+i,text_id:'reader-'+i,
   english:'We have checked the other exits. Please wait here while we get everything ready.',
   chinese:'你好，今天我们一起去看看。路上还有很多有趣的事情，慢慢来就好。',favorite:i%5===0}));
  await page.goto(preview.origin);await page.locator('.transcript-line .reading-text').first().waitFor();
  const current=page.locator('.current-line'),history=page.locator('.transcript-line');
  assert.equal(await history.count(),10,'History has ten complete, scrollable captions');
  for(const selector of ['.current-english','.current-chinese']){
   const size=await current.locator(selector).evaluate(el=>getComputedStyle(el).fontSize);
   assert.equal(await history.first().locator(selector).evaluate(el=>getComputedStyle(el).fontSize),size,'Current/history typography is equal');
   assert(parseFloat(size)>=27,'Default text stays large at every width');
  }
  assert.equal(await page.locator('.line-list').evaluate(el=>getComputedStyle(el).overflowY),'visible','History uses document scrolling');
  assert.equal(await page.locator('.status-strip,.transcript-tabs,.transcript-heading,.column-labels').count(),0,'Obsolete dashboard chrome is removed');
  const before=await current.boundingBox();
  const publishUpdates=state=>{readerUpdates={state,message:'Checking installed language files',progress:state==='updating'?.4:null,items:[]};stateRevision++;fixtureSocket.send(JSON.stringify({type:'update_status',updates:readerUpdates,context:stateContext()}));};
  for(const state of ['checking','updating','retrying','error','ready']){
   publishUpdates(state);
   await page.getByLabel('Game language updates',{exact:true}).click();
   await page.locator('.update-popover').waitFor();
   assert.equal((await current.boundingBox()).y,before.y,'Game updates never displace the caption');
   await page.getByLabel('Game language updates',{exact:true}).click();
  }
  await page.screenshot({path:`${preview.output}/${name}-reader-${pw}-${ph}-${zoom}.png`});
  await page.getByRole('button',{name:'Favorites',exact:true}).click();
  assert.equal(await history.count(),7,'Favorites includes saved lines from the current session');
  assert.equal(await page.getByRole('button',{name:'History',exact:true}).getAttribute('aria-pressed'),'true');
  await page.getByRole('button',{name:'History',exact:true}).click();
  await page.getByRole('button',{name:'Previous 10',exact:true}).click();
  assert.match(await page.locator('.history-pagination').textContent(),/11–20/);
  await page.getByRole('button',{name:'Newer 10',exact:true}).click();
  if(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight+100)){
   await page.mouse.wheel(0,600);await page.waitForFunction(()=>scrollY>100);
   await page.locator('.reader-stream.is-scrolled').waitFor();
  }
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Reader has no horizontal overflow');
  // A caption taller than the viewport must be scrollable, not permanently pinned.
  readerRows=readerRows.map(row=>row.id===6030?{...row,english:row.english.repeat(80),chinese:row.chinese.repeat(80)}:row);
  await page.reload();await current.locator('.current-english').waitFor();
  await page.waitForFunction(()=>!document.querySelector('.reader-stream').classList.contains('can-pin'));
  await page.getByRole('button',{name:'Previous 10',exact:true}).click();
  assert.match(await page.locator('.history-pagination').textContent(),/11–20/,'Long current captions do not prevent history access');
  readerRows=[];await page.reload();await page.getByText('Matched game dialogue appears here.',{exact:true}).waitFor();
  await page.getByRole('heading',{name:'Earlier lines',exact:true}).waitFor();
  console.log(`${name}: reader ${width}x${height} / ${zoom} passed`);
  readerRows=null;readerUpdates=null;
 }
 if(name==='webkit'||process.argv.includes('--reader-layout')){await context.close();continue;}
 await page.goto(preview.origin);await page.locator('.reading-hanzi').first().click();await page.locator('.word-sheet').waitFor();
 await page.getByRole('tab',{name:'Context',exact:true}).waitFor();
 assert.deepEqual(await page.locator('.word-tabs').getByRole('tab').allTextContents(),['Context','Translation','Definition'],'Toolkit reads the account popup order and enable flags');
 assert.equal(await page.locator('.word-tabs').getByRole('tab',{selected:true}).textContent(),'Context','Toolkit opens the first account tab');
 await page.getByRole('textbox',{name:'Ask Lexirise about this word',exact:true}).fill('Is this polite?');
 await page.getByRole('button',{name:'Ask Lexirise',exact:true}).click();
 await page.locator('.word-context-answer').filter({hasText:'The greeting is polite in this sentence.'}).waitFor();
 assert.deepEqual(localWrites.at(-1),{path:'/api/lines/1/reading/context',body:{start:0,question:'Is this polite?'}});
 await page.getByRole('textbox',{name:'Ask Lexirise about this word',exact:true}).fill('Simulate busy AI');
 await page.getByRole('textbox',{name:'Ask Lexirise about this word',exact:true}).press('Enter');
 await page.getByRole('alert').filter({hasText:'Lexirise returned no answer. Please ask again.'}).waitFor();
 await page.getByRole('textbox',{name:'Ask Lexirise about this word',exact:true}).fill('Is this polite?');
 await page.getByRole('textbox',{name:'Ask Lexirise about this word',exact:true}).press('Enter');
 await page.getByRole('alert').filter({hasText:'Lexirise returned no answer. Please ask again.'}).waitFor({state:'hidden'});
 await page.getByRole('tab',{name:'Translation',exact:true}).click();assert.match(await page.locator('.word-sheet-body').textContent(),/Hello/);
 await page.getByRole('tab',{name:'Definition',exact:true}).click();
 if(name==='chromium'&&zoom===1&&[1920,390].includes(pw))await page.locator('.word-sheet').screenshot({path:`${preview.output}/account-popup-${pw}.png`});
 await page.locator('.word-sheet').evaluate(n=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 let b=await page.locator('.word-sheet').boundingBox();assert(b&&b.x>=-1&&b.y>=-1&&b.x+b.width<=width+1&&b.y+b.height<=height+1,name+' toolkit lookup fits '+JSON.stringify(b));
 const expectedWidth=Math.min(width<=560?340:400,width-32),heightCap=width<=560?Math.min(360,height*.6):320;
 assert(Math.abs(b.width-expectedWidth)<=1,name+' toolkit shares compact lookup width');
 assert(b.height<=heightCap+1,name+' toolkit shares compact lookup height');
 assert.equal(await page.locator('.word-sheet-body').evaluate(n=>getComputedStyle(n).fontSize),'13px','Toolkit shares compact lookup typography');
 assert.equal(await page.locator('.word-sheet').evaluate(n=>n.getRootNode()===document),true,'Toolkit portal stays in document');
 await page.keyboard.press('Escape');await page.getByRole('button',{name:'Lexirise reading options',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Lexirise reading options'});await dialog.waitFor();await page.getByLabel('Text size',{exact:true}).waitFor();
 assert.equal(await dialog.getByText('5 · neutral',{exact:true}).count(),1);assert.equal(await dialog.getByText('Migaku tone palette').count(),0);
 await page.getByLabel('Pronunciation readings',{exact:true}).selectOption('all');
 await page.getByLabel('Tone 1 color',{exact:true}).fill('#123456');
 assert.equal(await page.getByLabel('Tone 1 color',{exact:true}).inputValue(),'#123456');
 await page.getByRole('button',{name:'Reset colors',exact:true}).click();assert.equal(await page.getByLabel('Tone 1 color',{exact:true}).inputValue(),'#ff526b');
 assert.equal(writes.length,0,'Reading edits never write account settings');
 if(name==='chromium'&&width===1920&&zoom===1)await dialog.screenshot({path:`${preview.output}/shared-reading-options.png`});
 b=await dialog.boundingBox();assert(b&&b.x>=0&&b.y>=0&&b.x+b.width<=width+1&&b.y+b.height<=height+1,name+' toolkit settings fits '+JSON.stringify(b));
 await page.keyboard.press('Escape');await page.getByRole('button',{name:'Account settings',exact:true}).click();await page.getByRole('button',{name:'Study languages, dictionaries and account preferences',exact:true}).click();await page.getByLabel('Edit account language').waitFor();
 await page.getByLabel('Edit account language').selectOption('ja');assert.equal(await page.locator('.reading-text').first().getAttribute('lang'),'zh','Editing Japanese account settings never reinterprets Chinese transcript');
 assert.equal(writes.length,0);await page.keyboard.press('Escape');
 if(pw===1920&&zoom===1){
  await page.getByRole('button',{name:'Account settings',exact:true}).click();await page.getByRole('button',{name:'Study languages, dictionaries and account preferences',exact:true}).click();await page.getByLabel('Edit account language').waitFor();
  await page.getByLabel('Edit account language').selectOption('zh');
  const presets=page.getByLabel('toneColorPreset',{exact:true});
  const options=await presets.locator('option').evaluateAll(nodes=>nodes.map(node=>node.value));
  assert(options.includes('mdbg')&&options.includes('colorblind'),'Current account presets are imported from shared source');
  const palette=await presets.inputValue()==='colorblind'?'mdbg':'colorblind';
  await presets.selectOption(palette);assert.equal(writes.length,0,'Palette selection does not write account settings');
  await page.getByRole('button',{name:'Save to Lexirise',exact:true}).click();await page.getByText('Saved to Lexirise.',{exact:true}).waitFor();
  assert.deepEqual(writes.pop(),{languageSettings:{zh:{toneColorPreset:palette}}},'Explicit save sends only the requested account palette');
  await page.keyboard.press('Escape');
 }
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' toolkit layout has no horizontal overflow at '+width);
 if(process.argv.includes('--reading-settings')){console.log(name+': reading settings '+width+'x'+height+' passed');await context.close();continue;}
 await page.getByRole('button',{name:'Capture setup',exact:true}).click();const capture=page.getByRole('dialog',{name:'Capture setup'});await capture.waitFor();b=await capture.boundingBox();assert(b&&b.x>=0&&b.x+b.width<=width+1,'Capture setup fits');
 await page.keyboard.press('Escape');await capture.waitFor({state:'hidden'});
 await page.locator('.game-library > summary').click();
 const games=page.getByRole('navigation',{name:'Game transcript'});
 await page.getByLabel('Target language',{exact:true}).selectOption('ja');
 assert.equal(await games.getByRole('button',{name:'Where Winds Meet',exact:true}).count(),0,'Unverified WWM integration stays excluded');
 await games.getByRole('button',{name:'Cyberpunk 2077',exact:true}).click();
 await page.locator('.current-line.game-cyberpunk').waitFor();
 await page.locator('.current-line').getByText(cyberpunkStudyLine.source_text,{exact:true}).waitFor();
 assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'fr','Cyberpunk uses its selected French study language');
 assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),true,'Cyberpunk uses original audio');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Cyberpunk tabs fit the viewport');
 if(pw===3840)await page.screenshot({path:`${preview.output}/${name}-cyberpunk-4k-${zoom}.png`});
 await page.getByRole('button',{name:'Capture setup',exact:true}).click();await capture.waitFor();
 assert.equal(await capture.getByRole('button',{name:'Top-right tips',exact:true}).count(),0,'Cyberpunk keeps tips separate from NPC chatter');
 await capture.getByRole('button',{name:'NPC chatter',exact:true}).click();
 assert.equal(await capture.locator('input[type=range]').first().inputValue(),'10');
 await capture.locator('input[type=range]').first().fill('12');
 await capture.getByRole('button',{name:'Dialogue',exact:true}).click();
 assert.equal(await capture.getByLabel('V voice').inputValue(),'unconfigured');
 await capture.getByLabel('V voice').selectOption('male');
 await capture.getByRole('button',{name:'Update TextMaps',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.setup-actions button')?.textContent.includes('Update TextMaps'));
 assert(localWrites.some(w=>w.path==='/api/games/cyberpunk/update'),'Refresh selects Cyberpunk assets');
 await capture.getByRole('button',{name:'Save capture settings',exact:true}).click();await capture.waitFor({state:'hidden'});
 const saved=localWrites.find(w=>w.path==='/api/settings');
 assert.equal(saved.body.cyberpunk_tip_region.left,.12,'NPC calibration saved independently');assert.equal(saved.body.cyberpunk_v_voice,'male');assert.deepEqual(saved.body.cyberpunk_region,{left:.12,top:.59,width:.76,height:.37});
 assert.deepEqual(saved.body.region,region,'Saving Cyberpunk preserves ZZZ calibration');assert.equal(writes.length,0,'Game setup never changes account settings');
 for(const[game,label,left]of [['beyond','BEYOND: Two Souls','10'],['heavyrain','HEAVY RAIN','5']]){
 await games.getByRole('button',{name:label,exact:true}).click();
 await page.locator(`.current-line.game-${game}`).waitFor();
 await page.locator('.current-line').getByText(beyondLine.source_text,{exact:true}).waitFor();
 assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'nl',label+' uses Dutch study text');
 await page.getByRole('button',{name:'Favorites',exact:true}).click();
 assert.equal(await page.locator('.transcript-line .current-chinese').getAttribute('lang'),'nl','Saved source uses its actual locale');
 assert.equal(await page.locator('.transcript-line .current-english').getAttribute('lang'),'zh-Hans','Saved translation uses its actual locale');
 await page.getByRole('button',{name:'History',exact:true}).click();
 assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),true,label+' uses original Dutch audio');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),label+' fits the viewport');
 await page.getByRole('button',{name:'Capture setup',exact:true}).click();await capture.waitFor();
 assert.equal(await capture.locator('input[type=range]').first().inputValue(),left);
 await page.keyboard.press('Escape');await capture.waitFor({state:'hidden'});
 }
 for(const[game,label]of [['wuwa','Wuthering Waves'],['witcher3','The Witcher 3: Wild Hunt']]){
  await games.getByRole('button',{name:label,exact:true}).click();await page.locator(`.current-line.game-${game}`).waitFor();
  if(game==='witcher3'){
   await page.locator('.current-line').getByText(witcherStudyLine.source_text,{exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),true,'Witcher uses original audio');
   assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'de','Witcher uses the selected German study language');
  }else{
   await page.getByText('Download the Chinese voice pack in Wuthering Waves',{exact:true}).waitFor();
   assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'ja','Wuthering retains the selected Japanese study language');
   await page.locator('.current-line').getByText(wuwaLine.source_text,{exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),true,'Previously captured original Japanese audio remains playable');
  }
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),label+' tabs fit');
  if(pw===3840)await page.screenshot({path:`${preview.output}/${name}-${game}-4k-${zoom}.png`});
  await page.getByRole('button',{name:'Capture setup',exact:true}).click();await capture.waitFor();
  await capture.getByRole('button',{name:game==='wuwa'?'Top-right tips':'NPC chatter',exact:true}).click();
  assert.equal(await capture.locator('input[type=range]').first().inputValue(),game==='wuwa'?'58':'8');
  if(game==='wuwa'){
   await capture.getByRole('button',{name:'Centered story cards',exact:true}).click();
   assert.equal(await capture.locator('input[type=range]').first().inputValue(),'12');
   await capture.locator('input[type=range]').first().fill('14');
  }
  await capture.getByRole('button',{name:'Dialogue',exact:true}).click();
  if(game==='wuwa'){assert.equal(await capture.getByLabel('Rover voice').inputValue(),'unconfigured');await capture.getByLabel('Rover voice').selectOption('female');}
  else assert.equal(await capture.getByLabel('V voice').count(),0,'Witcher has no Cyberpunk voice selector');
  await capture.getByRole('button',{name:'Update TextMaps',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.setup-actions button')?.textContent.includes('Update TextMaps'));
  assert(localWrites.some(w=>w.path===`/api/games/${game}/update`),label+' refresh selects its own assets');
  await capture.getByRole('button',{name:'Save capture settings',exact:true}).click();await capture.waitFor({state:'hidden'});
  const last=localWrites.filter(w=>w.path==='/api/settings').at(-1).body;
  if(game==='wuwa'){assert.equal(last.wuwa_rover_voice,'female','Rover choice survives asset refresh');assert.equal(last.wuwa_cinematic_region.left,.14,'Story card calibration is independent');assert.equal(last.wuwa_capture_chatter,false,'Unverified top-right channel stays off');}
  assert.deepEqual(last.cyberpunk_region,saved.body.cyberpunk_region,'Game calibration is independent');assert.equal(last.cyberpunk_v_voice,'male');
  assert.deepEqual(last.region,region,'New games preserve ZZZ calibration');assert.equal(writes.length,0,'New games never change account settings');
 }
 for(const[game,label,left]of [['nte','Neverness to Everness','10'],...newRpgs.map(([game,label])=>[game,label,'10'])]){
  await games.getByRole('button',{name:label,exact:true}).click();await page.locator(`.current-line.game-${game}`).waitFor();
  assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),true,label+' original voice is playable');
  assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'ja',label+' uses its selected Japanese study language');
  await page.locator('.current-line').getByText(nteLine.source_text,{exact:true}).waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Game tabs fit');
  await page.getByRole('button',{name:'Capture setup',exact:true}).click();await capture.waitFor();
  assert.equal(await capture.getByRole('button',{name:'NPC chatter',exact:true}).count(),0);
  assert.equal(await capture.getByRole('button',{name:'Top-right tips',exact:true}).count(),0);
  assert.equal(await capture.locator('input[type=range]').first().inputValue(),left,'Independent default crop');
  if(game==='nte')await capture.getByRole('button',{name:'Use tested dialogue crop',exact:true}).click();
  assert.equal(await capture.locator('input[type=range]').first().inputValue(),left);
  if(game==='nte')await capture.getByLabel('Game picture area',{exact:true}).selectOption('16:9');
  const voiceLabel=game==='nte'?'Zero voice':newRpgs.find(([id])=>id===game)[2];
  await capture.getByLabel(voiceLabel,{exact:true}).selectOption('female');
  await capture.locator('input[type=range]').first().fill('11');
  await capture.getByRole('button',{name:'Update TextMaps',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.setup-actions button')?.textContent.includes('Update TextMaps'));
  assert(localWrites.some(w=>w.path===`/api/games/${game}/update`),'Correct game updater');
  await capture.getByRole('button',{name:'Save capture settings',exact:true}).click();await capture.waitFor({state:'hidden'});
  const savedGame=localWrites.filter(w=>w.path==='/api/settings').at(-1).body;
  if(game==='nte')assert.equal(savedGame.nte_picture_area,'16:9','Picture area persists independently');
  assert.equal(savedGame[game+'_player_voice'],'female','Explicit player voice survives game refresh');
  assert.equal(savedGame.nte_player_voice,'female','Explicit Zero voice survives other game calibration');
  assert.equal(savedGame[`${game}_region`].left,.11,'New crop persists');assert.deepEqual(savedGame.region,region,'ZZZ crop stays independent');
  assert.equal(writes.length,0,'New games cause no account writes');
  if(name==='chromium'&&pw===320)await page.screenshot({path:`${preview.output}/${game}-mobile.png`});
 }
 await games.getByRole('button',{name:'PRAGMATA',exact:true}).click();await page.locator('.current-line.game-pragmata').waitFor();
 assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'fr','PRAGMATA retains the selected French study language');
 await page.locator('.current-line').getByText(pragmataLine.source_text,{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),true,'Localized PRAGMATA original voice is playable');
 assert.equal(writes.length,0,'Reading a PRAGMATA locale never changes account settings');
 assert.equal(await games.getByRole('button',{name:"Hito's World",exact:true}).count(),0,'Archived Hito is absent');
 assert.equal(await games.getByRole('button',{name:'Honkai Impact 3rd',exact:true}).count(),0,'Archived game is absent');
 if(zoom===1&&[1920,320].includes(pw)){
  const beforeArchive=localWrites.length;
  await page.getByLabel('Archived game history',{exact:true}).selectOption('hito');
  await page.locator('.line-list').getByText(hitoHistory.english,{exact:true}).waitFor();
  await page.locator('.line-list').getByText(hitoFavorite.english,{exact:true}).waitFor();
  assert.equal(await page.locator('.current-line.game-hito').count(),0,'Archive has no live capture panel');
  assert(await page.getByRole('button',{name:'Capture setup',exact:true}).isDisabled());
  assert(await page.locator('.capture-toggle').isDisabled());
  assert.equal(await page.getByRole('link',{name:'Share transcript to another device',exact:true}).count(),0);
  await page.getByRole('button',{name:'Favorites',exact:true}).click();
  assert.equal(await page.locator('.line-list .transcript-line').count(),1,'Archived favorites remain accessible');
  await page.locator('.line-list').getByText(hitoFavorite.english,{exact:true}).waitFor();
  assert.equal(localWrites.length,beforeArchive,'Viewing retired history does not write or refresh game assets');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Archived history fits');
  await page.getByLabel('Archived game history',{exact:true}).selectOption('');
 }
 await games.getByRole('button',{name:'Zenless Zone Zero',exact:true}).click();await page.locator('.current-line.game-zzz').waitFor();
 if(zoom===1&&pw===1920){for(const[w,h]of [[320,568],[1280,720],[568,320],[900,720]]){
  await page.setViewportSize({width:w,height:h});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Resize does not overflow');
  await page.getByRole('button',{name:'Lexirise reading options',exact:true}).click();await dialog.waitFor();const box=await dialog.boundingBox();assert(box&&box.x>=0&&box.y>=0&&box.x+box.width<=w+1&&box.y+box.height<=h+1,'Resized toolkit settings fit');await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
 }}
 includeComic=true;
 fixtureCapture={...fixtureCapture,running:true,phase:'matched',visible_text_ids:[comicLine.text_id]};
 stateRevision++;fixtureSocket.send(JSON.stringify({context:stateContext(),type:'line',line:comicLine}));
 stateRevision++;fixtureSocket.send(JSON.stringify({context:stateContext(),type:'capture_status',capture:fixtureCapture}));
 await page.locator('.current-line').getByText(comicLine.english,{exact:true}).waitFor();
 assert.match(await page.locator('.current-line .match-label').textContent(),/Game-file text/,'Text-only comic has no misleading voice check');
 assert(await page.getByRole('button',{name:'Original voice unavailable',exact:true}).isDisabled(),'Unmapped comic never offers unrelated audio');
 fixtureCapture={...fixtureCapture,phase:'waiting',visible_text_ids:[]};
 stateRevision++;fixtureSocket.send(JSON.stringify({context:stateContext(),type:'capture_status',capture:fixtureCapture}));
 await page.locator('.current-line').getByText(comicLine.english,{exact:true}).waitFor();
 assert.equal(await page.locator('.current-empty').count(),0,'A disappeared subtitle remains readable until its replacement');
 await page.reload();
 await page.locator('.current-line').getByText(comicLine.english,{exact:true}).waitFor();
 assert.equal(await page.getByText(comicLine.english,{exact:true}).count(),1,'Retained current line is not duplicated in history after reload');
 includeZzzStudy=true;
 fixtureCapture={...fixtureCapture,phase:'matched',visible_text_ids:[zzzStudyLine.text_id]};
 await page.reload();await page.locator('.current-line').getByText(zzzStudyLine.source_text,{exact:true}).waitFor();
 assert.equal(await page.locator('.current-line').getByText(comicLine.english,{exact:true}).count(),0,'The next confirmed subtitle replaces the retained one');
 assert.equal(await page.locator('.current-line .reading-text').getAttribute('lang'),'ja','ZZZ follows the selected Japanese study language');
 assert(await page.getByRole('button',{name:'Play current voice line',exact:true}).isEnabled(),'ZZZ original Japanese audio is playable');
 await page.getByRole('button',{name:'Capture setup',exact:true}).click();await capture.waitFor();
 await capture.getByLabel('Proxy voice',{exact:true}).selectOption('female');
 await capture.getByRole('button',{name:'Save capture settings',exact:true}).click();await capture.waitFor({state:'hidden'});
 assert.equal(localWrites.filter(w=>w.path==='/api/settings').at(-1).body.zzz_proxy_voice,'female','Explicit Belle voice choice is saved locally');
 assert.equal(writes.length,0,'ZZZ study and Proxy choices do not change account settings');
 console.log(name+': toolkit '+width+'x'+height+' zoom/DPR '+zoom+' and text-only comic passed');await context.close();
 }await browser.close();browser=null;}
}finally{
 await preview.stop();
}
