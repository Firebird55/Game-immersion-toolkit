import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
// Exact npm versions/integrities are pinned in package-lock.json. No game files enter this map.
export function ocrAssets(){
 const files=new Map();
 files.set('ocr/verified-worker.js',readFileSync('scripts/ocr-worker-compat.js'));
 for(const name of ['tesseract.esm.min.js','worker.min.js','worker.min.js.LICENSE.txt','tesseract.min.js.LICENSE.txt'])files.set('ocr/'+name,readFileSync('node_modules/tesseract.js/dist/'+name));
 for(const name of readdirSync('node_modules/tesseract.js-core').filter(n=>/^tesseract-core.*\.wasm(?:\.js)?$/.test(n)))files.set('ocr/core/'+name,readFileSync('node_modules/tesseract.js-core/'+name));
 for(const code of ['eng','chi_sim','chi_tra'])files.set('ocr/lang/'+code+'.traineddata.gz',readFileSync(`node_modules/@tesseract.js-data/${code}/4.0.0_best_int/${code}.traineddata.gz`));
 files.set('ocr/opencc.mjs',readFileSync('node_modules/opencc-js/dist/esm/t2cn.js'));
 files.set('ocr/LICENSE-OPENCC.txt',readFileSync('node_modules/opencc-js/LICENSE'));
 files.set('ocr/NOTICE-OPENCC.txt',readFileSync('node_modules/opencc-js/THIRD_PARTY_LICENSES.md'));
 files.set('ocr/LICENSE-OPENCC-APACHE.txt',readFileSync('node_modules/opencc-js/LICENSES/Apache-2.0.txt'));
 files.set('ocr/LICENSE-APACHE.txt',readFileSync('node_modules/tesseract.js-core/LICENSE'));
 files.set('ocr/NOTICE.txt',Buffer.from('Tesseract.js 7.0.0 and Tesseract.js-core 7.0.0: Apache-2.0. https://github.com/naptha/tesseract.js\nEnglish/Simplified Chinese/Traditional Chinese traineddata: naptha/tessdata, Apache-2.0. https://github.com/naptha/tessdata/blob/gh-pages/LICENSE\nLanguage npm packaging: @tesseract.js-data/eng, chi_sim and chi_tra 1.0.0 (MIT metadata). Model files retain the upstream Apache license.\nOpenCC-JS 1.4.2: MIT implementation and Apache-2.0 dictionary derivatives. https://github.com/nk2028/opencc-js\nAll files are served locally. No images are sent to an OCR service.\n'));
 const checks=Object.fromEntries([...files].map(([name,data])=>[name,createHash('sha256').update(data).digest('hex')]));
 const trusted=JSON.parse(readFileSync(new URL('./mobile-ocr-integrity.json',import.meta.url))).files;
 for(const [name,sha] of Object.entries(trusted))if(checks[name]!==sha)throw new Error('Pinned OCR runtime bytes changed: '+name);
 files.set('ocr/checksums.json',Buffer.from(JSON.stringify(checks)));
 // QR transfer stays on the devices; pin and self-host its runtime and notices.
 files.set('pairing/qrcode.mjs',readFileSync('node_modules/qrcode-generator/dist/qrcode.mjs'));
 const scanner=readFileSync('node_modules/jsqr/dist/jsQR.js','utf8');
 files.set('pairing/jsqr.mjs',Buffer.from('const module={exports:{}};const exports=module.exports;\n'+scanner+'\nexport default module.exports;\n'));
 files.set('pairing/fflate.mjs',readFileSync('node_modules/fflate/esm/browser.js'));
 files.set('pairing/LICENSE-JSQR.txt',readFileSync('node_modules/jsqr/LICENSE'));
 files.set('pairing/LICENSE-FFLATE.txt',readFileSync('node_modules/fflate/LICENSE'));
 files.set('pairing/LICENSE-QRCODE.txt',Buffer.from('Copyright (c) 2009 Kazuhiko Arase\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\n'));
 return files;
}
export const mime=name=>name.endsWith('.wasm')?'application/wasm':name.endsWith('.gz')?'application/gzip':name.endsWith('.json')||name.endsWith('.webmanifest')?'application/json':name.endsWith('.css')?'text/css':name.endsWith('.html')?'text/html':name.endsWith('.svg')?'image/svg+xml':name.endsWith('.png')?'image/png':name.endsWith('.txt')?'text/plain':'text/javascript';
