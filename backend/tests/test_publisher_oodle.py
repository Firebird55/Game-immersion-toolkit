"""Bounded codec/capability tests; original game software is never loaded."""
import hashlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend import publisher_oodle as codec
from backend.game_data_protocol import GameDataError
from backend.prebuilt_node_reader import PrebuiltNodeReader


def capability(tmp_path,monkeypatch):
    root=tmp_path/'closed-resources';root.mkdir()
    node=root/'node.exe';node.write_bytes(b'authored nonexecuted Node stand-in')
    module=root/'dependencies/ooz/index.js';module.parent.mkdir(parents=True);module.write_bytes(b'authored wrapper')
    decoder=module.parent/'build/ooz.js';decoder.parent.mkdir();decoder.write_bytes(b'authored WASM stand-in')
    for key,path in (('NODE_SHA256',node),('WRAPPER_SHA256',module),('DECODER_SHA256',decoder)):
        monkeypatch.setattr(codec,key,hashlib.sha256(path.read_bytes()).hexdigest())
    reader=SimpleNamespace(executable=node,root=root,identity='f'*64,environment=PrebuiltNodeReader.environment)
    from backend import prebuilt_node_reader
    monkeypatch.setattr(prebuilt_node_reader,'production_zzz_reader',lambda **kw:reader)
    layout=SimpleNamespace(mode='bundle',profile='runtime')
    return codec.create_compression(platform='windows',layout=layout),reader


def test_explicit_capability_uses_only_pinned_node_clean_environment_and_bounded_batch(tmp_path,monkeypatch):
    runtime,reader=capability(tmp_path,monkeypatch);seen=[]
    monkeypatch.setenv('NODE_OPTIONS','--import=untrusted');monkeypatch.setenv('NODE_PATH','untrusted')
    def run(command,**options):
        seen.append((command,options));return SimpleNamespace(returncode=0,stdout=b'aaaaabb')
    monkeypatch.setattr(codec,'_run',run)
    assert runtime.decode([('Oodle',b'one',5),('Oodle',b'two',2)],work=tmp_path,check=lambda:None)==b'aaaaabb'
    command,options=seen[0]
    assert command[0]==str(reader.executable) and command[-1]==(reader.root/'dependencies/ooz/index.js').as_uri()
    assert options['input']==b'\x03\0\0\0\x05\0\0\0one\x03\0\0\0\x02\0\0\0two'
    assert options['env']['PATH']=='' and 'NODE_OPTIONS' not in options['env'] and 'NODE_PATH' not in options['env']
    assert options['timeout']==30 and options['cwd']==tmp_path
    assert runtime.identity['schema']=='toolkit-owned-oodle-windows/1'


@pytest.mark.parametrize('bad',[('Zlib',b'x',1),('Oodle',b'',1),('Oodle',b'x',True),('Oodle',b'x',codec.MAX_DECODED+1)])
def test_bad_bounds_or_methods_fail_before_process(tmp_path,monkeypatch,bad):
    runtime,_=capability(tmp_path,monkeypatch)
    monkeypatch.setattr(codec,'_run',lambda *a,**kw:pytest.fail('Unbounded input was executed.'))
    with pytest.raises(GameDataError):runtime.decode([bad],work=tmp_path,check=lambda:None)


@pytest.mark.parametrize('failure',['status','length','timeout','changed'])
def test_process_failure_or_changed_software_never_returns_partial_data(tmp_path,monkeypatch,failure):
    runtime,reader=capability(tmp_path,monkeypatch)
    def run(*args,**kw):
        if failure=='timeout':raise TimeoutError('owned-decoder')
        if failure=='changed':(reader.root/'dependencies/ooz/index.js').write_bytes(b'changed')
        return SimpleNamespace(returncode=1 if failure=='status' else 0,stdout=b'' if failure=='length' else b'a')
    monkeypatch.setattr(codec,'_run',run)
    with pytest.raises(GameDataError):runtime.decode([('Oodle',b'x',1)],work=tmp_path,check=lambda:None)


def test_android_and_source_mode_never_resolve_or_execute_desktop_decoder(tmp_path,monkeypatch):
    from backend import prebuilt_node_reader
    monkeypatch.setattr(prebuilt_node_reader,'production_zzz_reader',lambda **kw:pytest.fail('Desktop resolver used'))
    assert codec.create_compression(platform='android') is None
    assert codec.create_compression(platform='windows',layout=SimpleNamespace(mode='source',profile='source')) is None


def test_android_import_does_not_require_process_crypto_or_desktop_resources():
    script='''import sys
class RejectDesktop:
 def find_spec(self,name,path=None,target=None):
  if name in {'subprocess','backend.prebuilt_node_reader','backend.runtime_bundle','Crypto'} or name.startswith('Crypto.'):
   raise AssertionError('Desktop dependency imported eagerly: '+name)
sys.meta_path.insert(0,RejectDesktop())
from backend.publisher_oodle import create_compression
assert create_compression(platform='android') is None
'''
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
