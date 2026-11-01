# R19 SQLite connection-operation fences

Status: implemented programmatic source boundary with local SQLite/thread
regressions; no new frozen/native runtime receipt or full mutable-root detach
acceptance. The [completion plan](r19-completion-plan.md) and
[R18 host contract](r18-storage-host-contract.md) retain their existing gates.
The SQL ownership changes build no installer and change no source updater,
schema, settings mapping, account, shared component or PR #59 behavior. The
separate frozen language-registry path correction below preserves source paths
and supplies no additional ownership/copy authority.

`TranscriptStore.freeze_connections(timeout)` closes admission to that store's
normal SQL connection-operation scopes, waits for their transaction exit and
actual `Connection.close()` return, then returns a typed
`TranscriptConnectionFence`. The existing request admission mechanism is reused
at this underlying store boundary; capture/publication/speaker callers do not
need to arrive through an HTTP request to be counted. Ordinary behavior is
unchanged outside the explicit strict writer protocol. The existing
`writers=true` Runtime handoff now composes these programmatic APIs as described
below; no dedicated per-store HTTP/CLI control or serialized SQL token is added.

The token binds the exact issuing store, issued token object and local admission
epoch. `fence.check(store)` refuses a different store, a manually constructed
token, stale epoch, reopened admission, active scopes or retained failed-close
ownership. `store.resume_connections(fence)` invalidates the old token before
opening admission and advances the epoch. Repeated successful freeze while the
same fence is current returns that checked object. There is no force-resume,
data-path setter, root replacement, database reopen, copy permission or owner
reconstruction from metadata.

TranscriptStore delegates this mechanism to `SqliteOperationLifetime`, the same
small admitted-operation/transaction/freeze implementation used by the Lexirise
ledger and reading SQL scopes. Its raw `_connect` factory, `TranscriptConnectionCloseError`,
`TranscriptStorePoisonedError`, original failure identities and
`TranscriptConnectionFence` remain unchanged. The existing private failed-list
observation point remains an alias of the owner's actual failures; successful
connections are not retained. Internal test instrumentation follows the owner
object rather than adding copied scalar state or proxy fields to the store.

## Lexirise ledger root and pinned sessions

`LexiriseService` creates one SQL-operation lifetime owner before constructor
SQL. Every normal `pin()` copy retains that exact owner, including the gate,
failure list, locks, epoch and canonical fence. Independent service instances
remain independent owners, even for an identical database pathname. This is
not a global path lock or account authorization boundary.

`service.freeze_connections(timeout)` waits for admitted SQL scopes in the root
and all those pins. Its `LexiriseConnectionFence.check(service_or_pin)` accepts
only that shared owner and the current issued token; any of those pins may
resume with that exact token. A pin created while frozen or poisoned does not
gain fresh SQL admission. Stale, manually constructed and wrong-owner tokens
refuse. The single timeout/polling and invalidation-before-resume rules below
apply to these SQL owners.

The ledger's connection scope still performs the existing dynamic
`sqlite3.connect(self.db_path, timeout=10)` call. A scope stays active through
its whole transaction body, explicit intermediate commits and actual close,
including mocked or ordinary HTTP work already inside that SQL scope. Freeze
never acquires the ledger's `_lock`; admitted bookkeeping must be able to finish
while it waits. Body and transaction-exit errors propagate unchanged when close
succeeds. On failed close, `LexiriseConnectionCloseError` retains the actual
connection, root service/owner and original body, transaction and close errors.
Fresh `LexiriseLedgerPoisonedError` wrappers refuse later root/pin SQL without
reopening or retrying close. These are private cleanup errors, not a retryable
remote `LexiriseError`; their objects/tracebacks/credentials are never serialized.

Ledger reads and public return values materialize SQL rows/dictionaries rather
than returning SQL cursors. Its explicit statement scopes close SELECT cursors
before HTTP work and close write cursors before the existing intermediate
commits. HTTP `_items` pagination is separate from SQL cursor
lifetime. The SQL fence does not cover an entire send with several SQL scopes,
work queued before `_lock`, HTTP-only settings/deck requests, key selection or
file/client lifetimes outside its SQL scopes. It supplies no queue-retirement
guarantee like the separate initial-WebSocket admission ticket. Outer producer
admission/drain is still necessary before a future aggregate data fence.

