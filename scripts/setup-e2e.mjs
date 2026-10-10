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
  for(const[width,height,dpr]of [[1280,900,1],[390,844,1],[320,568,1],[768,1024,1.25]]){
   const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:dpr}),page=await context.newPage(),writes=[];
   const region={left:.1,top:.6,width:.8,height:.25};
   const settings={preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,cyberpunk_region:region,cyberpunk_tip_region:region,wuwa_region:region,wuwa_tip_region:region,wuwa_cinematic_region:region,witcher3_region:region,witcher3_tip_region:region,auto_start:false};
   const games=Object.entries({zzz:'Zenless Zone Zero',pragmata:'PRAGMATA',hito:"Hito's World",cyberpunk:'Cyberpunk 2077',wuwa:'Wuthering Waves',witcher3:'The Witcher 3'}).map(([id,title])=>({id,title,configured_path:null,detected_path:id==='zzz'?'F:/Games/ZZZ':null,folder_state:id==='zzz'?'detected':'missing',folder_hint:'Choose your installed game folder.',voice_state:id==='hito'?'not_required':'missing',voice_hint:'Install the Mandarin voice pack in your game launcher.',tools_missing:id==='hito'?[]:['Voice decoder'],index_ready:false,indexed_lines:0,audio_ready:false,index_message:'Ready for setup',update_state:'waiting',update_message:'Prepare your game tools',progress:100,last_checked:null,needs_attention:false}));
   const setup={completed:false,version:'fixture',games,auto_start:false,free_gb:80,lexirise_configured:false,jobs:{},native:{},capture_check:null,requirements:[{id:'ocr',title:'Subtitle OCR',ready:true,help:''},{id:'audio',title:'Audio conversion',ready:true,help:''}]};
   await page.routeWebSocket('ws://127.0.0.1:8766/api/ws',()=>{});
   await page.route('http://127.0.0.1:8766/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method(),body=request.postData()?JSON.parse(request.postData()):{};
    let status=200,value={};
    if(method==='POST'){writes.push({path,body,headers:request.headers()});assert.equal(request.headers()['x-proxy-transcript'],'setup');}
    if(path==='/api/status')value={capture:{running:false,phase:'stopped',message:'Synthetic capture',active_game:null,visible_text_ids:[]},textmaps:{ready:false,state:'not_ready',message:'Choose a game',entry_count:0},audio:{ready:false,message:'fixture'},settings,session:{id:'fixture',line_count:0,total_line_count:0}};
    else if(path==='/api/setup')value=setup;
    else if(path==='/api/setup/report')value={version:'fixture',platform:'Windows',requirements:{ocr:true},games:[{id:'zzz',folder_state:'configured'}]};
    else if(path==='/api/setup/games/zzz'){
     if(body.path==='F:/wrong'){status=400;value={detail:'Required game files were not found. Previous folder kept.'};}
     else{games[0].configured_path=body.use_automatic?null:body.path;games[0].folder_state=body.use_automatic?'detected':'configured';value=setup;}
    }else if(path==='/api/setup/games/zzz/tools'){games[0].tools_missing=[];setup.jobs.zzz={state:'ready',message:'Tools ready',progress:100};value={started:true};}
    else if(path==='/api/setup/games/zzz/refresh'){games[0].index_ready=true;games[0].indexed_lines=3;games[0].audio_ready=true;games[0].voice_state='present';games[0].update_message='Synthetic game data refreshed';value={started:true};}
    else if(path==='/api/setup/native/checks'){setup.capture_check=true;value={started:true};}
    else if(path.startsWith('/api/setup/native/'))value={started:true};
    else if(path==='/api/setup/complete'){setup.completed=true;setup.auto_start=body.auto_start;value={completed:true};}
    else if(path==='/api/lines'||path==='/api/favorites')value=[];
    else if(path==='/api/lexirise')value={configured:false,sent:{},decks:{}};
    await route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(value)});
   });
   await page.goto('http://localhost:'+port);
   const dialog=page.getByRole('dialog',{name:'Toolkit setup'});
   await dialog.waitFor();
   const field=dialog.getByLabel('Installed game folder');
   await field.fill('F:/wrong');await dialog.getByRole('button',{name:'Save game folder',exact:true}).click();
   await dialog.getByRole('alert').waitFor();assert.equal(games[0].configured_path,null);
   await field.fill('F:/Games/ZZZ');await dialog.getByRole('button',{name:'Save game folder',exact:true}).click();
   await dialog.getByText('Folder: Verified',{exact:true}).waitFor();
   await dialog.getByRole('button',{name:'Install game tools',exact:true}).click();
   await dialog.getByRole('button',{name:'Refresh game data',exact:true}).click();
   await dialog.getByText('3 subtitle pairs indexed · Original voices ready',{exact:true}).waitFor();
   await dialog.getByLabel('Game to configure',{exact:true}).selectOption('hito');
   assert.equal(await dialog.getByLabel('Installed game folder').inputValue(),'');
   assert(await dialog.getByRole('button',{name:'Refresh game data',exact:true}).isDisabled());
   await dialog.getByLabel('Game to configure',{exact:true}).selectOption('zzz');
   assert.equal(await dialog.getByLabel('Installed game folder').inputValue(),'F:/Games/ZZZ');
   const box=await dialog.boundingBox();assert(box&&box.x>=0&&box.y>=0&&box.x+box.width<=width+1&&box.y+box.height<=height+1);
   assert(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Setup has horizontal overflow');
   if(name==='chromium'&&(width===1280||width===390))await dialog.screenshot({path:`output/playwright/toolkit-setup-${width===1280?'desktop':'mobile'}.png`});
   await dialog.getByRole('button',{name:'Next',exact:true}).click();
   await dialog.getByRole('button',{name:'Run OCR and display test',exact:true}).click();
   await dialog.getByText('OCR and display test passed.',{exact:true}).waitFor();
   await dialog.getByLabel('Start capture automatically when I open the toolkit').check();
   await dialog.getByRole('button',{name:'Next',exact:true}).click();
   await dialog.getByLabel('Reading mode',{exact:true}).selectOption('lexirise');
   await dialog.getByRole('button',{name:'Set up local API key',exact:true}).click();
   assert.equal(await dialog.locator('input[type=password]').count(),0);
   const downloaded=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download setup report',exact:true}).click();
   const report=JSON.parse(readFileSync(await (await downloaded).path(),'utf8'));assert(!JSON.stringify(report).includes('F:/Games'));assert.equal(report.version,'fixture');
   await dialog.getByRole('button',{name:'Finish setup',exact:true}).click();await dialog.waitFor({state:'hidden'});
   assert.equal(setup.auto_start,true);assert.equal(await page.evaluate(()=>localStorage.getItem('proxy-transcript-reading-mode')),'lexirise');
   assert(writes.every(write=>write.path.startsWith('/api/setup/')),'Setup performed an account write');
   assert.deepEqual(writes.find(write=>write.path==='/api/setup/native/lexirise').body,{});
   await page.reload();await page.getByRole('button',{name:'Setup',exact:true}).waitFor();
   assert.equal(await page.getByRole('dialog',{name:'Toolkit setup'}).count(),0);
   await context.close();console.log(name+': first-run setup, folder validation, refresh, native actions, report and persistence '+width+'x'+height+' passed');
  }
  await browser.close();browser=null;
 }
}finally{await browser?.close();if(process.platform==='win32'){try{execFileSync('taskkill',['/PID',String(server.pid),'/T','/F'],{stdio:'ignore'});}catch{}}else server.kill();}
