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
