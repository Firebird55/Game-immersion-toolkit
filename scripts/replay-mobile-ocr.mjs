// Private footage replay. This server is bound to loopback and never used for Pages.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import http from 'node:http';
import {chromium} from 'playwright';
import {ocrAssets,mime} from './mobile-assets.mjs';
const directory=resolve(process.argv[2]??'output/mobile-replay'),assets=ocrAssets(),cases=JSON.parse(readFileSync(resolve(directory,'manifest.json'))).cases;
const server=http.createServer((req,res)=>{const path=new URL(req.url,'http://localhost').pathname;try{let bytes;if(path==='/')bytes=Buffer.from('<html><body>Private OCR verification</body></html>');else if(path.startsWith('/ocr/'))bytes=assets.get(path.slice(1));else if(['/library.mjs','/ocr-pipeline.mjs'].includes(path))bytes=readFileSync('public/mobile-capture'+path);else if(path.startsWith('/private/')){const file=resolve(directory,path.slice(9));if(!file.startsWith(directory+'\\')&&!file.startsWith(directory+'/'))throw Error();bytes=readFileSync(file);}if(!bytes)throw Error();res.setHeader('Content-Type',path.endsWith('.png')?'image/png':mime(path));res.end(bytes);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
let browser;const report=[];
try{
 browser=await chromium.launch({headless:true});const page=await browser.newPage();await page.goto(base);
 await page.evaluate(async()=>{const {default:T}=await import('/ocr/tesseract.esm.min.js');window.ocr=await T.createWorker('eng',1,{workerPath:location.origin+'/ocr/worker.min.js',corePath:location.origin+'/ocr/core/',langPath:location.origin+'/ocr/lang/',workerBlobURL:false});window.pipeline=await import('/ocr-pipeline.mjs');window.lib=await import('/library.mjs');});
 let previousGame='';
 for(const [index,clip] of cases.entries()){
  if(process.env.MOBILE_REPLAY_FILTER&&!clip.name.toLowerCase().includes(process.env.MOBILE_REPLAY_FILTER.toLowerCase()))continue;
  if(clip.game!==previousGame){await page.evaluate(async game=>{const rows=await fetch('/private/'+game+'.json').then(r=>r.json());window.matcher=new lib.DialogueMatcher(rows.map((r,i)=>({...r,id:String(i)})));},clip.game);previousGame=clip.game;}
  const result=await page.evaluate(async clip=>{
   const image=new Image(),canvas=document.createElement('canvas'),emitted=new Set(),channels=new Set(),diagnostics=[];let stable=null;
   const player=clip.player_voice??(clip.expected?.every(id=>id.endsWith(':female'))?'female':'unconfigured');
   for(const frame of clip.frames){image.src='/private/'+frame;await image.decode();let accepted=null,menu=false;
    for(const region of pipeline.regions(clip.game)){
     if(region.channel!=='dialogue'&&menu)continue;
     pipeline.cropFrame(image,canvas,region.crop,'16:9');const recognized=await pipeline.recognizeRegion(ocr,canvas,region,'eng');if(!recognized)continue;
     const parsed=pipeline.candidates(recognized,region,canvas.width,canvas.height,clip.game);if(region.channel==='dialogue')menu=parsed.menu;
     const match=matcher.matchCandidates(parsed.values,region.channel,player,region.fragment);if(match.state==='matched')accepted={...match,channel:region.channel};
     if(diagnostics.length<600)diagnostics.push({frame,channel:region.channel,text:recognized.text,candidates:parsed.values.slice(0,6),refined:recognized.refinedTexts,accepted:accepted?.row.textId??null});if(accepted)break;
    }
    if(!accepted){stable=null;continue;}const key=accepted.row.textId;stable=stable?.key===key?{key,count:stable.count+1}:{key,count:1};if(stable.count===2){emitted.add(key);channels.add(accepted.channel);}
   }
   const actual=[...emitted],missed=(clip.expected??[]).filter(id=>!emitted.has(id)),unexpected=actual.filter(id=>clip.expect_no_lines||clip.excluded?.includes(id)||clip.expected_exact&&!clip.expected.includes(id)),wrongChannels=[...channels].filter(c=>clip.allowed_channels&&!clip.allowed_channels.includes(c));return {actual,missed,unexpected,wrongChannels,diagnostics};
  },clip);
  const ok=!result.missed.length&&!result.unexpected.length&&!result.wrongChannels.length;report.push({name:clip.name,game:clip.game,resolution:clip.resolution,frames:clip.frames.length,ok,...result});
  console.log(`${index+1}/${cases.length} ${clip.game} ${clip.resolution}: ${ok?'PASS':'FAIL'} (${result.actual.length} accepted; ${result.missed.length} missed; ${result.unexpected.length} unexpected)`);
  writeFileSync(resolve(directory,process.env.MOBILE_REPLAY_REPORT??'report.json'),JSON.stringify(report,null,2));
 }
 await page.evaluate(()=>ocr.terminate());
 console.log(`Browser footage checks: ${report.filter(r=>r.ok).length}/${report.length} passed`);if(report.some(r=>!r.ok))process.exitCode=1;
}finally{await browser?.close();await new Promise(r=>server.close(r));}
