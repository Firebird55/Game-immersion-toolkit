// Exercise the shipped reader with authored dialogue and mocked account requests.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import * as engines from 'playwright';
import {mime} from './mobile-assets.mjs';
import {TONE} from '../tests/mobile-media-fixtures.mjs';

const root=resolve(process.env.MOBILE_PREVIEW_DIR??'public/mobile-capture');
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost'),name=url.pathname.slice(1)||'index.html';
 if(name==='shadow-reader-fixture.mjs'){res.setHeader('Content-Type','text/javascript');res.end(`const reader=document.getElementById('reader-root'),host=document.createElement('div');reader.replaceWith(host);const shadow=host.attachShadow({mode:'open'});for(const link of document.querySelectorAll('link[rel=stylesheet]'))shadow.append(link.cloneNode());shadow.append(reader);const get=document.getElementById.bind(document);document.getElementById=id=>id==='reader-root'?reader:get(id);await import('./companion.js');`);return;}
 if(name==='index.html'&&url.searchParams.has('shadow-reader')){res.setHeader('Content-Type','text/html');res.end(readFileSync(resolve(root,name),'utf8').replace('src="./companion.js"','src="./shadow-reader-fixture.mjs"'));return;}
 if(name.includes('..')){res.writeHead(404).end();return;}
 try{res.setHeader('Content-Type',mime(name));res.end(readFileSync(resolve(root,name)));}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
