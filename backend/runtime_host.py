"""Frozen process ownership, with separate private probes and an internal owner.

Fixed probes keep their original mocked API-side-effect scope. The normal
standby building block has no launcher/updater caller or candidate-admission
authority. Neither is a routing, migration or writer-stop/store-copy capability.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
from dataclasses import replace
import hashlib
import json
import math
import ntpath
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from .runtime_bundle import RuntimeBundleError
from .runtime_probe_common import developer_environment, synthetic_roots
from .windows_preparation_process import WindowsPreparationProcess, _kernel as preparation_kernel

SCHEMA = 'proxy-r19-owned-host-probe-v1'
KEEPER_SCHEMA = 'proxy-r19-frozen-keeper-probe-v1'
KEEPER_FAILURES = frozenset({
    'registered-host-unconfirmed', 'keeper-control-unavailable', 'keeper-control-invalid',
    'keeper-guardian-startup', 'keeper-guardian-identity', 'keeper-guardian-descendants',
    'keeper-fixture-unavailable', 'keeper-lease-release-unconfirmed', 'unexpected-keeper-failure',
    'guardian-census-unavailable', 'guardian-census-truncated', 'guardian-census-close-unconfirmed',
    'registered-member-ownership-unconfirmed', 'unknown-registered-member',
    'registered-cohort-incomplete', 'registered-member-observer-unavailable',
    'registered-cohort-aliased', 'registered-observer-close-unconfirmed',
    'registered-listener-unavailable', 'registered-listener-role-mismatch',
    'registered-listener-changed', 'registered-writer-not-live',
    'registered-writer-drain-unconfirmed', 'members-remain-after-registered-stop',
    'readiness-deadline', 'keeper-recovery-required'})
START_TIMEOUT = 60
STOP_TIMEOUT = 10
FRONTEND = 'http://127.0.0.1:3000/'
API = 'http://127.0.0.1:8766'


class HostProbeFailure(RuntimeBundleError):
    def __init__(self, code):
        self.code = code
        super().__init__('Owned frozen host probe failed: ' + code)


class OwnedStandbySlotError(RuntimeBundleError):
    """The retained owner holds the original errors and uncertain resources."""
    def __init__(self, owner):
        self.owner = owner
        super().__init__('The experimental normal standby owner requires review; it cannot be reused.')


def _standby_path(path, directory):
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RuntimeBundleError('Standby inputs cannot traverse links or reparse points.')
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise RuntimeBundleError('Standby input ancestor is not a directory.')
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise RuntimeBundleError('Standby input has an unsupported file type.')
    return info


def _standby_system_environment():
    """Authoritative OS roots only; no inherited keys, proxy or Python settings."""
    kernel = preparation_kernel()
    roots = []
    for name in ('GetSystemDirectoryW', 'GetSystemWindowsDirectoryW'):
        function = getattr(kernel, name)
        function.argtypes, function.restype = [wintypes.LPWSTR, wintypes.UINT], wintypes.UINT
        buffer = ctypes.create_unicode_buffer(32768)
        length = function(buffer, len(buffer))
        if not 0 < length < len(buffer):
            raise RuntimeBundleError('Authoritative Windows directories are unavailable.')
        path = Path(buffer.value)
        if not path.is_absolute():
            raise RuntimeBundleError('Authoritative Windows directory is invalid.')
        _standby_path(path, True)
        roots.append(str(path))
    return {'SystemRoot':roots[1], 'WINDIR':roots[1], 'PATH':os.pathsep.join(roots)}


class OwnedStandbySlot:
    """Internal normal-process owner with permanently closed work admission.

    The caller supplies independently reviewed full inventory pins and a fresh
    disposable root. These pins confer no source, rights or slot eligibility.
    There is deliberately no ordinary launcher/updater/CLI caller.
    """
    def __init__(self, layout, *, disposable, inventory_files, inventory_directories,
                 trusted_manifest_sha256, api_port, frontend_port):
        from .runtime_bundle import RuntimeLayout, relative_resource, EXPERIMENT_CHILDREN
        from .bundle_host import SyntheticRoot
        if (sys.platform != 'win32' or type(layout) is not RuntimeLayout
                or layout.mode != 'bundle' or layout.profile != 'runtime-experiment'
                or layout.resource_root != layout.application_root/'_internal'
                or layout.executable != layout.application_root/'GameImmersionToolkit.exe'
                or layout.children != EXPERIMENT_CHILDREN or layout.legacy_root is not None
                or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',layout.version)
                or not re.fullmatch(r'[a-f0-9]{40}',layout.source_commit)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',layout.build_id)
                or type(disposable) is not SyntheticRoot
                or type(trusted_manifest_sha256) is not str or not re.fullmatch('[a-f0-9]{64}', trusted_manifest_sha256)
                or any(type(port) is not int or not 1024 < port < 65536 or port in (3000,8766)
                       for port in (api_port, frontend_port)) or api_port == frontend_port):
            raise RuntimeBundleError('Need an experimental normal slot, explicit private ports and disposable state.')
        if (type(inventory_files) not in (list,tuple) or type(inventory_directories) not in (list,tuple)
                or not 1 <= len(inventory_files) <= 16384 or len(inventory_directories) > 16384):
            raise RuntimeBundleError('Complete standby inventory is unavailable.')
        files, aliases, total = {}, set(), 0
        def name(value):
            if type(value) is not str or len(value)>1024:
                raise RuntimeBundleError('Unsupported standby inventory name.')
            relative_resource(value)
            if len(value.encode('utf-8')) > 1024 or len(Path(value).parts) > 64 or any(ord(c) < 32 for c in value):
                raise RuntimeBundleError('Unsupported standby inventory name.')
            if value.casefold() in aliases:
                raise RuntimeBundleError('Aliased standby inventory entry.')
            aliases.add(value.casefold())
            return value
        for entry in inventory_files:
            if (type(entry) is not dict or set(entry) != {'path','bytes','sha256'}
                    or type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= 512*1024**2
                    or type(entry['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', entry['sha256'])):
                raise RuntimeBundleError('Unsupported standby inventory identity.')
            files[name(entry['path'])] = (entry['bytes'], entry['sha256'])
            total += entry['bytes']
        directories = tuple(name(value) for value in inventory_directories)
        if (total > 2*1024**3 or files.get('_internal/runtime-manifest.json', (None,None))[1] != trusted_manifest_sha256
                or 'GameImmersionToolkit.exe' not in files):
            raise RuntimeBundleError('Standby inventory does not bind its executable and manifest.')
        self.layout, self.disposable, self.manifest_pin = layout, disposable, trusted_manifest_sha256
        self._files, self._directories = files, frozenset(directories)
        self.api_port, self.frontend_port = api_port, frontend_port
        self.api_origin, self.frontend_origin = f'http://127.0.0.1:{api_port}', f'http://127.0.0.1:{frontend_port}'
        self.tree, self.scratch, self.frontend = None, None, None
        self.children, self.errors, self.unconfirmed_observers, self.unconfirmed_http = {}, [], [], []
        self._abort = threading.Event()
        self.ready = self.closed = self.recovery_required = self.cleanup_confirmed = False
        self._started = self._close_attempted = self._ambiguous_creation = False
        self._membership_unconfirmed = False
        self._validation_failed = False
        self._tree_constructed = False
        self._operation = threading.RLock()
        self._validate_disposable()

    @staticmethod
    def _deadline(timeout):
        if type(timeout) not in (float,int) or not 0 < timeout <= 300 or not math.isfinite(timeout):
            raise ValueError('Need a finite positive standby timeout at most 300 seconds.')
        return time.monotonic()+timeout

    @property
    def ready(self):
        return self._ready and not self._abort.is_set()

    @ready.setter
    def ready(self,value):
        self._ready=value

    def _remaining(self,deadline):
        if self._abort.is_set():
            raise self._failed()
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('The absolute standby deadline expired.')
        return remaining

    def _remember(self, stage, error):
        self._abort.set()
        if not any(current is error for _stage,current in self.errors):
            self.errors.append((stage,error))
        self.recovery_required, self.ready = True, False

    def _failed(self):
        return OwnedStandbySlotError(self)

    def _validate_disposable(self):
        root = self.disposable.path
        _standby_path(root, True)
        if _standby_path(root/'.r19-synthetic-fixture.json', False).st_size>4096:
            raise RuntimeBundleError('Disposable standby marker exceeds its bound.')
        self.disposable.verify()
        with os.scandir(root) as entries:
            if any(entry.name != '.r19-synthetic-fixture.json' for entry in entries):
                raise RuntimeBundleError('Normal standby state must start marker-only.')
        for name in ('settings_root','data_root','cache_root','work_root','tool_root','state_root','default_export_root'):
            path = getattr(self.layout,name)
            if (path == root or not path.is_relative_to(root)
                    or any(path.is_relative_to(root/name) or (root/name).is_relative_to(path)
                           for name in ('host-profile','host-temp'))):
                raise RuntimeBundleError('Every standby writable root must be separate from the private profile.')

    def _verify_slot(self, deadline):
        try:
            return self._verify_slot_bytes(deadline)
        except BaseException:
            # Existing readers retain their actual stream in the original
            # traceback on close failure. Do not infer full cleanup from an
            # empty process set after any uncertain input verification.
            self._validation_failed = True
            raise

    def _verify_slot_bytes(self, deadline):
        from .desktop_frontend import _experimental_slot_frontend
        root = self.layout.application_root
        _standby_path(root, True)
        seen_files, seen_directories, pending = set(), set(), [root]
        while pending:
            directory = pending.pop()
            _standby_path(directory, True)
            with os.scandir(directory) as entries:
                for entry in entries:
                    self._remaining(deadline)
                    path = directory/entry.name
                    name = path.relative_to(root).as_posix()
                    if name in self._directories:
                        _standby_path(path, True); seen_directories.add(name); pending.append(path)
                    elif name in self._files:
                        info = _standby_path(path, False)
                        size, expected = self._files[name]
                        if info.st_size != size or info.st_nlink != 1:
                            raise RuntimeBundleError('Standby file size or single-file identity differs.')
                        digest, count = hashlib.sha256(), 0
                        with path.open('rb') as stream:
                            while True:
                                self._remaining(deadline)
                                chunk = stream.read(min(1024**2,size-count+1))
                                if not chunk: break
                                count += len(chunk); digest.update(chunk)
                                if count > size: raise RuntimeBundleError('Standby file grew outside its pin.')
                        if count != size or digest.hexdigest() != expected:
                            raise RuntimeBundleError('Standby file checksum differs.')
                        seen_files.add(name)
                    else:
                        raise RuntimeBundleError('Standby tree has an unknown inventory entry.')
        if seen_files != set(self._files) or seen_directories != self._directories:
            raise RuntimeBundleError('Standby tree is missing an inventory entry.')
        for name, digest in self.layout.resources.items():
            if self._files.get('_internal/'+name, (None,None))[1] != digest:
                raise RuntimeBundleError('Standby resources differ from the complete inventory.')
        self.frontend = _experimental_slot_frontend(self.layout, self.manifest_pin)
        self._remaining(deadline)

    @contextmanager
    def _job(self, deadline):
        lock = self.tree._lifecycle
        if not lock.acquire(timeout=max(0,deadline-time.monotonic())):
            raise TimeoutError('Standby native control is still busy.')
        try: yield
        finally: lock.release()

    def _live(self):
        if any(self.tree.kernel.WaitForSingleObject(child.process_handle,0) != 258 for child in self.children.values()):
            raise RuntimeBundleError('A retained standby process is not live.')

    def _observe(self, pid):
        kernel = self.tree.kernel
        handle = kernel.OpenProcess(0x101000,False,pid)
        if not handle: raise RuntimeBundleError('Standby observation is unavailable.')
        primary = None
        try:
            member = wintypes.BOOL()
            if not kernel.IsProcessInJob(handle,self.tree.handle,ctypes.byref(member)) or not member.value:
                raise RuntimeBundleError('Standby listener/member belongs to another Job.')
            matches = [role for role,child in self.children.items() if child.created and not child.closed
                       and same_process_object(handle,child.process_handle)]
            if len(matches) != 1 or kernel.WaitForSingleObject(handle,0) != 258:
                raise RuntimeBundleError('Standby observation is not one live genuine creation object.')
            return matches[0]
        except BaseException as error:
            primary = error
            self._remember('observation',error)
            raise
        finally:
            try:
                if not kernel.CloseHandle(handle):
                    error = OSError('Standby observer close is unconfirmed.')
                    error.winerror = ctypes.get_last_error()
                    raise error
            except BaseException as error:
                self.unconfirmed_observers.append(handle)  # Never query, close or retry this raw value again.
                self._remember('observer-close',error)
                if primary is None: raise

    def _census(self, deadline, *, complete):
        try:
            members = self.tree._process_ids(deadline)
            if (len(members) > 2 or len(set(members)) != len(members)
                    or any(type(pid) is not int or pid <= 0 for pid in members)):
                raise RuntimeBundleError('Standby Job membership is unknown or aliased.')
            roles = [self._observe(pid) for pid in members]
            if len(set(roles)) != len(roles) or complete and set(roles) != {'api','frontend'}:
                raise RuntimeBundleError('Standby Job membership is incomplete or aliased.')
        except BaseException:
            self._membership_unconfirmed = True
            raise

    @contextmanager
    def _listeners(self, deadline):
        self._census(deadline,complete=True); self._live()
        expected = {self.api_port:'api',self.frontend_port:'frontend'}
        observed = listener_processes(tuple(expected))
        for port,members in observed.items():
            if port not in expected or len(members) != 1 or self._observe(next(iter(members))) != expected[port]:
                raise RuntimeBundleError('Standby listener is not its retained role.')
        complete = set(observed) == set(expected)
        yield complete
        after = listener_processes(tuple(expected))
        for port,members in after.items():
            if port not in expected or len(members) != 1 or self._observe(next(iter(members))) != expected[port]:
                raise RuntimeBundleError('Standby listener is not its retained role.')
        if complete and after != observed:
            raise RuntimeBundleError('Standby listener identity changed during HTTP.')
        self._census(deadline,complete=True); self._live()

    def _http(self, port, path, limit, deadline):
        """Fixed loopback HTTP/1.x, bounded bytes and one deadline through every recv."""
        connection = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        primary = None
        try:
            connection.settimeout(self._remaining(deadline)); connection.connect(('127.0.0.1',port))
            connection.settimeout(self._remaining(deadline))
            connection.sendall(f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n'.encode('ascii'))
            raw = bytearray()
            while b'\r\n\r\n' not in raw:
                connection.settimeout(self._remaining(deadline)); data = connection.recv(4096)
                if not data: raise RuntimeBundleError('Standby HTTP headers ended early.')
                raw.extend(data)
                if len(raw) > 65536+limit: raise RuntimeBundleError('Standby HTTP exceeded its bound.')
                if b'\r\n\r\n' not in raw and len(raw) > 65536:
                    raise RuntimeBundleError('Standby HTTP headers exceed their bound.')
            head, body = bytes(raw).split(b'\r\n\r\n',1)
            lines, headers = head.split(b'\r\n'), {}
            if len(head) > 65536 or len(lines) > 100 or not re.fullmatch(rb'HTTP/1\.[01] 200 [^\r\n]*',lines[0]):
                raise RuntimeBundleError('Standby HTTP status/headers differ.')
            for line in lines[1:]:
                key, separator, value = line.partition(b':')
                key = key.lower()
                if not separator or not re.fullmatch(rb'[a-z0-9-]+',key) or key in headers:
                    raise RuntimeBundleError('Standby HTTP header is duplicate or malformed.')
                headers[key] = value.strip()
            length = headers.get(b'content-length',b'')
            if not re.fullmatch(rb'[0-9]{1,10}',length) or b'transfer-encoding' in headers or int(length)>limit or len(body)>int(length):
                raise RuntimeBundleError('Standby HTTP framing exceeds the fixed response contract.')
            body = bytearray(body)
            while len(body) < int(length):
                connection.settimeout(self._remaining(deadline)); data = connection.recv(min(65536,int(length)-len(body)))
                if not data: raise RuntimeBundleError('Standby HTTP body ended early.')
                body.extend(data)
            self._remaining(deadline)
            return bytes(body),headers
        except BaseException as error:
            primary = error
            raise
        finally:
            try: connection.close()
            except BaseException as error:
                self.unconfirmed_http.append(connection); self._remember('http-close',error)
                if primary is None: raise

    def start(self, timeout=START_TIMEOUT):
        deadline = self._deadline(timeout)
        if not self._operation.acquire(timeout=self._remaining(deadline)):
            error=TimeoutError('Standby owner control is busy; retain its actual owner.')
            self._remember('control-lock',error)
            raise self._failed() from error
        try:
            if self._started or self.recovery_required or self.closed: raise self._failed()
            self._started = True
            try:
                self._validate_disposable(); self._verify_slot(deadline)
                root = self.disposable.path
                profile, temporary = root/'host-profile',root/'host-temp'
                profile.mkdir(); temporary.mkdir()
                base = _standby_system_environment()
                base.update({name:str(profile) for name in ('LOCALAPPDATA','APPDATA','USERPROFILE','HOME')})
                base.update(TEMP=str(temporary),TMP=str(temporary))
                self.layout.work_root.mkdir(parents=True)
                self.scratch = Path(tempfile.mkdtemp(prefix='normal-standby-',dir=self.layout.work_root))
                self._remaining(deadline)
                # Keep the actual owner before its native constructor can
                # acquire a Job and then fail its own close. No factory or
                # traceback-derived adoption supplies this ownership record.
                self.tree = WindowsPreparationProcess.__new__(WindowsPreparationProcess)
                WindowsPreparationProcess.__init__(self.tree)
                self._tree_constructed = True
                with self._job(deadline):
                    for role,args in (('frontend',['--port',str(self.frontend_port)]),('api',['--port',str(self.api_port),'--standby','--candidate-closed'])):
                        self._remaining(deadline)
                        before = tuple(self.tree.created_children)
                        try:
                            child = self.tree.create_suspended(self.layout.child_command(role,args),cwd=self.scratch,
                                env=self.layout.child_environment(role,environ=base),detached_console=True)
                        finally:
                            added = self.tree.created_children[len(before):]
                            if len(added) == 1: self.children[role] = added[0]
                            elif added: self._ambiguous_creation = True
                        if role not in self.children or child is not self.children[role] or child.owner is not self.tree:
                            self._ambiguous_creation = True
                            raise RuntimeBundleError('Standby creation output is not its retained native registry record.')
                        self._remaining(deadline)
                    from .windows_preparation_process import _SuspendedChild
                    values = tuple(self.children.values())
                    if (any(not isinstance(child,_SuspendedChild) or not child.created or child.closed for child in values)
                            or len({id(child) for child in values}) != 2
                            or same_process_object(values[0].process_handle,values[1].process_handle)):
                        self._ambiguous_creation = True
                        raise RuntimeBundleError('Standby role creations have an ambiguous lifetime identity.')
                    self._census(deadline,complete=True)
                    for child in self.children.values():
                        self._remaining(deadline); child.resume_once(); self._remaining(deadline)
                    while True:
                        self._remaining(deadline)
                        with self._listeners(deadline) as listening:
                            if listening:
                                body,_ = self._http(self.api_port,'/api/runtime/ready',65536,deadline)
                                from .desktop_frontend import _unique_object
                                result = json.loads(body,object_pairs_hook=_unique_object)
                                index = self.frontend.files['index.html']
                                body,headers = self._http(self.frontend_port,'/',index['bytes'],deadline)
                                if (len(body) != index['bytes'] or hashlib.sha256(body).hexdigest() != index['sha256']
                                        or headers.get(b'etag') != ('"'+index['sha256']+'"').encode('ascii')
                                        or headers.get(b'content-type') != index['mime'].encode('ascii')):
                                    raise RuntimeBundleError('Normal standby frontend identity differs.')
                                if (type(result) is not dict or set(result)!={'ready','standby'}
                                        or type(result.get('ready')) is not bool or result.get('standby') is not True):
                                    raise RuntimeBundleError('Normal standby readiness response differs.')
                                if result['ready']:
                                    self._verify_slot(deadline); self.ready = True; self._remaining(deadline); return self
                        time.sleep(min(.05,self._remaining(deadline)))
            except BaseException as error:
                self._remember('start',error)
                self._cleanup(deadline)
                raise self._failed() from error
        finally: self._operation.release()

    def _cleanup(self, deadline):
        self._close_attempted, self.ready = True, False
        errors_before = len(self.errors)
        try:
            if self.tree is not None:
                if not self._tree_constructed or getattr(self.tree,'_ownership_unconfirmed',False):
                    raise RuntimeBundleError('Standby native-owner initialization/ownership is unconfirmed.')
                with self._job(deadline):
                    self.tree._admission_closed = True
                    if not self._ambiguous_creation:
                        try: self._census(deadline,complete=False)
                        except BaseException as error: self._remember('pre-stop-census',error)
                    for child in (() if self._ambiguous_creation else self.tree.created_children):
                        if child.closed: continue
                        try: child.stop_and_wait(deadline)
                        except BaseException as error: self._remember('writer-stop',error)
                        if child.exited and not child.closed:
                            try: child.close_after_exit()
                            except BaseException as error: self._remember('writer-close',error)
                    if not self._ambiguous_creation and not self._membership_unconfirmed and all(child.closed for child in self.tree.created_children):
                        if self.tree._process_ids(deadline): raise RuntimeBundleError('Unknown standby members remain after retained writer stop.')
                        self.tree.close()
                    else:
                        raise RuntimeBundleError('Standby creation cleanup is unconfirmed.')
            self.cleanup_confirmed = (len(self.errors) == errors_before and not self._validation_failed
                and not self.unconfirmed_observers and not self.unconfirmed_http)
            if self.cleanup_confirmed and not self.recovery_required:
                if self.scratch is not None: shutil.rmtree(self.scratch)
                self.closed = True
        except BaseException as error:
            self.cleanup_confirmed = False
            self._remember('cleanup',error)

    def close(self, timeout=STOP_TIMEOUT):
        deadline = self._deadline(timeout)
        if not self._operation.acquire(timeout=self._remaining(deadline)):
            error=TimeoutError('Standby owner control is busy; retain its actual owner.')
            self._remember('control-lock',error)
            raise self._failed() from error
        try:
            if self.closed: return
            if self._close_attempted: raise self._failed()
            self._cleanup(deadline)
            if not self.closed: raise self._failed() from (self.errors[0][1] if self.errors else None)
        finally: self._operation.release()


class _TcpRow(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
        ('state', 'local_address', 'local_port', 'remote_address', 'remote_port', 'pid')]


def listener_processes(ports=(3000, 8766)):
    """Observe selected IPv4 listeners; never authorize termination by PID."""
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
            if row.state == 2 and row.local_address in (0, loopback) and port in ports:
                owners.setdefault(port, set()).add(row.pid)
        return owners
    raise HostProbeFailure('listener-inventory-unavailable')


def same_process_object(first, second):
    library = ctypes.WinDLL('kernelbase', use_last_error=True)
    compare = library.CompareObjectHandles
    compare.argtypes, compare.restype = [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL
    return bool(compare(first, second))


class _ProcessEntry(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('usage', ctypes.c_uint32), ('pid', ctypes.c_uint32),
        ('heap', ctypes.c_size_t), ('module', ctypes.c_uint32), ('threads', ctypes.c_uint32),
        ('parent', ctypes.c_uint32), ('priority', ctypes.c_int32), ('flags', ctypes.c_uint32),
        ('image', ctypes.c_wchar * 260)]


def guardian_children(pid):
    """A bounded current census, never complete lifetime/admission evidence.

    Only parent/child identifiers are considered privately; no process name,
    system inventory or PID is published or adopted as termination authority.
    """
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes, kernel.CreateToolhelp32Snapshot.restype = [ctypes.c_uint32, ctypes.c_uint32], wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes, function.restype = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS only.
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise HostProbeFailure('guardian-census-unavailable')
    try:
        entry = _ProcessEntry(); entry.size = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            raise HostProbeFailure('guardian-census-unavailable')
        parents = {}
        for _ in range(65536):
            parents[entry.pid] = entry.parent
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise HostProbeFailure('guardian-census-unavailable')
                break
        else:
            raise HostProbeFailure('guardian-census-truncated')
        pending, descendants = {pid}, set()
        while pending:
            children = {child for child, parent in parents.items() if parent in pending} - descendants - {pid}
            descendants.update(children); pending = children
        return descendants
    finally:
        if not kernel.CloseHandle(snapshot):
            raise HostProbeFailure('guardian-census-close-unconfirmed')


def _empty_guardian_observation():
    return {'schema': 'proxy-r19-guardian-census-observation-v1', 'state': 'not-observed',
        'reason': 'none', 'candidate_count': 0, 'inspected_count': 0, 'truncated': False,
        'lineage': 'census-not-authority', 'records': []}


def _guardian_observer_kernel():
    kernel = preparation_kernel()  # Reuse existing observer/wait/close bindings.
    fields = ctypes.POINTER(wintypes.FILETIME)
    for name, args, result in (
        ('GetProcessTimes', [wintypes.HANDLE, fields, fields, fields, fields], wintypes.BOOL),
        ('QueryFullProcessImageNameW', [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ('GetSystemDirectoryW', [wintypes.LPWSTR, wintypes.UINT], wintypes.UINT),
        ('GetProcessId', [wintypes.HANDLE], wintypes.DWORD)):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel


def _guardian_image_role(actual, runtime, system_directory, retained_creation):
    # Same exact-path principle as C1; a matching basename/prefix grants nothing.
    if actual.startswith(('\\\\?\\', '\\\\.\\')):
        return 'unknown'
    key = lambda value: ntpath.normcase(ntpath.normpath(str(value)))
    if key(actual) == key(runtime):
        return 'retained-runtime-creation' if retained_creation else 'runtime-image-only'
    if key(actual) == key(ntpath.join(system_directory, 'conhost.exe')):
        return 'windows-console-host'
    return 'unknown'


def observe_guardian_candidates(guardian, runtime, candidates, retained, known_creations=()):
    """Failure-only read-only observation, never lineage/admission authority.

    Keep genuine observation objects during each query. A stale parent PID or
    creation ordering cannot promote a census candidate into an owned child.
    Unknown native outcomes retain the private handles without reuse or retry.
    """
    report = _empty_guardian_observation()
    report.update(state='observed', candidate_count=min(len(candidates), 65536))
    if retained:
        report.update(state='unavailable', reason='prior-observation-unconfirmed', truncated=bool(candidates))
        return report
    deadline = time.monotonic()+3

    def fail(reason):
        report.update(state='unavailable', reason=reason)
        # Any already-created observation handles remain private/inaccessible
        # after an unconfirmed native call; the surrounding keeper holds alive.
        for record in retained:
            record['poisoned'] = True

    def stamp(handle):
        values = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
            raise OSError('query-unavailable')
        return values[0].dwHighDateTime << 32 | values[0].dwLowDateTime

    def image(handle):
        buffer, count = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(count)) or not 0 < count.value < len(buffer):
            raise OSError('query-unavailable')
        return buffer.value

    def open_observer(pid):
        handle = kernel.OpenProcess(0x101000, False, pid)
        if handle:
            record = {'handle': handle, 'poisoned': False}
            retained.append(record)
            return record

    try:
        kernel = _guardian_observer_kernel()
        root = guardian._handle  # Retained genuine Popen creation handle.
        if (kernel.GetProcessId(root) != guardian.pid or kernel.WaitForSingleObject(root, 0) != 258):
            fail('root-unavailable')
            return report
        root_stamp = stamp(root)
        system = ctypes.create_unicode_buffer(32768)
        length = kernel.GetSystemDirectoryW(system, len(system))
        if not 0 < length < len(system):
            fail('query-unavailable')
            return report
        for pid in sorted(candidates)[:16]:
            if time.monotonic() >= deadline:
                fail('query-budget-exhausted'); break
            item = {'role': 'unknown', 'state': 'observed', 'creation_order': 'unavailable'}
            report['records'].append(item)
            first = open_observer(pid)
            if first is None:
                item['state'] = 'open-unavailable'
                report.update(state='unavailable', reason='query-unavailable')
                continue
            held = [first]
            try:
                result = kernel.WaitForSingleObject(first['handle'], 0)
                if result == 0:
                    item['state'] = 'exit-observed'
                    report.update(state='unavailable', reason='query-unavailable')
                elif result != 258 or kernel.GetProcessId(first['handle']) != pid:
                    item['state'] = 'identity-unavailable'; fail('identity-unavailable'); break
                else:
                    started = stamp(first['handle'])
                    item['creation_order'] = 'before-guardian' if started < root_stamp else 'at-or-after-guardian'
                    actual = image(first['handle'])
                    second = open_observer(pid)
                    if second is None:
                        item['state'] = 'identity-unavailable'; fail('identity-unavailable'); break
                    held.append(second)
                    if not same_process_object(first['handle'], second['handle']):
                        item['state'] = 'identity-changed'; fail('identity-changed'); break
                    live = kernel.WaitForSingleObject(first['handle'], 0)
                    if live not in (0, 258):
                        item['state'] = 'identity-unavailable'; fail('identity-unavailable'); break
                    root_live = kernel.WaitForSingleObject(root, 0)
                    if root_live not in (0, 258):
                        item['state'] = 'identity-unavailable'; fail('root-unavailable'); break
                    if live == 0 or root_live == 0:
                        item['state'] = 'exit-observed'
                        report.update(state='unavailable', reason='query-unavailable')
                    else:
                        created = any(same_process_object(first['handle'], handle) for handle in (root, *known_creations))
                        item['role'] = _guardian_image_role(actual, runtime, system.value, created)
                for record in reversed(held):
                    try:
                        closed = kernel.CloseHandle(record['handle'])
                    except BaseException:
                        closed = False
                    if not closed:
                        item.update(role='unknown', state='observer-close-unconfirmed'); fail('observer-close-unconfirmed'); break
                    retained.remove(record)
                if report['reason'] == 'observer-close-unconfirmed':
                    break
            except BaseException:
                item['state'] = 'query-unavailable'; fail('query-unavailable'); break
    except BaseException:
        fail('query-unavailable')
    finally:
        report['inspected_count'] = len(report['records'])
        report['truncated'] = report['candidate_count'] > report['inspected_count']
    return report


class FrozenProbeHost:
    """Own precisely two existing frozen entrypoints and their real Windows job."""
    def __init__(self, layout):
        if (sys.platform != 'win32' or layout.mode != 'bundle' or layout.profile != 'runtime-experiment'
                or layout.executable != layout.application_root/'GameImmersionToolkit.exe'):
            raise HostProbeFailure('experimental-windows-image-required')
        synthetic_roots(layout)
        developer_environment()
        self.layout = layout
        self.tree = None
        self.processes = {}
        self.logs = []
        self.scratch = None
        self.closed = False
        self.registered_mode = False
        self.registered = {}
        self.recovery_required = False
        self._source_admission_started = self._source_admitted = False

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

    def _recovery(self, code):
        self.recovery_required = True
        raise HostProbeFailure(code)

    def start_registered(self, *, detached_console=False, wal_probe=False, grammar_probe=False, populated_probe=False):
        """Create the two fixed actual writers before resuming either of them."""
        if (type(wal_probe) is not bool or type(grammar_probe) is not bool or type(populated_probe) is not bool
                or sum((wal_probe, grammar_probe, populated_probe)) > 1
                or populated_probe and detached_console is not True):
            raise HostProbeFailure('invalid-private-probe-case')
        if self.tree is not None or self.closed:
            raise HostProbeFailure('host-already-started-or-closed')
        populated = None
        if populated_probe:
            from .runtime_probe import populated_roots
            populated = populated_roots(self.layout)
        self.registered_mode = True
        self.layout.work_root.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(tempfile.mkdtemp(prefix='registered-host-', dir=self.layout.work_root))
        self.tree = WindowsPreparationProcess()
        commands = [('frontend', self.layout.child_command('frontend', ['--port', '3000'])),
                    ('api', [str(self.layout.executable), '--runtime-probe',
                             'api-populated' if populated_probe else 'api-grammar' if grammar_probe else 'api-wal' if wal_probe else 'api'])]
        try:
            for role, command in commands:
                environment = self.layout.child_environment(role)
                environment['PROXY_TRANSCRIPT_STANDBY'] = '1'
                if populated_probe and role == 'api':
                    environment['LOCALAPPDATA'] = str(populated['host-profile'].path)
                self.registered[role] = self.tree.create_suspended(command, cwd=self.scratch, env=environment,
                    detached_console=detached_console)
            self.check_registered_members()
        except BaseException:
            self.recovery_required = True
            raise

    def _registered_role(self, observer):
        kernel = self.tree.kernel
        member = wintypes.BOOL()
        if not kernel.IsProcessInJob(observer, self.tree.handle, ctypes.byref(member)) or not member.value:
            self._recovery('registered-member-ownership-unconfirmed')
        matches = [role for role, child in self.registered.items()
                   if same_process_object(observer, child.process_handle)]
        if len(matches) != 1:
            self._recovery('unknown-registered-member')
        return matches[0]

    def check_registered_members(self, require_all=True):
        if self.recovery_required:
            raise HostProbeFailure('keeper-recovery-required')
        if self.tree is None or set(self.registered) != {'frontend', 'api'}:
            self._recovery('registered-cohort-incomplete')
        kernel = self.tree.kernel
        with self.tree._lifecycle:
            seen = set()
            for pid in self.tree._process_ids(time.monotonic()+3):
                observer = kernel.OpenProcess(0x101000, False, pid)
                if not observer:
                    self._recovery('registered-member-observer-unavailable')
                try:
                    role = self._registered_role(observer)
                    if role in seen:
                        self._recovery('registered-cohort-aliased')
                    seen.add(role)
                finally:
                    if not kernel.CloseHandle(observer):
                        self._recovery('registered-observer-close-unconfirmed')
            if require_all and seen != {'frontend', 'api'}:
                self._recovery('registered-cohort-incomplete')

    def resume_registered(self):
        try:
            self.check_registered_members()
            for child in self.registered.values():
                child.resume_once()
        except BaseException:
            self.recovery_required = True
            raise

    def quiesce_registered(self):
        """Existing opt-in C2 barrier, only for the paused authored API probe."""
        if not self.registered_mode:
            raise HostProbeFailure('registered-cohort-required')
        with self._registered_listener_scope() as owned:
            if not owned:
                self._recovery('registered-listener-unavailable')
            request = Request(API+'/api/runtime/quiesce?writers=true', data=b'', method='POST',
                              headers={'X-Proxy-Transcript': 'update'})
            # The API owns its existing total 30-second deadline; 35 is only
            # the transport budget. A failure leaves the keeper holding leases.
            with urlopen(request, timeout=35) as response:
                handoff = json.loads(response.read(65537))
                if response.status != 200 or handoff.get('running') is not False:
                    self._recovery('registered-writer-drain-unconfirmed')
            try:
                with urlopen(API+'/api/status', timeout=3) as response:
                    status = response.status
                    response.read(1)
            except HTTPError as response:
                with response:
                    status = response.code
                    response.read(1)
            if status != 503 or self._json('/api/health', 3).get('status') != 'ok':
                self._recovery('registered-writer-drain-unconfirmed')

    def _registered_startup_complete(self):
        """Validate observed startup listeners; never grant scoped HTTP authority."""
        try:
            self._alive()
            self.check_registered_members()
            owners, kernel = listener_processes(), self.tree.kernel
            with self.tree._lifecycle:
                for port, members in owners.items():
                    for pid in members:
                        observer = kernel.OpenProcess(0x101000, False, pid)
                        if not observer:
                            self._recovery('registered-listener-unavailable')
                        try:
                            role = self._registered_role(observer)
                            if role != {3000: 'frontend', 8766: 'api'}.get(port):
                                self._recovery('registered-listener-role-mismatch')
                        finally:
                            if not kernel.CloseHandle(observer):
                                self._recovery('registered-observer-close-unconfirmed')
                self._alive()
                self.check_registered_members()
            return set(owners) == {3000, 8766} and all(len(ids) == 1 for ids in owners.values())
        except BaseException:
            self.recovery_required = True
            raise

    @contextmanager
    def _registered_listener_scope(self):
        self.check_registered_members()
        owners, kernel = listener_processes(), self.tree.kernel
        with self.tree._lifecycle:
            for port, members in owners.items():
                for pid in members:
                    observer = kernel.OpenProcess(0x101000, False, pid)
                    if not observer:
                        self._recovery('registered-listener-unavailable')
                    try:
                        role = self._registered_role(observer)
                        if role != ('frontend' if port == 3000 else 'api'):
                            self._recovery('registered-listener-role-mismatch')
                    finally:
                        if not kernel.CloseHandle(observer):
                            self._recovery('registered-observer-close-unconfirmed')
            ready = set(owners) == {3000, 8766} and all(len(ids) == 1 for ids in owners.values())
            yield ready
            if listener_processes() != owners:
                self._recovery('registered-listener-changed')
            self._alive()
            self.check_registered_members()

    def _alive(self):
        if self.registered_mode:
            for child in self.registered.values():
                if self.tree.kernel.WaitForSingleObject(child.process_handle, 0) != 258:
                    self._recovery('registered-writer-not-live')
        if any(process.poll() is not None for process in self.processes.values()):
            raise HostProbeFailure('child-exited')

    @contextmanager
    def _listener_scope(self):
        if self.registered_mode:
            with self._registered_listener_scope() as ready:
                yield ready
            return
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

    def _admit_authored_source(self, deadline):
        """One fixed source-fixture control; never copied-target activation.

        This class starts only the mocked native/account API probe entrypoints.
        OwnedStandbySlot has no such control and its admission stays closed.
        """
        if self._source_admission_started or self.recovery_required:
            raise HostProbeFailure('registered-host-unconfirmed')
        self._source_admission_started = True
        try:
            with self._listener_scope() as owned:
                self._alive()
                if not owned:
                    raise HostProbeFailure('registered-host-unconfirmed')
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise HostProbeFailure('readiness-deadline')
                request = Request(API+'/api/runtime/activate', data=b'{"running":false}', method='POST',
                    headers={'Content-Type': 'application/json', 'X-Proxy-Transcript': 'update'})
                with urlopen(request, timeout=remaining) as response:
                    raw = response.read(65537)
                    if response.status != 200 or len(raw) > 65536:
                        raise HostProbeFailure('registered-host-unconfirmed')
                    # Preserve pairs so duplicate/unknown response keys cannot
                    # turn an ambiguous response into a normal acknowledgement.
                    value = json.loads(raw, object_pairs_hook=list)
                    if value != [('active', True)] or value[0][1] is not True:
                        raise HostProbeFailure('registered-host-unconfirmed')
                self._alive()
                if time.monotonic() >= deadline:
                    raise HostProbeFailure('readiness-deadline')
            # The scope's final genuine listener/creation checks must finish
            # before callers may perform even an authored favorite/readback.
            if time.monotonic() >= deadline:
                raise HostProbeFailure('readiness-deadline')
            self._source_admitted = True
        except BaseException:
            self.recovery_required = True
            raise

    def wait_services(self, timeout=START_TIMEOUT):
        deadline = time.monotonic() + timeout
        if self._source_admission_started:
            raise HostProbeFailure('registered-host-unconfirmed')
        while time.monotonic() < deadline:
            self._alive()
            ready_to_admit = False
            remaining = min(.5, max(.001, deadline-time.monotonic()))
            # Missing owned listeners during startup are observation-only.
            # Native/identity/cleanup failures must escape the HTTP retry catch.
            if self.registered_mode and not self._registered_startup_complete():
                time.sleep(min(.05, max(0, deadline-time.monotonic())))
                continue
            try:
                with self._listener_scope() as owned:
                    if owned:
                        try:
                            ready = self._json('/api/runtime/ready', remaining)
                            with urlopen(FRONTEND, timeout=remaining) as response:
                                frontend_ready = response.status == 200
                                response.read(1)
                            if ready.get('ready') is True and frontend_ready:
                                self._alive()
                                ready_to_admit = True
                        except (OSError, ValueError):
                            pass  # Only unready HTTP is a startup observation.
            except BaseException:
                # A scope-exit/native observer failure cannot be converted into
                # permission to admit an apparently ready source fixture.
                self.recovery_required = True
                raise
            if ready_to_admit:
                # Activation/identity/cleanup failures are not retryable startup
                # observations. Keep the actual source cohort and leases owned.
                self._admit_authored_source(deadline)
                return
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
        if self.registered_mode:
            return self._close_registered(timeout)
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

    def _close_registered(self, timeout):
        if self.recovery_required:
            raise HostProbeFailure('keeper-recovery-required')
        deadline = time.monotonic()+timeout
        try:
            with self.tree._lifecycle:
                self.tree._admission_closed = True
                self.check_registered_members(require_all=False)
                for child in self.registered.values():
                    child.stop_and_wait(deadline)
                # Unknown descendants must never disappear through the legacy
                # generic drain and become a passing fixed-cohort result.
                if self.tree._process_ids(deadline):
                    self._recovery('members-remain-after-registered-stop')
                self.tree.close()
                self.tree = None
            shutil.rmtree(self.scratch)
            self.closed = True
        except BaseException:
            self.recovery_required = True
            raise


def hold_keeper_recovery():
    # Exiting would close leases before unknown writers were confirmed stopped.
    # The build-host harness may terminate us only as an unverified failure.
    while True:
        time.sleep(5)


class _FrozenKeeperProbe:
    """Fixed probe orchestration around FrozenProbeHost, not a second host."""
    def __init__(self, layout, case, stream):
        FrozenProbeHost(layout)  # Same profile/image/synthetic/dev-tool guards.
        self.layout, self.case = layout, case
        self.host = self.guardian = None
        self.leases = []
        self.fixture = layout.work_root / 'keeper-fixture'
        self.commands = queue.Queue(maxsize=4)
        self.guardian_port = None
        self.guardian_signaled = False
        self.released = False
        self.descendant_observation = _empty_guardian_observation()
        self._guardian_observer_holds = []
        def read():
            try:
                while True:
                    line = stream.readline(65)
                    if not line:
                        self.commands.put(None); return
                    if len(line) > 64 or not line.endswith('\n'):
                        self.commands.put('invalid'); return
                    self.commands.put(line.strip())
            except BaseException:
                self.commands.put(None)
        threading.Thread(target=read, daemon=True, name='fixed-keeper-probe-input').start()

    def emit(self, phase, *, status='observing', failure=None):
        records = self.host.registered.values() if self.host is not None else ()
        value = {'schema': KEEPER_SCHEMA, 'kind': 'keeper', 'phase': phase,
            'case': self.case, 'status': status, 'build_id': self.layout.build_id,
            'source_commit': self.layout.source_commit, 'writers_created': len(self.host.registered) if self.host else 0,
            'writers_resumed': sum(child.resumed for child in records),
            'guardian': 'readonly-frozen-frontend-port-zero', 'guardian_exit': 'signaled' if self.guardian_signaled else 'not-confirmed',
            'guardian_console_mode': 'detached-process', 'writer_console_mode': 'detached-process',
            'api_external_side_effects': 'mocked', 'native_owned_process_tree': 'real',
            'census': 'observations-only-not-lifetime-proof', 'keeper_loss': 'unavailable',
            'dynamic_writer_admission': 'unavailable', 'production_activation': False,
            'store_copy': False, 'installer': 'not-built', 'r19_complete': False}
        if failure is not None:
            # Only fixed code categories, never exception/model/log/path text.
            value['failure'] = failure if failure in KEEPER_FAILURES else 'unexpected-keeper-failure'
            value['guardian_descendants'] = self.descendant_observation
        print(json.dumps(value), flush=True)

    def command(self, expected, timeout=60):
        try:
            value = self.commands.get(timeout=timeout)
        except queue.Empty as error:
            raise HostProbeFailure('keeper-control-unavailable') from error
        if value != expected:
            raise HostProbeFailure('keeper-control-invalid')

    def prepare(self):
        from .bundle_host import ExclusiveFileLease, _reject_links
        temporary = Path(tempfile.gettempdir()).resolve()
        _reject_links(self.layout.work_root)
        if not self.layout.work_root.resolve().is_relative_to(temporary):
            raise HostProbeFailure('keeper-fixture-unavailable')
        self.fixture.mkdir(parents=True, exist_ok=False)
        private = self.fixture / 'authored-state'
        roots = dict(settings_root=private, data_root=private/'data-v1', cache_root=private/'cache-v1',
            work_root=private/'cache-v1/work', tool_root=private/'tools-v1', state_root=private/'host-v1',
            default_export_root=private/'exports')
        roots['state_root'].mkdir(parents=True)
        (roots['state_root']/'synthetic-probe.json').write_text(json.dumps({'build_id': self.layout.build_id, 'synthetic': True}))
        self.writer_layout = replace(self.layout, **roots)
        self.host = FrozenProbeHost(self.writer_layout)
        paths = (self.fixture/'legacy/data/companion-operation.lock',
                 self.fixture/'private-target/host-v1/migration-runtime.lock')
        for path in paths:
            path.parent.mkdir(parents=True)
            self.leases.append(ExclusiveFileLease(path))
        self.emit('roots-ready')

    def start_guardian(self):
        environment = self.writer_layout.child_environment('frontend')
        self.guardian = subprocess.Popen(self.writer_layout.child_command('frontend', ['--port', '0']),
            cwd=self.fixture, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS)
        line = queue.Queue(maxsize=1)
        def read():
            try: line.put(self.guardian.stdout.readline(65537))
            except BaseException: line.put(None)
        threading.Thread(target=read, daemon=True, name='readonly-guardian-startup').start()
        try:
            ready = json.loads(line.get(timeout=20))
            manifest = json.loads(self.layout.resource('desktop/desktop-manifest.json').read_bytes())
            port = ready.get('port')
            if (ready.get('ready') is not True or type(port) is not int or not 1024 < port < 65536
                    or port in (3000, 8766) or ready.get('build_id') != manifest['build_id']):
                raise ValueError('invalid fixed guardian metadata')
            self.guardian_port, self.guardian_index = port, manifest['files']['index.html']
        except (ValueError, TypeError, KeyError, queue.Empty) as error:
            raise HostProbeFailure('keeper-guardian-startup') from error
        self.check_guardian()

    def check_guardian(self):
        guardian, port = self.guardian, self.guardian_port
        if guardian.poll() is not None or listener_processes((port,)) != {port: {guardian.pid}}:
            raise HostProbeFailure('keeper-guardian-identity')
        candidates = guardian_children(guardian.pid)
        if candidates:
            self.observe_descendants(candidates)
            raise HostProbeFailure('keeper-guardian-descendants')
        with urlopen('http://127.0.0.1:'+str(port)+'/', timeout=1) as response:
            body = response.read(self.guardian_index['bytes']+1)
            if (response.status != 200 or len(body) != self.guardian_index['bytes']
                    or hashlib.sha256(body).hexdigest() != self.guardian_index['sha256']):
                raise HostProbeFailure('keeper-guardian-identity')
        if guardian.poll() is not None or listener_processes((port,)) != {port: {guardian.pid}}:
            raise HostProbeFailure('keeper-guardian-identity')
        candidates = guardian_children(guardian.pid)
        if candidates:
            self.observe_descendants(candidates)
            raise HostProbeFailure('keeper-guardian-identity')

    def observe_descendants(self, candidates):
        if self.descendant_observation['state'] != 'not-observed':
            return  # Failure-only one-shot; never retry unconfirmed root/query handles.
        try:
            known = tuple(child.process_handle for child in self.host.registered.values())
            self.descendant_observation = observe_guardian_candidates(self.guardian, self.layout.executable,
                candidates, self._guardian_observer_holds, known)
        except BaseException:
            self.descendant_observation = _empty_guardian_observation()
            self.descendant_observation.update(state='unavailable', reason='query-unavailable',
                candidate_count=min(len(candidates), 65536), truncated=bool(candidates))

    def wait_guardian_loss(self):
        deadline, next_census = time.monotonic()+60, 0
        while self.guardian.poll() is None:
            if time.monotonic() >= deadline:
                raise HostProbeFailure('keeper-control-unavailable')
            self.host._alive()
            if time.monotonic() >= next_census:
                self.host.check_registered_members()
                self.check_guardian()
                next_census = time.monotonic()+.25
            try:
                command = self.commands.get(timeout=.05)
            except queue.Empty:
                continue
            if command != 'lose-guardian':
                raise HostProbeFailure('keeper-control-invalid')
            self.guardian.kill()  # Only our retained Popen creation object.
        self.guardian.wait(timeout=3)
        self.guardian_signaled = True
        candidates = guardian_children(self.guardian.pid)
        if candidates:
            self.observe_descendants(candidates)
            raise HostProbeFailure('keeper-guardian-descendants')

    def run(self):
        try:
            self.prepare()
            self.command('start')
            for lease in self.leases:
                lease.acquire()
            self.start_guardian()
            self.host.start_registered(detached_console=True)
            if self.case == 'keeper-after-ready':
                self.host.resume_registered()
                self.host.wait_services()
                self.check_guardian()
                self.emit('services-ready')
            else:
                self.emit('writers-suspended')
            self.wait_guardian_loss()
            # Loss itself drives drainage; there is no separate drain command.
            if self.case == 'keeper-after-ready':
                self.host.quiesce_registered()
            self.host.close()
            self.guardian.stdout.close()
            self.emit('writers-signaled-leases-held')
            self.command('release')  # Probe observation latch, not writer authority.
            for lease in reversed(self.leases):
                try: lease.close()
                except BaseException as error:
                    raise HostProbeFailure('keeper-lease-release-unconfirmed') from error
            self.released = True
            self.emit('released', status='passed')
            return 0
        except BaseException as error:
            category = error.code if isinstance(error, HostProbeFailure) else 'unexpected-keeper-failure'
            if not isinstance(error, HostProbeFailure) and self.host is not None and self.host.recovery_required:
                category = 'registered-host-unconfirmed'
            # No finally/context manager releases leases or exits with live or
            # unknown writer objects. Even a broken event pipe cannot bypass
            # the live owner/Job/creation-handle recovery hold.
            try:
                self.emit('recovery-required', status='failed', failure=category)
            except BaseException:
                pass
            hold_keeper_recovery()
            raise AssertionError('Recovery holder must not return.')


def main(kind, layout):
    if kind != 'host':
        raise HostProbeFailure('unknown-host-probe')
    # Fixed authored test controls only. Nothing is accepted by a production
    # child or API; the full runtime profile and source launcher stay unchanged.
    case = sys.stdin.readline().strip()
    if case == 'authored-populated-state-copy-v1':
        from .runtime_data_copy_probe import run_populated
        return run_populated(layout, sys.stdin)
    if case in {'authored-data-copy', 'authored-data-copy-resume', 'authored-data-copy-wal', 'authored-data-copy-grammar'}:
        from .runtime_data_copy_probe import run as data_copy_probe
        return data_copy_probe(layout, sys.stdin, case=case)
    if case in {'keeper-before-resume', 'keeper-after-ready'}:
        return _FrozenKeeperProbe(layout, case, sys.stdin).run()
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
