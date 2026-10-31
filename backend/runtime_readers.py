"""Runtime-owned reading creation/pools; not SQL detach or global ownership."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import math
import threading
import time
from types import MappingProxyType

from .reading import LexiriseReadingService
from .runtime_writers import QuiesceableExecutor, RuntimeWriterGate, WritersQuiescing
from .sqlite_operation_lifetime import SqliteOperationLifetime


_DEFAULT = object()


@dataclass(eq=False, repr=False)
class _Lookup:
    registry: RuntimeReadingRegistry
    epoch: object
    thread: threading.Thread


@dataclass(eq=False, repr=False)
class ReadingCreationRecord:
    reader: LexiriseReadingService
    creator: threading.Thread
    state: str = 'constructing'
    error: BaseException | None = None
    cleanup_error: BaseException | None = None


@dataclass(eq=False, repr=False)
class _ReadingControl:
    finished: bool = False


@dataclass(eq=False, repr=False)
class _ReadingSqlMember:
    reader: LexiriseReadingService
    owner: SqliteOperationLifetime
    epoch: int | None = None
    token: object = None
    resumed: bool = False
    error: BaseException | None = None
    retirement_epoch: object = field(default_factory=object)
    reserved: bool = False


@dataclass(eq=False, repr=False)
class _ReadingSqlSet:
    registry: RuntimeReadingRegistry
    epoch: object
    records: tuple
    members: tuple[_ReadingSqlMember, ...]
    default: LexiriseReadingService
    error: BaseException | None = None


class ReadingRegistryPoisonedError(RuntimeError):
    def __init__(self, registry, record):
        super().__init__('Reading service construction cleanup remains unconfirmed.')
        self.registry, self.record = registry, record
        self.error = record.error


class RuntimeReadingRegistry:
    """Keep actual default/partial/cached readers before constructor entry."""
    def __init__(self, directory):
        self.directory = directory
        self._lock = threading.Lock()
        self._accepting = True
        self._epoch = object()
        self._lookups = set()
        self._records = {}
        self._cache = {}
        self.cached = MappingProxyType(self._cache)
        self._failure = None
        self._control = None
        self._resumed_epoch = None
        self._shutdown = False
        self._sql_set = None

    def _require_clean(self):
        if self._failure is not None:
            failure = self._failure
            raise ReadingRegistryPoisonedError(self, failure) from failure.error

    def _require_lookup(self, lookup):
        self._require_clean()
        if (type(lookup) is not _Lookup or lookup not in self._lookups or lookup.registry is not self
                or lookup.thread is not threading.current_thread() or lookup.epoch is not self._epoch
                or not self._accepting or self._shutdown):
            raise WritersQuiescing('Reading service creation is quiescing.')

    @contextmanager
    def lookup(self):
        with self._lock:
            self._require_clean()
            if not self._accepting or self._shutdown:
                raise WritersQuiescing('Reading service creation is quiescing.')
            lookup = _Lookup(self, self._epoch, threading.current_thread())
            self._lookups.add(lookup)
        failed = False
        try:
            yield lookup
        except BaseException:
            failed = True
            raise
        finally:
            with self._lock:
                self._lookups.remove(lookup)
                if not failed:
                    self._require_clean()
                    if lookup.epoch is not self._epoch or not self._accepting or self._shutdown:
                        raise WritersQuiescing('Reading service creation is quiescing.')

    def create_default(self, lexirise):
        with self.lookup() as lookup:
            return self._get(lookup, _DEFAULT, lexirise, None, None)

    def get_or_create(self, lookup, key, session, *, source_language, translation_language):
        if (type(key) is not tuple or len(key) != 4 or any(type(item) is not str for item in key)
                or key[1] != source_language or key[2] != translation_language):
            raise ValueError('The reading service key differs from its resolved languages.')
        return self._get(lookup, key, session, source_language, translation_language)

    def _get(self, lookup, key, session, source, target):
        while True:
            with self._lock:
                self._require_lookup(lookup)
                record = self._records.get(key)
                if record is None:
                    reader = object.__new__(LexiriseReadingService)
                    record = ReadingCreationRecord(reader, threading.current_thread())
                    self._records[key] = record  # Actual object owned before any constructor work.
                    break
                if record.state == 'ready':
                    return record.reader
            time.sleep(.005)  # No registry lock over the other actual constructor.
        try:
            if key is _DEFAULT:
                LexiriseReadingService.__init__(reader, self.directory, session)
            else:
                LexiriseReadingService.__init__(reader, self.directory, session,
                    source_language=source, translation_language=target)
        except BaseException as error:
            with self._lock:
                record.error, record.state = error, 'failed'
                if self._failure is None: self._failure = record
                self._accepting = False
                self._epoch = object()
                self._resumed_epoch = None
                self._require_clean()  # Fresh wrapper, original constructor traceback retained.
        with self._lock:
            record.state = 'ready'
            if key is not _DEFAULT: self._cache[key] = reader
            self._require_lookup(lookup)  # A retired call cannot return a newly completed object.
            return reader

    @staticmethod
    def _deadline(value):
        if type(value) not in {int, float}:
            raise ValueError('Reading lifecycle requires a finite monotonic deadline.')
        try: result = float(value)
        except OverflowError:
            raise ValueError('Reading lifecycle requires a finite monotonic deadline.') from None
        if not math.isfinite(result):
            raise ValueError('Reading lifecycle requires a finite monotonic deadline.')
        return result

    def _acquire(self, deadline):
        remaining = min(threading.TIMEOUT_MAX, max(0.0, deadline-time.monotonic()))
        if not self._lock.acquire(timeout=remaining):
            raise TimeoutError('Reading lifecycle metadata is still owned.')

    def stop_creation(self, deadline):
        deadline = self._deadline(deadline)
        self._acquire(deadline)
        try:
            if self._sql_set is not None:
                if self._accepting or self._epoch is not self._sql_set.epoch or self._lookups:
                    raise TimeoutError('Retained reading SQL ownership changed.')
                return  # This exact stopped cohort still owns its original epoch.
            self._epoch = object()
            self._accepting = False
            self._resumed_epoch = None
        finally:
            self._lock.release()

    def owned_snapshot(self, deadline):
        """Private actual-object observation, not a data/copy capability."""
        deadline = self._deadline(deadline)
        self._acquire(deadline)
        try:
            return tuple(self._records.values())
        finally:
            self._lock.release()

    def _require_sql_locked(self, sql_set):
        self._require_clean()
        self._release_finished_control()
        records = tuple(self._records.values())
        if (type(sql_set) is not _ReadingSqlSet or self._sql_set is not sql_set
                or sql_set.registry is not self or self._epoch is not sql_set.epoch
                or self._accepting or self._lookups or self._control is not None or self._shutdown
                or _DEFAULT not in self._records or self._records[_DEFAULT].reader is not sql_set.default
                or len(records) != len(sql_set.records) or len(sql_set.members) != len(records)
                or any(actual is not expected for actual, expected in zip(records, sql_set.records))):
            raise TimeoutError('Retained reading SQL ownership changed.')
        for record, member in zip(sql_set.records, sql_set.members):
            if (type(member) is not _ReadingSqlMember or record.state != 'ready' or record.reader is not member.reader
                    or member.reader._sql_lifetime is not member.owner
                    or member.owner.subject is not member.reader):
                raise TimeoutError('Retained reading SQL member changed.')

    def reserve_sql_owned(self, deadline):
        deadline = self._deadline(deadline)
        self._acquire(deadline)
        try:
            self._require_clean()
            self._release_finished_control()
            if self._accepting or self._lookups or self._control is not None or self._shutdown:
                raise TimeoutError('Reading SQL requires stopped creation and completed pool control.')
            if self._sql_set is None:
                records = tuple(self._records.values())
                if _DEFAULT not in self._records:
                    raise TimeoutError('Default reading SQL ownership is not retained.')
                members = []
                for record in records:
                    if (record.state != 'ready' or not isinstance(record.reader, LexiriseReadingService)
                            or type(record.reader._sql_lifetime) is not SqliteOperationLifetime
                            or record.reader._sql_lifetime.subject is not record.reader):
                        raise TimeoutError('Reading SQL member ownership is unconfirmed.')
                    owner = record.reader._sql_lifetime
                    members.append(_ReadingSqlMember(record.reader, owner, epoch=owner.epoch))
                if len({member.owner for member in members}) != len(members):
                    raise TimeoutError('Reading SQL owners unexpectedly alias.')
                self._sql_set = _ReadingSqlSet(self, self._epoch, records, tuple(members), self._records[_DEFAULT].reader)
            self._require_sql_locked(self._sql_set)
            if time.monotonic() > deadline:
                raise TimeoutError('Reading SQL reservation deadline expired.')
            return self._sql_set
        finally:
            self._lock.release()

    def check_sql_set(self, sql_set, deadline):
        deadline = self._deadline(deadline)
        self._acquire(deadline)
        try:
            self._require_sql_locked(sql_set)
            if time.monotonic() > deadline:
                raise TimeoutError('Reading SQL metadata deadline expired.')
        finally:
            self._lock.release()

    @staticmethod
    def _sql_error(sql_set, member, error):
        if member.error is None: member.error = error
        if sql_set.error is None: sql_set.error = error

    def reserve_sql_epochs(self, sql_set, deadline):
        self.check_sql_set(sql_set, deadline)
        for member in sql_set.members:
            if not member.reserved:
                try:
                    if member.owner._reserve_until(member, deadline) is not member:
                        raise ValueError('Reading SQL controller result differs.')
                    member.reserved = True
                except BaseException as error:
                    self._sql_error(sql_set, member, error)
                    raise
            else:
                member.owner._check_control_until(member, member.epoch, deadline)
        self.check_sql_set(sql_set, deadline)

    def freeze_sql_owned(self, sql_set, deadline):
        self.check_sql_set(sql_set, deadline)
        for member in sql_set.members:
            try:
                if not member.reserved or member.epoch is None:
                    raise TimeoutError('Reading SQL freeze progress differs.')
                if member.resumed:
                    member.owner._check_resumed_until(member.token, deadline, member)
                elif member.token is None:
                    member.token = member.owner._freeze_until(deadline, member.epoch, member)
                else:
                    member.owner._check_until(member.token, deadline, member)
            except BaseException as error:
                self._sql_error(sql_set, member, error)
                raise
        self.check_sql_owned(sql_set, deadline)

    def check_sql_owned(self, sql_set, deadline, *, resumed=False):
        self.check_sql_set(sql_set, deadline)
        for member in sql_set.members:
            if (not member.reserved or member.token is None or type(member.token) is not member.owner._fence_type
                    or member.token._epoch != member.epoch
                    or resumed and not member.resumed):
                raise TimeoutError('Reading SQL transition remains incomplete.')
            if member.resumed:
                member.owner._check_resumed_until(member.token, deadline, member)
            else:
                member.owner._check_until(member.token, deadline, member)
        self.check_sql_set(sql_set, deadline)

    def resume_sql_owned(self, sql_set, deadline):
        self.check_sql_owned(sql_set, deadline)
        for member in sql_set.members:
            if not member.resumed:
                try:
                    member.owner._resume_until(member.token, deadline, member)
                    member.resumed = True  # Never submit that invalidated token again.
                except BaseException as error:
                    self._sql_error(sql_set, member, error)
                    raise
        self.check_sql_owned(sql_set, deadline, resumed=True)

    def _begin_drain(self, deadline):
        self.stop_creation(deadline)
        while True:
            self._acquire(deadline)
            try:
                self._release_finished_control()
                if self._control is not None:
                    raise TimeoutError('Another reading lifecycle operation is still owned.')
                if not self._lookups:
                    control = _ReadingControl()
                    self._control = control
                    return control, tuple(self._records.values())
            finally:
                self._lock.release()
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Reading service creation has not finished.')
            time.sleep(min(.01, remaining))

    def _release_finished_control(self):
        # Called only under the metadata lock. Completion means the actual
        # control body/finalizer returned; each pool still validates its own
        # potentially continuing drain before resume can succeed.
        if type(self._control) is _ReadingControl and self._control.finished:
            self._control = None

    def _finish_control(self, control, deadline):
        try:
            self._acquire(deadline)
            try:
                if self._control is not control:
                    raise TimeoutError('Reading lifecycle ownership changed.')
                self._control = None
            finally:
                self._lock.release()
        finally:
            # A lost final timed acquire must not orphan an otherwise terminal
            # operation forever. No pool/SQL work follows this publication.
            control.finished = True

    def quiesce_owned(self, deadline):
        deadline = self._deadline(deadline)
        control, records = self._begin_drain(deadline)
        try:
            for record in records:
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise TimeoutError('Reading pool drain has not finished.')
                try:
                    if record.state == 'ready':
                        record.reader.quiesce(remaining)
                    else:
                        pool = vars(record.reader).get('pool')
                        if pool is not None:
                            if not isinstance(pool, QuiesceableExecutor):
                                raise RuntimeError('Partial reading pool ownership is unconfirmed.')
                            pool.quiesce(remaining)
                except BaseException as error:
                    if record.cleanup_error is None: record.cleanup_error = error
                    raise
            self._acquire(deadline)
            try:
                self._require_clean()
                if time.monotonic() > deadline: raise TimeoutError('Reading pool drain has not finished.')
            finally:
                self._lock.release()
        finally:
            self._finish_control(control, deadline)

    def resume_pools(self, deadline=None):
        # Recovery is called synchronously in the event loop: registry metadata
        # must be immediately available; never wait there behind a long holder.
        supplied = deadline is not None
        deadline = self._deadline(deadline) if supplied else time.monotonic()
        self._acquire(deadline)
        try:
            sql_set = self._sql_set
        finally:
            self._lock.release()
        if sql_set is not None:
            if not supplied: raise TimeoutError('Reading SQL recovery requires its active deadline.')
            self.check_sql_owned(sql_set, deadline, resumed=True)
        self._acquire(deadline)
        try:
            self._require_clean()
            self._release_finished_control()
            if self._shutdown:
                raise TimeoutError('Reading creation or lifecycle work is still owned.')
            if self._accepting:
                # stop_creation may itself have timed out before changing
                # admission. Recovery still closes/retires it before any pool
                # resume, and refuses every actual in-flight lookup below.
                self._epoch = object()
                self._accepting = False
                self._resumed_epoch = None
            if self._lookups or self._control is not None:
                raise TimeoutError('Reading creation or lifecycle work is still owned.')
            control, epoch = _ReadingControl(), self._epoch
            self._control = control
            self._resumed_epoch = None
            records = tuple(self._records.values())
        finally:
            self._lock.release()
        try:
            for record in records: record.reader.resume()
            self._acquire(deadline if supplied else time.monotonic())
            try:
                self._require_clean()
                if supplied and time.monotonic() > deadline:
                    raise TimeoutError('Reading recovery deadline expired.')
                if self._epoch is not epoch or self._lookups or self._shutdown:
                    raise TimeoutError('Reading recovery ownership changed.')
                self._resumed_epoch = epoch
            finally:
                self._lock.release()
        finally:
            self._finish_control(control, deadline if supplied else time.monotonic())

    def reopen_creation(self):
        self._acquire(time.monotonic())
        try:
            self._require_clean()
            if self._sql_set is not None:
                raise TimeoutError('Reading SQL admission requires its explicit Runtime transition.')
            if (self._shutdown or self._lookups or self._control is not None
                    or self._resumed_epoch is not self._epoch):
                raise TimeoutError('Reading recovery is incomplete.')
            self._accepting = True
        finally:
            self._lock.release()

    def _reopen_sql_creation(self, sql_set, gate, deadline):
        # Runtime already holds all actual owner controller locks and validated
        # their post-resume states. Only metadata is held together here.
        if type(gate) is not RuntimeWriterGate:
            raise ValueError('Runtime request gate ownership differs.')
        self._acquire(deadline)
        try:
            self._require_sql_locked(sql_set)
            if any(not member.resumed or member.owner._controller is not member for member in sql_set.members):
                raise TimeoutError('Reading SQL controllers are not ready to retire.')
            if self._resumed_epoch is not self._epoch:
                raise TimeoutError('Reading pool recovery is incomplete.')
            remaining = min(threading.TIMEOUT_MAX, max(0.0, deadline-time.monotonic()))
            if not gate._condition.acquire(timeout=remaining):
                raise TimeoutError('Runtime request admission metadata is still owned.')
            try:
                if time.monotonic() > deadline or gate._accepting or gate._active:
                    raise TimeoutError('Runtime request admission is not ready to reopen.')
                self._accepting = True
                self._sql_set = None
                gate._accepting = True
            finally:
                gate._condition.release()
        finally:
            self._lock.release()

    def shutdown(self, deadline):
        deadline = self._deadline(deadline)
        self._acquire(deadline)
        try:
            self._shutdown = True
        finally:
            self._lock.release()
        self.quiesce_owned(deadline)
