import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,copyFileSync,rmSync,existsSync,readdirSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,sep} from 'node:path';
import net from 'node:net';
import {resolvePython} from './python-runtime.mjs';

if(process.platform!=='win32'){console.log('Prepared companion updates require Windows.');process.exit(0);}
const repository=process.cwd(),temporary=realpathSync.native(mkdtempSync(join(tmpdir(),'companion-update-')));
const python=execFileSync(resolvePython({root:repository}).command,['-B','-c','import sys; print(sys.executable)'],{encoding:'utf8'}).trim();
const children=[],fixture=join(repository,'scripts/fixtures/companion-update');
const port=()=>new Promise(resolve=>{const server=net.createServer();server.listen(0,'127.0.0.1',()=>{const value=server.address().port;server.close(()=>resolve(value));});});
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const json=(path,value)=>writeFileSync(path,JSON.stringify(value));
const powershell=process.env.PWSH||'powershell.exe';
async function ready(url){for(let i=0;i<100;i++){try{if((await fetch(url)).ok)return;}catch{}await wait(50);}throw Error('Fixture did not start');}
function child(command,args,options={}){const value=spawn(command,args,{stdio:['ignore','pipe','pipe'],...options});value.diagnostics='';value.stderr.on('data',chunk=>{value.diagnostics=(value.diagnostics+chunk).slice(-12000);});children.push(value);return value;}
const psQuote=value=>"'"+String(value).replaceAll("'","''")+"'";
function shell(command){return execFileSync(powershell,['-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',Buffer.from("$ProgressPreference='SilentlyContinue'; "+command,'utf16le').toString('base64')],{encoding:'utf8'});}
function identity(child,root){return JSON.parse(shell(`. ${psQuote(join(repository,'scripts/companion-runtime.ps1'))}; New-CompanionProcessRecord (Get-Process -Id ${child.pid}) ${psQuote(root)} | ConvertTo-Json -Compress`));}
function stopRecorded(root,exceptRouter=false){
 const record=join(root,'data/processes.json');if(!existsSync(record))return;
 shell(`. ${psQuote(join(repository,'scripts/companion-runtime.ps1'))}; $records=Read-CompanionProcesses ${psQuote(record)} ${psQuote(root)}; foreach($name in @($records.Keys)){if(${exceptRouter?"$name -ne 'router'":'$true'}){Stop-CompanionProcess $records[$name] ${psQuote(root)}}}`);
}
function terminate(child){if(child.exitCode===null&&!child.killed)child.kill();}

