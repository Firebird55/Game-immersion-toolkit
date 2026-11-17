"""Use the actual closed toolchain verifier; never compile or acquire tools."""
from types import SimpleNamespace

import pytest

from backend import nte_game_data_runtime as runtime, nte_assets, nte_toolchain
from backend.game_data_protocol import GameDataError
from backend.tests.test_nte_toolchain import fixture


def context(layout):
    cache, directory = layout.cache_root/'nte/cache', layout.work_root/'nte/task'
    cache.mkdir(parents=True); directory.mkdir(parents=True)
    return SimpleNamespace(cache_directory=cache, directory=directory, check=lambda: None)


def test_exact_offline_command_uses_the_existing_owned_verified_windows_chain(tmp_path, monkeypatch):
    layout, dependencies = fixture(tmp_path, monkeypatch)
    ctx = context(layout)
    monkeypatch.setattr(nte_assets, 'ensure_extractor', lambda *_: pytest.fail('Implicit preparation'))
    reader = runtime.resolve('windows', ctx, layout=layout)
    source = ctx.cache_directory/'empty'; source.mkdir()
    output = ctx.directory/'tables'
    for operation in runtime.OPERATIONS:
        command, environment, working = reader.invocation(source, output, operation)
        assert command == [str(reader.executable), operation, str(source), str(dependencies), str(output)]
        assert working == dependencies and 'DOTNET_ROOT' not in environment
    assert reader.identity['kind'] == 'nte-owned-windows-reader-v1'
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('Implicit SDK lookup'))
    actual = nte_assets._reader_invocation(source, reader.executable, output, 'publisher-tables', game_data_reader=reader)
    assert actual[0][0] == str(reader.executable)
    with pytest.raises(ValueError):
        nte_assets._reader_invocation(source, reader.executable, output, 'publisher-tables',
                                     game_data_reader=SimpleNamespace(executable=reader.executable))


@pytest.mark.parametrize('platform', ['android', 'linux', 'macos'])
def test_other_hosts_never_resolve_or_execute_a_windows_dependency(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(nte_toolchain, 'resolve', lambda **_: pytest.fail('Windows reader on another host'))
    ctx = SimpleNamespace(check=lambda: None)
    with pytest.raises(GameDataError) as rejected:
        runtime.resolve(platform, ctx)
    assert rejected.value.code == 'nte_reader_unavailable'


@pytest.mark.parametrize('change', ['helper', 'dependency', 'output', 'source', 'mode'])
def test_mutated_closure_and_foreign_paths_fail_before_any_process(tmp_path, monkeypatch, change):
    layout, dependencies = fixture(tmp_path, monkeypatch)
    ctx = context(layout); reader = runtime.resolve('windows', ctx, layout=layout)
    source = ctx.cache_directory/'empty'; source.mkdir()
    output, operation = ctx.directory/'tables', 'publisher-tables'
    if change == 'helper': reader.executable.write_bytes(b'foreign helper')
    elif change == 'dependency': (dependencies/'UEExtractor.dll').write_bytes(b'foreign dependency')
    elif change == 'output': output = layout.data_root/'another-preparation'
    elif change == 'source': source = layout.data_root/'foreign-source'
    else: operation = 'voice'
    with pytest.raises(GameDataError): reader.invocation(source, output, operation)
