# R19 runtime writer quiesce boundary

The explicit local `/api/runtime/quiesce?writers=true` and
`/api/runtime/activate?writers=true` protocol accounts for application writers
before returning capture handoff state. The default endpoints retain the source
updater's existing capture-only handoff, including its recovery behavior; they
do not close HTTP admission or impose the new Hito writer gate. Neither protocol
returns a store-copy proof. The strict protocol advances C2 of the
[completion plan](r19-completion-plan.md). The supervising host/update transaction
and native Windows acceptance remain open. Frozen automatic updates and production runtime activation retain
their existing disabled gates. No installer is built.

## Admission, drain and recovery

The strict protocol closes ordinary HTTP admission and keeps admitted requests counted
through their final response body, including streaming responses. GET requests
are included because reading/lookup/setup endpoints can write caches or consume
folder-picker results. Health, readiness and the authenticated local handoff
controls remain available. Existing local-access and account isolation checks
still apply; an idle read-only WebSocket is not a writer barrier.

The initial WebSocket status snapshot is a known store-accessing producer. Its
endpoint captures one Runtime, hub, bound status function and writer gate before
the first await. It also captures an opaque process-local admission ticket while
that gate is accepting. The actual status worker enters the gate with that
ticket inside its thread and leaves only after the full status operation ends.
Cancelling/disconnecting the async waiter cannot decrement that active scope
early. Cleanup disconnects the same captured hub, including cancellation and
partially completed connection setup.

Stopping admission retires all earlier tickets. A queued pre-stop snapshot
refuses status/SQL even if its thread starts after a later resume. Tickets bind
the exact gate and opaque epoch, are not serialized or stored in a successful
ticket registry, and do not increase the active count merely by being captured.
They are epoch bindings, not one-use operation IDs. Ordinary unticketed HTTP/
source admission retains its existing behavior. A valid local WebSocket refused
by this gate completes acceptance before closing with retryable code 1013;
untrusted Host/Origin still receives middleware code 1008 before acceptance or
status access.

The two explicit HTTP `asyncio.to_thread` producers, regional capture preview
and manual ingest matching, also capture one Runtime, gate, opaque ticket and
bound worker callable before their first worker await. Their actual thread
enters with that ticket and leaves in `finally` only after its complete operation
returns or raises. The HTTP middleware keeps its separate request scope through
ASGI completion. Cancelling that request cannot retire an already-running worker
scope; drain still waits for the worker. A worker whose admission is refused
does not leave a scope it never entered. Refused/retired tickets produce a fixed
HTTP 503 with `Retry-After: 1`; a pre-stop queued worker cannot start its resource
operation in a later resumed epoch.

Regional preview can use the capture object's shared background-capture provider
from the loop's default executor. That thread is distinct from the capture/OCR
executor pools. Counting its actual work prevents a cancelled HTTP waiter from
making request drain appear complete while preview can still access that
provider. The no-region path still reads the cached preview bytes without a new
worker or ticket. This is an admission/operation boundary, not proof of WGC/MSS
native handle cleanup or a warm capture session.

Manual ingest's worker performs only its bound index match. After a successful
await, transcript insertion and `on_line` remain in the coroutine's existing HTTP
scope and use the captured Runtime. Its capture session ID is still read after
matching. Cancelling the match await prevents those following statements from
running; the fix does not move SQL/publication into a worker or claim that a
cancelled ingest was previously proven to write a transcript afterward. A loaded
TextMapIndex match can update its in-memory cache, so the surviving thread still
has resource ownership even without a subsequent SQL write.

These changes apply to those two explicit asyncio workers. Synchronous reading
routes retain their existing FastAPI/Starlette `run_in_threadpool` dispatch
through AnyIO, whose default is `abandon_on_cancel=False`; they are not silently
rewritten or given an all-thread cancellation guarantee. Other default-executor
lifecycle work remains under its own existing producer/cleanup contracts.

The shared lifecycle lock serializes quiesce and activation. A strict
quiesce attempt has one existing 30-second budget, beginning before lifecycle
lock acquisition. Request admission-stop/drain metadata is bounded off-loop by
that same deadline. A timed-out or disconnected
waiter retains the real cleanup task. Activation refuses while that task or a
retired preparation/worker generation still runs. Recovery reopens ordinary
HTTP admission only after worker recovery and update/capture activation. A failed
native capture stop retains its control and session state; strict recovery
retries that actual stop before resuming executors or capture. An unresolved
native stop keeps strict recovery unavailable.

