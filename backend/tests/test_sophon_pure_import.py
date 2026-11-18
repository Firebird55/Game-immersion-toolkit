"""Portable source staging must run without desktop tools or a default downloader."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys

import zstandard


def test_actual_closed_package_imports_and_writes_without_desktop_or_default_network(tmp_path):
    root = Path(__file__).resolve().parents[2]
    # The base APK also owns the shared locale module's deferred Steam table.
    selected, pending = set(), ['sophon_assets', 'game_data', 'zzz_pc_stages', 'zzz_pc_audio', 'steam_games']
    while pending:
        name = pending.pop()
        if name in selected: continue
        selected.add(name)
        module = ast.parse((root / 'backend' / (name + '.py')).read_text(encoding='utf8'))
        for node in module.body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                pending.extend([node.module.split('.')[0]] if node.module else [alias.name for alias in node.names])
    assert not {'game_tools', 'game_assets', 'publisher_http', 'runtime_bundle',
                'prebuilt_readers', 'prebuilt_node_reader', 'voice_assets', 'honkai_assets', 'hoyo_publisher_voice'} & selected
    for name in selected | {'__init__'}:
        target = tmp_path / 'owned/backend' / (name + '.py')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / 'backend' / target.name, target)
    code = r'''
import sys,socket,hashlib,importlib.abc
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.append(sys.argv[2])
class NoDesktop(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'backend.game_tools','backend.game_assets','backend.publisher_http','backend.runtime_bundle',
                  'backend.prebuilt_readers','backend.prebuilt_node_reader','backend.voice_assets','backend.zzz_assets',
                  'backend.honkai_assets','backend.hoyo_publisher_voice','backend.zzz_publisher'}:
   raise AssertionError('Imported a desktop/default transport dependency')
sys.meta_path.insert(0,NoDesktop())
def no_network(*a,**k):raise AssertionError('Unexpected network operation')
socket.socket.connect=no_network;socket.create_connection=no_network
import zstandard
from backend import sophon_assets as source
payload=b'authored context-owned metadata'
packed=zstandard.ZstdCompressor().compress(payload)
digest=hashlib.md5(payload).hexdigest();calls=[]
def fetch(url,*,limit):
 calls.append((url,limit));assert limit==len(packed);return packed
cache=root.parent/'cache';cache.mkdir()
actual=source._verified(cache,'https://publisher.invalid/fixture',len(packed),len(payload),digest,source.MAX_CHUNK,fetch=fetch)
assert actual==payload and (cache/digest).read_bytes()==payload and len(calls)==1
assert source._verified(cache,'https://publisher.invalid/fixture',len(packed),len(payload),digest,source.MAX_CHUNK,fetch=no_network)==payload
from backend import zzz_pc_stages as catalogue
links = [{'text_id': 'Authored', 'source': 'Authored_voice', 'voice_status': 'unavailable'}]
expanded, channels, evidence, kinds = catalogue._group_links(links)
rows = catalogue._dialogue_records({'ja': {'Authored': '合成字幕'}}, 'ja', {'ja'}, channels, evidence, kinds, {})
catalogue._omit_requested_audio(rows, links, expanded, 'sophon-authored', 'ja')
assert rows[0]['audio'] is None and rows[0]['audio_omitted_by_request']
assert rows[0]['source_voice_binding']['sources'] == ['Authored_voice']
snapshot = cache / 'textmap.json'
catalogue.write_payload('zzz', {'format': 2, 'game': 'zzz', 'source_locale': 'ja', 'records': rows},
                        'ja', (), snapshot, reader_revision=catalogue.LANGUAGE_INDEX_VERSION)
assert snapshot.is_file()
from backend import zzz_pc_audio as audio
from types import SimpleNamespace
context = SimpleNamespace(cache_directory=cache, check=lambda: None)
candidate = {'schema': audio.SCHEMA, 'content': rows}
identity = audio._store(context, 'candidates', candidate)
assert identity == hashlib.sha256(audio.encoded(candidate)).hexdigest()
assert audio._load(context, 'candidates', identity) == candidate
for name,module in list(sys.modules.items()):
 if name=='backend' or name.startswith('backend.'):
  assert Path(module.__file__).is_relative_to(root),name
print('Closed owned context/cache route passed without desktop or network imports.')
'''
    dependency_root = str(Path(zstandard.__file__).resolve().parent.parent)
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(tmp_path / 'owned'), dependency_root],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-2500:]
