// Read only the exact imported acceptance fixture. No arbitrary app paths,
// credentials, dialogue rows or audio bytes enter the diagnostic artifact.
import {execFileSync} from 'node:child_process';
import {statSync} from 'node:fs';

const fixture = String.raw`
import hashlib,json,re,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
 entries=archive.infolist()
 assert len(entries)==3 and all(item.compress_type==zipfile.ZIP_STORED and 0<item.file_size<=4*1024**2 for item in entries)
 names={item.filename for item in entries}
 assert len(names)==3 and {'manifest.json','textmap.json'}<names
 audio=next(name for name in names if name not in {'manifest.json','textmap.json'})
 assert re.fullmatch(r'audio/[0-9a-f]{64}\.wav',audio)
 manifest_raw=archive.read('manifest.json');manifest=json.loads(manifest_raw)
 text=archive.read('textmap.json');payload=json.loads(text);clip=archive.read(audio)
 digest=lambda value:hashlib.sha256(value).hexdigest()
 assert audio=='audio/'+digest(clip)+'.wav'
 assert manifest['format']=='toolkit-prepared-library-v1' and manifest['game']=='zzz'
 assert manifest['files']=={'textmap.json':{'sha256':digest(text),'size':len(text)},audio:{'sha256':digest(clip),'size':len(clip)}}
 assert payload['game']=='zzz' and payload['source_locale']=='en' and len(payload['records'])==1
 row=payload['records'][0]
 assert row['text_id']=='authored:bridge' and row['source_text']=='Follow the river beyond the bridge.'
 assert row['voice_status']=='voiced' and row['audio_locale']=='en' and row['audio']=={'prepared_clip':audio,'locale':'en'}
 print(json.dumps({'revision':digest(manifest_raw),'text_sha256':digest(text),'text_size':len(text),
  'audio_member':audio,'audio_sha256':digest(clip),'audio_size':len(clip)}))
`;

export function authoredLibraryIdentity(path) {
 if (!statSync(path).isFile() || statSync(path).size > 4 * 1024 ** 2) throw Error('Authored fixture exceeds its bound');
 const python = process.env.PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3');
 return JSON.parse(execFileSync(python, ['-I', '-B', '-c', fixture, path],
  {encoding: 'utf8', timeout: 10_000, stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 4096}));
}

export function inspectAuthoredLibrary(adb, packageName, expected) {
 if (!['io.github.firebird55.gameimmersiontoolkit.debug', 'io.github.firebird55.gameimmersiontoolkit'].includes(packageName)
     || ![expected?.revision, expected?.text_sha256, expected?.audio_sha256].every(value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value))
     || ![expected?.text_size, expected?.audio_size].every(value => Number.isSafeInteger(value) && value > 0 && value <= 4 * 1024 ** 2)
     || expected?.audio_member !== 'audio/' + expected.audio_sha256 + '.wav')
  throw Error('Only an exact authored app fixture can be inspected');
 const result = {expected_fixture_valid: true, inspected: true, current_manifest_matches: false};
 try {
  const pointer = JSON.parse(adb('shell', 'run-as', packageName, 'head', '-c', '512', 'files/toolkit/libraries/current.json'));
  result.current_manifest_matches = pointer.revision === expected.revision && pointer.text_sha256 === expected.text_sha256;
  if (!result.current_manifest_matches) return result; // Never follow another library's pointer.
  const root = 'files/toolkit/libraries/' + expected.revision + '/';
  for (const [kind, member, digest, size] of [['text', 'textmap.json', expected.text_sha256, expected.text_size],
    ['audio', expected.audio_member, expected.audio_sha256, expected.audio_size]]) {
   try {
    const actualSize = adb('shell', 'run-as', packageName, 'stat', '-c', '%s', root + member);
    result[kind + '_present'] = /^\d+$/.test(actualSize) && Number.isSafeInteger(Number(actualSize));
    result[kind + '_bytes'] = result[kind + '_present'] ? Number(actualSize) : null;
    result[kind + '_size_matches'] = result[kind + '_present'] && Number(actualSize) === size;
    if (!result[kind + '_size_matches']) {result[kind + '_sha256_matches'] = false;continue;}
    const actualHash = adb('shell', 'run-as', packageName, 'sha256sum', root + member).split(/\s+/)[0];
    result[kind + '_sha256_matches'] = /^[a-f0-9]{64}$/.test(actualHash) && actualHash === digest;
   } catch {result[kind + '_present'] = false;result[kind + '_check_failed'] = true;}
  }
 } catch {result.current_manifest_unavailable = true;}
 return result;
}
