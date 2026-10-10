import test from 'node:test';import assert from 'node:assert/strict';import {mkdtempSync,mkdirSync,writeFileSync,existsSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';import {copyBuiltFrontend} from '../scripts/distribution-assets.mjs';
test('packaging keeps deployable assets while omitting state produced by browser verification',()=>{
 const root=mkdtempSync(join(tmpdir(),'toolkit-distribution-')),source=join(root,'dist'),target=join(root,'package');
 const names=['server/wrangler.json','client/index.html','server/.wrangler/state/v3/cache/metadata.sqlite','server/.wrangler/state/config.json','client/.cache/runtime.txt','server/request.log'];
 for(const name of names){const file=join(source,name);mkdirSync(join(file,'..'),{recursive:true});writeFileSync(file,'fixture');}
 copyBuiltFrontend(source,target);
 for(const name of names.slice(0,2))assert(existsSync(join(target,name)),'Missing application asset: '+name);
 for(const name of names.slice(2))assert(!existsSync(join(target,name)),'Runtime material copied: '+name);
});
