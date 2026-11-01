"""Probe fixture structure and failure checks; actual apphost runs in native CI."""
import importlib.util
import json
from pathlib import Path
import copy
import io
import os
import threading
from types import SimpleNamespace

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
    observation=probe._Observation()
    with pytest.raises(ValueError) as caught: probe._layout(helper, resources, tmp_path / 'probe', observation=observation)
    observation.failed(caught.value)
    value=observation.failure()
    assert value['stage'] == ('source-identity' if fault == 'checkout-dirty' else 'helper-receipt' if fault == 'dependency-bytes' else 'resource-receipt')
    assert value['child'] == probe._child_default() and observation.owners == [] and value['completed_checks'] == []


@pytest.mark.parametrize('fault', [None, 'runtime', 'payload'])
def test_native_probe_asserts_child_results_and_authored_bytes(tmp_path, monkeypatch, fault):
    probe = module(); helper, resources, _ = source_fixture(tmp_path, monkeypatch, probe)
    layout, reader, _ = probe._layout(helper, resources, tmp_path / 'probe')
    def execute(command, request, env, cwd, *, reject=False, observation=None):
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
    observation = probe._Observation()
    if fault:
        with pytest.raises(ValueError) as caught: probe.run_checks(layout, reader, tmp_path / 'probe', observation=observation)
        observation.failed(caught.value)
        failed = observation.failure()
        assert failed['stage'] == ('runtime-identity' if fault == 'runtime' else 'nte-voice')
        assert failed['operation'] == ('runtime-identity' if fault == 'runtime' else 'nte-voice-zh')
        assert failed['completed_checks'] == list(probe.CHECKS[:0 if fault == 'runtime' else 2])
    else:
        checks = probe.run_checks(layout, reader, tmp_path / 'probe', observation=observation)
        assert len(checks) == 7 and all(checks.values())
        assert observation.completed == list(probe.CHECKS)


def active_observation(probe):
    value = probe._Observation(); value.at('runtime-identity', 'runtime-identity', 'identity-json')
    return value


def fake_owner(probe, monkeypatch, *, stdout=b'Game reader completed\n', stderr=b'', code=0,
               communicate_error=None, stop_error=None, close_error=None):
    calls = []; owner = SimpleNamespace()
    def communicate(**kwargs):
        calls.append(('communicate', kwargs))
        if communicate_error is not None: raise communicate_error
        return stdout, stderr
    def stop():
        calls.append('stop')
        if stop_error is not None: raise stop_error
    def close():
        calls.append('close')
        if close_error is not None: raise close_error
    owner.process = SimpleNamespace(communicate=communicate, returncode=code)
    owner.stop, owner.close_streams = stop, close
    def create(command, **kwargs):
        calls.append(('create', command, kwargs)); return owner
    monkeypatch.setattr(probe, 'OwnedProcess', create)
    return owner, calls


@pytest.mark.parametrize('fault', ['timeout', 'exit', 'stdout', 'stderr', 'unknown'])
def test_actual_execution_boundary_retains_first_error_without_raw_context(monkeypatch, tmp_path, fault):
    probe = module(); observation = active_observation(probe)
    error = probe.subprocess.TimeoutExpired(['PRIVATE-COMMAND'], 60, output=b'PRIVATE-OUTPUT') if fault == 'timeout' else OSError('PRIVATE-ERROR')
    owner, calls = fake_owner(probe, monkeypatch, stdout=b'PRIVATE' * 1200 if fault == 'stdout' else b'PRIVATE',
        stderr=b'PRIVATE' * 1200 if fault == 'stderr' else b'', code=1 if fault == 'exit' else 0,
        communicate_error=error if fault in ('timeout', 'unknown') else None)
    with pytest.raises(Exception) as caught:
        probe._execute(['owned-command'], {'owned': 'input'}, {'OWNED': 'VALUE'}, tmp_path, observation=observation)
    value = observation.failure()
    assert value['failure_kind'] == {'timeout':'timeout', 'exit':'exit-mismatch', 'stdout':'output-limit', 'stderr':'output-limit', 'unknown':'unknown'}[fault]
    assert value['cleanup'] == dict(state='confirmed', step='complete')
    assert observation.owners == [owner] and observation.errors[0] is caught.value
    if fault in ('timeout', 'unknown'): assert caught.value is error
    assert calls[-2:] == ['stop', 'close']
    assert calls[1][1] == dict(input=b'{"owned": "input"}', timeout=60)
    assert 'PRIVATE' not in json.dumps(value)


