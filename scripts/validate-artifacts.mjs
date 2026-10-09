
import {readFileSync,statSync} from 'node:fs';import {createHash} from 'node:crypto';import {execFileSync} from 'node:child_process';

function zipNames(data){
 let end=-1;for(let i=data.length-22;i>=Math.max(0,data.length-65557);i--)if(data.readUInt32LE(i)===0x06054b50){end=i;break;}
 if(end<0)throw new Error('Invalid ZIP end record');
 const count=data.readUInt16LE(end+10);let cursor=data.readUInt32LE(end+16);const names=[];
 for(let i=0;i<count;i++){if(data.readUInt32LE(cursor)!==0x02014b50)throw new Error('Invalid ZIP directory');
 const n=data.readUInt16LE(cursor+28),extra=data.readUInt16LE(cursor+30),comment=data.readUInt16LE(cursor+32);
 names.push(data.subarray(cursor+46,cursor+46+n).toString('utf8'));cursor+=46+n+extra+comment;}
 return names;
}

const sums=readFileSync('release/SHA256SUMS','utf8').trim().split('\n'),pkg=JSON.parse(readFileSync('package.json','utf8'));
for(const line of sums){const [hash,file]=line.split('  ');if(!file||file.includes('/')||file.includes('..'))throw new Error('Unsafe checksum name');const data=readFileSync('release/'+file);if(createHash('sha256').update(data).digest('hex')!==hash)throw new Error('Checksum mismatch');
 if(/\.(?:js|json|md|txt)$/.test(file)&&/lx_[A-Za-z0-9]{40,}|gh[pousr]_[A-Za-z0-9]{30,}/.test(data.toString()))throw new Error('Secret in artifact');
 if(file.endsWith('.user.js')){if(!data.toString().includes('@version      '+pkg.version)&&!new RegExp('@version\\s+'+pkg.version.replaceAll('.','\\.')).test(data.toString()))throw new Error('Userscript version mismatch');if(/@(?:updateURL|downloadURL)/.test(data.toString()))throw new Error('Private userscript must not embed automatic download credentials');}
 if(file.endsWith('.zip')){const entries=zipNames(data);if(entries.some(p=>/node_modules\/|\/data\/|\.dpapi$|\.db$|\.mp3$|\.wav$|^\.git\//.test(p)))throw new Error('Private/generated asset in ZIP');if(pkg.name==='game-immersion-toolkit'&&!entries.some(p=>p.includes('/dist/client/')))throw new Error('Built frontend missing');}
}
const provenance=JSON.parse(readFileSync('release/PROVENANCE.json','utf8'));
if(provenance.version!==pkg.version||provenance.sourceCommit!==execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim())throw new Error('Artifact provenance mismatch');
console.log('Checksums, metadata and private-artifact boundaries verified.');
