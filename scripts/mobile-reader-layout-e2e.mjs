// Exercise the shipped reader with authored dialogue and mocked account reads.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import * as engines from 'playwright';
import {mime} from './mobile-assets.mjs';
import {TONE} from '../tests/mobile-media-fixtures.mjs';

const root=resolve(process.env.MOBILE_PREVIEW_DIR??'public/mobile-capture');
const server=http.createServer((req,res)=>{
 const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';
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
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,deviceScaleFactor:3,serviceWorkers:'block'});
  const page=await context.newPage(),errors=[],requests=[];
  let deferredResizes=0;
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
   const body=request.postDataJSON();requests.push(body);
   let data;
   if(body.path==='/v1/settings')data={languages:['zh'],global:{},languageSettings:{zh:{}}};
   else if(body.path==='/v1/analyze/text')data={occurrences:segments.map(([word,transliteration],i)=>({word,transliteration,charStart:chinese.indexOf(word),charEnd:chinese.indexOf(word)+word.length,isWordLike:true,entryId:i+1,tones:[3,3]})),entryMetaById:Object.fromEntries(segments.map((s,i)=>[i+1,{gloss:s[2]}])),stateByEntryId:{}};
   else if(body.path==='/v1/dictionary/lookup')data={word:body.payload.text,translations:[{target_lang:'en',translation:'hello; a greeting to welcome someone',part_of_speech:['interjection']}],supplementalEntries:[{dictionary_name:'Fixture dictionary',headword:body.payload.text,html:'<ul>'+Array.from({length:24},(_,i)=>'<li>Authored dictionary explanation '+(i+1)+' with enough detail to exercise scrolling.</li>').join('')+'</ul>'}],characterInfo:{pinyin:['nǐ'],gloss:'you'}};
   else if(body.path==='/v1/analyze/context')data={meaning:'A friendly greeting used when meeting a traveler.'};
   else throw Error('Unexpected mock account request: '+body.path);
   return route.fulfill({json:data,headers});
  });
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.getByRole('heading',{name:'Your next line belongs here.'}).waitFor();
  await page.selectOption('#source','pc');
  await page.evaluate(rows=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{message:{type:'page'},rows}})),rows);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.locator('input[name=key]').fill('mock-layout-key');
  await page.locator('input[name=pass]').fill('safe layout fixture passphrase');
  await page.locator('input[name=confirm]').fill('safe layout fixture passphrase');
  await page.getByRole('button',{name:'Connect Lexirise',exact:true}).click();
  await page.getByRole('button',{name:'Lock',exact:true}).waitFor();
  await page.getByLabel('Reader mode').selectOption('lexirise');
  await page.getByRole('button',{name:'Reader',exact:true}).click();
  await page.locator('.current-card .reading-hanzi').first().waitFor();
  await page.getByRole('button',{name:'Dismiss',exact:true}).click();

  // Small phone, ordinary phones, landscape, and a reduced CSS viewport that
  // represents enlarged display scaling. Touch targets remain at least 44px.
  for(const viewport of [{width:320,height:568},{width:375,height:667},{width:390,height:844},{width:430,height:932},{width:844,height:390},{width:260,height:568}]){
   await page.setViewportSize(viewport);
   await page.locator('.current-card').scrollIntoViewIfNeeded();
   const layout=await page.evaluate(()=>({
    overflow:document.documentElement.scrollWidth>innerWidth+1,
    innerPadding:getComputedStyle(document.querySelector('.current-dialogue')).padding,
    card:document.querySelector('.history-list .dialogue').getBoundingClientRect().height,
    actions:[...document.querySelectorAll('.current-dialogue .line-actions button')].map(b=>({top:b.getBoundingClientRect().top,height:b.getBoundingClientRect().height})),
   }));
   if(layout.overflow){
    console.error('Overflow geometry',name,viewport,await page.evaluate(()=>[...document.querySelectorAll('main,main *')].map(el=>{const r=el.getBoundingClientRect();return {tag:el.tagName,id:el.id,classes:el.className,left:r.left,right:r.right,width:r.width};}).filter(r=>r.width>0&&(r.left<0||r.right>innerWidth+1)).slice(0,15)));
    await page.screenshot({path:`output/playwright/mobile-layout-overflow-${name}-${viewport.width}.png`,fullPage:true});
   }
   assert.equal(layout.overflow,false,`${name} page overflow at ${viewport.width}`);
   assert.equal(layout.innerPadding,'0px');
   assert(layout.actions.every(b=>b.height>=44));
   assert(layout.actions.every(b=>Math.abs(b.top-layout.actions[0].top)<1),'Actions use one row');
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
   if(viewport.height>600)assert(sheet.height>viewport.height*.65,'Lookup is no longer capped at 360px');
   const controls=await page.locator('.word-sheet-close').boundingBox();assert(controls.width>=44&&controls.height>=44);
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
  assert.deepEqual(errors,[]);
  assert(deferredResizes<=1,'WebKit must not enter a repeated resize loop');
  if(deferredResizes)console.log('webkit: one deferred initial ResizeObserver delivery; subsequent layout stable');
  assert(requests.every(r=>r.method==='GET'||r.path.startsWith('/v1/analyze/')||r.path.startsWith('/v1/dictionary/')),'Layout verification never writes account data');
  console.log(`${name}: phone, landscape, display scaling, compact cards, lookup scrolling/tabs/dismissal and desktop passed`);
  await context.close();await browser.close();browser=null;
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
