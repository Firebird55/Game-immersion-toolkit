"""ASR native import probe; no main-runtime imports belong in this image."""
import json
import sys

from .runtime_bundle import RuntimeBundleError
from .runtime_probe_common import synthetic_roots, block_remote_access, loaded_native


def asr(layout):
    import numpy as np
    import sherpa_onnx
    if not callable(sherpa_onnx.OfflineRecognizer.from_sense_voice) or int(np.zeros(1).size) != 1:
        raise RuntimeBundleError('ASR native API is unavailable.')
    if any(name in sys.modules for name in ('onnxruntime', 'kaldi_native_fbank', 'backend.api', 'oneocr')):
        raise RuntimeBundleError('ASR imported the main runtime native family.')
    return {'sherpa_native_import': 'passed', 'model_inference': 'not-run; separate user model required',
            'loaded_native': loaded_native(layout)}



def main(kind, layout):
    if sys.platform != 'win32' or kind != 'asr':
        raise RuntimeBundleError('ASR probe requires its isolated Windows image.')
    synthetic_roots(layout)
    sys.addaudithook(block_remote_access)
    details = asr(layout)
    print(json.dumps({'schema': 'proxy-r19-runtime-probe-v1', 'source_commit': layout.source_commit,
        'build_id': layout.build_id, 'kind': kind, 'status': 'passed', 'details': details,
        'real_accounts_accessed': False, 'installed_game_probe': 'not-run', 'rights_review': 'pending-exact-output',
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}))
    return 0
