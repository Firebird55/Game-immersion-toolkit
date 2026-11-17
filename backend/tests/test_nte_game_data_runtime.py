"""Use the actual closed toolchain verifier; never compile or acquire tools."""
from types import SimpleNamespace
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import subprocess

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


def codec_fixture(tmp_path, monkeypatch):
    layout, dependencies = fixture(tmp_path, monkeypatch)
    name = 'notices/MANAGED-COMPONENTS.json'
    packet = {'supplier_sha256': nte_toolchain.DEPENDENCIES['UEExtractor.dll'],
              'components': [{'name': 'OodleSharp', 'sha256': 'a'*64}]}
    data = json.dumps(packet).encode(); (dependencies/name).write_bytes(data)
    manifest = json.loads((dependencies/'dependencies.json').read_bytes())
    manifest['files'][name] = hashlib.sha256(data).hexdigest()
    (dependencies/'dependencies.json').write_text(json.dumps(manifest))
    resources = dict(layout.resources)
    for relative in (name, 'dependencies.json'):
        resources[nte_toolchain.PREFIX+relative] = hashlib.sha256((dependencies/relative).read_bytes()).hexdigest()
    layout = replace(layout, resources=resources)
    return runtime.resolve('windows', context(layout), layout=layout)


@pytest.mark.parametrize('fault', [None, 'nonce', 'raw_sha256', 'stored_sha256', 'codec_sha256',
                                  'blocks', 'extra', 'missing', 'output', 'exit', 'cancel', 'timeout'])
def test_codec_receipt_binds_this_invocation_and_cleans_owned_inputs(tmp_path, monkeypatch, fault):
    reader = codec_fixture(tmp_path, monkeypatch); ctx = reader.context
    calls = []
    class Process:
        returncode = None
        killed = False
        def __init__(self, command, **kwargs):
            assert command[1] == '--decode-oodle'
            self.source, self.output = Path(command[2]), Path(command[4])
            assert self.source.is_relative_to(ctx.cache_directory) and self.output.is_relative_to(ctx.directory)
            assert kwargs['cwd'] == Path(command[3]) and 'DOTNET_ROOT' not in kwargs['env']
            calls.append(self)
        def communicate(self, *, input, timeout):
            packet = json.loads(input)
            assert packet['blocks'] == [{'stored_bytes': 3, 'raw_bytes': 4}, {'stored_bytes': 2, 'raw_bytes': 3}]
            assert (self.source/'block.bin').read_bytes() == b'abcde'
            if fault == 'cancel':
                ctx.check = lambda: (_ for _ in ()).throw(GameDataError('cancelled', 'Cancelled', 409))
                raise subprocess.TimeoutExpired('owned decoder', timeout)
            if fault == 'timeout':
                raise subprocess.TimeoutExpired('owned decoder', timeout)
            result = b'ABCDEFG'; (self.output/'decoded.bin').write_bytes(result)
            receipt = {key: packet[key] for key in ('schema', 'nonce', 'stored_bytes', 'raw_bytes', 'stored_sha256', 'codec_sha256')}
            receipt.update(blocks=2, raw_sha256=hashlib.sha256(result).hexdigest())
            if fault in receipt: receipt[fault] = 0 if fault == 'blocks' else '0'*len(receipt[fault])
            elif fault == 'extra': receipt['extra'] = 'untrusted'
            elif fault == 'output': (self.output/'decoded.bin').write_bytes(b'changed')
            if fault != 'missing': (self.output/'complete.json').write_text(json.dumps(receipt))
            self.returncode = 1 if fault == 'exit' else 0
        def poll(self): return self.returncode
        def kill(self): self.killed = True; self.returncode = -1
        def wait(self, **kwargs): return self.returncode
    monkeypatch.setattr(runtime.subprocess, 'Popen', Process)
    if fault == 'timeout':
        clock = iter([0, 0, 61]); monkeypatch.setattr(runtime.time, 'monotonic', lambda: next(clock))
    if fault:
        with pytest.raises(GameDataError): reader.oodle([(b'abc', 4), (b'de', 3)])
    else:
        assert reader.oodle([(b'abc', 4), (b'de', 3)]) == b'ABCDEFG'
    assert len(calls) == 1
    assert not calls[0].source.exists() and not calls[0].output.exists()
    assert calls[0].killed == (fault in ('cancel', 'timeout'))


def test_codec_budget_batches_are_bounded_and_untrusted_notice_never_executes(tmp_path, monkeypatch):
    reader = codec_fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(runtime.NteGameDataReader, '_oodle_batch', lambda self, rows: calls.append(rows) or b'x'*len(rows))
    assert reader.oodle([(b'x', 1)]*513) == b'x'*513
    assert [len(batch) for batch in calls] == [512, 1]
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Untrusted codec started'))
    for blocks in ([], [(b'', 1)], [(b'a', True)], [(b'a', 129*1024**2)], [(b'a', 128*1024**2)]*5):
        with pytest.raises(GameDataError): reader.oodle(blocks)


def test_codec_notice_is_verified_again_before_starting_process(tmp_path, monkeypatch):
    reader = codec_fixture(tmp_path, monkeypatch)
    path = reader.layout.resource_root/nte_toolchain.PREFIX/'notices/MANAGED-COMPONENTS.json'
    path.write_text('{}')
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Untrusted codec started'))
    with pytest.raises((GameDataError, ValueError)):
        reader.oodle([(b'a', 1)])


@pytest.mark.parametrize('fault', [None, 'cancel', 'timeout'])
def test_owned_inventory_process_is_cancellable_bounded_and_uses_exact_operation(tmp_path, monkeypatch, fault):
    layout, _ = fixture(tmp_path, monkeypatch)
    ctx = context(layout); reader = runtime.resolve('windows', ctx, layout=layout)
    source = ctx.cache_directory/'empty'; source.mkdir()
    output = ctx.directory/'inventory'; owned = []
    class Process:
        returncode = None; killed = False
        def __init__(self, command, **kwargs):
            assert command[1] == 'publisher-dialogue-inventory'
            assert kwargs['stdout'] == runtime.subprocess.DEVNULL and kwargs['stderr'] == runtime.subprocess.DEVNULL
            assert 'DOTNET_ROOT' not in kwargs['env']; owned.append(self)
        def communicate(self, *, input, timeout):
            assert json.loads(input) == {'inventory_nonce': 'a'*32}
            if fault == 'cancel': ctx.check = lambda: (_ for _ in ()).throw(GameDataError('cancelled', 'Cancelled', 409))
            if fault: raise subprocess.TimeoutExpired('owned inventory', timeout)
            self.returncode = 0
        def poll(self): return self.returncode
        def kill(self): self.killed = True; self.returncode = -1
        def wait(self, **kwargs): return self.returncode
    monkeypatch.setattr(runtime.subprocess, 'Popen', Process)
    if fault == 'timeout':
        timer = iter([0, 0, 61]); monkeypatch.setattr(runtime.time, 'monotonic', lambda: next(timer))
    if fault:
        with pytest.raises(GameDataError): reader.execute(source, output, 'publisher-dialogue-inventory', {'inventory_nonce': 'a'*32}, timeout=60)
    else:
        assert reader.execute(source, output, 'publisher-dialogue-inventory', {'inventory_nonce': 'a'*32}, timeout=60).returncode == 0
    assert len(owned) == 1 and owned[0].killed == bool(fault)
