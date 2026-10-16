import http from 'node:http';
import {appendFileSync} from 'node:fs';
const [port,events]=process.argv.slice(2);
let running=true;
http.createServer((request,response)=>{
 response.setHeader('Content-Type','application/json');
 if(request.url==='/api/runtime/quiesce'){
  running=false;appendFileSync(events,JSON.stringify({name:'quiesced',at:Date.now()/1000})+'\n');
  response.end(JSON.stringify({running:true,session_id:'continuous-session'}));
 }else if(request.url==='/api/health')response.end(JSON.stringify({status:'ok'}));
 else response.end(JSON.stringify({capture:{running,active_game:'zzz'},session:{id:'continuous-session'},worker:'old'}));
}).listen(Number(port),'127.0.0.1');
