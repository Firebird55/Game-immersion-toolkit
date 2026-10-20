import assert from 'node:assert/strict';
import {readFileSync,readdirSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {ocrAssets} from './mobile-assets.mjs';

// Independent publication boundary: adding a builder asset requires an explicit
// review here. A file-count increase alone must never admit an arbitrary file.
export const previewSources=['interface-copy.mjs','interface-language.mjs','ocr-models.json','caption-confirmation.mjs','games-data.json','games.css','games.mjs','core.mjs','recovery-config.json','relay.mjs','qr-pairing.mjs','qr-render.mjs','qr-ui.mjs','library.mjs','storage.mjs','ocr-packs.mjs','library-worker.mjs','ocr-pipeline.mjs','mobile-ui.mjs','transcript-channel.mjs','pc-provider.mjs','vault.mjs','capture.js','companion.js','companion.css','style.css','icon.svg','icon.png','manifest.webmanifest'];
export function verifyPreviewAssets(root,runtimeAssets=ocrAssets()){
 const names=readdirSync(root).filter(name=>name!=='desktop.ini');
 const expected=['index.html','games.html','build.json','.nojekyll','sw.js','ocr','pairing'];
 for(const source of previewSources){const dot=source.lastIndexOf('.'),stem=source.slice(0,dot),extension=source.slice(dot);
  const found=names.filter(name=>name.startsWith(stem+'.')&&name.endsWith(extension)&&/^[a-f0-9]{16}$/.test(name.slice(stem.length+1,-extension.length)));
  assert.equal(found.length,1,'Exactly one reviewed asset: '+source);
  const content=readFileSync(new URL(found[0],root));assert.equal(found[0],stem+'.'+createHash('sha256').update(content).digest('hex').slice(0,16)+extension,'Asset content matches its name: '+source);expected.push(found[0]);
 }
 assert.deepEqual(names.sort(),expected.sort(),'Publication contains exactly the approved companion and guide assets');
 const files=readdirSync(root,{recursive:true}).map(name=>name.replaceAll('\\','/')).filter(name=>name.split('/').at(-1)!=='desktop.ini'&&statSync(new URL(name,root)).isFile());
 const expectedFiles=[...expected.filter(name=>!['ocr','pairing'].includes(name)),...runtimeAssets.keys()];
 assert.deepEqual(files.sort(),expectedFiles.sort(),'Nested publication files stay within the QR/OCR allowlist');
 for(const[name,bytes]of runtimeAssets)assert.equal(createHash('sha256').update(readFileSync(new URL(name,root))).digest('hex'),createHash('sha256').update(bytes).digest('hex'),'Pinned QR/OCR bytes: '+name);
}
