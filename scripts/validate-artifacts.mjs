import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {scanArtifact} from './publication-scan.mjs';
const pkg=JSON.parse(readFileSync('package.json','utf8'));
const sums=readFileSync('release/SHA256SUMS','utf8').trim().split('\n');
for(const line of sums){
 const [hash,file]=line.split('  ');if(!file||file.includes('/')||file.includes('\\')||file.includes('..')||!/^[a-f0-9]{64}$/.test(hash))throw new Error('Unsafe checksum entry');
 const data=readFileSync('release/'+file);if(createHash('sha256').update(data).digest('hex')!==hash)throw new Error('Checksum mismatch');
 const entries=scanArtifact(data,file);
 if(/\.(zip|tgz)$/.test(file)){
  for(const required of ['LICENSE','NOTICE.md','AGENTS.md','CONTRIBUTING.md'])if(!entries.some(e=>e.name===required||e.name.endsWith('/'+required)))throw new Error('Missing distribution notice: '+required);
  if(pkg.name==='game-immersion-toolkit'&&!entries.some(e=>e.name.includes('/dist/client/')))throw new Error('Built frontend missing');
 }
}
for(const required of ['LICENSE','NOTICE.md'])if(!sums.some(s=>s.endsWith('  '+required)))throw new Error('Missing standalone notice');
const provenance=JSON.parse(readFileSync('release/PROVENANCE.json','utf8'));
if(provenance.version!==pkg.version||provenance.sourceCommit!==execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim())throw new Error('Provenance mismatch');
console.log('Decompressed archives, licenses, checksums and provenance verified.');