mkdirSync('output/playwright',{recursive:true});
const segments=[['你好','nǐhǎo','hello'],['旅行者','lǚxíngzhě','traveler'],['欢迎','huānyíng','welcome'],['来到','láidào','arrive'],['这里','zhèlǐ','here']];
const chinese='你好，旅行者。欢迎来到这里。';
const rows=Array.from({length:3},(_,i)=>({source:'pc-layout-fixture',game:'zzz',id:i+1,createdAt:1700000000000+i*1000,chinese,english:'Hello, traveler. Welcome to this place.',speakerChinese:'向导',speakerEnglish:'Guide',audio:false}));
let browser;
try{
 for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
  browser=await engines[name].launch({headless:true});
  const context=await browser.newContext({locale:'en-US',viewport:{width:390,height:844},hasTouch:true,deviceScaleFactor:3,serviceWorkers:'block'});
  // A cancelled transport may settle later (including intercepted WebKit
  // requests). Exercise that boundary explicitly instead of relying on abort.
  await context.addInitScript(()=>{
   // Deliver a real IndexedDB read after a live PC event. The page must queue
   // that event until history restoration finishes rather than overwrite it.
   const nativeGet=IDBObjectStore.prototype.get;
   IDBObjectStore.prototype.get=function(key){
    const request=nativeGet.call(this,key);
    if(key!=='pc-history'||window.historyRestoreHeld||location.search.includes('shadow-reader'))return request;
    window.historyRestoreHeld=true;
    return new Proxy(request,{
     get(target,key){const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;},
     set(target,key,value){if(key==='onsuccess'){target.onsuccess=event=>{window.releaseHistoryRestore=()=>value.call(target,event);};return true;}return Reflect.set(target,key,value,target);}
    });
   };
   const nativeFetch=window.fetch.bind(window);
   window.fetch=(input,options)=>{
    if(window.ignoreNextDeckAbort&&typeof options?.body==='string'&&JSON.parse(options.body).path?.startsWith('/v1/decks?')){
     window.ignoreNextDeckAbort=false;const {signal,...retained}=options;return nativeFetch(input,retained);
    }
    return nativeFetch(input,options);
   };
  });
  const page=await context.newPage(),errors=[],requests=[],failedRequests=[];
  page.on('requestfailed',request=>failedRequests.push(new URL(request.url()).pathname+': '+request.failure()?.errorText));
  let deferredResizes=0,holdLookup=false,releaseLookup; const analysisAccounts=[];let dutchTarget='zh-hans',holdDecks=false,releaseDecks,failInitialSettings=true,heldAction=null,releaseAction;
  page.on('pageerror',e=>{
   // WebKit can defer one observer delivery while the anchored library mounts
   // and asynchronous dictionary data resizes the phone sheet. Require stable
   // geometry below and reject repeated deliveries or any application error.
   if(name==='webkit'&&e.message==='ResizeObserver loop completed with undelivered notifications.')deferredResizes++;
   else errors.push(e.message);
  });
  await context.route('https://game-immersion-lexirise.boazbrak.workers.dev/**',route=>{
   const request=route.request(),headers={'Access-Control-Allow-Origin':'*','Cache-Control':'no-store'};
   if(request.method()==='OPTIONS')return route.fulfill({status:204,headers:{...headers,'Access-Control-Allow-Headers':'Authorization, Content-Type'}});
   const body=request.postDataJSON();requests.push(body);if(body.path==='/v1/analyze/text')analysisAccounts.push(request.headers().authorization==='Bearer mock-layout-key-second'?'second':'first');
   if(heldAction&&body.method===heldAction.method&&body.path.startsWith(heldAction.path)){const result=heldAction.result;heldAction=null;releaseAction=()=>route.fulfill({...result,headers}).catch(()=>{});return;}
   let data;
   if(body.path==='/v1/settings'&&failInitialSettings){failInitialSettings=false;return route.fulfill({status:503,json:{detail:'Synthetic settings outage'},headers});}
   if(body.path==='/v1/settings')data={languages:['zh','nl','de'],global:{effectiveTranslationLanguage:'en'},languageSettings:{zh:{},nl:{effectiveTranslationLanguage:dutchTarget,inlineGlossMode:'always'},de:{effectiveTranslationLanguage:'nl'}}};
   else if(body.path==='/v1/analyze/text'&&['nl','de'].includes(body.payload.language))data={occurrences:[{word:'Een',charStart:0,charEnd:3,isWordLike:true,entryId:99}],entryMetaById:{99:{gloss:'一个'}},stateByEntryId:{}};
   else if(body.path==='/v1/analyze/text')data={occurrences:segments.map(([word,transliteration],i)=>({word,transliteration,charStart:chinese.indexOf(word),charEnd:chinese.indexOf(word)+word.length,isWordLike:true,entryId:i+1,tones:[3,3]})),entryMetaById:Object.fromEntries(segments.map((s,i)=>[i+1,{gloss:s[2]}])),stateByEntryId:{}};
   else if(body.path==='/v1/dictionary/lookup')data={word:body.payload.text,translations:[{target_lang:'en',translation:'hello; a greeting to welcome someone',part_of_speech:['interjection']},{target_lang:'zh-hans',translation:'荷兰语词义',part_of_speech:[]},{target_lang:'nl',translation:'Nederlandse betekenis',part_of_speech:[]}],supplementalEntries:[{dictionary_name:'Fixture dictionary',headword:body.payload.text,html:'<ul>'+Array.from({length:24},(_,i)=>'<li>Authored dictionary explanation '+(i+1)+' with enough detail to exercise scrolling.</li>').join('')+'</ul>'}],characterInfo:{pinyin:['nǐ'],gloss:'you'}};
   else if(body.path==='/v1/vocabulary')data={item:{id:77}};
   else if(/^\/v1\/decks\/\d+\/items$/.test(body.path))data={added_count:1};
   else if(body.path==='/v1/me')data={user:{id:1}};
   else if(body.path.startsWith('/v1/decks?'))data={decks:[{id:42,title:'Previous Dutch deck',owner_user_id:1,language:'nl',unit_type:'sentence',deck_type:'snapshot'}]};
   else if(body.path==='/v1/analyze/context')data={meaning:'A friendly greeting used when meeting a traveler.'};
   else throw Error('Unexpected mock account request: '+body.path);
   if(body.path==='/v1/dictionary/lookup'&&holdLookup){holdLookup=false;releaseLookup=()=>route.fulfill({json:{...data,translations:[{target_lang:'en',translation:'FIRST ACCOUNT PENDING',part_of_speech:[]}]},headers}).catch(()=>{});return;}
   if(body.path.startsWith('/v1/decks?')&&holdDecks){holdDecks=false;releaseDecks=()=>route.fulfill({json:data,headers}).catch(()=>{});return;}
   return route.fulfill({json:data,headers});
  });
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.getByRole('heading',{name:'Game immersion toolkit',exact:true}).waitFor().catch(async error=>{throw Error('Reader failed to mount: '+JSON.stringify({errors,requests:failedRequests,body:(await page.locator('body').innerText()).slice(0,2000)}),{cause:error});});
  await page.getByRole('button',{name:'Settings',exact:true}).click();await page.selectOption('#source','pc');
  await page.waitForFunction(()=>typeof window.releaseHistoryRestore==='function');
  await page.evaluate(rows=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'page'},rows}})),rows);
  await page.evaluate(()=>window.releaseHistoryRestore());
  await page.getByRole('button',{name:'Play',exact:true}).click();
  // Live sessions collapse setup; leaving Reader makes configuration accessible.
  const stream=detail=>page.evaluate(detail=>window.dispatchEvent(new CustomEvent('mobile-stream',{detail})),detail);
  await stream({state:'connected',live:false});
  await page.waitForFunction(()=>document.body.classList.contains('reader-active'));
  assert.equal(await page.locator('.device-bar').isVisible(),false);
  assert.equal(await page.locator('.public-guide').isVisible(),false);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  assert(await page.locator('.device-bar').isVisible(),'Settings restores setup while playing');
  await page.selectOption('#source','mobile');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await stream({state:'connected',live:true});
  assert(await page.getByRole('heading',{name:'1. Open your library'}).isVisible(),'Mobile setup remains until OCR starts');
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('mobile-ocr-state',{detail:{scanning:true}})));
  await page.waitForFunction(()=>document.body.classList.contains('reader-active'));
  assert.equal(await page.locator('.device-bar').isVisible(),false);
  assert.equal(await page.getByRole('heading',{name:'1. Open your library'}).isVisible(),false,'Library setup hides during play');
  assert.equal(await page.getByRole('heading',{name:'2. Connect your game'}).isVisible(),false,'Screen setup hides during play');
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('mobile-ocr-state',{detail:{scanning:false}})));
  await page.waitForFunction(()=>!document.body.classList.contains('reader-active'));
  assert(await page.getByRole('heading',{name:'1. Open your library'}).isVisible(),'Pausing restores setup');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.selectOption('#source','pc');
  await stream({state:'disconnected',live:false});
  // Separate source and translation sizes persist and affect plain transcripts.
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Source language font size',{exact:false}).fill('36');
  await page.getByLabel('Target language font size',{exact:false}).fill('19');
  await page.waitForFunction(async()=>{const saved=await(await import('./storage.mjs')).get('browser-reading');return saved?.options.fontSize===36&&saved?.translationFontSize===19;});
  await page.reload();
  await page.waitForFunction(()=>typeof window.releaseHistoryRestore==='function');
  await page.evaluate(()=>window.releaseHistoryRestore());
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  assert.equal(await page.getByLabel('Source language font size',{exact:false}).inputValue(),'36');
  assert.equal(await page.getByLabel('Target language font size',{exact:false}).inputValue(),'19');
  await page.selectOption('#source','pc');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.locator('.current-card .migaku-sentence').waitFor();
  assert.equal(await page.locator('.current-card .translation').evaluate(el=>getComputedStyle(el).fontSize),'19px');
  assert(Math.abs(await page.locator('.current-card .migaku-sentence').evaluate(el=>parseFloat(getComputedStyle(el).fontSize))-39.6)<.1,'Source size changes plain game text');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Source language font size',{exact:false}).fill('27');
  await page.getByLabel('Target language font size',{exact:false}).fill('14');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.locator('input[name=key]').fill('mock-layout-key');
  await page.locator('input[name=pass]').fill('safe layout fixture passphrase');
  await page.locator('input[name=confirm]').fill('safe layout fixture passphrase');
  await page.getByRole('button',{name:'Connect Lexirise',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'Lexirise settings could not be loaded'}).waitFor();
  await page.getByRole('button',{name:'Unlock',exact:true}).waitFor({timeout:3000});
  assert.equal(await page.locator('input[name=key]').count(),0,'A stored key survives a temporary settings failure');
  assert.equal(await page.locator('input[name=confirm]').count(),0,'Retry unlock only needs the existing passphrase');
  assert(await page.evaluate(async()=>Boolean(await(await import('./storage.mjs')).get('lexirise-vault'))),'Encrypted vault was saved before settings failed');
  await page.locator('input[name=pass]').fill('safe layout fixture passphrase');
  await page.getByRole('button',{name:'Unlock',exact:true}).click();
  await page.getByRole('button',{name:'Lock',exact:true}).waitFor();
  const settingsBefore=requests.filter(r=>r.path==='/v1/settings').length;
  await page.getByRole('button',{name:'Account settings',exact:true}).click();
  const accountDialog=page.getByRole('dialog',{name:'Lexirise account settings',exact:true});
  await page.waitForTimeout(250);
  assert.equal(requests.filter(r=>r.path==='/v1/settings').length-settingsBefore,1,'Opening the panel must not create an adapter reload loop');
  await accountDialog.getByLabel('translationLanguage',{exact:true}).selectOption('de');
  await page.evaluate(()=>document.querySelector('#status').textContent='Settings draft fixture');
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  assert.equal(await accountDialog.getByLabel('translationLanguage',{exact:true}).inputValue(),'de','Unrelated parent update preserves the settings draft');
  assert.equal(requests.filter(r=>r.path==='/v1/settings').length-settingsBefore,1,'Parent updates keep settings adapter identity');
  await accountDialog.getByRole('button',{name:'Close Lexirise settings'}).click();
  await page.getByLabel('Reader mode').selectOption('lexirise');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.locator('.current-card .reading-hanzi').first().waitFor();
  await page.getByRole('button',{name:'Dismiss',exact:true}).click();

  // Keep a real shipped reader mounted while its parent processes unrelated work.
  const historyWord=page.locator('.history-list .dialogue').last().locator('.reading-hanzi').first();
  await historyWord.click();await page.locator('.word-dictionary').waitFor();
  await page.getByRole('tab',{name:'Context',exact:true}).click();
  await page.getByRole('tab',{name:'Definition',exact:true}).click();
  await page.locator('.word-sheet-body').evaluate(el=>el.scrollTop=90);
  await page.getByRole('tab',{name:'Definition',exact:true}).focus();
  await page.evaluate(()=>{window.readerFixture={sheet:document.querySelector('.word-sheet'),focus:document.activeElement,word:document.querySelector('.history-list .dialogue:last-child .reading-hanzi'),scroll:document.querySelector('.word-sheet-body').scrollTop};});
  const analyzedBefore=requests.filter(r=>r.path==='/v1/analyze/text').length;
  const stableReader=async reason=>{
   await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
   assert(await page.evaluate(()=>window.readerFixture.sheet===document.querySelector('.word-sheet')),reason+': lookup must stay mounted');
   assert(await page.evaluate(()=>window.readerFixture.word===document.querySelector('.history-list .dialogue:last-child .reading-hanzi')),reason+': transcript reader must stay mounted');
   assert(await page.evaluate(()=>window.readerFixture.focus===document.activeElement),reason+': keyboard focus must survive');
   assert.equal(await page.getByRole('tab',{name:'Definition',exact:true}).getAttribute('aria-selected'),'true',reason+': selected lookup tab survives');
   assert.equal(await page.locator('.word-sheet-body').evaluate(el=>el.scrollTop),await page.evaluate(()=>window.readerFixture.scroll),reason+': lookup scroll survives');
   assert.equal(requests.filter(r=>r.path==='/v1/analyze/text').length,analyzedBefore,reason+': unchanged text must not be analyzed again');
  };
  await page.evaluate(()=>document.querySelector('#status').textContent='Synthetic connection status');
  await stableReader('Connection status');
  await page.evaluate(rows=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'line'},rows}})),[{...rows[0],id:4,createdAt:1700000004000}]);
  await stableReader('New transcript line');
  // Hold only the IndexedDB completion callback, then reopen the lookup before
  // the real favorite mutation refreshes React. The click itself dismisses the
  // popup by the shared reader's intentional outside-click policy.
  await page.evaluate(()=>{
   const original=IDBDatabase.prototype.transaction;
   IDBDatabase.prototype.transaction=function(...args){
    const tx=original.apply(this,args);if(args[0]==='state'&&args[1]==='readwrite'){
     IDBDatabase.prototype.transaction=original;let complete;
     Object.getOwnPropertyDescriptor(IDBTransaction.prototype,'oncomplete').set.call(tx,event=>{window.finishFavoriteWrite=()=>complete?.call(tx,event);});
     Object.defineProperty(tx,'oncomplete',{get:()=>complete,set:value=>{complete=value;}});
    }return tx;
   };
  });
  await page.locator('.history-list .dialogue').last().getByRole('button',{name:'☆ Favorite',exact:true}).evaluate(el=>el.click());
  await page.locator('.word-sheet').waitFor({state:'detached'});
  await page.waitForFunction(()=>typeof window.finishFavoriteWrite==='function');
  assert(await page.evaluate(()=>window.readerFixture.word===document.querySelector('.history-list .dialogue:last-child .reading-hanzi')),'Favorite click preserves the reader node');
  await historyWord.click();await page.locator('.word-dictionary').waitFor();
  await page.locator('.word-sheet-body').evaluate(el=>el.scrollTop=90);
  await page.getByRole('tab',{name:'Definition',exact:true}).focus();
  await page.evaluate(()=>{window.readerFixture.sheet=document.querySelector('.word-sheet');window.readerFixture.focus=document.activeElement;window.readerFixture.scroll=document.querySelector('.word-sheet-body').scrollTop;window.finishFavoriteWrite();});
  await page.locator('.history-list .dialogue').last().getByRole('button',{name:'★ Favorited',exact:true}).waitFor();
  await stableReader('Favorite completion');
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('pc-capabilities',{detail:{source:'pc-layout-fixture'}})));
  await stableReader('Unrelated source capability state');
  await page.keyboard.press('Escape');await page.locator('.word-sheet').waitFor({state:'detached'});

  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Reader mode').selectOption('migaku');
  assert.equal(await page.locator('.reading-hanzi').count(),0,'Mode switch removes Lexirise reader UI');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.locator('.current-card .migaku-sentence').evaluate(el=>{el.innerHTML='<span data-migaku-fixture="1">'+el.textContent+'</span>';window.migakuFixture=el.firstChild;});
  const beforeMigaku=requests.length;
  await page.evaluate(()=>document.querySelector('#status').textContent='Independent Migaku status');
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  assert(await page.evaluate(()=>window.migakuFixture===document.querySelector('[data-migaku-fixture]')),'Parent updates preserve extension-owned Migaku text');
  assert.equal(requests.length,beforeMigaku,'Migaku mode is independent of account analysis');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Reader mode').selectOption('lexirise');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.locator('.current-card .reading-hanzi').first().waitFor();
  assert(await page.evaluate(()=>!window.readerFixture.word.isConnected),'Mode change invalidates the previous reader context');
  await page.locator('.current-card .reading-hanzi').first().click();await page.locator('.word-sheet').waitFor();
  await page.evaluate(()=>{window.settingsReaderFixture=document.querySelector('.current-card .reading-hanzi');window.dispatchEvent(new Event('lexirise-account-settings'));});
  await page.waitForFunction(()=>!window.settingsReaderFixture.isConnected);
  await page.locator('.word-sheet').waitFor({state:'detached'});
  await page.locator('.current-card .reading-hanzi').first().waitFor();

  // Small phone, ordinary phones, landscape, and a reduced CSS viewport that
  // represents enlarged display scaling. Transcript controls stay compact.
  for(const viewport of [{width:320,height:568},{width:375,height:667},{width:390,height:844},{width:430,height:932},{width:844,height:390},{width:260,height:568}]){
   await page.setViewportSize(viewport);
   await page.locator('.current-card').scrollIntoViewIfNeeded();
   const layout=await page.evaluate(()=>({
    overflow:document.documentElement.scrollWidth>innerWidth+1,
    innerPadding:getComputedStyle(document.querySelector('.current-dialogue')).padding,
    card:document.querySelector('.history-list .dialogue').getBoundingClientRect().height,
    actions:[...document.querySelectorAll('.current-dialogue .line-actions button')].map(b=>({top:b.getBoundingClientRect().top,height:b.getBoundingClientRect().height})),
    toolbar:[...document.querySelectorAll('.history-toolbar button,.history-toolbar input')].map(el=>({top:el.getBoundingClientRect().top,height:el.getBoundingClientRect().height})),
   }));
   if(layout.overflow){
    console.error('Overflow geometry',name,viewport,await page.evaluate(()=>[...document.querySelectorAll('main,main *')].map(el=>{const r=el.getBoundingClientRect();return {tag:el.tagName,id:el.id,classes:el.className,left:r.left,right:r.right,width:r.width};}).filter(r=>r.width>0&&(r.left<0||r.right>innerWidth+1)).slice(0,15)));
    await page.screenshot({path:`output/playwright/mobile-layout-overflow-${name}-${viewport.width}.png`,fullPage:true});
   }
   assert.equal(layout.overflow,false,`${name} page overflow at ${viewport.width}`);
   assert.equal(layout.innerPadding,'0px');
   assert(layout.actions.every(b=>b.height>=32&&b.height<=40),'Sentence actions are compact: '+JSON.stringify({viewport,actions:layout.actions}));
   assert(layout.actions.every(b=>Math.abs(b.top-layout.actions[0].top)<1),'Actions use one row');
   assert(layout.toolbar.every(b=>b.height<=34&&Math.abs(b.top-layout.toolbar[0].top)<1),'History, favorites and search share one compact row');
   if(viewport.width===390){assert(layout.card<310,'Short annotated history should fit in a compact card');await page.screenshot({path:`output/playwright/mobile-reader-${name}-390.png`,fullPage:true});await page.locator('.history-list .dialogue').first().screenshot({path:`output/playwright/mobile-history-${name}-390.png`});}

   await page.locator('.current-card .reading-hanzi').first().click();
   await page.locator('.word-dictionary').waitFor();
   const sheet=await page.locator('.word-sheet').boundingBox();
   await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
   const settled=await page.locator('.word-sheet').boundingBox();
   assert(Math.abs(sheet.width-settled.width)<1&&Math.abs(sheet.height-settled.height)<1,'Lookup layout stabilizes after data loads');
   assert(sheet.x>=7&&sheet.x+sheet.width<=viewport.width-7,`${name}: sheet within viewport`);
   assert(sheet.width>=viewport.width-18,'Lookup uses phone width');
   assert(sheet.y>=0&&sheet.y+sheet.height<=viewport.height,'Lookup within visible height');
   assert(sheet.height<=viewport.height*.5,'Lookup occupies at most half the screen');
   const currentCard=await page.locator('.current-card').boundingBox();
   assert(currentCard.y>=0&&currentCard.y+currentCard.height<=sheet.y,'Current line remains visible above lookup');
   const controls=await page.locator('.word-sheet-close').boundingBox();assert(controls.width>=32&&controls.height>=32);
   if(viewport.width===390)await page.screenshot({path:`output/playwright/mobile-lookup-${name}-390.png`});
   await page.locator('.word-sheet-body').evaluate(el=>el.scrollTop=el.scrollHeight);
   assert(await page.locator('.word-sheet-body').evaluate(el=>el.scrollTop>0),'Long definitions scroll');
   assert(await page.getByRole('button',{name:'Close word lookup'}).isVisible());
   await page.getByRole('tab',{name:'Context',exact:true}).click();
   assert.equal(await page.getByRole('tab',{name:'Context',exact:true}).getAttribute('aria-selected'),'true');
   await page.getByRole('button',{name:'Close word lookup'}).click();
   await page.locator('.word-sheet').waitFor({state:'detached'});
   // Reset the next lookup to Definition after checking horizontal tab access.
   await page.locator('.current-card .reading-hanzi').first().click();
   await page.getByRole('tab',{name:'Definition',exact:true}).click();
   await page.keyboard.press('Escape');
   await page.locator('.word-sheet').waitFor({state:'detached'});
  }
  // Long current lines get their own upper scroll area rather than being
  // obscured by dictionary details, even when looking up a history word.
  await page.setViewportSize({width:390,height:844});
  const longRow={...rows[0],id:4,createdAt:1700000004000,chinese:chinese.repeat(12)};
  await page.evaluate(row=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'line'},rows:[row]}})),longRow);
  await page.waitForFunction(()=>document.querySelector('.current-card .reading-text')?.textContent.length>200);
  await page.locator('.history-list .dialogue').last().locator('.reading-hanzi').first().click();
  await page.locator('.word-dictionary').waitFor();
  const longCard=await page.locator('.current-card').boundingBox(),longSheet=await page.locator('.word-sheet').boundingBox();
  assert(longCard.y>=0&&longCard.y+longCard.height<=longSheet.y,'Long current line stays above a history lookup');
  await page.locator('.current-card').evaluate(el=>el.scrollTop=el.scrollHeight);
  assert(await page.locator('.current-card').evaluate(el=>el.scrollTop>0),'Long current line scrolls independently');
  await page.screenshot({path:`output/playwright/mobile-long-lookup-${name}-390.png`});
  await page.getByRole('button',{name:'Close word lookup'}).click();
  await page.evaluate(row=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'line'},rows:[row]}})),{...longRow,chinese});
  await page.waitForFunction(()=>document.querySelector('.current-card .reading-text')?.textContent.length<200);
  await page.setViewportSize({width:1280,height:900});
  await page.locator('.current-card .reading-hanzi').first().click();
  await page.locator('.word-dictionary').waitFor();
  const desktop=await page.locator('.word-sheet').boundingBox();assert(desktop.width<=401&&desktop.height<=321,'Desktop retains shared compact lookup');
  await page.getByRole('button',{name:'Close word lookup'}).click();
  await page.setViewportSize({width:390,height:844});
  await page.locator('.current-card .reading-hanzi').nth(1).click();
  await page.locator('.word-sheet').waitFor();
  assert(await page.locator('.word-sheet-top').evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Longer headwords wrap without overflowing the header');
  await page.locator('.companion-nav').click({position:{x:1,y:1}});
  await page.locator('.word-sheet').waitFor({state:'detached'});
  await page.locator('.current-card .reading-hanzi').first().focus();
  await page.keyboard.press('Enter');
  await page.locator('.word-sheet').waitFor();
  await page.keyboard.press('Escape');
  await page.locator('.word-sheet').waitFor({state:'detached'});
  assert(await page.locator('.current-card .reading-hanzi').first().evaluate(el=>el===document.activeElement),'Keyboard lookup restores focus');
  await page.getByRole('button',{name:'Reading options',exact:true}).click();
  await page.getByLabel('Text size',{exact:true}).fill('48');
  await page.getByRole('button',{name:'Close Lexirise settings'}).click();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Largest reading text remains within the phone');
  assert(Math.abs(await page.locator('.current-card .reading-text').evaluate(el=>parseFloat(getComputedStyle(el).fontSize))-52.8)<.1,'Annotated source text respects the largest size');
  await page.locator('.current-card .reading-hanzi').first().click();
  await page.locator('.word-dictionary').waitFor();
  assert.equal(await page.locator('.word-sheet').evaluate(el=>getComputedStyle(el).fontSize),'14px','Lookup size is independent of transcript size');
  await page.getByRole('button',{name:'Close word lookup'}).click();
  await page.evaluate(tone=>{
   const bytes=Uint8Array.from(atob(tone),c=>c.charCodeAt(0));
   document.querySelector('#voice-player').src=URL.createObjectURL(new Blob([bytes],{type:'audio/mpeg'}));
  },TONE);
  await page.locator('#voice-player').waitFor({state:'visible'});
  await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));
  const player=await page.locator('#voice-player').boundingBox();
  const finalActions=await page.locator('.history-list .dialogue').last().locator('.line-actions').boundingBox();
  assert(finalActions.y+finalActions.height<=player.y,'Final history actions can scroll clear of fixed native audio controls');
  assert(await page.locator('main').evaluate(el=>parseFloat(getComputedStyle(el).paddingBottom)>=100),'Playback reserves native control and safe-area clearance');
  await page.evaluate(()=>{const player=document.querySelector('#voice-player');URL.revokeObjectURL(player.src);player.removeAttribute('src');player.load();});
  assert.equal(await page.locator('main').evaluate(el=>parseFloat(getComputedStyle(el).paddingBottom)),32,'Inactive audio does not add empty page space');
  // A pending read from the old vault session may finish after replacement.
  // The new account gets fresh reader state and the old result stays invisible.
  holdLookup=true;await page.locator('.current-card .reading-hanzi').last().click();
  await page.waitForTimeout(100);assert(releaseLookup,'Old account has a pending lookup');
  const beforeReplacement=analysisAccounts.length;
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByRole('button',{name:'Replace key / forgotten passphrase',exact:true}).click();
  assert.equal(await page.locator('.reading-hanzi').count(),0,'Lock invalidates account readers immediately');
  await page.locator('input[name=key]').fill('mock-layout-key-second');
  await page.locator('input[name=pass]').fill('second layout fixture passphrase');
  await page.locator('input[name=confirm]').fill('second layout fixture passphrase');
  await page.getByRole('button',{name:'Connect Lexirise',exact:true}).click();
  await page.getByRole('button',{name:'Lock',exact:true}).waitFor();
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.locator('.current-card .reading-hanzi').first().waitFor();await releaseLookup();
  assert.equal(await page.getByText('FIRST ACCOUNT PENDING',{exact:true}).count(),0,'Old account response cannot populate replacement readers');
  assert(analysisAccounts.slice(beforeReplacement).includes('second'),'Replacement account performs its own analysis');
  await page.evaluate(()=>window.languageReaderFixture=document.querySelector('.current-card .reading-hanzi'));
  for(const game of ['beyond','heavyrain']){
  await page.getByRole('button',{name:'Settings',exact:true}).click();await page.selectOption('#game',game);await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.evaluate(game=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'page'},rows:[{source:'pc-layout-fixture',game,id:7,createdAt:1700000010000,chinese:'合成测试句子。',english:'',speakerChinese:'',speakerEnglish:'',audio:false,sourceLanguage:'nl',sourceLocale:'nl',sourceText:'Een volledige testzin.',translationLocale:'zh-Hans',translationText:'合成测试句子。',audioLocale:'nl'}]}})),game);
  await page.locator('.current-card .reading-text[lang="nl"]').waitFor();
  assert(await page.evaluate(()=>!window.languageReaderFixture.isConnected),'Language context invalidates the previous reader');
  await page.locator('.current-card .reading-hanzi').first().click();
  await page.locator('.word-sheet').getByText('荷兰语词义',{exact:false}).first().waitFor();
  assert(requests.some(r=>r.path==='/v1/dictionary/lookup'&&r.payload.language==='nl'),'Dutch lookup uses its own learning language');
  await page.getByRole('button',{name:'Close word lookup'}).click();
  }
  // Resolve changed settings before constructing a new pinned-target session.
  await page.evaluate(()=>{window.previousTargetReader=document.querySelector('.current-card .reading-hanzi');window.dispatchEvent(new Event('lexirise-account-settings'));});
  await page.waitForFunction(()=>!window.previousTargetReader.isConnected);
  await page.locator('.current-card .reading-hanzi').first().waitFor();
  holdLookup=true;releaseLookup=null;await page.locator('.current-card .reading-hanzi').first().click();
  await page.waitForTimeout(100);assert(releaseLookup,'Target change has a pending old lookup');
  dutchTarget='nl';
  await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-account-settings')));
  await page.locator('.word-sheet').waitFor({state:'detached'});
  await page.locator('.current-card .reading-hanzi').first().waitFor();
  await releaseLookup();
  await page.locator('.current-card .reading-hanzi').first().click();
  await page.locator('.word-sheet').getByText('Nederlandse betekenis',{exact:false}).first().waitFor();
  assert.equal(await page.getByText('FIRST ACCOUNT PENDING',{exact:true}).count(),0,'Previous target cannot publish after settings change');
  await page.getByRole('button',{name:'Close word lookup'}).click();
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByText('Sentence saving and decks',{exact:true}).click();holdDecks=true;
  await page.getByRole('button',{name:'Load my decks',exact:true}).click();
  for(let attempt=0;!releaseDecks&&attempt<100;attempt++)await page.waitForTimeout(20);
  assert(releaseDecks,'A previous source deck read is pending');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'page'},rows:[{source:'pc-layout-fixture',game:'heavyrain',id:8,createdAt:1700000011000,chinese:'测试',english:'',audio:false,sourceLanguage:'de',sourceLocale:'de',sourceText:'Een',translationLocale:'nl',translationText:'Een fixture'}]}})));
  await page.locator('.current-card .reading-text[lang="de"]').waitFor();
  await page.locator('.current-card .reading-hanzi').first().click();
  await page.locator('.word-sheet').getByText('Nederlandse betekenis',{exact:false}).first().waitFor();
  assert(requests.some(r=>r.path==='/v1/dictionary/lookup'&&r.payload.language==='de'),'German lookup resolves its own Dutch target');
  // Returning to the same cached source session still starts a new UI scope.
  await page.getByRole('button',{name:'Close word lookup'}).click();
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'page'},rows:[{source:'pc-layout-fixture',game:'heavyrain',id:9,createdAt:1700000012000,chinese:'测试',english:'',audio:false,sourceLanguage:'nl',sourceLocale:'nl',sourceText:'Een terugkeer.',translationLocale:'nl',translationText:'Fixture return'}]}})));
  await page.locator('.current-card .reading-text[lang="nl"]').waitFor();
  await releaseDecks();await page.waitForTimeout(100);
  assert.equal(await page.getByLabel('Save destination').locator('option[value="42"]').count(),0,'Late Dutch decks cannot populate a returned Dutch reader generation');
  // A retired action owns its failures as well as its successful results. Real
  // fetch/abort paths must not publish errors into the replacement reader.
  let actionRowId=100;
  const changeActionSource=async language=>{
   await page.evaluate(({language,id})=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'page'},rows:[{source:'pc-layout-fixture',game:'heavyrain',id,createdAt:1700000100000+id,chinese:'测试',english:'',audio:false,sourceLanguage:language,sourceLocale:language,sourceText:'Een actie.',translationLocale:'nl',translationText:'Authored action fixture'}]}})),{language,id:actionRowId++});
   await page.locator('.current-card .reading-text[lang="'+language+'"]').waitFor({state:'attached'});
   await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  };
  const holdAction=(path,method='GET',result={status:503,json:{detail:'Synthetic delayed account failure'}})=>{heldAction={path,method,result};releaseAction=null;};
  const waitForAction=async()=>{for(let attempt=0;!releaseAction&&attempt<100;attempt++)await page.waitForTimeout(20);assert(releaseAction,'Synthetic account action must be in flight');};
  const finishRetiredAction=async(reason,release=releaseAction)=>{await release();await page.waitForTimeout(100);assert.equal(await page.getByRole('alert').count(),0,reason+': retired failure must stay out of current UI');};
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  holdAction('/v1/decks?');await page.getByRole('button',{name:'Load my decks',exact:true}).click();await waitForAction();
  await changeActionSource('de');await changeActionSource('nl');
  await finishRetiredAction('Source A to B to A');
  holdAction('/v1/decks','POST');await page.getByLabel('New deck name',{exact:true}).fill('Authored pending deck');await page.getByRole('button',{name:'Create deck',exact:true}).click();await waitForAction();
  dutchTarget='zh-hans';await page.evaluate(()=>{window.actionTargetNode=document.querySelector('.current-card .reading-text');window.dispatchEvent(new Event('lexirise-account-settings'));});
  await page.waitForFunction(()=>!window.actionTargetNode.isConnected&&document.querySelector('.current-card .reading-text'));
  await finishRetiredAction('Effective target change during deck creation');
  await page.evaluate(()=>window.ignoreNextDeckAbort=true);
  holdAction('/v1/decks?');await page.getByRole('button',{name:'Load my decks',exact:true}).click();await waitForAction();const releaseLockedAction=releaseAction;
  await page.getByRole('button',{name:'Lock',exact:true}).click();await page.getByRole('button',{name:'Unlock',exact:true}).waitFor({timeout:3000});
  assert.equal(await page.getByRole('alert').count(),0,'Explicit lock does not report an aborted account action as an error');
  await page.locator('input[name=pass]').fill('second layout fixture passphrase');await page.getByRole('button',{name:'Unlock',exact:true}).click();await page.getByRole('button',{name:'Lock',exact:true}).waitFor();await page.getByText('Sentence saving and decks',{exact:true}).click();
  holdAction('/v1/decks?');await page.getByRole('button',{name:'Load my decks',exact:true}).click();await waitForAction();
  await finishRetiredAction('Vault lock and unlock',releaseLockedAction);
  assert(await page.getByRole('button',{name:'Load my decks',exact:true}).isDisabled(),'Finishing old account work cannot release the current action gate');
  await releaseAction();await page.getByRole('alert').filter({hasText:'Lexirise returned HTTP 503'}).waitFor();await page.getByRole('alert').getByRole('button',{name:'Dismiss',exact:true}).click();
  holdAction('/v1/vocabulary','POST');await page.getByRole('button',{name:'Play',exact:true}).click();await page.locator('.current-card').getByRole('button',{name:'Save sentence',exact:true}).click();await waitForAction();
  await changeActionSource('de');await finishRetiredAction('Source change during sentence saving');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await changeActionSource('nl');await page.getByRole('button',{name:'Load my decks',exact:true}).click();await page.getByLabel('Save destination').selectOption('42');
  const deckWritesBefore=requests.filter(r=>/^\/v1\/decks\/\d+\/items$/.test(r.path)).length;
  holdAction('/v1/vocabulary','POST',{status:200,json:{item:{id:77}}});await page.getByRole('button',{name:'Play',exact:true}).click();await page.locator('.current-card').getByRole('button',{name:'Save sentence',exact:true}).click();await waitForAction();
  await changeActionSource('de');await finishRetiredAction('Retired sentence success');
  assert.equal(requests.filter(r=>/^\/v1\/decks\/\d+\/items$/.test(r.path)).length,deckWritesBefore,'Retired sentence save cannot issue a later deck mutation');
  assert.equal(await page.getByRole('status').filter({hasText:'Sentence saved to Lexirise'}).count(),0,'Retired sentence success cannot update current reader status');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  holdAction('/v1/decks?');await page.getByRole('button',{name:'Load my decks',exact:true}).click();await waitForAction();await releaseAction();
  await page.getByRole('alert').filter({hasText:'Lexirise returned HTTP 503'}).waitFor();
  await page.getByRole('alert').getByRole('button',{name:'Dismiss',exact:true}).click();
  // Mount the same shipped application with its reader portal in a Shadow
  // root from the start, so React registers native events at the proper root.
  const shadowPage=await context.newPage(),shadowErrors=[],shadowFailures=[];
  shadowPage.on('pageerror',e=>{errors.push(e.message);shadowErrors.push(e.message);});
  shadowPage.on('requestfailed',request=>shadowFailures.push(new URL(request.url()).pathname+': '+request.failure()?.errorText));
  await shadowPage.goto('http://127.0.0.1:'+server.address().port+'/?shadow-reader=1');
  await shadowPage.getByRole('button',{name:'Settings',exact:true}).click().catch(async error=>{throw Error('Shadow reader failed to mount: '+JSON.stringify({errors:shadowErrors,requests:shadowFailures,body:(await shadowPage.locator('body').innerText()).slice(0,2000)}),{cause:error});});
  await shadowPage.locator('input[name=pass]').fill('second layout fixture passphrase');
  await shadowPage.getByRole('button',{name:'Unlock',exact:true}).click();await shadowPage.getByRole('button',{name:'Lock',exact:true}).waitFor();
  await shadowPage.getByRole('button',{name:'Settings',exact:true}).click();await shadowPage.selectOption('#source','pc');await shadowPage.getByRole('button',{name:'Play',exact:true}).click();
  const shadowWord=shadowPage.locator('.current-card .reading-hanzi').first();await shadowWord.waitFor();
  await shadowWord.focus();await shadowPage.keyboard.press('Enter');await shadowPage.locator('.word-sheet').waitFor();
  await shadowPage.evaluate(()=>{window.shadowSheet=document.querySelector('.word-sheet');document.querySelector('#status').textContent='Shadow reader status';});
  await shadowPage.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  assert(await shadowPage.evaluate(()=>window.shadowSheet===document.querySelector('.word-sheet')),'Shadow DOM lookup survives a parent update');
  await shadowPage.keyboard.press('Escape');await shadowPage.locator('.word-sheet').waitFor({state:'detached'});
  assert(await shadowWord.evaluate(el=>el.getRootNode().activeElement===el),'Shadow DOM keyboard lookup restores token focus');
  await shadowPage.evaluate(()=>document.documentElement.style.zoom='1.25');
  await shadowWord.click();await shadowPage.locator('.word-sheet').waitFor();
  assert(await shadowPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Shadow reader fits at 125% zoom');
  await shadowPage.close();
  assert.deepEqual(errors,[]);
  assert(deferredResizes<=1,'WebKit must not enter a repeated resize loop');
  if(deferredResizes)console.log('webkit: one deferred initial ResizeObserver delivery; subsequent layout stable');
  assert.deepEqual(requests.filter(r=>r.method!=='GET'&&!r.path.startsWith('/v1/analyze/')&&!r.path.startsWith('/v1/dictionary/')).map(r=>r.method+' '+r.path),['POST /v1/decks','POST /v1/vocabulary','POST /v1/vocabulary'],'Only explicit synthetic account mutation fixtures are exercised');
  console.log(`${name}: phone, landscape, display scaling, compact cards, lookup scrolling/tabs/dismissal, retired account actions and desktop passed`);
  await context.close();await browser.close();browser=null;
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
