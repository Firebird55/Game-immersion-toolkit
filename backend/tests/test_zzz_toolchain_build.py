"""Owned build recipe behavior; supplier/native acceptance is a separate probe."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('zzz_builder', ROOT / 'scripts/build-zzz-toolchain.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_transpile_uses_explicit_compiler_and_relocates_only_known_imports(tmp_path):
    node = shutil.which('node')
    compiler = ROOT / 'node_modules/typescript/lib/typescript.js'
    if not node or not compiler.is_file():
        pytest.skip('Build recipe test needs developer Node and the locked compiler')
    source = b"""import {decompress} from 'ooz-wasm';
import xxhash from 'xxhash-wasm';
const unpackMhyFile = (value: Uint8Array): Uint8Array => value;
export const selected = [decompress, xxhash];
"""
    first = builder.transpile(source, compiler, Path(node), tmp_path / 'first')
    second = builder.transpile(source, compiler, Path(node), tmp_path / 'second')
    assert first == second
    assert b"from '../dependencies/ooz/index.js'" in first
    assert b"from '../dependencies/xxhash/esm/xxhash-wasm.js'" in first
    assert b'export { unpackMhyFile };' in first
    assert b': Uint8Array' not in first
    assert not list(tmp_path.rglob('node_modules'))
    with pytest.raises(ValueError, match='transpilation failed'):
        builder.transpile(b'const unpackMhyFile = () => {};', compiler, Path(node), tmp_path / 'missing-imports')


def test_build_rejects_ambient_or_replaced_node_before_acquisition(tmp_path, monkeypatch):
    binary = tmp_path / 'node.exe'; binary.write_bytes(b'authored executable fixture')
    runtime = {'schema': 'toolkit-node-runtime-v1', 'platform': 'win-x64', 'version': builder.NODE_VERSION,
               'executable': 'node.exe', 'archive_sha256': builder.ARCHIVES['win-x64'][1],
               'executable_sha256': builder.digest(binary.read_bytes())}
    (tmp_path / 'runtime.json').write_text(json.dumps(runtime))
    monkeypatch.setattr(builder, 'host_platform', lambda: 'win-x64')
    assert builder.verified_node(binary) == binary
    binary.write_bytes(b'replaced')
    monkeypatch.setattr(builder.zzz_inputs, 'acquire_inputs', lambda *_a, **_k: pytest.fail('No acquisition'))
    with pytest.raises(ValueError, match='already collected'):
        builder.build(tmp_path / 'output', tmp_path / 'evidence', 'win-x64', binary)
    assert not (tmp_path / 'output').exists() and not (tmp_path / 'evidence').exists()


def test_build_keeps_immutable_output_separate_from_evidence(tmp_path):
    with pytest.raises(ValueError, match='separate folders'):
        builder.build(tmp_path / 'output', tmp_path / 'output/evidence', 'win-x64', tmp_path / 'node')
