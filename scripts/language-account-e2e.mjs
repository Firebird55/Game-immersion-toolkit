import assert from 'node:assert/strict';
import {startPreview} from './e2e-preview.mjs';

import {chromium,firefox} from 'playwright';

const preview=await startPreview('language-account');
let browser;
try{
 for(const[name,engine]of [['chromium',chromium],['firefox',firefox]].filter(([name])=>!process.env.ACCOUNT_TEST_BROWSERS||process.env.ACCOUNT_TEST_BROWSERS.split(',').includes(name))){
  browser=await preview.launchBrowser(engine,{headless:true});
  for(const[width,height]of [[1280,900],[390,844]]){
   const context=await browser.newContext({locale:'en-US',viewport:{width,height}}),page=await context.newPage();
   let generation=0;const stateContext=()=>({runtime_id:'account-fixture',state_version:generation,account_generation:generation});
   let automatic={enabled:false,paused:false,destination:'',languages:{},jobs:{},locales:[{locale:'ja',name:'Japanese',voice_label:'Not detected — install this voice language in the game/launcher'},{locale:'en',name:'English',voice_label:'Installed'}],translations:['en','fr'],browseActive:false,browsedDestination:'',browseMessage:''};
   let active='first',prepared=false,releaseOld,releaseExport,exportMode='success',configured=true,deckMode='normal',releaseDeck;
   const sent={first:{},second:{},legacy:{}}; const unexpected=[];
   const writes=[],requests=[];
   const accountLanguages={first:['en','zh'],second:['en','zh'],legacy:['en','zh']};
   let failLanguageWrite=false,holdLanguageRead=false,releaseLanguageRead,captureGame='genshin',unvoiced=false;
   let initialLanguageGate=true;const initialLanguageReads=[];
   const preferences=()=>({languages:accountLanguages[active],global:{translationLanguage:'fr',effectiveTranslationLanguage:'fr',wordPopupOpenMode:'click'},
    languageSettings:{en:{effectiveTranslationLanguage:active==='first'?'zh-hans':'nl',inlineGlossMode:'always',wordPopup:{tabs:[{id:'definition',enabled:true}],openOn:'first'}},zh:{effectiveTranslationLanguage:'en',inlineGlossMode:'off'}}});
   const region={left:.1,top:.6,width:.8,height:.25};
   const updates={state:'retrying',progress:null,automatic:true,message:'Installed game files changed. The reader could not prepare the selected language; the previous table was kept.',items:[{game:'zzz',locale:'zh-Hans',state:'error',message:'The new archive format needs a reader update. Original voices remain unavailable until preparation succeeds.'},{game:'beyond',locale:'nl',state:'ready',message:'Prepared Dutch subtitles and original audio are current.'}]};
   const settings={preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,auto_start:false};
   const line=()=>({id:1,game:'zzz',created_at:new Date().toISOString(),session_id:'fixture',source_ocr:'Hello',english:'Hello',chinese:'你好',source_language:'en',source_locale:'en',source_text:'Hello',translation_locale:active==='first'?'zh-Hans':'nl',translation_text:active==='first'?'你好':'Hallo',text_id:'fixture',channel:'dialogue',score:100,match_kind:'exact',voiced:!unvoiced,has_audio:!unvoiced,voice_status:unvoiced?'unvoiced':'voiced',favorite:false});
   const languages=()=>({context:stateContext(),selected:prepared?'zh-Hans':null,enabled_languages:['en','zh'],targets:{en:active==='first'?'zh-hans':'nl',zh:'en'},locales:[
    {locale:'zh-Hans',language:'zh',name:'Simplified Chinese',reader_available:true,prepared:prepared?{targets:['en'],mapped_lines:1}:null},
    {locale:'ko',language:'ko',name:'Korean',reader_available:false,prepared:null}]});
   const game={id:'zzz',title:'Zenless Zone Zero',detected_path:'F:/Games/ZZZ',configured_path:null,folder_state:'detected',folder_hint:'Choose game folder',voice_state:'present',tools_missing:[],index_ready:true,indexed_lines:1,audio_ready:true,update_state:'idle',update_message:'Ready',progress:100};
   await page.addInitScript(()=>localStorage.setItem('proxy-transcript-reading-mode','lexirise'));
   await page.routeWebSocket('ws://127.0.0.1:8766/api/ws',()=>{});
   await page.route('http://127.0.0.1:8766/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname,body=request.postData()?JSON.parse(request.postData()):{};
    requests.push({path,method:request.method(),account:request.headers()['x-proxy-transcript-account']});
    if(!['GET','OPTIONS'].includes(request.method()))writes.push({path,body});
    const respond=(value,status=200)=>route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body:JSON.stringify(value)});
    if(request.method()==='OPTIONS')return respond({});
    if(path==='/api/settings'){if(request.method()==='PATCH')Object.assign(settings,body);return respond(settings);}
    if(path==='/api/toolkit-update')return respond({installed_version:'fixture',enabled:true,state:'current',message:'Toolkit is up to date'});
    if((/^\/api\/lines\/\d+\/(reading|lexirise)/.test(path)||path==='/api/lexirise/decks'||path==='/api/lexirise/settings'&&request.headers()['x-proxy-transcript-account']!==undefined)&&request.headers()['x-proxy-transcript-account']!==active)return respond({detail:'Account changed. Retry with the selected account.'},409);
    if(path==='/api/snapshot')return respond({context:stateContext(),status:{capture:{running:true,active_game:captureGame,visible_text_ids:['fixture'],phase:'matched',message:'Ready'},textmaps:{ready:true,entry_count:1},updates,audio:{ready:true},settings,session:{id:'fixture',line_count:1,total_line_count:1},selected_languages:{zzz:{source_language:'en',source_locale:'en'}}},lines:[line()],lexirise:{configured,account:active,sent:sent[active],decks:{}}});
    if(path==='/api/status')return respond({capture:{running:true,active_game:captureGame,visible_text_ids:['fixture'],phase:'matched',message:'Ready'},textmaps:{ready:true,entry_count:1},updates,audio:{ready:true},settings,session:{id:'fixture',line_count:1,total_line_count:1},selected_languages:{zzz:{source_language:'en',source_locale:'en'}}});
    if(path==='/api/lines')return respond(url.searchParams.get('game')==='zzz'?[line()]:[]);
    if(path==='/api/favorites')return respond([]);
    if(path==='/api/setup')return respond({completed:true,version:'fixture',games:[game],requirements:[],jobs:{},native:{},auto_start:false,lexirise_configured:true,mobile_export:{state:'idle'},free_gb:10});
    if(path==='/api/setup/games/zzz/automatic-mobile-export'){if(request.method()==='POST'){if(body.action==='save')automatic={...automatic,enabled:body.enabled,destination:body.destination,languages:body.languages};if(body.action==='pause'||body.action==='resume')automatic.paused=body.action==='pause';}return respond(automatic);}
    if(path==='/api/lexirise')return respond({configured,account:active,sent:sent[active],decks:{}});
    if(path==='/api/lexirise/accounts')return respond({active,profiles:[{id:'first',name:'First account'},{id:'second',name:'Second account'}]});
    if(path==='/api/lexirise/accounts/select'){active=body.id;generation++;return respond({active});}
    if(path==='/api/lexirise/settings'){
     // ReadingText also loads unscoped preferences during startup. Hold only
     // the game picker's account-scoped read, regardless of request ordering.
     if(request.method()==='GET'&&request.headers()['x-proxy-transcript-account']===active&&initialLanguageGate){
      const result=preferences();initialLanguageReads.push(()=>respond(result));
      releaseLanguageRead=async()=>{initialLanguageGate=false;await Promise.all(initialLanguageReads.splice(0).map(release=>release()));};return;
     }
     if(request.method()==='GET'&&request.headers()['x-proxy-transcript-account']===active&&holdLanguageRead){holdLanguageRead=false;const result=preferences();releaseLanguageRead=()=>respond(result);return;}
     if(request.method()==='PATCH'&&body.languages){
      if(failLanguageWrite)return respond({detail:'Synthetic language save failed'},502);
      accountLanguages[active]=body.languages;
     }
     return respond(preferences());
    }
    if(path==='/api/lexirise/decks'){
     const result=request.method()==='GET'?{decks:[{id:active==='first'?11:active==='second'?22:33,title:active+' destination'}]}:{deck:{id:body.deck_id??44,title:active+' destination'}};
     if(deckMode===(request.method()==='GET'?'hold-get':'hold-post')){deckMode='normal';releaseDeck=()=>respond(result);return;}
     if(['GET','POST'].includes(request.method()))return respond(result);
    }
    if(path==='/api/lines/1/lexirise'&&request.method()==='POST'){
     const account=active;
     const complete=()=>{sent[account]['line:1']=account==='first'?11:account==='second'?22:33;return respond({deck_id:sent[account]['line:1'],audio_included:!unvoiced});};
     if(exportMode==='hold'){releaseExport=complete;return;}
     if(exportMode==='conflict')return respond({detail:'Synthetic account conflict'},409);
     if(exportMode==='network')return route.abort('failed');
     return complete();
    }
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
    unexpected.push(request.method()+' '+path);return respond({detail:'Unexpected fixture route'},500);
   });
   await page.goto(preview.origin);
   await page.waitForFunction(()=>document.querySelector('select[aria-label="Target language"]')?.disabled);
   for(let i=0;i<100&&!releaseLanguageRead;i++)await page.waitForTimeout(20);
   assert(releaseLanguageRead,'Initial account-language read is held after the capture snapshot');
   assert.equal(await page.getByLabel('Target language',{exact:true}).isDisabled(),true,'The target selector remains disabled while its account-language read is held');
   await releaseLanguageRead();
   await page.waitForFunction(()=>document.querySelector('select[aria-label="Game"]')?.value==='genshin');
   captureGame='zzz';
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   const send=page.locator('.current-line .lexirise-send');
   await send.waitFor();
   await send.click();
   await page.waitForTimeout(100);
   assert.equal(requests.filter(r=>r.path==='/api/lines/1/lexirise').at(-1).account,'first','Initial missing account resolves to current account before export');
   await page.getByText('Sentence and voice saved in Lexirise · Zenless Zone Zero.',{exact:true}).waitFor({timeout:5000});

   const updatePanel=page.getByRole('region',{name:'Automatic data update status'});
   await updatePanel.locator('summary').click();
   const details=await updatePanel.locator('details').evaluate(el=>({width:el.getBoundingClientRect().width,parent:el.parentElement.getBoundingClientRect().width,fits:el.scrollWidth<=el.clientWidth+1}));
   assert(details.fits&&details.width>details.parent*.8,'Expanded update details use the full row, not a narrow right column');
   await updatePanel.screenshot({path:`${preview.output}/update-details-${name}-${width}.png`});
   await updatePanel.locator('summary').click();
   await page.screenshot({path:`${preview.output}/main-${name}-${width}.png`});
   await page.getByRole('button',{name:'Capture setup',exact:true}).click();
   const captureSettings=page.getByRole('dialog',{name:'Capture setup',exact:true});
   await captureSettings.getByLabel('Include unvoiced dialogue',{exact:true}).check();
   await captureSettings.getByRole('button',{name:'Save capture settings',exact:true}).click();
   await captureSettings.waitFor({state:'hidden'});
   assert.equal(settings.capture_unvoiced,true,'Capture toggle is saved through local settings');
   await page.locator('.current-line .reading-hanzi').click();
   await page.waitForTimeout(100);
   assert(releaseOld,'Old-account lookup is pending');
   await page.getByRole('button',{name:'Account settings',exact:true}).click();
   const panel=page.getByRole('dialog',{name:'Lexirise account settings'});
   const accountGeometry=await panel.evaluate(el=>{
    const account=el.querySelector('fieldset'),heading=el.querySelector('[data-slot="dialog-header"]');
    const bounds=el.getBoundingClientRect();
    return {fits:el.scrollWidth<=el.clientWidth+1,width:bounds.width,
     gap:account.getBoundingClientRect().top-heading.getBoundingClientRect().bottom};
   });
   assert(accountGeometry.fits&&accountGeometry.width<=Math.min(width,700),'Account controls remain compact and fit the viewport');
   assert(accountGeometry.gap>=0&&accountGeometry.gap<90,'Account fields follow the heading without an empty wizard row');
   await panel.screenshot({path:`${preview.output}/account-${name}-${width}.png`});
   await panel.getByLabel('Active Lexirise account').selectOption('second');
   await panel.getByText('Selected account loaded.',{exact:true}).waitFor();
   await panel.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
   await page.locator('.current-line .reading-hanzi').click();
   await page.locator('.word-sheet-body').getByText('SECOND ACCOUNT ONLY',{exact:true}).waitFor();
   await releaseOld();
   assert.equal(await page.getByText('FIRST ACCOUNT ONLY',{exact:true}).count(),0,'Old response cannot populate the new account');
   assert(requests.some(r=>r.path.endsWith('/lookup')&&r.account==='second'));
   await page.keyboard.press('Escape');
   const switchAccount=async account=>{
    await page.getByRole('button',{name:'Account settings',exact:true}).click();
    const panel=page.getByRole('dialog',{name:'Lexirise account settings'});
    await panel.getByLabel('Active Lexirise account').selectOption(account);
    await panel.getByText('Selected account loaded.',{exact:true}).waitFor();
    await panel.getByLabel('Game export destination').locator('option').filter({hasText:account+' destination'}).waitFor({state:'attached'});
    assert.equal(await panel.getByLabel('Game export destination').locator('option').filter({hasText:(account==='first'?'second':'first')+' destination'}).count(),0,'Decks belong to the selected account');
    await panel.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
   };
   // Retry failures clear busy, and synchronous clicks still dispatch once.
   for(const failure of ['conflict','network']){
    exportMode=failure;const before=requests.filter(r=>r.path==='/api/lines/1/lexirise').length;
    await send.evaluate(el=>{el.click();el.click();});
    await page.waitForFunction(()=>document.querySelector('.current-line .lexirise-send')?.getAttribute('aria-busy')==='false');
    assert.equal(requests.filter(r=>r.path==='/api/lines/1/lexirise').length,before+1);
    assert.equal(await send.isEnabled(),true,'Failed export becomes retryable');
   }
   exportMode='hold';await send.click();await page.waitForTimeout(100);assert(releaseExport);
   await switchAccount('first');await switchAccount('second');await releaseExport();
   await page.waitForFunction(()=>document.querySelector('.current-line .lexirise-send')?.getAttribute('aria-busy')==='false');
   assert.equal(await page.getByText('Sentence and voice saved in Lexirise · Zenless Zone Zero.',{exact:true}).count(),0,'Old export feedback cannot appear under a different account');
   assert.equal(await send.getAttribute('aria-busy'),'false');
   assert.equal(await send.isEnabled(),true,'A→B→A rejects a completion from the previous account generation');
   await switchAccount('first');await switchAccount('second');
   assert.equal(await send.isEnabled(),false,'Returning to the exported account loads its own sent state');
   exportMode='success';await switchAccount('legacy');await send.click();
   await page.getByText('Sentence and voice saved in Lexirise · Zenless Zone Zero.',{exact:true}).waitFor();
   assert.equal(requests.filter(r=>r.path==='/api/lines/1/lexirise').at(-1).account,'legacy');
   await switchAccount('first');
   // Every deck load gets a fresh account scope; both old reads and writes are
   // discarded after a switch, including a round trip to the same identifier.
   await page.getByRole('button',{name:'Account settings',exact:true}).click();
   const deckPanel=page.getByRole('dialog',{name:'Lexirise account settings'});
   const chooseInPanel=async account=>{
    await deckPanel.getByLabel('Active Lexirise account').selectOption(account);
    await deckPanel.getByText('Selected account loaded.',{exact:true}).waitFor();
    await deckPanel.getByLabel('Game export destination').locator('option').filter({hasText:account+' destination'}).waitFor({state:'attached'});
   };
   await deckPanel.getByLabel('Game export destination').locator('option').filter({hasText:'first destination'}).waitFor({state:'attached'});
   deckMode='hold-get';releaseDeck=null;await deckPanel.getByRole('button',{name:'Reload destinations',exact:true}).click();
   await page.waitForTimeout(100);assert(releaseDeck);await chooseInPanel('second');await releaseDeck();
   assert.equal(await deckPanel.getByLabel('Game export destination').locator('option').filter({hasText:'first destination'}).count(),0,'Old A deck response does not replace B destinations');
   await chooseInPanel('first');await deckPanel.getByLabel('Game export destination').selectOption('11');
   deckMode='hold-post';releaseDeck=null;const deckWritesBefore=writes.filter(w=>w.path==='/api/lexirise/decks').length;
   await deckPanel.getByRole('button',{name:'Use selected deck',exact:true}).evaluate(el=>{el.click();el.click();});
   await page.waitForTimeout(100);assert(releaseDeck);assert.equal(writes.filter(w=>w.path==='/api/lexirise/decks').length,deckWritesBefore+1,'Deck double click dispatches once');
   await chooseInPanel('second');await chooseInPanel('first');await releaseDeck();
   await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
   assert.equal(await deckPanel.getByText('Destination saved for this account.',{exact:true}).count(),0,'Previous A generation cannot report saved in the new A generation');
   await deckPanel.getByLabel('Game export destination').selectOption('11');
   await deckPanel.getByRole('button',{name:'Use selected deck',exact:true}).click();
   await deckPanel.getByText('Destination saved for this account.',{exact:true}).waitFor();
   assert.deepEqual(writes.filter(w=>w.path==='/api/lexirise/decks').at(-1).body,{game:'zzz',language:'en',deck_id:11});
   await deckPanel.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
   configured=false;
   const unconfiguredResponse=page.waitForResponse(r=>r.url().endsWith('/api/snapshot'));
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));await unconfiguredResponse;
   const exportsBefore=requests.filter(r=>r.path==='/api/lines/1/lexirise').length;
   assert.equal(await send.isEnabled(),false,'Unconfigured export stays disabled');await send.evaluate(el=>el.click());
   assert.equal(requests.filter(r=>r.path==='/api/lines/1/lexirise').length,exportsBefore,'Unconfigured account cannot export');
   configured=true;await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   assert.deepEqual(unexpected,[],'Every API route must be explicitly mocked');
   await page.getByRole('button',{name:'Settings',exact:true}).click();
   const setup=page.getByRole('dialog',{name:'Settings'});
   await setup.locator('.language-table button').first().waitFor();
   assert.equal(writes.filter(w=>w.path.endsWith('/languages')).length,0,'Opening setup never prepares languages');
   await setup.getByRole('button',{name:'Prepare language',exact:true}).click();
   await setup.getByRole('button',{name:'Use this language',exact:true}).waitFor();
   assert.deepEqual(writes.filter(w=>w.path.endsWith('/languages')),[{path:'/api/setup/games/zzz/languages',body:{locale:'zh-Hans',action:'prepare',target:'en'}}]);
   await setup.locator('summary').filter({hasText:'Keep mobile library updated'}).click();
   const automaticPanel=setup.getByRole('region',{name:'Automatic mobile exports'});
   await automaticPanel.getByLabel('Keep mobile library updated',{exact:true}).check();
   await automaticPanel.getByLabel('Export folder',{exact:true}).fill('F:/Private cloud/Mobile Libraries');
   await automaticPanel.getByLabel('Japanese',{exact:true}).check();
   await automaticPanel.getByLabel('Japanese translation',{exact:true}).selectOption('fr');
   await automaticPanel.getByRole('button',{name:'Save settings',exact:true}).click();
   await automaticPanel.getByRole('button',{name:'Pause',exact:true}).waitFor();
   assert.deepEqual(automatic.languages,{ja:'fr'});assert.equal(automatic.enabled,true);
   await automaticPanel.getByRole('button',{name:'Pause',exact:true}).click();await automaticPanel.getByRole('button',{name:'Resume',exact:true}).waitFor();
   assert(await automaticPanel.getByText('Not detected — install this voice language in the game/launcher',{exact:true}).isVisible());
   assert.equal(writes.filter(w=>w.path.includes('automatic-mobile-export')&&w.body.action==='save').length,1);
   assert(await automaticPanel.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Automatic export controls fit the viewport');
   await setup.getByText('Advanced',{exact:true}).click();
   const rebuilt=page.waitForResponse(r=>r.url().endsWith('/languages')&&r.request().method()==='POST');
   await setup.getByRole('button',{name:'Rebuild table',exact:true}).click();await rebuilt;
   assert.deepEqual(writes.filter(w=>w.path.endsWith('/languages')).at(-1).body,{locale:'zh-Hans',action:'rebuild',target:'en'},'Explicit rebuild has a distinct forced operation');
   assert(!writes.some(w=>w.path==='/api/lexirise/settings'),'Read/switch/setup does not write reading preferences');
   assert.equal(writes.filter(w=>w.path==='/api/lexirise/decks').length,2,'Only explicit destination buttons write decks');
   assert(await setup.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Language setup fits viewport');
   await setup.screenshot({path:`${preview.output}/languages-${name}-${width}.png`});
   await setup.getByRole('button',{name:'General & Updates',exact:true}).click();
   const writesBefore=writes.length;
   for(const [locale,label] of [['nl','Instellingen'],['zh-Hans','设置'],['zh-Hant','設定']]){await page.getByRole('dialog').locator('select').selectOption(locale);await page.getByRole('dialog',{name:label,exact:true}).waitFor();assert.equal(await page.locator('html').getAttribute('lang'),locale);}
   assert.equal(writes.length,writesBefore,'Interface language is local and never changes learning/account data');
   await page.getByRole('dialog').locator('select').selectOption('en');
   await page.keyboard.press('Escape');
   await page.getByRole('dialog',{name:'Settings',exact:true}).waitFor({state:'hidden'});
   const target=page.getByLabel('Target language',{exact:true});
   const picker=page.getByRole('region',{name:'Games and target language'});
   const targets=()=>target.locator('option').evaluateAll(options=>options.map(option=>option.value).sort());
   assert.deepEqual(await targets(),['en','zh'],'Lexirise target picker only offers account languages');
   await target.selectOption('en');
   await picker.locator('.game-library > summary').click();
   const cards=page.getByRole('navigation',{name:'Game transcript'});
   assert.equal(await cards.getByRole('button').count(),11,'English shows all eleven voiced games');
   await picker.screenshot({path:`${preview.output}/game-picker-all-${name}-${width}.png`});
   await picker.getByRole('searchbox',{name:'Search games'}).fill('witcher');
   assert.equal(await cards.getByRole('button').count(),1);
   await cards.getByRole('button').click();
   assert.equal(await picker.getByText('The Witcher 3: Wild Hunt · Supported subtitles',{exact:true}).count(),1);
   assert(await picker.getByText('Different from target',{exact:false}).count()>0,'Subtitle differences are labelled');
   await picker.getByRole('searchbox',{name:'Search games'}).fill('');
   await picker.getByRole('button',{name:'Add language to Lexirise',exact:true}).click();
   const addChoice=picker.getByLabel('Language to add',{exact:true});
   assert.equal(await addChoice.locator('option[value="en"]').count(),0,'Already enabled languages are not offered for addition');
   assert.equal(await addChoice.locator('option[value="th"]').count(),0,'Subtitle-only languages are not offered for addition');
   await addChoice.selectOption('ja');failLanguageWrite=true;
   await picker.getByRole('button',{name:'Add to my Lexirise account',exact:true}).evaluate(button=>{button.click();button.click();});
   await picker.getByRole('alert').filter({hasText:'Synthetic language save failed'}).waitFor();
   assert.deepEqual(await targets(),['en','zh'],'Failed account save does not expose an unowned language');
   failLanguageWrite=false;
   await picker.getByRole('button',{name:'Add to my Lexirise account',exact:true}).click();
   await target.locator('option[value="ja"]').waitFor({state:'attached'});
   assert.deepEqual(accountLanguages.first,['en','zh','ja'],'Adding preserves existing languages');
   assert.equal(await target.inputValue(),'ja');
   assert.deepEqual(writes.filter(w=>w.path==='/api/lexirise/settings').at(-1).body,{languages:['en','zh','ja']},'Only languages are written');
   const settingsWrites=writes.filter(w=>w.path==='/api/lexirise/settings').length;
   await page.getByLabel('Reading',{exact:true}).selectOption('migaku');
   assert.deepEqual(await targets(),['de','en','es','fr','it','ja','ko','nl','pl','pt','ru','zh'],'Independent mode shows every voiced language once');
   await target.selectOption('nl');
   assert.equal(await cards.getByRole('button').count(),2,'Dutch only offers the two games with Dutch voice');
   assert.equal(await picker.getByRole('button',{name:'Add language to Lexirise',exact:true}).count(),0);
   assert.equal(writes.filter(w=>w.path==='/api/lexirise/settings').length,settingsWrites,'Browsing independent mode never writes account preferences');
   await picker.screenshot({path:`${preview.output}/game-picker-${name}-${width}.png`});
   await page.evaluate(()=>{document.documentElement.style.zoom='1.5';});
   assert(await picker.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Picker fits at 150% zoom');
   await page.evaluate(()=>{document.documentElement.style.zoom='';});
   await page.getByLabel('Reading',{exact:true}).selectOption('lexirise');
   await target.locator('option[value="ja"]').waitFor({state:'attached'});
   // Account changes must clear the previous account's list, including no-game languages.
   accountLanguages.second=['nl'];active='second';generation++;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   await target.locator('option[value="nl"]').waitFor({state:'attached'});
   assert.deepEqual(await targets(),['nl']);
   accountLanguages.second=['la'];
   await picker.getByRole('button',{name:'Reload languages',exact:true}).click();
   await target.locator('option[value="la"]').waitFor({state:'attached'});
   assert.equal(await cards.getByRole('button').count(),0,'An account language without game voices shows an empty game list');
   const waitForHeldRead=async()=>{for(let i=0;i<100;i++){if(releaseLanguageRead)return;await page.waitForTimeout(20);}throw Error('Expected held language read');};
   holdLanguageRead=true;releaseLanguageRead=null;
   await picker.getByRole('button',{name:'Reload languages',exact:true}).click();await waitForHeldRead();
   active='first';generation++;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   await target.locator('option[value="ja"]').waitFor({state:'attached'});
   await releaseLanguageRead();
   assert.deepEqual(await targets(),['en','ja','zh'],'Delayed reads cannot leak another account\'s languages');
   const beforeStaleAdd=writes.filter(w=>w.path==='/api/lexirise/settings').length;
   await picker.getByLabel('Language to add',{exact:true}).selectOption('nl');
   holdLanguageRead=true;releaseLanguageRead=null;
   await picker.getByRole('button',{name:'Add to my Lexirise account',exact:true}).click();await waitForHeldRead();
   active='second';generation++;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   await target.locator('option[value="la"]').waitFor({state:'attached'});
   await releaseLanguageRead();
   assert.equal(writes.filter(w=>w.path==='/api/lexirise/settings').length,beforeStaleAdd,'Switching accounts cancels a pending add before its write');
   // Certified silent dialogue remains readable and exportable without a fake
   // missing-voice error or promising an audio upload.
   unvoiced=true;captureGame='zzz';active='first';generation++;delete sent.first['line:1'];
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   await page.getByLabel('Game',{exact:true}).selectOption('zzz');
   await page.locator('.current-line').getByText('Unvoiced dialogue',{exact:true}).waitFor();
   assert.equal(await page.locator('.current-line').getByRole('button',{name:'Original voice unavailable',exact:true}).count(),0);
   await send.click();
   await page.getByText('Sentence saved in Lexirise · Zenless Zone Zero.',{exact:true}).waitFor();
   assert.deepEqual(unexpected,[],'No unexpected API routes during the full scenario');
   console.log(`${name}: isolated account responses and manual per-language setup ${width} passed`);
   await context.close();
  }
  await browser.close();browser=null;
 }
}finally{
 await preview.stop();
}
