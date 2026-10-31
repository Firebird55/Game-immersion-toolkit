"""Supplier replay accepts only exact, bounded native packaging transformations."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('macos_replay', ROOT / 'packaging/runtime-bundle/macos_replay.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
spec = importlib.util.spec_from_file_location('replay_review', ROOT / 'scripts/review-desktop-inputs.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.mark.parametrize('name', ['../lib.dylib', '_internal/../lib.dylib',
    '/_internal/lib.dylib', '_internal//lib.dylib', '_internal/./lib.dylib',
    '_internal\\lib.dylib', '_internal/C:lib.dylib', 'other/_internal/lib.dylib', '_internal'])
def test_replay_destination_cannot_escape_or_reinterpret(name):
    with pytest.raises(ValueError):
        replay.collected_destination(name)


def test_collected_destination_preserves_actual_library_depth():
    assert replay.collected_destination('_internal/PySide6/Qt/lib/QtCore') == 'PySide6/Qt/lib/QtCore'
    assert replay.collected_destination('asr/_internal/sherpa_onnx/lib/libonnxruntime.dylib') == 'sherpa_onnx/lib/libonnxruntime.dylib'


def test_foreign_host_cannot_claim_native_replay(monkeypatch):
    monkeypatch.setattr(replay.sys, 'platform', 'win32')
    with pytest.raises(ValueError, match='native build host'):
        replay.replay(b'\xcf\xfa\xed\xfe', '_internal/libfixture.dylib', 'macos-arm64')


def test_replay_tool_source_and_version_are_bound(tmp_path, monkeypatch):
    root = tmp_path / 'fixture'
    root.mkdir()
    path = root / 'fixture.py'
    path.write_bytes(b'# authored tool source\n')
    value = {'version': '1.0', 'sha256': '1'*64,
             'files': {'fixture.py': hashlib.sha256(path.read_bytes()).hexdigest()}}
    distribution = SimpleNamespace(version='1.0', locate_file=lambda member: root / member)
    monkeypatch.setattr(replay, 'TOOL_PACKAGES', ('fixture',))
    monkeypatch.setattr(replay.importlib.metadata, 'distribution', lambda name: distribution)
    assert replay.verify_toolchain({'fixture': value})['fixture']['source_files_verified'] == 1
    path.write_bytes(b'# substituted source\n')
    with pytest.raises(ValueError, match='source differs'):
        replay.verify_toolchain({'fixture': value})
    distribution.version = '2.0'
    with pytest.raises(ValueError, match='version differs'):
        replay.verify_toolchain({'fixture': value})


def test_member_recheck_detects_replaced_archive_without_extracting(tmp_path):
    archive = tmp_path / 'supplier.zip'
    data = b'\xcf\xfa\xed\xfeauthored fixture'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('libfixture.dylib', data)
    supplier = {'archive': archive, 'member': 'libfixture.dylib', 'sha256': review.sha(data)}
    assert review.supplier_member(supplier) == data
    supplier['member'] = '../libfixture.dylib'
    with pytest.raises((ValueError, RuntimeError)):
        review.supplier_member(supplier)
    supplier['member'] = 'libfixture.dylib'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('libfixture.dylib', data + b'changed')
    with pytest.raises(ValueError, match='changed'):
        review.supplier_member(supplier)


def test_reviewer_requires_exact_output_bytes_and_records_supplier(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    (root / '_internal').mkdir(parents=True)
    data = b'\xcf\xfa\xed\xfeauthored delivered fixture'
    path = root / '_internal/libfixture.dylib'
    path.write_bytes(data)
    expected = review.sha(data)
    receipt = {'files': [{'path': '_internal/libfixture.dylib', 'bytes': len(data), 'sha256': expected}]}
    value = review.Review(root, receipt, 'macos-arm64')
    value.macho_supplier(tmp_path / 'supplier.zip', 'libfixture.dylib', 'a'*64, 'exact supplier fixture')
    monkeypatch.setattr(review, 'verify_toolchain', lambda wheels: {'fixture': 'verified'})
    monkeypatch.setattr(review, 'supplier_member', lambda supplier: b'\xcf\xfa\xed\xfesource fixture')
    monkeypatch.setattr(review, 'replay_macho', lambda *args: 'b'*64)
    value.macos_postprocessing()
    assert expected not in value.origins
    assert value.checks['native_inputs']['blockers'][0]['code'] == 'macos-replay-mismatch'
    value.checks['native_inputs']['blockers'].clear()
    monkeypatch.setattr(review, 'replay_macho', lambda *args: expected)
    value.macos_postprocessing()
    assert expected in value.origins
    assert not value.checks['native_inputs']['blockers']
    assert value.checks['native_inputs']['evidence'][-1]['matched'][0]['supplier_sha256'] == 'a'*64


@pytest.mark.skipif(sys.platform != 'darwin', reason='actual Apple linker and signing tools required')
def test_native_macos_replay_reproduces_actual_collected_dylib(tmp_path):
    from PyInstaller.building.utils import process_collected_binary
    from PyInstaller.config import CONF
    import platform

    source = tmp_path / 'fixture.c'
    source.write_text('int fixture_value(void) { return 42; }\n')
    dylib = tmp_path / 'libfixture.dylib'
    subprocess.run(['/usr/bin/cc', '-dynamiclib', str(source), '-o', str(dylib),
        '-Wl,-headerpad_max_install_names', '-Wl,-install_name,/authored/libfixture.dylib'], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    architecture = 'arm64' if platform.machine() == 'arm64' else 'x86_64'
    original = dict(CONF)
    try:
        CONF['cachedir'] = str(tmp_path / 'builder-cache')
        CONF['upx_dir'] = None
        built = Path(process_collected_binary(str(dylib), 'nested/libfixture.dylib',
            target_arch=architecture, strict_arch_validation=True))
        target = 'macos-arm64' if architecture == 'arm64' else 'macos-x64'
        assert replay.replay(dylib.read_bytes(), '_internal/nested/libfixture.dylib', target) == review.digest(built)
        assert replay.replay(dylib.read_bytes(), '_internal/nested/libfixture.dylib', target) != review.sha(built.read_bytes() + b'changed')
    finally:
        CONF.clear()
        CONF.update(original)
