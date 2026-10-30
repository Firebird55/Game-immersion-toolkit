"""One real frozen process owner, restricted to the existing private host probe.

The frontend is real. The API is the existing fixed API probe, with its external
account/game/OCR startup side effects mocked. This is not an installed launcher,
router, updater, migration coordinator or writer-stop/store-copy capability.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

from .runtime_bundle import RuntimeBundleError
from .runtime_probe_common import developer_environment, synthetic_roots
from .windows_preparation_process import WindowsPreparationProcess

SCHEMA = 'proxy-r19-owned-host-probe-v1'
START_TIMEOUT = 60
STOP_TIMEOUT = 10
FRONTEND = 'http://127.0.0.1:3000/'
API = 'http://127.0.0.1:8766'


class HostProbeFailure(RuntimeBundleError):
    def __init__(self, code):
        self.code = code
        super().__init__('Owned frozen host probe failed: ' + code)


class _TcpRow(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
        ('state', 'local_address', 'local_port', 'remote_address', 'remote_port', 'pid')]


def listener_processes():
    """Observe IPv4 listeners for the two canonical addresses; never kill by PID."""
    library = ctypes.WinDLL('iphlpapi', use_last_error=True)
    query = library.GetExtendedTcpTable
    query.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), wintypes.BOOL,
                      ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    query.restype = ctypes.c_uint32
    size = ctypes.c_uint32()
    result = query(None, ctypes.byref(size), False, 2, 3, 0)  # AF_INET, OWNER_PID_LISTENER
    loopback = int.from_bytes(socket.inet_aton('127.0.0.1'), 'little')
    for _ in range(4):
        if result not in (0, 122) or not 4 <= size.value <= 4*1024*1024:
            raise HostProbeFailure('listener-inventory-unavailable')
        buffer = ctypes.create_string_buffer(size.value)
        result = query(buffer, ctypes.byref(size), False, 2, 3, 0)
        if result == 122:
            continue
        if result:
            raise HostProbeFailure('listener-inventory-unavailable')
        count = ctypes.c_uint32.from_buffer(buffer).value
        if count > 65536 or 4 + count*ctypes.sizeof(_TcpRow) > len(buffer):
            raise HostProbeFailure('listener-inventory-unavailable')
        owners = {}
        for index in range(count):
            row = _TcpRow.from_buffer_copy(buffer, 4 + index*ctypes.sizeof(_TcpRow))
            port = socket.ntohs(row.local_port & 0xffff)
            if row.state == 2 and row.local_address in (0, loopback) and port in (3000, 8766):
                owners.setdefault(port, set()).add(row.pid)
        return owners
    raise HostProbeFailure('listener-inventory-unavailable')


class FrozenProbeHost:
    """Own precisely two existing frozen entrypoints and their real Windows job."""
    def __init__(self, layout):
        if (sys.platform != 'win32' or layout.mode != 'bundle' or layout.profile != 'runtime-experiment'
                or layout.executable.name.casefold() != 'proxytranscriptruntime.exe'):
            raise HostProbeFailure('experimental-windows-image-required')
        synthetic_roots(layout)
        developer_environment()
        self.layout = layout
        self.tree = None
        self.processes = {}
        self.logs = []
        self.scratch = None
        self.closed = False

    def start(self):
        if self.tree is not None or self.closed:
            raise HostProbeFailure('host-already-started-or-closed')
        self.layout.work_root.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(tempfile.mkdtemp(prefix='owned-host-', dir=self.layout.work_root))
        self.tree = WindowsPreparationProcess()
        # No arbitrary child, executable, command text, port or live root input.
        commands = [('frontend', self.layout.child_command('frontend', ['--port', '3000'])),
                    ('api', [str(self.layout.executable), '--runtime-probe', 'api'])]
        for role, command in commands:
            output = (self.scratch / (role + '.log')).open('wb')
            self.logs.append(output)
            environment = self.layout.child_environment(role)
            environment['PROXY_TRANSCRIPT_STANDBY'] = '1'
            self.processes[role] = subprocess.Popen(self.tree.command(command), cwd=self.scratch,
                env=environment, stdin=subprocess.DEVNULL,
                stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)

    def _alive(self):
        if any(process.poll() is not None for process in self.processes.values()):
            raise HostProbeFailure('child-exited')

    @contextmanager
    def _listener_scope(self):
        owners = listener_processes()
        kernel = self.tree.kernel
        with ExitStack() as handles:
            def close_observer(handle):
                if not kernel.CloseHandle(handle):
                    raise HostProbeFailure('listener-observer-close-unconfirmed')
            retained = []
            for members in owners.values():
                for pid in members:
                    handle = kernel.OpenProcess(0x101000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED
                    if not handle:
                        raise HostProbeFailure('listener-ownership-unconfirmed')
                    handles.callback(close_observer, handle)
                    member = wintypes.BOOL()
                    if not kernel.IsProcessInJob(handle, self.tree.handle, ctypes.byref(member)):
                        raise HostProbeFailure('listener-ownership-unconfirmed')
                    if not member.value:
                        raise HostProbeFailure('foreign-canonical-listener')
                    if kernel.WaitForSingleObject(handle, 0) != 258:
                        raise HostProbeFailure('listener-exited')
                    retained.append(handle)
            if set(owners) != {3000, 8766} or any(len(members) != 1 for members in owners.values()):
                yield False
                return
            yield True
            # The HTTP result is accepted only while the same real owned
            # listeners and retained process objects are still live.
            if listener_processes() != owners or any(kernel.WaitForSingleObject(handle, 0) != 258 for handle in retained):
                raise HostProbeFailure('listener-ownership-changed')

    @staticmethod
    def _json(path, timeout):
        with urlopen(API + path, timeout=timeout) as response:
            return json.loads(response.read(65537))

    def wait_services(self, timeout=START_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._alive()
            remaining = min(.5, max(.001, deadline-time.monotonic()))
            try:
                with self._listener_scope() as owned:
                    if owned:
                        ready = self._json('/api/runtime/ready', remaining)
                        with urlopen(FRONTEND, timeout=remaining) as response:
                            frontend_ready = response.status == 200
                            response.read(1)
                        if ready.get('ready') is True and frontend_ready:
                            self._alive()
                            return
            except (OSError, ValueError):
                pass
            time.sleep(min(.05, max(0, deadline-time.monotonic())))
        raise HostProbeFailure('readiness-deadline')

    def wait_unprepared_index(self, timeout=3):
        """A fixed negative fixture: live HTTP/OCR-probe, absent ZZZ index."""
        deadline, observed = time.monotonic() + timeout, False
        while time.monotonic() < deadline:
            self._alive()
            try:
                with self._listener_scope() as owned:
                    if owned:
                        state = self._json('/api/runtime/ready?game=zzz', min(.5, max(.001, deadline-time.monotonic())))
                        if state.get('ready') is True:
                            raise HostProbeFailure('negative-index-fixture-was-ready')
                        observed = state.get('ready') is False
            except (OSError, ValueError):
                pass
            time.sleep(min(.05, max(0, deadline-time.monotonic())))
        raise HostProbeFailure('unprepared-index-deadline' if observed else 'negative-index-http-unavailable')

    def members(self):
        self._alive()
        # Private control output only. IDs come from the live owned Job Object;
        # the caller retains observation handles, never uses this JSON to kill.
        return self.tree._process_ids(time.monotonic()+3)

    def exit_frontend(self):
        process = self.processes['frontend']
        if process.poll() is None:
            process.kill()  # The retained Popen handle, not a reopened PID.
        process.wait(timeout=3)

    def monitor(self, stream):
        commands = queue.Queue()
        def read():
            for line in stream:
                commands.put(line.strip())
            commands.put('stop')
        threading.Thread(target=read, daemon=True, name='owned-host-probe-control').start()
        while True:
            self._alive()
            try:
                command = commands.get(timeout=.05)
            except queue.Empty:
                continue
            if command == 'stop':
                return
            if command == 'exit-frontend':
                self.exit_frontend()
            else:
                raise HostProbeFailure('invalid-private-probe-command')

    def close(self, timeout=STOP_TIMEOUT):
        if self.closed:
            return
        deadline = time.monotonic()+timeout
        try:
            # Reap every bootstrap before an empty-job observation. A delayed
            # bootstrap must not join and spawn after cleanup was confirmed.
            for process in self.processes.values():
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=max(.001, deadline-time.monotonic()))
            if self.tree is not None:
                self.tree.terminate(timeout=max(.001, deadline-time.monotonic()))
                self.tree.close()
                self.tree = None
        except (OSError, TimeoutError, subprocess.TimeoutExpired) as error:
            # Retain ownership and private evidence. OS job-handle cleanup on
            # host exit is not reported as confirmed child-process exit.
            raise HostProbeFailure('owned-cleanup-unconfirmed') from error
        finally:
            for output in self.logs:
                output.close()
        if self.scratch is not None:
            shutil.rmtree(self.scratch)
        self.closed = True


def main(kind, layout):
    if kind != 'host':
        raise HostProbeFailure('unknown-host-probe')
    # Fixed authored test controls only. Nothing is accepted by a production
    # child or API; the full runtime profile and source launcher stay unchanged.
    case = sys.stdin.readline().strip()
    if case not in {'normal', 'unprepared-index'}:
        raise HostProbeFailure('invalid-private-probe-case')
    host = FrozenProbeHost(layout)
    failure = None
    try:
        host.start()
        host.wait_services()
        print(json.dumps({'schema': SCHEMA, 'status': 'services-ready', 'kind': 'host',
            'build_id': layout.build_id, 'source_commit': layout.source_commit,
            'job_members': host.members(), 'api_external_side_effects': 'mocked',
            'native_owned_process_tree': 'real', 'r19_complete': False}), flush=True)
        if case == 'unprepared-index':
            host.wait_unprepared_index()
        host.monitor(sys.stdin)
    except BaseException as error:
        failure = error
    try:
        host.close()
    except BaseException as error:
        failure = error
    result = {'schema': SCHEMA, 'status': 'failed' if failure else 'passed', 'kind': 'host',
        'build_id': layout.build_id, 'source_commit': layout.source_commit,
        'api_external_side_effects': 'mocked', 'native_owned_process_tree': 'real',
        'owned_cleanup': 'confirmed' if host.closed else 'unconfirmed', 'r19_complete': False}
    if failure:
        result['failure'] = failure.code if isinstance(failure, HostProbeFailure) else 'unexpected-host-failure'
    print(json.dumps(result), flush=True)
    return 2 if failure else 0
