"""Scoped behavior fixtures; real extracted Job/handle cases run on Windows."""
import io
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from backend import bundle_entry, runtime_host
from backend.runtime_bundle import RuntimeLayout


@pytest.fixture
def normal_slot(tmp_path, monkeypatch):
    """Authored immutable bytes + genuine HTTP; Win32 creations are typed doubles."""
    from backend.tests.test_desktop_frontend import immutable_slot
    from backend.bundle_host import create_synthetic_root
    from backend.desktop_frontend import DesktopFrontendServer
    from backend.windows_preparation_process import _SuspendedChild
    layout, pin = immutable_slot(tmp_path,'owned-normal')
    layout.executable.write_bytes(b'authored placeholder; not a native runtime')
    disposable = create_synthetic_root(tmp_path/'disposable-normal')
    root = disposable.path
    layout = replace(layout, settings_root=root/'settings',data_root=root/'data',cache_root=root/'cache',
        work_root=root/'cache/work',tool_root=root/'tools',state_root=root/'state',default_export_root=root/'exports')
    state = SimpleNamespace(ready=True,create_failure=None,post_create_failure=False,alias=False,
        stop_errors={},close_errors={},job_close_error=None,observer_close_error=None,foreign=False,
        unknown=False,unknown_transient=False,exit_after_http=False,remap_after_http=False,delay_body=False,
        requested=threading.Event(),release=threading.Event(),calls=[])
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*_args): pass
        def do_GET(self):
            assert self.path == '/api/runtime/ready'
            payload=json.dumps({'ready':state.ready,'standby':True}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(payload)))
            self.send_header('Content-Type','application/json');self.end_headers()
            state.requested.set()
            if state.delay_body: state.release.wait(3)
            try:self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError):pass
            if state.exit_after_http:state.tree.created_children[0].exited=True
            if state.remap_after_http:state.foreign=True
    api=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    frontend=DesktopFrontendServer(layout.resource_root/'desktop',0)
    threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (api,frontend)]
    for thread in threads:thread.start()
    files=[{'path':path.relative_to(layout.application_root).as_posix(),'bytes':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
           for path in layout.application_root.rglob('*') if path.is_file()]
    directories=[path.relative_to(layout.application_root).as_posix()
                 for path in layout.application_root.rglob('*') if path.is_dir()]
    class Child(_SuspendedChild):
        def __init__(self,owner,role):
            super().__init__(owner);self.role,self.pid,self.handle=role,101+len(owner.created_children),object()
            self.created,self._admitted=True,True
        @property
        def process_handle(self):
            if self.closed:raise OSError('Authored closed creation handle')
            return self.handle
        def resume_once(self):
            assert not self.resumed and not self.closed
            state.calls.append(('resume',self.role));self.resumed=True
        def stop_and_wait(self,deadline):
            state.calls.append(('stop',self.role,deadline))
            if self.role in state.stop_errors:raise state.stop_errors[self.role]
            if time.monotonic()>=deadline:raise TimeoutError('Authored absolute cleanup deadline')
            self.exited=True
        def close_after_exit(self):
            if self.closed:return
            assert self.exited
            state.calls.append(('close-child',self.role))
            if self.role in state.close_errors:raise state.close_errors[self.role]
            self.closed=True
    class Kernel:
        def OpenProcess(self,_access,_inherit,pid):
            state.calls.append(('observe',pid))
            return SimpleNamespace(target=next((child for child in state.tree.created_children if child.pid==pid),None))
        def IsProcessInJob(self,observer,_job,result):
            result._obj.value=observer.target is not None;return True
        def WaitForSingleObject(self,handle,_timeout):
            target=handle.target if isinstance(handle,SimpleNamespace) else next(
                (child for child in state.tree.created_children if child.handle is handle),None)
            return 0 if target is not None and target.exited else 258
        def CloseHandle(self,handle):
            state.calls.append(('close-observer',handle))
            return state.observer_close_error is None
    class Tree:
        def __init__(self):
            self.kernel,self.handle,self._lifecycle,self.created_children=Kernel(),object(),threading.RLock(),[]
            self._admission_closed=False;state.tree=self
        def create_suspended(self,command,**options):
            role=command[2]
            child=Child(self,role);self.created_children.append(child)
            state.calls.append(('create',role,command,options))
            if state.create_failure is not None and role=='api':
                if not state.post_create_failure:child.created=False;child.closed=True
                raise state.create_failure
            if state.alias and role=='api':child.handle=self.created_children[0].handle
            return child
        def _process_ids(self,deadline):
            if time.monotonic()>=deadline:raise TimeoutError('Authored absolute census deadline')
            active=[child.pid for child in self.created_children if child.created and not child.exited]
            return active+([999] if state.unknown and (active or not state.unknown_transient) else [])
        def close(self):
            state.calls.append(('close-job',))
            if state.job_close_error is not None:raise state.job_close_error
            assert all(child.closed for child in self.created_children)
            self.handle=None
    monkeypatch.setattr(runtime_host,'WindowsPreparationProcess',Tree)
    monkeypatch.setattr(runtime_host,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(runtime_host,'_standby_system_environment',lambda:{'SystemRoot':'AUTHORED_OS','PATH':'AUTHORED_OS'})
    monkeypatch.setattr(runtime_host,'same_process_object',lambda first,second:
        (first.target.handle if isinstance(first,SimpleNamespace) and first.target is not None else first) is second)
    def listeners(ports):
        assert set(ports)=={api.server_port,frontend.server_port}
        return {api.server_port:{999 if state.foreign else 102},frontend.server_port:{101}}
    monkeypatch.setattr(runtime_host,'listener_processes',listeners)
    def make(**options):
        arguments=dict(disposable=disposable,inventory_files=files,inventory_directories=directories,
            trusted_manifest_sha256=pin,api_port=api.server_port,frontend_port=frontend.server_port)
        arguments.update(options)
        return runtime_host.OwnedStandbySlot(layout,**arguments)
    yield SimpleNamespace(make=make,layout=layout,root=disposable,state=state,api=api,frontend=frontend,
        files=files,directories=directories,pin=pin,child_type=Child)
    state.release.set()
    for server in (api,frontend):server.shutdown();server.server_close()
    for thread in threads:thread.join(2);assert not thread.is_alive()


def test_normal_standby_owns_fixed_real_commands_before_resume_and_actual_http_identity(normal_slot,monkeypatch):
    value=normal_slot;monkeypatch.setenv('LEXIRISE_API_KEY','authored-parent-key-must-not-be-inherited')
    owner=value.make();assert owner.start(timeout=2) is owner and owner.ready
    calls=value.state.calls;creates=[call for call in calls if call[0]=='create']
    assert len(creates)==2 and calls.index(creates[1])<next(i for i,call in enumerate(calls) if call[0]=='resume')
    assert creates[0][2]==value.layout.child_command('frontend',['--port',str(value.frontend.server_port)])
    assert creates[1][2]==value.layout.child_command('api',['--port',str(value.api.server_port),'--standby','--candidate-closed'])
    assert all('--runtime-probe' not in call[2] for call in creates)
    for _,_,_,options in creates:
        assert options['detached_console'] is True
        assert options['env']['LOCALAPPDATA']==str(value.root.path/'host-profile')
        assert options['env']['TEMP']==str(value.root.path/'host-temp')
        assert not {'LEXIRISE_API_KEY','PYTHONPATH','HTTP_PROXY'} & set(options['env'])
    children=tuple(owner.children.values());tree=owner.tree
    owner.close(timeout=2)
    assert owner.closed and owner.cleanup_confirmed and not owner.recovery_required and not owner.errors
    assert owner.tree is tree and all(child.closed and child.exited for child in children)
    assert not owner.scratch.exists()
    count=len(calls);owner.close();assert len(calls)==count
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start()


def test_normal_standby_waits_for_both_owned_listeners_without_treating_startup_progress_as_http_change(normal_slot,monkeypatch):
    value=normal_slot;owner=value.make();observations=[]
    def listeners(ports):
        observations.append(value.state.requested.is_set())
        if len(observations)==1:return {value.frontend.server_port:{101}}
        return {value.api.server_port:{102},value.frontend.server_port:{101}}
    monkeypatch.setattr(runtime_host,'listener_processes',listeners)
    owner.start(timeout=2)
    assert owner.ready and observations==[False,False,False,True]
    assert not owner.errors and not owner.recovery_required
    owner.close(timeout=2)
    assert owner.closed and owner.cleanup_confirmed


def test_normal_standby_missing_listener_interval_still_refuses_new_foreign_binding_before_http(normal_slot,monkeypatch):
    value=normal_slot;owner=value.make();observations=[]
    def listeners(ports):
        observations.append(tuple(ports))
        if len(observations)==1:return {value.frontend.server_port:{101}}
        return {value.api.server_port:{999},value.frontend.server_port:{101}}
    monkeypatch.setattr(runtime_host,'listener_processes',listeners)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert len(observations)==2 and not value.state.requested.is_set()
    assert owner.recovery_required and not owner.ready
    assert all(call[1] in {'api','frontend'} for call in value.state.calls if call[0]=='stop')


def test_normal_standby_retains_actual_job_before_partial_constructor_close_poison_without_retry(normal_slot,monkeypatch):
    from backend import windows_preparation_process as process
    value=normal_slot;owner=value.make();handle=object();calls=[]
    set_error,close_error=OSError('Authored Job configuration failure'),OSError('Authored Job constructor close failure')
    errors=iter((set_error,close_error))
    class Kernel:
        def CreateJobObjectW(self,*_args):calls.append('create-job');return handle
        def SetInformationJobObject(self,*_args):calls.append('set-info');return False
        def CloseHandle(self,actual):
            assert actual is handle
            calls.append('close-job');return False
    monkeypatch.setattr(process,'_kernel',lambda:Kernel())
    monkeypatch.setattr(process.ctypes,'get_last_error',lambda:6,raising=False)
    monkeypatch.setattr(process.ctypes,'WinError',lambda _code:next(errors),raising=False)
    monkeypatch.setattr(runtime_host,'WindowsPreparationProcess',process.WindowsPreparationProcess)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    tree=owner.tree
    assert type(tree) is process.WindowsPreparationProcess and tree._handle is handle
    assert tree._ownership_unconfirmed and not owner._tree_constructed
    assert any(current is close_error for _,current in owner.errors) and close_error.__context__ is set_error
    assert owner.recovery_required and not owner.cleanup_confirmed and not owner.closed
    assert calls==['create-job','set-info','close-job']
    with pytest.raises(OSError):_=tree.handle
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert calls==['create-job','set-info','close-job']


@pytest.mark.parametrize('after',[False,True])
def test_normal_standby_keeps_and_cleans_actual_second_creation_record_on_failure(normal_slot,after):
    value=normal_slot;error=OSError('Authored creation failure')
    value.state.create_failure,value.state.post_create_failure=error,after
    owner=value.make()
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert owner.recovery_required and any(current is error for _,current in owner.errors)
    assert len(owner.children)==2 and all(child.closed for child in owner.children.values())
    assert not any(call[0]=='resume' for call in value.state.calls)
    assert owner.scratch.exists() and owner.cleanup_confirmed and not owner.closed
    count=len(value.state.calls)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close()
    assert len(value.state.calls)==count


@pytest.mark.parametrize('fault',['foreign-listener','aliased-creation','unknown-member'])
def test_normal_standby_refuses_observation_as_creation_authority_and_never_kills_unknown(normal_slot,fault):
    value=normal_slot
    setattr(value.state,{'foreign-listener':'foreign','aliased-creation':'alias','unknown-member':'unknown'}[fault],True)
    owner=value.make()
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert owner.recovery_required and not owner.ready and not owner.closed
    assert not value.state.requested.is_set()
    assert all(call[1] in {'api','frontend'} for call in value.state.calls if call[0]=='stop')
    if fault!='foreign-listener':assert owner.tree.handle is not None and not owner.cleanup_confirmed
    if fault=='aliased-creation':assert not any(call[0] in {'stop','close-child'} for call in value.state.calls)


def test_normal_standby_cleanup_errors_are_independent_sticky_and_never_retried(normal_slot):
    value=normal_slot;owner=value.make();owner.start(timeout=2)
    stop_error,close_error=OSError('Authored frontend stop failure'),OSError('Authored API handle close failure')
    value.state.stop_errors['frontend']=stop_error;value.state.close_errors['api']=close_error
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    assert {id(error) for _,error in owner.errors}>={id(stop_error),id(close_error)}
    assert [call[1] for call in value.state.calls if call[0]=='stop']==['frontend','api']
    assert owner.tree.handle is not None and owner.scratch.exists() and not owner.cleanup_confirmed
    calls=len(value.state.calls)
    for _ in range(2):
        with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    assert len(value.state.calls)==calls


def test_normal_standby_absolute_deadline_covers_real_http_and_failed_cleanup_without_reset(normal_slot):
    value=normal_slot;owner=value.make();value.state.delay_body=True
    errors=[]
    def start():
        try:owner.start(timeout=.2)
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=start);begin=time.monotonic();thread.start()
    assert value.state.requested.wait(1)
    thread.join(1)
    assert not thread.is_alive() and time.monotonic()-begin<1
    assert errors and isinstance(errors[0],runtime_host.OwnedStandbySlotError)
    assert owner.recovery_required and not owner.ready and owner.tree.handle is not None
    deadlines=[call[2] for call in value.state.calls if call[0]=='stop']
    assert len(deadlines)==2 and deadlines[0]==deadlines[1] and deadlines[0]<=begin+.3


@pytest.mark.parametrize('options',[{'api_port':True},{'api_port':0},{'api_port':3000},
    {'frontend_port':8766},{'trusted_manifest_sha256':'invalid'},{'inventory_files':[]},
    {'inventory_directories':['../outside']}])
def test_normal_standby_refuses_unbounded_or_self_authorizing_inputs_before_creation(normal_slot,options):
    with pytest.raises(RuntimeError):normal_slot.make(**options)
    assert normal_slot.state.calls==[]


@pytest.mark.parametrize('fault',['extra','changed','missing','alias'])
def test_normal_standby_checks_complete_inventory_before_any_native_creation(normal_slot,fault):
    value=normal_slot
    if fault=='alias':
        value.files.append({**value.files[0],'path':value.files[0]['path'].upper()})
        with pytest.raises(RuntimeError):value.make()
    else:
        owner=value.make()
        if fault=='extra':(value.layout.application_root/'unlisted.txt').write_bytes(b'owned unexpected bytes')
        elif fault=='changed':value.layout.executable.write_bytes(b'changed authored executable')
        else:value.layout.executable.unlink()
        with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
        assert owner.tree is None and owner.recovery_required
    assert value.state.calls==[]


def test_normal_standby_root_first_link_refusal_never_reads_descendant_metadata(normal_slot,monkeypatch):
    value=normal_slot;owner=value.make()
    link=value.layout.resource_root/'desktop'
    held=link.parent.parent.parent/'held-authored-desktop'
    link.rename(held);link.symlink_to(held,target_is_directory=True)
    calls=[];original_lstat,original_open=Path.lstat,Path.open
    def lstat(path,*args,**kwargs):
        if link in path.parents:calls.append('descendant-lstat')
        return original_lstat(path,*args,**kwargs)
    def opened(path,*args,**kwargs):
        if link in path.parents:calls.append('descendant-open')
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat);monkeypatch.setattr(Path,'open',opened)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert calls==[] and value.state.calls==[]


