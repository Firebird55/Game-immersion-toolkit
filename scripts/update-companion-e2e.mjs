import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,copyFileSync,rmSync,existsSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import net from 'node:net';

if(process.platform!=='win32'){console.log('Prepared companion updates require Windows.');process.exit(0);}
const repository=process.cwd(),temporary=mkdtempSync(join(tmpdir(),'companion-update-'));
const pythonLocal=join(process.env.LOCALAPPDATA??'','Programs/Proxy Transcript/venv/Scripts/python.exe');
const python=existsSync(pythonLocal)?pythonLocal:execFileSync('python',['-c','import sys; print(sys.executable)'],{encoding:'utf8'}).trim();
const children=[],fixture=join(repository,'scripts/fixtures/companion-update');
const port=()=>new Promise(resolve=>{const server=net.createServer();server.listen(0,'127.0.0.1',()=>{const value=server.address().port;server.close(()=>resolve(value));});});
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const json=(path,value)=>writeFileSync(path,JSON.stringify(value));
const powershell=process.env.PWSH||'powershell.exe';
async function ready(url){for(let i=0;i<100;i++){try{if((await fetch(url)).ok)return;}catch{}await wait(50);}throw Error('Fixture did not start');}
function child(command,args,options={}){const value=spawn(command,args,{stdio:['ignore','pipe','pipe'],...options});children.push(value);return value;}
function terminate(id){try{execFileSync('taskkill',['/PID',String(id),'/T','/F'],{stdio:'ignore'});}catch{}}

try{
 for(const fail of [false,true]){
  const root=join(temporary,fail?'failed update':'successful update'),source=join(root,'new source');
  for(const name of ['data','new source/backend','new source/scripts','new source/.openai'])mkdirSync(join(root,name),{recursive:true});
  for(const name of ['companion-runtime.ps1','retire-companion.ps1','companion-router.mjs'])copyFileSync(join(repository,'scripts',name),join(source,'scripts',name));
  copyFileSync(join(repository,'backend/check_environment.py'),join(source,'backend/check_environment.py'));
  copyFileSync(join(fixture,'backend.py'),join(source,'backend/main.py'));
  for(const [from,to]of [['frontend.mjs','fixture-front.mjs'],['install.mjs','install-fixture.mjs'],['build.mjs','build-fixture.mjs']])copyFileSync(join(fixture,from),join(source,'scripts',to));
  writeFileSync(join(source,'backend/__init__.py'),'');writeFileSync(join(source,'requirements.lock.txt'),'');
  writeFileSync(join(source,'VERSION'),'0.0.0-test');json(join(source,'.openai/hosting.json'),{});
  const packageValue={name:'game-immersion-toolkit',version:'0.0.0-test',type:'module',scripts:{postinstall:'node scripts/install-fixture.mjs',build:'node scripts/build-fixture.mjs'}};
  json(join(source,'package.json'),packageValue);json(join(source,'package-lock.json'),{name:packageValue.name,version:packageValue.version,lockfileVersion:3,requires:true,packages:{'':packageValue}});
  if(fail)writeFileSync(join(source,'backend/fail.flag'),'candidate must not activate');
  const oldPort=await port(),api=await port(),front=await port();
  const old=child(process.execPath,[join(fixture,'old-server.mjs'),String(oldPort),join(root,'data/events.log')]);
  await ready('http://127.0.0.1:'+oldPort+'/api/health');
  const state=join(root,'data/companion-runtime.json');json(state,{version:1,active:{apiPort:oldPort,frontendPort:oldPort,python,source}});
  const router=child(process.execPath,[join(repository,'scripts/companion-router.mjs'),'--state',state,'--assets',join(root,'data/runtime-assets'),'--api-port',String(api),'--frontend-port',String(front)]);
  await ready('http://127.0.0.1:'+api+'/api/health');json(join(root,'data/processes.json'),{router:router.pid,backend:old.pid,frontend:old.pid});
  const update=child(powershell,['-NoProfile','-ExecutionPolicy','Bypass','-File',join(repository,'scripts/update-companion.ps1'),'-Root',root,'-SourceRoot',source,'-ApiPort',String(api),'-FrontendPort',String(front),'-ReadyTimeoutSeconds',fail?'3':'30']);
  let output='';const collect=b=>{output+=b;if(process.argv.includes('--verbose'))process.stdout.write(b);};update.stdout.on('data',collect);update.stderr.on('data',collect);
  let done=false;const completion=new Promise(resolve=>update.on('exit',code=>{done=true;resolve(code);}));
  const samples=[];
  while(!done){
   const response=await fetch('http://127.0.0.1:'+api+'/api/status');assert(response.ok,'The existing API went offline while preparing an update');samples.push(await response.json());await wait(60);
  }
  const code=await completion;
  if(code!==(fail?1:0)){
   const logs=join(root,'data/runtime-logs');
   if(existsSync(logs))for(const file of readdirSync(logs))if(file.endsWith('.log'))output+='\n'+file+': '+readFileSync(join(logs,file),'utf8').slice(-4000);
  }
  assert.equal(code,fail?1:0,output);
  assert(samples.some(sample=>sample.worker==='old'&&sample.capture.running),'No working old capture survived preparation');
  const current=await(await fetch('http://127.0.0.1:'+api+'/api/status')).json();
  if(fail){assert.equal(current.worker,'old');assert(current.capture.running);}
  else{
   assert.equal(current.worker,'new');assert(current.capture.running);assert.equal(current.session.id,'continuous-session');
   const events=readFileSync(join(root,'data/events.log'),'utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
   assert(events.findIndex(event=>event.name==='ready')<events.findIndex(event=>event.name==='quiesced'),'Old capture paused before the replacement was ready');
   const records=JSON.parse(readFileSync(join(root,'data/processes.json'),'utf8'));for(const [name,id]of Object.entries(records))if(name!=='router')terminate(id);
  }
  terminate(router.pid);terminate(old.pid);
  console.log(fail?'Failed candidate leaves live translations available.':'Prepared replacement preserves availability, capture state and session.');
 }
}finally{
 for(const process of children)terminate(process.pid);
 for(const name of ['successful update','failed update']){
  const record=join(temporary,name,'data/processes.json');
  if(existsSync(record))for(const id of Object.values(JSON.parse(readFileSync(record,'utf8'))))terminate(id);
 }
 const checked=resolve(temporary),prefix=resolve(tmpdir())+sep+'companion-update-';
 if(!checked.startsWith(prefix))throw Error('Unexpected fixture cleanup path');
 rmSync(checked,{recursive:true,force:true,maxRetries:3,retryDelay:100});
}
