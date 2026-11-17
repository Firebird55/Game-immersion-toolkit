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
    assert set(policy['providers']) == {'nte', 'reverse1999'}
    assert len(policy['files']) == 10 and len(portable_sources()) == 67
    assert 'backend/android_authored_game_data.py' in portable_sources()
    assert 'backend/text_display.py' in portable_sources()
    assert {key.removeprefix('backend/').removesuffix('.py') for key in policy['files']} == {
        module for provider in policy['providers'].values() for module in provider['modules']} | set(policy['context_modules'])
    assert all(not provider['snapshot_runtime'] and provider['dependencies'] == ['python-stdlib']
        for provider in policy['providers'].values())
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
import sys,json,socket,builtins,time,hashlib,io
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
original_import=builtins.__import__
def guarded(name,*args,**kwargs):
 if any(name==value or name.startswith(value+'.') for value in policy['forbidden_stage_imports']):deny()
 return original_import(name,*args,**kwargs)
builtins.__import__=guarded
from backend.game_data_providers import create_game_data_providers
from backend.game_data import GameDataService
from backend.publisher_transport import PublisherTransport
from backend import nte_updater_source as source,nte_updater_baseline as baseline
class UnusedNative:
 def __getattribute__(self,name):raise AssertionError('A pure stage queried a native service')
providers=create_game_data_providers(platform='android',native=UnusedNative())
assert set(providers)=={'nte','reverse1999'}
assert all(name not in sys.modules for name in policy['forbidden_stage_imports'])
# A mismatched late-stage call must fail at the Android gate before a desktop
# source module import, including when these modules do not exist in the APK.
from types import SimpleNamespace
from backend.game_data_protocol import GameDataError
for stage in ('original-indices','archive-index-ranges','authoring-import-ranges',
 'process-authoring','initial-descriptions','dialogue-package-ranges',
 'process-metadata','global-import-metadata'):
 try:providers['nte'].download(SimpleNamespace(stage=stage),SimpleNamespace(check=lambda:None))
 except GameDataError as error:assert error.code=='nte_reader_unavailable'
 else:raise AssertionError('Android admitted a desktop-only continuation')
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
inputs=source._inputs(data['inputs'])
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
 assert len([url for url in calls if url.endswith('.zip')])==2
 for name,module in list(sys.modules.items()):
  if name=='backend' or name.startswith('backend.'):
   assert Path(module.__file__).is_relative_to(owned),name
 print(json.dumps({'schema':'android-publisher-closed-source-host-v1','registry':['nte','reverse1999'],
  'owned_modules':len(list((owned/'backend').glob('*.py'))),'no_external_network':True,'no_desktop_helper':True,
  'actual_context_transport':True,'stage_never_ready':True,'unknown_content_size_preserved':True,
  'asset_requests':len([url for url in calls if url.endswith('.zip')]),'native_android_execution':False}))
finally:service.close()
'''


def test_exact_closed_namespace_executes_real_bootstrap_without_desktop_or_network_fallback(tmp_path):
    # These are authored PE/configuration fixtures from the game owner's tests,
    # never original game software or an alternative preparation implementation.
    from backend.tests.fixtures.nte_updater_inputs import Originals
    from backend.nte_updater_source import plan
    original = Originals();inputs = plan(fetch=original.fetch)
    members = {}
    for artifact in inputs.artifacts:
        with ZipFile(io.BytesIO(original.bodies[artifact.url])) as archive:
            members[artifact.role] = hashlib.sha256(archive.read(artifact.member)).hexdigest()
    bodies = {**original.bodies, **{original.base + '/Version.ini':original.version_body,
        original.manifest_url:ElementTree.tostring(original.root)}}
    fixture = {'inputs':inputs.description(),'members':members,
        'bodies':{url:base64.b64encode(raw).decode('ascii') for url,raw in bodies.items()}}
    owned = tmp_path / 'owned'
    for name in portable_sources():
        path = owned / name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT / name,path)
    data = tmp_path / 'authored.json';data.write_text(json.dumps(fixture))
    result = subprocess.run([sys.executable,'-I','-B','-c',BOOTSTRAP,str(owned),str(data),str(POLICY)],
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,result.stderr[-3000:]
    proof = json.loads(result.stdout)
    assert proof['owned_modules'] == 67 and proof['registry'] == ['nte','reverse1999']
    assert proof['actual_context_transport'] and proof['stage_never_ready'] and proof['asset_requests'] == 2
    assert proof['native_android_execution'] is False
