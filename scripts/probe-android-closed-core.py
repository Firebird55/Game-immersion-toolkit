"""Exercise the actual APK-owned Python namespace with desktop dependency wheels.

This proves owned-source delivery and reference behavior, not Android native ABI
execution. The hosted Android job must separately load the actual target wheels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


BOOTSTRAP = r'''
import json,sys,hashlib,socket
from pathlib import Path
def no_network(*args,**kwargs):
    raise RuntimeError('The authored packaged-source proof forbids network access')
socket.socket.connect=no_network
socket.create_connection=no_network
if sys.version_info[:2] != (3,12) or 'backend' in sys.modules:
    raise RuntimeError('Use an isolated Python 3.12 reference process')
origin=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(origin))
import backend.android_host
import backend.android_protected_storage
import backend.android_accounts
import backend.android_account_api
import backend.android_authored_accounts
from backend.game_data_providers import create_game_data_providers
reviewed_publishers=set(json.loads(sys.argv[3]))
registered=create_game_data_providers(platform='android',native=None)
if not reviewed_publishers <= set(registered) or (origin.suffix=='.imy' and set(registered)!=reviewed_publishers):
    raise RuntimeError('The packaged publisher factory closure differs from its reviewed policy')
from backend.android_probe import run
result=json.loads(run(sys.argv[2]))
audio=Path(result['private_audio_path'])
if not audio.is_file() or hashlib.sha256(audio.read_bytes()).hexdigest()!=result['results']['old_recording_sha256']:
    raise RuntimeError('The authored native media path is missing or differs from the retained original recording')
result.pop('private_audio_path',None)
owned={name:module.__file__ for name,module in sys.modules.items()
       if (name=='backend' or name.startswith('backend.')) and getattr(module,'__file__',None)}
prefix=origin.as_posix().rstrip('/')+'/'
if any(not Path(path).as_posix().startswith(prefix) for path in owned.values()):
    raise RuntimeError('A repository backend module masked missing packaged source')
forbidden={'mss','oneocr','PIL','cv2','rapidocr_onnxruntime','windows_capture','backend.capture'}
if forbidden.intersection(sys.modules):
    raise RuntimeError('The shared core imported a desktop platform/transport dependency')
result['owned_module_names']=sorted(owned)
result['publisher_source_stages']=sorted(reviewed_publishers)
print(json.dumps(result,sort_keys=True))
'''


def execute(origin, directory):
    result = subprocess.run([sys.executable, '-I', '-B', '-c', BOOTSTRAP, str(origin), str(directory),
        json.dumps(sorted(json.loads((Path(__file__).resolve().parents[1] / 'packaging/android/publisher-sources.json').read_text())['providers']))],
        capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Owned Python delivery probe failed:\n' + result.stderr[-4096:])
    return json.loads(result.stdout)


def probe(apk, work, *, reference=None):
    work = Path(work).absolute();work.mkdir(parents=True, exist_ok=True)
    packaged = work / 'app.imy'
    with zipfile.ZipFile(apk) as archive:
        entry = archive.getinfo('assets/chaquopy/app.imy')
        if entry.file_size > 32 * 1024**2:
            raise ValueError('The owned Python package exceeds its delivery bound')
        packaged.write_bytes(archive.read(entry))
        manifest = json.loads(archive.read('assets/core-source-manifest.json'))
    actual = execute(packaged, work / 'packaged-fixture')
    if reference:
        expected = json.loads(Path(reference).read_text(encoding='utf8'))
    else:
        repository = Path(__file__).resolve().parents[1]
        expected = execute(repository, work / 'desktop-fixture')
    if actual['results'] != expected['results'] or actual['result_sha256'] != expected['result_sha256']:
        raise ValueError('Packaged shared-core behavior differs from the maintained desktop reference')
    if set(actual['results']['prepared_games']) != {'zzz', 'genshin', 'starrail', 'endfield', 'wuwa', 'nte'}:
        raise ValueError('The six game fixtures did not execute inside the delivered package')
    return {'schema': 'toolkit-android-owned-package-proof-v1',
        'apk_sha256': hashlib.sha256(Path(apk).read_bytes()).hexdigest(),
        'owned_source_files': manifest['files'], 'owned_module_names': actual['owned_module_names'],
        'publisher_source_stages': actual['publisher_source_stages'],
        'result_sha256': actual['result_sha256'], 'prepared_games': actual['results']['prepared_games'],
        'dependency_overlay': 'desktop-reference-wheels', 'owned_package_reference_behavior': 'passed',
        'network': 'blocked-before-owned-module-import',
        'android_native_runtime_acceptance': 'not-established-by-desktop-overlay', 'release_eligibility': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(probe(args.apk, args.work_dir, reference=args.reference),
        sort_keys=True, indent=2) + '\n', encoding='utf8')
