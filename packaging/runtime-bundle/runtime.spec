# Executed after the native builder has validated its exact installed inputs.
# A runtime profile is a construction choice, never a release approval.
import json
import os
from pathlib import Path
import sys

root = Path(SPECPATH).parents[1]
sys.path.insert(0, str(root))
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata
from backend.runtime_bundle import CHILD_TARGETS

inputs = json.loads(Path(os.environ['PROXY_RUNTIME_BUILD_INPUTS']).read_text(encoding='utf-8'))
runtime = inputs['profile'] in {'runtime', 'runtime-experiment'}
resource_root = Path(os.environ['PROXY_RUNTIME_EVIDENCE_ROOT'])
data = [(str(resource_root / item['path']), str(Path(item['path']).parent)) for item in inputs['resources']]
hidden = ['backend.desktop_frontend'] if inputs['profile'] == 'frontend-experiment' else []
binaries = []

def production_module(name):
    if name.startswith(('onnxruntime.quantization', 'onnxruntime.transformers', 'scipy._lib.array_api_compat.torch')):
        return False
    if name == 'cv2.data':
        return False  # Unused Haar-cascade models are outside the runtime closure.
    return not any(part.lower() in {'tests', 'test', 'testing', 'selftest', 'conftest', 'pytest'} for part in name.split('.'))

def package_closure(package):
    # Test corpora, private examples and embedded FFmpeg are not runtime inputs.
    # PyInstaller's normal package hooks still collect dependent native DLLs.
    return (collect_data_files(package, excludes=['**/tests/**', '**/test/**', '**/testing/**', '**/SelfTest/**', '**/__pycache__/**']),
            collect_dynamic_libs(package), collect_submodules(package, filter=production_module))

if runtime:
    # Registry-selected imports cannot be discovered from import_module alone.
    # Collect every backend reader, retaining all 25 games and shared parsers.
    hidden = [name for name in collect_submodules('backend', filter=production_module)
              if name not in {'backend.agent_transcribe', 'backend.asr_probe'}]
    hidden += [target for kind, (mode, target) in CHILD_TARGETS.items()
               if mode == 'module' and kind != 'asr']
    packages = ['uvicorn', 'numpy', 'scipy', 'kaldi_native_fbank', 'onnxruntime',
                'cv2', 'PIL', 'Crypto', 'rapidfuzz', 'opencc', 'pypinyin', 'certifi',
                'rapidocr_onnxruntime', 'pyclipper', 'shapely', 'zstandard']
    if sys.platform == 'win32':
        packages += ['windows_capture', 'pyaudiowpatch', 'oneocr']
    elif sys.platform == 'linux':
        packages += ['Xlib', 'secretstorage', 'jeepney', 'cryptography', 'cffi']
        hidden += ['keyring.backends.SecretService', 'jaraco.classes',
                   'jaraco.context', 'jaraco.functools', 'more_itertools']
    elif sys.platform == 'darwin':
        packages += ['objc', 'Quartz', 'AppKit', 'Foundation']
        hidden += ['keyring.backends.macOS', 'jaraco.classes',
                   'jaraco.context', 'jaraco.functools', 'more_itertools']
    # Qt's module hooks collect the platform plugin and its native dependencies.
    # Do not collect all of Essentials (Designer, QML, SQL, etc. are not used).
    hidden += ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'shiboken6']
    data += copy_metadata('PySide6-Essentials') + copy_metadata('shiboken6')
    for package in packages:
        package_data, package_binaries, package_hidden = package_closure(package)
        data += package_data
        binaries += package_binaries
        hidden += package_hidden

main = Analysis([str(root / 'backend/bundle_entry.py')], pathex=[str(root)],
    hookspath=[str(root / 'packaging/runtime-bundle/hooks')],
    binaries=binaries, datas=data, hiddenimports=hidden,
    excludes=['sherpa_onnx', 'sherpa_onnx_core', 'pytest', 'backend.tests', 'pip', 'setuptools', 'imageio_ffmpeg', 'cv2.data'])
# OpenCV's generic hook also collects its Haar-cascade examples. Capture uses
# image conversion/thresholding, never those models; do not relabel them as user
# data or relax the private-tree gate to accept arbitrary `data/` directories.
main.datas = [entry for entry in main.datas if not entry[0].replace('\\', '/').startswith('cv2/data/')]
main_pyz = PYZ(main.pure)
main_exe = EXE(main_pyz, main.scripts, [], exclude_binaries=True,
    name='GameImmersionToolkit', console=True, contents_directory='_internal')
main_collection = COLLECT(main_exe, main.binaries, main.datas, name='GameImmersionToolkit')

if runtime:
    # Separate Analysis, executable, directory and native library tree. Putting
    # both ONNX families in one collection defeats process/DLL isolation.
    asr_data, asr_binaries, asr_hidden = package_closure('sherpa_onnx')
    # sherpa-onnx-core is a distribution, not an importable module. Its DLLs
    # live in sherpa_onnx/lib and package_closure above collects that exact tree.
    asr_data += copy_metadata('sherpa-onnx-core')
    asr = Analysis([str(root / 'backend/bundle_entry.py')], pathex=[str(root)],
        binaries=asr_binaries, datas=asr_data, hiddenimports=['backend.agent_transcribe', 'backend.asr_probe', *asr_hidden],
        excludes=['onnxruntime', 'kaldi_native_fbank', 'oneocr', 'backend.api', 'backend.capture',
                  'backend.desktop_host', 'backend.desktop_host_ui', 'PySide6', 'shiboken6',
                  'pytest', 'cv2', 'scipy', 'pip', 'setuptools'])
    asr_pyz = PYZ(asr.pure)
    asr_exe = EXE(asr_pyz, asr.scripts, [], exclude_binaries=True,
        name='GameImmersionToolkitAsr', console=True, contents_directory='_internal')
    asr_collection = COLLECT(asr_exe, asr.binaries, asr.datas, name='GameImmersionToolkitAsr')