The lifecycle covers these existing producers:

| Producer | Drain or explicit refusal |
| --- | --- |
| Admitted HTTP work | Wait through ASGI completion; new ordinary requests receive 503 while closed |
| Initial WebSocket status | Count the actual status thread; retire its queued ticket on admission stop, including across resume |
| Regional preview and manual ingest matching | Count actual default-executor work after HTTP cancellation; reject retired worker tickets before resource access, including across resume |
| Manual mobile exports and pickers | Close admission; refuse live monitor/process, picker or asynchronous cancellation work |
| Automatic export destination picker | Refuse an active picker before stopping the existing automatic-export service |
| Native setup/tool preparation | Close admission; join the actual tool thread and native-completion callbacks, including refresh work after process exit |
| Language preparation | Reuse its generation/publication locks, bounded close and cleanup-failure handling; recovery requires the retired workers to finish |
| Background update/index jobs | Await the existing close/index/map operations and check their tracked thread/process liveness |
| Reading lookups | Close the executor and join actual worker exit, including cache-writing Future callbacks |
| Capture/OCR | Stop capture and retain/drain current and timed-out retired OCR executors |
| Voice decoding and transcript audio publication | Drain every legacy/current/locale voice executor, then await queued capture publication coroutines that can enrich stored speakers |
| Hito grammar/cache worker | Refuse handoff while its tracked preparation thread or subprocess remains live; a supervising shutdown/restart adapter remains required |
| Known SQL owners | After all final producer bookkeeping, freeze TranscriptStore, one ledger root/pin owner and the exact retained default/cached Reading owner set; retain canonical tokens/partial progress |

