import test from 'node:test';import assert from 'node:assert/strict';import {gzipSync} from 'node:zlib';
import {scanArtifact,scanContent,privatePath} from '../scripts/publication-scan.mjs';
function tgz(name,text){const h=Buffer.alloc(512);h.write(name);h.write('0000644',100);h.write('0000000',108);h.write('0000000',116);h.write(Buffer.byteLength(text).toString(8).padStart(11,'0'),124);h[156]=48;const b=Buffer.from(text);return gzipSync(Buffer.concat([h,b,Buffer.alloc((512-b.length%512)%512),Buffer.alloc(1024)]));}
test('archive scan inspects compressed payloads and rejects private paths',()=>{
 assert.throws(()=>scanArtifact(tgz('package/source.js','ghp_'+ 'a'.repeat(40)),'package.tgz'),/credential/);
 assert.throws(()=>scanArtifact(tgz('package/data/cache.db','local'),'package.tgz'),/Private/);
 assert.throws(()=>scanArtifact(tgz('../outside','text'),'package.tgz'),/unsafe/);
 assert.equal(scanArtifact(tgz('package/LICENSE','Project license'),'package.tgz').length,1);
});
test('profile paths and credentials are rejected without echoing their values',()=>{
 assert.throws(()=>scanContent(Buffer.from('C:/'+['Users','example','private'].join('/')),'fixture'),/profile path: fixture/);
 assert(privatePath('data/new-game/index.db'));assert(!privatePath('backend/data-model.py'));
});
