import asyncio
import copy
import threading
import time
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from backend import automatic_mobile_export as auto
from backend.export_lock import ExportLock, ExportLockCleanupError


def fixture(tmp_path, monkeypatch):
    destination = tmp_path / 'cloud'
    destination.mkdir()
    install = tmp_path / 'game'
    install.mkdir()
    state = {'stamp': 'v1', 'calls': 0, 'fail': False, 'change': False}
    adapter = SimpleNamespace(TEXT_LOCALES={'ja': 'JP', 'en': 'EN', 'fr': 'FR'}, SUPPORTED_LOCALES=['ja', 'en'], LANGUAGE_INDEX_VERSION=1,
                              fingerprint=lambda _: state['stamp'])
    monkeypatch.setattr(auto, 'asset_adapter', lambda _: (adapter, ''))
    monkeypatch.setattr(auto, 'probe', lambda *_: 'present')
    from backend import media_tools
    monkeypatch.setattr(media_tools, 'ffmpeg_executable', lambda: 'mock-ffmpeg')
    decoder = tmp_path / 'data/voice-assets/vgmstream' / ('vgmstream-cli.exe' if sys.platform == 'win32' else 'vgmstream-cli')
    decoder.parent.mkdir(parents=True)
    decoder.write_bytes(b'mock')
    manager = auto.AutomaticMobileExports(tmp_path, home=tmp_path / 'local', install_lookup=lambda _: install)
    monkeypatch.setattr(manager.picker, '_validate_folder', lambda value: (Path(value), Path(value)))
    manager.configure('zzz', True, str(destination), {'ja': 'en'})
    class Process:
        def __init__(self, command, *, stdout, **kwargs):
            state['calls'] += 1
            assert kwargs['cwd'] == Path(auto.__file__).resolve().parents[1] != manager.root
            assert command[command.index('--root') + 1] == str(manager.root)
            assert '--account-signature' not in command
            assert command[command.index('--source-locale')+1] in ('ja', 'en')
            output = Path(command[command.index('--output')+1]);output.mkdir(parents=True, exist_ok=True)
            candidate = output / 'candidate.zip'
            candidate.write_bytes(('completed-'+state['stamp']).encode())
            stdout.write(json.dumps({'state': 'complete', 'bundle': str(candidate)})+'\n');stdout.flush()
            self.returncode = state.get('exit', 1) if state['fail'] else 0
            if state['change']:
                state['stamp'] += '-changed'
        def poll(self): return self.returncode
    class Owned:
        def __init__(self, command, **kwargs):
            self.process = Process(command, **kwargs)
        def stop(self):
            return self.process.returncode
        def close_streams(self):
            pass
    monkeypatch.setattr(auto, 'OwnedProcess', Owned)
    def run():
        manager.reconcile()
        manager.observed = {key: (stamp, -1000) for key, (stamp, _) in manager.observed.items()}
        manager.reconcile()
    return manager, state, destination, run


def test_initial_noop_update_add_remove_and_restart(tmp_path, monkeypatch):
    manager, state, destination, run = fixture(tmp_path, monkeypatch)
    run();assert state['calls'] == 1
    published = next(destination.rglob('*.zip'));original = published.stat().st_mtime_ns
    run();assert state['calls'] == 1 and published.stat().st_mtime_ns == original
    manager.action('zzz', 'update');run()
    assert state['calls'] == 1 and published.stat().st_mtime_ns == original
    state['stamp'] = 'v2';run();assert state['calls'] == 2
    assert published.read_bytes() == b'completed-v2'
    assert next((manager.home/'recovery').rglob('*.zip')).read_bytes() == b'completed-v1'
    manager.configure('zzz', True, str(destination), {'ja': 'en', 'en': 'fr'});run();assert state['calls'] == 3
    manager.configure('zzz', True, str(destination), {'ja': 'en'});run();assert len(list(destination.rglob('*.zip'))) == 2
    manager.action('zzz', 'pause')
    restored = auto.AutomaticMobileExports(tmp_path, home=manager.home, install_lookup=manager.install_lookup)
    assert restored.status('zzz')['paused']
    state['stamp'] = 'v3';restored.reconcile();assert state['calls'] == 3
    manager.action('zzz', 'resume');run();assert state['calls'] == 4
    published.unlink();run();assert published.exists() and state['calls'] == 5


