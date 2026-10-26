// A GitHub-created version tag may precede an npm metadata bump. Prepare that
// metadata in the build checkout; preserve the immutable tagged source commit.
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
export function releaseMetadata(tag, pkg, lock) {
  if (!/^v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(tag)) throw Error('Use a version tag such as v0.20.0.');
  const version = tag.slice(1);
  return {pkg: {...pkg, version}, lock: {...lock, version,
    ...(lock.packages ? {packages: {...lock.packages, '': {...lock.packages[''], version}}} : {})}};
}
if (process.argv[1] === fileURLToPath(import.meta.url) && process.env.GITHUB_REF?.startsWith('refs/tags/')) {
  const tag = process.env.GITHUB_REF.slice('refs/tags/'.length);
  const {pkg, lock} = releaseMetadata(tag, JSON.parse(readFileSync('package.json','utf8')), JSON.parse(readFileSync('package-lock.json','utf8')));
  writeFileSync('package.json', JSON.stringify(pkg,null,2)+'\n');
  writeFileSync('package-lock.json', JSON.stringify(lock,null,2)+'\n');
  writeFileSync('VERSION', pkg.version+'\n');
  writeFileSync('release-version.json', JSON.stringify({version:pkg.version,releaseCommand:'npm run release -- --version '+pkg.version},null,2)+'\n');
  console.log('Prepared distribution version '+pkg.version+' from the immutable release tag.');
}
