import {cpSync} from 'node:fs';
import {relative} from 'node:path';
import {privatePath} from './publication-scan.mjs';
/** Copy build output only: local browser tests and serving create runtime state here. */
export function copyBuiltFrontend(source,destination){
 cpSync(source,destination,{recursive:true,filter:path=>{
  const name=relative(source,path).replaceAll('\\','/');
  return !privatePath(name)&&!/(?:^|\/)(?:\.wrangler|\.cache)(?:\/|$)/.test(name)&&!name.endsWith('.log');
 }});
}
