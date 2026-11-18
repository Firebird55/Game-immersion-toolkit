"""Actual authored PE/candidate/codec reader reference; never an Android claim."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

import pytest

from backend import android_probe
from backend.genshin_blb_native import discover_candidates
from backend.genshin_blb_portable import PortableHelper
from backend.genshin_native_x64 import Image
from backend.genshin_original_bootstrap import prepare_profile
from backend.tests.test_genshin_blb_native import requires_decoder

ROOT=Path(__file__).resolve().parents[2]


def generator():
    spec=importlib.util.spec_from_file_location('authored_genshin_component',ROOT/'scripts/prepare-android-genshin-profile-probe.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


class ReferenceRuntime:
    """Real Windows decoder + portable reader, not a fake Android capability."""
    def __init__(self): self.helper=PortableHelper();self.calls=[]
    @property
    def identity(self): return self.helper.identity
    def channel_profile(self, executable, source, receipt, contract, *, directory, check_cancel):
        self.calls.append(receipt['sha256'])
        return prepare_profile(executable,source,receipt,contract,self.helper,
            directory=directory,check_cancel=check_cancel)


def test_fixture_is_bounded_deterministic_and_owns_actual_pe_method_ranges():
    raw=generator().fixture();value=json.loads(raw)
    assert len(raw)<=65536 and generator().fixture()==raw
    image=Image(base64.b64decode(value['executable_base64']))
    assert len(image.function_starts)==3 and len(image.sections)==2
    assert sorted({hashlib.sha256(image.window(start)).hexdigest() for start in image.function_starts})==value['expected']['method_sha256s']
    assert value['original_game_bytes'] is False
    assert set(value['fixture_sources'])==set(generator().FIXTURE_SOURCES)


@requires_decoder
def test_complete_real_native_candidate_and_compressed_profile_reference(tmp_path):
    raw=generator().fixture();value=json.loads(raw)
    candidates=discover_candidates(Image(base64.b64decode(value['executable_base64'])))
    assert len(candidates)==2
    assert sum(candidate.sha256==value['expected']['parameters_sha256'] for candidate in candidates)==1
    runtime=ReferenceRuntime();sentinel=tmp_path/'accepted-profile.bin';sentinel.write_bytes(b'prior authored state')
    result=android_probe._genshin_profile_cases(tmp_path,raw.decode(),runtime)
    assert result['passed'] and result['codec_candidates']==2 and result['accepted_candidates']==1
    assert result['malformed_rejections']==2 and result['prior_state_retained_on_failure'] is True
    assert len(runtime.calls)==3 and hashlib.sha256(sentinel.read_bytes()).hexdigest()==value['expected']['payload_sha256']
    assert result['runtime_provenance'] is None and 'installed_host_decoder' not in result
    assert not list(tmp_path.glob('channel-codec-*')) and not (tmp_path/'profile.pending').exists()


@requires_decoder
@pytest.mark.parametrize('change',['payload-eof','complete-map','expected-body','expected-methods'])
def test_bad_primary_fixture_preserves_the_previous_profile_and_leaves_no_candidate_scratch(tmp_path,change):
    value=json.loads(generator().fixture());sentinel=tmp_path/'accepted-profile.bin';prior=b'previous valid authored profile'
    sentinel.write_bytes(prior)
    if change in ('payload-eof','complete-map'):
        raw=next(row['carrier_base64'] for row in value['malformed'] if row['kind']==change)
        data=base64.b64decode(raw);value['carrier_base64']=raw
        value['expected'].update(carrier_bytes=len(data),carrier_sha256=hashlib.sha256(data).hexdigest(),carrier_md5=hashlib.md5(data).hexdigest())
    elif change=='expected-body': value['expected']['body_sha256']='0'*64
    else:value['expected']['method_sha256s']=['0'*64]
    with pytest.raises(ValueError):android_probe._genshin_profile_cases(tmp_path,json.dumps(value),ReferenceRuntime())
    assert sentinel.read_bytes()==prior and not (tmp_path/'profile.pending').exists()
    assert not list(tmp_path.glob('channel-codec-*'))


def test_actual_android_entry_requires_the_started_hosts_verified_decoder_before_fixture_io(tmp_path,monkeypatch):
    from backend import android_host
    monkeypatch.setattr(android_host,'_host',None)
    with pytest.raises(ValueError,match='installed host data decoder'):android_probe.run_genshin_profile(tmp_path,'{}')
    assert not list(tmp_path.iterdir())


def test_closed_namespace_imports_all_component_identity_inputs_without_desktop_fallback(tmp_path):
    from backend.tests.test_android_publisher_sources import portable_sources
    owned=tmp_path/'owned'
    for name in portable_sources():
        target=owned/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    script=r'''
import importlib.abc,importlib,json,socket,subprocess,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
def deny(*a,**k):raise AssertionError('Unexpected desktop, supplier or network dependency')
socket.socket.connect=deny;socket.create_connection=deny;subprocess.Popen=deny
forbidden={'capstone','Crypto','pefile','java','backend.game_tools','backend.publisher_http','backend.runtime_bundle'}
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if any(name==value or name.startswith(value+'.') for value in forbidden):deny()
sys.meta_path.insert(0,Block())
from backend.genshin_android_runtime import AndroidGenshinRuntime,_ANDROID_IMPLEMENTATION
from backend.genshin_reader_identity import implementation_identity
for name in _ANDROID_IMPLEMENTATION:importlib.import_module('backend.'+name)
assert len(implementation_identity(_ANDROID_IMPLEMENTATION))==64
try:AndroidGenshinRuntime(None)
except ValueError:pass
else:raise AssertionError('Missing actual Android decoder admitted')
from backend.game_data_providers import create_game_data_providers
assert set(create_game_data_providers(platform='android'))=={'nte','reverse1999','wuwa'}
assert 'backend.genshin_game_data' not in sys.modules
for name,module in list(sys.modules.items()):
 if name=='backend' or name.startswith('backend.'):
  assert Path(module.__file__).is_relative_to(Path(sys.argv[1]))
print(json.dumps({'owned_modules':len(list((Path(sys.argv[1])/'backend').glob('*.py'))),
                  'component_imports_verified':True,'native_android_execution':False}))
'''
    result=subprocess.run([sys.executable,'-I','-B','-c',script,str(owned)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr[-3000:]
    assert json.loads(result.stdout)=={'owned_modules':len(portable_sources()),
        'component_imports_verified':True,'native_android_execution':False}


@pytest.mark.parametrize('change',[None,'carrier','fixture-source','method-ownership','missing-negative','notice','extra-asset'])
def test_actual_apk_profile_asset_audit_binds_authored_inputs_and_original_notice(tmp_path,change):
    value=json.loads(generator().fixture())
    if change=='carrier': value['carrier_base64']=base64.b64encode(b'changed'*100).decode()
    if change=='fixture-source':value['fixture_sources'][next(iter(value['fixture_sources']))]='0'*64
    if change=='method-ownership':value['expected']['method_sha256s']=[]
    if change=='missing-negative':value['malformed'].pop()
    path=tmp_path/'authored-assets.zip'
    with ZipFile(path,'w') as output:
        output.writestr('assets/genshin-profile-authored.json',json.dumps(value))
        output.writestr('assets/genshin-profile-licenses/AnimeStudio-LICENSE.txt',
            b'changed' if change=='notice' else (ROOT/'packaging/genshin-reader/AnimeStudio-LICENSE.txt').read_bytes())
        if change=='extra-asset':output.writestr('assets/genshin-profile-unreviewed.bin',b'extra')
    spec=importlib.util.spec_from_file_location('genshin_apk_component_audit',ROOT/'scripts/verify-android-apk.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    with ZipFile(path) as source:
        if change:
            with pytest.raises(ValueError):audit.verify_genshin_profile_component(source,ROOT)
        else:
            result=audit.verify_genshin_profile_component(source,ROOT)
            assert result['expected']['codec_candidates']==2 and result['software_notice']['expression']=='MIT'
            assert result['profile_only'] is True and result['factory_activated'] is False
