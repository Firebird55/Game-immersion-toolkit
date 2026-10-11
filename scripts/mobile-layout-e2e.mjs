// Authored synthetic scenes verify the production OCR regions, including black
// comic bubbles, cards, legacy panels and negative response/HUD text. They do
// not claim coverage of real quests or publishers' fonts.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync} from 'node:fs';
import {chromium} from 'playwright';
import {ocrAssets,mime} from './mobile-assets.mjs';
const assets=ocrAssets(),server=http.createServer((req,res)=>{const path=req.url;const bytes=path==='/'?Buffer.from('<html><body>Owned OCR layout fixtures</body></html>'):path==='/library.mjs'||path==='/ocr-pipeline.mjs'?readFileSync('public/mobile-capture'+path):assets.get(path.slice(1));if(!bytes){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(path));res.end(bytes);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{browser=await chromium.launch({headless:true});const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);
 await page.evaluate(async()=>{const {default:T}=await import('/ocr/tesseract.esm.min.js');window.ocr=await T.createWorker('eng',1,{workerPath:location.origin+'/ocr/worker.min.js',corePath:location.origin+'/ocr/core/',langPath:location.origin+'/ocr/lang/',workerBlobURL:false});window.pipeline=await import('/ocr-pipeline.mjs');window.lib=await import('/library.mjs');});
 const games=['zzz','wuwa','pragmata','cyberpunk','witcher3','nte','honkai3','hito'],scenes=[...games.map(game=>({game,kind:'dialogue',channel:'dialogue'})),{game:'zzz',kind:'comic',channel:'cinematic'},{game:'wuwa',kind:'card',channel:'cinematic'},{game:'cyberpunk',kind:'overhead',channel:'gameplay'},{game:'witcher3',kind:'top',channel:'gameplay'},{game:'honkai3',kind:'panel',channel:'dialogue'},{game:'honkai3',kind:'whitepanel',channel:'dialogue'},{game:'wuwa',kind:'choice',negative:true},{game:'cyberpunk',kind:'hud',negative:true}];
 let count=0;
 for(const resolution of [[1280,720],[1920,1080],[3840,2160],[3440,1440]])for(const scene of scenes){
  const result=await page.evaluate(async({scene,resolution})=>{
   const [width,height]=resolution,source=document.createElement('canvas');source.width=width;source.height=height;const ctx=source.getContext('2d'),pw=Math.min(width,height*16/9),ph=pw*9/16,x=(width-pw)/2,y=(height-ph)/2,s=ph/720;
   ctx.fillStyle='#000';ctx.fillRect(0,0,width,height);let tx=.25,ty=scene.game==='nte'?.845:scene.game==='hito'?.84:.835,size=30,color='white';
   if(scene.kind==='comic'){ctx.fillStyle='white';ctx.fillRect(x+pw*.20,y+ph*.26,pw*.60,ph*.14);tx=.24;ty=.345;color='black';size=28;}
   if(scene.kind==='card'){tx=.25;ty=.45;size=38;}
   if(scene.kind==='overhead'){tx=.4;ty=.27;size=24;}
   if(scene.kind==='top'){tx=.25;ty=.06;size=24;}
   if(scene.kind==='panel'){tx=.44;ty=.81;size=30;ctx.fillStyle='white';ctx.font=`${30*s}px Arial`;ctx.fillText('zqqqq xxxxx',x+pw*.06,y+ph*.81);}
   if(scene.kind==='whitepanel'){ctx.fillStyle='#eee';ctx.fillRect(x+pw*.07,y+ph*.72,pw*.86,ph*.24);tx=.18;ty=.85;color='black';}
   if(scene.kind==='choice'){tx=.70;ty=.76;size=16;}
   if(scene.kind==='hud'){tx=.01;ty=.94;size=15;}
   if(scene.game==='hito'){tx=.4;size=24;}
   const english='The lantern is bright.',row={id:'a'.repeat(64),textId:scene.game+':owned-fixture',english,chinese:'灯笼很亮。',sourceVoice:'a'.repeat(64),channels:['dialogue','gameplay','cinematic']},matcher=new lib.DialogueMatcher([row]);ctx.font=`${size*s}px Arial`;ctx.fillStyle=color;ctx.fillText(english,x+pw*tx,y+ph*ty);
   const canvas=document.createElement('canvas'),trace=[];let menu=false;
   for(const region of pipeline.regions(scene.game)){
    if(region.channel!=='dialogue'&&menu)continue;pipeline.cropFrame(source,canvas,region.crop,'16:9');const recognized=await pipeline.recognizeRegion(ocr,canvas,region,'eng');if(!recognized)continue;const parsed=pipeline.candidates(recognized,region,canvas.width,canvas.height,scene.game);trace.push({channel:region.channel,text:recognized.text,candidates:parsed.values});if(region.channel==='dialogue')menu=parsed.menu;const result=matcher.matchCandidates(parsed.values,region.channel);if(result.state==='matched')return {channel:region.channel};
   }return {channel:null,trace};
  },{scene,resolution});
  if(result.channel!==(scene.negative?null:scene.channel))console.log(result.trace);assert.equal(result.channel,scene.negative?null:scene.channel,`${scene.game}/${scene.kind} at ${resolution.join('x')}`);count++;
 }
 await page.evaluate(()=>ocr.terminate());console.log(`chromium: ${count} owned game-layout, special-panel, negative menu/HUD and multi-resolution OCR cases passed`);
}finally{await browser?.close();await new Promise(r=>server.close(r));}
