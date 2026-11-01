"""R19 host orchestration probes, restricted to marked synthetic temp roots.

The production source host remains Vinext/Wrangler. This module cannot activate
a real installation: process ownership and a global writer barrier are supplied
by fixture adapters, not established by readiness or copied process records.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from typing import Iterator, Protocol
import uuid


FRONTEND_ORIGIN = 'http://127.0.0.1:3000'
API_BASE = 'http://127.0.0.1:8766'
WEBSOCKET_URL = 'ws://127.0.0.1:8766/api/ws'
_MARKER = '.r19-synthetic-fixture.json'
_SCHEMA = 'proxy-r19-synthetic-fixture-v1'


class HostProbeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reject_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0)
                                 & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise HostProbeError('unsafe-path', 'Synthetic probe paths cannot follow links or reparse points.')


def _atomic_json(path: Path, value: dict) -> None:
    """Publish one checkpoint; separate pointer/journal files are not one txn."""
    _reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        with pending.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        from .atomic_files import replace
        replace(pending, path)
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        pending.unlink(missing_ok=True)


@dataclass(frozen=True)
class SyntheticRoot:
    path: Path
    fixture_id: str
    installation_id: str

    def verify(self) -> None:
        _reject_links(self.path)
        temporary = Path(tempfile.gettempdir()).resolve()
        if self.path.is_symlink() or not self.path.is_relative_to(temporary) or self.path == temporary:
            raise HostProbeError('synthetic-root-required', 'Only a marked temporary synthetic root is accepted.')
        marker = self.path / _MARKER
        if marker.is_symlink():
            raise HostProbeError('synthetic-root-required', 'Fixture markers cannot be symbolic links.')
        try:
            record = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise HostProbeError('synthetic-root-required', 'The synthetic fixture marker is unavailable.') from error
        expected = {'schema': _SCHEMA, 'fixture_id': self.fixture_id, 'installation_id': self.installation_id}
        if record != expected:
            raise HostProbeError('synthetic-root-required', 'The synthetic fixture marker changed.')


def create_synthetic_root(path: Path, *, installation_id: str | None = None) -> SyntheticRoot:
    """Create a new empty fixture; never label a pre-existing data directory."""
    path = Path(path).absolute()
    raw_temporary = Path(tempfile.gettempdir()).absolute()
    temporary = raw_temporary.resolve()
    # The OS temp root may itself have a system alias (e.g. /var on macOS).
    # Normalize only that trusted prefix, never a caller-created child link.
    if path.is_relative_to(raw_temporary):
        path = temporary / path.relative_to(raw_temporary)
    if '..' in path.parts:
        raise HostProbeError('synthetic-root-required', 'Fixture paths cannot contain parent traversal.')
    _reject_links(path)
    resolved = path.resolve()
    if path.exists() or path.is_symlink() or not resolved.is_relative_to(temporary) or resolved == temporary:
        raise HostProbeError('synthetic-root-required', 'Create a new fixture below the temporary directory.')
    identity = str(uuid.UUID(installation_id)) if installation_id is not None else str(uuid.uuid4())
    root = SyntheticRoot(resolved, str(uuid.uuid4()), identity)
    root.path.mkdir(parents=True, exist_ok=False)
    _atomic_json(root.path / _MARKER, {'schema': _SCHEMA, 'fixture_id': root.fixture_id, 'installation_id': identity})
    return root


class ExclusiveFileLease:
    """Keep the lock handle open; never unlink it or lend ownership via JSON.

    Windows uses the legacy launcher's CreateFile exclusive-share semantics.
    POSIX flock is only the synthetic macOS test analogue, not Windows proof.
    """
    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def retained_descriptors(self):
        """Guardians retain this OS lease through parent death, not a PID copy.

        Values are Windows HANDLEs or POSIX descriptors, consumed on the same
        platform by OwnedProcess before it starts any application child.
        """
        return ((self._handle if os.name == 'nt' else self._handle.fileno()),) if self.held else ()

    def acquire(self) -> None:
        if self.held:
            raise HostProbeError('nested-operation', 'The operation lease is not reentrant.')
        _reject_links(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                          ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            handle = kernel.CreateFileW(str(self.path), 0x80000000 | 0x40000000, 0, None, 4, 0x80, None)
            if handle == wintypes.HANDLE(-1).value:
                raise HostProbeError('operation-busy', 'Another launcher or update owns this operation lock.')
            self._handle = handle
        else:
            import fcntl
            stream = self.path.open('a+b')
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                stream.close()
                raise HostProbeError('operation-busy', 'Another synthetic operation owns this lock.') from error
            self._handle = stream

    def close(self) -> None:
        if not self.held:
            return
        handle = self._handle
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            if not kernel.CloseHandle(handle):
                raise HostProbeError('lock-close-failed', 'The operation lock handle could not be closed.')
        else:
            handle.close()
        self._handle = None


@dataclass(frozen=True)
class WriterStopProof:
    capture_stopped: bool
    preparation_stopped: bool
    exports_stopped: bool
    request_writers_stopped: bool
    worker_processes_reaped: bool

    @property
    def complete(self) -> bool:
        return all(value is True for value in vars(self).values())


@dataclass(frozen=True)
class SyntheticReadiness:
    backend: bool
    frontend: bool
    resources: bool
    selected_index: bool

    @property
    def complete(self) -> bool:
        return all(value is True for value in vars(self).values())


@dataclass(frozen=True)
class SyntheticHandoff:
    running: bool
    session_id: str = 'synthetic-session'


class SyntheticRuntime(Protocol):
    """Injected fixture ownership, never a claim of verified native handles."""
    installation_id: str
    runtime_id: str

    def prepare(self) -> None: ...
    def ready(self) -> SyntheticReadiness: ...
    def capture_running(self) -> bool: ...
    def write_generation(self) -> int: ...
    def quiesce(self) -> tuple[WriterStopProof, SyntheticHandoff]: ...
    def activate(self, handoff: SyntheticHandoff) -> None: ...
    def stop(self) -> WriterStopProof: ...


class SyntheticWriterBarrier:
    def __init__(self, coordinator: SyntheticHostCoordinator, generations: tuple):
        self._coordinator = coordinator
        self._generations = generations
        self._invalid = False

    def invalidate(self) -> None:
        self._invalid = True

    def check(self, source: SyntheticRoot) -> None:
        owner = self._coordinator
        source.verify()
        if (self._invalid or owner._barrier is not self or source != owner.legacy or not owner._leases_held()
                or any(runtime.capture_running() or runtime.write_generation() != generation
                       for runtime, generation in self._generations)):
            raise HostProbeError('writer-barrier-required', 'A current stopped-writer fixture barrier is required.')

    def check_target(self, target: SyntheticRoot) -> None:
        target.verify()
        if target != self._coordinator.state:
            raise HostProbeError('target-lease-required', 'The copy target must own this coordinator target lease.')


class SyntheticHostCoordinator:
    """Exercise ordering and durable recovery while holding both real leases.

    No HTTP endpoint or production launcher consumes this coordinator. The opaque
    owner is an in-process object, never a browser bypass flag. Existing source
    update-companion.ps1 cannot run inside this guard: its nested lease acquisition
    is deliberately rejected rather than temporarily releasing legacy exclusion.
    """
    production_activation_allowed = False
    guarded_source_updates_available = False

    def __init__(self, legacy: SyntheticRoot, state: SyntheticRoot, source: SyntheticRuntime):
        legacy.verify()
        state.verify()
        if (legacy.installation_id != state.installation_id or legacy.path == state.path
                or legacy.path.is_relative_to(state.path) or state.path.is_relative_to(legacy.path)):
            raise HostProbeError('invalid-fixture-layout', 'Fixture roots must be separate and have one installation identity.')
        self.legacy, self.state, self.current = legacy, state, source
        self._legacy_lease = ExclusiveFileLease(legacy.path / 'data/companion-operation.lock')
        self._target_lease = ExclusiveFileLease(state.path / 'host-v1/migration-runtime.lock')
        self._serialization = threading.Lock()
        self._operation_thread = None
        self._owner = object()
        self._opened = False
        self._barrier = None
        self._previous = None
        self._activation_generation = None
        self._owned = [source]
        self._recovery_required = False
        self._sequence = 0
        self.journal_path = state.path / 'host-v1/recovery.json'
        self.pointer_path = state.path / 'host-v1/route.json'
        self._verify_runtime(source)

    @property
    def owner(self):
        return self._owner

    def _verify_runtime(self, runtime: SyntheticRuntime) -> None:
        if runtime.installation_id != self.legacy.installation_id or not runtime.runtime_id:
            raise HostProbeError('ownership-mismatch', 'The fixture runtime belongs to a different installation.')

    def _leases_held(self) -> bool:
        return self._opened and self._legacy_lease.held and self._target_lease.held

    def _require_owner(self, owner, *, closing=False) -> None:
        if owner is not self._owner or not self._leases_held():
            raise HostProbeError('ownership-required', 'The live in-process guard owner is required.')
        self.legacy.verify()
        self.state.verify()
        if self._recovery_required and not closing:
            raise HostProbeError('recovery-required', 'Resolve the retained fixture recovery checkpoint before another operation.')

    @contextmanager
    def _operation(self):
        if self._operation_thread == threading.get_ident():
            raise HostProbeError('nested-operation', 'An owner operation cannot acquire its coordinator recursively.')
        with self._serialization:
            self._operation_thread = threading.get_ident()
            try:
                yield
            finally:
                self._operation_thread = None

    def _record(self, stage: str, **details) -> None:
        if stage == 'recovery-required':
            self._recovery_required = True
        self._sequence += 1
        _atomic_json(self.journal_path, {
            'schema': 'proxy-r19-synthetic-host-v1', 'installation_id': self.legacy.installation_id,
            'sequence': self._sequence, 'stage': stage, 'active_runtime_id': self.current.runtime_id,
            'legacy_exclusion_held': self._leases_held(), 'production_activation_allowed': False,
            'launcher_checkpoint': 'unchanged-unverified-R20', **details,
        })

    def _publish_pointer(self, runtime: SyntheticRuntime) -> None:
        _atomic_json(self.pointer_path, {'schema': 'proxy-r19-synthetic-route-v1',
                                       'runtime_id': runtime.runtime_id, 'frontend_origin': FRONTEND_ORIGIN,
                                       'api_base': API_BASE, 'websocket_url': WEBSOCKET_URL})

    def __enter__(self):
        if self.journal_path.exists():
            raise HostProbeError('recovery-required', 'Inspect existing checkpoints; copied runtime IDs are not live ownership.')
        self._legacy_lease.acquire()
        try:
            self._target_lease.acquire()
            self._opened = True
            self._record('source-active')
            self._publish_pointer(self.current)
        except BaseException:
            self._opened = False
            self._target_lease.close()
            self._legacy_lease.close()
            raise
        return self

    def __exit__(self, *_):
        self.close(self.owner)

    def require_guarded_source_update(self, owner) -> None:
        self._require_owner(owner)
        raise HostProbeError('guarded-source-update-unavailable',
                             'The source updater acquires this legacy lock again. Keep the source host; activation remains incomplete.')

    def _quiesce(self, runtime: SyntheticRuntime) -> SyntheticHandoff:
        try:
            proof, handoff = runtime.quiesce()
        except BaseException:
            self._record('recovery-required', reason='quiesce-raised')
            raise
        if not isinstance(proof, WriterStopProof) or not proof.complete or runtime.capture_running():
            self._record('recovery-required', reason='quiesce-incomplete')
            raise HostProbeError('quiesce-incomplete', 'All fixture writers and owned workers must stop before takeover or copy.')
        if not isinstance(handoff, SyntheticHandoff):
            self._record('recovery-required', reason='invalid-handoff')
            raise HostProbeError('invalid-handoff', 'The typed synthetic handoff is required.')
        return handoff

    def _stop(self, runtime: SyntheticRuntime) -> None:
        proof = runtime.stop()
        if not isinstance(proof, WriterStopProof) or not proof.complete or runtime.capture_running():
            raise HostProbeError('cleanup-unconfirmed', 'Keep exclusion held until all owned fixture writers have stopped.')

    @contextmanager
    def stopped_writers(self, owner) -> Iterator[SyntheticWriterBarrier]:
        """Hold serialization throughout copy; readiness cannot mint this token."""
        with self._operation():
            self._require_owner(owner)
            handoff = self._quiesce(self.current)
            self._record('writers-stopped')
            barrier = SyntheticWriterBarrier(self, tuple((runtime, runtime.write_generation()) for runtime in self._owned))
            self._barrier = barrier
            try:
                yield barrier
                barrier.check(self.legacy)
            except BaseException:
                self._barrier = None
                self._record('recovery-required', reason='copy-or-writer-barrier-failed')
                raise
            else:
                self._barrier = None
                self.current.activate(handoff)
                self._record('source-resumed-after-copy')

    def update(self, owner, candidate: SyntheticRuntime) -> None:
        """Synthetic owned update operation; never invokes the source updater."""
        with self._operation():
            self._require_owner(owner)
            self._verify_runtime(candidate)
            if candidate is self.current or candidate.runtime_id == self.current.runtime_id or candidate.capture_running():
                raise HostProbeError('invalid-candidate', 'A distinct fixture candidate must start in standby.')
            old = self.current
            handoff = None
            candidate_generation = candidate.write_generation()
            self._owned.append(candidate)
            try:
                candidate.prepare()
                ready = candidate.ready()
                if not isinstance(ready, SyntheticReadiness) or not ready.complete or candidate.capture_running():
                    raise HostProbeError('candidate-not-ready', 'Candidate resources, frontend and selected index must be ready in standby.')
                self._record('candidate-ready', candidate_runtime_id=candidate.runtime_id)
                handoff = self._quiesce(old)
                self._record('source-quiesced', candidate_runtime_id=candidate.runtime_id)
                candidate.activate(handoff)
                if old.capture_running():
                    raise HostProbeError('competing-capture', 'The source still owns capture.')
                self._record('candidate-activated', candidate_runtime_id=candidate.runtime_id)
                self._publish_pointer(candidate)
                self._previous = (old, handoff)
                self.current = candidate
                self._activation_generation = candidate_generation
                self._record('route-published')
            except BaseException:
                try:
                    self._stop(candidate)
                    if handoff is not None:
                        if candidate.write_generation() != candidate_generation:
                            raise HostProbeError('post-activation-writes', 'Preserve candidate data for reconciliation before restoring the old snapshot.')
                        self._publish_pointer(old)
                        old.activate(handoff)
                    self.current = old
                    self._record('recovery-required' if self._recovery_required else 'update-failed-source-retained')
                except BaseException:
                    self._record('recovery-required', candidate_runtime_id=candidate.runtime_id)
                    raise
                raise

    def rollback(self, owner) -> None:
        with self._operation():
            self._require_owner(owner)
            if self._previous is None:
                raise HostProbeError('rollback-unavailable', 'No retained verified fixture runtime is available.')
            if self.current.write_generation() != self._activation_generation:
                self._record('recovery-required', reason='post-activation-writes')
                raise HostProbeError('post-activation-writes', 'Preserve new writes and reconcile them before data rollback.')
            old, handoff = self._previous
            try:
                self._stop(self.current)
                self._record('rollback-candidate-stopped')
                self._publish_pointer(old)
                old.activate(handoff)
                self.current = old
                self._previous = None
                self._record('rolled-back')
            except BaseException:
                self._record('recovery-required')
                raise

    def close(self, owner) -> None:
        with self._operation():
            self._require_owner(owner, closing=True)
            try:
                for runtime in self._owned:
                    self._stop(runtime)
                self._record('all-writers-stopped')
            except BaseException:
                self._record('recovery-required', reason='cleanup-unconfirmed')
                raise
            self._target_lease.close()
            self._legacy_lease.close()
            self._opened = False


def inspect_synthetic_recovery(state: SyntheticRoot) -> dict:
    """Report checkpoints without adopting stored process IDs or starting work."""
    state.verify()
    journal_path, pointer_path = state.path / 'host-v1/recovery.json', state.path / 'host-v1/route.json'
    _reject_links(journal_path)
    _reject_links(pointer_path)
    journal = json.loads(journal_path.read_text(encoding='utf-8'))
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    if (journal.get('schema') != 'proxy-r19-synthetic-host-v1'
            or pointer.get('schema') != 'proxy-r19-synthetic-route-v1'
            or journal.get('installation_id') != state.installation_id):
        raise HostProbeError('invalid-checkpoint', 'The fixture recovery checkpoint is incompatible.')
    return {'journal': journal, 'pointer': pointer, 'process_ownership': 'must-reverify',
            'installed_launcher': 'unchanged-unverified-R20', 'production_activation_allowed': False}
