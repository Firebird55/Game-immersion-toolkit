import {mkdirSync,writeFileSync,existsSync,readFileSync} from 'node:fs';
import {dirname} from 'node:path';
import {ocrAssets} from './mobile-assets.mjs';
// Generated, licensed runtime assets for the desktop-served mobile page.
// Source control excludes this directory; Pages builds from the same allowlist.
for(const [name,bytes] of ocrAssets()){const target='public/mobile-capture/'+name;if(existsSync(target)&&readFileSync(target).equals(bytes))continue;mkdirSync(dirname(target),{recursive:true});writeFileSync(target,bytes);}

const {buildBrowserReader}=await import('./build-browser-reader.mjs');await buildBrowserReader();