Constructor table/schema/commit behavior and account/language-scoped export
deduplication remain intact. Connection creation is not cached or moved into
the lifetime owner. The existing authored C5 interceptor still sets/reads
NO_CKPT_ON_CLOSE before the exact three stores perform constructor SQL; the
owner creates no extra SQLite connection, factory argument, URI, SQL query or
successful holder. Factory failures propagate from their existing boundary;
the new owner does not invent a physical-close proof for an object which that
factory never handed over.

## Reading SQL scopes and independent pool lifetime

Each `LexiriseReadingService` now creates its own SQL-operation owner before
constructor SQL. Its `freeze_connections(timeout)` and
`ReadingConnectionFence.check(reader)` apply only to that exact reader, issued
token object and local epoch. `resume_connections(fence)` invalidates the token
before reopening SQL admission. Independent readers remain independent owners,
even when they use the same `reading-cache-v2.db` path or Lexirise session.
There is no path lock, account authorization or Runtime reader inventory in it.

The five existing reading connection boundaries retain the exact dynamic
`sqlite3.connect(self.path)` factory call without added arguments, PRAGMAs or
opens. Constructor and writes keep their connection transaction context; the
cache and grammar SELECT scopes use the helper's nontransactional
`closing(connection)` context. It never invokes transaction enter/exit, commit
or rollback. Existing SQL, local grammar 0/4 overrides, scoped cache keys,
Chinese text and schema remain intact. The durable grammar choices in this
mixed cache/choice database are not treated as disposable cache data.

Existing normal sites retain the order reader RLock, SQL admission, connect,
read/transaction, actual close and failure publication, SQL leave, RLock release.
Constructor SQL retains its existing absence of that outer RLock. Freeze,
check and resume do not acquire the reader RLock or join its pool. Key/settings
selection and JSON processing stay at their existing boundaries.

On failed close, `ReadingConnectionCloseError` retains the actual reader,
owner, connection and original body/transaction/close errors. Later SQL and
fence operations raise fresh `ReadingConnectionsPoisonedError` wrappers before
another open, without retrying close or extending the original failure's
traceback. These private cleanup errors are not remote `LexiriseError` retries
and are never serialized. The shared helper's existing transactional error and
ownership behavior remains the same for TranscriptStore and the ledger.

Reading `quiesce()` and `resume()` remain separate pool-only controls. A worker's
Future can be done before its writing callback closes SQL. An already-complete
Future can also invoke a newly attached callback inline in its caller, outside
any pool worker. The SQL fence counts that callback's admitted SQL scope; pool
join alone does not certify it. A failed worker close remains owned after pool
join; the existing callback's marker-save attempt refuses before connecting and
its pending-word finally block still runs. Pool replacement cannot clear poison.

Most reading HTTP, settings/key work and intervals between SQL scopes are
outside SQL admission. A valid SQL token can coexist with unfinished HTTP;
its later SQL refuses while frozen. Queued outer work has no retirement ticket
and can seek fresh SQL admission after a valid resume. The concrete Runtime
composition below stops known producers/creation and drains pools/callbacks
before closing SQL admission. A future all-file aggregate boundary remains
separate; this adds no copy/activation token or new control route.

