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
