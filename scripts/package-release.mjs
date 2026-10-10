
import {execFileSync} from 'node:child_process';
import {mkdirSync,readFileSync,writeFileSync,copyFileSync,readdirSync,cpSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dependencyNotices} from './dependency-notices.mjs';
import {copyBuiltFrontend} from './distribution-assets.mjs';
const pkg=JSON.parse(readFileSync('package.json','utf8')),version=pkg.version;
if(!/^\d+\.\d+\.\d+(?:-[\w.-]+)?$/.test(version))throw new Error('Unsafe package version');
if(process.env.GITHUB_REF?.startsWith('refs/tags/')&&process.env.GITHUB_REF!=='refs/tags/v'+version)throw new Error('Release tag and version differ');
const sha=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
const repository=process.env.GITHUB_REPOSITORY||({ '@firebird55/lexirise-components':'Firebird55/Lexirise-shared-components','emulingo-lexirise':'Firebird55/Emulingo-Lexirise-userscript','game-immersion-toolkit':'Firebird55/Game-immersion-toolkit'}[pkg.name]);
const provenance={version,sourceCommit:sha,repository,shared:pkg.name==='@firebird55/lexirise-components'?null:JSON.parse(readFileSync('vendor/lexirise-components/PROVENANCE.json','utf8'))};
mkdirSync('release',{recursive:true});writeFileSync('release/THIRD_PARTY_LICENSES.txt',dependencyNotices());writeFileSync('release/PROVENANCE.json',JSON.stringify(provenance,null,2)+'\n');
if(pkg.name==='@firebird55/lexirise-components'){
 writeFileSync('PROVENANCE.json',JSON.stringify(provenance,null,2)+'\n');
 execFileSync('npm',['pack','--ignore-scripts','--pack-destination','release'],{stdio:'inherit',shell:process.platform==='win32'});
 execFileSync('git',['archive','--format=zip','-o','release/lexirise-components-source-'+version+'.zip','HEAD']);
}else if(pkg.name==='emulingo-lexirise'){
 copyFileSync('dist/emulingo-lexirise.user.js','release/emulingo-lexirise-'+version+'.user.js');
 copyFileSync('src/userscript-header.txt','release/userscript-metadata.txt');copyFileSync('RELEASE.md','release/INSTALL.md');
}else{
 if(process.platform!=='win32')throw new Error('Toolkit distribution is packaged on Windows.');
 const folder='release/Game-immersion-toolkit-'+version;mkdirSync(folder,{recursive:true});
 execFileSync('git',['archive','--format=tar','-o','release/source.tar','HEAD']);
 execFileSync('tar',['-xf','release/source.tar','-C',folder]);
 copyFileSync('release/THIRD_PARTY_LICENSES.txt',folder+'/THIRD_PARTY_LICENSES.txt');
 copyBuiltFrontend('dist',folder+'/dist');copyFileSync('release/PROVENANCE.json',folder+'/PROVENANCE.json');
 execFileSync('powershell',['-NoProfile','-Command',"$ErrorActionPreference='Stop'; Compress-Archive -LiteralPath '"+folder+"' -DestinationPath 'release/Game-immersion-toolkit-"+version+".zip'"],{stdio:'inherit'});
 execFileSync(process.execPath,['-e',"require('fs').unlinkSync('release/source.tar')"]);
}
for(const file of ['INSTALL.md','INSTALL.html','AGENTS.md','CONTRIBUTING.md','LICENSE','NOTICE.md','THIRD_PARTY_NOTICES.md','SECURITY.md'])copyFileSync(file,'release/'+file);
const assets=readdirSync('release').filter(f=>statSync('release/'+f).isFile()&&f!=='SHA256SUMS');
writeFileSync('release/SHA256SUMS',assets.map(f=>createHash('sha256').update(readFileSync('release/'+f)).digest('hex')+'  '+f).join('\n')+'\n');
console.log('Release assets and SHA-256 checksums prepared for '+version+' @ '+sha);
