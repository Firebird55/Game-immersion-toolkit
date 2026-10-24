import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdirSync,readFileSync} from 'node:fs';
import {chromium,firefox} from 'playwright';
const port=4322,server=spawn(process.execPath,['node_modules/wrangler/bin/wrangler.js','dev','--config','dist/server/wrangler.json','--port',String(port),'--ip','127.0.0.1'],{stdio:['ignore','pipe','pipe']});
let browser;
mkdirSync('output/playwright',{recursive:true});
try{
 await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Setup preview startup timeout')),30000);server.stdout.on('data',b=>{if(String(b).includes('localhost:'+port)||String(b).includes('127.0.0.1:'+port)){clearTimeout(timer);resolve();}});server.stderr.on('data',b=>process.stderr.write(b));server.once('error',reject);});
 for(const[name,engine]of [['chromium',chromium],['firefox',firefox]]){
  browser=await engine.launch({headless:true});
  for(const[width,height,dpr]of [[1280,900,1],[390,844,1],[320,568,1],[640,480,2],[640,360,2],[568,320,1],[768,1024,1.25]]){
   const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:dpr}),page=await context.newPage(),writes=[],unexpected=[];
   let pickerAttempts=0,setupOffline=false,exportRevision=0,exportLocale='ja';
   const fixtureContext={runtime_id:'setup-fixture',state_version:0,account_generation:0};
   const exportScope=game=>'fixture-'+game+'-'+exportRevision;
   const region={left:.1,top:.6,width:.8,height:.25};
   const settings={nte_region:region,honkai3_region:region,preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,cyberpunk_region:region,cyberpunk_tip_region:region,wuwa_region:region,wuwa_tip_region:region,wuwa_cinematic_region:region,witcher3_region:region,witcher3_tip_region:region,auto_start:false};
   const games=Object.entries({zzz:'Zenless Zone Zero',pragmata:'PRAGMATA',starrail:'Honkai: Star Rail',genshin:'Genshin Impact',endfield:'Arknights: Endfield',cyberpunk:'Cyberpunk 2077',wuwa:'Wuthering Waves',witcher3:'The Witcher 3',nte:'Neverness to Everness'}).map(([id,title])=>({id,title,configured_path:null,detected_path:id==='zzz'?'F:/Games/ZZZ':null,folder_state:id==='zzz'?'detected':'missing',folder_hint:'Choose your installed game folder.',voice_state:'missing',voice_hint:id==='honkai3'?'Coverage limited to verified catalog 4.7 dialogue.':'Install the Mandarin voice pack in your game launcher.',tools_missing:['nte','endfield'].includes(id)?['.NET 10 SDK','NTE reader']:['Voice decoder'],index_ready:false,indexed_lines:0,audio_ready:false,index_message:'Ready for setup',update_state:'waiting',update_message:'Prepare your game tools',progress:100,last_checked:null,needs_attention:false}));
   games.find(g=>g.id==='nte').catalog_message='Catalog update unavailable or incompatible; using the last complete catalog.';
   games.find(g=>g.id==='nte').catalog_warning=true;
   games.find(g=>g.id==='cyberpunk').expansion_message='Phantom Liberty needs its Mandarin voice archive. Install the Simplified Chinese language pack through your game launcher, then refresh.';
   games.find(g=>g.id==='cyberpunk').expansion_state='missing_voice';
   const setup={mobile_export:{state:'idle',progress:0,message:'Ready',destinationFolder:'F:/Exports'},completed:false,version:'fixture',games,auto_start:false,free_gb:80,lexirise_configured:false,jobs:{},native:{},capture_check:null,requirements:[{id:'ocr',title:'Subtitle OCR',ready:true,help:''},{id:'audio',title:'Audio conversion',ready:true,help:''}]};
   await page.routeWebSocket('ws://127.0.0.1:8766/api/ws',()=>{});
   await page.route('http://127.0.0.1:8766/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method(),body=request.postData()?JSON.parse(request.postData()):{};
    if(method==='OPTIONS'){await route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'}});return;}
    let status=200,value={};
    if(method==='POST'){writes.push({path,body,headers:request.headers()});assert.equal(request.headers()['x-proxy-transcript'],'setup');}
    if(method==='POST'&&path.includes('/mobile-export')){
     const selected=path.startsWith('/api/setup/games/')?path.split('/')[4]:body.game??'zzz';
     if(request.headers()['x-proxy-transcript-export-scope']!==exportScope(selected)){
      await route.fulfill({status:409,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify({detail:'Account or learning language changed. Reload Setup before retrying.'})});return;
     }
    }
    if(path==='/api/snapshot')value={context:fixtureContext,status:{capture:{running:false,phase:'stopped',message:'Synthetic capture',active_game:null,visible_text_ids:[]},textmaps:{ready:false,state:'not_ready',message:'Choose a game',entry_count:0},audio:{ready:false,message:'fixture'},settings,session:{id:'fixture',line_count:0,total_line_count:0}},lines:[],lexirise:{configured:false,sent:{}}};
    else if(path==='/api/status')value={capture:{running:false,phase:'stopped',message:'Synthetic capture',active_game:null,visible_text_ids:[]},textmaps:{ready:false,state:'not_ready',message:'Choose a game',entry_count:0},audio:{ready:false,message:'fixture'},settings,session:{id:'fixture',line_count:0,total_line_count:0}};
    else if(path==='/api/setup'){if(setupOffline){await route.abort();return;}const selected=url.searchParams.get('game')??'zzz';value={...setup,mobile_export:{...setup.mobile_export,scope:exportScope(selected),sourceLocale:exportLocale,selectedGame:selected}};}
    else if(/^\/api\/setup\/games\/[^/]+\/languages$/.test(path)&&method==='GET'){
     const selected=path.split('/')[4];assert(games.some(game=>game.id===selected&&game.id!=='hito'),'Unexpected language fixture game: '+selected);
     value={context:fixtureContext,selected:null,enabled_languages:null,targets:{},translation_locales:['en','zh-Hans'],locales:[
      {locale:'zh-Hans',language:'zh',name:'Simplified Chinese',reader_available:true,prepared:null,table_bytes:0,reclaimable_bytes:0,voice_state:'not_checked'}]};
    }
    else if(path==='/api/setup/report')value={version:'fixture',platform:'Windows',requirements:{ocr:true},games:[{id:'zzz',folder_state:'configured'}]};
    else if(path==='/api/setup/games/zzz'){
     if(body.path==='F:/wrong'){status=400;value={detail:'Required game files were not found. Previous folder kept.'};}
     else{games[0].configured_path=body.use_automatic?null:body.path;games[0].folder_state=body.use_automatic?'detected':'configured';value=setup;}
    }else if(path==='/api/setup/games/zzz/tools'){games[0].tools_missing=[];setup.jobs.zzz={state:'ready',message:'Tools ready',progress:100};value={started:true};}
    else if(path==='/api/setup/games/zzz/refresh'){games[0].index_ready=true;games[0].indexed_lines=3;games[0].audio_ready=true;games[0].voice_state='present';games[0].update_message='Synthetic game data refreshed';value={started:true};}
    else if(path.endsWith('/mobile-export/preview')){value={estimatedBytes:body.include_audio?5e9:4096,estimateLowBytes:3e9,estimateHighBytes:8e9,workingBytes:16e9,freeBytes:80e9,rows:3,basis:'Synthetic estimate'};}
    else if(path==='/api/setup/mobile-export/browse'){
     pickerAttempts++;
     if(pickerAttempts<=2){setup.mobile_export.browseActive=true;setup.mobile_export.browsePhase='starting';}
     else{setup.mobile_export.destinationFolder='E:/Mobile libraries';setup.mobile_export.browseActive=false;}
     value={started:true};
    }
    else if(path==='/api/setup/mobile-export/browse/cancel'){setup.mobile_export.browseActive=false;setup.mobile_export.browsePhase=null;setup.mobile_export.browseMessage='Folder browser closed. You can paste a destination or try Browse again.';value={cancelled:true};}
    else if(path==='/api/setup/games/zzz/mobile-export'){setup.mobile_export=body.include_audio?{...setup.mobile_export,state:'exporting',game:'zzz',progress:42,message:'Synthetic export in progress',estimatedCatalogBytes:4096,total:3}:{...setup.mobile_export,state:'complete',game:'zzz',progress:100,message:'Synthetic export complete',folder:'F:/Exports/synthetic',bundle:'F:/Exports/synthetic/Synthetic Game - Mandarin - Mobile Library.zip',bytes:4096,coverage:{dialogue:3,exportedVoices:0}};value={started:true};}
    else if(path==='/api/setup/mobile-export/cancel'){setup.mobile_export={...setup.mobile_export,state:'cancelled',message:'Synthetic export cancelled'};value={cancelled:true};}
    else if(path==='/api/setup/native/checks'){setup.capture_check=true;value={started:true};}
    else if(path.startsWith('/api/setup/native/'))value={started:true};
    else if(path==='/api/setup/complete'){setup.completed=true;setup.auto_start=body.auto_start;value={completed:true};}
    else if(path==='/api/lines'||path==='/api/favorites')value=[];
    else if(path==='/api/lexirise')value={context:fixtureContext,account:'legacy',configured:false,sent:{},decks:{}};
    else {unexpected.push(method+' '+path);status=500;value={detail:'Unexpected setup fixture route'};}
    await route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(value)});
   });
   await page.goto('http://localhost:'+port);
   const dialog=page.getByRole('dialog',{name:'Settings'});
   await dialog.waitFor();
   await dialog.locator('.language-table').waitFor();
   assert.equal(await dialog.getByRole('alert').count(),0,'All setup data must load before testing folder validation');
   await dialog.getByText('Change installation folder',{exact:true}).click();
   const field=dialog.getByLabel('Installed game folder');
   await field.fill('F:/wrong');await dialog.getByRole('button',{name:'Save game folder',exact:true}).click();
   await dialog.getByRole('alert').waitFor();assert.equal(games[0].configured_path,null);
   await field.fill('F:/Games/ZZZ');await dialog.getByRole('button',{name:'Save game folder',exact:true}).click();
   await dialog.getByText('Folder saved on this PC. Prepare game tools if needed, then refresh game data.',{exact:true}).waitFor();
   assert.equal(games[0].configured_path,'F:/Games/ZZZ');
   await dialog.getByRole('button',{name:'Install game tools',exact:true}).click();
   await dialog.getByRole('button',{name:'Refresh game data',exact:true}).click();
   await dialog.getByText('3 pairs',{exact:true}).waitFor();
   await dialog.locator('.toolkit-mobile-export > summary').click();
   await dialog.getByText('≈ 5.00 GB',{exact:true}).waitFor();
   await dialog.getByRole('button',{name:'Browse',exact:true}).click();
   await dialog.getByText('Starting the folder browser. You can close it here if no window appears.',{exact:true}).waitFor();
   assert(await dialog.getByLabel('Save libraries to',{exact:true}).isDisabled());
   setup.mobile_export.browsePhase='open';
   await dialog.getByText('Choose a folder in the Windows dialog. If it stalls, close it here and paste a path.',{exact:true}).waitFor();
   await dialog.getByRole('button',{name:'Close picker',exact:true}).click();
   await page.waitForFunction(()=>!document.querySelector('#mobile-export-folder').disabled);
   assert.equal(await dialog.getByLabel('Save libraries to',{exact:true}).inputValue(),'F:/Exports');
   await dialog.getByRole('button',{name:'Browse',exact:true}).click();
   await dialog.getByRole('button',{name:'Close picker',exact:true}).waitFor();
   setupOffline=true;
   await dialog.getByText('The companion disconnected. Start it again and reopen Setup.',{exact:true}).waitFor();
   assert(await dialog.getByLabel('Save libraries to',{exact:true}).isEnabled());
   assert.equal(await dialog.getByRole('button',{name:'Close picker',exact:true}).count(),0);
   setupOffline=false;
   await dialog.getByRole('button',{name:'Browse',exact:true}).click();
   await page.waitForFunction(()=>document.querySelector('#mobile-export-folder').value==='E:/Mobile libraries');
   await dialog.getByRole('button',{name:'Export mobile library',exact:true}).click();await dialog.getByText('Synthetic export in progress',{exact:true}).waitFor();
   assert.equal(await dialog.getByRole('progressbar',{name:'Mobile export progress'}).getAttribute('value'),'42');
   assert.deepEqual(writes.find(w=>w.path.endsWith('/mobile-export')).body,{include_audio:true,destination_folder:'E:/Mobile libraries'});
   await dialog.getByRole('button',{name:'Cancel export',exact:true}).click();await dialog.getByText('Synthetic export cancelled',{exact:true}).waitFor();
   await dialog.getByLabel('Original game voices',{exact:false}).uncheck();await dialog.getByRole('button',{name:'Resume export',exact:true}).click();await dialog.getByText('Ready to transfer',{exact:true}).waitFor();
   await dialog.getByText('Copy this library file to your phone',{exact:false}).waitFor();
   assert.deepEqual(writes.filter(w=>w.path.endsWith('/mobile-export')).at(-1).body,{include_audio:false,destination_folder:'E:/Mobile libraries'});await dialog.getByText('F:/Exports/synthetic/Synthetic Game - Mandarin - Mobile Library.zip',{exact:true}).waitFor();
   if(width===1280){
    const exportsBefore=writes.filter(w=>w.path.endsWith('/mobile-export')).length;
    await dialog.getByLabel('Save libraries to',{exact:true}).fill('F:/Unsaved old-language choice');
    exportRevision++;exportLocale='ko';setup.mobile_export={...setup.mobile_export,state:'idle',destinationFolder:'D:/Other-language transfer'};
    await page.waitForFunction(()=>document.querySelector('#mobile-export-folder')?.value==='D:/Other-language transfer');
    await dialog.getByText('≈ 5.00 GB',{exact:true}).waitFor();
    assert.equal(writes.filter(w=>w.path.endsWith('/mobile-export')).length,exportsBefore,'A scope refresh must not start an export');
    assert(writes.filter(w=>w.path.endsWith('/mobile-export/preview')).some(w=>w.headers['x-proxy-transcript-export-scope']===exportScope('zzz')));
   }
   assert.equal(await dialog.getByLabel('Game to configure',{exact:true}).locator('option[value=hito]').count(),0);
   for(const game of ['starrail','genshin','endfield']){
    await dialog.getByLabel('Game to configure',{exact:true}).selectOption(game);
    assert.equal(await dialog.getByLabel('Installed game folder').inputValue(),'');
    assert(await dialog.getByRole('button',{name:'Refresh game data',exact:true}).isDisabled());
   }
   await dialog.getByLabel('Game to configure',{exact:true}).selectOption('zzz');
   assert.equal(await dialog.getByLabel('Installed game folder').inputValue(),'F:/Games/ZZZ');
   for(const game of ['nte']){
    await dialog.getByLabel('Game to configure',{exact:true}).selectOption(game);
    if(game==='nte')assert.equal(await dialog.getByRole('link',{name:'Microsoft .NET 10 SDK'}).getAttribute('href'),'https://dotnet.microsoft.com/download/dotnet/10.0');
    else assert((await dialog.getByText(/Coverage limited to verified catalog 4.7 dialogue/).innerText()).includes('Coverage limited'));
    await dialog.getByText(games.find(g=>g.id===game).catalog_message,{exact:true}).waitFor();
   }
   await dialog.getByLabel('Game to configure',{exact:true}).selectOption('cyberpunk');
   await dialog.getByText(games.find(g=>g.id==='cyberpunk').expansion_message,{exact:true}).waitFor();
   await dialog.getByLabel('Game to configure',{exact:true}).selectOption('zzz');
   const box=await dialog.boundingBox();assert(box&&box.x>=0&&box.y>=0&&box.x+box.width<=width+1&&box.y+box.height<=height+1);
   assert(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Setup has horizontal overflow');
   if(name==='chromium'&&(width===1280||width===390))await dialog.screenshot({path:`output/playwright/toolkit-setup-${width===1280?'desktop':'mobile'}.png`});
   await dialog.getByRole('button',{name:'Next',exact:true}).click();
   await dialog.getByRole('button',{name:'Run OCR and display test',exact:true}).click();
   await dialog.getByText('OCR and display test passed.',{exact:true}).waitFor();
   await dialog.getByLabel('Start capture automatically when I open the toolkit').check();
   await dialog.getByRole('button',{name:'Next',exact:true}).click();
   await dialog.getByLabel('Reading mode',{exact:true}).selectOption('lexirise');
   await dialog.getByRole('button',{name:'Next',exact:true}).click();
   await dialog.getByRole('button',{name:'Set up local API key',exact:true}).click();
   assert.equal(await dialog.locator('input[type=password]').count(),0);
   await dialog.getByRole('button',{name:'General & Updates',exact:true}).click();
   const downloaded=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download setup report',exact:true}).click();
   const report=JSON.parse(readFileSync(await (await downloaded).path(),'utf8'));assert(!JSON.stringify(report).includes('F:/Games'));assert.equal(report.version,'fixture');
   await dialog.getByRole('button',{name:'Finish setup',exact:true}).click();await dialog.waitFor({state:'hidden'});
   assert.equal(setup.auto_start,true);assert.equal(await page.evaluate(()=>localStorage.getItem('proxy-transcript-reading-mode')),'lexirise');
   assert(writes.every(write=>write.path.startsWith('/api/setup/')),'Setup performed an account write');
   assert.deepEqual(writes.find(write=>write.path==='/api/setup/native/lexirise').body,{});
   await page.reload();await page.getByRole('button',{name:'Settings',exact:true}).waitFor();
   assert.equal(await page.getByRole('dialog',{name:'Settings'}).count(),0);
   assert.deepEqual(unexpected,[],'Every setup API route must be explicitly mocked');
   assert.equal(await page.getByRole('alert').count(),0,'Successful setup leaves no hidden fixture errors');
   await context.close();console.log(name+': first-run setup, folder validation, refresh, native actions, report and persistence '+width+'x'+height+' passed');
  }
  await browser.close();browser=null;
 }
}finally{await browser?.close();if(process.platform==='win32'){try{execFileSync('taskkill',['/PID',String(server.pid),'/T','/F'],{stdio:'ignore'});}catch{}}else server.kill();}
