"""Actual dependency resolution contracts with authored bytes; no game assets."""
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from backend import nte_assets, nte_toolchain as chain, runtime_bundle
from backend.preparation_errors import PreparationFailure
from backend.tests.test_prebuilt_readers import helper_fixture, digest


def fixture(tmp_path, monkeypatch):
    layout, _, _ = helper_fixture(tmp_path, 'nte')
    root = layout.resource_root / chain.PREFIX
    files = {name: ('authored ' + name).encode() for name in chain.DEPENDENCIES}
    pins = {name: digest(data) for name, data in files.items()}
    monkeypatch.setattr(chain, 'DEPENDENCIES', pins)
    monkeypatch.setattr(chain, 'host_platform', lambda: 'win-x64')
    files.update({'notices/UEEXTRACTOR-LICENSE.txt': b'authored notice',
                  'notices/DEPENDENCIES.md': b'authored dependency evidence'})
    manifest = {'schema': chain.SCHEMA, 'platform': 'win-x64',
                'files': {name: digest(data) for name, data in files.items()}}
    files['dependencies.json'] = json.dumps(manifest).encode()
    resources = dict(layout.resources)
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resources[chain.PREFIX + name] = digest(data)
    return replace(layout, resources=resources), root


def test_frozen_commands_use_verified_apphost_and_separate_native_dependencies(tmp_path, monkeypatch):
    layout, tools = fixture(tmp_path, monkeypatch)
    install = tmp_path / 'authored game'; install.mkdir()
    for mode in chain.MODES:
        for private in (layout.work_root, layout.cache_root, layout.data_root):
            output = private / 'authored task/output'
            command, env, cwd = chain.command(install, output, mode, layout=layout)
            assert command == [str(layout.resource_root / 'helpers/nte/NteReader.exe'), mode,
                               str(install), str(tools), str(output)]
            assert cwd == tools
            assert 'DOTNET_ROOT' not in env and 'DOTNET_STARTUP_HOOKS' not in env
            assert env['DOTNET_MULTILEVEL_LOOKUP'] == '0'


@pytest.mark.parametrize('change', ['missing', 'tampered', 'outer-missing', 'wrong-platform', 'extra', 'nested-code', 'approval-string'])
def test_dependency_closure_is_exact_and_cannot_be_forged_by_review_fields(tmp_path, monkeypatch, change):
    layout, root = fixture(tmp_path, monkeypatch)
    manifest = json.loads((root / 'dependencies.json').read_text())
    if change == 'missing':
        (root / 'zlib-ng2.dll').unlink()
    elif change == 'tampered':
        (root / 'oodle-data-shared.dll').write_bytes(b'changed')
    elif change == 'outer-missing':
        resources = dict(layout.resources); del resources[chain.PREFIX + 'UEExtractor.dll']
        layout = replace(layout, resources=resources)
    elif change == 'wrong-platform':
        monkeypatch.setattr(chain, 'host_platform', lambda: 'linux-x64')
    elif change == 'extra':
        (root / 'injected.dll').touch()
    else:
        name = 'notices/injected.dll' if change == 'nested-code' else 'oodle-data-shared.dll'
        data = b'not a reviewed library'
        (root / name).write_bytes(data)
        manifest['files'][name] = digest(data)
        manifest['rights_review'] = 'approved'
        (root / 'dependencies.json').write_text(json.dumps(manifest))
        resources = dict(layout.resources)
        resources[chain.PREFIX + name] = digest(data)
        resources[chain.PREFIX + 'dependencies.json'] = digest((root / 'dependencies.json').read_bytes())
        layout = replace(layout, resources=resources)
    with pytest.raises(PreparationFailure):
        chain.resolve(layout=layout)


@pytest.mark.parametrize('target', ['game', 'application', 'dependencies', 'outside', 'root'])
def test_game_runtime_and_unowned_outputs_are_rejected(tmp_path, monkeypatch, target):
    layout, tools = fixture(tmp_path, monkeypatch)
    install = tmp_path / 'game'; install.mkdir()
    destination = {'game': install / 'out', 'application': layout.application_root / 'out',
                   'dependencies': tools / 'out', 'outside': tmp_path / 'out', 'root': layout.work_root}[target]
    with pytest.raises(ValueError):
        chain.command(install, destination, 'index', layout=layout)


def test_normal_frozen_nte_adapter_never_calls_sdk_or_downloads_executables(tmp_path, monkeypatch):
    layout, tools = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(chain, 'discover_layout', lambda: layout)
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('No SDK discovery'))
    monkeypatch.setattr(nte_assets, 'download', lambda *_a, **_k: pytest.fail('No executable download'))
    monkeypatch.setattr(nte_assets, 'install_archive', lambda *_a, **_k: pytest.fail('No executable install'))
    monkeypatch.setattr(nte_assets, 'fingerprint', lambda *_: 'authored-stamp')
    monkeypatch.setattr(nte_assets, '_archive_metadata', lambda *_: 'private-authored-metadata')
    # Keep synthetic archive metadata out of even the test host's key store.
    metadata = tmp_path / 'already-cached'; metadata.touch()
    monkeypatch.setattr(nte_assets, '_metadata_path', lambda *_: metadata)
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs)); return SimpleNamespace(returncode=0)
    monkeypatch.setattr(nte_assets.subprocess, 'run', run)
    install = tmp_path / 'game'; install.mkdir()
    executable = nte_assets.ensure_extractor(layout.data_root / 'nte/tools')
    destination = layout.data_root / 'nte/temporary-index'
    for voice in ('Chinese', 'English', 'Japanese', 'Korean'):
        nte_assets.run_reader(install, executable, destination, 'index',
                              locales=['en', 'zh-CN', 'zh-Hant', 'ja', 'ko'], voice_language=voice)
    assert len(calls) == 4
    for args, kwargs in calls:
        assert args[0] == str(executable) and args[1] == 'index'
        assert kwargs['cwd'] == tools
        assert 'private-authored-metadata' not in str(args)
        assert json.loads(kwargs['input'])['archive_metadata'] == 'private-authored-metadata'
        assert kwargs['env']['DOTNET_MULTILEVEL_LOOKUP'] == '0'


def test_build_collector_rejects_duplicate_or_oversized_selected_members():
    path = Path(__file__).resolve().parents[2] / 'scripts/build-nte-toolchain.py'
    spec = importlib.util.spec_from_file_location('nte_build_test', path)
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('runtime.dll', b'first')
        with pytest.warns(UserWarning):
            container.writestr('runtime.dll', b'second')
    with pytest.raises(ValueError):
        builder.extract(archive.getvalue(), {'format': 'zip', 'member': 'runtime.dll'})
