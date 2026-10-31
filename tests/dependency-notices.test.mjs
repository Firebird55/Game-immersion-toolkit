import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {dependencyNoticeAudit,dependencyNotices} from '../scripts/dependency-notices.mjs';

function fixture(t,packages){
 const root=mkdtempSync(join(tmpdir(),'toolkit-notices-'));
 t.after(()=>rmSync(root,{recursive:true,force:true}));
 const put=(name,text)=>{const path=join(root,name);mkdirSync(join(path,'..'),{recursive:true});writeFileSync(path,typeof text==='object'?JSON.stringify(text):text);};
 put('package-lock.json',{packages});put('styles/GEIST-OFL.txt','Authored test font terms');
 return {root,put};
}
const entry={version:'1.0.0',integrity:'sha512-authored-fixture'};

test('collects complete nested vendor and LICENSES directory notices',t=>{
 const {root,put}=fixture(t,{'node_modules/example':entry});
 put('node_modules/example/package.json',{name:'example',version:'1.0.0'});
 put('node_modules/example/LICENSE','Primary authored terms');
 put('node_modules/example/dist/vendor/d3/LICENSE','Independent vendor terms');
 put('node_modules/example/LICENSES/Apache-2.0.txt','Independent named license');
 const result=dependencyNoticeAudit({root});
 assert.equal(result.omissions.length,0);assert.equal(result.records.length,3);
 assert.ok(result.inputs.some(p=>p.endsWith(join('vendor','d3','LICENSE'))));
 assert.match(dependencyNotices({root}),/Independent vendor terms/);
});

test('a nested vendor license does not supply the primary package grant',t=>{
 const {root,put}=fixture(t,{'node_modules/example':entry});
 put('node_modules/example/package.json',{name:'example',version:'1.0.0',license:'MIT'});
 put('node_modules/example/vendor/LICENSE','Vendor terms only');
 assert.equal(dependencyNoticeAudit({root}).omissions.length,1);
 assert.throws(()=>dependencyNotices({root}),/incomplete/);
});

test('only explicitly incompatible optional and absent dev packages are excluded',t=>{
 const {root}=fixture(t,{
  'node_modules/other-os':{...entry,optional:true,os:['linux']},
  'node_modules/dev':{...entry,dev:true},
  'node_modules/current':{...entry,optional:true,os:['win32']},
  'node_modules/required':entry});
 const audit=dependencyNoticeAudit({root,platform:'win32',arch:'x64'});
 assert.equal(audit.excluded.length,2);assert.equal(audit.omissions.length,2);
 assert.ok(audit.omissions.some(x=>x.package==='node_modules/current'));
});

test('rejects drift between installed metadata and the lock',t=>{
 const {root,put}=fixture(t,{'node_modules/example':entry});
 put('node_modules/example/package.json',{name:'example',version:'2.0.0'});
 assert.throws(()=>dependencyNoticeAudit({root}),/version differs/);
});

function supplemented(t){
 const {root,put}=fixture(t,{'node_modules/example':entry});
 const declaration={name:'example',version:'1.0.0',license:'MIT',author:'Authored fixture'};
 put('node_modules/example/package.json',declaration);
 const bytes=Buffer.from('Authored permission and warranty fixture');
 put('packaging/frontend-notices/terms.txt',bytes.toString());
 put('packaging/frontend-notices/sources.json',{
  schema:'toolkit-frontend-notice-supplements-v1',
  sources:[{path:'terms.txt',bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),url:'https://example.invalid/exact-source'}],
  packages:[{name:'example',...entry,files:['terms.txt'],resolution:'declared-license-by-reference',declaration,copyright_notice:'No copyright statement supplied.'}]});
 return {root,put};
}

test('exact declared-license resolution retains attribution without invented copyright',t=>{
 const {root}=supplemented(t);const audit=dependencyNoticeAudit({root});
 assert.equal(audit.omissions.length,0);
 assert.match(dependencyNotices({root}),/declared-license-by-reference/);
 assert.match(dependencyNotices({root}),/No copyright statement supplied/);
 assert.equal(audit.inputs.length,3);
});

test('a changed supplement cannot inherit its previous pin',t=>{
 const {root,put}=supplemented(t);put('packaging/frontend-notices/terms.txt','Changed');
 assert.throws(()=>dependencyNoticeAudit({root}),/Pinned frontend notice changed/);
});

test('a different installed author declaration cannot inherit a pinned resolution',t=>{
 const {root,put}=supplemented(t);put('node_modules/example/package.json',{name:'example',version:'1.0.0',license:'MIT',author:'Different author'});
 assert.throws(()=>dependencyNoticeAudit({root}),/declaration differs/);
});

test('rejects package traversal before opening a notice',t=>{
 const {root}=fixture(t,{'node_modules/../../outside':entry});
 assert.throws(()=>dependencyNoticeAudit({root}),/Unsafe dependency notice path/);
});
