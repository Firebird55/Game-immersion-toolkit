import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
// Exact npm versions/integrities are pinned in package-lock.json. No game files enter this map.
export function ocrAssets(){
 const files=new Map();
 for(const name of ['tesseract.esm.min.js','worker.min.js','worker.min.js.LICENSE.txt','tesseract.min.js.LICENSE.txt'])files.set('ocr/'+name,readFileSync('node_modules/tesseract.js/dist/'+name));
 for(const name of readdirSync('node_modules/tesseract.js-core').filter(n=>/^tesseract-core.*\.wasm(?:\.js)?$/.test(n)))files.set('ocr/core/'+name,readFileSync('node_modules/tesseract.js-core/'+name));
 for(const code of ['eng','chi_sim'])files.set('ocr/lang/'+code+'.traineddata.gz',readFileSync(`node_modules/@tesseract.js-data/${code}/4.0.0_best_int/${code}.traineddata.gz`));
 files.set('ocr/LICENSE-APACHE.txt',readFileSync('node_modules/tesseract.js-core/LICENSE'));
 files.set('ocr/NOTICE.txt',Buffer.from('Tesseract.js 7.0.0 and Tesseract.js-core 7.0.0: Apache-2.0. https://github.com/naptha/tesseract.js\nEnglish/Simplified Chinese traineddata: naptha/tessdata, Apache-2.0. https://github.com/naptha/tessdata/blob/gh-pages/LICENSE\nLanguage npm packaging: @tesseract.js-data/eng and chi_sim 1.0.0 (MIT metadata). Model files retain the upstream Apache license.\nAll files are served locally. No images are sent to an OCR service.\n'));
 const checks=Object.fromEntries([...files].map(([name,data])=>[name,createHash('sha256').update(data).digest('hex')]));
 const trusted=JSON.parse(readFileSync(new URL('./mobile-ocr-integrity.json',import.meta.url))).files;
 for(const [name,sha] of Object.entries(trusted))if(checks[name]!==sha)throw new Error('Pinned OCR runtime bytes changed: '+name);
 files.set('ocr/checksums.json',Buffer.from(JSON.stringify(checks)));
 return files;
}
export const mime=name=>name.endsWith('.wasm')?'application/wasm':name.endsWith('.gz')?'application/gzip':name.endsWith('.json')||name.endsWith('.webmanifest')?'application/json':name.endsWith('.css')?'text/css':name.endsWith('.html')?'text/html':name.endsWith('.svg')?'image/svg+xml':name.endsWith('.png')?'image/png':name.endsWith('.txt')?'text/plain':'text/javascript';
