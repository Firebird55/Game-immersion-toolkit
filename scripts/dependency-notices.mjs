import {readFileSync,readdirSync,existsSync,lstatSync} from 'node:fs';
import {resolve,join,relative,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {nativeBuildPolicy, readBrowserNativeExclusions, POLICY, GUARD} from './frontend-native-exclusions.mjs';

const sha256=bytes=>createHash('sha256').update(bytes).digest('hex');
const noticeName=name=>/^(?:licen[cs]e|notice|copying|copyright)(?:[._-].*)?$/i.test(name)
  || /^(?:third[_-]?party[_-]?(?:licenses?|notices?))(?:[._-].*)?$/i.test(name);

function checked(root,name){
 if(typeof name!=='string'||!name||name.includes('\\')||name.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('Unsafe dependency notice path');
 const file=resolve(root,name);
 if(!file.startsWith(resolve(root)+sep))throw Error('Unsafe dependency notice path');
 for(let p=file;p!==resolve(root);p=resolve(p,'..'))if(existsSync(p)&&lstatSync(p).isSymbolicLink())throw Error('Dependency notices cannot traverse links');
 return file;
}

export function packageNoticeFiles(directory){
 const found=[];let count=0;
 function walk(folder,underLicenses=false){
  for(const entry of readdirSync(folder,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name,'en'))){
   if(++count>100000)throw Error('Dependency notice inventory exceeds its limit');
   if(entry.name==='node_modules'||entry.name==='.git')continue;
   if(entry.isSymbolicLink())throw Error('Dependency notices cannot traverse links');
   const path=join(folder,entry.name);
   if(entry.isDirectory())walk(path,underLicenses||/^licen[cs]es$/i.test(entry.name));
   else if(entry.isFile()&&(underLicenses||noticeName(entry.name))){
    if(lstatSync(path).size>4*1024*1024)throw Error('Dependency notice exceeds its size limit');
    found.push(path);
   }
  }
 }
 walk(directory);return found;
}

function permits(values,value){
 if(!Array.isArray(values)||!values.length)return true;
 return !values.includes('!'+value)&&(!values.some(v=>!v.startsWith('!'))||values.includes(value)||values.includes('any'));
}

function absentExclusions(root,packages,platform,arch){
 const excluded=new Map(),incoming=new Map();
 const resolveDependency=(parent,name)=>{
  let directory=parent;
  for(;;){
   const candidate=(directory?directory+'/':'')+'node_modules/'+name;
   if(Object.hasOwn(packages,candidate))return candidate;
   if(!directory)return null;
   const index=directory.lastIndexOf('/node_modules/');
   directory=index<0?'':directory.slice(0,index);
  }
 };
 for(const [path,entry] of Object.entries(packages)){
  if(path.startsWith('node_modules/')&&!existsSync(checked(root,path))){
   if(entry.dev)excluded.set(path,{reason:'development-only absent'});
   else if(entry.optional&&(!permits(entry.os,platform)||!permits(entry.cpu,arch)||!permits(entry.libc,'glibc')))
    excluded.set(path,{reason:'optional incompatible platform'});
  }
  for(const name of new Set(['dependencies','optionalDependencies','devDependencies','peerDependencies']
    .flatMap(field=>Object.keys(entry[field]??{})))){
   const target=resolveDependency(path,name);
   if(target){if(!incoming.has(target))incoming.set(target,new Set());incoming.get(target).add(path);}
  }
 }
 // Recent npm versions prune descendants of incompatible optional packages.
 // A child need not repeat its parent's os/cpu restriction. Exclude it only
 // when every resolved incoming edge is already excluded, never just because
 // its own metadata says "optional" or because installation omitted it.
 for(let changed=true;changed;){
  changed=false;
  for(const [path,entry] of Object.entries(packages)){
   if(!path.startsWith('node_modules/')||!entry.optional||excluded.has(path)||existsSync(checked(root,path)))continue;
   const parents=[...(incoming.get(path)??[])];
   if(parents.length&&parents.every(parent=>excluded.has(parent))){
    excluded.set(path,{reason:'optional dependency of excluded packages',parents:parents.sort()});changed=true;
   }
  }
 }
 return excluded;
}

export function dependencyNoticeAudit({root=process.cwd(),platform=process.platform,arch=process.arch,frontendRoot}={}){
 root=resolve(root);
 const lock=JSON.parse(readFileSync(join(root,'package-lock.json'),'utf8'));
 const supplementPath=join(root,'packaging/frontend-notices/sources.json');
 const supplements=existsSync(supplementPath)?JSON.parse(readFileSync(supplementPath,'utf8')):{sources:[],packages:[]};
 if(supplements.schema&&supplements.schema!=='toolkit-frontend-notice-supplements-v1')throw Error('Unknown frontend notice supplements');
 const sourceMap=new Map(),inputs=new Set(existsSync(supplementPath)?[supplementPath]:[]),records=[],omissions=[],excluded=[];
 const nativePolicy=nativeBuildPolicy(root);
 const nativeExclusions=frontendRoot?readBrowserNativeExclusions(root,frontendRoot):null;
 if(nativePolicy){inputs.add(join(root,POLICY));inputs.add(join(root,GUARD));}
 const absent=absentExclusions(root,lock.packages??{},platform,arch);
 for(const source of supplements.sources){
  const path=checked(root,'packaging/frontend-notices/'+source.path),bytes=readFileSync(path);
  if(sha256(bytes)!==source.sha256||bytes.length!==source.bytes)throw Error('Pinned frontend notice changed: '+source.path);
  if(sourceMap.has(source.path))throw Error('Duplicate frontend notice source');
  sourceMap.set(source.path,{...source,path,bytes});inputs.add(path);
 }
 for(const [packagePath,entry] of Object.entries(lock.packages??{}).sort(([a],[b])=>a.localeCompare(b,'en'))){
  if(!packagePath.startsWith('node_modules/'))continue;
  const directory=checked(root,packagePath),name=packagePath.split('node_modules/').at(-1);
  if(!existsSync(directory)){
   if(absent.has(packagePath)){
    excluded.push({package:packagePath,version:entry.version,...absent.get(packagePath)});continue;
   }
   omissions.push({package:packagePath,version:entry.version,reason:'Production dependency is absent from the locked installation'});continue;
  }
  const metadataPath=checked(root,packagePath+'/package.json');
  const metadata=JSON.parse(readFileSync(metadataPath,'utf8'));
  if(metadata.version!==entry.version)throw Error('Dependency notice version differs from lock: '+packagePath);
  inputs.add(metadataPath);
  const files=packageNoticeFiles(directory);
  let primary=files.some(file=>relative(directory,file).split(sep).length===1&&noticeName(file.split(sep).at(-1)));
  for(const path of files){
   const bytes=readFileSync(path);inputs.add(path);
   records.push({package:packagePath,version:entry.version,file:relative(directory,path).split(sep).join('/'),sha256:sha256(bytes),text:bytes.toString('utf8')});
  }
  const supplement=supplements.packages.find(p=>p.name===name&&p.version===entry.version&&p.integrity===entry.integrity);
  if(supplement){
   if(supplement.resolution==='declared-license-by-reference'){
    for(const [key,value] of Object.entries(supplement.declaration))if(JSON.stringify(metadata[key])!==JSON.stringify(value))throw Error('Pinned license declaration differs: '+packagePath);
   }
   for(const name of supplement.files){
    const source=sourceMap.get(name);if(!source)throw Error('Missing frontend notice supplement');
    records.push({package:packagePath,version:entry.version,file:'upstream/'+name,sha256:source.sha256,
     source:source.url,resolution:supplement.resolution,
     declaration:supplement.declaration,copyright_notice:supplement.copyright_notice,
     note:supplement.note,scope:supplement.scope,text:source.bytes.toString('utf8')});
   }
   primary=true;
  }
  if(!primary&&!entry.dev){
   const candidate=nativePolicy?.packages.some(item=>item.package===packagePath);
   if(candidate&&nativeExclusions)excluded.push({package:packagePath,version:entry.version,reason:'Native build input absent from every shipped browser build',coverage:nativeExclusions.coverage});
   else omissions.push({package:packagePath,version:entry.version,reason:'No full primary license notice or exact supplier supplement',...(candidate?{pending_native_build_evidence:true}:{})});
  }
 }
 return {schema:'toolkit-frontend-notice-audit-v1',lock_sha256:sha256(readFileSync(join(root,'package-lock.json'))),
  records,omissions,excluded,inputs:[...inputs].sort()};
}

export function requireCompleteNotices(audit,{deferNativeBuildEvidence=false}={}){
 const omissions=audit.omissions.filter(item=>!deferNativeBuildEvidence||!item.pending_native_build_evidence);
 if(!omissions.length)return;
 const safe=value=>String(value??'unknown').replace(/[^\x20-\x7e]/g,'?').slice(0,180);
 const details=omissions.slice(0,12).map(item=>safe(item.package)+' ('+safe(item.reason)+')');
 const remaining=omissions.length-details.length;
 throw Error('Production dependency notices incomplete: '+details.join(', ')+(remaining?' ; '+remaining+' additional omissions':''));
}

export function dependencyNotices(options){
 const root=resolve(options?.root??process.cwd()),audit=dependencyNoticeAudit(options),blocks=[];
 requireCompleteNotices(audit);
 for(const entry of audit.records){
  let heading=entry.package+' @ '+entry.version+' — '+entry.file;
  if(entry.source)heading+='\nSource: '+entry.source+'\nSHA-256: '+entry.sha256;
  if(entry.resolution)heading+='\nResolution: '+entry.resolution;
  if(entry.declaration)heading+='\nExact package declaration: '+JSON.stringify(entry.declaration);
  for(const name of ['copyright_notice','note','scope'])if(entry[name])heading+='\n'+entry[name];
  blocks.push(heading+'\n'+entry.text);
 }
 if(!blocks.length)throw Error('Dependency license notices missing');
 blocks.push('Geist and Geist Mono — styles/GEIST-OFL.txt\n'+readFileSync(join(root,'styles/GEIST-OFL.txt'),'utf8'));
 if(existsSync(join(root,'public/mobile-capture/pairing/LICENSE-QRCODE.txt')))blocks.push('qrcode-generator 2.0.4 — MIT\n'+readFileSync(join(root,'public/mobile-capture/pairing/LICENSE-QRCODE.txt'),'utf8'));
 return 'Third-party dependency notices from the locked installation. These licenses remain independent of the project license.\n\n'+blocks.join('\n\n--------------------\n\n')+'\n';
}
