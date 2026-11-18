import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync, statSync, utimesSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {desktopMatrix, profileForTag, releaseRecord, WINDOWS_ANDROID} from '../scripts/release-profile.mjs';

const script = fileURLToPath(new URL('../scripts/prepare-release-version.mjs', import.meta.url));
function metadata(version) {
  const pkg = {name:'authored-release-fixture',version,dependencies:{example:'1.0.0'}};
  return {
    'package.json': JSON.stringify(pkg,null,2)+'\n',
    'package-lock.json': JSON.stringify({name:pkg.name,version,lockfileVersion:3,
      packages:{'':pkg,'node_modules/example':{version:'1.0.0',integrity:'authored'}}},null,2)+'\n',
    VERSION: version+'\n',
    'release-version.json': JSON.stringify({version,releaseCommand:'npm run release -- --version '+version},null,2)+'\n',
  };
}
function run(cwd, tag) {
  execFileSync(process.execPath,[script],{cwd,env:{...process.env,GITHUB_REF:'refs/tags/'+tag},stdio:'pipe'});
}

for (const eol of ['\n','\r\n']) test(`same-version ${JSON.stringify(eol)} checkout is not written`, () => {
  const cwd = mkdtempSync(join(tmpdir(),'release-version-preserve-'));
  try {
    const before = new Map();
    for (const [name, content] of Object.entries(metadata('0.23.0'))) {
      const path = join(cwd,name);
      writeFileSync(path,content.replace(/\n/g,eol));
      utimesSync(path,new Date('2001-01-01T00:00:00Z'),new Date('2001-01-01T00:00:00Z'));
      before.set(name,{bytes:readFileSync(path),stat:statSync(path,{bigint:true})});
    }
    run(cwd,'v0.23.0');
    for (const [name, original] of before) {
      const path = join(cwd,name), after = statSync(path,{bigint:true});
      assert.deepEqual(readFileSync(path),original.bytes,name);
      assert.equal(after.ino,original.stat.ino,name);
      assert.equal(after.mtimeNs,original.stat.mtimeNs,name);
    }
  } finally {rmSync(cwd,{recursive:true,force:true});}
});

test('a genuinely newer tag changes every version field without changing dependencies', () => {
  const cwd = mkdtempSync(join(tmpdir(),'release-version-change-'));
  try {
    for (const [name, content] of Object.entries(metadata('0.23.0')))
      writeFileSync(join(cwd,name),content.replace(/\n/g,'\r\n'));
    run(cwd,'v0.23.1');
    for (const [name, expected] of Object.entries(metadata('0.23.1')))
      assert.equal(readFileSync(join(cwd,name),'utf8'),expected,name);
  } finally {rmSync(cwd,{recursive:true,force:true});}
});

test('the Windows and Android profile is exact-tag only and survives checkout preparation', () => {
  const version = '0.24.0';
  const selection = releaseRecord(version, WINDOWS_ANDROID);
  const cwd = mkdtempSync(join(tmpdir(), 'release-version-platforms-'));
  try {
    for (const [name, content] of Object.entries(metadata(version))) writeFileSync(join(cwd, name), content);
    const record = join(cwd, 'release-version.json');
    writeFileSync(record, JSON.stringify(selection));
    run(cwd, 'v' + version);
    assert.deepEqual(JSON.parse(readFileSync(record, 'utf8')), selection);
    assert.equal(profileForTag('refs/tags/v' + version, selection), WINDOWS_ANDROID);
    assert.deepEqual(desktopMatrix(WINDOWS_ANDROID).include.map(({target}) => target), ['windows-x64']);
    for (const ref of ['refs/tags/v0.24.1', 'refs/heads/main']) {
      assert.deepEqual(desktopMatrix(profileForTag(ref, selection)).include.map(({target}) => target),
        ['windows-x64', 'linux-x64', 'macos-arm64']);
    }
    assert.throws(() => releaseRecord(version, 'windows'), /release profile/);
    assert.throws(() => releaseRecord(version + '-test', WINDOWS_ANDROID), /stable numeric version/);
    run(cwd, 'v0.24.1');
    assert.deepEqual(JSON.parse(readFileSync(record, 'utf8')), releaseRecord('0.24.1'));
  } finally {
    rmSync(cwd, {recursive: true, force: true});
  }
});
