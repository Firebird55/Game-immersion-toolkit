"""Probe fixture structure and failure checks; actual apphost runs in native CI."""
import importlib.util
import json
from pathlib import Path

import pytest

from backend.spyro_unreal import PakSet
from backend.tests.test_nte_toolchain import fixture as chain_fixture
from backend.tests.test_prebuilt_readers import digest, save


def module():
    path = Path(__file__).resolve().parents[2] / 'scripts/probe-native-unreal.py'
    spec = importlib.util.spec_from_file_location('native_unreal_probe', path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def test_authored_compressed_archive_is_readable_by_independent_format_reader(tmp_path):
    probe = module()
    members = {'Client/Content/Aki/ConfigDB/db_plot_audio.db': b'Authored table bytes' * 100,
               probe.WUWA_PREFIX + 'en_owned.wem': probe.authored_wave()}
    probe.authored_pak(tmp_path / 'Falcon/Content/Paks/pakchunk0.pak', members)
    archives = PakSet(tmp_path)
    for name, data in members.items():
        assert archives.read(name) == data


def source_fixture(tmp_path, monkeypatch, probe):
    layout, tools = chain_fixture(tmp_path, monkeypatch)
    helper = layout.resource_root / 'helpers/nte'
    manifest = json.loads((helper / 'helper-manifest.json').read_text())
    source = tmp_path / 'source'
    names = set(manifest['source_inputs']) | probe.RESOURCE_SOURCES
    for name in names:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'authored source')
    monkeypatch.setattr(probe, 'ROOT', source)
    monkeypatch.setattr(probe, 'host_platform', lambda: 'win-x64')
    monkeypatch.setattr(probe.subprocess, 'check_output', lambda command, **kw: '' if command[1] == 'status' else 'a' * 40)
    manifest['source_inputs'] = {name: digest((source / name).read_bytes()) for name in manifest['source_inputs']}
    receipt = json.loads((helper / 'build-receipt.json').read_text()); receipt['source_inputs'] = manifest['source_inputs']
    data = json.dumps(receipt).encode(); (helper / 'build-receipt.json').write_bytes(data)
    manifest['files']['build-receipt.json'] = {'bytes': len(data), 'sha256': digest(data)}
    save(layout, helper, manifest)
    # The collector's full managed-component notice is required by public evidence.
    data = b'authored managed component lock'
    name = 'notices/MANAGED-COMPONENTS.json'; (tools / name).write_bytes(data)
    dependency_manifest = json.loads((tools / 'dependencies.json').read_text())
    dependency_manifest['files'][name] = digest(data)
    (tools / 'dependencies.json').write_text(json.dumps(dependency_manifest))
    receipt = {'schema': 'toolkit-native-resources-v1', 'platform': 'win-x64',
        'source_commit': 'a' * 40, 'source_dirty': False,
        'source_inputs': {name: digest((source / name).read_bytes()) for name in probe.RESOURCE_SOURCES},
        'files': [{'path': p.relative_to(layout.resource_root).as_posix(), 'bytes': p.stat().st_size,
                   'sha256': digest(p.read_bytes())} for p in tools.rglob('*') if p.is_file()]}
    (layout.resource_root / 'resource-manifest.json').write_text(json.dumps(receipt))
    return helper, layout.resource_root, source


def test_probe_reuses_exact_runtime_receipts_and_dependency_closure(tmp_path, monkeypatch):
    probe = module(); helper, resources, _ = source_fixture(tmp_path, monkeypatch, probe)
    layout, reader, identities = probe._layout(helper, resources, tmp_path / 'probe')
    assert reader.executable.name == 'NteReader.exe'
    assert layout.source_commit == 'a' * 40
    assert set(identities) == {'helper_manifest_sha256', 'resource_manifest_sha256', 'managed_components_sha256'}


@pytest.mark.parametrize('fault', ['dirty', 'commit', 'source', 'dependency-bytes', 'checkout-dirty'])
def test_probe_rejects_stale_or_changed_collection_evidence_before_execution(tmp_path, monkeypatch, fault):
    probe = module(); helper, resources, source = source_fixture(tmp_path, monkeypatch, probe)
    path = resources / 'resource-manifest.json'
    receipt = json.loads(path.read_text())
    if fault == 'dirty': receipt['source_dirty'] = True
    elif fault == 'commit': receipt['source_commit'] = 'b' * 40
    elif fault == 'source': (source / 'scripts/build-nte-toolchain.py').write_bytes(b'changed')
    elif fault == 'checkout-dirty':
        monkeypatch.setattr(probe.subprocess, 'check_output', lambda command, **kw: ' M changed' if command[1] == 'status' else 'a' * 40)
    else: (resources / 'toolchains/nte/UEExtractor.dll').write_bytes(b'changed')
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError): probe._layout(helper, resources, tmp_path / 'probe')


@pytest.mark.parametrize('fault', [None, 'runtime', 'payload'])
def test_native_probe_asserts_child_results_and_authored_bytes(tmp_path, monkeypatch, fault):
    probe = module(); helper, resources, _ = source_fixture(tmp_path, monkeypatch, probe)
    layout, reader, _ = probe._layout(helper, resources, tmp_path / 'probe')
    def execute(command, request, env, cwd, *, reject=False):
        if command[-1] == '--runtime-identity':
            return json.dumps({'schema': 'proxy-nte-runtime-identity-v1', 'runtime_version': probe.RUNTIME,
                'runtime_origin': 'external' if fault == 'runtime' else 'app-local', 'game_execution_approved': False,
                'corelib_sha256': reader.manifest['files']['System.Private.CoreLib.dll']['sha256']}).encode()
        assert 'DOTNET_ROOT' not in env and 'DOTNET_STARTUP_HOOKS' not in env
        if reject: return b'expected fixed rejection'
        mode, output = command[1], Path(command[-1]); output.mkdir(parents=True)
        voice = probe.authored_wave()
        if mode == 'inventory':
            (output / 'inventory.json').write_text(json.dumps([f'HT/Content/WwiseAudio/Media/{l}/42.wem' for l in probe.VOICE_LOCALES]))
        elif mode == 'voice': (output / 'voice.wem').write_bytes(b'changed' if fault == 'payload' else voice)
        elif mode == 'wuwa-list':
            (output / 'files.json').write_text(json.dumps([probe.WUWA_PREFIX + p + '_owned.wem' for p in probe.VOICE_LOCALES.values()]))
        else:
            name = probe.CONFIG_PATH if request['filter'] == 'ConfigDB/db_plot_audio.db' else request['filter']
            value = b'Authored toolkit configuration extraction fixture.\n' * 16 if name == probe.CONFIG_PATH else voice
            path = output / name; path.parent.mkdir(parents=True); path.write_bytes(value)
            (output / 'files.json').write_text(json.dumps([name]))
        return b'Game reader completed'
    monkeypatch.setattr(probe, '_execute', execute)
    if fault:
        with pytest.raises(ValueError): probe.run_checks(layout, reader, tmp_path / 'probe')
    else:
        checks = probe.run_checks(layout, reader, tmp_path / 'probe')
        assert len(checks) == 7 and all(checks.values())
