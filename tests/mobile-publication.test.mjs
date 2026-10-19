import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdirSync,mkdtempSync,writeFileSync,unlinkSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,sep,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {previewSources,verifyPreviewAssets} from '../scripts/mobile-publication.mjs';

test('publication boundary admits the guide and rejects substitutions, extra files and changed nested assets',t=>{
 const parent=resolve(tmpdir()),directory=mkdtempSync(resolve(parent,'game-publication-')),root=pathToFileURL(directory+sep);
 t.after(()=>{assert(directory.startsWith(parent+sep+'game-publication-'));rmSync(directory,{recursive:true,force:true});});
 const put=(name,bytes)=>{const path=resolve(directory,name);assert(path.startsWith(directory+sep));mkdirSync(dirname(path),{recursive:true});writeFileSync(path,bytes);};
 for(const name of ['index.html','games.html','build.json','.nojekyll','sw.js'])put(name,'owned publication fixture');
 const hashed=new Map();for(const source of previewSources){const bytes=Buffer.from(source),dot=source.lastIndexOf('.'),name=source.slice(0,dot)+'.'+createHash('sha256').update(bytes).digest('hex').slice(0,16)+source.slice(dot);put(name,bytes);hashed.set(source,name);}
 const runtimeAssets=new Map([['ocr/runtime.mjs',Buffer.from('owned OCR fixture')],['pairing/jsqr.mjs',Buffer.from('owned QR fixture')]]);
 for(const [name,bytes]of runtimeAssets)put(name,bytes);
 const verify=()=>verifyPreviewAssets(root,runtimeAssets);
 assert.doesNotThrow(verify);
 // An arbitrary replacement must fail even when the root file count is unchanged.
 const css=hashed.get('games.css');unlinkSync(resolve(directory,css));put('private.db','owned negative fixture');assert.throws(verify,/games.css/);unlinkSync(resolve(directory,'private.db'));put(css,Buffer.from('games.css'));
 put('unreviewed.json','{}');assert.throws(verify,/exactly the approved/);unlinkSync(resolve(directory,'unreviewed.json'));
 put('ocr/unreviewed.txt','owned negative fixture');assert.throws(verify,/Nested publication/);unlinkSync(resolve(directory,'ocr/unreviewed.txt'));
 put('pairing/jsqr.mjs','changed owned fixture');assert.throws(verify,/Pinned QR\/OCR/);
});
