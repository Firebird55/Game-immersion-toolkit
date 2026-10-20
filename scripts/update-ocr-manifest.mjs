// Explicit maintenance command; never executed by a normal build.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const locales={en:'eng',nl:'nld','zh-Hans':'chi_sim','zh-Hant':'chi_tra',ja:'jpn',ko:'kor',fr:'fra',it:'ita',de:'deu','es-ES':'spa','es-419':'spa','pt-BR':'por','pt-PT':'por',ru:'rus',pl:'pol',ar:'ara',cs:'ces',hu:'hun',th:'tha',tr:'tur',uk:'ukr',da:'dan',fi:'fin',el:'ell',no:'nor',sv:'swe',id:'ind',vi:'vie'};
const models={};
for(const code of new Set(Object.values(locales))){
 const builtin=['eng','chi_sim','chi_tra'].includes(code);
 const url=`https://cdn.jsdelivr.net/npm/@tesseract.js-data/${code}@1.0.0/4.0.0_best_int/${code}.traineddata.gz`;
 const bytes=builtin?readFileSync(`node_modules/@tesseract.js-data/${code}/4.0.0_best_int/${code}.traineddata.gz`):await fetch(url).then(async r=>{if(!r.ok)throw Error(`${code}: HTTP ${r.status}`);return Buffer.from(await r.arrayBuffer());});
 models[code]={url:builtin?`./ocr/lang/${code}.traineddata.gz`:url,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),builtin,license:'Apache-2.0',packageVersion:'1.0.0'};
 console.log(`${code}: ${bytes.length} bytes`);
}
writeFileSync('public/mobile-capture/ocr-models.json',JSON.stringify({format:1,locales,models},null,2)+'\n');
