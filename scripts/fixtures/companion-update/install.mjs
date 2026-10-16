import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
mkdirSync('node_modules/wrangler/bin',{recursive:true});
writeFileSync('node_modules/wrangler/package.json',JSON.stringify({type:'module'}));
writeFileSync('node_modules/wrangler/bin/wrangler.js',readFileSync('scripts/fixture-front.mjs'));