@pytest.mark.parametrize('stop_fails,close_fails,body_fails', [(True,False,True),(False,True,True),(True,True,True),(True,False,False),(False,True,False)])
def test_cleanup_closes_only_after_confirmed_stop_and_does_not_replace_body(monkeypatch, tmp_path, stop_fails, close_fails, body_fails):
    probe = module(); observation = active_observation(probe)
    body, stop, close = OSError('PRIVATE-BODY'), OSError('PRIVATE-STOP'), OSError('PRIVATE-CLOSE')
    owner, calls = fake_owner(probe, monkeypatch, communicate_error=body if body_fails else None,
        stop_error=stop if stop_fails else None, close_error=close if close_fails else None)
    with pytest.raises(OSError) as caught:
        probe._execute(['owned'], {}, {}, tmp_path, observation=observation)
    assert caught.value is (body if body_fails else stop if stop_fails else close)
    assert calls.count('stop') == 1 and calls.count('close') == (0 if stop_fails else 1)
    assert calls[-1:] == ['stop'] if stop_fails else calls[-2:] == ['stop', 'close']
    value = observation.failure()
    assert value['failure_kind'] == ('unknown' if body_fails else 'cleanup')
    assert value['cleanup'] == dict(state='unconfirmed', step='stop' if stop_fails else 'close')
    assert observation.owners == [owner] and observation.errors[0] is caught.value
    assert not stop_fails or stop in observation.errors
    assert (close in observation.errors) == (close_fails and not stop_fails)
    assert 'PRIVATE' not in json.dumps(value)


def test_unconfirmed_stop_returns_without_closing_real_blocked_buffered_reader(tmp_path, monkeypatch):
    probe = module(); read_fd, write_fd = os.pipe()
    raw = io.FileIO(read_fd, mode='rb', closefd=True)
    inside_read, reader_done, execute_done = (threading.Event() for _ in range(3))
    closes = []; reader_results = []; reader_errors = []; execute_errors = []; calls = []
    class RealPipeRaw(io.RawIOBase):
        def readable(self): return True
        def readinto(self, target):
            # BufferedReader holds its real internal lock before entering here.
            inside_read.set()
            return raw.readinto(target)
        def close(self):
            closes.append('raw-close'); raw.close(); super().close()
    stream = io.BufferedReader(RealPipeRaw())
    body = probe.subprocess.TimeoutExpired(['owned-command'], 60)
    stop = OSError('PRIVATE-UNCONFIRMED-STOP')
    def communicate(**kwargs):
        calls.append('communicate'); assert kwargs == {'input': b'{}', 'timeout': 60}; raise body
    def stopped(): calls.append('stop'); raise stop
    def close_streams(): calls.append('close'); stream.close()
    owner = SimpleNamespace(process=SimpleNamespace(communicate=communicate), stdout=stream,
                            stop=stopped, close_streams=close_streams)
    monkeypatch.setattr(probe, 'OwnedProcess', lambda *args, **kwargs: owner)
    observation = active_observation(probe)
    def read():
        try: reader_results.append(stream.read(1))
        except BaseException as error: reader_errors.append(error)
        finally: reader_done.set()
    def execute():
        try: probe._execute(['owned'], {}, {}, tmp_path, observation=observation)
        except BaseException as error: execute_errors.append(error)
        finally: execute_done.set()
    reader = threading.Thread(target=read, name='owned-probe-pipe-reader')
    running = threading.Thread(target=execute, name='owned-probe-execute')
    reader.start()
    try:
        assert inside_read.wait(2)
        running.start()
        assert execute_done.wait(2), 'Unconfirmed stop must return without acquiring the reader lock'
        assert not reader_done.is_set() and not stream.closed and not raw.closed
        assert calls == ['communicate', 'stop'] and closes == []
        assert execute_errors == [body] and observation.errors == [body, stop]
        assert observation.owners == [owner] and owner.stdout is stream
        value = observation.failure()
        assert value['failure_kind'] == 'timeout' and value['cleanup'] == dict(state='unconfirmed', step='stop')
        assert 'PRIVATE' not in json.dumps(value)
    finally:
        # Only the test releases its actual writer endpoint to deliver EOF.
        # It never calls the producer's unconfirmed close or retries that owner.
        os.close(write_fd)
        reader.join(2)
        if running.ident is not None: running.join(2)
        if not reader.is_alive() and not running.is_alive() and not stream.closed: stream.close()
    assert not reader.is_alive() and not running.is_alive()
    assert reader_errors == [] and reader_results == [b'']
    assert calls == ['communicate', 'stop'] and closes == ['raw-close']
    assert stream.closed and raw.closed and execute_errors == [body]


