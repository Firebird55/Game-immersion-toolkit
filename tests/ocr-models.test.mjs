import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const manifest=JSON.parse(readFileSync('public/mobile-capture/ocr-models.json','utf8'));
test('Every advertised OCR locale resolves to a pinned, size-bounded model',()=>{
 assert(Object.keys(manifest.locales).length>=28);
 for(const code of Object.values(manifest.locales))assert(manifest.models[code]);
 for(const [code,model] of Object.entries(manifest.models)){
  assert(Number.isSafeInteger(model.bytes)&&model.bytes>0&&model.bytes<100*1024**2);
  assert.match(model.sha256,/^[a-f0-9]{64}$/);
  assert.equal(model.builtin?model.url:`https://cdn.jsdelivr.net/npm/@tesseract.js-data/${code}@1.0.0/4.0.0_best_int/${code}.traineddata.gz`,model.url);
 }
});
