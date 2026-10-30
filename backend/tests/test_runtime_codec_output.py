"""Disk output scope and Analysis boundary, not a Windows decode/build result."""
import json
from pathlib import Path
import runpy
import shutil
import sys
from types import SimpleNamespace

import pytest

from backend.preparation_errors import PreparationFailure
from backend.tests.test_prebuilt_codecs import fixture, seal, digest
from backend.tests.test_runtime_experiment import recorder


def codec_output(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    layout, home, manifest = fixture(tmp_path, monkeypatch)
    source = tmp_path / 'source'
    for name in manifest['source_inputs']:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'authored codec preparation source fixture')
    (source / 'package.json').write_text(json.dumps({'version': '0.0.1'}))
    manifest['source_inputs'] = {name: digest((source / name).read_bytes()) for name in manifest['source_inputs']}
    layout = seal(layout, home, manifest)
    resources = [{'path': name, 'sha256': checksum} for name, checksum in layout.resources.items()]
    value = {'profile': 'runtime-experiment', 'source_commit': layout.source_commit,
        'build_id': 'authored-codec-scope', 'resources': resources, 'components': []}
    output = tmp_path / 'candidate'
    target = output / 'ProxyTranscriptRuntime/_internal/codecs/xiph-flac'
    shutil.copytree(home, target)
    return module, value, source, layout.resource_root, output, target


def test_exact_native_codec_output_is_accepted_after_existing_pe_notice_source_verification(tmp_path, monkeypatch):
    _module, value, source, evidence, output, _target = codec_output(tmp_path, monkeypatch)
    from closure import validate_codec_output
    validate_codec_output(value, source, evidence, output)
    (evidence / 'codecs/xiph-flac/notices/COPYING.GPL').write_bytes(b'changed required notice')
    with pytest.raises(PreparationFailure): validate_codec_output(value, source, evidence, output)


@pytest.mark.parametrize('name', ['ProxyTranscriptRuntime/_internal/FLAC.dll',
    'ProxyTranscriptRuntime/flac.exe', 'ProxyTranscriptAsr/_internal/FLAC.dll',
    'unrelated/FlAc.DlL'])
def test_extra_codec_basename_is_rejected_even_when_byte_identical_and_is_preserved(tmp_path, monkeypatch, name):
    _module, value, source, evidence, output, target = codec_output(tmp_path, monkeypatch)
    from closure import ClosureError, write_candidate
    extra = output / name; extra.parent.mkdir(parents=True, exist_ok=True)
    data = (target / ('flac.exe' if extra.suffix == '.exe' else 'FLAC.dll')).read_bytes()
    extra.write_bytes(data)
    with pytest.raises(ClosureError, match='extra or misplaced'): write_candidate(value, source, evidence, output)
    assert extra.read_bytes() == data, 'A failing output gate must not silently delete the unwanted file'
    assert not (output / 'CANDIDATE-PROVENANCE.json').exists()
    assert not (output / 'RUNTIME-INVENTORY.json').exists()
    assert not (output / 'ProxyTranscriptRuntime/_internal/runtime-manifest.json').exists()


@pytest.mark.parametrize('change', ['missing', 'modified', 'case-changed'])
def test_expected_codec_output_requires_exact_path_and_native_bytes(tmp_path, monkeypatch, change):
    _module, value, source, evidence, output, target = codec_output(tmp_path, monkeypatch)
    from closure import ClosureError, validate_codec_output
    path = target / 'FLAC.dll'
    if change == 'missing': path.unlink()
    elif change == 'modified': path.write_bytes(b'wrong native image')
    else: path.rename(target / 'FlAc.DlL')
    with pytest.raises(ClosureError): validate_codec_output(value, source, evidence, output)


def test_spec_keeps_verified_codec_pe_files_outside_analysis_then_delivers_explicit_data(tmp_path, monkeypatch):
    _module, value, _source, evidence, _output, _target = codec_output(tmp_path, monkeypatch)
    repository = Path(__file__).resolve().parents[2]
    inputs = tmp_path / 'inputs.json'; inputs.write_text(json.dumps(value))
    monkeypatch.setenv('PROXY_RUNTIME_BUILD_INPUTS', str(inputs))
    monkeypatch.setenv('PROXY_RUNTIME_EVIDENCE_ROOT', str(evidence))
    hooks = SimpleNamespace(collect_data_files=lambda *_a, **_k: [], collect_dynamic_libs=lambda *_a, **_k: [],
        collect_submodules=lambda *_a, **_k: [], copy_metadata=lambda *_a, **_k: [])
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils.hooks', hooks)
    analyses = []
    def analysis(_scripts, *, datas, binaries, **_kwargs):
        analyses.append([*datas, *binaries])
        return SimpleNamespace(pure=[], scripts=[], binaries=list(binaries),
            datas=[(str(Path(destination) / Path(origin).name), origin, 'DATA') for origin, destination in datas])
    result = runpy.run_path(str(repository / 'packaging/runtime-bundle/runtime.spec'), init_globals={
        'SPECPATH': str(repository / 'packaging/runtime-bundle'), 'Analysis': analysis,
        'PYZ': lambda *_a, **_k: None, 'EXE': lambda *_a, **_k: None, 'COLLECT': lambda *_a, **_k: None})
    assert len(analyses) == 2
    assert not any(Path(origin).name.casefold() in {'flac.exe', 'flac.dll'} for rows in analyses for origin, _ in rows)
    actual = {name.replace('\\', '/'): (origin, kind) for name, origin, kind in result['main'].datas}
    for name in ('flac.exe', 'FLAC.dll'):
        member = 'codecs/xiph-flac/' + name
        assert actual[member] == (str(evidence / member), 'DATA')
    assert 'codecs/xiph-flac/notices/COPYING.GPL' in actual
