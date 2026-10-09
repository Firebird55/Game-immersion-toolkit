
import assert from 'node:assert/strict';import {spawn,execFileSync} from 'node:child_process';import {chromium,firefox} from 'playwright';
// Exercise the actual built Windows distribution, not the dev dependency optimizer.
const port=4321,server=spawn(process.execPath,['node_modules/wrangler/bin/wrangler.js','dev','--config','dist/server/wrangler.json','--port',String(port),'--ip','127.0.0.1'],{stdio:['ignore','pipe','pipe']});
let browser;
const region={left:.1,top:.6,width:.8,height:.25},settings={preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,hito_auto_regions:true,process_names:[],window_title_contains:[],scan_interval_ms:250,stable_frames:2,fuzzy_threshold:82,auto_start:false,save_unmatched:false};
const line={id:1,created_at:new Date().toISOString(),session_id:'fixture',game:'zzz',source_ocr:'Hello',english:'Hello',chinese:'你好',text_id:'fixture',score:100,match_kind:'exact',channel:'dialogue',voiced:true,has_audio:false,favorite:false};
const account={languages:['zh'],native_lang:'en',global:{translationLanguage:'en',interfaceLanguage:null,disableWordPopups:false,wordPopupOpenMode:'click',useCustomProficiencyColors:false,customProficiencyColors:{known:'green'}},languageSettings:{zh:{readingAid:'pinyin',script:'simplified',fontSize:'md'},nl:{fontSize:'md'}}};
const token={start:0,end:2,word:'你好',pinyin:'nǐ hǎo',zhuyin:'ㄋㄧˇ ㄏㄠˇ',tones:[3,3],proficiency:0,meaning:'hello',entryId:1};
function response(path,query,method,body){
 if(path==='/api/status')return {capture:{running:false,phase:'stopped',message:'Fixture capture',active_game:'zzz',visible_text_ids:['fixture']},textmaps:{ready:true,state:'ready',message:'fixture',entry_count:1},audio:{ready:false,message:'fixture'},settings,session:{id:'fixture',line_count:1,total_line_count:1}};
 if(path==='/api/lexirise')return {configured:true,decks:{},sent:{}};
 if(path==='/api/lines')return query.get('game')==='zzz'?[line]:[];
 if(path==='/api/favorites')return [];
 if(path==='/api/lexirise/settings'){if(method==='PATCH'){Object.assign(account.global,body.global??{});for(const[l,changes]of Object.entries(body.languageSettings??{}))Object.assign(account.languageSettings[l]??={},changes);}return account;}
 if(path==='/api/lines/1/reading')return {text:'你好',tokens:[token],grammar:[]};
 if(path.endsWith('/lookup'))return {translations:[{meaning:'hello',partOfSpeech:['greeting'],examples:[]}],examples:[],dictionaries:[],alternateReadings:[],components:[]};
 if(path.endsWith('/characters'))return {characters:[]};
 if(path.endsWith('/examples'))return {examples:[]};
 if(path.endsWith('/similar'))return {suggestions:[],generated:true};
 if(path.endsWith('/context'))return {meaning:'A greeting',conciseMeaning:'hello',reading:'nǐ hǎo'};
 return {};
}
try{
 await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Toolkit preview startup timeout')),30000);server.stdout.on('data',b=>{if(String(b).includes('localhost:'+port)||String(b).includes('127.0.0.1:'+port)){clearTimeout(timer);resolve();}});server.stderr.on('data',b=>process.stderr.write(b));server.once('error',reject);});
 for(const[name,engine]of [['chromium',chromium],['firefox',firefox]]){browser=await engine.launch({headless:true});
 for(const[pw,ph,zoom]of [[1920,1080,1],[1920,1080,1.25],[1280,720,1.5],[1280,720,2],[390,844,1],[320,568,1],[568,320,1],[900,720,1],[768,1024,1.25],[3840,2160,2]]){
 const width=Math.floor(pw/zoom),height=Math.floor(ph/zoom),context=await browser.newContext({viewport:{width,height},deviceScaleFactor:zoom}),page=await context.newPage(),writes=[];
 await page.addInitScript(()=>localStorage.setItem('proxy-transcript-reading-mode','lexirise'));
 await page.route('http://127.0.0.1:8766/**',async route=>{const req=route.request(),url=new URL(req.url());const body=req.postData()?JSON.parse(req.postData()):{};
 if(req.method()==='PATCH'&&url.pathname==='/api/lexirise/settings')writes.push(body);
 await route.fulfill({status:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type,X-Proxy-Transcript','Access-Control-Allow-Methods':'GET,POST,PATCH,OPTIONS'},body:JSON.stringify(response(url.pathname,url.searchParams,req.method(),body))});});
 await page.goto('http://localhost:'+port);await page.locator('.reading-hanzi').first().click();await page.locator('.word-sheet').waitFor();
 await page.locator('.word-sheet').evaluate(n=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 let b=await page.locator('.word-sheet').boundingBox();assert(b&&b.x>=-1&&b.y>=-1&&b.x+b.width<=width+1&&b.y+b.height<=height+1,name+' toolkit lookup fits '+JSON.stringify(b));
 const expectedWidth=Math.min(width<=560?340:400,width-32),heightCap=width<=560?Math.min(360,height*.6):320;
 assert(Math.abs(b.width-expectedWidth)<=1,name+' toolkit shares compact lookup width');
 assert(b.height<=heightCap+1,name+' toolkit shares compact lookup height');
 assert.equal(await page.locator('.word-sheet-body').evaluate(n=>getComputedStyle(n).fontSize),'13px','Toolkit shares compact lookup typography');
 assert.equal(await page.locator('.word-sheet').evaluate(n=>n.getRootNode()===document),true,'Toolkit portal stays in document');
 await page.keyboard.press('Escape');await page.getByRole('button',{name:'Lexirise reading options',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Lexirise reading options'});await dialog.waitFor();await page.getByLabel('Edit account language').waitFor();
 b=await dialog.boundingBox();assert(b&&b.x>=0&&b.y>=0&&b.x+b.width<=width+1&&b.y+b.height<=height+1,name+' toolkit settings fits '+JSON.stringify(b));
 await page.getByLabel('Edit account language').selectOption('ja');assert.equal(await page.locator('.reading-text').first().getAttribute('lang'),'zh','Editing Japanese account settings never reinterprets Chinese transcript');
 assert.equal(writes.length,0);await page.keyboard.press('Escape');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' toolkit layout has no horizontal overflow at '+width);
 await page.getByRole('button',{name:'Capture setup',exact:true}).click();const capture=page.getByRole('dialog',{name:'Capture setup'});await capture.waitFor();b=await capture.boundingBox();assert(b&&b.x>=0&&b.x+b.width<=width+1,'Capture setup fits');
 await page.keyboard.press('Escape');await capture.waitFor({state:'hidden'});
 if(zoom===1&&pw===1920){for(const[w,h]of [[320,568],[1280,720],[568,320],[900,720]]){
  await page.setViewportSize({width:w,height:h});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Resize does not overflow');
  await page.getByRole('button',{name:'Lexirise reading options',exact:true}).click();await dialog.waitFor();const box=await dialog.boundingBox();assert(box&&box.x>=0&&box.y>=0&&box.x+box.width<=w+1&&box.y+box.height<=h+1,'Resized toolkit settings fit');await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
 }}
 console.log(name+': toolkit '+width+'x'+height+' zoom/DPR '+zoom+' passed');await context.close();
 }await browser.close();browser=null;}
}finally{await browser?.close();if(process.platform==='win32'){try{execFileSync('taskkill',['/PID',String(server.pid),'/T','/F'],{stdio:'ignore'});}catch{}}else server.kill();}
