"""Fixed app-local grammar dispatch and build-input integrity contracts."""
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

from backend import node_tools
from backend.preparation_errors import PreparationFailure
from backend.tests.test_runtime_bundle import frozen_layout


def owned_layout(tmp_path, monkeypatch):
    layout = frozen_layout(tmp_path)
    monkeypatch.setattr(node_tools, 'host_platform', lambda: 'win-x64')
    manifest = {'schema': 'toolkit-node-runtime-v1', 'platform': 'win-x64', 'version': node_tools.NODE_VERSION,
                'executable': 'node.exe', 'archive_sha256': node_tools.ARCHIVES['win-x64'][1],
                'executable_sha256': hashlib.sha256(b'owned binary').hexdigest()}
    files = {'toolchains/node/node.exe': b'owned binary', 'toolchains/node/LICENSE': b'owned notice',
             'toolchains/node/runtime.json': json.dumps(manifest).encode(), node_tools.ENTRY: b'owned fixed operation',
             'backend/node_modules/acorn/LICENSE': b'owned fixture license',
             'backend/node_modules/acorn/dist/acorn.js': b'owned fixture parser',
             'backend/node_modules/acorn/package.json': json.dumps({'name': 'acorn', 'version': node_tools.ACORN_VERSION}).encode()}
    for name, data in files.items():
        path = layout.resource_root / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return replace(layout, resources={name: hashlib.sha256(data).hexdigest() for name, data in files.items()})


def test_frozen_grammar_uses_verified_runtime_entry_and_no_global_loader(tmp_path, monkeypatch):
    layout = owned_layout(tmp_path, monkeypatch)
    monkeypatch.setattr(node_tools.shutil, 'which', lambda _: pytest.fail('system Node lookup'))
    monkeypatch.setenv('NODE_OPTIONS', '--import=untrusted')
    monkeypatch.setenv('NODE_PATH', 'untrusted')
    monkeypatch.setenv('NPM_CONFIG_USERCONFIG', 'private')
    command, env = node_tools.grammar_command(tmp_path / 'game.asar', tmp_path / 'catalog.json', layout=layout)
    assert command == [str(layout.resource_root / 'toolchains/node/node.exe'), str(layout.resource_root / node_tools.ENTRY),
                       str(tmp_path / 'game.asar'), str(tmp_path / 'catalog.json')]
    assert env['PATH'] == ''
    assert not {'NODE_OPTIONS', 'NODE_PATH', 'NPM_CONFIG_USERCONFIG'} & env.keys()


@pytest.mark.parametrize('name', ['toolchains/node/node.exe', 'toolchains/node/LICENSE', 'toolchains/node/runtime.json',
                                node_tools.ENTRY, 'backend/node_modules/acorn/package.json',
                                'backend/node_modules/acorn/LICENSE', 'backend/node_modules/acorn/dist/acorn.js'])
def test_missing_or_changed_resource_cannot_fall_back_to_global_tools(tmp_path, monkeypatch, name):
    layout = owned_layout(tmp_path, monkeypatch)
    monkeypatch.setattr(node_tools.shutil, 'which', lambda _: pytest.fail('system Node lookup'))
    path = layout.resource_root / name
    path.write_bytes(b'changed')
    with pytest.raises(PreparationFailure, match='Repair the application'):
        node_tools.grammar_command(tmp_path / 'game.asar', tmp_path / 'catalog', layout=layout)
    path.unlink()
    with pytest.raises(PreparationFailure):
        node_tools.grammar_command(tmp_path / 'game.asar', tmp_path / 'catalog', layout=layout)


def test_wrong_platform_cannot_run_even_if_resources_are_unchanged(tmp_path, monkeypatch):
    layout = owned_layout(tmp_path, monkeypatch)
    monkeypatch.setattr(node_tools, 'host_platform', lambda: 'darwin-arm64')
    with pytest.raises(PreparationFailure):
        node_tools.grammar_command(tmp_path / 'game.asar', tmp_path / 'catalog', layout=layout)


def test_build_archive_reader_only_reads_requested_regular_members():
    spec = importlib.util.spec_from_file_location('node_builder', Path(__file__).resolve().parents[2] / 'scripts/build-node-toolchain.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    for linked in (False, True):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            member = tarfile.TarInfo('owned/node')
            if linked:
                member.type = tarfile.SYMTYPE; member.linkname = '../../outside'
                archive.addfile(member)
            else:
                member.size = 6; archive.addfile(member, io.BytesIO(b'binary'))
            unused = tarfile.TarInfo('unselected/tool'); unused.size = 6
            archive.addfile(unused, io.BytesIO(b'unused'))
        if linked:
            with pytest.raises(ValueError, match='Unsafe'):
                builder.selected_members(data.getvalue(), {'owned/node'})
        else:
            assert builder.selected_members(data.getvalue(), {'owned/node'}) == {'owned/node': b'binary'}
            with pytest.raises(ValueError, match='missing'):
                builder.selected_members(data.getvalue(), {'missing'})