def test_constructor_failure_never_adopts_or_reconstructs_an_owner(monkeypatch, tmp_path):
    probe = module(); observation = active_observation(probe); error = OSError('PRIVATE-CONSTRUCTOR'); calls=[]
    def create(*args, **kwargs): calls.append('create'); raise error
    monkeypatch.setattr(probe, 'OwnedProcess', create)
    with pytest.raises(OSError) as caught: probe._execute(['owned'], {}, {}, tmp_path, observation=observation)
    assert caught.value is error and calls == ['create'] and observation.owners == [] and observation.errors[0] is error
    value=observation.failure()
    assert value['child'] == probe._child_default() and value['failure_kind'] == 'spawn'
    assert value['cleanup'] == dict(state='unconfirmed', step='not-run')
    assert 'not-created' not in json.dumps(value) and 'PRIVATE' not in json.dumps(value)


@pytest.mark.parametrize('raw,code,reject,reply', [(b'Game reader completed\n',0,False,'completed'),
    (b'Game reader failed; check the game files and reader version\r\n',1,True,'reader-failed'),
    (b'Unsupported NTE localization format; update the toolkit reader\n',3,True,'unsupported-format'),
    (b'PRIVATE-FALSE-REPLY',7,True,'other'),(b'',1,True,'other')])
def test_fixed_reply_is_observation_only_and_keeps_original_reject_predicate(monkeypatch, tmp_path, raw, code, reject, reply):
    probe=module(); observation=active_observation(probe); owner,calls=fake_owner(probe,monkeypatch,stdout=raw,code=code)
    assert probe._execute(['owned'], {}, {}, tmp_path, reject=reject, observation=observation) == raw
    assert observation.child['reply'] == reply and observation.owners == [] and observation.first is None
    # The fixed response itself never changes the exit acceptance criterion.
    owner.process.returncode=1 if not reject else 0
    with pytest.raises(ValueError): probe._execute(['owned'], {}, {}, tmp_path, reject=reject, observation=observation)
    assert observation.failure()['failure_kind'] == 'exit-mismatch'


def test_failed_probe_keeps_actual_fixture_owner_and_error_without_cleanup_retry(tmp_path, monkeypatch):
    probe=module(); fixture=tmp_path/'owned-fixture'; fixture.mkdir(); (fixture/'canary').write_bytes(b'authored')
    monkeypatch.setattr(probe.tempfile,'mkdtemp',lambda **kwargs:str(fixture))
    monkeypatch.setattr(probe,'host_platform',lambda:'win-x64')
    owner=SimpleNamespace(); error=OSError('PRIVATE-ERROR'); calls=[]
    def layout(*args,observation):
        observation.at('runtime-identity','runtime-identity'); observation.owners.append(owner)
        observation.cleanup=dict(state='unconfirmed',step='stop'); observation.failed(error,'cleanup'); raise error
    monkeypatch.setattr(probe,'_layout',layout)
    monkeypatch.setattr(probe.shutil,'rmtree',lambda *args,**kwargs:calls.append('remove'))
    value=probe.probe(tmp_path/'helper',tmp_path/'resources'); held=probe._RETAINED_FAILURES[-1]
    assert held.fixture == fixture and held.owners == [owner] and held.errors[0] is error
    assert calls == [] and (fixture/'canary').read_bytes() == b'authored'
    assert value['passed'] is False and value['stage']=='runtime-identity' and 'PRIVATE' not in json.dumps(value)


def test_success_projection_and_fixture_cleanup_are_not_replaced_by_diagnostics(tmp_path,monkeypatch):
    probe=module(); fixture=tmp_path/'owned-fixture'; fixture.mkdir(); source='a'*40
    monkeypatch.setattr(probe.tempfile,'mkdtemp',lambda **kwargs:str(fixture)); monkeypatch.setattr(probe,'host_platform',lambda:'win-x64')
    identities={n:'b'*64 for n in ('helper_manifest_sha256','resource_manifest_sha256','managed_components_sha256')}
    monkeypatch.setattr(probe,'_layout',lambda *args,**kw:(SimpleNamespace(source_commit=source),None,identities))
    def checks(*args,observation):
        observation.completed=list(probe.CHECKS);return {n:True for n in probe.CHECKS}
    monkeypatch.setattr(probe,'run_checks',checks)
    result=probe.probe(tmp_path/'helper',tmp_path/'resources')
    assert result == dict(schema='toolkit-unreal-native-probe-v1',platform='win-x64',source_commit=source,source_dirty=False,
        execution='actual-app-local-process',**identities,probe_source_sha256=probe.digest(Path(probe.__file__).read_bytes()),
        checks={n:True for n in probe.CHECKS},passed=True,real_games_accessed=False,real_accounts_accessed=False,
        game_asset_validation='not-performed',encrypted_archive_validation='not-performed',oodle_validation='not-performed',rights_review='pending')
    assert not fixture.exists() and probe._RETAINED_FAILURES == []


