# Executed only after closure.py has validated the exact Windows build inputs.
import json
import os
from pathlib import Path
import sys

root = Path(SPECPATH).parents[1]
sys.path.insert(0, str(root))
from PyInstaller.utils.hooks import collect_all, collect_submodules
from backend.runtime_bundle import CHILD_TARGETS

inputs = json.loads(Path(os.environ['PROXY_RUNTIME_BUILD_INPUTS']).read_text(encoding='utf-8'))
runtime = inputs['profile'] == 'runtime'
if runtime:
    raise SystemExit('Full runtime profile is disabled until helper/host artifacts and exact collected-file closure are implemented and reviewed.')
data = [(str(root / item['path']), str(Path(item['path']).parent)) for item in inputs['resources']]
hidden = []
binaries = []
if runtime:
    # Registry-selected imports cannot be discovered from import_module alone.
    # Collect every backend reader, retaining all 25 games and shared parsers.
    hidden = [name for name in collect_submodules('backend')
              if not name.startswith('backend.tests') and name != 'backend.agent_transcribe']
    hidden += [target for kind, (mode, target) in CHILD_TARGETS.items()
               if mode == 'module' and kind != 'asr']
    for package in ('uvicorn', 'numpy', 'scipy', 'kaldi_native_fbank', 'onnxruntime',
                    'cv2', 'PIL', 'windows_capture', 'pyaudiowpatch', 'Crypto',
                    'rapidfuzz', 'opencc', 'pypinyin', 'certifi', 'oneocr'):
        package_data, package_binaries, package_hidden = collect_all(package)
        data += package_data
        binaries += package_binaries
        hidden += package_hidden

main = Analysis([str(root / 'backend/bundle_entry.py')], pathex=[str(root)],
    binaries=binaries, datas=data, hiddenimports=hidden,
    excludes=['sherpa_onnx', 'sherpa_onnx_core', 'pytest', 'backend.tests'])
main_pyz = PYZ(main.pure)
main_exe = EXE(main_pyz, main.scripts, [], exclude_binaries=True,
    name='ProxyTranscriptRuntime', console=True, contents_directory='_internal')
main_collection = COLLECT(main_exe, main.binaries, main.datas, name='ProxyTranscriptRuntime')

if runtime:
    # Separate Analysis, executable, directory and native library tree. Putting
    # both ONNX families in one collection defeats process/DLL isolation.
    asr_data, asr_binaries, asr_hidden = collect_all('sherpa_onnx')
    asr = Analysis([str(root / 'backend/bundle_entry.py')], pathex=[str(root)],
        binaries=asr_binaries, datas=asr_data, hiddenimports=['backend.agent_transcribe', *asr_hidden],
        excludes=['onnxruntime', 'kaldi_native_fbank', 'oneocr', 'backend.api', 'backend.capture', 'pytest'])
    asr_pyz = PYZ(asr.pure)
    asr_exe = EXE(asr_pyz, asr.scripts, [], exclude_binaries=True,
        name='ProxyTranscriptAsr', console=True, contents_directory='_internal')
    asr_collection = COLLECT(asr_exe, asr.binaries, asr.datas, name='ProxyTranscriptAsr')
