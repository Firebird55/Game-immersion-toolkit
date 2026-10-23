import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, symlinkSync, unlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {rm} from 'node:fs/promises';
import {dirname, delimiter, join, resolve} from 'node:path';
import net from 'node:net';
import {chromium, firefox} from 'playwright';

// Use the real canonical build in an isolated source tree. Never borrow generated
// public assets from the working checkout or supply missing files from npm at
// serving time. --built-root validates an independently extracted distribution.
const repository=process.cwd(),started=Date.now();
const builtArg=process.argv.indexOf('--built-root');
if(builtArg!==-1&&!process.argv[builtArg+1])throw Error('--built-root requires a directory');
const baseline=process.argv.includes('--baseline');
assert(!(baseline&&builtArg!==-1),'Baseline reproduction requires a clean source build');
const temporary=builtArg===-1?mkdtempSync(join(tmpdir(),'companion-source-build-')):null;
const root=temporary??resolve(process.argv[builtArg+1]);
const generated=['companion.js','companion.css','ocr','pairing'];
const environment={...process.env,PATH:dirname(process.execPath)+delimiter+process.env.PATH,WRANGLER_SEND_METRICS:'false',WRANGLER_WRITE_LOGS:'false',MINIFLARE_REGISTRY_PATH:join(root,'.wrangler/registry')};
let server,browser,serverOutput='',passed=false;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function npmCli(){
 const candidates=[process.env.npm_execpath,join(dirname(process.execPath),'node_modules/npm/bin/npm-cli.js'),join(dirname(process.execPath),'../lib/node_modules/npm/bin/npm-cli.js')].filter(Boolean);
 for(const command of execFileSync(process.platform==='win32'?'where.exe':'which',['npm'],{encoding:'utf8'}).trim().split(/\r?\n/)){
  const path=realpathSync(command);if(path.endsWith('.js'))candidates.push(path);
  candidates.push(join(dirname(path),'node_modules/npm/bin/npm-cli.js'));
 }
 const value=candidates.find(existsSync);if(!value)throw Error('Cannot locate the npm CLI beside the active Node runtime');return value;
}
async function runBuild(args,expectPreparationFailure=false){
 const child=spawn(process.execPath,args,{cwd:root,env:environment,stdio:['ignore','pipe','pipe']});
 let output='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>output+=b);
 const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
 if(expectPreparationFailure){
  assert.notEqual(code,0,'Canonical build accepted an asset preparation failure');
  assert(output.includes('SYNTHETIC_ASSET_PREPARATION_FAILURE'),'Build failed before reaching the controlled asset preparation failure');
  assert(!existsSync(join(root,'dist/server/wrangler.json')),'Frontend build ran after asset preparation failed');
 }else assert.equal(code,0,'Clean source frontend build failed: '+output.replaceAll(root,'<fixture>').replaceAll(repository,'<repository>').slice(-6000));
}
try{
 if(temporary){
  const files=execFileSync('git',['ls-files','-z'],{cwd:repository,encoding:'utf8'}).split('\0').filter(Boolean);
  for(const file of files){if(!existsSync(join(repository,file)))continue;mkdirSync(dirname(join(root,file)),{recursive:true});cpSync(join(repository,file),join(root,file));}
  // Windows junctions do not require developer mode or symlink privileges.
  symlinkSync(join(repository,'node_modules'),join(root,'node_modules'),process.platform==='win32'?'junction':'dir');
  for(const file of generated)assert(!existsSync(join(root,'public/mobile-capture',file)),'Source fixture unexpectedly contains generated assets: '+file);
  if(!baseline){
   const preparation=join(root,'scripts/prepare-mobile-assets.mjs'),original=readFileSync(preparation);
   writeFileSync(preparation,"throw Error('SYNTHETIC_ASSET_PREPARATION_FAILURE');\n"+original);
   try{await runBuild([npmCli(),'run','build'],true);}finally{writeFileSync(preparation,original);}
  }
  await runBuild(baseline?[join(root,'node_modules/vinext/dist/cli.js'),'build']:[npmCli(),'run','build']);
 }
 const assets=join(root,'dist/client/mobile-capture');
 for(const file of generated)assert(existsSync(join(assets,file)),(baseline?'BASELINE_MISSING_GENERATED_ASSETS: ':'Built distribution is missing generated assets: ')+file);
 const checks=JSON.parse(readFileSync(join(assets,'ocr/checksums.json'),'utf8'));
 const required=['companion.js','companion.css','pairing/qrcode.mjs','pairing/jsqr.mjs','pairing/fflate.mjs',...Object.keys(checks)];
 const port=await new Promise((resolve,reject)=>{const listener=net.createServer();listener.once('error',reject);listener.listen(0,'127.0.0.1',()=>{const port=listener.address().port;listener.close(()=>resolve(port));});});
 const base='http://127.0.0.1:'+port;
 server=spawn(process.execPath,[join(repository,'node_modules/wrangler/bin/wrangler.js'),'dev','--config',join(root,'dist/server/wrangler.json'),'--ip','127.0.0.1','--port',String(port),'--inspector-port','0'],{cwd:root,env:environment,stdio:['ignore','pipe','pipe']});
 server.stdout.on('data',b=>serverOutput+=b);server.stderr.on('data',b=>serverOutput+=b);
 server.on('error',error=>{serverOutput+=error.message;});
 let ready=false;
 for(let attempt=0;attempt<240;attempt++){
  if(server.exitCode!==null)break;
  try{if((await fetch(base+'/mobile-capture/index.html')).ok){ready=true;break;}}catch{}
  await delay(250);
 }
 assert(ready,'Built frontend did not start: '+serverOutput.replaceAll(root,'<fixture>').replaceAll(repository,'<repository>').slice(-4000));
 for(const [name,engine] of [['chromium',chromium],['firefox',firefox]]){
  browser=await engine.launch();
  const context=await browser.newContext({serviceWorkers:'block',locale:'en-US'}),page=await context.newPage(),missing=[],errors=[],unexpected=[];
  page.on('response',response=>{if(response.url().startsWith(base)&&response.status()===404)missing.push(new URL(response.url()).pathname);});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error'&&!message.text().includes('net::ERR'))errors.push(message.text());});
  await context.route('http://127.0.0.1:8766/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(route.request().method()!=='GET'||!['/api/snapshot','/api/status','/api/lexirise','/api/lines','/api/favorites','/api/setup'].includes(path)){
    unexpected.push(route.request().method()+' '+path);
    return route.fulfill({status:500,json:{detail:'Unexpected packaged browser API request'}});
   }
   if(path==='/api/setup')return route.fulfill({json:{completed:true,version:'fixture',games:[],requirements:[],jobs:{},native:{},auto_start:false,lexirise_configured:false,mobile_export:{state:'idle'},free_gb:10}});
   const region={left:.1,top:.6,width:.8,height:.25};
   const status={capture:{running:false,phase:'stopped',message:'Synthetic capture',active_game:null,visible_text_ids:[]},textmaps:{ready:false,state:'not_ready',message:'Fixture'},audio:{ready:false},settings:{auto_start:false,preferred_game:'auto',region,tip_region:region,cinematic_region:region},session:{id:'fixture',line_count:0,total_line_count:0}};
   const value=path==='/api/snapshot'?{context:{runtime_id:'build-fixture',state_version:0,account_generation:0},status,lines:[],lexirise:{configured:false,sent:{}}}:path==='/api/status'?status:path==='/api/lexirise'?{configured:false,sent:{}}:[];
   return route.fulfill({json:value,headers:{'Access-Control-Allow-Origin':'*'}});
  });
  await context.routeWebSocket('ws://127.0.0.1:8766/api/ws',()=>{});
  await page.goto(base+'/');
  await page.getByRole('button',{name:'Settings',exact:true}).waitFor({timeout:10000}).catch(async error=>{throw Error('Built desktop failed to mount: '+JSON.stringify({errors,body:(await page.locator('body').innerText()).slice(0,2000)}),{cause:error});});
  await page.goto(base+'/mobile-capture/index.html');
  await page.getByRole('heading',{name:'Your next line belongs here.'}).waitFor();
  // Fetch from the browser origin to prove the deployed worker serves all OCR,
  // pairing, reader JS and CSS assets. There is no test-server fallback.
  for(const file of required){
   const status=await page.evaluate(async path=>{const response=await fetch('/mobile-capture/'+path);await response.arrayBuffer();return response.status;},file);
   assert.equal(status,200,'Packaged asset was not served: '+file);
  }
  assert.deepEqual(missing,[],name+' requested missing packaged assets');
  assert.deepEqual(unexpected,[],name+' made unexpected API requests or attempted an account write');
  assert.deepEqual(errors,[],name+' mobile companion failed to load');
  await context.close();await browser.close();browser=null;
  console.log(name+': built desktop and mobile companions mounted; JS/CSS/OCR/pairing assets served without 404.');
 }
 passed=true;
 console.log(temporary?'Clean canonical source build includes all generated mobile assets.':'Extracted distribution serves its own generated mobile assets.');
}finally{
 await browser?.close();
 if(server&&server.exitCode===null){
  if(process.platform==='win32'){try{execFileSync('taskkill',['/PID',String(server.pid),'/T','/F'],{stdio:'ignore'});}catch{}}
  else server.kill();
  await Promise.race([new Promise(r=>server.once('close',r)),delay(5000)]);
 }
 if(temporary){
  assert.equal(realpathSync(dirname(temporary)),realpathSync(tmpdir()),'Cleanup must stay inside the owned temporary directory');
  // Unlink dependencies so recursive cleanup stays within the owned fixture.
  const dependencyLink=join(temporary,'node_modules');
  if(existsSync(dependencyLink)){assert(lstatSync(dependencyLink).isSymbolicLink());unlinkSync(dependencyLink);}
  await rm(temporary,{recursive:true,force:true,maxRetries:6,retryDelay:250});
 }
 mkdirSync(join(repository,'output/checks'),{recursive:true});
 writeFileSync(join(repository,'output/checks',baseline?'windows-source-build-baseline.json':temporary?'windows-source-build.json':'windows-packaged-assets.json'),JSON.stringify({check:baseline?'legacy-setup-build':temporary?'clean-source-build':'packaged-assets',platform:process.platform,elapsedMs:Date.now()-started,passed,nativeOcr:'OPEN: native Windows capture requires hardware verification'},null,2));
}
