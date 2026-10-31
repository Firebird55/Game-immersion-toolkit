// Compatibility entrypoint for source tools. The frozen and source hosts share
// backend.desktop_gateway; this wrapper owns no independent routing logic.
import {spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {resolvePython} from './python-runtime.mjs';
import {stopOwnedProcess} from './e2e-preview.mjs';

export async function startRouter({statePath,assetDirectory,apiPort=8766,frontendPort=3000,shutdownTimeoutMs=5000,onLog=()=>{}}){
 if(!Number.isInteger(shutdownTimeoutMs)||shutdownTimeoutMs<1||shutdownTimeoutMs>30000)throw Error('Invalid router shutdown deadline');
 const root=fileURLToPath(new URL('..',import.meta.url));
 const args=['-u','-m','backend.desktop_gateway','--state',resolve(statePath),'--api-port',String(apiPort),'--frontend-port',String(frontendPort),'--shutdown-stdin','--shutdown-timeout',String(shutdownTimeoutMs/1000)];
 if(assetDirectory)args.push('--assets',resolve(assetDirectory));
 const child=spawn(resolvePython({root}).command,args,{cwd:root,windowsHide:true,detached:process.platform!=='win32',stdio:['pipe','pipe','pipe']});
 let output='',errors='',closing;
 child.stderr.on('data',chunk=>{errors=(errors+chunk).slice(-4000);onLog(chunk);});
 function close(){
  return closing??=new Promise((done,reject)=>{
   const finish=(code,signal)=>code===0&&!signal?done():reject(Error('Companion router shutdown failed. '+errors));
   if(child.exitCode!==null||child.signalCode!==null){finish(child.exitCode,child.signalCode);return;}
   let forced=false;
   const timeout=setTimeout(()=>{
    forced=true;
    void stopOwnedProcess(child).then(()=>reject(Error('Companion router shutdown deadline expired; owned process was stopped.')),reject);
   },shutdownTimeoutMs+3000);
   child.once('exit',(code,signal)=>{clearTimeout(timeout);if(!forced)finish(code,signal);});
   child.stdin.on('error',()=>{}); // Exit status, not a broken shutdown pipe, determines the outcome.
   child.stdin.end('stop\n');
  });
 }
 try{
  const ready=await new Promise((done,reject)=>{
   const timeout=setTimeout(()=>reject(Error('Desktop gateway startup timed out. '+errors)),15000);
   child.once('error',error=>{clearTimeout(timeout);reject(error);});
   child.once('exit',code=>{clearTimeout(timeout);reject(Error('Desktop gateway exited '+code+'. '+errors));});
   child.stdout.on('data',chunk=>{
    output+=chunk;
    for(const line of output.split('\n')){try{const value=JSON.parse(line);if(value.ready){clearTimeout(timeout);done(value);return;}}catch{}}
   });
  });
  return {...ready,close};
 }catch(error){await close();throw error;}
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=name=>process.argv[process.argv.indexOf(name)+1];
 const router=await startRouter({statePath:value('--state'),assetDirectory:process.argv.includes('--assets')?value('--assets'):undefined,
  onLog:chunk=>process.stderr.write(chunk),apiPort:process.argv.includes('--api-port')?Number(value('--api-port')):8766,
  frontendPort:process.argv.includes('--frontend-port')?Number(value('--frontend-port')):3000});
 const stop=()=>{void router.close().then(()=>process.exit(0),error=>{console.error(error.message);process.exit(1);});};
 process.on('SIGINT',stop);process.on('SIGTERM',stop);
 console.log('Desktop transcript ready on port '+router.frontendPort+'. Open Share for its local-network address.');
}