@pytest.mark.parametrize('field',['exit_after_http','remap_after_http'])
def test_normal_standby_real_http_success_cannot_outlive_its_creation_or_listener(normal_slot,field):
    value=normal_slot;setattr(value.state,field,True);owner=value.make()
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert value.state.requested.is_set() and owner.recovery_required and not owner.ready
    assert owner.errors and not owner.closed


def test_normal_standby_failed_observer_close_is_retained_and_no_raw_handle_is_reused(normal_slot,monkeypatch):
    value=normal_slot;value.state.observer_close_error=OSError('Authored observer close failure')
    monkeypatch.setattr(runtime_host.ctypes,'get_last_error',lambda:6,raising=False)
    owner=value.make()
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert owner.unconfirmed_observers and any(getattr(error,'winerror',None)==6 for _,error in owner.errors)
    assert owner.tree.handle is not None and not owner.cleanup_confirmed
    count=len(value.state.calls)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close()
    assert len(value.state.calls)==count


def test_normal_standby_job_close_failure_retains_exact_owner_and_original_error_without_retry(normal_slot):
    value=normal_slot;owner=value.make();owner.start(timeout=2)
    error=OSError('Authored Job close failure');value.state.job_close_error=error;tree=owner.tree;handle=tree.handle
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    assert owner.tree is tree and tree.handle is handle and any(current is error for _,current in owner.errors)
    assert sum(call[0]=='close-job' for call in value.state.calls)==1
    traceback=error.__traceback__
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    assert sum(call[0]=='close-job' for call in value.state.calls)==1
    assert error.__traceback__ is traceback


def test_normal_standby_control_lock_deadline_poison_is_sticky_without_late_creation(normal_slot):
    value=normal_slot;owner=value.make();errors=[];finished=threading.Event()
    def worker():
        try:owner.start(timeout=.05)
        except BaseException as error:errors.append(error)
        finally:finished.set()
    owner._operation.acquire()
    thread=threading.Thread(target=worker);thread.start()
    try:assert finished.wait(.5)
    finally:owner._operation.release();thread.join(1)
    assert errors and isinstance(errors[0],runtime_host.OwnedStandbySlotError)
    assert owner.recovery_required and not owner.ready and owner.tree is None
    assert any(stage=='control-lock' and isinstance(error,TimeoutError) for stage,error in owner.errors)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.start(timeout=2)
    assert value.state.calls==[]


def test_normal_standby_private_scratch_cleanup_failure_is_not_complete_or_retried(normal_slot,monkeypatch):
    value=normal_slot;owner=value.make();owner.start(timeout=2)
    error=OSError('Authored scratch cleanup failure');attempts=[]
    def failed(path):attempts.append(path);raise error
    monkeypatch.setattr(runtime_host.shutil,'rmtree',failed)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    assert attempts==[owner.scratch] and owner.scratch.exists()
    assert not owner.cleanup_confirmed and not owner.closed and owner.recovery_required
    assert any(current is error for _,current in owner.errors)
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close()
    assert attempts==[owner.scratch]


def test_normal_standby_observes_unknown_member_before_parent_stop_cannot_hide_its_exit(normal_slot):
    value=normal_slot;owner=value.make();owner.start(timeout=2)
    value.state.unknown=value.state.unknown_transient=True
    with pytest.raises(runtime_host.OwnedStandbySlotError):owner.close(timeout=2)
    assert all(child.closed and child.exited for child in owner.children.values())
    assert owner.tree.handle is not None and not owner.cleanup_confirmed
    assert not any(call[0]=='close-job' for call in value.state.calls)
    assert owner._membership_unconfirmed and owner.recovery_required


@pytest.fixture
def layout(tmp_path, monkeypatch):
    app, private = tmp_path/'app', tmp_path/'private'
    app.mkdir(); (app/'ProxyTranscriptRuntime.exe').write_bytes(b'authored-image-placeholder')
    state = private/'host-v1'; state.mkdir(parents=True)
    (state/'synthetic-probe.json').write_text(json.dumps({'build_id': 'host-fixture', 'synthetic': True}))
    value = RuntimeLayout(mode='bundle', profile='runtime-experiment', application_root=app,
        resource_root=app/'_internal', executable=app/'ProxyTranscriptRuntime.exe', data_root=private/'data-v1',
        settings_root=private, cache_root=private/'cache-v1', tool_root=private/'tools-v1',
        work_root=private/'cache-v1/work', state_root=state, default_export_root=private/'exports',
        build_id='host-fixture', source_commit='a'*40, children=('frontend', 'api', 'windows-bootstrap'))
    monkeypatch.setattr(runtime_host, 'sys', SimpleNamespace(platform='win32', stdin=io.StringIO('normal\nstop\n')))
    monkeypatch.setattr(runtime_host, 'developer_environment', lambda: None)
    return value


