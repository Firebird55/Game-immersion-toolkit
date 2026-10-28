"""Synthetic closure failures, not native Node/game acceptance evidence."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import prebuilt_node_reader as reader
from backend.preparation_errors import PreparationFailure
from backend.tests.test_runtime_bundle import frozen_layout


def fixture(tmp_path, monkeypatch):
    layout = frozen_layout(tmp_path)
    root = layout.resource_root / reader.PREFIX
    (root / 'runtime').mkdir(parents=True)
    binary = bytearray(128)
    binary[:2] = b'MZ'
    binary[60:64] = (64).to_bytes(4, 'little')
    binary[64:70] = b'PE\0\0\x64\x86'
    digest = hashlib.sha256(binary).hexdigest()
    monkeypatch.setattr(reader, 'EXECUTABLE_SHA256', digest)
    for name in reader.FILES:
        (root / name).write_bytes(binary if name == 'runtime/node.exe' else b'authored synthetic resource')
    files = {name: {'bytes': (root / name).stat().st_size,
                    'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest()} for name in reader.FILES}
    value = {'schema': reader.SCHEMA, 'kind': 'authored-probe', 'purpose': 'authored-probe-only',
             'platform': 'win-x64', 'source_commit': layout.source_commit, 'source_dirty': False, 'entry': 'probe.mjs',
             'executable': 'runtime/node.exe', 'game_execution_allowed': False, 'files': files,
             'runtime': {'version': reader.VERSION, 'archive_sha256': reader.ARCHIVE_SHA256,
                         'executable_sha256': digest, 'license_sha256': files['runtime/LICENSE']['sha256']},
             'source_inputs': {'LICENSE': files['LICENSE']['sha256'], **{'packaging/zzz-reader/' + name: files[name]['sha256'] if name in files else 'd' * 64
                 for name in ('probe.mjs', 'probe-worker.mjs', 'sum.wat', 'sum.wasm.hex', 'NOTICE.md')}}}
    return layout, root, value


def seal(layout, root, value):
    value['build_id'] = hashlib.sha256(json.dumps(value['files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    (root / 'helper-manifest.json').write_text(json.dumps(value), encoding='utf-8')
    return replace(layout, resources={reader.PREFIX + path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in root.rglob('*') if path.is_file()})


def test_game_receipts_cannot_authorize_zzz_even_with_approval_strings():
    for kind in ('voice-links', 'cinematic-links', 'zzz', 'probe', '../probe'):
        with pytest.raises(PreparationFailure, match='corresponding-source'):
            reader.prebuilt_node_reader(kind, layout=SimpleNamespace(rights='approved', profile='full'))


def test_valid_probe_has_fixed_command_private_work_and_no_loader_environment(tmp_path, monkeypatch):
    layout, root, value = fixture(tmp_path, monkeypatch)
    helper = reader.prebuilt_node_reader('authored-probe', layout=seal(layout, root, value))
    work = layout.work_root / 'synthetic'
    work.mkdir(parents=True)
    input_path, output = work / 'input.json', work / 'result.json'
    input_path.write_text('{}')
    command = helper.command(work=work, input_path=input_path, output_path=output)
    assert command[:3] == [str(root / 'runtime/node.exe'), str(root / 'probe.mjs'), '--probe']
    assert helper.environment({'SystemRoot': 'Windows', 'PATH': 'developer', 'NODE_OPTIONS': '--import=bad',
                               'NODE_PATH': 'bad', 'NODE_COMPILE_CACHE': 'bad', 'HOME': 'private', 'NPM_CONFIG_USERCONFIG': 'private'}) == {'PATH': '', 'SystemRoot': 'Windows'}
    assert not output.exists()
    with pytest.raises(PreparationFailure, match='fresh owned'):
        helper.command(work=work, input_path=input_path, output_path=tmp_path / 'outside.json')
    with pytest.raises(PreparationFailure, match='traversal or aliases'):
        helper.command(work=work / '..' / 'synthetic', input_path=input_path, output_path=output)
    with pytest.raises(PreparationFailure, match='traversal or aliases'):
        helper.command(work=layout.work_root / 'child/../../outside', input_path=input_path, output_path=output)
    with pytest.raises(PreparationFailure, match='portable plain'):
        helper.command(work=work, input_path=input_path, output_path=work / 'result:stream')
    (work / 'result.json.pending').write_text('previous')
    with pytest.raises(PreparationFailure, match='fresh owned'):
        helper.command(work=work, input_path=input_path, output_path=output)


@pytest.mark.parametrize('change', ['missing-license', 'extra-directory', 'extra-file', 'unbound-manifest',
                                   'wrong-entry', 'wrong-runtime', 'wrong-build-id', 'game-approved', 'tampered-worker', 'not-pe'])
def test_incomplete_or_changed_probe_fails_before_any_command(tmp_path, monkeypatch, change):
    layout, root, value = fixture(tmp_path, monkeypatch)
    if change == 'missing-license':
        (root / 'runtime/LICENSE').unlink(); del value['files']['runtime/LICENSE']
    elif change == 'extra-directory': (root / 'hidden-empty').mkdir()
    elif change == 'extra-file': (root / 'game.db').write_bytes(b'not shipped')
    elif change == 'wrong-entry': value['entry'] = 'node_modules/typescript/lib/tsc.js'
    elif change == 'wrong-runtime': value['runtime']['version'] = '24'
    elif change == 'game-approved': value['game_execution_allowed'] = True
    elif change == 'not-pe':
        (root / 'runtime/node.exe').write_bytes(b'not a Windows executable')
        digest = hashlib.sha256((root / 'runtime/node.exe').read_bytes()).hexdigest()
        monkeypatch.setattr(reader, 'EXECUTABLE_SHA256', digest)
        value['runtime']['executable_sha256'] = digest
        value['files']['runtime/node.exe'] = {'bytes': 24, 'sha256': digest}
    layout = seal(layout, root, value)
    if change == 'unbound-manifest': layout = replace(layout, resources={})
    elif change == 'tampered-worker': (root / 'probe-worker.mjs').write_text('changed')
    elif change == 'wrong-build-id':
        value['build_id'] = 'f' * 64
        (root / 'helper-manifest.json').write_text(json.dumps(value))
        layout = replace(layout, resources={**layout.resources, reader.PREFIX + 'helper-manifest.json': hashlib.sha256((root / 'helper-manifest.json').read_bytes()).hexdigest()})
    with pytest.raises(PreparationFailure, match='missing or incompatible'):
        reader.prebuilt_node_reader('authored-probe', layout=layout)


def test_unlisted_link_is_rejected_even_when_target_is_otherwise_allowlisted(tmp_path, monkeypatch):
    layout, root, value = fixture(tmp_path, monkeypatch)
    layout = seal(layout, root, value)
    (root / 'extra-link').symlink_to(root / 'probe.mjs')
    with pytest.raises(PreparationFailure, match='missing or incompatible'):
        reader.prebuilt_node_reader('authored-probe', layout=layout)


def test_frozen_zzz_dispatch_stops_before_path_probe_or_metadata_download(tmp_path, monkeypatch):
    from backend import zzz_assets, runtime_bundle
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    monkeypatch.setattr(reader, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    monkeypatch.setattr(zzz_assets.game_tools, 'refresh_zzz_metadata', lambda *args, **kwargs: pytest.fail('Unexpected download'))
    monkeypatch.setattr(zzz_assets.shutil, 'which', lambda *args: pytest.fail('Unexpected PATH discovery'))
    with pytest.raises(PreparationFailure, match='corresponding-source'):
        zzz_assets._links(tmp_path / 'absent-game', tmp_path / 'absent-data', 'revision', lambda _: None)
    assert list(tmp_path.iterdir()) == []