Runtime's default and dynamically cached readers use the separate
[reading creation and pool owner](#runtime-reading-creation-and-pool-ownership)
described below. Its retained records replace the earlier cache-only inventory
and coalesce concurrent same-key construction. Per-reader SQL admission remains
distinct from pool lifetime. The strict Runtime sequence now retains/composes
that exact SQL-owner set; settings/file resources are not covered.

## Owned statement cursors

Normal SQL sites in TranscriptStore, the Lexirise ledger and Reading now use the
existing lifetime helper's narrow `cursor(connection)` context. It obtains and
owns the actual cursor **before** execute, fetch or iteration can fail, and
closes it exactly once after its statement result is consumed. Known cursor
close finishes before transaction exit and connection close; operation admission
remains active through all cleanup and failed-object publication. There is no
connection proxy, replacement factory, successful cursor registry or enumeration
of arbitrary Python/SQLite objects.

SQL, schema, parameters, materialized results and connection arguments stay the
same. Transcript insertion copies the cursor's lastrowid scalar before closing
that cursor, then performs its existing SELECT. Multirow queries and grammar
comprehensions are consumed inside their cursor scope. Reading reads still use
no connection transaction enter/exit, commit or rollback. No cursor scope is
extended across an existing ledger HTTP request merely to hold its resources.
The raw `_connect` hook, exact C5 constructor interception and intermediate
ledger commits remain intact.

A failed cursor close creates a fixed-text private `_SqliteCursorCloseError`
retaining the actual owner, connection, cursor and original body/close errors.
The owner records it before operation leave. Its existing configured poison
wrapper refuses later SQL/freeze/resume without another connection or cursor;
even an attempt at another owned cursor on that still-open connection refuses.
Unknown cleanup remains poisoned even if an independent lock happens to be
available. Actual failed cursor/connection objects are not replaced or retried.

When body, cursor close, transaction exit and connection close fail together,
the original body, actual transaction error and actual connection-close error
retain their existing connection-failure fields and identities. The cursor
failure retains its actual cursor-close error and any actual transaction error.
Only the exact cursor-failure object issued and retained by this owner, with
this actual owner/connection binding, may be unwrapped to its original body for
that bookkeeping. Matching class, fields, message or equality is insufficient.
The actual escaped exception is kept distinct from its original body so a
rollback/commit error is not mistaken for that body. Falsey exceptions remain
errors; selection uses explicit None/identity checks.

If cursor creation raises before handing over an object, the helper does not
invent ownership of an unseen cursor. The connection still follows its existing
transaction/close path. Body/transaction errors propagate unchanged when both
known cursor and connection close succeed. These private cleanup failures are
not remote retry instructions and are never serialized. Their exception graphs
and failed objects remain process-local ownership, not an external recovery or
physical-resource certificate.

## Timeout and failure handling

Use one finite, non-boolean int/float timeout between zero and Python's native
`threading.TIMEOUT_MAX`. One monotonic deadline covers waiting for freeze/resume
serialization, gate/failure-lock acquisition and operation drain; phases do not
receive fresh budgets. Zero requests an immediate, nonblocking poll. A short
concurrent freezer cannot wait indefinitely behind a longer one. Once this
freeze closes admission, timeout leaves it closed and issues no token; a later
explicit freeze must observe actual scope completion before succeeding. A
timeout waiting for serialization before touching admission changes no state.
Neither timeout nor cancellation proves another thread stopped.

Drain uses short bounded polling with a deadline-limited condition-lock acquire
on every round. It does not use `Condition.wait`: that API reacquires its RLock
without a timeout after the timed wait and could exceed the total budget under
late contention. The gate lock is released between checks; bounded rests are
at most 10 ms and never exceed the remaining budget.

Scopes leave the active gate only after transaction/close handling and any
failure publication. The failure-ownership lock is not held while awaiting
drain. Existing close failures keep their actual connection and original body,
transaction and close exceptions; subsequent calls raise fresh poison wrappers
without retrying that close or reopening the store. A zero active-call count
alone cannot create or resume a fence after failed close. The implementation
does not keep a registry of successful connections/cursors or inspect GC/weakrefs.

## Exact proof limit

Each token certifies that the issuing owner's **admitted connection-operation
scopes have drained** and their close calls returned without a recorded failure.
Ordinary service statements additionally close their known explicitly owned
cursors within those scopes. The token still does not certify physical SQLite/
OS handle closure. CPython uses `sqlite3_close_v2`; an unfinished cursor created
through a raw/private bypass can keep SQLite resources alive after a successful
connection close return. See the
[SQLite close contract](https://www.sqlite.org/c3ref/close.html),
[CPython 3.12 connection implementation](https://raw.githubusercontent.com/python/cpython/v3.12.13/Modules/_sqlite/connection.c)
and [cursor implementation](https://raw.githubusercontent.com/python/cpython/v3.12.13/Modules/_sqlite/cursor.c).
No GC, successful-resource registry, pointer inspection or rename success is substituted for
that missing resource-lifetime boundary.

Ordinary TranscriptStore methods return materialized rows/models/scalars,
consume multirow queries, and do not expose a cursor. Its private connection
factory/scope is not a containment boundary against arbitrary Python code.
An owned cursor is already explicitly closed even if its Python reference or
body traceback remains retained. Raw/private `connection.execute/cursor` clients
can bypass that statement mechanism; their tracebacks or escaped cursors remain
outside the known-cursor claim. Future blob/backup or other resource types need
explicit lifetime rather than inheriting a cursor guarantee. Physical Windows
store detach remains separately unverified. A method with multiple connection scopes may be
between them when freeze succeeds; its next scope is refused. The fence does
not certify that every outer public method invocation has returned. The same
private-cursor/traceback limitation applies to Lexirise SQL scopes, pins and
reading scopes.

This is not a RuntimeDataFence, all-store/global writer proof, process signal,
`WriterStopProof`, immutable-slot eligibility or safe copy/directory-swap token.
Other independent service/store instances and raw SQLite clients are not
covered. Settings/file access, escaped reader references, indexes/voice
references and other registered workers still need their own resource-lifetime
connections. The reading registry below separately owns Runtime's known reader
creation and pools. The initial WebSocket status thread has a separate epoch/admission
boundary; it does not aggregate these owners into a RuntimeDataFence. Producer
drains which write final bookkeeping must complete before underlying SQL
admission closes.

The existing capture C2 path normally retains the OCR engine object while
joining its current/retired worker pools. This change neither proves native OCR
usability nor changes capture. Retaining an object while resume creates a fresh
worker pool is not proof of a usable warm native session. That future aggregate
boundary needs explicit same-engine operation evidence and must remain distinct
from whole registered-cohort process-signaled ownership. Global/dynamic writers,
keeper death, warm routing, copied-data activation, rights and Windows 11
acceptance remain open.

## Runtime reading creation and pool ownership

`RuntimeReadingRegistry` is the Runtime's reading-specific creation owner.
`Runtime.reading_for` reserves an admitted lookup before pinning the account,
resolving settings or computing the existing exact account/language/translation/
settings key. The registry lock protects only short metadata transitions; no
credential, HTTP, SQL, constructor or pool operation executes under it. A single
record owns the actual fixed `LexiriseReadingService` object before its
constructor starts. Concurrent same-key callers share the eventual instance;
independent keys can construct concurrently. Default, cached, in-flight and
failed constructor objects remain retained. The `_readers` view is read-only
and is no longer the lifecycle authority.

Strict C2 closes lookup/creation admission before awaiting HTTP requests. Its
existing one monotonic deadline includes registry metadata acquisition, in-flight
lookup/constructor drain and every owned reading pool. Actual blocking work
remains in `_handoff_drains` after waiter timeout or disconnect. A stopped lookup
cannot return a reader, even if its constructor later succeeds; the completed
object stays owned for pool drain. Resume refuses live creation or a failed
record, resumes pools while creation stays closed, then reopens creation only
at the existing final request-admission step. Registry metadata acquisition at
these synchronous recovery calls is nonblocking. A partial recovery or concurrent
stop cannot authorize reopening. Ordinary capture-only source handoff keeps its
existing behavior and does not opt into this strict creation boundary.
If the final metadata acquire exhausts its budget after a control body has
finished, its exact terminal control record remains observable and can be
retired by the next bounded drain/recovery. That does not reset a constructor
failure or bypass a pool's own still-running drain. Recovery also handles a
stop which timed out before changing admission: it first closes/retires creation,
then refuses any live lookup before resuming pools. It never assumes that a
failed stop had already closed admission.

Constructor failure permanently closes this registry's creation admission. A
fresh `ReadingRegistryPoisonedError` keeps the actual partial object and original
constructor exception/traceback, including a retained failed SQL connection if
present; later refusals do not grow that original traceback. Shutdown closes
creation, waits for real lookups/constructors and drains default and cached pools
under one declared reader-shutdown budget. It also joins any known initialized
pool on a failed partial reader, then still refuses cleanup success. It does not
retry failed SQL close, replace the failed key or reset the registry. Retention
depends on the living Runtime/raised failure; this supplies no external startup-
failure or process-death lifetime guarantee.

This creation/pool boundary alone does not count an escaped reader's arbitrary
direct SQL/HTTP work, close every physical SQLite resource or mint a
`RuntimeDataFence` or `WriterStopProof`. The separate SQL composition below
counts admitted SQL scopes of every retained reader. Independent readers, global
dynamic writers, keeper death, mutable-root detach and warm routing remain
separate requirements. Existing C5 constructor interception retains exactly its
three actual store opens, with no successful-connection registry or new SQL.

## Concrete Runtime SQL composition

The existing strict `quiesce_writers` path first closes request and reader
creation admission, drains requests and the existing export/setup/update/map/
reading/capture/voice producers, settles final publication coroutines, and
preserves the existing live-Hito refusal. Only then does its retained blocking
SQL step reserve the actual TranscriptStore/lifetime, the single Lexirise
root/pin owner and all retained default/cached ready Reading owners. A partial
constructor remains a refusal; the cache view or database pathname cannot
replace the registry's actual records. Different readers at the same pathname
remain different SQL owners. Root/pins share one owner.

Runtime installs a private actual-object handoff record before reservation can
fail. Registry metadata retains its exact record/member set and stopped epoch.
Each owner's expected epoch is captured before the first freeze, and the owner
binds its actual retained Runtime/registry member as the private controller under
its serialization lock. An integer epoch or matching closed/pending metadata
does not grant control: a different public controller's pending timeout is a
refusal. Every member is reserved before the first freeze. Each returned
canonical token is stored immediately, bound to its actual owner/subject and
reserved epoch. Ordinary strict response data remains the existing CaptureHandoff: these
private records never become wire data, a RuntimeDataFence or copy permission.

One monotonic deadline starts before Runtime lifecycle-lock acquisition and
covers request admission/drain metadata, registry/owner locks and the complete
strict SQL phase. Request metadata stop and bounded polling run in retained
blocking handoff steps, so a condition-lock holder cannot block the event loop
or obtain a new budget before the first producer drain. SQL freeze/check/resume
use private absolute-deadline helper primitives; public per-store timeout and
zero-poll semantics remain intact outside a retained Runtime controller. During
that reservation, competing public freeze/resume calls refuse. An opaque public
entry epoch also retires a public call queued before reservation, even if that
call acquires serialization after final Runtime admission. No Runtime call uses
an unbounded token check.
Registry locks protect only metadata: SQL, HTTP and pool work run outside them.

Failure issues no aggregate success. Partial tokens, actual objects, original
errors and actual tasks stay owned while request/creation admission is closed.
A failure before the initial metadata stop can leave admission unchanged; it
has not performed quiescence, and explicit recovery first closes/drains that
boundary. A clean pending SQL retry continues the same retained cohort/epoch,
without rerunning producers or rotating a retained registry SQL epoch. It can
observe an operation which actually finished; it never retries failed close.
SQL owners which have not reached freeze, or which partially resumed, need not
all have closed admission on a failed attempt. No copy/barrier claim follows.

Recovery closes/drains request and creation admission before native-stop/SQL
recovery. It completes pending freezes, then checks every canonical token before
resuming any SQL owner. Successful member resumes are recorded immediately and
never resubmitted after a later member/activation failure. Every resumed owner
must match its actual old issued token, its expected old epoch plus one, clean
failures and accepting admission. The helper keeps only the latest actual
resumed-token identity checkpoint, not a token history or connection registry.
Neither a matching fabricated token nor a newly observed epoch is adopted.
If an operation changed the owner and then failed before returning its result,
that unknown progress remains unavailable here rather than reconstructed from
the owner's current fence/metadata. This also applies to a lost reservation
result: its already-bound controller is not silently adopted on retry.

All SQL recovery finishes before producer pools, capture/update activation and
final reader/HTTP admission. Producer pool recovery also remains an actual
retained blocking step. A later activation failure keeps the SQL progress record
so retry checks post-resume ownership instead of submitting stale tokens again.
The actual controller binding stays retained through final admission. Runtime
acquires all owner serialization locks with the same deadline before acquiring
registry/request metadata. It then checks the canonical post-resume state with
a locked helper which never reacquires the non-reentrant serialization lock.
All fallible checks and lock acquisition finish before reader/request admission
opens; controller/record retirement afterward only installs already-prepared
metadata while those owner locks stay held. This prevents a competing public
freeze between the last owner check and final admission. No SQL, HTTP or pool
work runs under the registry lock. A failed final lock acquire preserves every
controller and closed request/creation admission. Existing capture-only source
handoff/activation does not opt in.

This composes only the known SQL owners and existing producer ordering. It does
not settle settings/account/language files, external export-volume work or all
dynamic/native resources. No actual Windows os.replace/rename of .db/WAL/SHM
files is proved by these tests. Native known-scope replacement belongs with the
next coherent populated-copy/adaptor validation unit. Physical Windows detach/
reopen, complete mutable-root fencing, warm OCR and installed-client acceptance
remain unverified.

## Frozen language-preparation registry default

`LanguagePreparation(path=None)` uses the discovered bundle `settings_root`
for `languages.json` and its existing `languages.requests.json` companion.
This binds the default before constructor reads and keeps the existing JSON
format and pending-file replacement behavior. An explicit `path` bypasses
layout discovery and remains unchanged. The existing canonical `sys.frozen`
flag chooses validated bundle discovery; environment root variables do not
turn source code into a bundle. Source mode directly retains its exact
`LOCALAPPDATA` / `Proxy Transcript/languages.json` calculation, including the
existing `.` fallback when that environment variable is absent or empty.
Invalid bundle discovery refuses instead of reading a different host registry.
Source does not acquire a new layout-validation gate before its legacy default:
an empty `LOCALAPPDATA` still works even when the separate source layout resolver
rejects a relative settings root. Tests exercise the real source resolver and
an authored frozen manifest/root set, including missing-root and invalid-manifest
refusal without falling back to host state.

The default belongs in this service: Runtime construction, `selected_snapshot`
and both export `prepare_source` selection-generation reconstructions create it
without a path. The mobile-export worker reaches these defaults through
`prepare_source`; index/language-build workers do not construct the registry.
All these callers therefore use the same explicit frozen settings root,
including the generation check after switching a selection away and back.
An unselected bundle account cannot borrow a selection from the host registry.

This does not move files, change game/language choices, add a JSON-operation
fence, authorize migration or repair an unreadable named account. The existing
host `%LOCALAPPDATA%/Programs/Proxy Transcript/accounts.dpapi` locator stays
unchanged, as required by the [R18 host contract](r18-storage-host-contract.md).
Local tests use real owned temporary registry/request writes, reconstruction
and selection. An in-process mobile-export worker uses the actual selection
and generation code with strict account/settings/asset-metadata, lock and export
boundary mocks. Host registry/request/protected-store sentinel bytes remain
unchanged. These are path/consumer source tests, not frozen bootstrap, real
account/DPAPI, game extraction, mobile transfer or native installation proof.

## Validation

The focused [storage tests](../backend/tests/test_storage.py) use actual SQLite
connections and Events to hold both a transaction and its close call. They
exercise refusal before new connection creation, bounded competing freezers,
one deadline across serialization/drain, timeout/retry after actual completion,
close failure retention/no retry, invalid tokens and invalid timeout values.
An Event-controlled holder takes the gate condition only after admission closes;
freeze must time out while that holder and the actual connection-close remain
live, with no token and admission still closed.
An actual SQLite negative case retains an unfinished private cursor and shows
that a valid token can coexist with an independent exclusive-lock refusal;
fixture disposal is not used as product resource-release evidence.
That raw-private negative remains alongside the new positive owned-statement
case; it is not evidence of an ordinary public API race.
The existing Chinese/Hito/body/transaction/early-return tests remain applicable.
The [Lexirise lifetime tests](../backend/tests/test_lexirise_lifetime.py) exercise
real deferred transaction and close faults, original exception retention,
shared root/pin poison/fences, two held pin SQL/close scopes, bounded contention,
and a mock HTTP body holding the existing ledger lock. They also preserve
intermediate export commits through a remote-plus-close fault, forbid automatic
retry through a poisoned owner, and verify exact three-store C5 constructor
interception. Explicit fake keys and strict MockTransport prevent credential
fallback or real account writes. A pin-specific negative cursor case preserves
the physical-resource limitation instead of relying on fixture disposal.
The [reading lifetime tests](../backend/tests/test_reading_lifetime.py) observe
actual read transaction enter/exit and rollback-on-close behavior, write commit/
rollback/early-return semantics, constructor/body/transaction/close failures,
fresh poison wrappers and canonical per-reader fences. Events hold actual read
and write bodies and close calls, including a worker callback and an inline
already-done Future callback. Pool join/SQL failure and HTTP-outside-SQL negatives
keep their separate boundaries visible. Exact three-store C5 constructor
interception, a same-path independent reader and an unfinished private cursor
are tested without inventing global or physical-detach authority. Fake keys and
strict MockTransport prohibit real account or credential fallback.
The [Runtime reader tests](../backend/tests/test_runtime_readers.py) retain actual
objects before constructor entry, hold real SQLite close and mock settings HTTP
on Events, check same-key single construction, exact scoped cache keys, permanent
constructor failure/original traceback retention and no SQL close retry. They
exercise bounded initial/late metadata contention, partial recovery and default/
cached worker/callback shutdown. Existing handoff, cancellation and update-startup
fixtures explicitly provide this producer; production has no missing-registry
fallback. A cancelled handoff test keeps the actual creation thread and drain
task owned. Source tests also preserve the exact three-store C5 factory boundary.
The [owned statement tests](../backend/tests/test_sqlite_operation_resources.py)
retain actual cursors and body tracebacks while independently checking local
SQLite locks, and hold cursor-close calls on Events before connection close.
They exercise execute failure before a result is handed over, failure before
cursor-factory handover, actual deferred commit and denied rollback, both cleanup
faults together, falsey exceptions and repeated poison without close retry.
A same-class/equal-fields imitation error is deliberately equal to an issued
failure but cannot authorize body-error unwrapping. Root/pin poison is shared;
Reading read contexts remain nontransactional. Strict mock HTTP checks that
ledger cursors close before network work and intermediate commits remain.
Failed fixture disposal happens only after assertions and is not product
cleanup/retry evidence. Native Windows physical release remains unverified.
The [Runtime SQL tests](../backend/tests/test_runtime_sql_lifetime.py) use actual
temporary stores, root/pins, default/multiple readers and reader/voice pools.
Event-controlled producers exercise final SQL bookkeeping, a still-owned SQL
scope, late metadata contention, a retired constructor and cancelled handoff
waiters. Tests cover partial freeze/resume, lost transition results, final
activation retry, canonical/foreign tokens, unexpected post-resume epochs,
omitted members/defaults, poison/no close retry and a fresh second cohort.
The partial-freeze retry case waits for the real last owner's admission stop
while its SQLite scope and retained handoff task remain live, then uses a
test-only module-local helper clock to expire the received absolute deadline.
The shared time module and asyncio clock remain real. It does not
infer that phase from a short whole-Runtime timeout; separate metadata/lifecycle
tests cover the total timeout budget. Production deadlines are unchanged; this
controlled source test adds no native or measured default-30-second evidence.
Controller regressions cover a different public timed-out stop, a lost actual
reservation result, an already-queued public call delayed through Runtime
activation, and a concurrent public freeze at the final admission boundary.
Holding a final owner serialization lock through the deadline leaves all
controllers retained and request/creation admission closed without a lock leak.
An actual request-gate condition holder keeps its lock through the caller's
deadline while the event loop stays responsive. The native-cleanup test uses
an explicit adapter, not a native call, and checks one shared recovery deadline.
Earlier producer-only fixtures explicitly adapt the new boundary rather than
giving production a missing-owner fallback. Real credentials/transport/default
Runtime roots remain forbidden in the actual SQL cohort.
These are local source regressions, not native Windows or full R19 acceptance.