def test_closed_failure_projection_refuses_forged_progress_labels_and_private_fields():
    probe=module(); observation=active_observation(probe); observation.failed(ValueError('PRIVATE'),'identity-json')
    value=observation.failure()
    changes=[lambda v:v.update(private='PRIVATE'),lambda v:v.update(passed=0),lambda v:v.update(stage='PRIVATE'),
        lambda v:v.update(operation='nte-voice-zh'),lambda v:v.update(completed_checks=[probe.CHECKS[0]]),
        lambda v:v['child'].update(state='not-created'),lambda v:v['child'].update(exit='one'),
        lambda v:v['cleanup'].update(state='confirmed'),lambda v:v['child'].update(reply='PRIVATE'),
        lambda v:v.update(failure_kind='extracted-bytes')]
    for change in changes:
        bad=copy.deepcopy(value);change(bad)
        with pytest.raises(ValueError):probe.validate_failure(bad)


def test_real_fixture_and_commands_distinguish_first_actual_reader_failure(monkeypatch,tmp_path):
    probe=module();helper,resources,_=source_fixture(tmp_path,monkeypatch,probe)
    layout,reader,_=probe._layout(helper,resources,tmp_path/'probe');observation=probe._Observation();calls=[]
    def create(command,**options):
        identity=command[-1]=='--runtime-identity'
        assert 'DOTNET_ROOT' not in options['env'] and 'DOTNET_STARTUP_HOOKS' not in options['env']
        raw=json.dumps(dict(schema='proxy-nte-runtime-identity-v1',runtime_version=probe.RUNTIME,runtime_origin='app-local',
            game_execution_approved=False,corelib_sha256=reader.manifest['files']['System.Private.CoreLib.dll']['sha256'])).encode() if identity else b'Game reader failed; check the game files and reader version\n'
        owner=SimpleNamespace(process=SimpleNamespace(returncode=0 if identity else 1,communicate=lambda **kw:(raw,b'')),
            stop=lambda:calls.append('stop'),close_streams=lambda:calls.append('close'))
        calls.append(('create',tuple(command),owner));return owner
    monkeypatch.setattr(probe,'OwnedProcess',create)
    with pytest.raises(ValueError):probe.run_checks(layout,reader,tmp_path/'probe',observation=observation)
    value=observation.failure()
    assert value['stage']=='nte-inventory' and value['operation']=='nte-inventory' and value['failure_kind']=='exit-mismatch'
    assert value['completed_checks']==[probe.CHECKS[0]]
    assert value['child']==dict(state='returned',exit='one',stdout='nonempty',stderr='empty',reply='reader-failed')
    assert value['cleanup']==dict(state='confirmed',step='complete')
    created=[row for row in calls if isinstance(row,tuple)]
    assert len(created)==2 and observation.owners==[created[-1][2]] and calls[-2:]==['stop','close']


def test_successful_native_checks_cannot_mask_failed_fixture_removal(tmp_path,monkeypatch):
    probe=module();fixture=tmp_path/'owned-fixture';fixture.mkdir();error=OSError('PRIVATE-REMOVE');calls=[]
    monkeypatch.setattr(probe.tempfile,'mkdtemp',lambda **kw:str(fixture));monkeypatch.setattr(probe,'host_platform',lambda:'win-x64')
    monkeypatch.setattr(probe,'_layout',lambda *args,**kw:(SimpleNamespace(source_commit='a'*40),None,{}))
    def checks(*args,observation):observation.completed=list(probe.CHECKS);return {n:True for n in probe.CHECKS}
    def remove(root):calls.append(root);raise error
    monkeypatch.setattr(probe,'run_checks',checks);monkeypatch.setattr(probe.shutil,'rmtree',remove)
    value=probe.probe(tmp_path/'helper',tmp_path/'resources');held=probe._RETAINED_FAILURES[-1]
    assert value['passed'] is False and value['stage']=='fixture-cleanup' and value['failure_kind']=='cleanup'
    assert value['completed_checks']==list(probe.CHECKS) and value['cleanup']==dict(state='unconfirmed',step='fixture')
    assert held.fixture==fixture and held.errors[0] is error and calls==[fixture] and fixture.exists()
    assert 'PRIVATE' not in json.dumps(value)