@pytest.fixture
def owned(layout, monkeypatch):
    calls = []
    class Kernel:
        def OpenProcess(self, _access, _inherit, pid): return pid
        def IsProcessInJob(self, _handle, _job, result):
            result._obj.value = True
            return True
        def WaitForSingleObject(self, _handle, _timeout): return 258
        def CloseHandle(self, _handle): return True
    class Tree:
        kernel, handle = Kernel(), 123
        def command(self, command):
            calls.append(('wrap', command))
            return ['fixed-bootstrap', *command]
        def _process_ids(self, _deadline): return [101, 102, 103, 104]
        def terminate(self, timeout): calls.append('job-drain')
        def close(self): calls.append('job-close')
    class Process:
        def __init__(self, command, **options):
            self.role = 'frontend' if 'frontend' in command else 'api'
            self.code = None
            calls.append(('spawn', self.role, command, options))
        def poll(self): return self.code
        def kill(self):
            calls.append(('kill-bootstrap', self.role)); self.code = 1
        def wait(self, timeout):
            calls.append(('reap-bootstrap', self.role)); return self.code
    monkeypatch.setattr(runtime_host, 'WindowsPreparationProcess', Tree)
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: {3000: {102}, 8766: {104}})
    monkeypatch.setattr(runtime_host, 'subprocess', SimpleNamespace(Popen=Process,
        CREATE_NO_WINDOW=0, DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired))
    return runtime_host.FrozenProbeHost(layout), calls


def test_fixed_children_keep_bootstraps_and_job_until_real_drain(owned, layout):
    host, calls = owned
    host.start()
    assert host.members() == [101, 102, 103, 104]
    wrapped = [call[1] for call in calls if isinstance(call, tuple) and call[0] == 'wrap']
    assert wrapped == [layout.child_command('frontend', ['--port', '3000']),
        [str(layout.executable), '--runtime-probe', 'api']]
    for call in calls:
        if isinstance(call, tuple) and call[0] == 'spawn':
            options = call[3]
            assert options['cwd'].is_relative_to(layout.work_root)
            assert options['env']['PROXY_TRANSCRIPT_SETTINGS_ROOT'] == str(layout.settings_root)
    scratch = host.scratch
    host.close()
    assert calls[-6:] == [('kill-bootstrap', 'frontend'), ('reap-bootstrap', 'frontend'),
        ('kill-bootstrap', 'api'), ('reap-bootstrap', 'api'), 'job-drain', 'job-close']
    assert host.closed and host.tree is None and not scratch.exists()
    host.close()
    with pytest.raises(runtime_host.HostProbeFailure): host.start()


def test_partial_start_failure_still_reaps_bootstrap_and_job(owned, monkeypatch):
    host, calls = owned
    spawn = runtime_host.subprocess.Popen
    def fail_second(command, **options):
        if command[-1] == 'api': raise OSError('authored API spawn failure')
        return spawn(command, **options)
    monkeypatch.setattr(runtime_host.subprocess, 'Popen', fail_second)
    with pytest.raises(OSError): host.start()
    host.close()
    assert ('reap-bootstrap', 'frontend') in calls
    assert calls[-2:] == ['job-drain', 'job-close'] and host.closed


def test_failed_job_drain_retains_ownership_and_private_logs(owned, monkeypatch):
    host, calls = owned
    host.start()
    tree = host.tree
    def fail(**_): raise TimeoutError('authored unconfirmed native cleanup')
    monkeypatch.setattr(tree, 'terminate', fail)
    with pytest.raises(runtime_host.HostProbeFailure, match='owned-cleanup-unconfirmed'): host.close()
    assert host.tree is tree and not host.closed and host.scratch.exists()
    assert 'job-close' not in calls


@pytest.mark.parametrize('invalid_handle', [False, True])
def test_failed_native_job_close_keeps_host_unclosed_until_owned_retry(owned, monkeypatch, invalid_handle):
    import ctypes
    from backend.windows_preparation_process import WindowsPreparationProcess
    host, calls = owned
    host.start()
    original = host.tree
    owner = WindowsPreparationProcess.__new__(WindowsPreparationProcess)
    owner._handle = object()
    exact_handle = owner.handle
    attempts = []
    protection = {'enabled': True}
    def close(handle):
        attempts.append(handle)
        return not protection['enabled']
    def protected(_handle, flags):
        flags._obj.value = 2 if protection['enabled'] else 0
        return 1
    owner.kernel = SimpleNamespace(CloseHandle=close, GetHandleInformation=protected)
    owner.terminate = original.terminate
    host.tree = owner
    scratch = host.scratch
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 6 if invalid_handle else 5, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda error: OSError(error, 'authored close failure'), raising=False)
    with pytest.raises(runtime_host.HostProbeFailure, match='owned-cleanup-unconfirmed'):
        host.close()
    assert host.tree is owner
    assert not host.closed and scratch.exists() and attempts == [exact_handle]
    if invalid_handle:
        with pytest.raises(OSError, match='ownership is unconfirmed'):
            _ = owner.handle
        # Retry the actual owner drain. Its poisoned guard must stop before
        # invoking any kernel method with the potentially recycled value.
        owner.terminate = WindowsPreparationProcess.terminate.__get__(owner)
        with pytest.raises(runtime_host.HostProbeFailure, match='owned-cleanup-unconfirmed'):
            host.close()
        assert not host.closed and host.tree is owner and scratch.exists()
        assert attempts == [exact_handle] and calls.count('job-drain') == 1
        return
    assert owner.handle is exact_handle
    protection['enabled'] = False
    host.close()
    assert host.closed and host.tree is None and owner.handle is None
    assert not scratch.exists() and attempts == [exact_handle, exact_handle]
    assert calls.count('job-drain') == 2


def test_exit_frontend_uses_retained_handle_and_monitor_stops_slot(owned):
    host, calls = owned
    host.start()
    try:
        with pytest.raises(runtime_host.HostProbeFailure, match='child-exited'):
            host.monitor(io.StringIO('exit-frontend\n'))
        assert calls.count(('kill-bootstrap', 'frontend')) == 1
    finally:
        host.close()
    assert ('reap-bootstrap', 'api') in calls and calls[-1] == 'job-close'


def test_readiness_refusal_cannot_be_replaced_by_a_live_process(owned, monkeypatch):
    host, _ = owned
    host.start()
    monkeypatch.setattr(host, '_json', lambda *_: {'ready': False})
    try:
        with pytest.raises(runtime_host.HostProbeFailure, match='readiness-deadline'):
            host.wait_services(timeout=.001)
        with pytest.raises(runtime_host.HostProbeFailure, match='unprepared-index-deadline'):
            host.wait_unprepared_index(timeout=.001)
    finally:
        host.close()


def test_existing_private_roots_and_experimental_image_are_required(layout, monkeypatch):
    (layout.state_root/'synthetic-probe.json').unlink()
    with pytest.raises(RuntimeError, match='synthetic roots'): runtime_host.FrozenProbeHost(layout)
    monkeypatch.setattr(runtime_host, 'sys', SimpleNamespace(platform='darwin'))
    with pytest.raises(runtime_host.HostProbeFailure, match='experimental-windows-image-required'):
        runtime_host.FrozenProbeHost(layout)


def test_frozen_entry_uses_fixed_host_probe_without_new_child_target(layout, monkeypatch):
    modules = []
    monkeypatch.setattr(bundle_entry, 'discover_layout', lambda: layout)
    def module(name):
        modules.append(name)
        return SimpleNamespace(main=lambda kind, current: 7 if kind == 'host' and current is layout else 99)
    monkeypatch.setattr(bundle_entry, 'import_module', module)
    assert bundle_entry.main(['--runtime-probe', 'host']) == 7
    assert modules == ['backend.runtime_host']
    assert 'host' not in bundle_entry.CHILD_TARGETS


def test_foreign_ready_listener_is_refused_while_own_bootstraps_are_alive(owned, monkeypatch):
    host, calls = owned
    host.start()
    def foreign(_handle, _job, result):
        result._obj.value = False
        return True
    monkeypatch.setattr(host.tree.kernel, 'IsProcessInJob', foreign)
    monkeypatch.setattr(host, '_json', lambda *_: pytest.fail('Foreign readiness must never be consulted'))
    try:
        assert all(process.poll() is None for process in host.processes.values())
        with pytest.raises(runtime_host.HostProbeFailure, match='foreign-canonical-listener'):
            host.wait_services(timeout=.01)
    finally:
        host.close()
    assert calls.count(('kill-bootstrap', 'frontend')) == 1
    assert calls.count(('kill-bootstrap', 'api')) == 1


def test_listener_identity_is_rechecked_before_readiness_is_accepted(owned, monkeypatch):
    host, _ = owned
    host.start()
    observations = iter([{3000: {102}, 8766: {104}}, {3000: {999}, 8766: {104}}])
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: next(observations))
    monkeypatch.setattr(host, '_json', lambda *_: {'ready': True})
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'x'
    monkeypatch.setattr(runtime_host, 'urlopen', lambda *_a, **_k: Response())
    try:
        with pytest.raises(runtime_host.HostProbeFailure, match='listener-ownership-changed'):
            host.wait_services(timeout=.01)
    finally:
        host.close()


@pytest.fixture
def registered(layout, monkeypatch):
    """Separate fake-native fixture; it does not certify Windows execution."""
    calls, members, exited = [], {101, 102}, set()
    class Kernel:
        def OpenProcess(self, _access, _inherit, pid):
            calls.append(('observe', pid)); return pid+1000
        def IsProcessInJob(self, observer, _job, result):
            result._obj.value = observer-1000 in members
            return True
        def WaitForSingleObject(self, handle, _timeout): return 0 if handle in exited else 258
        def CloseHandle(self, handle): calls.append(('close-observer', handle)); return True
    class Child:
        def __init__(self, pid): self.pid, self.process_handle, self.resumed = pid, pid, False
        def resume_once(self):
            calls.append(('resume', self.pid)); self.resumed = True
        def stop_and_wait(self, _deadline):
            calls.append(('stop', self.pid)); exited.add(self.pid); members.discard(self.pid)
    class Tree:
        kernel, handle, _lifecycle = Kernel(), 123, threading.RLock()
        def create_suspended(self, command, **options):
            pid = 101+sum(isinstance(call, tuple) and call[0] == 'create' for call in calls)
            calls.append(('create', pid, command, options)); return Child(pid)
        def _process_ids(self, _deadline): return sorted(members)
        def terminate(self, _timeout): pytest.fail('Unknown cohort must never enter generic drain')
        def close(self):
            assert exited == {101, 102}
            calls.append('job-close')
    monkeypatch.setattr(runtime_host, 'WindowsPreparationProcess', Tree)
    monkeypatch.setattr(runtime_host, 'same_process_object', lambda observer, creation: observer-1000 == creation)
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda *_: {3000: {101}, 8766: {102}})
    return runtime_host.FrozenProbeHost(layout), calls, members


