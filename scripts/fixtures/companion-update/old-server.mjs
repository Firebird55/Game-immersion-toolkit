import http from 'node:http';
import {appendFileSync,existsSync,readFileSync} from 'node:fs';
const [port,events,mode]=process.argv.slice(2);
let running=!['paused','resumed'].includes(mode);
http.createServer((request,response)=>{
 if(mode==='resumed'&&existsSync(events)&&readFileSync(events,'utf8').includes('"name": "ready"'))running=true;
 response.setHeader('Content-Type','application/json');
 if(request.url==='/api/runtime/quiesce'){
  const wasRunning=running;
  running=false;appendFileSync(events,JSON.stringify({name:'quiesced',at:Date.now()/1000})+'\n');
  response.end(JSON.stringify({running:wasRunning,session_id:'continuous-session'}));
 }else if(request.url==='/api/health')response.end(JSON.stringify({status:'ok'}));
 else if(request.url.startsWith('/api/lines'))response.end(JSON.stringify([{game:'beyond'}]));
 else if(['paused','resumed'].includes(mode))response.end(JSON.stringify({capture:{running,active_game:running?'zzz':null},settings:{preferred_game:'auto'},textmaps:{ready:true},session:{id:'continuous-session'},worker:'old'}));
 else response.end(JSON.stringify({capture:{running,active_game:'zzz'},session:{id:'continuous-session'},worker:'old'}));
}).listen(Number(port),'127.0.0.1');
