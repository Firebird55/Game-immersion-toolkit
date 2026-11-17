"""Software input and pinned reference API checks; not Android execution."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import zstandard

ROOT = Path(__file__).resolve().parents[2]


def builder():
    spec = importlib.util.spec_from_file_location('owned_zstd_builder', ROOT / 'scripts/build-android-zstandard.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_wrong_software_input_stops_before_any_toolchain_execution(tmp_path, monkeypatch):
    owned = builder();source = tmp_path / 'source.tar.gz';source.write_bytes(b'not the authenticated upstream source')
    monkeypatch.setattr(owned.subprocess, 'run', lambda *a, **k: pytest.fail('Compiler ran before original-source authentication'))
    with pytest.raises(ValueError, match='pinned receipt'):
        owned.build(tmp_path / 'work', source, tmp_path / 'ndk', tmp_path / 'ndk.zip', tmp_path / 'python')


def test_complete_original_notices_keep_embedded_copyright_and_compat_header(tmp_path):
    owned = builder()
    for name in ('LICENSE', 'zstd/LICENSE', 'zstd/COPYING', 'c-ext/pythoncapi_compat.h'):
        path = tmp_path / name;path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('Original notice for ' + name).encode())
    (tmp_path / 'zstd/zstd.c').write_bytes(b'/* Copyright original owner. Exact original notice. */\nint code;\n/* Copyright second owner. */')
    policy = json.loads((ROOT / 'packaging/android/zstandard-native.json').read_text())
    notices = owned.original_notices(tmp_path, policy)
    assert len(notices) == 5
    assert notices['c-ext/pythoncapi_compat.h'] == b'Original notice for c-ext/pythoncapi_compat.h'
    assert b'Copyright original owner. Exact original notice.' in notices['embedded-original-notices.txt']
    assert b'Copyright second owner.' in notices['embedded-original-notices.txt']
    assert b'int code;' not in notices['embedded-original-notices.txt']


VECTORS = json.loads((ROOT / 'packaging/android/zstandard-authored-vectors.json').read_text())


@pytest.mark.parametrize('case', VECTORS['cases'], ids=lambda case: case['name'])
def test_pinned_native_reference_has_exact_bounded_manifest_api(case):
    assert zstandard.__version__ == VECTORS['version'] and zstandard.backend == 'cext'
    assert list(zstandard.ZSTD_VERSION) == VECTORS['zstd']
    frame = bytes.fromhex(case['frame_hex'])
    expected = case['result']
    try:
        output = zstandard.ZstdDecompressor(max_window_size=case['max_window_size_bytes']).decompress(
            frame, max_output_size=case['max_output_size'], allow_extra_data=False)
    except (zstandard.ZstdError, ValueError) as error:
        assert expected['accepted'] is False and type(error).__name__ == expected['error']
    else:
        assert expected['accepted'] is True and len(output) == expected['bytes']
        assert hashlib.sha256(output).hexdigest() == expected['sha256']
        parameters = zstandard.get_frame_parameters(frame)
        assert parameters.window_size <= case['max_window_size_bytes']
        # The pinned function returns signed -1 for unknown content size;
        # its separately exposed C constant is the unsigned UINT64_MAX.
        assert zstandard.CONTENTSIZE_UNKNOWN == 2**64 - 1
        assert zstandard.frame_content_size(frame) in (-1, len(output))
