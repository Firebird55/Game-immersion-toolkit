import {build} from 'vite';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,existsSync,mkdirSync,readdirSync} from 'node:fs';
function fingerprint(){
 const hash=createHash('sha256');
 for(const root of ['mobile','lib','vendor/lexirise-components','public/mobile-capture']){
  for(const file of readdirSync(root,{recursive:true}).map(String).sort()){
   if(!/\.(?:jsx?|tsx?|css|json|mjs)$/.test(file)||file==='companion.js'||file==='companion.css'||file.replaceAll('\\','/').startsWith('ocr/'))continue;
   const path=root+'/'+file;hash.update(path);hash.update(readFileSync(path));
  }
 }
 for(const path of ['package-lock.json','scripts/build-browser-reader.mjs'])hash.update(readFileSync(path));
 return hash.digest('hex');
}
export async function buildBrowserReader(){
 const key=fingerprint(),receipt='output/build-cache/browser-reader.json',outputs=['public/mobile-capture/companion.js','public/mobile-capture/companion.css'];
 if(existsSync(receipt)&&outputs.every(existsSync)){
  const prior=JSON.parse(readFileSync(receipt,'utf8'));
  if(prior.key===key&&outputs.every(path=>prior.outputs[path]===createHash('sha256').update(readFileSync(path)).digest('hex'))){console.log('Browser reader unchanged; reusing verified output.');return;}
 }
 await build({configFile:false,publicDir:false,define:{'process.env.NODE_ENV':'"production"'},logLevel:'warn',build:{target:'es2022',outDir:'public/mobile-capture',emptyOutDir:false,minify:true,cssCodeSplit:false,lib:{entry:fileURLToPath(new URL('../mobile/companion.jsx',import.meta.url)),formats:['es'],fileName:()=> 'companion.js',cssFileName:'companion'},rollupOptions:{onwarn(warning,warn){if(warning.code!=='MODULE_LEVEL_DIRECTIVE')warn(warning);},output:{assetFileNames:'companion.[ext]'}}}});
 mkdirSync('output/build-cache',{recursive:true});writeFileSync(receipt,JSON.stringify({key,outputs:Object.fromEntries(outputs.map(path=>[path,createHash('sha256').update(readFileSync(path)).digest('hex')]))}));
}
if(process.argv[1]===fileURLToPath(import.meta.url))await buildBrowserReader();
