"""Owned SenseVoice-format fixture: native API/format proof, no trained model.

The small protobuf writer follows the public ONNX schema; it carries no model
weights, sampled speech, corpus tokens or copied model metadata. Native probing
is Windows-only and is called in bounded child processes by reference-asr.py.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys


def varint(value):
    value &= (1 << 64) - 1
    data = bytearray()
    while value >= 128:
        data.append((value & 127) | 128)
        value >>= 7
    data.append(value)
    return bytes(data)


def number(field, value):
    return varint(field << 3) + varint(value)


def blob(field, value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return varint((field << 3) | 2) + varint(len(value)) + value


def value_info(name, dtype, shape):
    # ValueInfoProto.type -> TypeProto.tensor_type -> TensorShapeProto.dim.
    dims = b''.join(blob(1, number(1, v) if isinstance(v, int) else blob(2, v)) for v in shape)
    return blob(1, name) + blob(2, blob(1, number(1, dtype) + blob(2, dims)))


def tensor(name, dtype, shape, raw):
    return (b''.join(number(1, v) for v in shape) + number(2, dtype)
            + blob(8, name) + blob(9, raw))


def node(op, inputs, output):
    return b''.join(blob(1, name) for name in inputs) + blob(2, output) + blob(4, op)


def model_bytes(wrong_shape=False):
    """Return deterministic logits [1,T+4,6] derived only from input shape.

    CTC IDs 1..4 are authored controls; repeated ID5 becomes AUTHORED. The graph
    deliberately does not recognize sound. Four inputs match the fixed adapter.
    """
    initializers = [tensor('time_index', 7, [], struct.pack('<q', 1)),
        tensor('zero', 7, [], struct.pack('<q', 0)),
        tensor('one', 7, [], struct.pack('<q', 1)),
        tensor('four', 7, [], struct.pack('<q', 4)),
        tensor('five', 7, [], struct.pack('<q', 5)),
        tensor('depth', 7, [], struct.pack('<q', 6)),
        tensor('axis_zero', 7, [1], struct.pack('<q', 0)),
        tensor('hot_values', 1, [2], struct.pack('<ff', -10, 10))]
    nodes = [('Shape', ['features'], 'feature_shape'),
        ('Gather', ['feature_shape', 'time_index'], 'time'),
        ('Add', ['time', 'four'], 'time_with_controls'),
        ('Range', ['zero', 'time_with_controls', 'one'], 'positions'),
        ('Add', ['positions', 'one'], 'increasing_ids'),
        ('Min', ['increasing_ids', 'five'], 'token_ids'),
        ('OneHot', ['token_ids', 'depth', 'hot_values'], 'unbatched_logits'),
        ('Unsqueeze', ['unbatched_logits', 'axis_zero'], 'logits')]
    graph = b''.join(blob(1, node(*n)) for n in nodes) + blob(2, 'OwnedFormatFixture')
    graph += b''.join(blob(5, t) for t in initializers)
    for name, dtype, shape in [('features', 1, [1, 'T', 79 if wrong_shape else 80]),
            ('features_length', 6, [1]), ('language', 6, [1]), ('text_norm', 6, [1])]:
        graph += blob(11, value_info(name, dtype, shape))
    graph += blob(12, value_info('logits', 1, [1, 'T_plus_four', 6]))
    metadata = {'comment': 'Independently authored format fixture; no trained weights',
        'vocab_size': '6', 'blank_id': '0', 'lfr_window_size': '1', 'lfr_window_shift': '1',
        'normalize_samples': '1', 'with_itn': '1', 'without_itn': '0',
        'lang_auto': '0', 'lang_zh': '1', 'lang_en': '2', 'lang_ja': '3',
        'lang_ko': '4', 'lang_yue': '5', 'neg_mean': ','.join(['0'] * 80),
        'inv_stddev': ','.join(['1'] * 80)}
    # ModelProto: IR9, opset13, graph; no external tensor data or custom ops.
    return (number(1, 9) + blob(2, 'proxy-r19-owned-format-fixture') + blob(7, graph)
        + blob(8, number(2, 13))
        + b''.join(blob(14, blob(1, k) + blob(2, v)) for k, v in sorted(metadata.items())))


def fixtures(root):
    root.mkdir(parents=True)
    (root / 'model.onnx').write_bytes(model_bytes())
    (root / 'wrong-shape.onnx').write_bytes(model_bytes(wrong_shape=True))
    (root / 'corrupt.onnx').write_bytes(b'owned-invalid-onnx-fixture')
    (root / 'tokens.txt').write_text(
        '<blank> 0\n<lang> 1\n<emotion> 2\n<event> 3\n<itn> 4\nAUTHORED 5\n', encoding='utf-8')
    # 0.5 seconds of independently authored silence; no recorded audio.
    (root / 'silence.f32').write_bytes(b'\0' * 8000 * 4)
    return {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(root.iterdir())}


def probe(package, numpy_root, fixture, case):
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise ValueError('Native ASR reference probing requires Windows x64.')
    package, numpy_root, fixture = package.resolve(), numpy_root.resolve(), fixture.resolve()
    if importlib.util.find_spec('sherpa_onnx') is not None:
        raise ValueError('An ambient sherpa package must not satisfy the experiment.')
    sys.path.insert(0, str(package))
    sys.path.insert(0, str(numpy_root))
    # Deliberate package-local loader directory; PATH is never a codec fallback.
    with os.add_dll_directory(str(package / 'sherpa_onnx' / 'lib')):
        import numpy as np
        import sherpa_onnx
        from sherpa_onnx.lib import _sherpa_onnx
        if Path(np.__file__).resolve().parent != numpy_root / 'numpy':
            raise ValueError('The imported NumPy is outside the exact separate wheel input.')
        if Path(_sherpa_onnx.__file__).resolve().parent != package / 'sherpa_onnx' / 'lib':
            raise ValueError('The imported binding is outside the owned candidate.')
        if sherpa_onnx.GenerationConfig is not None or sherpa_onnx.OfflineTtsSupertonicModelConfig is not None:
            raise ValueError('Disabled-TTS placeholders differ.')
        if (sherpa_onnx.__version__ != '1.13.8+proxy.r19.asr1' or sherpa_onnx.version != '1.13.8'
                or sherpa_onnx.git_sha1 != '8c8e275d'
                or sherpa_onnx.onnxruntime_version != '1.28.2'):
            raise ValueError('The separate binding or actual native ONNX API version differs.')
        native = ctypes.WinDLL('kernel32', use_last_error=True)
        native.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        native.GetModuleHandleW.restype = ctypes.c_void_p
        native.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
        native.GetModuleFileNameW.restype = ctypes.c_uint
        handle = native.GetModuleHandleW('onnxruntime.dll')
        path = ctypes.create_unicode_buffer(32768)
        length = native.GetModuleFileNameW(handle, path, len(path)) if handle else 0
        origin = Path(path.value).resolve() if length and length < len(path) else None
        wanted = package / 'sherpa_onnx' / 'lib' / 'onnxruntime.dll'
        if origin != wanted:
            raise ValueError('The loaded ONNX DLL did not originate in the owned candidate.')
        model = {'decode': 'model.onnx', 'wrong-shape': 'wrong-shape.onnx',
                 'corrupt': 'corrupt.onnx'}[case]
        try:
            recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(fixture / model), tokens=str(fixture / 'tokens.txt'),
                num_threads=2, language='zh', use_itn=True, debug=False)
        except Exception:
            if case != 'corrupt':
                raise
            result = 'rejected-invalid-model'
        else:
            if case == 'corrupt':
                raise ValueError('The corrupt ONNX model was accepted.')
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, np.fromfile(fixture / 'silence.f32', dtype=np.float32))
            recognizer.decode_stream(stream)
            text = stream.result.text
            if text != ('AUTHORED' if case == 'decode' else ''):
                raise ValueError('Actual native SenseVoice-format inference differs.')
            result = 'decoded-owned-format' if case == 'decode' else 'native-shape-error-empty-result'
        return {'case': case, 'result': result, 'binding_origin': 'candidate/sherpa_onnx/lib',
            'binding_filename': Path(_sherpa_onnx.__file__).name,
            'binding_sha256': hashlib.sha256(Path(_sherpa_onnx.__file__).read_bytes()).hexdigest(),
            'onnx_dll_origin': 'candidate/sherpa_onnx/lib/onnxruntime.dll',
            'onnx_dll_sha256': hashlib.sha256(wanted.read_bytes()).hexdigest(),
            'compiled_version': sherpa_onnx.version,
            'compiled_onnxruntime_api_version': sherpa_onnx.onnxruntime_version,
            'upstream_embedded_git_metadata': sherpa_onnx.git_sha1,
            'embedded_git_metadata_is_source_proof': False,
            'trained_model': False, 'speech_recognition_accuracy_verified': False,
            'fixture_contract': 'native-format-api-only-independent-graph-tokens-pcm'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--numpy', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--case', choices=['decode', 'wrong-shape', 'corrupt'], required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = probe(args.package, args.numpy, args.fixtures, args.case)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except Exception:
        print('Native ASR reference probe failed; inspect its private host log.', file=sys.stderr)
        sys.exit(1)
