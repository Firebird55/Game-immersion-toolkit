import {mkdirSync,writeFileSync} from 'node:fs';
mkdirSync('dist/server',{recursive:true});
mkdirSync('dist/client/_next/static',{recursive:true});
writeFileSync('dist/server/wrangler.json','{}');
writeFileSync('dist/client/_next/static/reader.js','fixture asset');
