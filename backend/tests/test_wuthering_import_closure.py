"""Closed publisher modules must not load desktop discovery just to save data."""
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def test_locale_identity_is_shared_with_the_full_reader():
    from backend import wuthering_assets as assets, wuthering_locales as locales
    assert assets.SUPPORTED_LOCALES is locales.SUPPORTED_LOCALES
    assert assets.TEXT_LOCALES is locales.TEXT_LOCALES
    assert assets.VOICE_LOCALES is locales.VOICE_LOCALES
    assert locales.VOICE_LOCALES['zh-Hans'] == locales.VOICE_LOCALES['zh-Hant'] == ('zh', 7)
    assert set(locales.TEXT_LOCALES) == {'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'fr', 'de', 'ru', 'th', 'vi', 'id', 'es-ES', 'pt-BR'}


def test_actual_minimal_package_language_save_and_owned_source_cache(tmp_path):
    package = tmp_path / 'package' / 'backend'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf8')
    modules = ('wuwa_game_data', 'game_data_protocol', 'publisher_transport', 'private_data_paths',
               'atomic_files', 'wuthering_locales', 'wuthering_source_cache')
    for name in modules:
        module = importlib.import_module('backend.' + name)
        shutil.copyfile(module.__file__, package / (name + '.py'))
    program = r'''
import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
blocked = {'backend.game_tools', 'backend.runtime_bundle', 'backend.runtime_paths',
 'backend.steam_games', 'backend.wuthering_assets', 'backend.textmaps', 'backend.models',
 'backend.wuthering_native_bootstrap', 'backend.wuthering_metadata', 'backend.export_lock'}
class Denied:
 def find_spec(self, fullname, *args):
  if fullname in blocked: raise AssertionError('Desktop/registry import: ' + fullname)
sys.meta_path.insert(0, Denied())
def audit(event, args):
 if event in ('socket.connect', 'subprocess.Popen', 'winreg.OpenKey', 'winreg.SetValue'):
  raise AssertionError('Unexpected platform operation: ' + event)
sys.addaudithook(audit)
from backend import wuwa_game_data as factory, wuthering_source_cache as sources
from backend.game_data_protocol import GameDataRequest
root = Path(sys.argv[2])
factory._request(GameDataRequest('global', 'ja', ('en', 'zh-Hans')))
factory._save(root / 'metadata', b'complete synthetic source')
depot = 'Client/Content/Aki/WwiseAudio_Generated/Media/en/fixture.wem'
reference = (('https://owned.aki-game.net/fixture.pak', 2048, 'a' * 40), 9)
data = b'RIFF' + bytes((8, 0, 0, 0)) + b'WAVEfull'
sources.remember(root, depot, reference, data)
assert sources.cached(root, depot, reference) == data
assert (root / 'metadata').read_bytes() == b'complete synthetic source'
assert not (blocked & set(sys.modules))
print(json.dumps({'backend_modules': sorted(n for n in sys.modules if n.startswith('backend.'))}))
'''
    result = subprocess.run([sys.executable, '-B', '-I', '-c', program, str(package.parent), str(tmp_path / 'outputs')],
                            check=True, capture_output=True, text=True, timeout=20)
    loaded = json.loads(result.stdout)['backend_modules']
    assert 'backend.atomic_files' in loaded and 'backend.game_tools' not in loaded


def test_passive_bootstrap_source_isolated_from_transport_crypto_and_registry(tmp_path):
    from backend.tests.test_wuthering_native_bootstrap import manifest, source
    import zlib
    ref, raw = source(tmp_path)
    package = tmp_path / 'pure-package' / 'backend'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf8')
    for name in ('wuthering_bootstrap_source', 'wuthering_elf_bootstrap'):
        module = importlib.import_module('backend.' + name)
        shutil.copyfile(module.__file__, package / (name + '.py'))
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'source.json').write_text(json.dumps(ref), encoding='utf8')
    (inputs / 'manifest.axml').write_bytes(manifest())
    compressor = zlib.compressobj(wbits=-15)
    packed = compressor.compress(raw) + compressor.flush()
    (inputs / 'module.deflate').write_bytes(packed)
    program = r'''
import sys, json, zlib
from pathlib import Path
sys.path.insert(0, sys.argv[1])
allowed = {'backend', 'backend.wuthering_bootstrap_source', 'backend.wuthering_elf_bootstrap'}
class Denied:
 def find_spec(self, fullname, *args):
  if (fullname.startswith('backend.') and fullname not in allowed) or fullname.split('.')[0] in {'Crypto', 'certifi', 'winreg'}:
   raise AssertionError('Unexpected platform/crypto import: ' + fullname)
sys.meta_path.insert(0, Denied())
def audit(event, args):
 if event in ('socket.connect', 'subprocess.Popen', 'winreg.OpenKey', 'winreg.SetValue'):
  raise AssertionError('Unexpected platform operation: ' + event)
sys.addaudithook(audit)
from backend import wuthering_bootstrap_source as source
root = Path(sys.argv[2])
ref = json.loads((root / 'source.json').read_text(encoding='utf8'))
validated = source.reference(ref)
assert validated == ref and validated is not ref
assert source.identity(ref) == source.identity(validated)
assert source._library((root / 'manifest.axml').read_bytes()) == ref['module']['name']
compressed, decoded = root / 'module.deflate', root / 'decoded.so'
entry = {'plain': ref['module']['plain_bytes'], 'packed': compressed.stat().st_size,
         'crc': int(ref['module']['crc32'], 16)}
size, crc, digest, packed_digest = source._decode_module(compressed, decoded, entry)
assert (size, crc, digest) == (entry['plain'], entry['crc'], ref['module']['sha256'])
assert source._file_hash(compressed) == packed_digest
assert source._file_hash(decoded) == digest
assert source.default_output(decoded, digest).parameter == bytes(range(32))
assert not list(root.rglob('*.dpapi'))
print(json.dumps({'backend_modules': sorted(n for n in sys.modules if n.startswith('backend.'))}))
'''
    result = subprocess.run([sys.executable, '-B', '-I', '-c', program, str(package.parent), str(inputs)],
                            check=True, capture_output=True, text=True, timeout=20)
    assert json.loads(result.stdout)['backend_modules'] == ['backend.wuthering_bootstrap_source', 'backend.wuthering_elf_bootstrap']


