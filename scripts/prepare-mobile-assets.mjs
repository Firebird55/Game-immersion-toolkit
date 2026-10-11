import {mkdirSync,writeFileSync} from 'node:fs';
import {dirname} from 'node:path';
import {ocrAssets} from './mobile-assets.mjs';
// Generated, licensed runtime assets for the desktop-served mobile page.
// Source control excludes this directory; Pages builds from the same allowlist.
for(const [name,bytes] of ocrAssets()){const target='public/mobile-capture/'+name;mkdirSync(dirname(target),{recursive:true});writeFileSync(target,bytes);}
