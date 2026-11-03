# Parent-held initial idle activation (source experiment)

The source experiment implements one parent-held initial idle activation through
the existing host. It changes no updater caller, route, storage schema, dependency,
manifest, installer or acceptance gate. Tests do not construct Runtime against
default data or contact an account. The source-only mode explicitly refuses frozen
startup; it is not exposed by the ordinary launcher or updater.

The implementation retains the existing DesktopHost → Service →
OwnedProcess → main → API path. `_start(..., parent_control=True)` is an internal
opt-in source standby operation requiring the current real held installation
lease and exact Service implementation. It does not change `install_update`.
`_activate_parent_idle` validates the same Service, lease and actual lease-handle
object before and after the command. No route/control record, PID or HTTP header
is activation authority.

The only protocol is strict binary ASCII LF with at most 128 bytes including LF:

| Parent input | Child output |
| --- | --- |
| `TPC1\|1\|BIND` | `TPC1\|1\|BOUND\|<actual-private-port>` |
| `TPC1\|2\|ACTIVATE-IDLE` | `TPC1\|2\|ACTIVE` or fixed `REFUSED` |

EOF, partial/oversize/invalid frames, unexpected sequence, duplicate commands,
missing identity or broken IO poison the binding. No resend, resynchronization,
permissive JSON readiness or HTTP activation fallback exists. The retained pipe
is a capability to this child; it attests no executable provenance or license.
The child has one sequential input consumer (initial bind, then one reader),
one serialized output writer, and the existing ASGI loop for Runtime transitions.
Normal output is redirected to stderr while the actual stdout wrapper and binary
endpoint remain retained. Parent stderr uses a fixed-buffer discard consumer.

The exact gate exists before API imports/service constructors. Runtime is retained
before its service constructors. Before grant or Task creation, the initial frame
checks actual capture, RequestBarrier/idle Event, registry, operation lock,
drain-list and gate epoch identities, inactive capture, paused idle request owner,
and absence of any prior SQL handoff, writer handoff, quiesce task, request-stop
record or partial drain. This is intentionally initial-idle-only. Setting standby
metadata alone cannot make a previously quiesced cohort eligible.

The retained decoded command creates one canonical object grant for the same
Runtime/gate and actual Task. The actual Task/ASGI loop/thread must be the caller;
possession of that grant by another Task is insufficient. The Task is retained
before a launch Event allows effects, and the initial-cohort check repeats at
actual activation entry after acquiring its existing operation lock.

Exactly two fixed worker records cover pool resume and final admission. Their
actual bound method, worker Thread and waiter Task are retained before Thread
start. Method entry requires the same current Thread and canonical record/role,
once only. A copied/completed record, a second Task/thread, wrong method role or
reentrant call refuses. The actual result/error is retained before permission is
retired and completion published. The waiter observes actual Thread exit within
the caller's existing absolute deadline; timeout/cancellation leaves the same
actual operation retained, without resubmission. No ContextVar, thread identifier,
caller-selected callback or generic operation registry supplies authority.

The first source mode skips the unused no-op SQL resume. Direct parent-mode SQL
resume, activate_workers, resume_writers and gate.resume refuse before effects;
ordinary unbound recovery remains unchanged. Final admission holds the existing
gate condition then the parent metadata lock. Every fallible check and the
bounded registry metadata operation precedes the prepared metadata commit; no
second validator can fail after the gate opens. No IO, SQL or pool join runs
under the parent lock. Final admission consumes the grant. Ordinary ACTIVE
enter/ticket/start_updates remain usable without it. Permanent closed-candidate
behavior is preserved. New nested helper calls are class-qualified so unchanged
ordinary unbound Runtime fixtures keep their existing no-extra-argument contract.

The actual API wrapper reuses the original writer middleware record/callback and
validates per-record identity before lifespan construction. Parent standby exposes
only health/readiness HTTP; trusted OPTIONS and HTTP activation are rejected
before effects. Closed WebSockets accept then close 1013 before hub/status work;
untrusted origins retain the existing 1008 policy. BOUND means actual socket and
startup binding, not OCR/game readiness. The existing ready predicate is checked
by the actual idle-activation action before effects.

Partial Service, OwnedProcess, Windows Job and Popen objects remain retained
before their fallible initialization. Constructor uncertainty permits no owner
query/reconstruction/retry. Parent stop signals the existing separate liveness
endpoint first, confirms its existing owned-process/tree exit path, then joins
the actual control IO threads within the same stop budget. It closes streams
once only after actual IO completion. A timeout never closes a stream to unblock
another thread, infers success or releases a lease. Original errors and actual
resources remain held; this conservative source experiment refuses reuse after
a fault.

Portable tests use real anonymous pipes/FileIO/Events, the actual Runtime
no-SQL-record activate/admit methods with explicit producer adapters, real ASGI,
and the existing authored real-SQLite retained-cohort fixture. They exercise
fragmentation/bounds, retained activation after a cancelled waiter, missing/copied
command/grant refusal, ordinary ACTIVE work, partial constructors, liveness before
stream close, and four unchanged ordinary-main contracts. These parent-control
fixtures start no application service, native game/helper, default Runtime,
credential fallback, real account or browser. The real authored-SQLite scenario
verifies that a foreign Task is refused before effects and the designated Task
subsequently succeeds. Other cases cover
cross-thread/role/copy/reentry/completed-worker negatives, the unchanged ordinary
HTTP activation fixture, symmetric lease pre/post checks and a controlled final
metadata/retirement ordering test. The same-handle lease-alias test is explicitly
an authored identity substitution, not evidence of an ordinary product race.
The earlier private v1/v2 design reviews remain historical source evidence;
these application checks do not retroactively relabel earlier candidates.