def test_registered_cohort_is_created_before_any_resume_and_closed_after_signals(registered, layout):
    host, calls, _ = registered
    host.start_registered()
    assert [call[0] for call in calls].count('create') == 2
    assert not any(call[0] == 'resume' for call in calls)
    host.resume_registered()
    creation = [call for call in calls if call[0] == 'create']
    assert creation[0][2] == layout.child_command('frontend', ['--port', '3000'])
    assert creation[1][2] == [str(layout.executable), '--runtime-probe', 'api']
    assert creation[1][3]['env']['PROXY_TRANSCRIPT_STANDBY'] == '1'
    assert all(call[3]['detached_console'] is False for call in creation)
    host.close()
    assert calls[-3:] == [('stop', 101), ('stop', 102), 'job-close']
    assert host.closed and host.tree is None


def test_registered_detached_mode_is_explicit_for_both_fixed_writers(registered):
    host, calls, _ = registered
    host.start_registered(detached_console=True)
    creation = [call for call in calls if call[0] == 'create']
    assert len(creation) == 2 and all(call[3]['detached_console'] is True for call in creation)
    assert not any(call[0] == 'resume' for call in calls)
    host.close()


def test_registered_wal_choice_changes_only_the_fixed_api_probe(registered, layout):
    host, calls, _ = registered
    host.start_registered(detached_console=True, wal_probe=True)
    creation = [call for call in calls if call[0] == 'create']
    assert creation[0][2] == layout.child_command('frontend', ['--port', '3000'])
    assert creation[1][2] == [str(layout.executable), '--runtime-probe', 'api-wal']
    assert all(call[3]['detached_console'] is True for call in creation)
    assert not any(call[0] == 'resume' for call in calls)
    host.resume_registered(); host.close()
    assert calls[-3:] == [('stop', 101), ('stop', 102), 'job-close']


def test_registered_populated_choice_binds_only_api_to_fixed_owned_test_host(registered, layout):
    from backend.bundle_host import create_synthetic_root
    host, calls, _ = registered
    source = create_synthetic_root(layout.work_root/'p2-native/legacy')
    roots = {name:create_synthetic_root(source.path.parent/name, installation_id=source.installation_id)
        for name in ('private-target', 'external-state', 'host-profile')}
    root = source.path
    host.layout = replace(layout, settings_root=root, data_root=root/'data', cache_root=root/'cache-v1',
        work_root=root/'cache-v1/work', tool_root=root/'tools-v1', state_root=root/'probe-state', default_export_root=root/'exports')
    host.start_registered(detached_console=True, populated_probe=True)
    creation = [call for call in calls if call[0] == 'create']
    assert creation[0][2] == host.layout.child_command('frontend', ['--port','3000'])
    assert creation[1][2] == [str(layout.executable),'--runtime-probe','api-populated']
    assert creation[1][3]['env']['LOCALAPPDATA'] == str(roots['host-profile'].path)
    assert creation[0][3]['env'].get('LOCALAPPDATA') != str(roots['host-profile'].path)
    assert all(call[3]['detached_console'] is True for call in creation)
    assert not any(call[0] == 'resume' for call in calls)
    host.resume_registered(); host.close()


@pytest.mark.parametrize('selection', [{'populated_probe':value} for value in (None, 0, 1, 'true', [], {})]+
    [{'populated_probe':True}, {'populated_probe':True,'detached_console':True,'grammar_probe':True},
     {'populated_probe':True,'detached_console':True,'wal_probe':True}])
def test_populated_policy_refuses_ambiguous_or_non_detached_choices_before_creation(registered, selection):
    host, calls, _ = registered
    with pytest.raises(runtime_host.HostProbeFailure): host.start_registered(**selection)
    assert calls == [] and host.tree is None


def test_populated_role_roots_are_validated_before_creating_any_native_object(registered):
    host, calls, _ = registered
    with pytest.raises(RuntimeError): host.start_registered(detached_console=True, populated_probe=True)
    assert calls == [] and host.tree is None


def test_fixed_populated_case_dispatch_has_no_new_general_child_target(layout, monkeypatch):
    from backend import runtime_data_copy_probe
    calls = []
    monkeypatch.setattr(runtime_host.sys, 'stdin', io.StringIO('authored-populated-state-copy-v1\n'))
    monkeypatch.setattr(runtime_data_copy_probe, 'run_populated', lambda current, stream:calls.append((current, stream)) or 19)
    assert runtime_host.main('host', layout) == 19 and calls[0][0] is layout
    assert 'api-populated' not in bundle_entry.CHILD_TARGETS
    monkeypatch.setattr(runtime_host.sys, 'stdin', io.StringIO('authored-populated-state-copy-v1 arbitrary\n'))
    with pytest.raises(runtime_host.HostProbeFailure): runtime_host.main('host', layout)
    assert len(calls) == 1


def test_registered_grammar_choice_changes_only_the_fixed_api_probe(registered, layout):
    host, calls, _ = registered
    host.start_registered(detached_console=True, grammar_probe=True)
    creation = [call for call in calls if call[0] == 'create']
    assert creation[0][2] == layout.child_command('frontend', ['--port', '3000'])
    assert creation[1][2] == [str(layout.executable), '--runtime-probe', 'api-grammar']
    assert not any(call[0] == 'resume' for call in calls)
    host.resume_registered(); host.close()
    assert calls[-3:] == [('stop', 101), ('stop', 102), 'job-close']


@pytest.mark.parametrize('selection', [{'grammar_probe': value} for value in [None, 0, 1, 'true', [], {}]]+
                         [{'grammar_probe': True, 'wal_probe': True}])
def test_registered_grammar_choice_refuses_ambiguous_policies_before_creation(registered, selection):
    host, calls, _ = registered
    with pytest.raises(runtime_host.HostProbeFailure, match='invalid-private-probe-case'):
        host.start_registered(**selection)
    assert not calls and host.tree is None and host.scratch is None


@pytest.mark.parametrize('value', [None, 0, 1, 'true', 'api-wal', [], {}])
def test_registered_wal_choice_refuses_non_bool_before_any_native_creation(registered, value):
    host, calls, _ = registered
    with pytest.raises(runtime_host.HostProbeFailure, match='invalid-private-probe-case'):
        host.start_registered(wal_probe=value)
    assert host.tree is None and host.scratch is None and not calls


def test_registered_unknown_same_image_member_cannot_be_drained_or_adopted(registered):
    host, calls, members = registered
    host.start_registered()
    tree = host.tree
    members.add(999)
    with pytest.raises(runtime_host.HostProbeFailure, match='unknown-registered-member'):
        host.check_registered_members()
    previous = list(calls)
    with pytest.raises(runtime_host.HostProbeFailure, match='keeper-recovery-required'): host.close()
    assert calls == previous and host.tree is tree and host.scratch.exists()
    assert host.recovery_required and not host.closed


def test_registered_listener_must_match_creation_object_and_fixed_role(registered, monkeypatch):
    host, _, _ = registered
    host.start_registered(); host.resume_registered()
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: {3000: {102}, 8766: {101}})
    with pytest.raises(runtime_host.HostProbeFailure, match='registered-listener-role-mismatch'):
        with host._listener_scope(): pytest.fail('Swapped roles cannot reach HTTP')
    assert host.recovery_required


def test_registered_http_result_cannot_outlive_listener_identity(registered, monkeypatch):
    host, _, _ = registered
    host.start_registered(); host.resume_registered()
    sequence = iter([{3000: {101}, 8766: {102}}, {3000: {999}, 8766: {102}}])
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: next(sequence))
    with pytest.raises(runtime_host.HostProbeFailure, match='registered-listener-changed'):
        with host._listener_scope() as ready: assert ready
    assert host.recovery_required


def test_registered_startup_missing_then_owned_listeners_reach_http_only_inside_complete_stable_scope(registered, monkeypatch):
    host, _, _ = registered
    host.start_registered(); host.resume_registered()
    full = {3000: {101}, 8766: {102}}
    sequence = iter([{}, {3000: {101}}, full, full, full])
    observations, http, scopes = [], [], []
    def listeners():
        value = next(sequence, full); observations.append(value); return value
    monkeypatch.setattr(runtime_host, 'listener_processes', listeners)
    original = host._registered_listener_scope
    from contextlib import contextmanager
    @contextmanager
    def scoped():
        scopes.append(True)
        with original() as ready:
            assert ready
            yield ready
    monkeypatch.setattr(host, '_registered_listener_scope', scoped)
    def api(*_args):
        assert scopes == [True] and len(observations) == 4 and observations[-1] == full
        http.append('api'); return {'ready': True}
    class Response:
        status = 200
        def __enter__(self):
            assert scopes == [True] and len(observations) == 4
            http.append('frontend'); return self
        def __exit__(self, *_): pass
        def read(self, _): return b'x'
    monkeypatch.setattr(host, '_json', api)
    monkeypatch.setattr(runtime_host, 'urlopen', lambda *_a, **_k: Response())
    host.wait_services(timeout=1)
    assert observations == [{}, {3000: {101}}, full, full, full]
    assert http == ['api', 'frontend'] and not host.recovery_required
    host.close()


@pytest.mark.parametrize('fault', ['foreign', 'wrong-role', 'exit', 'close-refused', 'close-raised', 'member', 'query'])
def test_registered_startup_partial_native_refusals_never_become_http_retries(registered, monkeypatch, fault):
    host, calls, members = registered
    host.start_registered(); host.resume_registered()
    tree = host.tree
    calls.clear()
    close_attempts, queries = [], []
    partial = {3000: {999 if fault == 'foreign' else 102 if fault == 'wrong-role' else 101}}
    error = OSError('authored native refusal')
    def listeners():
        queries.append(True)
        if fault == 'query': raise error
        return partial
    monkeypatch.setattr(runtime_host, 'listener_processes', listeners)
    monkeypatch.setattr(host, '_json', lambda *_: pytest.fail('Unconfirmed startup cannot consult HTTP'))
    monkeypatch.setattr(runtime_host, 'urlopen', lambda *_a, **_k: pytest.fail('Unconfirmed startup cannot consult HTTP'))
    if fault == 'exit':
        monkeypatch.setattr(tree.kernel, 'WaitForSingleObject', lambda handle, _: 0 if handle == 102 else 258)
    elif fault.startswith('close-'):
        def close(handle):
            close_attempts.append(handle)
            if fault == 'close-raised': raise error
            return False
        monkeypatch.setattr(tree.kernel, 'CloseHandle', close)
    elif fault == 'member': members.add(999)
    expected = OSError if fault in {'close-raised','query'} else runtime_host.HostProbeFailure
    with pytest.raises(expected) as raised: host.wait_services(timeout=1)
    if expected is OSError: assert raised.value is error
    assert host.recovery_required and host.tree is tree and not host.closed and host.scratch.exists()
    assert len(queries) <= 1
    if fault.startswith('close-'): assert len(close_attempts) == 1
    assert not any(isinstance(call, tuple) and call[0] == 'stop' for call in calls)


