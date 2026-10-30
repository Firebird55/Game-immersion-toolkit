import {execFileSync} from 'node:child_process';
import {readFileSync,lstatSync} from 'node:fs';
import {scanContent,privatePath,reviewedSourceArchive} from './publication-scan.mjs';
const git=(...args)=>execFileSync('git',args,{encoding:'utf8',maxBuffer:128*1024*1024,stdio:['pipe','pipe','pipe']});
const refs=git('for-each-ref','--format=%(refname)').trim().split('\n').filter(r=>r.startsWith('refs/heads/')||r.startsWith('refs/tags/')||r.startsWith('refs/remotes/origin/'));
const commits=[...new Set(git('rev-list','HEAD',...refs).trim().split('\n').filter(Boolean))];
const identity=email=>email==='noreply@github.com'||/^[^\s<>]+@users\.noreply\.github\.com$/.test(email);
if(process.argv.includes('--public')){
 for(const id of commits){const lines=git('show','-s','--format=%ae%n%ce%n%B',id).split('\n');if(!identity(lines[0])||!identity(lines[1]))throw new Error('Personal email in commit metadata; sanitize before publication.');scanContent(Buffer.from(lines.slice(2).join('\n')),'commit message');}
 for(const ref of refs.filter(r=>r.startsWith('refs/tags/'))){const mail=git('for-each-ref','--format=%(taggeremail)',ref).trim().replace(/^<|>$/g,'');if(mail&&!identity(mail))throw new Error('Personal email in tag metadata');}
}
const objects=git('rev-list','--objects','HEAD',...refs).trim().split('\n');
for(const row of objects){const name=row.slice(row.indexOf(' ')+1);if(row.includes(' ')&&privatePath(name))throw new Error('Private path in reachable history: '+name);}
const ids=[...new Set(objects.map(l=>l.split(' ')[0]))];
const batch=execFileSync('git',['cat-file','--batch'],{input:ids.join('\n')+'\n',maxBuffer:512*1024*1024});
let offset=0,blobs=0;
while(offset<batch.length){const end=batch.indexOf(10,offset);if(end<0)break;const [oid,type,length]=batch.subarray(offset,end).toString().split(' ');offset=end+1;const size=Number(length);if(!Number.isFinite(size))throw new Error('Unscannable Git object');if(type==='blob'){blobs++;scanContent(batch.subarray(offset,offset+size),'reachable blob '+oid);}offset+=size+1;}
for(const file of git('ls-files').trim().split('\n').filter(Boolean)){
 if(privatePath(file))throw new Error('Private/generated tracked file: '+file);
 const data=readFileSync(file);
 if(/\.(zip|tgz)$/.test(file)&&!(lstatSync(file).isFile()&&reviewedSourceArchive(file,data)))throw new Error('Private/generated tracked file: '+file);
 scanContent(data,file);
}
console.log('Publication scan passed: '+commits.length+' commits, '+blobs+' blobs and working files.');
