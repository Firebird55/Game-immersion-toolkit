import {normalize,subtitleRows} from './library.mjs';
export const crops={zzz:[.08,.67,.84,.25],wuwa:[.10,.64,.80,.32],pragmata:[.08,.67,.84,.25],cyberpunk:[.12,.59,.76,.37],witcher3:[.08,.63,.84,.34],nte:[.10,.80,.80,.18],honkai3:[.04,.72,.96,.24],hito:[.35,.765,.365,.18]};
export const extraCrops={cyberpunk:{overhead:[.10,.12,.70,.62]},witcher3:{overhead:[.08,0,.76,.74]},wuwa:{card:[.12,.20,.76,.43]},zzz:{comic:[.04,.06,.92,.88]},honkai3:{panel:[.39,.72,.61,.16]},nte:{compact:[.10,.80,.80,.09]}};
export function regions(game,crop=crops[game],extra=true,cinematic=true,custom={}){
 const result=[{crop,channel:'dialogue',ink:game==='hito'?null:game==='cyberpunk'?'blue':'white'}];
 if(cinematic&&['honkai3','nte'].includes(game))result.push({crop:game==='honkai3'?custom.panel??extraCrops.honkai3.panel:custom.compact??extraCrops.nte.compact,channel:'dialogue',ink:'white'});
 if(extra&&['cyberpunk','witcher3'].includes(game)){
  const [left,top,width,height]=custom.overhead??extraCrops[game].overhead;
  if(game==='witcher3')result.push({crop:[left,top,width,Math.min(.10,height)],channel:'gameplay',raw:true,line:true});
  else if(height>.2)result.push({crop:[left,top+.08,width,Math.min(.14,height-.08)],channel:'gameplay',raw:true});
  // Overlapping strips keep small overhead captions legible without asking OCR
  // to segment a whole textured game scene. Matches remain exact and unique.
  for(let y=top;y<top+height-.05;y+=.12)result.push({crop:[left,y,width,Math.min(.22,top+height-y)],channel:'gameplay',ink:game==='cyberpunk'?'blue':'white'});
 }
 if(cinematic&&game==='wuwa')result.push({crop:custom.card??extraCrops.wuwa.card,channel:'cinematic',black:true});
 if(cinematic&&game==='zzz')result.push({crop:custom.comic??extraCrops.zzz.comic,channel:'cinematic',fragment:true});
 return result;
}
export function cropFrame(source,canvas,region,picture='window'){
 const w=source.videoWidth??source.naturalWidth??source.width,h=source.videoHeight??source.naturalHeight??source.height;
 if(!w||!h)throw new Error('Connect the receiving game screen first.');
 let x=0,y=0,pw=w,ph=h;if(picture==='16:9'){if(w/h>16/9){pw=h*16/9;x=(w-pw)/2;}else{ph=w*9/16;y=(h-ph)/2;}}
 const [left,top,width,height]=region,cw=pw*width,ch=ph*height,scale=Math.min(2,1440/h,2304/cw,1024/ch);
 canvas.width=Math.max(1,Math.round(cw*scale));canvas.height=Math.max(1,Math.round(ch*scale));canvas.getContext('2d',{willReadFrequently:true}).drawImage(source,x+pw*left,y+ph*top,cw,ch,0,0,canvas.width,canvas.height);return canvas;
}
export function prepareImage(canvas,region,language){
 const context=canvas.getContext('2d',{willReadFrequently:true}),pixels=context.getImageData(0,0,canvas.width,canvas.height);let dark=0,total=0,black=0,bright=0;
 for(let i=0;i<pixels.data.length;i+=64){total++;const sum=pixels.data[i]+pixels.data[i+1]+pixels.data[i+2];if(sum<240)dark++;if(sum<100)black++;if(sum>600)bright++;}
 if(region.black&&black/total<.75)return false;
 if(region.raw)return true;
 if(region.ink&&bright/total>.55)return true; // dark text on a pale dialogue panel
 if(region.ink||language.includes('chi_sim')&&dark/total>.75){
  const width=canvas.width,height=canvas.height,stride=width+1,outline=region.ink?new Uint32Array(stride*(height+1)):null;
  if(outline)for(let y=0;y<height;y++){let row=0;for(let x=0;x<width;x++){const i=(y*width+x)*4;row+=Math.max(pixels.data[i],pixels.data[i+1],pixels.data[i+2])<130?1:0;outline[(y+1)*stride+x+1]=outline[y*stride+x+1]+row;}}
  for(let i=0;i<pixels.data.length;i+=4){const r=pixels.data[i],g=pixels.data[i+1],b=pixels.data[i+2],high=Math.max(r,g,b),low=Math.min(r,g,b);let foreground=region.ink==='blue'?r>65&&g>80&&b>90&&(b-r>4||low>170)&&high-low<85:region.ink==='white'?low>95&&high-low<85||high>160&&low>35&&high-low>80:r+g+b>300;
   if(foreground&&outline){const x=i/4%width,y=Math.floor(i/4/width),x0=Math.max(0,x-3),x1=Math.min(width,x+4),y0=Math.max(0,y-3),y1=Math.min(height,y+4);foreground=outline[y1*stride+x1]-outline[y0*stride+x1]-outline[y1*stride+x0]+outline[y0*stride+x0]>0;}
   const value=foreground?0:255;pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=value;
  }context.putImageData(pixels,0,0);
 }
 return true;
}
function refinementBounds(data,width,height){
 const lines=cleanOcrBlocks(data.blocks).flatMap(b=>b.paragraphs).flatMap(p=>p.lines).filter(l=>l.bbox&&(l.confidence??0)>=45&&normalize(l.text).length>=3&&l.bbox.y1-l.bbox.y0<height*.2).sort((a,b)=>a.bbox.y0-b.bbox.y0);
 const groups=[];for(const line of lines){const b=line.bbox,previous=groups.at(-1),h=b.y1-b.y0;if(previous&&b.y0-previous.y1<Math.max(h,previous.lineHeight)*1.5&&b.x0<previous.x1&&b.x1>previous.x0){previous.x0=Math.min(previous.x0,b.x0);previous.x1=Math.max(previous.x1,b.x1);previous.y1=Math.max(previous.y1,b.y1);previous.text+=' '+line.text;previous.score+=line.confidence;}else groups.push({...b,text:line.text,score:line.confidence,lineHeight:h});}
 return groups.filter(b=>normalize(b.text).length>=12&&b.y1-b.y0<height*.65&&b.x1-b.x0>width*.1).sort((a,b)=>normalize(b.text).length-normalize(a.text).length).slice(0,1);
}
function comicBubbles(canvas){
 const probe=document.createElement('canvas'),scale=Math.min(1,640/canvas.width);probe.width=Math.round(canvas.width*scale);probe.height=Math.round(canvas.height*scale);probe.getContext('2d').drawImage(canvas,0,0,probe.width,probe.height);
 const data=probe.getContext('2d').getImageData(0,0,probe.width,probe.height).data,w=probe.width,h=probe.height,white=new Uint8Array(w*h),queue=new Int32Array(w*h),found=[];
 for(let k=0;k<white.length;k++){const i=k*4,r=data[i],g=data[i+1],b=data[i+2];white[k]=Math.min(r,g,b)>200&&Math.max(r,g,b)-Math.min(r,g,b)<50?1:0;}
 for(let k=0;k<white.length;k++)if(white[k]){let start=0,end=1,left=k%w,right=left,top=Math.floor(k/w),bottom=top;queue[0]=k;white[k]=0;while(start<end){const at=queue[start++],x=at%w,y=Math.floor(at/w);left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);for(const next of [x?at-1:-1,x<w-1?at+1:-1,y?at-w:-1,y<h-1?at+w:-1])if(next>=0&&white[next]){white[next]=0;queue[end++]=next;}}
  if(end>600&&right-left>50&&bottom-top>18&&end/((right-left+1)*(bottom-top+1))>.4)found.push({x:Math.max(0,(left-2)/scale),y:Math.max(0,(top-2)/scale),w:(right-left+5)/scale,h:(bottom-top+5)/scale,area:end});
 }
 return found.sort((a,b)=>b.area-a.area).slice(0,4);
}
export async function recognizeRegion(worker,canvas,region,language,isCurrent=()=>true){
 let original=null;if(region.channel==='gameplay'||region.channel==='dialogue'){original=document.createElement('canvas');original.width=canvas.width;original.height=canvas.height;original.getContext('2d').drawImage(canvas,0,0);}
 if(!prepareImage(canvas,region,language))return null;
 await worker.setParameters({tessedit_pageseg_mode:region.fragment?'11':region.line?'7':'6'});
 const result=await worker.recognize(canvas,{}, {text:true,blocks:true});if(!isCurrent())return result.data;
 if(region.fragment){const refined=[];for(const b of comicBubbles(canvas)){if(!isCurrent())break;const scale=Math.min(1.5,1280/b.w,512/b.h),image=document.createElement('canvas');image.width=Math.round(b.w*scale);image.height=Math.round(b.h*scale);image.getContext('2d').drawImage(canvas,b.x,b.y,Math.min(b.w,canvas.width-b.x),Math.min(b.h,canvas.height-b.y),0,0,image.width,image.height);await worker.setParameters({tessedit_pageseg_mode:'6'});const bubble=await worker.recognize(image,{}, {text:true});refined.push(bubble.data.text);}return {...result.data,refinedTexts:refined};}
 if(!original)return result.data;
 const words=(result.data.blocks??[]).flatMap(b=>b.paragraphs??[]).flatMap(p=>p.lines??[]).filter(l=>(l.confidence??0)>=45&&l.bbox?.x1-l.bbox?.x0>canvas.width*.25&&l.bbox?.y1-l.bbox?.y0<canvas.height*.25).flatMap(l=>l.words??[]).filter(w=>w.bbox&&w.confidence<85&&normalize(w.text).length>=4).sort((a,b)=>a.confidence-b.confidence).slice(0,3);
 for(const word of words){
  if(!isCurrent())return result.data;
  const b=word.bbox,x=Math.max(0,b.x0-4),y=Math.max(0,b.y0-4),w=Math.min(original.width-x,b.x1-b.x0+8),h=Math.min(original.height-y,b.y1-b.y0+8),scale=Math.min(3,1600/w,256/h),image=document.createElement('canvas');image.width=Math.round(w*scale);image.height=Math.round(h*scale);image.getContext('2d').drawImage(original,x,y,w,h,0,0,image.width,image.height);
  await worker.setParameters({tessedit_pageseg_mode:'7'});const reread=await worker.recognize(image,{}, {text:true});if(reread.data.confidence>=80&&reread.data.text.trim()&&reread.data.text.trim().length<150){word.text=reread.data.text.trim();word.confidence=reread.data.confidence;}
 }
 if(words.length){for(const line of (result.data.blocks??[]).flatMap(b=>b.paragraphs??[]).flatMap(p=>p.lines??[]))if(line.words?.length)line.text=line.words.map(w=>w.text).join(' ');result.data.text=(result.data.blocks??[]).flatMap(b=>b.paragraphs??[]).flatMap(p=>p.lines??[]).map(l=>l.text).join('\n');}
 if(region.channel!=='gameplay')return result.data;
 await worker.setParameters({tessedit_pageseg_mode:'6'});
 // Re-read only a detected text paragraph at larger glyph size. No dictionary
 // hints or relaxed matching are used to turn a guess into an exact caption.
 const refined=[];for(const b of refinementBounds(result.data,canvas.width,canvas.height)){
  if(!isCurrent())break;
  const x=Math.max(0,b.x0-6),y=Math.max(0,b.y0-6),w=Math.min(original.width-x,b.x1-b.x0+12),h=Math.min(original.height-y,b.y1-b.y0+12),scale=Math.min(3,2304/w,384/h),image=document.createElement('canvas');image.width=Math.round(w*scale);image.height=Math.round(h*scale);image.getContext('2d').drawImage(original,x,y,w,h,0,0,image.width,image.height);
  const reread=await worker.recognize(image,{}, {text:true});refined.push(reread.data.text);
 }
 return {...result.data,refinedTexts:refined};
}
export function cleanOcrBlocks(blocks){
 function cleanLine(line){
  const words=[...line.words??[]];
  while(words.length&&(words[0].confidence<50||!normalize(words[0].text)))words.shift();
  while(words.length&&(words.at(-1).confidence<50||!normalize(words.at(-1).text)))words.pop();
  const boxes=words.map(w=>w.bbox).filter(Boolean),bbox=boxes.length?{x0:Math.min(...boxes.map(b=>b.x0)),x1:Math.max(...boxes.map(b=>b.x1)),y0:Math.min(...boxes.map(b=>b.y0)),y1:Math.max(...boxes.map(b=>b.y1))}:line.bbox;
  return words.length?{...line,bbox,text:words.map(w=>w.text).join(' '),confidence:words.reduce((n,w)=>n+w.confidence,0)/words.length}:line;
 }
 return (blocks??[]).map(block=>({...block,paragraphs:(block.paragraphs??[]).map(paragraph=>({...paragraph,lines:(paragraph.lines??[]).map(cleanLine)}))}));
}
export function candidates(data,region,width,height,game){
 const blocks=cleanOcrBlocks(data.blocks);
 let lines=data.text.split('\n').map(s=>s.trim()).filter(Boolean),menu=false;
 if(region.channel!=='dialogue'&&blocks.length)lines=blocks.flatMap(b=>b.paragraphs).flatMap(p=>p.lines).filter(l=>(l.confidence??100)>=45&&normalize(l.text).length>=6).map(l=>l.text);
 if(region.channel==='dialogue'&&!['zzz','pragmata','hito'].includes(game)){const filtered=subtitleRows(blocks,region.crop,width,height,game);lines=filtered.lines;menu=filtered.menu;}
 if(/(?:press|hold)\s+(?:to|[a-z])|skip dialogue|confirm selection|选择回答|跳过剧情/i.test(data.text))return {values:[],menu};
 if(lines.length>18||region.channel!=='dialogue'&&lines.length>8)lines=[];
 // Keep bilingual rows apart and remove authored speaker prefixes.
 lines=lines.flatMap(line=>line.split(/(?<=[。！？])\s*(?=[A-Za-z])|(?<=[.!?])\s*(?=[\u3400-\u9fff])|\s*[~～]\s*/)).filter(line=>normalize(line));
 const values=[];for(let i=0;i<lines.length;i++)for(let j=i+1;j<=Math.min(lines.length,i+6);j++){const block=lines.slice(i,j);if(new Set(block.map(s=>/[\u3400-\u9fff]/.test(s))).size>1)continue;const value=block.join(' ');if(region.channel==='dialogue'||normalize(value).length>=(/[\u3400-\u9fff]/.test(value)?6:12)){values.push(value);if(/[:：]/.test(value))values.push(value.split(/[:：]/).slice(1).join(':').trim());}}
 for(const text of data.refinedTexts??[])values.push(...candidates({text,blocks:[]},region,width,height,game).values);
 return {values:[...new Set(values)].sort((a,b)=>b.length-a.length),menu};
}