def test_registered_complete_startup_still_rejects_changed_scoped_http_listeners(registered, monkeypatch):
    host, _, _ = registered
    host.start_registered(); host.resume_registered()
    full = {3000: {101}, 8766: {102}}
    sequence = iter([full, full, {3000: {999}, 8766: {102}}])
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda: next(sequence))
    http = []
    def api(*_): http.append('api'); return {'ready': True}
    monkeypatch.setattr(host, '_json', api)
    class Response:
        status = 200
        def __enter__(self): http.append('frontend'); return self
        def __exit__(self, *_): pass
        def read(self, _): return b'x'
    monkeypatch.setattr(runtime_host, 'urlopen', lambda *_a, **_k: Response())
    with pytest.raises(runtime_host.HostProbeFailure, match='registered-listener-changed'):
        host.wait_services(timeout=1)
    assert http == ['api','frontend'] and host.recovery_required and not host.closed


@pytest.mark.parametrize('boundary', ['partial-create', 'resume', 'stop', 'job-close', 'observer-close'])
def test_registered_failures_retain_owner_and_never_report_closed(registered, monkeypatch, boundary):
    host, calls, _ = registered
    if boundary == 'partial-create':
        original = runtime_host.WindowsPreparationProcess.create_suspended
        def create(tree, command, **options):
            if command[-1] == 'api': raise OSError('authored creation failure')
            return original(tree, command, **options)
        monkeypatch.setattr(runtime_host.WindowsPreparationProcess, 'create_suspended', create)
        with pytest.raises(OSError): host.start_registered()
    else:
        host.start_registered()
        def fail(*_a, **_k): raise OSError('authored native failure')
        if boundary == 'resume':
            monkeypatch.setattr(host.registered['api'], 'resume_once', fail)
            with pytest.raises(OSError): host.resume_registered()
        elif boundary == 'observer-close':
            monkeypatch.setattr(host.tree.kernel, 'CloseHandle', lambda _: False)
            with pytest.raises(runtime_host.HostProbeFailure, match='registered-observer-close-unconfirmed'):
                host.check_registered_members()
        else:
            monkeypatch.setattr(host.registered['api'] if boundary == 'stop' else host.tree,
                                'stop_and_wait' if boundary == 'stop' else 'close', fail)
            with pytest.raises(OSError): host.close()
    assert host.recovery_required and host.tree is not None and not host.closed
    assert host.scratch.exists() and 'job-close' not in calls
    with pytest.raises(runtime_host.HostProbeFailure, match='keeper-recovery-required'): host.close()


def test_registered_quiesce_uses_existing_explicit_protocol_with_paused_fixture(registered, monkeypatch):
    host, _, _ = registered
    host.start_registered(); host.resume_registered()
    requests = []
    class Response:
        status = 200
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return self.body
    def request(value, **options):
        requests.append((value, options))
        if isinstance(value, runtime_host.Request): return Response(b'{"running":false}')
        if value.endswith('/api/status'):
            raise runtime_host.HTTPError(value, 503, 'authored closed admission', {}, io.BytesIO(b'{}'))
        assert value.endswith('/api/health')
        return Response(b'{"status":"ok"}')
    monkeypatch.setattr(runtime_host, 'urlopen', request)
    host.quiesce_registered()
    assert requests[0][0].full_url.endswith('/api/runtime/quiesce?writers=true')
    assert requests[0][0].method == 'POST' and requests[0][1]['timeout'] == 35
    assert requests[0][0].get_header('X-proxy-transcript') == 'update'
    assert [value for value, _ in requests[1:]] == [runtime_host.API+'/api/status', runtime_host.API+'/api/health']
    host.close()


@pytest.mark.parametrize('status,health', [(200, 'ok'), (502, 'ok'), (503, 'failed'), (503, None)])
def test_registered_quiesce_rejects_open_admission_or_unavailable_control(registered, monkeypatch, status, health):
    host, calls, _ = registered
    host.start_registered(); host.resume_registered()
    class Response:
        def __init__(self, code, body): self.status, self.body = code, body
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return self.body
    def request(value, **_):
        if isinstance(value, runtime_host.Request): return Response(200, b'{"running":false}')
        if value.endswith('/api/status'):
            if status >= 400: raise runtime_host.HTTPError(value, status, 'authored status', {}, io.BytesIO(b'{}'))
            return Response(status, b'{}')
        if health is None: raise OSError('authored health transport failure')
        return Response(200, json.dumps({'status': health}).encode())
    monkeypatch.setattr(runtime_host, 'urlopen', request)
    expected = OSError if health is None else runtime_host.HostProbeFailure
    with pytest.raises(expected): host.quiesce_registered()
    assert not host.closed and host.tree is not None and 'job-close' not in calls


@pytest.mark.parametrize('case', ['keeper-before-resume', 'keeper-after-ready'])
def test_keeper_loss_drives_drain_but_leases_wait_for_explicit_release(layout, monkeypatch, capsys, case):
    calls = []
    keeper = runtime_host._FrozenKeeperProbe(layout, case, io.StringIO(''))
    class Lease:
        def acquire(self): calls.append('acquire')
        def close(self):
            assert 'writers-signaled' in calls and 'release' in calls
            calls.append('lease-close')
    class Host:
        registered, recovery_required = {}, False
        def start_registered(self, **options):
            assert options == {'detached_console': True}
            calls.append('create-two'); self.registered = {role: SimpleNamespace(resumed=False) for role in ('frontend', 'api')}
        def resume_registered(self):
            calls.append('resume-two')
            for child in self.registered.values(): child.resumed = True
        def wait_services(self): calls.append('ready')
        def quiesce_registered(self): calls.append('strict-c2')
        def close(self): calls.append('writers-signaled')
    def prepare(): keeper.host, keeper.leases = Host(), [Lease(), Lease()]
    def command(expected): calls.append(expected)
    def guardian_loss():
        calls.append('guardian-loss'); keeper.guardian_signaled = True
    monkeypatch.setattr(keeper, 'prepare', prepare)
    monkeypatch.setattr(keeper, 'command', command)
    monkeypatch.setattr(keeper, 'start_guardian', lambda: setattr(keeper, 'guardian', SimpleNamespace(stdout=io.StringIO())))
    monkeypatch.setattr(keeper, 'check_guardian', lambda: None)
    monkeypatch.setattr(keeper, 'wait_guardian_loss', guardian_loss)
    assert keeper.run() == 0
    assert calls.count('lease-close') == 2 and calls.index('guardian-loss') < calls.index('writers-signaled')
    assert ('resume-two' in calls) == (case == 'keeper-after-ready')
    if case == 'keeper-after-ready': assert calls.index('strict-c2') < calls.index('writers-signaled')
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[-2]['phase'] == 'writers-signaled-leases-held'
    assert output[-1]['status'] == 'passed' and keeper.released
    assert output[-1]['r19_complete'] is False and output[-1]['census'] == 'observations-only-not-lifetime-proof'
    assert output[-1]['guardian_console_mode'] == output[-1]['writer_console_mode'] == 'detached-process'
    assert str(layout.settings_root) not in json.dumps(output)


@pytest.mark.parametrize('failure', ['writer-stop', 'unknown-members', 'lease-close'])
def test_keeper_unconfirmed_cleanup_holds_live_owner_and_leases(layout, monkeypatch, capsys, failure):
    calls = []
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    class Held(BaseException): pass
    class Lease:
        def acquire(self): calls.append('acquire')
        def close(self):
            calls.append('lease-close')
            raise OSError('private-path secret-value must not be emitted')
    class Host:
        registered, recovery_required = {}, False
        def start_registered(self, **options): assert options == {'detached_console': True}
        def close(self):
            if failure != 'lease-close':
                self.recovery_required = True
                raise OSError('private-path secret-value must not be emitted')
    def prepare(): keeper.host, keeper.leases = Host(), [Lease(), Lease()]
    def loss():
        keeper.guardian_signaled = True
        if failure == 'unknown-members':
            keeper.host.recovery_required = True
            raise runtime_host.HostProbeFailure('unknown-registered-member')
    def hold(): calls.append('live-holder'); raise Held()
    monkeypatch.setattr(keeper, 'prepare', prepare)
    monkeypatch.setattr(keeper, 'command', lambda *_: None)
    monkeypatch.setattr(keeper, 'start_guardian', lambda: setattr(keeper, 'guardian', SimpleNamespace(stdout=io.StringIO())))
    monkeypatch.setattr(keeper, 'wait_guardian_loss', loss)
    monkeypatch.setattr(runtime_host, 'hold_keeper_recovery', hold)
    with pytest.raises(Held): keeper.run()
    assert calls[-1] == 'live-holder' and not keeper.released
    assert calls.count('lease-close') == (1 if failure == 'lease-close' else 0)
    output = capsys.readouterr().out
    assert 'recovery-required' in output and '"status": "passed"' not in output
    assert 'private-path' not in output and 'secret-value' not in output


