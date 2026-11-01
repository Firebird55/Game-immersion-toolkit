"""Authored resource failures and frozen dispatch, not installed-game evidence."""
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import game_tools, node_tools, prebuilt_node_reader as reader
from backend.preparation_errors import PreparationFailure
from backend.tests.test_runtime_bundle import frozen_layout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path, monkeypatch, target='win-x64'):
    layout = frozen_layout(tmp_path, profile='runtime')
    root = layout.resource_root / reader.ZZZ_PREFIX
    files = {'upstream/galgame-perform.ts': b'authored source', 'upstream/galgame-perform.mjs': b'authored compiled reader',
             'upstream/LICENSE': b'authored terms', 'inputs.json': b'{}', 'BUILD-RECIPE.json': b'{}',
             'TOOLKIT-LICENSE': b'authored terms', **{'scripts/' + name: b'authored script' for name in reader.ZZZ_SCRIPTS},
             **{'dependencies/' + name: b'authored dependency' for name in reader.ZZZ_DEPENDENCIES}}
    monkeypatch.setattr(game_tools, 'READER_SHA', digest(files['upstream/galgame-perform.ts']))
    monkeypatch.setattr(reader, 'ZZZ_DEPENDENCIES', {name: digest(b'authored dependency') for name in reader.ZZZ_DEPENDENCIES})
    monkeypatch.setattr(node_tools, 'host_platform', lambda: target)
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    executable = 'node.exe' if target.startswith('win-') else 'node'
    node = layout.resource_root / 'toolchains/node'
    node.mkdir()
    (node / executable).write_bytes(b'authored non-executable node fixture')
    (node / 'LICENSE').write_bytes(b'authored node terms')
    (node / 'runtime.json').write_text(json.dumps({'schema': 'toolkit-node-runtime-v1', 'platform': target,
        'version': node_tools.NODE_VERSION, 'executable': executable, 'archive_sha256': node_tools.ARCHIVES[target][1],
        'executable_sha256': digest((node / executable).read_bytes())}))
    value = {'schema': reader.ZZZ_SCHEMA, 'platform': target, 'source_commit': layout.source_commit, 'source_dirty': False,
             'upstream_revision': game_tools.READER_REVISION, 'upstream_sha256': game_tools.READER_SHA,
             'inputs_sha256': digest(files['inputs.json']),
             'files': {name: {'bytes': len(data), 'sha256': digest(data)} for name, data in files.items()}}
    return layout, root, value


def seal(layout, root, value):
    value['build_id'] = digest(json.dumps(value['files'], sort_keys=True, separators=(',', ':')).encode())
    (root / 'runtime.json').write_text(json.dumps(value))
    return replace(layout, resources={path.relative_to(layout.resource_root).as_posix(): digest(path.read_bytes())
        for path in layout.resource_root.rglob('*') if path.is_file()})


@pytest.mark.parametrize('target', ['win-x64', 'linux-x64', 'darwin-arm64'])
def test_fixed_scene_commands_require_verified_resources_and_owned_work(tmp_path, monkeypatch, target):
    layout, root, value = fixture(tmp_path, monkeypatch, target)
    helper = reader.production_zzz_reader(layout=seal(layout, root, value))
    work, game = layout.work_root / 'zzz-scenes', tmp_path / 'Game 空格'
    work.mkdir(parents=True); game.mkdir()
    for mode in ('dialogue', 'comic', 'cinematic'):
        command = helper.command(mode, game_data=game, work=work)
        assert command[0] == str(helper.executable)
        assert command[-1] == str(root / 'upstream/galgame-perform.mjs')
        assert command[2:4] == [str(game), str(work)]
        assert 'node_modules' not in ' '.join(command) and 'typescript' not in ' '.join(command)
        if mode != 'cinematic':
            assert command[4:6] == [mode, 'language-links-' + mode + '.json']
    assert helper.environment({'NODE_OPTIONS': '--import malware', 'NODE_PATH': 'bad', 'PATH': 'bad'}) == {'PATH': ''}
    with pytest.raises(PreparationFailure, match='Unsupported'):
        helper.command('arbitrary.mjs', game_data=game, work=work)
    with pytest.raises(PreparationFailure, match='separate private'):
        helper.command('comic', game_data=game, work=game)
    with pytest.raises(PreparationFailure, match='normalized'):
        helper.command('comic', game_data=game, work=work / '..' / 'zzz-scenes')


@pytest.mark.parametrize('change', ['missing-license', 'extra-file', 'extra-dir', 'wrong-source', 'dirty-source',
    'wrong-upstream', 'wrong-platform', 'wrong-node', 'tampered-script', 'unbound-manifest', 'wrong-build',
    'arbitrary-code', 'changed-dependency', 'probe-profile', 'wrong-inputs'])
