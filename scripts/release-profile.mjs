import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

export const WINDOWS_ANDROID = 'windows-android';
const ALL_DESKTOPS = 'all-desktops';
const desktopTargets = [
  {runner: 'windows-2025', target: 'windows-x64', node_target: 'win-x64', dotnet_rid: 'win-x64'},
  {runner: 'ubuntu-24.04', target: 'linux-x64', node_target: 'linux-x64', dotnet_rid: 'linux-x64'},
  {runner: 'macos-15', target: 'macos-arm64', node_target: 'darwin-arm64', dotnet_rid: 'osx-arm64'},
];

export function releaseRecord(version, profile = ALL_DESKTOPS) {
  if (profile !== ALL_DESKTOPS && profile !== WINDOWS_ANDROID) {
    throw new Error('Choose release profile all-desktops or windows-android.');
  }
  const releaseCommand = 'npm run release -- --version ' + version;
  if (profile === ALL_DESKTOPS) return {version, releaseCommand};
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Windows and Android require a stable numeric version.');
  return {version, releaseCommand: releaseCommand + ' --profile ' + profile, profile};
}

export function profileForTag(ref, record) {
  if (typeof record.version !== 'string' || ref !== 'refs/tags/v' + record.version) return ALL_DESKTOPS;
  return releaseRecord(record.version, record.profile).profile ?? ALL_DESKTOPS;
}

export function desktopMatrix(profile) {
  return {include: profile === WINDOWS_ANDROID ? desktopTargets.slice(0, 1) : desktopTargets};
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const record = JSON.parse(readFileSync('release-version.json', 'utf8'));
  const profile = profileForTag(process.env.GITHUB_REF, record);
  // Both values consist exclusively of approved constants.
  console.log(`profile=${profile}\ndesktop_matrix=${JSON.stringify(desktopMatrix(profile))}`);
}
