import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
export function dependencyNotices(){
 const lock=JSON.parse(readFileSync('package-lock.json','utf8')),blocks=[];
 for(const [path,entry] of Object.entries(lock.packages??{})){
  if(!path.startsWith('node_modules/'))continue;
  const directory=resolve(path);if(!directory.startsWith(resolve('node_modules')+'/')&&!directory.startsWith(resolve('node_modules')+'\\'))throw new Error('Unsafe dependency license path');
  if(!existsSync(directory))continue;
  const notices=readdirSync(directory).filter(name=>/^(?:licen[cs]e|notice|copying)(?:[.-].*)?$/i.test(name));
  for(const file of notices){try{blocks.push(path+' @ '+entry.version+' — '+file+'\n'+readFileSync(join(directory,file),'utf8'));}catch(error){if(error.code!=='EISDIR')throw error;}}
 }
 if(!blocks.length)throw new Error('Dependency license notices missing');
 // next/font downloads these assets at build time, outside the npm dependency tree.
 blocks.push('Geist and Geist Mono — styles/GEIST-OFL.txt\n'+readFileSync('styles/GEIST-OFL.txt','utf8'));
 if(existsSync('public/mobile-capture/pairing/LICENSE-QRCODE.txt'))blocks.push('qrcode-generator 2.0.4 — MIT\n'+readFileSync('public/mobile-capture/pairing/LICENSE-QRCODE.txt','utf8'));
 return 'Third-party dependency notices from the locked installation. These licenses remain independent of the project license.\n\n'+blocks.join('\n\n--------------------\n\n')+'\n';
}