@pytest.mark.parametrize('pipe_error', [BrokenPipeError, OSError])
def test_keeper_broken_event_pipe_cannot_bypass_live_recovery_hold(layout, monkeypatch, pipe_error):
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    calls = []
    class Held(BaseException): pass
    class Lease:
        def acquire(self): calls.append('acquire')
        def close(self): pytest.fail('Broken output cannot release a live writer lease')
    child = SimpleNamespace(resumed=False, process_handle=object())
    host = SimpleNamespace(registered={'frontend': child, 'api': child}, recovery_required=False,
        start_registered=lambda **options: calls.append('writers-created') if options == {'detached_console': True} else pytest.fail('Fixed keeper detached mode missing'),
        close=lambda: pytest.fail('Event failure cannot invent successful drainage'))
    def prepare(): keeper.host, keeper.leases = host, [Lease(), Lease()]
    def emit(*_a, **_k):
        calls.append('broken-event'); raise pipe_error('authored closed control pipe')
    def hold(): calls.append('live-holder'); raise Held()
    monkeypatch.setattr(keeper, 'prepare', prepare)
    monkeypatch.setattr(keeper, 'command', lambda *_: None)
    monkeypatch.setattr(keeper, 'start_guardian', lambda: None)
    monkeypatch.setattr(keeper, 'emit', emit)
    monkeypatch.setattr(runtime_host, 'hold_keeper_recovery', hold)
    with pytest.raises(Held): keeper.run()
    assert calls == ['acquire', 'acquire', 'writers-created', 'broken-event', 'broken-event', 'live-holder']
    assert keeper.host is host and len(keeper.leases) == 2 and not keeper.released


@pytest.mark.parametrize('fault', ['wrong-listener', 'after-http-change', 'descendant', 'tampered-index'])
def test_guardian_identity_is_bound_to_retained_creation_and_actual_http(layout, monkeypatch, fault):
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    keeper.guardian = SimpleNamespace(pid=301, poll=lambda: None)
    keeper.guardian_port = 49301
    body = b'authored closed index'
    keeper.guardian_index = {'bytes': len(body), 'sha256': runtime_host.hashlib.sha256(body).hexdigest()}
    observations = iter([{49301: {301}}, {49301: {999}}])
    monkeypatch.setattr(runtime_host, 'listener_processes',
        (lambda _: next(observations)) if fault == 'after-http-change' else lambda _: {49301: {999 if fault == 'wrong-listener' else 301}})
    monkeypatch.setattr(runtime_host, 'guardian_children', lambda _: {444} if fault == 'descendant' else set())
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'tampered' if fault == 'tampered-index' else body
    monkeypatch.setattr(runtime_host, 'urlopen', lambda *_a, **_k: Response())
    with pytest.raises(runtime_host.HostProbeFailure, match='keeper-guardian-'):
        keeper.check_guardian()


def test_guardian_fault_only_uses_retained_popen_and_loss_is_signaled(layout, monkeypatch):
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO('lose-guardian\n'))
    calls = []
    class Guardian:
        pid, code = 301, None
        def poll(self): return self.code
        def kill(self): calls.append('retained-kill'); self.code = 1
        def wait(self, timeout): calls.append('retained-wait'); return self.code
    keeper.guardian = Guardian()
    keeper.host = SimpleNamespace(_alive=lambda: None, check_registered_members=lambda: None)
    monkeypatch.setattr(keeper, 'check_guardian', lambda: None)
    monkeypatch.setattr(runtime_host, 'guardian_children', lambda _: set())
    keeper.wait_guardian_loss()
    assert calls == ['retained-kill', 'retained-wait'] and keeper.guardian_signaled


def test_fixed_guardian_detaches_with_only_explicit_popen_stdio(layout, monkeypatch):
    from dataclasses import replace
    manifest = layout.resource_root/'desktop/desktop-manifest.json'
    manifest.parent.mkdir(parents=True)
    body = json.dumps({'build_id': 'authored-frontend', 'files': {'index.html': {'bytes': 1,
        'sha256': runtime_host.hashlib.sha256(b'x').hexdigest()}}}).encode()
    manifest.write_bytes(body)
    selected = replace(layout, resources={'desktop/desktop-manifest.json': runtime_host.hashlib.sha256(body).hexdigest()})
    keeper = runtime_host._FrozenKeeperProbe(selected, 'keeper-before-resume', io.StringIO(''))
    keeper.writer_layout = selected
    calls = []
    class Guardian:
        def __init__(self, command, **options):
            calls.append((command, options))
            self.stdout = io.StringIO(json.dumps({'ready': True, 'port': 49301, 'build_id': 'authored-frontend'})+'\n')
    monkeypatch.setattr(runtime_host.subprocess, 'Popen', Guardian)
    monkeypatch.setattr(runtime_host.subprocess, 'DETACHED_PROCESS', 8, raising=False)
    monkeypatch.setattr(keeper, 'check_guardian', lambda: calls.append('owned-readiness-check'))
    keeper.start_guardian()
    command, options = calls[0]
    assert command == selected.child_command('frontend', ['--port', '0'])
    assert options['creationflags'] == 8 and options['close_fds'] is True
    assert options['stdin'] == options['stderr'] == subprocess.DEVNULL
    assert options['stdout'] == subprocess.PIPE and options['encoding'] == 'utf-8'
    assert calls[1] == 'owned-readiness-check' and isinstance(keeper.guardian, Guardian)


def test_keeper_roots_are_new_and_target_lease_is_separate_from_writer_state(layout, monkeypatch, capsys):
    from backend.bundle_host import ExclusiveFileLease
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    keeper.prepare()
    assert all(isinstance(lease, ExclusiveFileLease) and not lease.held for lease in keeper.leases)
    assert keeper.leases[0].path == keeper.fixture/'legacy/data/companion-operation.lock'
    assert keeper.leases[1].path == keeper.fixture/'private-target/host-v1/migration-runtime.lock'
    assert keeper.writer_layout.state_root == keeper.fixture/'authored-state/host-v1'
    assert not keeper.leases[1].path.is_relative_to(keeper.writer_layout.settings_root)
    assert keeper.writer_layout.settings_root != layout.settings_root
    runtime_host.synthetic_roots(keeper.writer_layout)
    assert json.loads(capsys.readouterr().out)['phase'] == 'roots-ready'
    with pytest.raises(FileExistsError): keeper.prepare()


def test_keeper_temp_guard_rejects_siblings_but_accepts_authored_children(layout, monkeypatch):
    from dataclasses import replace
    selected_temp = layout.settings_root/'empty-host'
    selected_temp.mkdir()
    monkeypatch.setattr(runtime_host.tempfile, 'gettempdir', lambda: str(selected_temp))
    sibling = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    with pytest.raises(runtime_host.HostProbeFailure, match='keeper-fixture-unavailable'): sibling.prepare()
    assert not sibling.fixture.exists()
    private = selected_temp/'keeper-before-resume'
    nested = replace(layout, settings_root=private, data_root=private/'data-v1', cache_root=private/'cache-v1',
        work_root=private/'cache-v1/work', tool_root=private/'tools-v1', state_root=private/'host-v1',
        default_export_root=private/'exports')
    nested.state_root.mkdir(parents=True)
    (nested.state_root/'synthetic-probe.json').write_text(json.dumps({'build_id': layout.build_id, 'synthetic': True}))
    keeper = runtime_host._FrozenKeeperProbe(nested, 'keeper-before-resume', io.StringIO(''))
    keeper.prepare()
    assert keeper.fixture.is_relative_to(selected_temp)
    assert keeper.writer_layout.settings_root.is_relative_to(selected_temp)


@pytest.mark.parametrize('close_ok', [True, False])
def test_guardian_census_is_bounded_observation_with_checked_snapshot_close(monkeypatch, close_ok):
    import ctypes
    rows = iter([(1, 0), (301, 1), (401, 301), (402, 401), (999, 1)])
    calls = []
    class Function:
        def __init__(self, action): self.action = action
        def __call__(self, *args): return self.action(*args)
    def advance(_snapshot, value):
        try: pid, parent = next(rows)
        except StopIteration: return False
        value._obj.pid, value._obj.parent = pid, parent
        return True
    def close(handle): calls.append(('snapshot-close', handle)); return close_ok
    kernel = SimpleNamespace(CreateToolhelp32Snapshot=Function(lambda kind, pid: 7 if (kind, pid) == (2, 0) else None),
        Process32FirstW=Function(advance), Process32NextW=Function(advance), CloseHandle=Function(close))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *_a, **_k: kernel, raising=False)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 18, raising=False)
    if close_ok:
        assert runtime_host.guardian_children(301) == {401, 402}
    else:
        with pytest.raises(runtime_host.HostProbeFailure, match='guardian-census-close-unconfirmed'):
            runtime_host.guardian_children(301)
    assert calls == [('snapshot-close', 7)]


@pytest.fixture
def guardian_observers(monkeypatch):
    """Fake read-only native calls; never process admission or Windows proof."""
    calls, held = [], []
    runtime = r'C:\authored-runtime\ProxyTranscriptRuntime.exe'
    class Kernel:
        mode = None
        queried = False
        root = 11
        opens = 0
        values = {11: (100, 1000, object())}
        tokens = {}
        paths = {}
        stamps = {}
        def GetProcessId(self, handle):
            calls.append(('id', handle))
            return 999 if self.mode == 'wrong-id' and handle != self.root else self.values[handle][0]
        def WaitForSingleObject(self, handle, _timeout):
            calls.append(('wait', handle))
            if self.mode == 'post-query-wait-failure' and self.queried and handle != self.root: return 0xffffffff
            return 0 if self.mode == 'exited' and handle != self.root else 258
        def OpenProcess(self, access, inherit, pid):
            assert access == 0x101000 and inherit is False
            calls.append(('open', pid))
            if self.mode == 'open-failure': return 0
            self.opens += 1
            handle = 1000+self.opens
            token = self.tokens.setdefault(pid, object())
            if self.mode == 'reused-object' and self.opens == 2: token = object()
            self.values[handle] = (pid, self.stamps.get(pid, 1100), token)
            return handle
        def GetProcessTimes(self, handle, creation, *_rest):
            calls.append(('time', handle))
            if self.mode == 'root-query-failure' and handle == self.root: return False
            creation._obj.dwLowDateTime = self.values[handle][1]
            return True
        def GetSystemDirectoryW(self, buffer, _limit):
            calls.append('system-directory'); buffer.value = r'C:\Windows\System32'
            return len(buffer.value)
        def QueryFullProcessImageNameW(self, handle, flags, buffer, count):
            assert flags == 0
            calls.append(('image', handle))
            if self.mode == 'query-failure': return False
            self.queried = True
            buffer.value = self.paths.get(self.values[handle][0], runtime)
            count._obj.value = len(buffer.value)
            return True
        def CloseHandle(self, handle):
            calls.append(('close', handle))
            if self.mode == 'close-failure': return False
            if self.mode == 'close-exception': raise OSError('private exception marker')
            return True
    kernel = Kernel()
    monkeypatch.setattr(runtime_host, '_guardian_observer_kernel', lambda: kernel)
    monkeypatch.setattr(runtime_host, 'same_process_object', lambda first, second: kernel.values[first][2] is kernel.values[second][2])
    return kernel, SimpleNamespace(pid=100, _handle=11), runtime, held, calls


