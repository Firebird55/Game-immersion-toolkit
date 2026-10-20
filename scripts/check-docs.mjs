import {execFileSync} from 'node:child_process';
import {existsSync,readFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
const files=execFileSync('git',['ls-files','*.md'],{encoding:'utf8'}).trim().split('\n');
const failures=[];
for(const file of files) {
  if(!existsSync(file)||file.startsWith('vendor/'))continue;
  for(const match of readFileSync(file,'utf8').matchAll(/\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const link=match[1];
    if(/^(?:[a-z]+:|#|\/)/i.test(link))continue;
    const path=decodeURIComponent(link.split('#')[0].split('?')[0]);
    if(path&&!existsSync(resolve(dirname(file),path))) failures.push(`${file}: ${link}`);
  }
}
if(failures.length)throw Error('Broken local documentation links:\n'+failures.join('\n'));
console.log('Documentation links checked.');