The concrete [SQL composition](r19-mutable-store-lifetime.md#concrete-runtime-sql-composition)
reserves actual objects before its first SQL freeze, keeps reader creation
closed and uses private absolute-deadline freeze/check/resume operations.
Registry locks hold no SQL/HTTP/pool work. A clean pending retry continues its
same owner set/epoch; failed close remains poisoned and is never retried.
No missing-owner fallback or pathname-based deduplication can manufacture success.
Ledger identity checks use the real service class captured before a scoped
constructor hook. The existing authored grammar probe can wrap construction
while returning that actual service; a callable factory is not a Python type.
Foreign objects remain refused even when they expose another owner's SQL helper.
Each actual owner binds its retained member as the private controller before
any freeze. Matching epoch/pending metadata cannot transfer another public
controller's timed-out stop. Competing public freeze/resume calls refuse until
final Runtime admission; an entry epoch retires already-queued public calls.

Strict recovery first closes/drains request/creation admission, then completes
pending freezes and prevalidates every canonical token. SQL resumes before
producer pools/capture/updates and final HTTP/reader admission. Successful member
resumes remain recorded through partial or final activation failure, so retry
does not submit invalidated tokens again. Post-resume checks use the actual old
issued token and its expected next epoch; unknown/lost results cannot be adopted
from current metadata. Native-stop, SQL and pool recovery steps share the one
30-second recovery deadline and retain actual work after waiter cancellation.
The final request/reader opening holds every owner serialization lock through
its post-resume checks, metadata opening and deterministic controller retirement.
All fallible checks/acquires precede opening, using that same deadline; no owner
lock is recursively acquired and no SQL runs under registry metadata locks.

An export's `cancelled` status, an exited setup process, a done Future, standby,
health and OCR readiness cannot substitute for those waits. Failed cleanup
keeps admission closed until explicit strict activation/recovery succeeds. A
strict handoff cannot be recovered with a default capture-only activation: both
calls must opt into `writers=true`. The default source updater does not opt in
and remains usable with a live Hito worker. Under the strict protocol an active
Hito grammar worker prevents successful handoff until its supervising adapter
exists. The code does not start a native process termination operation merely to manufacture a
successful handoff.

## Limits and remaining gates

A return from quiesce is capture handoff state, not independent authorization to
copy settings, databases or credentials. The synthetic migration coordinator
still requires its own synthetic proof and does not accept this response as a
production barrier. No live migration or account write is exercised here.
Concrete SQL composition does not promote the response to a RuntimeDataFence:
settings/file/account/language/export-volume owners remain incomplete. The
tests establish no Windows .db/WAL/SHM replacement or physical detach/reopen;
that native known-scope check remains part of the next populated-copy/adaptor
unit, alongside the other mutable-resource owners.
The WebSocket fix covers this one initial status producer, not every future
message/queued callback, active socket or mutable resource. The two explicit HTTP
worker scopes likewise do not enumerate every thread or lifecycle task. A ticket does not
prove physical connection/cursor/file closure, a complete RuntimeDataFence,
whole-process signaling, a safe copied-store cutover or preserved OCR warmth.

Existing export/update cancellation and several game/legacy native processes
still lack complete supervising host ownership. Checking their tracked process
and thread is necessary but does not establish descendant exit, prevent PID
reuse, cover detached legacy updaters, or retain a lease across crash/restart.
The Hito refusal deliberately leaves its integration unavailable. The source
updater's nested-lock/detached transaction is not approved for frozen updates.

Completion-plan C1–C4 and E still require an extracted compiler-free entry host,
Windows owned-handle/Job Object integration, continuous legacy exclusion,
verified immutable-slot takeover and route publication, native failure/crash
recovery, protected TEST credentials, copied-store continuity and real browser
profile/reconnect evidence. Windows 10/11 native checks remain explicit and
unavailable on a macOS development host. Component rights, durable source
supply, notices and maintenance approval remain separate prerequisites.

## Focused regressions

`backend/tests/test_runtime_writers.py` exercises real blocked threads, a Future
whose callback still writes after `done()`, response streaming, retired OCR
workers, post-process native refresh, cancelled export labels, queued capture
publications, activation serialization and disconnected handoff waiters.
It also checks wrong-gate/type and retired admission tickets without changing
ordinary unticketed admission. `test_hito_api.py` uses real SQLite and controlled
thread Events for snapshot cancellation/error balance, queued execution after
stop-plus-resume, and binding/cleanup of the original Runtime and hub.
`test_local_access.py` exercises the actual ASGI acceptance/1013 ordering and
preserved pre-dispatch Host/Origin refusal. Account side effects are mocked;
these source tests introduce no new native runtime receipt.
`test_threaded_http_producers.py` uses the actual ASGI app without lifespan,
temporary SQLite/transcript and TextMapIndex fixtures, and authored frame/window
providers. It verifies cancellation while actual work continues, ordinary and
worker-cancellation error balance, a queued stale ticket across stop/resume,
fresh success, refused-entry/no-leave, captured Runtime/gate/callable identity,
post-match session selection and cached-preview/404 behavior. The cancelled
match case retains its zero-row/zero-publication negative. A queued HTTP waiter
which remains live is still counted by middleware; the test's manual stop/resume
transition is an epoch negative, not evidence of successful Runtime quiesce.
Credential/native/network access is forbidden by the fixtures. These source
regressions establish no physical Windows cleanup or global resource fence.
`test_runtime_sql_lifetime.py` composes actual temporary SQL stores/root/pins/
readers with explicit producer/native-cleanup adapters. It covers final
bookkeeping before freeze, retained tasks and partial token progress, all
metadata-lock deadlines, request-stop event-loop responsiveness, pending retry,
lost results, canonical/post-epoch refusal, retired constructors, second cohorts
and activation failures without stale-token reuse. Existing producer-only
fixtures explicitly name their SQL adapters; they do not prove that cohort.
Real SQLite/Event regressions refuse a foreign pending controller, retire a
public call delayed across the whole handoff, and exclude a competing public
freeze between the last SQL check and final admission. A final owner-lock
timeout keeps all controllers and closed admission for a later explicit retry.
`test_runtime_handoff.py` exercises the existing endpoint ordering and explicit
Hito refusal, default source compatibility and rejection of a default-protocol
bypass. `test_preparation_cancellation.py` retains capture/session identity
through failed drain, delayed recovery and restarted preparation.

The related local-access, reading, capture, setup and manual/automatic export
suites remain necessary. These authored fixtures are behavioral regressions;
they are not Windows process-tree or protected-store acceptance evidence.