def test_guardian_diagnostics_classify_only_exact_images_and_keep_lineage_unproved(guardian_observers):
    kernel, guardian, runtime, held, calls = guardian_observers
    kernel.tokens[101] = object(); kernel.values[901] = (101, 1100, kernel.tokens[101])
    kernel.paths.update({103: r'C:\Windows\System32\conhost.exe', 104: r'C:\authored-cwd\conhost.exe',
        105: r'C:\Windows\System32\other.exe', 106: r'\\?\C:\Windows\System32\conhost.exe',
        107: r'C:\other-runtime\ProxyTranscriptRuntime.exe'})
    kernel.stamps[103] = 900  # A stale parent-ID relation remains only an observation.
    value = runtime_host.observe_guardian_candidates(guardian, runtime, set(range(101, 108)), held, (901,))
    assert value['state'] == 'observed' and value['lineage'] == 'census-not-authority'
    assert value['candidate_count'] == value['inspected_count'] == 7 and not held
    assert [row['role'] for row in value['records']] == ['retained-runtime-creation', 'runtime-image-only',
        'windows-console-host', 'unknown', 'unknown', 'unknown', 'unknown']
    assert value['records'][2]['creation_order'] == 'before-guardian'
    serialized = json.dumps(value)
    assert 'C:' not in serialized and '101' not in serialized and '1100' not in serialized
    assert len([call for call in calls if isinstance(call, tuple) and call[0] == 'close']) == 14


@pytest.mark.parametrize('mode,reason', [('wrong-id','identity-unavailable'), ('reused-object','identity-changed'),
    ('post-query-wait-failure','identity-unavailable'),
    ('query-failure','query-unavailable'), ('close-failure','observer-close-unconfirmed'),
    ('close-exception','observer-close-unconfirmed')])
def test_guardian_unconfirmed_observers_are_poisoned_and_never_reused(guardian_observers, mode, reason):
    kernel, guardian, runtime, held, calls = guardian_observers
    kernel.mode = mode
    value = runtime_host.observe_guardian_candidates(guardian, runtime, {101}, held)
    assert value['state'] == 'unavailable' and value['reason'] == reason
    assert held and all(record['poisoned'] for record in held)
    before = list(calls)
    retry = runtime_host.observe_guardian_candidates(guardian, runtime, {101}, held)
    assert retry['state'] == 'unavailable' and retry['reason'] == 'prior-observation-unconfirmed'
    assert calls == before
    assert 'private exception marker' not in json.dumps(value)


@pytest.mark.parametrize('mode,state', [('open-failure','open-unavailable'), ('exited','exit-observed')])
def test_guardian_transient_objects_are_unavailable_and_never_adopted(guardian_observers, mode, state):
    kernel, guardian, runtime, held, _ = guardian_observers
    kernel.mode = mode
    value = runtime_host.observe_guardian_candidates(guardian, runtime, {101}, held)
    assert value['state'] == 'unavailable' and value['records'][0]['state'] == state
    assert value['records'][0]['role'] == 'unknown' and not held


def test_guardian_diagnostics_limit_candidate_queries_without_inventing_membership(guardian_observers):
    _kernel, guardian, runtime, held, calls = guardian_observers
    value = runtime_host.observe_guardian_candidates(guardian, runtime, set(range(101, 121)), held)
    assert value['candidate_count'] == 20 and value['inspected_count'] == 16 and value['truncated']
    assert len([call for call in calls if isinstance(call, tuple) and call[0] == 'open']) == 32
    assert value['lineage'] == 'census-not-authority' and not held


def test_known_diagnostic_role_cannot_change_guardian_descendant_refusal(layout, monkeypatch):
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    keeper.guardian = SimpleNamespace(pid=301, poll=lambda: None)
    keeper.guardian_port = 49301
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda _: {49301: {301}})
    monkeypatch.setattr(runtime_host, 'guardian_children', lambda _: {401})
    def observe(candidates):
        assert candidates == {401}
        keeper.descendant_observation = {'role': 'windows-console-host'}
    monkeypatch.setattr(keeper, 'observe_descendants', observe)
    with pytest.raises(runtime_host.HostProbeFailure, match='keeper-guardian-descendants'): keeper.check_guardian()


def test_failed_guardian_observer_close_reaches_live_keeper_hold(guardian_observers, layout, monkeypatch, capsys):
    kernel, guardian, _runtime, held, _calls = guardian_observers
    kernel.mode = 'close-failure'; guardian.poll = lambda: None
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    keeper.guardian, keeper.guardian_port, keeper._guardian_observer_holds = guardian, 49301, held
    calls = []
    class Held(BaseException): pass
    class Lease:
        def acquire(self): calls.append('lease-acquired')
        def close(self): pytest.fail('Unconfirmed observation cannot release the keeper lease')
    def prepare():
        keeper.host = SimpleNamespace(registered={}, recovery_required=False)
        keeper.leases = [Lease(), Lease()]
    def hold(): calls.append('live-holder'); raise Held()
    monkeypatch.setattr(keeper, 'prepare', prepare)
    monkeypatch.setattr(keeper, 'command', lambda *_: None)
    monkeypatch.setattr(keeper, 'start_guardian', keeper.check_guardian)
    monkeypatch.setattr(runtime_host, 'listener_processes', lambda _: {49301: {guardian.pid}})
    monkeypatch.setattr(runtime_host, 'guardian_children', lambda _: {101})
    monkeypatch.setattr(runtime_host, 'hold_keeper_recovery', hold)
    with pytest.raises(Held): keeper.run()
    assert calls == ['lease-acquired', 'lease-acquired', 'live-holder']
    value = json.loads(capsys.readouterr().out)
    assert value['failure'] == 'keeper-guardian-descendants'
    assert value['guardian_descendants']['reason'] == 'observer-close-unconfirmed'
    assert held and all(item['poisoned'] for item in held) and not keeper.released


def test_keeper_diagnostic_root_query_failure_is_one_shot_even_without_observer_handles(guardian_observers, layout):
    kernel, guardian, _runtime, _held, calls = guardian_observers
    kernel.mode = 'root-query-failure'
    keeper = runtime_host._FrozenKeeperProbe(layout, 'keeper-before-resume', io.StringIO(''))
    keeper.guardian, keeper.host = guardian, SimpleNamespace(registered={})
    keeper.observe_descendants({101})
    assert keeper.descendant_observation['state'] == 'unavailable'
    assert keeper.descendant_observation['reason'] == 'query-unavailable'
    before = list(calls)
    keeper.observe_descendants({102})
    assert calls == before and keeper.descendant_observation['candidate_count'] == 1


