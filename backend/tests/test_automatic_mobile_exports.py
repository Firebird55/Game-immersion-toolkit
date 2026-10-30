import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from backend import automatic_mobile_export as auto
from backend.export_lock import ExportLock


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
    decoder = tmp_path / 'data/voice-assets/vgmstream/vgmstream-cli.exe'
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
