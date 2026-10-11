import {inflateRawSync,gunzipSync} from 'node:zlib';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const trustedOcr=JSON.parse(readFileSync(new URL('./mobile-ocr-integrity.json',import.meta.url))).files;
export const credentialPatterns=[/lx_[A-Za-z0-9]{40,}/,/gh[pousr]_[A-Za-z0-9]{30,}/,/github_pat_[A-Za-z0-9_]{30,}/,/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,/(?:AKIA|ASIA)[0-9A-Z]{16}/,/sk-(?:proj-|ant-)?[A-Za-z0-9_-]{40,}/,/xox[baprs]-[A-Za-z0-9-]{24,}/];
export function scanContent(data,label){
 const text=data.toString('utf8');
 if(credentialPatterns.some(p=>p.test(text))){
  // The upstream wrappers contain base64 WASM with chance credential-shaped
  // substrings. Only exact pinned bytes in the bundled OCR location qualify.
  const entry=label.match(/(?:^|\/)dist\/client\/mobile-capture\/(ocr\/core\/[^/]+\.wasm\.js)$/)?.[1];
  if(!entry||trustedOcr[entry]!==createHash('sha256').update(data).digest('hex'))throw new Error('Potential credential: '+label);
 }
 if(/[A-Z]:[\\/]+Users[\\/]+(?!Public\b|Default\b)[^\s"'<>\\/]+/i.test(text))throw new Error('Personal profile path: '+label);
}
export function privatePath(name){return /(?:^|\/)(?:data|node_modules|\.git|\.venv|output|outputs|diagnostics|work|\.watch)(?:\/|$)/i.test(name)||/(?:^|\/)\.env(?:\.|$)/i.test(name)||/\.(?:catalog|voices-[a-f0-9]+)\.zip$/i.test(name)||/\.(?:dpapi|db|sqlite(?:3)?|mp3|wav|mp4|wmv|onemodel|dll|exe|pdb|pem|key|pak(?:[._-][a-z0-9._-]+)?|pck|wem|bnk|blk|archive|asar|w3speech|w3strings|utoc|ucas|locres|hpw|unity3d|assets|bundle|usm|srt(?:_[a-z0-9-]+)?|usmap|uasset|uexp|ubulk)$/i.test(name);}
export function archiveEntries(data,name){
 const entries=[];
 if(name.endsWith('.zip')){
  let end=-1;for(let i=data.length-22;i>=Math.max(0,data.length-65557);i--)if(data.readUInt32LE(i)===0x06054b50){end=i;break;}
  if(end<0)throw new Error('Invalid ZIP');let cursor=data.readUInt32LE(end+16);const count=data.readUInt16LE(end+10);
  for(let i=0;i<count;i++){
   if(data.readUInt32LE(cursor)!==0x02014b50)throw new Error('Invalid ZIP directory');
   const n=data.readUInt16LE(cursor+28),extra=data.readUInt16LE(cursor+30),comment=data.readUInt16LE(cursor+32),size=data.readUInt32LE(cursor+24),compressed=data.readUInt32LE(cursor+20),method=data.readUInt16LE(cursor+10),local=data.readUInt32LE(cursor+42);
   if(size>200*1024*1024)throw new Error('Oversized archive entry');
   const file=data.subarray(cursor+46,cursor+46+n).toString();cursor+=46+n+extra+comment;
   if(file.endsWith('/'))continue;
   if(data.readUInt16LE(local+6)&1)throw new Error('Encrypted archive cannot be audited');
   const start=local+30+data.readUInt16LE(local+26)+data.readUInt16LE(local+28),bytes=data.subarray(start,start+compressed);
   const content=method===0?bytes:method===8?inflateRawSync(bytes,{maxOutputLength:200*1024*1024}):null;
   if(!content||content.length!==size)throw new Error('Unsupported archive compression');entries.push({name:file,data:content});
  }
 }else{
  const tar=name.endsWith('.tar')?data:gunzipSync(data,{maxOutputLength:200*1024*1024});
  for(let at=0;at+512<=tar.length;){
   const header=tar.subarray(at,at+512);if(header.every(x=>x===0))break;
   const str=(a,b)=>header.subarray(a,b).toString().replace(/\0.*$/s,'');
   const file=[str(345,500),str(0,100)].filter(Boolean).join('/'),size=parseInt(str(124,136).trim(),8)||0,type=str(156,157);
   if(!['','0','5','x','g'].includes(type))throw new Error('Unsupported archive link or special entry');
   if(type===''||type==='0')entries.push({name:file,data:tar.subarray(at+512,at+512+size)});
   at+=512+Math.ceil(size/512)*512;
  }
 }
 return entries;
}
export function scanArtifact(data,name,depth=0){
 if(depth>5)throw new Error('Archive nesting limit');scanContent(data,name);
 if(/\.(?:zip|tgz|tar|tar\.gz)$/.test(name)){
  const entries=archiveEntries(data,name);
  for(const entry of entries){
   if(entry.name.includes('\\')||entry.name.startsWith('/')||entry.name.split('/').includes('..')||privatePath(entry.name))throw new Error('Private or unsafe archive entry: '+entry.name);
   scanArtifact(entry.data,entry.name,depth+1);
  }
  return entries;
 }
 return [];
}