def test_failure_requires_retry_but_changed_source_requeues(tmp_path, monkeypatch):
    manager, state, destination, run = fixture(tmp_path, monkeypatch)
    state['fail'] = True;run();assert state['calls'] == 1
    run();assert state['calls'] == 1
    manager.action('zzz', 'retry');state['fail'] = False;run();assert state['calls'] == 2
    previous = next(destination.rglob('*.zip')).read_bytes()
    state['stamp'] = 'v2';state['change'] = True;run()
    assert next(destination.rglob('*.zip')).read_bytes() == previous
    assert manager.status('zzz')['jobs']['ja']['state'] == 'waiting'
    state['change'] = False;run();assert next(destination.rglob('*.zip')).read_bytes() != previous


def test_publisher_export_worker_pins_setup_edition_and_detects_a_change(tmp_path, monkeypatch):
    from backend import endfield_assets, endfield_release, game_paths, mobile_export_worker as worker
    from backend.publisher_regions import select_region, selected_region
    from backend.mobile_export_layout import work_folder
    from backend import language_worker

    host_tools = tmp_path / 'data/endfield/tools'
    output = tmp_path / 'exports'
    private_tools = work_folder(output) / 'source/tools'
    monkeypatch.setattr(game_paths, 'settings_path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(endfield_release, 'fingerprint', lambda region: 'publisher-' + region)
    monkeypatch.setattr(worker, 'prepare_source', lambda *_a, **_k: ([], None, None, None))
    monkeypatch.setattr(worker, 'export_library', lambda *_a, **_k: None)
    received = []
    def build(game, install, directory, _locale, _targets, snapshot):
        assert install is None
        region = selected_region(directory / 'tools', game)
        received.append(region)
        snapshot.write_text(json.dumps({'publisher_region': region}))
    monkeypatch.setattr(language_worker, 'build', build)
    select_region(host_tools, 'endfield', 'cn')
    args = ['worker', '--root', str(tmp_path), '--output', str(output), '--game', 'endfield',
            '--automatic-publisher', '--source-locale', 'en', '--translation-locale', 'ja',
            '--publisher-fingerprint', endfield_assets.publisher_fingerprint(host_tools)]
    monkeypatch.setattr(sys, 'argv', args)
    assert worker.main() == 0 and received == ['cn']
    assert selected_region(private_tools, 'endfield') == 'cn'
    select_region(host_tools, 'endfield', 'global')
    assert worker.main() == 1 and received == ['cn']
    args[-1] = endfield_assets.publisher_fingerprint(host_tools)
    assert worker.main() == 0 and received == ['cn', 'global']


def test_missing_pack_and_disconnected_destination_do_not_spawn(tmp_path, monkeypatch):
    manager, state, destination, run = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(auto, 'probe', lambda *_: 'missing');run();assert state['calls'] == 0
    assert 'Not detected' in manager.status('zzz')['jobs']['ja']['message']
    monkeypatch.setattr(auto, 'probe', lambda *_: 'present')
    destination.rmdir();run();assert state['calls'] == 0
    destination.mkdir();run();assert state['calls'] == 1


@pytest.mark.parametrize('failure', ['copy', 'checksum', 'replace', 'source'])
def test_publication_failure_keeps_previous(tmp_path, monkeypatch, failure):
    root = tmp_path/'cloud';root.mkdir();folder=root/'Game';folder.mkdir()
    dest=folder/'library.zip';dest.write_bytes(b'previous')
    candidate=tmp_path/'candidate.zip';candidate.write_bytes(b'new')
    recovery=tmp_path/'local'/'previous.zip'
    replace=auto.os.replace
    if failure=='replace':
        def locked(source,target):
            if Path(target)==dest: raise PermissionError('locked')
            return replace(source,target)
        monkeypatch.setattr(auto.os,'replace',locked)
    if failure=='checksum':
        monkeypatch.setattr(auto,'file_digest',lambda path: str(path))
    if failure=='copy':
        monkeypatch.setattr(auto.shutil,'disk_usage',lambda _:SimpleNamespace(free=0))
    def guard():
        if failure=='source': raise InterruptedError()
    with pytest.raises(OSError): auto.publish(candidate,dest,recovery,guard)
    assert dest.read_bytes()==b'previous'
    assert not dest.with_suffix('.zip.pending').exists()


def test_owned_locks_release_on_exit_and_rules_validate(tmp_path, monkeypatch):
    a,b=ExportLock(tmp_path/'queue'),ExportLock(tmp_path/'queue')
    assert a.acquire() and not b.acquire();a.close();assert b.acquire();b.close()
    manager,_,destination,_=fixture(tmp_path,monkeypatch)
    before=copy.deepcopy(manager.data)
    with pytest.raises(ValueError):manager.configure('zzz',True,str(destination),{'invented':'en'})
    assert manager.data==before


def test_interrupted_job_resumes_after_restart(tmp_path, monkeypatch):
    manager, state, destination, run = fixture(tmp_path, monkeypatch)
    manager._set('zzz', 'ja', state='exporting', message='Interrupted conversion')
    restored = auto.AutomaticMobileExports(tmp_path, home=manager.home, install_lookup=manager.install_lookup)
    restored.reconcile()
    restored.observed = {key: (stamp, -1000) for key, (stamp, _) in restored.observed.items()}
    restored.reconcile()
    assert state['calls'] == 1
    assert restored.status('zzz')['jobs']['ja']['state'] == 'complete'


def test_interrupted_destination_copy_leaves_no_partial_publication(tmp_path):
    folder=tmp_path/'cloud'/'Game';folder.mkdir(parents=True)
    dest=folder/'library.zip';dest.write_bytes(b'previous')
    candidate=tmp_path/'candidate.zip';candidate.write_bytes(bytes(5*1024**2))
    count=0
    def interrupt():
        nonlocal count
        count+=1
        if count==2:raise InterruptedError()
    with pytest.raises(InterruptedError):auto.publish(candidate,dest,tmp_path/'previous.zip',interrupt)
    assert dest.read_bytes()==b'previous'
    assert not dest.with_suffix('.zip.pending').exists()


def test_handoff_refuses_unconfirmed_process_cleanup(tmp_path):
    manager=auto.AutomaticMobileExports(tmp_path,home=tmp_path/'local')
    manager.process=SimpleNamespace(poll=lambda:None)
    with pytest.raises(RuntimeError,match='handoff cancelled'):
        manager.close()


def test_storage_failure_waits_and_low_space_does_not_repeat_conversion(tmp_path, monkeypatch):
    manager,state,destination,run=fixture(tmp_path,monkeypatch)
    state.update(fail=True,exit=3)
    run();assert state['calls']==1
    assert manager.status('zzz')['jobs']['ja']['state']=='waiting'
    usage=auto.shutil.disk_usage
    monkeypatch.setattr(auto.shutil,'disk_usage',lambda path: SimpleNamespace(free=0) if Path(path)==destination else usage(path))
    run();assert state['calls']==1
    monkeypatch.setattr(auto.shutil,'disk_usage',usage)
    state['fail']=False;run();assert state['calls']==2
    assert manager.status('zzz')['jobs']['ja']['state']=='complete'


def test_only_owned_old_completed_packages_are_pruned(tmp_path):
    import zipfile
    from backend.mobile_export_layout import work_folder, export_folder_name, catalog_name
    home=tmp_path/'local';output=home/'work'/'job'/'exports';output.mkdir(parents=True)
    current,previous='a'*64,'b'*64
    (output/'latest.json').write_text(json.dumps({'revision':current}))
    work=work_folder(output)
    old=[]
    for parent,name in [(output,export_folder_name('zzz',previous)),(work/'libraries',previous),(work/'previous-libraries',export_folder_name('zzz',previous))]:
        folder=parent/name;folder.mkdir(parents=True)
        with zipfile.ZipFile(folder/catalog_name('zzz'),'w') as archive:archive.writestr('manifest.json',json.dumps({'game':'zzz','revision':previous}))
        old.append(folder)
    retained=work/'libraries'/current;retained.mkdir()
    with zipfile.ZipFile(retained/catalog_name('zzz'),'w') as archive:archive.writestr('manifest.json',json.dumps({'game':'zzz','revision':current}))
    unrelated=output/'notes';unrelated.mkdir();(unrelated/'keep.txt').write_text('keep')
    auto.prune_completed_work(output,'zzz',home)
    assert all(not folder.exists() for folder in old)
    assert retained.exists() and (unrelated/'keep.txt').read_text()=='keep'


def test_failed_settings_save_cannot_activate_or_pause_a_rule(tmp_path, monkeypatch):
    manager, _, destination, _ = fixture(tmp_path, monkeypatch)
    before = copy.deepcopy(manager.data)
    stored = manager.path.read_bytes()
    def failed(*_): raise OSError('disk full')
    monkeypatch.setattr(auto, 'atomic_json', failed)
    with pytest.raises(OSError): manager.configure('zzz', False, str(destination), {'ja': 'en'})
    with pytest.raises(OSError): manager.action('zzz', 'pause')
    assert manager.data == before and manager.path.read_bytes() == stored


def test_repeated_unexplained_storage_failure_requires_retry(tmp_path, monkeypatch):
    manager, state, _, run = fixture(tmp_path, monkeypatch)
    state.update(fail=True, exit=3)
    run(); run(); run()
    assert state['calls'] == 2
    assert manager.status('zzz')['jobs']['ja']['state'] == 'error'
    manager.action('zzz', 'retry'); state['fail'] = False; run()
    assert state['calls'] == 3 and manager.status('zzz')['jobs']['ja']['state'] == 'complete'


def test_non_object_settings_report_recovery_without_overwriting(tmp_path):
    home = tmp_path / 'local';home.mkdir()
    (home / 'rules.json').write_text('[]', encoding='utf-8')
    manager = auto.AutomaticMobileExports(tmp_path, home=home)
    assert manager.configuration_error
    assert (home / 'rules.json').read_text(encoding='utf-8') == '[]'


def owned_stream(monkeypatch, owner, *, fault='before', entered=None, release=None):
    """Wrap a real owned file; both pre/post-real-close faults are meaningful."""
    original = Path.open
    state = SimpleNamespace(stream=None, opens=0, error=OSError('authored-private-close-sentinel'))

    class Stream:
        def __init__(self, raw):
            self.raw, self.close_calls, self.resource_calls = raw, 0, []

        def seek(self, *args):
            # This observes the handover before initialization/OS locking,
            # including the failed-acquire cleanup path that previously lost it.
            assert owner.stream is self
            self.resource_calls.append('seek')
            return self.raw.seek(*args)

        def write(self, *args):
            self.resource_calls.append('write')
            return self.raw.write(*args)

        def flush(self):
            self.resource_calls.append('flush')
            return self.raw.flush()

        def fileno(self):
            self.resource_calls.append('fileno')
            return self.raw.fileno()

        def close(self):
            assert owner.stream is self
            self.close_calls += 1
            if entered is not None:
                entered.set()
                assert release.wait(5), 'Owned stream close was not released.'
            if fault == 'before':
                raise state.error
            self.raw.close()
            if fault == 'after':
                raise state.error

    def open(path, mode='r', *args, **options):
        if path == owner.path and mode == 'a+b':
            state.opens += 1
            raw = original(path, mode, *args, **options)
            if state.stream is None:
                state.stream = Stream(raw)
                return state.stream
            return raw  # Independent real contenders use ordinary streams.
        return original(path, mode, *args, **options)

    monkeypatch.setattr(Path, 'open', open)
    return state


def assert_poison_refusals(owner, failure, operations):
    original, acquisition = failure.close_error, failure.acquire_error
    close_traceback = original.__traceback__
    acquire_traceback = acquisition.__traceback__ if acquisition is not None else None
    wrappers = []
    before = tuple(failure.stream.resource_calls)
    for operation in operations:
        with pytest.raises(ExportLockCleanupError) as refusal:
            operation()
        wrapper = refusal.value
        wrappers.append(wrapper)
        assert wrapper.owner is owner and wrapper.failure is failure
        assert wrapper.__cause__ is original and str(wrapper) == 'Export lock cleanup remains unconfirmed.'
        assert 'authored-private' not in str(wrapper)
        assert original.__traceback__ is close_traceback
        if acquisition is not None:
            assert acquisition.__traceback__ is acquire_traceback
    assert len({id(wrapper) for wrapper in wrappers}) == len(wrappers)
    assert failure.stream.close_calls == 1 and tuple(failure.stream.resource_calls) == before
    assert owner.stream is failure.stream


def test_real_lock_repeated_acquisition_does_not_replace_owner_and_release_is_reusable(tmp_path):
    path = tmp_path/'owned-queue'
    owner, contender = ExportLock(path), ExportLock(path)
    try:
        assert owner.acquire()
        stream = owner.stream
        assert not owner.acquire() and owner.stream is stream
        assert not contender.acquire() and contender.stream is None
        owner.close()
        assert owner.stream is None and stream.closed
        owner.close()  # Successful close remains idempotent.
        assert contender.acquire()
        assert not owner.acquire() and owner.stream is None
        contender.close()
        assert owner.acquire() and owner.stream is not stream
        owner.close()
        owner.require_released()
    finally:
        owner.close(); contender.close()


@pytest.mark.parametrize('fault', ['before', 'after'])
def test_failed_release_retains_exact_stream_and_error_even_after_real_close(tmp_path, monkeypatch, fault):
    owner, contender = ExportLock(tmp_path/'owned-queue'), ExportLock(tmp_path/'owned-queue')
    state = owned_stream(monkeypatch, owner, fault=fault)
    try:
        assert owner.acquire() and owner.stream is state.stream
        with pytest.raises(ExportLockCleanupError) as error:
            owner.close()
        failure = error.value.failure
        assert failure.stream is state.stream and failure.close_error is state.error
        assert failure.acquire_error is None and failure.close_attempted is True
        assert state.stream.raw.closed is (fault == 'after')
        # A close exception can follow actual OS release. Neither outcome is
        # grounds for the poisoned owner to query/reuse/reclose that stream.
        acquired = contender.acquire()
        assert acquired is (fault == 'after')
        if acquired: contender.close()
        before = state.opens
        assert_poison_refusals(owner, failure, [owner.close, owner.acquire,
            owner.require_released, owner.require_healthy, owner.close, owner.acquire])
        assert state.opens == before
        foreign = tmp_path/'foreign-owned-output'
        foreign.write_bytes(b'previous-complete-output')
        assert_poison_refusals(owner, failure, [owner.close, owner.acquire])
        assert foreign.read_bytes() == b'previous-complete-output'
    finally:
        # Dispose only the owned test fixture after proving no product retry.
        # This raw close is never production cleanup/acceptance evidence.
        if state.stream is not None and not state.stream.raw.closed:
            state.stream.raw.close()
        contender.close()


@pytest.mark.parametrize('fault', ['before', 'after'])
def test_failed_acquire_cleanup_retains_actual_unassigned_stream_and_original_lock_error(tmp_path, monkeypatch, fault):
    path = tmp_path/'owned-queue'
    held = ExportLock(path)
    assert held.acquire()
    owner = ExportLock(path)
    state = owned_stream(monkeypatch, owner, fault=fault)
    try:
        with pytest.raises(ExportLockCleanupError) as error:
            owner.acquire()  # Real OS lock conflict, followed by close fault.
        failure = error.value.failure
        assert failure.stream is state.stream is owner.stream
        assert isinstance(failure.acquire_error, OSError)
        assert failure.acquire_error is not state.error
        assert failure.close_error is state.error and state.stream.close_calls == 1
        assert state.stream.raw.closed is (fault == 'after')
        held.close()
        probe = ExportLock(path)
        assert probe.acquire()  # Busy acquisition never obtained the lock.
        probe.close()
        before = state.opens
        assert_poison_refusals(owner, failure, [owner.acquire, owner.close,
            owner.require_released, owner.acquire, owner.close])
        assert state.opens == before
    finally:
        held.close()
        if state.stream is not None and not state.stream.raw.closed:
            state.stream.raw.close()


def test_close_in_flight_has_one_actual_attempt_and_does_not_serialize_native_io_under_metadata(tmp_path, monkeypatch):
    owner = ExportLock(tmp_path/'owned-queue')
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    state = owned_stream(monkeypatch, owner, fault='before', entered=entered, release=release)
    assert owner.acquire()
    failures = []
    def close():
        try: owner.close()
        except BaseException as error: failures.append(error)
        finally: finished.set()
    thread = threading.Thread(target=close)
    thread.start()
    try:
        assert entered.wait(1)
        assert not finished.is_set() and owner.stream is state.stream
        start = time.monotonic()
        with pytest.raises(RuntimeError, match='still owned'): owner.close()
        with pytest.raises(RuntimeError, match='still owned'): owner.require_released()
        assert not owner.acquire()
        assert time.monotonic()-start < .2
        assert state.stream.close_calls == 1
        release.set()
        assert finished.wait(1)
        assert len(failures) == 1 and isinstance(failures[0], ExportLockCleanupError)
        assert_poison_refusals(owner, failures[0].failure, [owner.acquire, owner.close])
    finally:
        release.set(); thread.join(5)
        assert not thread.is_alive()
        if not state.stream.raw.closed: state.stream.raw.close()


@pytest.mark.parametrize('fault', ['before', 'after'])
@pytest.mark.parametrize('acquire_busy', [False, True])
def test_dead_automatic_loop_cannot_hide_close_or_failed_acquire_cleanup_and_previous_outputs_survive(
        tmp_path, monkeypatch, fault, acquire_busy):
    manager, _, destination, run = fixture(tmp_path, monkeypatch)
    run()  # Actual existing publication code with authored process/candidate.
    before = {p.relative_to(destination): p.read_bytes() for p in destination.rglob('*.zip')}
    rules = manager.path.read_bytes()
    manager.configuration_error = 'authored-configuration-refusal'
    held = ExportLock(manager.owner.path)
    if acquire_busy: assert held.acquire()
    state = owned_stream(monkeypatch, manager.owner, fault=fault)
    try:
        manager.start()
        thread = manager.thread
        thread.join(2)
        assert not thread.is_alive() and manager.stop.is_set()
        failure = manager.owner._failure
        assert failure.stream is state.stream and failure.close_error is state.error
        assert (failure.acquire_error is not None) is acquire_busy
        assert state.stream.close_calls == 1
        assert_poison_refusals(manager.owner, failure,
            [manager.close, manager.start, manager.owner.acquire, manager.close, manager.start])
        assert manager.thread is thread  # No replacement loop was admitted.
        assert manager.path.read_bytes() == rules
        assert {p.relative_to(destination): p.read_bytes() for p in destination.rglob('*.zip')} == before
    finally:
        held.close()
        if state.stream is not None and not state.stream.raw.closed: state.stream.raw.close()


def test_timed_out_handoff_keeps_real_automatic_close_until_stream_attempt_returns(tmp_path, monkeypatch):
    from backend.api import Runtime
    manager, _, _, _ = fixture(tmp_path, monkeypatch)
    manager.configuration_error = 'authored-configuration-refusal'
    entered, release = threading.Event(), threading.Event()
    state = owned_stream(monkeypatch, manager.owner, fault='before', entered=entered, release=release)
    async def run():
        runtime = Runtime.__new__(Runtime)
        runtime._handoff_drains = []
        manager.start()
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            thread = manager.thread
            manager.start()  # Healthy in-flight existing loop remains idempotent.
            assert manager.thread is thread
            with pytest.raises(TimeoutError):
                await runtime._handoff_step(manager.close, time.monotonic()+.03, blocking=True)
            drain, = runtime._handoff_drains
            assert not drain.done() and thread.is_alive() and state.stream.close_calls == 1
            release.set()
            with pytest.raises(ExportLockCleanupError): await drain
            assert not thread.is_alive()
            assert_poison_refusals(manager.owner, manager.owner._failure, [manager.close, manager.start])
        finally:
            release.set()
            await asyncio.to_thread(manager.thread.join, 5)
            for task in runtime._handoff_drains:
                if not task.done():
                    with pytest.raises(ExportLockCleanupError): await task
    try:
        asyncio.run(run())
    finally:
        release.set()
        if state.stream is not None and not state.stream.raw.closed: state.stream.raw.close()


def test_open_factory_failure_without_a_returned_stream_keeps_original_error_and_allows_retry(tmp_path, monkeypatch):
    owner = ExportLock(tmp_path/'owned-queue')
    original = Path.open
    failure, attempts = OSError('authored-open-failure'), []
    def open(path, mode='r', *args, **options):
        if path == owner.path and mode == 'a+b':
            attempts.append(True)
            if len(attempts) == 1: raise failure
        return original(path, mode, *args, **options)
    monkeypatch.setattr(Path, 'open', open)
    with pytest.raises(OSError) as error: owner.acquire()
    assert error.value is failure and owner.stream is None
    owner.require_released()
    try:
        assert owner.acquire() and len(attempts) == 2
        stream = owner.stream
        owner.close()
        assert stream.closed and owner.stream is None
        owner.require_released()
    finally:
        owner.close()


def test_healthy_automatic_lifecycle_releases_real_lock_and_keeps_start_idempotent(tmp_path, monkeypatch):
    manager = auto.AutomaticMobileExports(tmp_path, home=tmp_path/'owned-local')
    entered = threading.Event()
    reconcile = manager.reconcile
    def observe():
        reconcile(); entered.set()
    monkeypatch.setattr(manager, 'reconcile', observe)
    contender = ExportLock(manager.owner.path)
    previous = None
    try:
        for _ in range(2):
            entered.clear()
            manager.start()
            thread = manager.thread
            assert thread is not previous and entered.wait(1)
            manager.start()
            assert manager.thread is thread and thread.is_alive()
            assert not contender.acquire()
            stream = manager.owner.stream
            manager.close()
            assert not thread.is_alive() and stream.closed and manager.owner.stream is None
            assert contender.acquire()
            contender.close()
            previous = thread
    finally:
        manager.close(); contender.close()


def test_loop_body_error_is_preserved_through_failed_owner_close_without_traceback_growth(tmp_path, monkeypatch):
    manager = auto.AutomaticMobileExports(tmp_path, home=tmp_path/'owned-local')
    body = RuntimeError('authored-loop-body-failure')
    def fail(): raise body
    monkeypatch.setattr(manager, 'reconcile', fail)
    state = owned_stream(monkeypatch, manager.owner, fault='before')
    try:
        manager.start(); manager.thread.join(2)
        assert not manager.thread.is_alive()
        failure = manager.owner._failure
        assert failure.close_error is state.error and state.error.__context__ is body
        traceback = body.__traceback__
        assert_poison_refusals(manager.owner, failure, [manager.close, manager.start, manager.close])
        assert body.__traceback__ is traceback and state.error.__context__ is body
    finally:
        if state.stream is not None and not state.stream.raw.closed: state.stream.raw.close()