def test_minimal_stage_uses_explicit_crypto_without_desktop_or_crypto_imports(tmp_path):
    from Crypto.PublicKey import RSA
    from backend.tests.test_wuthering_native_bootstrap import signed_game, source
    key = RSA.generate(2048)
    _, module = source(tmp_path)
    package = tmp_path / 'stage-package' / 'backend'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf8')
    names = ('wuwa_game_data', 'game_data_protocol', 'publisher_transport', 'private_data_paths',
             'atomic_files', 'wuthering_locales', 'wuthering_bootstrap_source',
             'wuthering_elf_bootstrap', 'publisher_apk', 'publisher_apk_zip', 'publisher_crypto')
    for name in names:
        imported = importlib.import_module('backend.' + name)
        shutil.copyfile(imported.__file__, package / (name + '.py'))
    inputs = tmp_path / 'stage-inputs'
    inputs.mkdir()
    (inputs / 'carrier.apk').write_bytes(signed_game(module, key))
    # Public, newly generated fixture key only. No original client bytes/key.
    import base64
    (inputs / 'public.json').write_text(json.dumps({'n': key.n, 'e': key.e,
        'spki': base64.b64encode(key.public_key().export_key(format='DER')).decode()}), encoding='utf8')
    program = r'''
import sys, json, io, hashlib, hmac, base64, threading
from pathlib import Path
from types import SimpleNamespace
from email.message import Message
sys.path.insert(0, sys.argv[1])
blocked = {'backend.game_tools', 'backend.wuthering_native_bootstrap', 'backend.wuthering_metadata',
 'backend.export_lock', 'backend.wuthering_assets', 'backend.models', 'backend.runtime_paths'}
class Denied:
 def find_spec(self, fullname, *args):
  if fullname in blocked or fullname.split('.')[0] in {'Crypto','certifi','winreg','java'}:
   raise AssertionError('Unexpected desktop/crypto import: ' + fullname)
sys.meta_path.insert(0, Denied())
def audit(event, args):
 if event in ('socket.connect', 'subprocess.Popen', 'winreg.OpenKey', 'winreg.SetValue'):
  raise AssertionError('Unexpected platform operation: ' + event)
sys.addaudithook(audit)
from backend import wuwa_game_data as factory, publisher_crypto
from backend.game_data_protocol import GameDataRequest, PreparationStage
from backend.publisher_transport import PublisherTransport
root = Path(sys.argv[2]); apk = (root / 'carrier.apk').read_bytes()
public = json.loads((root / 'public.json').read_text(encoding='utf8'))
class FixturePublicCrypto:
 def rsa_verify_sha256(self, spki, data, signature):
  assert spki == base64.b64decode(public['spki'])
  length = (public['n'].bit_length() + 7) // 8
  if len(signature) != length or int.from_bytes(signature,'big') >= public['n']: return False
  decoded = pow(int.from_bytes(signature,'big'), public['e'], public['n']).to_bytes(length,'big')
  digest_info = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(data).digest()
  return hmac.compare_digest(decoded, bytes((0,1)) + bytes((255,)) * (length-len(digest_info)-3) + bytes(1) + digest_info)
marker, capability_calls = object(), []
def fixture_capability(*, platform, native):
 assert platform == 'android' and native is marker
 capability_calls.append(True)
 return FixturePublicCrypto()
# Explicit host-only capability simulation; no Android/JNI availability claim.
publisher_crypto.create_publisher_crypto = fixture_capability
url = 'https://owned.aki-game.com/client/download/original/game.apk'
calls, offline = [], False
class Response(io.BytesIO):
 def __init__(self, raw, url, status, headers):
  super().__init__(raw); self.url,self.status,self.headers=url,status,Message()
  for key,value in headers.items(): self.headers[key]=value
 def geturl(self): return self.url
 def read(self,n): return super().read(min(173,n))
def opener(request, **kwargs):
 assert not offline
 calls.append(request.full_url)
 if request.full_url.startswith(factory._source().CATALOGUE + '?_t='):
  raw = json.dumps({'primary':url,'version':'1.0.0'}).encode()
  return Response(raw,request.full_url,200,{'Content-Length':str(len(raw))})
 assert request.full_url == url
 headers = {'ETag':'"fixture"'}
 if request.get_header('Range'):
  start,end = map(int,request.get_header('Range')[6:].split('-'))
  headers.update({'Content-Range':f'bytes {start}-{end}/{len(apk)}','Content-Length':str(end-start+1)})
  return Response(apk[start:end+1],url,206,headers)
 headers['Content-Length'] = str(len(apk))
 return Response(apk,url,200,headers)
factory.PublisherTransport = lambda ctx,**kwargs: PublisherTransport(ctx,opener=opener,**kwargs)
consumed=[]
ctx=SimpleNamespace(request=GameDataRequest('global','ja'),stage_handle=None,cache_directory=root/'outputs',
 check=lambda:None,transfer_lock=threading.RLock(),remaining_bytes=lambda **kwargs:10**7,
 consume_bytes=lambda count,**kwargs:consumed.append(count))
adapter=factory.create_provider('android',SimpleNamespace(publisherCrypto=lambda:marker))
plan=adapter.plan(ctx.request,ctx)
assert plan.runtime_available and plan.download_bytes == len(apk)
stage=adapter.download(plan,ctx)
assert isinstance(stage,PreparationStage) and stage.restore_handle['stage']=='manifest-format'
assert len(capability_calls)==2
before=len(calls);offline=True;ctx.stage_handle=stage.restore_handle;adapter.native=None
assert not adapter.plan(ctx.request,ctx).runtime_available
assert len(calls)==before and not (blocked & set(sys.modules))
assert all(not name.startswith('Crypto') for name in sys.modules)
print(json.dumps({'stage':'manifest-format','module':stage.restore_handle['source']['module']['sha256']}))
'''
    result = subprocess.run([sys.executable, '-B', '-I', '-c', program, str(package.parent), str(inputs)],
                            check=False, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output == {'stage': 'manifest-format', 'module': __import__('hashlib').sha256(module).hexdigest()}
