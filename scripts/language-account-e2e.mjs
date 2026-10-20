import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
import {chromium,firefox} from 'playwright';

const port=4323;
const server=spawn(process.execPath,['node_modules/wrangler/bin/wrangler.js','dev','--config','dist/server/wrangler.json','--port',String(port),'--ip','127.0.0.1'],{stdio:['ignore','pipe','pipe']});
let browser;
mkdirSync('output/playwright',{recursive:true});
try{
 await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Account preview startup timeout')),30000);server.stdout.on('data',b=>{if(String(b).includes(':'+port)){clearTimeout(timer);resolve();}});server.once('error',reject);});
 for(const[name,engine]of [['chromium',chromium],['firefox',firefox]]){
  browser=await engine.launch({headless:true});
  for(const[width,height]of [[1280,900],[390,844]]){
   const context=await browser.newContext({viewport:{width,height}}),page=await context.newPage();
   let active='first',prepared=false,releaseOld;
   const writes=[],requests=[];
   const preferences=()=>({languages:['en','zh'],global:{translationLanguage:'fr',effectiveTranslationLanguage:'fr',wordPopupOpenMode:'click'},
    languageSettings:{en:{effectiveTranslationLanguage:active==='first'?'zh-hans':'nl',inlineGlossMode:'always',wordPopup:{tabs:[{id:'definition',enabled:true}],openOn:'first'}},zh:{effectiveTranslationLanguage:'en',inlineGlossMode:'off'}}});
   const region={left:.1,top:.6,width:.8,height:.25};
   const settings={preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,auto_start:false};
   const line=()=>({id:1,game:'zzz',created_at:new Date().toISOString(),session_id:'fixture',source_ocr:'Hello',english:'Hello',chinese:'你好',source_language:'en',source_locale:'en',source_text:'Hello',translation_locale:active==='first'?'zh-Hans':'nl',translation_text:active==='first'?'你好':'Hallo',text_id:'fixture',channel:'dialogue',score:100,match_kind:'exact',voiced:true,has_audio:true,favorite:false});
   const languages=()=>({selected:prepared?'zh-Hans':null,enabled_languages:['en','zh'],targets:{en:active==='first'?'zh-hans':'nl',zh:'en'},locales:[
    {locale:'zh-Hans',language:'zh',name:'Simplified Chinese',reader_available:true,prepared:prepared?{targets:['en'],mapped_lines:1}:null},
    {locale:'ko',language:'ko',name:'Korean',reader_available:false,prepared:null}]});
   const game={id:'zzz',title:'Zenless Zone Zero',detected_path:'F:/Games/ZZZ',configured_path:null,folder_state:'detected',folder_hint:'Choose game folder',voice_state:'present',tools_missing:[],index_ready:true,indexed_lines:1,audio_ready:true,update_state:'idle',update_message:'Ready',progress:100};
   await page.addInitScript(()=>localStorage.setItem('proxy-transcript-reading-mode','lexirise'));
   await page.routeWebSocket('ws://127.0.0.1:8766/api/ws',()=>{});
   await page.route('http://127.0.0.1:8766/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname,body=request.postData()?JSON.parse(request.postData()):{};
    requests.push({path,method:request.method(),account:request.headers()['x-proxy-transcript-account']});
    if(!['GET','OPTIONS'].includes(request.method()))writes.push({path,body});
    const respond=value=>route.fulfill({status:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body:JSON.stringify(value)});
    if(path==='/api/status')return respond({capture:{running:true,active_game:'zzz',visible_text_ids:['fixture'],phase:'matched',message:'Ready'},textmaps:{ready:true,entry_count:1},audio:{ready:true},settings,session:{id:'fixture',line_count:1,total_line_count:1},selected_languages:{zzz:{source_language:'en',source_locale:'en'}}});
    if(path==='/api/lines')return respond(url.searchParams.get('game')==='zzz'?[line()]:[]);
    if(path==='/api/favorites')return respond([]);
    if(path==='/api/setup')return respond({completed:true,version:'fixture',games:[game],requirements:[],jobs:{},native:{},auto_start:false,lexirise_configured:true,mobile_export:{state:'idle'},free_gb:10});
    if(path==='/api/lexirise')return respond({configured:true,account:active,sent:{},decks:{}});
    if(path==='/api/lexirise/accounts')return respond({active,profiles:[{id:'first',name:'First account'},{id:'second',name:'Second account'}]});
    if(path==='/api/lexirise/accounts/select'){active=body.id;return respond({active});}
    if(path==='/api/lexirise/settings')return respond(preferences());
    if(path==='/api/lexirise/decks')return respond({decks:[]});
    if(path==='/api/setup/games/zzz/languages'){
     if(request.method()==='POST')prepared=true;
     return respond(languages());
    }
    if(path==='/api/lines/1/reading')return respond({text:'Hello',tokens:[{start:0,end:5,word:'Hello',entryId:1,proficiency:0,pinyin:'',tones:[],meaning:active==='first'?'你好':'Hallo'}],grammar:[]});
    if(path.endsWith('/lookup')){
     const result={translations:[{meaning:active==='first'?'FIRST ACCOUNT ONLY':'SECOND ACCOUNT ONLY',partOfSpeech:[],examples:[]}],examples:[],dictionaries:[],components:[],alternateReadings:[]};
     if(active==='first'){releaseOld=()=>respond(result);return;}
     return respond(result);
    }
    return respond({});
   });
   await page.goto('http://localhost:'+port);
   await page.locator('.current-line .reading-hanzi').click();
   await page.waitForTimeout(100);
   assert(releaseOld,'Old-account lookup is pending');
   await page.getByRole('button',{name:'Account settings',exact:true}).click();
   const panel=page.getByRole('dialog',{name:'Lexirise account settings'});
   await panel.getByLabel('Active Lexirise account').selectOption('second');
   await panel.getByText('Selected account loaded.',{exact:true}).waitFor();
   await panel.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
   await page.locator('.current-line .reading-hanzi').click();
   await page.locator('.word-sheet-body').getByText('SECOND ACCOUNT ONLY',{exact:true}).waitFor();
   await releaseOld();
   assert.equal(await page.getByText('FIRST ACCOUNT ONLY',{exact:true}).count(),0,'Old response cannot populate the new account');
   assert(requests.some(r=>r.path.endsWith('/lookup')&&r.account==='second'));
   await page.keyboard.press('Escape');
   await page.getByRole('button',{name:'Settings',exact:true}).click();
   const setup=page.getByRole('dialog',{name:'Settings'});
   await setup.locator('.language-table button').first().waitFor();
   assert.equal(writes.filter(w=>w.path.endsWith('/languages')).length,0,'Opening setup never prepares languages');
   await setup.getByRole('button',{name:'Prepare language',exact:true}).click();
   await setup.getByRole('button',{name:'Use this language',exact:true}).waitFor();
   assert.deepEqual(writes.filter(w=>w.path.endsWith('/languages')),[{path:'/api/setup/games/zzz/languages',body:{locale:'zh-Hans',action:'prepare',target:'en'}}]);
   await setup.getByText('Advanced',{exact:true}).click();
   const rebuilt=page.waitForResponse(r=>r.url().endsWith('/languages')&&r.request().method()==='POST');
   await setup.getByRole('button',{name:'Rebuild table',exact:true}).click();await rebuilt;
   assert.deepEqual(writes.filter(w=>w.path.endsWith('/languages')).at(-1).body,{locale:'zh-Hans',action:'rebuild',target:'en'},'Explicit rebuild has a distinct forced operation');
   assert(!writes.some(w=>w.path==='/api/lexirise/settings'||w.path==='/api/lexirise/decks'),'Read/switch/setup does not provision account data');
   assert(await setup.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Language setup fits viewport');
   await setup.screenshot({path:`output/playwright/languages-${name}-${width}.png`});
   await setup.getByRole('button',{name:'General & Updates',exact:true}).click();
   const writesBefore=writes.length;
   for(const [locale,label] of [['nl','Instellingen'],['zh-Hans','设置'],['zh-Hant','設定']]){await page.getByRole('dialog').locator('select').selectOption(locale);await page.getByRole('dialog',{name:label,exact:true}).waitFor();assert.equal(await page.locator('html').getAttribute('lang'),locale);}
   assert.equal(writes.length,writesBefore,'Interface language is local and never changes learning/account data');
   await page.getByRole('dialog').locator('select').selectOption('en');
   console.log(`${name}: isolated account responses and manual per-language setup ${width} passed`);
   await context.close();
  }
  await browser.close();browser=null;
 }
}finally{
 if(browser)await browser.close();
 if(process.platform==='win32')try{execFileSync('taskkill',['/PID',String(server.pid),'/T','/F'],{stdio:'ignore'});}catch{}
 else server.kill('SIGTERM');
}