Open boundaries are explicit. Alternate SQL-registry admission, retained-SQL
activation, dynamic/global writers, code/data transaction and ordinary updater
integration remain uncovered. Actual Windows pipe inheritance, extra write-end
absence, guardian/Job process signals, partial native construction/close and
physical handles still require exact-head native evidence. A failed/stalled IO
owner can keep the source experiment and its installation lease held; it is not
an automatic recovery feature. OCR warmth, stable routing/chunks/profile, final
copy B, keeper loss, real Windows11 hardware, rights/source delivery and full R19
remain open. There is no installer or PR59 change.

## Local pending-write stop boundary (2026-11-02)

The parent's readiness/activation wait now observes its stop Event while the
retained control write is still pending, as well as while awaiting the child
acknowledgement. It records an unknown-completion failure immediately rather
than waiting out the write deadline. This stops only the waiter: the actual
write operation, IO threads and streams remain retained, with no resend,
concurrent close or inferred process exit. Late write completion cannot restore
binding authority. The existing conservative refusal after an IO fault remains.

The focused regression uses the actual Service IO threads and anonymous binary
pipes, with an authored Event delaying the input write. It verifies failure
before write completion, original-error retention, refusal of retry/cleanup and
one late completed write without authority revival. The process owner is an
authored adapter; this does not prove OS process termination or Windows pipe
behavior. Ordinary updater integration and all previously open boundaries above
remain unchanged.

Self-review also found that receiving an acknowledgement could bypass a stop or
IO failure recorded while the parent was blocked in its acknowledgement queue.
The wait now rechecks IO health, Stop and the absolute deadline after the queue
returns and before accepting the acknowledgement. The same pipe fixture covers
these three boundaries with a controlled queue-return schedule and clock. This
is source-level refusal evidence, not a native scheduling or cleanup proof.

## Unacknowledged host activation (2026-11-03)

Existing service-level write/queue failures, lease identity checks and ordinary
failed-cleanup tests did not combine an absent activation acknowledgement with
host shutdown and a late reply. One source scenario now exercises the actual
Service and DesktopHost activation/shutdown methods using anonymous pipes,
retained IO threads and an exclusive lease on a temporary authored root. The
actual activation frame is read without replying; an empty acknowledgement wait
then advances a controlled clock past the unchanged 30-second host budget.

Repeated host shutdown retains the same service, lease and actual handle; a
second lease cannot acquire the lock. The source scenario checks that late ACTIVE
is refused, the original timeout remains first, activation retry sends no command
and no IO stream is closed. It also exposed an ordinary `_start` path that could
construct a replacement over a retained parent-controlled service. Both ordinary
and parent starts now refuse that replacement before child construction. Other
ordinary service starts retain their existing behavior.

The child process owner is an authored adapter; no application service, account,
native worker or browser starts. The clock and late-reply schedule are controlled,
and POSIX locking is only an analogue of Windows exclusion. This is not native
process-exit, guardian-inheritance or full host-run/update-transaction acceptance.
It closes no previously open R19 gate and adds no automatic recovery behavior.

The replacement guard also covers failure while evaluating constructor arguments:
the host marks a parent Service before registering it, rather than waiting for
`Service.__init__`. A child-command failure therefore retains the same partial
service and lease and refuses both kinds of replacement start before reevaluating
the command. An authored command-builder failure checks this pre-constructor
boundary without creating any child or native process resource. The pipe tests
also bound initial-write completion and reject repeated reads after the injected
deadline, so those regressions fail without blocking on a second absent frame.

## Control EOF during pool resume (2026-11-03)

The existing EOF scenario closed the parent pipe after ACTIVE; the admission-lock
scenario injected retirement at final metadata commit. Neither covered actual
pipe EOF while the retained pool-resume worker was still running. One additional
source scenario now holds that actual worker Thread in an authored capture-pool
adapter, closes the parent's input write endpoint and awaits the shutdown signal.
It verifies closed request admission, refusal of a second activation, and retention
of the same pending activation Task, worker Thread, waiter and operation record.

The scenario exposed continuation after late pool completion: capture handoff
could be imported and standby cleared before the later grant check refused.
After observing actual pool Thread exit and its result, activation now rechecks
the same parent grant before continuing to capture import, background startup
or final admission. The test verifies that EOF remains the original error,
late completion produces only REFUSED, standby stays set, no capture import or
admission worker starts, and the original worker finishes without cancellation.
A bounded output-completion observation precedes each pipe read.

The already entered pool-resume method is allowed to finish; this is not rollback
of its pool changes, global producer termination or native process cleanup. The
scenario uses anonymous pipes, Events, the existing Runtime methods and authored
producer adapters, with no default Runtime, account, browser or game service.
Windows inheritance, guardian/lease lifetime, retained-SQL activation, ordinary
updater integration and all other R19 acceptance gaps remain open.

The same EOF scenario also covers a worker that fails after control loss, rather
than completing successfully. It checks the exact worker exception in both the
retained record and waiter, with EOF still first and the worker exception second
in the binding's errors. Worker result observation precedes the post-completion
grant check, so retirement does not replace the actual worker failure. Both
outcomes retain standby and closed admission and emit only REFUSED; the failure
case adds no runtime behavior or broader acceptance claim.
