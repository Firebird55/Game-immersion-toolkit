import http from 'node:http';
import net from 'node:net';
import {readFileSync,createReadStream,statSync,watchFile,unwatchFile} from 'node:fs';
import {resolve,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const mime={'.js':'text/javascript','.css':'text/css','.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml','.ico':'image/x-icon'};
function slot(value){
 if(!value||!['apiPort','frontendPort'].every(key=>Number.isInteger(value[key])&&value[key]>1024&&value[key]<65536))throw Error('Invalid runtime slot');
 return value;
}

export async function startRouter({statePath,assetDirectory,apiPort=8766,frontendPort=3000,shutdownTimeoutMs=3000}){
 if(!Number.isInteger(shutdownTimeoutMs)||shutdownTimeoutMs<1||shutdownTimeoutMs>30000)throw Error('Invalid router shutdown deadline');
 let state,closed=false,closing;
 const upgrades=new Set(),sockets=new Map(),requests=new Set();
 function refresh(){
  try{
   const next=JSON.parse(readFileSync(statePath,'utf8'));slot(next.active);
   if(next.active.apiPort===apiPort||next.active.frontendPort===frontendPort)throw Error('Recursive runtime route');
   const changed=state&&state.active.apiPort!==next.active.apiPort;
   state=next;
   if(changed)for(const pair of upgrades){pair.client.end();pair.upstream.end();}
  }catch(error){if(!state)throw error;}
 }
 refresh();
 watchFile(statePath,{interval:100,persistent:false},refresh);
 function cachedAsset(request,response){
  if(!assetDirectory||!['GET','HEAD'].includes(request.method))return false;
  let name;
  try{name=decodeURIComponent(new URL(request.url,'http://localhost').pathname);}catch{return false;}
  if(!name.startsWith('/_next/static/'))return false;
  const root=resolve(assetDirectory),file=resolve(root,name.slice('/_next/static/'.length)),local=relative(root,file);
  if(!local||local==='..'||local.startsWith('..'+sep)||local.includes(':'))return false;
  const type=Object.entries(mime).find(([extension])=>file.endsWith(extension))?.[1];
  if(!type)return false;
  try{
   const stat=statSync(file);if(!stat.isFile())return false;
   response.writeHead(200,{'Content-Type':type,'Content-Length':stat.size,'Cache-Control':'public, max-age=31536000, immutable'});
   if(request.method==='HEAD')response.end();else createReadStream(file).on('error',()=>response.destroy()).pipe(response);
   return true;
  }catch{return false;}
 }
 function server(kind){
  const instance=http.createServer((request,response)=>{
   if(closed){response.writeHead(503,{'Connection':'close'});response.end();return;}
   const socket=request.socket;sockets.set(socket,(sockets.get(socket)||0)+1);
   let finished=false;
   const release=()=>{
    if(finished)return;finished=true;
    const count=sockets.get(socket);
    if(count!==undefined){sockets.set(socket,count-1);if(closed&&count===1)socket.destroySoon();}
   };
   response.once('finish',release);response.once('close',release);
   refresh();
   if(kind==='frontend'&&cachedAsset(request,response))return;
   const upstream=http.request({host:'127.0.0.1',port:state.active[kind==='api'?'apiPort':'frontendPort'],agent:false,
    path:request.url,method:request.method,headers:request.headers},result=>{
     response.writeHead(result.statusCode,{...result.headers,'X-Proxy-Transcript-Router':'1'});
     result.on('error',()=>response.destroy());result.pipe(response);
    });
   requests.add(upstream);upstream.once('close',()=>requests.delete(upstream));
   upstream.on('error',()=>{if(!response.headersSent)response.writeHead(503,{'Content-Type':'application/json','Retry-After':'1'});response.end(JSON.stringify({detail:'Companion is starting. Reconnecting automatically.'}));});
   request.on('aborted',()=>upstream.destroy());response.on('close',()=>upstream.destroy());request.pipe(upstream);
  });
  instance.on('connection',socket=>{sockets.set(socket,0);socket.once('close',()=>sockets.delete(socket));});
  instance.on('upgrade',(request,client,head)=>{
   if(closed){client.destroy();return;}
   refresh();
   const upstream=net.connect({host:'127.0.0.1',port:state.active[kind==='api'?'apiPort':'frontendPort']});
   const pair={client,upstream};upgrades.add(pair);
   upstream.on('connect',()=>{
    upstream.write(`${request.method} ${request.url} HTTP/${request.httpVersion}\r\n`);
    for(let i=0;i<request.rawHeaders.length;i+=2)upstream.write(`${request.rawHeaders[i]}: ${request.rawHeaders[i+1]}\r\n`);
    upstream.write('\r\n');if(head.length)upstream.write(head);
    client.pipe(upstream);upstream.pipe(client);
   });
   const clear=()=>{upgrades.delete(pair);client.destroy();upstream.destroy();};
   client.on('error',clear);upstream.on('error',clear);client.on('close',clear);upstream.on('close',clear);
  });
  return instance;
 }
 const api=server('api'),frontend=server('frontend');
 const listen=(instance,port)=>new Promise((resolve,reject)=>{instance.once('error',reject);instance.listen(port,'127.0.0.1',()=>resolve(instance.address().port));});
 try{
  const apiListenPort=await listen(api,apiPort),frontendListenPort=await listen(frontend,frontendPort);
  return {apiPort:apiListenPort,frontendPort:frontendListenPort,close:()=>{
   if(closing)return closing;
   closed=true;unwatchFile(statePath,refresh);
   closing=(async()=>{
    for(const pair of upgrades){pair.client.destroy();pair.upstream.destroy();}
    const drained=Promise.all([api,frontend].map(instance=>new Promise(resolve=>{instance.close(resolve);instance.closeIdleConnections();})));
    // HTTP idle tracking excludes a TCP preconnection that sent no request.
    // Retain active responses for the bounded drain; only owned idle sockets
    // can be closed immediately.
    for(const [socket,count] of sockets)if(count===0)socket.destroy();
    let timedOut=false;
    const timer=setTimeout(()=>{
     timedOut=true;
     for(const request of requests)request.destroy();
     for(const socket of sockets.keys())socket.destroy();
    },shutdownTimeoutMs);
    try{await drained;}finally{clearTimeout(timer);}
    if(timedOut)throw Error('Companion router shutdown deadline expired; active requests were stopped.');
   })();
   return closing;
  }};
 }catch(error){unwatchFile(statePath,refresh);api.close();frontend.close();throw error;}
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=name=>process.argv[process.argv.indexOf(name)+1];
 const router=await startRouter({statePath:resolve(value('--state')),assetDirectory:resolve(value('--assets')),
  apiPort:process.argv.includes('--api-port')?Number(value('--api-port')):8766,
  frontendPort:process.argv.includes('--frontend-port')?Number(value('--frontend-port')):3000});
 const stop=()=>router.close().then(()=>process.exit(0),error=>{console.error(error.message);process.exit(1);});
 process.on('SIGINT',stop);process.on('SIGTERM',stop);
 console.log('Companion routes are ready on localhost.');
}