def test_native_listener_table_uses_fixed_windows_rows_and_only_canonical_addresses(monkeypatch):
    import ctypes
    import socket
    import struct
    rows = [(2, 0x0100007f, socket.htons(3000), 0, 0, 102),
            (2, 0, socket.htons(8766), 0, 0, 104),
            (2, 0x0200007f, socket.htons(3000), 0, 0, 999),
            (2, 0x0100007f, socket.htons(8000), 0, 0, 998)]
    data = struct.pack('<I', len(rows)) + b''.join(struct.pack('<6I', *row) for row in rows)
    class Query:
        def __call__(self, buffer, size, _ordered, family, table, _reserved):
            assert family == 2 and table == 3
            size._obj.value = len(data)
            if buffer is None: return 122
            ctypes.memmove(buffer, data, len(data))
            return 0
    monkeypatch.setattr(runtime_host.ctypes, 'WinDLL', lambda *_a, **_k: SimpleNamespace(GetExtendedTcpTable=Query()), raising=False)
    assert ctypes.sizeof(runtime_host._TcpRow) == 24
    assert runtime_host.listener_processes() == {3000: {102}, 8766: {104}}


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell observer identity categories')
def test_observer_diagnostics_are_fixed_categories_and_do_not_weaken_identity(tmp_path):
    # Extract only the pure classifier. Do not execute the candidate probe,
    # create real processes, inspect the desktop or access an account.
    source = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-runtime.ps1'
    script = tmp_path/'observer-fixture.ps1'
    script.write_text(r'''param([string]$ProbeScript)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($ProbeScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Owned host probe PowerShell parsing failed.' }
$definition = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-HostObserverIdentityCategory'}, $true)
if (-not $definition) { throw 'Missing fixed host observer classifier.' }
. ([scriptblock]::Create($definition.Extent.Text))
$roleDefinition = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-HostObserverRole'}, $true)
if (-not $roleDefinition) { throw 'Missing fixed host observer role classifier.' }
. ([scriptblock]::Create($roleDefinition.Extent.Text))
$expected = 'C:\authored-runtime\ProxyTranscriptRuntime.exe'
$owner = [pscustomobject]@{StartTime=[DateTime]'2020-01-01T00:00:00Z'}
function New-Observer([string]$Image=$expected, [bool]$Exited=$false, [int]$Offset=1) {
    return [pscustomobject]@{HasExited=$Exited; StartTime=$owner.StartTime.AddSeconds($Offset); MainModule=[pscustomobject]@{FileName=$Image}}
}
function Assert-Category($Observer, [string]$ExpectedCategory) {
    $category = Get-HostObserverIdentityCategory $Observer $owner $expected
    $allowed = @('verified-runtime', 'process-exited', 'process-state-unavailable',
        'creation-time-unavailable', 'process-predates-owner', 'image-unavailable',
        'process-exited-during-identity', 'runtime-image-prefix-spelling-mismatch',
        'runtime-image-other-path', 'windows-console-host-image', 'unexpected-image')
    if ($category -ne $ExpectedCategory) {
        $safeActual = if ($category -in $allowed) {$category} else {'unrecognized-category'}
        $safeExpected = if ($ExpectedCategory -in $allowed) {$ExpectedCategory} else {'unrecognized-category'}
        [Console]::Out.WriteLine('host-observer-mismatch expected=' + $safeExpected + ' actual=' + $safeActual)
        [Console]::Out.Flush()
        throw 'Fixed host observer classification failed.'
    }
    if ($category -match 'PRIVATE|authored-runtime|secret-user|^[A-Z]:') { throw 'Observer diagnostics exposed fixture identity.' }
}
Assert-Category (New-Observer) 'verified-runtime'
Assert-Category (New-Observer -Exited $true) 'process-exited'
Assert-Category (New-Observer -Offset -1) 'process-predates-owner'
Assert-Category (New-Observer -Image '') 'image-unavailable'
Assert-Category (New-Observer -Image 'C:\Windows\System32\conhost.exe') 'windows-console-host-image'
Assert-Category (New-Observer -Image 'C:\other-runtime\ProxyTranscriptRuntime.exe') 'runtime-image-other-path'
Assert-Category (New-Observer -Image '\\?\C:\authored-runtime\ProxyTranscriptRuntime.exe') 'runtime-image-prefix-spelling-mismatch'
Assert-Category (New-Observer -Image 'C:\secret-user\private-program.exe') 'unexpected-image'
$unreadable = New-Observer
$unreadable | Add-Member -MemberType ScriptProperty -Name HasExited -Value {throw 'PRIVATE fixture state failure'} -Force
Assert-Category $unreadable 'process-state-unavailable'
$unreadable = New-Observer
$unreadable | Add-Member -MemberType ScriptProperty -Name StartTime -Value {throw 'PRIVATE fixture time failure'} -Force
Assert-Category $unreadable 'creation-time-unavailable'
$unreadable = New-Observer
$unreadable | Add-Member -MemberType ScriptProperty -Name MainModule -Value {throw 'PRIVATE fixture image failure'} -Force
Assert-Category $unreadable 'image-unavailable'
$script:exitReads = 0
$exiting = New-Observer
$exiting | Add-Member -MemberType ScriptProperty -Name HasExited -Value {$script:exitReads++; return $script:exitReads -ge 2} -Force
Assert-Category $exiting 'process-exited-during-identity'
function Assert-Role($Observer, [string]$ExpectedRole) {
    $role = Get-HostObserverRole $Observer $owner $expected 'C:\Windows\System32\conhost.exe'
    $allowed = @('runtime', 'windows-console-host', 'system-console-image-unverified',
        'process-exited', 'process-predates-owner', 'process-state-unavailable',
        'image-unavailable', 'unexpected-image')
    if ($role -ne $ExpectedRole) {
        $safeActual = if ($role -in $allowed) {$role} else {'unrecognized-category'}
        $safeExpected = if ($ExpectedRole -in $allowed) {$ExpectedRole} else {'unrecognized-category'}
        [Console]::Out.WriteLine('host-observer-mismatch expected=' + $safeExpected + ' actual=' + $safeActual)
        [Console]::Out.Flush()
        throw 'Fixed host observer role classification failed.'
    }
}
Assert-Role (New-Observer) 'runtime'
Assert-Role (New-Observer -Image 'C:\Windows\System32\conhost.exe') 'windows-console-host'
Assert-Role (New-Observer -Image 'C:\authored-cwd\conhost.exe') 'system-console-image-unverified'
Assert-Role (New-Observer -Image 'C:\Windows\System32\other.exe') 'unexpected-image'
Assert-Role (New-Observer -Image 'C:\Windows\System32\conhost.exe' -Exited $true) 'process-exited'
Assert-Role (New-Observer -Image 'C:\Windows\System32\conhost.exe' -Offset -1) 'process-predates-owner'
$unknownConsole = New-Observer -Image 'C:\Windows\System32\conhost.exe'
$unknownConsole.HasExited = $null
Assert-Role $unknownConsole 'process-state-unavailable'
Assert-Role (New-Observer -Image '') 'image-unavailable'
Write-Output 'host-observer-categories-passed'
''', encoding='utf-8')
    shell = shutil.which('pwsh')
    assert shell, 'Hosted Windows observer tests require the workflow PowerShell runtime'
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(script),
        '-ProbeScript', str(source)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        categories = {'verified-runtime', 'process-exited', 'process-state-unavailable',
            'creation-time-unavailable', 'process-predates-owner', 'image-unavailable',
            'process-exited-during-identity', 'runtime-image-prefix-spelling-mismatch',
            'runtime-image-other-path', 'windows-console-host-image', 'unexpected-image',
            'unrecognized-category', 'runtime', 'windows-console-host', 'system-console-image-unverified'}
        safe = 'no-safe-category-result'
        for line in result.stdout.splitlines():
            parts = line.split()
            if (len(parts) == 3 and parts[0] == 'host-observer-mismatch'
                    and parts[1].startswith('expected=') and parts[2].startswith('actual=')
                    and parts[1][9:] in categories and parts[2][7:] in categories):
                safe = ' '.join(parts[1:])
        pytest.fail('Fixed observer classifier failed: ' + safe, pytrace=False)
    if result.stdout.strip() != 'host-observer-categories-passed':
        pytest.fail('Observer classifier returned an unexpected control result', pytrace=False)
    if 'PRIVATE' in result.stderr or 'secret-user' in result.stderr:
        pytest.fail('Observer diagnostics exposed private fixture detail', pytrace=False)


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell keeper harness failure/root contracts')
def test_keeper_harness_receipt_failure_cannot_bypass_livehold_and_roots_follow_temp(tmp_path):
    # Only named harness functions and authored fake observers. No candidate,
    # real writer, lease, user profile or account is opened by this contract.
    source = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-keeper.ps1'
    script = tmp_path/'keeper-harness-contract.ps1'
    script.write_text(r'''param([string]$ProbeScript,[string]$Fixture)
$ErrorActionPreference='Stop'
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($ProbeScript,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors) { throw 'Keeper harness parsing failed.' }
foreach ($name in @('Get-KeeperCaseRoots','Complete-KeeperHarness','Get-SafeGuardianObservation')) {
    $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    if (-not $definition) { throw 'Missing named keeper contract.' }
    . ([scriptblock]::Create($definition.Extent.Text))
}
$Output=Join-Path $Fixture 'authored-receipt.json'
$script:events=[Collections.Generic.List[string]]::new()
$script:breakReceipt=$true
function Write-KeeperReceipt([string]$Status) {
    $script:events.Add('receipt-'+$Status)
    if ($script:breakReceipt) { throw 'authored unavailable receipt destination' }
}
function Wait-KeeperHarnessRecovery { $script:events.Add('held'); throw 'expected-live-holder' }
function Assert-LiveHold([bool]$Failed,$Observer) {
    $script:events.Clear()
    $script:owned=@($Observer)
    try { Complete-KeeperHarness $Failed; throw 'liveholder was bypassed' }
    catch { if ($_.Exception.Message -cne 'expected-live-holder') { throw 'Keeper receipt failure bypassed recovery.' } }
    if ($script:events.Count -ne 2 -or $script:events[1] -cne 'held') { throw 'Keeper livehold ordering differs.' }
}
Assert-LiveHold $false ([pscustomobject]@{HasExited=$false})
Assert-LiveHold $true ([pscustomobject]@{HasExited=$false})
Assert-LiveHold $true ([pscustomobject]@{HasExited=$null})
$script:breakReceipt=$false
Assert-LiveHold $true ([pscustomobject]@{HasExited=$false})
$script:owned=@([pscustomobject]@{HasExited=$true})
$script:events.Clear()
Complete-KeeperHarness $false
if (@($script:events).Count -ne 1 -or $script:events[0] -cne 'receipt-passed') { throw 'Normal keeper receipt behavior differs.' }
foreach ($case in @('keeper-before-resume','keeper-after-ready')) {
    $roots=Get-KeeperCaseRoots $Fixture $case
    $selectedTemp=[IO.Path]::GetFullPath((Join-Path $Fixture 'empty-host'))+[IO.Path]::DirectorySeparatorChar
    foreach ($path in $roots.Values) {
        if (-not [IO.Path]::GetFullPath($path).StartsWith($selectedTemp,[StringComparison]::OrdinalIgnoreCase)) { throw 'Keeper root escapes selected TEMP.' }
    }
    if ($roots.PROXY_TRANSCRIPT_SETTINGS_ROOT -cne (Join-Path (Join-Path $Fixture 'empty-host') $case)) { throw 'Keeper cases are not nested below selected TEMP.' }
}
$valid='{"schema":"proxy-r19-guardian-census-observation-v1","state":"observed","reason":"none","candidate_count":1,"inspected_count":1,"truncated":false,"lineage":"census-not-authority","records":[{"role":"windows-console-host","state":"observed","creation_order":"before-guardian"}]}'
$projected=Get-SafeGuardianObservation ($valid | ConvertFrom-Json)
if ($projected.state -cne 'observed' -or $projected.records[0].role -cne 'windows-console-host' -or
    $projected.records[0].creation_order -cne 'before-guardian' -or $projected.lineage -cne 'census-not-authority') { throw 'Safe guardian projection differs.' }
foreach ($case in @('extra','role','count','state','null')) {
    $bad=$valid | ConvertFrom-Json
    if ($case -eq 'extra') { $bad | Add-Member -NotePropertyName raw_path -NotePropertyValue 'PRIVATE guardian path' }
    if ($case -eq 'role') { $bad.records[0].role='PRIVATE guardian image' }
    if ($case -eq 'count') { $bad.inspected_count=17 }
    if ($case -eq 'state') { $bad.records[0].state='query-unavailable' }
    if ($case -eq 'null') { $bad=$null }
    $safe=Get-SafeGuardianObservation $bad
    if ($safe.state -cne 'unavailable' -or $safe.reason -cne 'invalid-observation' -or
        $safe.records.Count -ne 0 -or ($safe | ConvertTo-Json -Depth 7 -Compress) -match 'PRIVATE|raw_path') { throw 'Malformed guardian projection escaped.' }
}
[Console]::Out.WriteLine('keeper-harness-contracts-passed')
''', encoding='utf-8')
    shell = shutil.which('pwsh')
    assert shell, 'Hosted Windows keeper tests require the workflow PowerShell runtime'
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(script),
        '-ProbeScript', str(source), '-Fixture', str(tmp_path)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or result.stdout.strip() != 'keeper-harness-contracts-passed':
        pytest.fail('Fixed keeper harness receipt/root contract failed', pytrace=False)