try{
 for(const mode of ['running','paused','resumed','resumed-at-quiesce','failed']){
  const fail=mode==='failed',resumed=mode.startsWith('resumed'),paused=mode==='paused'||resumed,expectedFailure=fail||resumed;
  const root=join(temporary,mode+' update'),source=join(root,'new source');
  for(const name of ['data','new source/backend','new source/scripts','new source/.openai'])mkdirSync(join(root,name),{recursive:true});
  for(const name of ['companion-runtime.ps1','retire-companion.ps1','companion-router.mjs'])copyFileSync(join(repository,'scripts',name),join(source,'scripts',name));
  copyFileSync(join(repository,'backend/check_environment.py'),join(source,'backend/check_environment.py'));
  for(const name of ['desktop_gateway.py','local_access.py'])copyFileSync(join(repository,'backend',name),join(source,'backend',name));
  copyFileSync(join(fixture,'backend.py'),join(source,'backend/main.py'));
  for(const [from,to]of [['frontend.mjs','fixture-front.mjs'],['install.mjs','install-fixture.mjs'],['build.mjs','build-fixture.mjs']])copyFileSync(join(fixture,from),join(source,'scripts',to));
  writeFileSync(join(source,'backend/__init__.py'),'');writeFileSync(join(source,'requirements.lock.txt'),'');
  writeFileSync(join(source,'VERSION'),'0.0.0-test');json(join(source,'.openai/hosting.json'),{});
  const packageValue={name:'game-immersion-toolkit',version:'0.0.0-test',type:'module',scripts:{postinstall:'node scripts/install-fixture.mjs',build:'node scripts/build-fixture.mjs'}};
  json(join(source,'package.json'),packageValue);json(join(source,'package-lock.json'),{name:packageValue.name,version:packageValue.version,lockfileVersion:3,requires:true,packages:{'':packageValue}});
  if(fail)writeFileSync(join(source,'backend/fail.flag'),'candidate must not activate');
  const oldPort=await port(),api=await port(),front=await port();
  const old=child(process.execPath,[join(fixture,'old-server.mjs'),String(oldPort),join(root,'data/events.log'),mode]);
  await ready('http://127.0.0.1:'+oldPort+'/api/health');
  const state=join(root,'data/companion-runtime.json');json(state,{version:1,active:{apiPort:oldPort,frontendPort:oldPort,python,source}});
  const router=child(process.execPath,[join(repository,'scripts/companion-router.mjs'),'--state',state,'--assets',join(root,'data/runtime-assets'),'--api-port',String(api),'--frontend-port',String(front)]);
  await ready('http://127.0.0.1:'+api+'/api/health');const oldRecord=identity(old,root);json(join(root,'data/processes.json'),{router:identity(router,root),backend:oldRecord,frontend:oldRecord});
  const update=child(powershell,['-NoProfile','-ExecutionPolicy','Bypass','-File',join(repository,'scripts/update-companion.ps1'),'-Root',root,'-SourceRoot',source,'-ApiPort',String(api),'-FrontendPort',String(front),'-ReadyTimeoutSeconds',fail?'3':'30']);
  let output='';const collect=b=>{output+=b;if(process.argv.includes('--verbose'))process.stdout.write(b);};update.stdout.on('data',collect);update.stderr.on('data',collect);
  let done=false;const completion=new Promise(resolve=>update.on('exit',code=>{done=true;resolve(code);}));
  const samples=[];
  while(!done){
   const response=await fetch('http://127.0.0.1:'+api+'/api/status');assert(response.ok,'The existing API went offline while preparing an update');samples.push(await response.json());await wait(60);
  }
  const code=await completion;
  if(code!==(expectedFailure?1:0)){
   const logs=join(root,'data/runtime-logs');
   if(existsSync(logs))for(const file of readdirSync(logs))if(file.endsWith('.log'))output+='\n'+file+': '+readFileSync(join(logs,file),'utf8').slice(-4000);
  }
  assert.equal(code,expectedFailure?1:0,output);
  assert(samples.some(sample=>sample.worker==='old'&&sample.capture.running===!paused),'The old capture state was not preserved during preparation');
  const current=await(await fetch('http://127.0.0.1:'+api+'/api/status')).json();
  if(expectedFailure){
   assert.equal(current.worker,'old');assert(current.capture.running);
   if(resumed){
    assert.match(output,/Capture started while the update was preparing/);
    const events=readFileSync(join(root,'data/events.log'),'utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
    if(mode==='resumed-at-quiesce'){
     const quiesced=events.findIndex(event=>event.name==='quiesced');
     assert(quiesced>=0&&events.findIndex(event=>event.name==='restored')>quiesced,'Quiesced capture was not restored');
     assert(!events.some(event=>event.name==='activated'),'An unprepared replacement started capture');
    }else assert(!events.some(event=>event.name==='quiesced'),'Resumed capture was stopped without warming its game');
   }
  }
  else{
   assert.equal(current.worker,'new');assert.equal(current.capture.running,!paused);assert.equal(current.session.id,'continuous-session');
   const events=readFileSync(join(root,'data/events.log'),'utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
   assert(events.findIndex(event=>event.name==='ready')<events.findIndex(event=>event.name==='quiesced'),'Old capture paused before the replacement was ready');
   const records=JSON.parse(readFileSync(join(root,'data/processes.json'),'utf8'));
   assert.equal(typeof records.backend.started,'string');assert.equal(realpathSync.native(records.backend.root),realpathSync.native(root));assert.equal(records.router.id,router.pid);
   stopRecorded(root,true);
  }
  terminate(router);terminate(old);
  console.log(expectedFailure?resumed?'Capture resumed during preparation stays on its current runtime.':'Failed candidate leaves live translations available.':paused?'Paused update ignores unrelated history and remains paused.':'Prepared replacement preserves availability, capture state and session.');
 }
}catch(error){
 for(const process of children)if(process.diagnostics)console.error(process.diagnostics);
 throw error;
}finally{
 for(const process of children)terminate(process);
 for(const name of ['running update','paused update','resumed update','resumed-at-quiesce update','failed update']){
  stopRecorded(join(temporary,name));
 }
 const checked=realpathSync.native(temporary),prefix=realpathSync.native(tmpdir())+sep+'companion-update-';
 if(!checked.startsWith(prefix))throw Error('Unexpected fixture cleanup path');
 rmSync(checked,{recursive:true,force:true,maxRetries:3,retryDelay:100});
}