def test_invalid_production_resources_never_authorize_game_commands(tmp_path, monkeypatch, change):
    layout, root, value = fixture(tmp_path, monkeypatch)
    if change == 'missing-license': del value['files']['dependencies/ooz/LICENSE']
    elif change == 'extra-file': (root / 'unbound.js').write_bytes(b'no')
    elif change == 'extra-dir': (root / 'empty-hidden').mkdir()
    elif change == 'wrong-source': value['source_commit'] = 'b' * 40
    elif change == 'dirty-source': value['source_dirty'] = True
    elif change == 'wrong-upstream': value['upstream_revision'] = 'b' * 40
    elif change == 'wrong-platform': value['platform'] = 'mac-x86'
    elif change == 'probe-profile': layout = replace(layout, profile='runtime-experiment')
    elif change == 'wrong-inputs': value['inputs_sha256'] = 'f' * 64
    elif change == 'arbitrary-code':
        (root / 'unexpected.mjs').write_bytes(b'no')
        value['files']['unexpected.mjs'] = {'bytes': 2, 'sha256': digest(b'no')}
    elif change == 'changed-dependency':
        path = root / 'dependencies/ooz/index.js'; path.write_bytes(b'changed')
        value['files']['dependencies/ooz/index.js'] = {'bytes': 7, 'sha256': digest(b'changed')}
    elif change == 'wrong-node':
        path = layout.resource_root / 'toolchains/node/runtime.json'
        node = json.loads(path.read_text()); node['version'] = '0.0.0'; path.write_text(json.dumps(node))
    layout = seal(layout, root, value)
    if change == 'unbound-manifest': layout = replace(layout, resources={})
    elif change == 'tampered-script': (root / 'scripts/extract_voice_links.mjs').write_bytes(b'changed')
    elif change == 'wrong-build':
        value['build_id'] = 'f' * 64
        path = root / 'runtime.json'; path.write_text(json.dumps(value))
        layout = replace(layout, resources={**layout.resources, reader.ZZZ_PREFIX + 'runtime.json': digest(path.read_bytes())})
    with pytest.raises(PreparationFailure, match='missing or incompatible'):
        reader.production_zzz_reader(layout=layout)


def test_frozen_scene_refresh_uses_app_local_commands_and_private_metadata(tmp_path, monkeypatch):
    from backend import zzz_assets, runtime_bundle
    layout, root, value = fixture(tmp_path, monkeypatch)
    layout = seal(layout, root, value)
    game = tmp_path / 'Game'; game.mkdir()
    directory = layout.data_root / 'languages/zzz/zh-Hans'
    monkeypatch.setattr(reader, 'discover_layout', lambda: layout)
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(zzz_assets, 'fingerprint', lambda _: 'authored-game-fingerprint')
    monkeypatch.setattr(zzz_assets.shutil, 'which', lambda *_: pytest.fail('No PATH lookup'))
    calls = []

    def metadata(project, *, revision, directory):
        assert project == layout.application_root and revision == 'authored-revision'
        assert directory == layout.work_root / 'zzz-scenes'
        for name in game_tools.METADATA_FILES:
            (directory / name).write_text('{}')
    monkeypatch.setattr(game_tools, 'refresh_zzz_metadata', metadata)

    def execute(command, **kwargs):
        calls.append(command)
        assert command[0].endswith('node.exe') and kwargs['env']['PATH'] == ''
        assert kwargs['cwd'] == layout.work_root / 'zzz-scenes'
        assert command[-1] == str(root / 'upstream/galgame-perform.mjs')
        tools = kwargs['cwd']
        if 'extract_voice_links.mjs' in command[1]:
            name = command[5]
            (tools / name).write_text(json.dumps([{'text_id': command[4], 'source': 'authored-voice'}]))
            (tools / (name + '.diagnostics.json')).write_text('{"records":1}')
        else:
            (tools / 'scene-links-cinematic.json').write_text('[{"text_id":"cutscene","event":"authored-event"}]')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(zzz_assets.subprocess, 'run', execute)
    first = zzz_assets._links(game, directory, 'authored-revision', lambda _: None)
    second = zzz_assets._links(game, directory, 'authored-revision', lambda _: None)
    assert first == second and len(calls) == 3
    assert [row['text_id'] for row in first[0]] == ['dialogue', 'comic']
    assert first[0][1]['channels'] == ['cinematic']
    assert first[1][0]['event'] == 'authored-event'
    assert not list(layout.work_root.rglob('*.mjs')) and not list(layout.work_root.rglob('*.ts'))
