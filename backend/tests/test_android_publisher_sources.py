"""Closed owned source delivery, not execution of Android native extensions."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'packaging/android/publisher-sources.json'


def portable_sources():
    script = (ROOT / 'packaging/android/app/build.gradle').read_text(encoding='utf8')
    names = re.findall(r"'([a-z0-9_]+\.py)'", script[:script.index('publisherPolicy.files.each')])
    return {'backend/' + name for name in names} | set(json.loads(POLICY.read_text())['files'])


def test_policy_pins_only_reviewed_pure_factories_and_all_actual_source_bytes():
    policy = json.loads(POLICY.read_text())
    assert policy['schema'] == 'toolkit-android-publisher-sources-v1'
    assert policy['source_normalization'] == 'utf8-lf'
    assert set(policy['providers']) == {'nte', 'reverse1999', 'wuwa', 'zzz'}
    assert len(policy['files']) == 48 and len(portable_sources()) == 106
    assert 'backend/android_authored_game_data.py' in portable_sources()
    assert 'backend/text_display.py' in portable_sources()
    assert 'backend/android_publisher_hash.py' in portable_sources()
    assert not {'backend/endfield_vfs.py', 'backend/endfield_xxhash.py', 'backend/endfield_game_data.py', 'backend/genshin_game_data.py'} & portable_sources()
    assert {key.removeprefix('backend/').removesuffix('.py') for key in policy['files']} == {
        module for provider in policy['providers'].values() for module in provider['modules']} | set(policy['context_modules'])
    assert all(not provider['snapshot_runtime'] for provider in policy['providers'].values())
    for name in ('nte', 'wuwa'):
        assert policy['providers'][name]['dependencies'] == ['python-stdlib','toolkit-publisher-crypto-v1']
    assert policy['providers']['reverse1999']['dependencies'] == ['python-stdlib']
    assert policy['providers']['zzz']['dependencies'] == [
        'python-stdlib', 'zstandard==0.25.0', 'toolkit-publisher-crypto-v1', 'toolkit-android-zzz-catalogue-v1']
    assert policy['providers']['nte']['stages'] == ['compatibility', 'manifest-verification']
    for name, receipt in policy['files'].items():
        assert re.fullmatch(r'backend/[a-z0-9_]+\.py', name)
        assert hashlib.sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == receipt['sha256_lf']
        assert re.fullmatch('[0-9a-f]{40}', receipt['source_commit'])


def test_apk_publisher_boundary_rejects_missing_module_and_changed_policy(tmp_path):
    spec = importlib.util.spec_from_file_location('publisher_apk_audit', ROOT / 'scripts/verify-android-apk.py')
    audit = importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    raw = POLICY.read_bytes();core = {'files':dict.fromkeys(portable_sources(), 'authored-core-receipt')}
    def archive(value):
        output = io.BytesIO()
        with ZipFile(output, 'w') as result: result.writestr('assets/publisher-source-policy.json', value)
        return ZipFile(io.BytesIO(output.getvalue()))
    with archive(raw) as source: audit.verify_publisher_sources(source, core, ROOT)
    missing = {'files':dict(core['files'])};missing['files'].pop('backend/nte_updater_native.py')
    with archive(raw) as source, pytest.raises(ValueError): audit.verify_publisher_sources(source, missing, ROOT)
    changed = json.loads(raw);changed['providers']['nte']['snapshot_runtime'] = True
    with archive(json.dumps(changed)) as source, pytest.raises(ValueError): audit.verify_publisher_sources(source, core, ROOT)


BOOTSTRAP = r'''
import sys,json,socket,time,io,importlib.abc
from pathlib import Path
from email.message import Message
from zipfile import ZipFile
owned=Path(sys.argv[1]);data=json.loads(Path(sys.argv[2]).read_text())
sys.path.insert(0,str(owned))
policy=json.loads(Path(sys.argv[3]).read_text())
def deny(*a,**k):raise AssertionError('An unaccounted network or desktop execution path was used')
socket.socket.connect=deny;socket.create_connection=deny
import subprocess
subprocess.Popen=deny
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if any(name==value or name.startswith(value+'.') for value in policy['forbidden_stage_imports']):deny()
sys.meta_path.insert(0,Block())
from backend.game_data_providers import create_game_data_providers
from backend.game_data import GameDataService
from backend.publisher_transport import PublisherTransport
from backend import nte_updater_source as source,nte_updater_baseline as baseline
from backend import android_zzz_catalogue, zzz_pc_sources, zzz_pc_stages
class UnusedNative:
 def __getattribute__(self,name):raise AssertionError('A pure stage queried a native service')
providers=create_game_data_providers(platform='android',native=UnusedNative())
assert set(providers)=={'nte','reverse1999','wuwa','zzz'}
assert all(name not in sys.modules for name in policy['forbidden_stage_imports'])
# A mismatched late-stage call must fail at the Android gate before a desktop
# source module import, including when these modules do not exist in the APK.
from types import SimpleNamespace
from backend.game_data_protocol import GameDataError
from backend.game_data_protocol import GameDataRequest
try:providers['wuwa'].plan(GameDataRequest('global','ja',('en',),'text'),SimpleNamespace(check=lambda:None,stage_handle=None))
except GameDataError as error:assert error.code=='game_runtime_unavailable'
else:raise AssertionError('Wuwa admitted a missing maintained native crypto capability')
for stage in ('original-indices','archive-index-ranges','authoring-import-ranges',
 'process-authoring','initial-descriptions','dialogue-package-ranges',
 'process-metadata','global-import-metadata','authored-subtitle-ranges','normalize-text',
 'audio-member-ranges','process-audio-bindings','materialize-audio','finalize-audio'):
 try:providers['nte'].download(SimpleNamespace(stage=stage),SimpleNamespace(check=lambda:None))
 except GameDataError as error:assert error.code=='nte_reader_unavailable'
 else:raise AssertionError('Android admitted a desktop-only continuation')
assert all(name not in sys.modules for name in policy['forbidden_stage_imports'])
try:providers['nte'].restore({'schema':'nte-original-text-snapshot-v1'},SimpleNamespace(check=lambda:None))
except GameDataError as error:assert error.code=='nte_text_source_invalid'
else:raise AssertionError('Android trusted an incomplete self-contained text receipt')
try:providers['nte'].restore({'schema':'nte-original-audio-snapshot-v1'},SimpleNamespace(check=lambda:None))
except GameDataError as error:assert error.code=='nte_audio_runtime_unavailable'
else:raise AssertionError('Android admitted a desktop-only original-audio runtime')
assert all(name not in sys.modules for name in policy['forbidden_stage_imports'])
class Response(io.BytesIO):
 status=200
 def __init__(self,body,url):
  super().__init__(body);self.url=url;self.headers=Message();self.headers['Content-Length']=str(len(body))
 def geturl(self):return self.url
import base64
bodies={url:base64.b64decode(value) for url,value in data['bodies'].items()}
calls=[]
def open_(request,**kwargs):
 assert request.full_url in bodies
 calls.append(request.full_url)
 assert request.headers['Accept-encoding']=='identity'
 return Response(bodies[request.full_url],request.full_url)
providers['nte'].opener=open_
providers['zzz'].native=None
providers['zzz'].transport_factory=lambda ctx,**kwargs:PublisherTransport(ctx,opener=open_,**kwargs)
inputs=source._inputs(data['inputs'])
artifact_urls={artifact.url for artifact in inputs.artifacts}
baseline.inputs=lambda:inputs
baseline.MEMBER_SHA256=data['members']
request={'region':'global','source_locale':'ja','target_locales':['en'],'content_mode':'text'}
activated=[]
service=GameDataService(owned.parent/'managed',providers,on_activate=lambda *a:activated.append(True))
try:
 plan=service.plan('nte',request)['game']
 assert len(calls)==2 and not any(url.endswith('.zip') for url in calls)
 assert plan['can_download'] and plan['download_bytes']>0
 assert plan['state']!='ready' and plan['installed_revision'] is None
 service.download('nte',{'plan_id':plan['plan_id'],'revision':plan['revision']})
 end=time.monotonic()+5
 while time.monotonic()<end:
  row=next(value for value in service.snapshot()['games'] if value['id']=='nte')
  if row['job'] and row['job']['status'] not in {'queued','running'}:break
  time.sleep(.01)
 assert row['job']['status']=='needs_plan' and row['state']!='ready' and not activated
 assert row['installed_revision'] is None and not row['can_activate']
 assert row['job']['downloaded_bytes']==plan['download_bytes']
 assert not (owned.parent/'managed/nte/current.json').exists()
 assert (owned.parent/'managed/nte/stage.json').is_file()
 warm=service.plan('nte',request)['game']
 assert warm['download_bytes'] is None and not warm['can_download'] and warm['state']!='ready'
 assert 'publisher cryptography' in warm['message']
 assert sum(url in artifact_urls for url in calls)==2
 assert not any(url in calls for url in data['release_urls'])

 # The closed package uses the actual publisher-crypto adapter and provider
 # with a host simulation of a single JCA operation. All desktop imports and
 # original transfers remain denied. Target JNI evidence comes separately.
 operations=[]
 class AuthoredJava:
  def proof(self):return json.dumps(data['crypto_proof'])
  def blockCipher(self,algorithm,mode,key,iv,body,decrypt):
   assert (algorithm,mode,decrypt)==('AES','CBC',True)
   assert body==base64.b64decode(data['ciphertext'])
   assert (key,iv)==(b'authored-demofix',b'fixture-iv000000')
   operations.append(True)
   return base64.b64decode(data['plaintext'])
 sys.modules['java']=SimpleNamespace(jclass=lambda name:AuthoredJava)
 providers['nte'].native=SimpleNamespace(publisherCrypto=AuthoredJava)
 transfer_start=len(calls)
 for mode in ('text','text-audio'):
  verified=service.plan('nte',{**request,'content_mode':mode})['game']
  assert not verified['can_download'] and verified['download_bytes'] is None and verified['required_disk_bytes'] is None
  assert verified['revision']!=warm['revision']
  assert 'inventory is verified' in verified['message'] and not verified['can_activate']
  assert len(verified['revision'])==len('nte-content-')+64
 assert operations==[True,True]
 assert calls[transfer_start:]==([source.VERSION_URL,inputs.manifest_url,*data['release_urls'],
    source.VERSION_URL,inputs.manifest_url,source.VERSION_URL,inputs.manifest_url]*2)
 assert not activated and not (owned.parent/'managed/nte/current.json').exists()
 assert not (owned.parent/'managed/nte/cache/tools/nte-publisher/format/original-updater/approvals').exists()

 # The production ZZZ registry reaches the consented source stage with only
 # its APK-owned imports and stops at the unavailable catalogue reader.
 for region in ('global','cn'):
  selection={**request,'region':region}
  bootstrap=service.plan('zzz',selection)['game']
  assert bootstrap['can_download'] and bootstrap['download_bytes']>0
  service.download('zzz',{'plan_id':bootstrap['plan_id'],'revision':bootstrap['revision']})
  end=time.monotonic()+5
  while time.monotonic()<end:
   row=next(value for value in service.snapshot()['games'] if value['id']=='zzz')
   if row['job'] and row['job']['status'] not in {'queued','running'}:break
   time.sleep(.01)
  assert row['job']['status']=='needs_plan' and not row['can_activate']
  assert row['job']['downloaded_bytes']==bootstrap['download_bytes']
  following=service.plan('zzz',selection)['game']
  assert following['download_bytes'] is None and not following['can_download']
  assert 'Dialogue preparation' in following['message']
 assert not activated and not (owned.parent/'managed/zzz/current.json').exists()
 assert all(name not in sys.modules for name in policy['forbidden_stage_imports'])
 for name,module in list(sys.modules.items()):
  if name=='backend' or name.startswith('backend.'):
   assert Path(module.__file__).is_relative_to(owned),name
 print(json.dumps({'schema':'android-publisher-closed-source-host-v1','registry':sorted(providers),
  'owned_modules':len(list((owned/'backend').glob('*.py'))),'no_external_network':True,'no_desktop_helper':True,
  'actual_context_transport':True,'stage_never_ready':True,'unknown_content_size_preserved':True,
  'asset_requests':sum(url in artifact_urls for url in calls),
  'manifest_verified':len(operations),'native_android_execution':False}))
finally:service.close()
'''


def test_exact_closed_namespace_authenticates_original_sources_without_desktop_or_network_fallback(tmp_path):
    # These are authored PE/configuration fixtures from the game owner's tests,
    # never original game software or an alternative preparation implementation.
    from Crypto.Cipher import AES
    from backend.publisher_crypto import MAX_BYTES, SOURCE_SHA256
    from backend.tests.fixtures.nte_updater_inputs import Originals, release_responses
    from backend.tests.test_zzz_game_data import publisher
    from backend.nte_updater_source import plan
    original = Originals();inputs = plan(fetch=original.fetch)
    members = {}
    for artifact in inputs.artifacts:
        with ZipFile(io.BytesIO(original.bodies[artifact.url])) as archive:
            members[artifact.role] = hashlib.sha256(archive.read(artifact.member)).hexdigest()
    release = release_responses()
    with ZipFile(io.BytesIO(next(raw for url, raw in release.items() if url.endswith('.zip')))) as archive:
        ciphertext = archive.read('ResList.bin')[16:]
    plaintext = AES.new(b'authored-demofix', AES.MODE_CBC, b'fixture-iv000000').decrypt(ciphertext)
    proof = {'schema':'toolkit-publisher-crypto-v1','abi':'arm64-v8a','source_sha256':SOURCE_SHA256,
        'platform_primitives':'JCA','apk_entry_verified':True,'licenses_verified':True,'system_fallback':False,
        'original_client_execution':False,'account_keys_reused':False,'pointer_bits':64,
        'library_sha256':'a'*64,'manifest_sha256':'b'*64,'key_bytes':32,'nonce_bytes':12,'max_bytes':MAX_BYTES}
    bodies = {**original.bodies, original.base + '/Version.ini':original.version_body,
        original.manifest_url:ElementTree.tostring(original.root), **release}
    for region in ('global', 'cn'):
        bodies.update(publisher(region)[0])
    fixture = {'inputs':inputs.description(),'members':members,
        'release_urls':list(release),'crypto_proof':proof,
        'ciphertext':base64.b64encode(ciphertext).decode('ascii'),
        'plaintext':base64.b64encode(plaintext).decode('ascii'),
        'bodies':{url:base64.b64encode(raw).decode('ascii') for url,raw in bodies.items()}}
    owned = tmp_path / 'owned'
    for name in portable_sources():
        path = owned / name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT / name,path)
    data = tmp_path / 'authored.json';data.write_text(json.dumps(fixture))
    result = subprocess.run([sys.executable,'-I','-B','-c',BOOTSTRAP,str(owned),str(data),str(POLICY)],
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,result.stderr[-3000:]
    proof = json.loads(result.stdout)
    assert proof['owned_modules'] == 106 and proof['registry'] == ['nte','reverse1999','wuwa','zzz']
    assert proof['actual_context_transport'] and proof['stage_never_ready'] and proof['asset_requests'] == 2
    assert proof['manifest_verified'] == 2
    assert proof['native_android_execution'] is False
