import {normalize,subtitleRows} from './library.mjs';
export const crops={zzz:[.08,.67,.84,.25],wuwa:[.10,.64,.80,.32],pragmata:[.08,.67,.84,.25],cyberpunk:[.12,.59,.76,.37],witcher3:[.08,.63,.84,.34],nte:[.10,.70,.80,.28],honkai3:[.04,.72,.96,.24],hito:[.35,.765,.365,.18]};
export const extraCrops={cyberpunk:{overhead:[.10,.12,.70,.62]},witcher3:{overhead:[.08,0,.76,.74]},wuwa:{card:[.12,.20,.76,.43]},zzz:{comic:[.04,.06,.92,.88]}};
export function regions(game,crop=crops[game],extra=true,cinematic=true,custom={}){
 const result=[{crop,channel:'dialogue'}];
 if(extra&&['cyberpunk','witcher3'].includes(game)){
  const [left,top,width,height]=custom.overhead??extraCrops[game].overhead;
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
 const [left,top,width,height]=region,cw=pw*width,ch=ph*height,requested=Math.min(2,1440/h,2304/cw,1024/ch),scale=requested>=1?Math.floor(requested):requested;
 canvas.width=Math.max(1,Math.round(cw*scale));canvas.height=Math.max(1,Math.round(ch*scale));canvas.getContext('2d',{willReadFrequently:true}).drawImage(source,x+pw*left,y+ph*top,cw,ch,0,0,canvas.width,canvas.height);return canvas;
}
export function prepareImage(canvas,region,language){
 const context=canvas.getContext('2d',{willReadFrequently:true}),pixels=context.getImageData(0,0,canvas.width,canvas.height);let dark=0,total=0,black=0;
 for(let i=0;i<pixels.data.length;i+=64){total++;const sum=pixels.data[i]+pixels.data[i+1]+pixels.data[i+2];if(sum<240)dark++;if(sum<100)black++;}
 if(region.black&&black/total<.75)return false;
 if(region.ink||language.includes('chi_sim')&&dark/total>.75){for(let i=0;i<pixels.data.length;i+=4){const r=pixels.data[i],g=pixels.data[i+1],b=pixels.data[i+2],foreground=region.ink==='blue'?r>65&&g>80&&b>90&&(b-r>4||Math.min(r,g,b)>170)&&Math.max(r,g,b)-Math.min(r,g,b)<85:region.ink==='white'?Math.min(r,g,b)>175&&Math.max(r,g,b)-Math.min(r,g,b)<65:r+g+b>300;const value=foreground?0:255;pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=value;}context.putImageData(pixels,0,0);}
 return true;
}
export function cleanOcrBlocks(blocks){return (blocks??[]).map(block=>({...block,paragraphs:(block.paragraphs??[]).map(paragraph=>({...paragraph,lines:(paragraph.lines??[]).map(line=>{const words=[...line.words??[]];while(words.length&&(words[0].confidence<50||!normalize(words[0].text)))words.shift();while(words.length&&(words.at(-1).confidence<50||!normalize(words.at(-1).text)))words.pop();return words.length?{...line,text:words.map(w=>w.text).join(' '),confidence:words.reduce((n,w)=>n+w.confidence,0)/words.length}:line;}))}))}));}
export function candidates(data,region,width,height,game){
 const blocks=cleanOcrBlocks(data.blocks);
 let lines=data.text.split('\n').map(s=>s.trim()).filter(Boolean),menu=false;
 if(region.channel!=='dialogue'&&blocks.length)lines=blocks.flatMap(b=>b.paragraphs).flatMap(p=>p.lines).filter(l=>(l.confidence??100)>=45&&normalize(l.text).length>=6).map(l=>l.text);
 if(region.channel==='dialogue'&&!['zzz','pragmata','hito'].includes(game)){const filtered=subtitleRows(blocks,region.crop,width,height,game);lines=filtered.lines;menu=filtered.menu;}
 if(lines.length>18||region.channel!=='dialogue'&&lines.length>8||/(?:press|hold)\s+(?:to|[a-z])|skip dialogue|confirm selection|选择回答|跳过剧情/i.test(data.text))return {values:[],menu};
 // Keep bilingual rows apart and remove authored speaker prefixes.
 lines=lines.flatMap(line=>line.split(/(?<=[。！？])\s*(?=[A-Za-z])|(?<=[.!?])\s*(?=[\u3400-\u9fff])|\s*[~～]\s*/)).filter(line=>normalize(line));
 const values=[];for(let i=0;i<lines.length;i++)for(let j=i+1;j<=Math.min(lines.length,i+6);j++){const block=lines.slice(i,j);if(new Set(block.map(s=>/[\u3400-\u9fff]/.test(s))).size>1)continue;const value=block.join(' ');if(region.channel==='dialogue'||normalize(value).length>=(/[\u3400-\u9fff]/.test(value)?6:12)){values.push(value);if(/[:：]/.test(value))values.push(value.split(/[:：]/).slice(1).join(':').trim());}}
 return {values:values.sort((a,b)=>b.length-a.length),menu};
}
