"""Bounded, host-issued native frame receipts; no image or credential storage."""
from collections import OrderedDict
from contextlib import contextmanager
import math
import re
import time
import weakref

ADMISSION_GAP_SECONDS = 3
# The native recognizer awaits ML Kit for at most 30 seconds. Allow bounded
# callback/bridge overhead without retaining arbitrary historical frame IDs.
MAX_RECEIPT_SECONDS = 35
MAX_RECEIPTS = 128
UUID = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')


class NativeFrameReceipt:
    __slots__ = ('_issuer', '_segment', '_sequence', '_received')

    def __init__(self, issuer, segment, sequence, received):
        self._issuer, self._segment = issuer, segment
        self._sequence, self._received = sequence, received

    def authorize(self, session, generation, sequence):
        """Only the issuer's currently executing result can authorize a scan."""
        return self._issuer._authorize(self, session, generation, sequence)


class NativeFrameAdmissions:
    """Called only under the host's session lock, after authenticated admission.

    A receipt is usable only inside one result context and cannot be serialized
    through the HTTP bridge. New source bindings or real admission gaps retire
    previous IDs. The ledger keeps no frames, URLs, account names or keys.
    """
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self._session = None
        self._generation = self._scope = None
        self._segment = object()
        self._pending = OrderedDict()
        self._last_admitted = None
        self._last_sequence = self._last_result = -1
        self._active = None

    def _same(self, session, generation, scope):
        return (self._session is not None and self._session() is session
            and generation == self._generation and scope == self._scope)

    def admit(self, session, generation, sequence, scope):
        # Scope comes from current host state, never a callback-supplied token.
        if (type(generation) is not int or not 0 < generation < 2**53 or type(sequence) is not int or not 0 < sequence < 2**53
                or not isinstance(scope, tuple) or len(scope) != 3
                or not isinstance(scope[0], str) or not re.fullmatch(r'[a-f0-9]{32}', scope[0])
                or type(scope[1]) is not int or not 0 <= scope[1] < 2**53
                or scope[2] is not None and (not isinstance(scope[2], tuple) or len(scope[2]) != 2
                    or not isinstance(scope[2][0], str) or not UUID.fullmatch(scope[2][0])
                    or type(scope[2][1]) is not int or scope[2][1] < 1)):
            raise ValueError('Invalid native frame admission scope')
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError('Invalid native frame admission clock')
        if not self._same(session, generation, scope):
            self.reset()
            self._session, self._generation, self._scope = weakref.ref(session), generation, scope
        if sequence <= self._last_sequence:
            raise ValueError('A native frame ID cannot be reused')
        if self._last_admitted is not None and not 0 <= now - self._last_admitted <= ADMISSION_GAP_SECONDS:
            self._segment = object()
            self._pending.clear()
        self._last_sequence, self._last_admitted = sequence, now
        while self._pending and (len(self._pending) >= MAX_RECEIPTS
                or now - next(iter(self._pending.values()))._received > MAX_RECEIPT_SECONDS):
            self._pending.popitem(last=False)
        self._pending[sequence] = NativeFrameReceipt(self, self._segment, sequence, now)

    @contextmanager
    def result(self, session, generation, sequence, scope):
        now = self.clock()
        receipt = self._pending.pop(sequence, None) if (self._same(session, generation, scope)
            and self._active is None and type(generation) is int and type(sequence) is int) else None
        if (not self._same(session, generation, scope) or self._active is not None or receipt is None
                or receipt._segment is not self._segment or sequence <= self._last_result
                or not 0 <= now - receipt._received <= MAX_RECEIPT_SECONDS
                or self._last_admitted is None or not 0 <= now - self._last_admitted <= ADMISSION_GAP_SECONDS):
            yield None
            return
        self._last_result, self._active = sequence, receipt
        for older in tuple(self._pending):
            if older <= sequence:
                del self._pending[older]
        try:
            yield receipt
        finally:
            self._active = None

    def _authorize(self, receipt, session, generation, sequence):
        if (self._active is not receipt or self._session is None or self._session() is not session
                or generation != self._generation or sequence != receipt._sequence
                or receipt._segment is not self._segment):
            raise ValueError('Native frame admission receipt is no longer valid')
        # Unleased compatibility submissions can be processed, but cannot
        # authorize confirmation across a long OCR completion gap.
        return self._segment if self._scope[2] is not None else None
