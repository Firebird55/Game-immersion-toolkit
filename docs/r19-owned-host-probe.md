# R19 owned frozen cold-start probe

The extracted `runtime-experiment` now has one fixed host probe in its own
frozen executable. It starts the existing frontend child and the existing API
probe at `http://127.0.0.1:3000/` and `http://127.0.0.1:8766`, retaining the same
WebSocket origin. No Node, npm, PowerShell interop compilation or external
Python is needed by this host process. The source launcher remains unchanged.

The process tree is real: the host retains a Windows Job Object and both
bootstrap process handles. The existing bootstrap joins the job before spawning
the frontend or API, with kill-on-close and no breakaway. On stop/failure the
host reaps every bootstrap before draining the job, so a delayed bootstrap
cannot spawn after an empty-job observation. An unconfirmed drain retains
ownership and private logs and cannot produce a passing cleanup result.

The frontend is the actual closed-manifest static server. The API is the
existing `runtime_probe.api` entrypoint: actual Runtime, SQLite, routes and
WebSocket, with account/game discovery, normal background startup and OCR
warmup side effects mocked. This is not native capture, real account access,
installed-game coverage or production host acceptance.

## Restricted entry and actual readiness ownership

`GameImmersionToolkit.exe --runtime-probe host` is accepted only by the
existing Windows main-image `runtime-experiment` profile and its existing
build-bound private synthetic roots. It is not a new `CHILD_TARGETS` production
entrypoint, manifest schema, installer or activation permission. The source
runtime and ASR image cannot use this entrypoint. Children use the fixed runtime
image/environment and private work folders; no arbitrary command, port, target
root or external application is accepted by the host.

Readiness requires both the API's existing readiness endpoint and actual
frontend HTTP success. Windows `GetExtendedTcpTable` binds each canonical IPv4
listener to an actual process handle. Each handle must be live and a member of
the retained Job Object, and remains held through the HTTP check. The listener
mapping and live process objects are checked again before accepting readiness.
An already-running unrelated listener cannot satisfy readiness while the new
bootstrap is still starting; it causes refusal and is never terminated.

A private stdin control channel supports only fixed authored probe cases:
normal stop, one retained frontend-bootstrap exit, and an absent ZZZ-index
readiness deadline. The latter first proves that the real owned HTTP services
are alive, then observes the existing selected-index endpoint remain unready.
These controls are not exposed by an application API or accepted as ownership,
rights approval, writer-stop proof or production update authorization.

## Native failure observations and metadata

`probe-frozen-runtime.ps1` starts this one frozen owner instead of owning
frontend/API separately. For every ready host it opens and retains observation
handles for the job's reported bootstrap/service processes while the owner is
alive. It checks their image and creation time and never uses their IDs to kill
or adopt them. The hosted cases require those retained handles to become
signaled and both canonical ports to be available after:

- normal host stop;
- a frontend bootstrap failure, causing whole-slot cleanup;
- actual host termination through its already retained parent handle;
- a real HTTP selected-index readiness deadline on the empty authored state.

The observation set must include at least four exact runtime-image processes
(the two bootstraps and two services). A native Job snapshot can also contain
an OS console helper. Such an additional observation is accepted only for the
exact `conhost.exe` under the authoritative .NET `Environment.SystemDirectory`,
with the same creation-time and live-handle checks. An arbitrary `WINDIR`, CWD
or matching basename cannot select that image. Every console-helper handle is
retained and must become signaled too; it cannot substitute for a runtime image
or bypass Job cleanup and port-release checks. This OS prerequisite is not
collected or redistributed in the candidate, and grants no component rights or
production activation approval.

A separate negative case starts the same fixed authored frontend/API outside the
new host Job. Both really answer readiness/HTTP before the new host starts. The
host must refuse them and leave those outer-owned fixture services alive; it
cannot adopt their HTTP responses or terminate them. The harness alone then
cleans up its retained fixture processes.

The `services-ready` message includes transient Job Object member IDs solely for
private test control. The uploaded receipt contains only allowlisted outcome
names, counts and scope labels. It excludes raw control records, IDs, handles,
local paths, account data and logs. Real Windows execution is required before
these cases can be recorded as passed; local fixtures cover ordering/refusal
behavior only. Windows Server evidence remains distinct from Windows 10/11
ordinary-user and capture acceptance.

## Remaining host/update gates

The actual Server 2025 checkpoint at `acc68be` passed in
[run 41144087092](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41144087092).
The [download review](r19-frozen-checkpoint-20261031.json) binds its source,
build and complete inventory identities. Each of the four owned stop/failure
cases retained four exact runtime-image handles plus two exact Windows console
helpers; all six became signaled and both canonical ports were released.
The foreign-ready-listener case refused adoption and left both outside-Job
fixtures alive. All 628 Windows contracts passed. The separate twenty authored
classifier cases also passed in the observer-only job; that smaller receipt
built or started no runtime and is not native ownership evidence.

Downloaded sanitized metadata artifact 13019929500 matched SHA-256
cb129c1d431a3e74909e2e973b6f01772d4e7a05af8faf1fa19f03d8f2df529f.
Native binaries stayed runner-local. API side effects were mocked, no account
was accessed and Windows 11/capture/production acceptance remains open.

This is cold-start/stop ownership for one disposable slot. It performs no route
switch, installed-host adoption, browser launch, update, migration, store copy
or credential operation. It neither consumes nor weakens the separate
`bundle_host.py` / `bundle_migration.py` synthetic coordinator contracts.

A supervising frozen update still needs continuous legacy exclusion, an
owner-aware transaction, verified immutable-slot selection, capture handoff,
recovery journal/pointer reconciliation and browser/profile continuity. The
source PowerShell update operation reacquires the legacy exclusive operation
lock; it cannot run inside a host holding that same lock. Host-crash Job cleanup
does not alone prove legacy exclusion stays held until every child is reaped.
No lock bypass or frozen update enablement is added here.

The current source router retains only `/_next/static/*` while the static
frontend build emits Vite `assets/*`. Frozen `desktop_frontend.frontend_root`
also rejects retained roots. Reusing the router is therefore insufficient to
keep old static chunks available during a frozen route swap. App-local router
closure, Vite chunk retention and equivalent browser reconnect/update behavior
remain required. Component rights, durable source delivery, native Windows
acceptance and the full runtime gate remain separate and open.

## Internal normal standby owner: source building block only

`runtime_host.OwnedStandbySlot` is a separate programmatic building block. It
starts the ordinary frozen `api` and `frontend` children, rather than a probe
API. There is no CLI dispatch, launcher, updater, router or production caller.
The existing cold probe and its historical receipts keep their original scope.

Inputs are restricted to the main-image `runtime-experiment` layout, its full
child inventory, two explicit distinct private ports, an owner-supplied complete
file/directory inventory and runtime-manifest digest, and a fresh marker-only
`SyntheticRoot`. All seven writable roots must be below that disposable root
and separate from the newly selected private host-profile and temporary folders.
The owner verifies every file's regular type, single-link identity, size and hash,
rejects extra/missing entries and case aliases, and checks root ancestors before
descendant metadata or reads. The bound inventory is limited to 16,384 files,
16,384 directories, 512 MiB per file and 2 GiB total. It includes the executable,
manifest and the whole resource/native tree. The existing frontend verifier
additionally checks its closed public build and manifest binding.

These supplied hashes are integrity pins, not slot ownership, complete source,
native dependency, rights or production-activation eligibility. Their independent
provenance remains a caller prerequisite. Verification is a bounded filesystem
snapshot before creation and again before readiness is accepted; it does not
provide continuous filesystem protection or a concurrent replacement proof.

Both exact native creation records are retained in the existing Windows Job
before either resumes. Commands are fixed normal
`api --port … --standby --candidate-closed` and
`frontend --port …` entrypoints. Their environment comes from
`layout.child_environment` with an explicit minimal OS environment: authoritative
Windows directories and fresh disposable profile/temp locations. Parent keys,
proxy configuration, Python paths and host account locations are not inherited.
There is no mock API, account-store constructor hook or OCR replacement in this
class. Missing ordinary Runtime prerequisites must actually keep it unready or
fail startup. Marker-only state supplies no prepared-game or usable-OCR evidence.

Readiness checks the ordinary API response and exact frontend index bytes, MIME
type and ETag, with live Job membership and listener-to-creation identity before
and after the HTTP work. PIDs from TCP/Job queries are used only to obtain and
close read-only observations; they never become termination authority. HTTP starts
only when both currently owned listeners are present. A missing-to-present transition before any
HTTP work is normal startup progress; foreign bindings, Job membership changes
and process death still refuse readiness. The HTTP reader uses fixed loopback
requests, explicit content lengths and bounded raw
headers/body. It follows no redirects or proxies and reapplies the same absolute
deadline to each receive. One start deadline also covers control-lock waits,
creation, resume, validation and attempted failure cleanup; cleanup receives no
fresh timeout budget.

Failures retain original exception objects and real ownership records. The actual
Job owner is retained before its native constructor begins. Incomplete construction
or poisoned native ownership cannot become successful empty-process cleanup and
is never queried, closed or retried by this owner. Known children are stopped/closed
independently, while ambiguous creation identity or
unknown membership prevents closing the Job as a successful cleanup shortcut.
The pre-stop census cannot turn into lifetime proof: an observed unknown member
still blocks success if it disappears when a known parent is stopped.
Failed observer values are never queried, closed or retried again. A later
`close()` cannot retry or erase an earlier cleanup failure. Unconfirmed records,
sockets and work directories remain with the failed owner; the caller must retain
that owner while recovery is unresolved. No process-exit/lease-lifetime proof is
introduced. Successful close removes only the owner's scratch directory; the
disposable state remains the caller's responsibility.

Portable tests use typed creation doubles and actual loopback HTTP/frontend
fixtures. They verify fixed commands/environment, creation-before-resume,
partial creation, changed inventory, root links, foreign/reused listener identity,
child exit, deadline expiry and independent sticky cleanup failures. They are
source behavior evidence, not Win32 or normal frozen startup acceptance.

### Closed candidate admission: source implementation, native proof pending

The integrated desktop host uses the current production startup and updater
from `main`. Ordinary `--standby` starts both request-admission layers closed and
supports ordinary activation. This resumable standby is distinct from the fixed
experimental owner's `--candidate-closed`. That option requires explicit standby, an explicit private
port, Windows and the validated frozen experimental main image. It constructs
one permanently closed `RuntimeWriterGate` before importing the API services,
then passes that exact object through a process-local app/lifespan binding into
Runtime before its first service constructor. Missing, wrong or replaced startup
bindings refuse startup; a changed Runtime gate refuses work. There is no open
fallback, new environment permission, endpoint, ticket or owner-authorized opener.

The existing writer middleware permits only health and readiness HTTP paths.
For this candidate configuration alone, that same middleware moves inside local
access validation and outside the outer writer barrier and CORS, so even a
trusted preflight for another path returns retryable 503 before dispatch.
The ordinary order is local access, outer writer barrier, CORS, then runtime
writer admission. The candidate order is local access, its pinned runtime writer
admission, outer writer barrier, then CORS.
Configuration also binds the original writer registration and its exact original
runtime callback, with no positional arguments or extra keyword inputs; replacing
the same-class record or changing its callback refuses before any configuration
or service effects. The bound lifespan rechecks that registration, callback and
configured order before constructing Runtime.
WebSockets accept then close with 1013 before hub/status access; untrusted origins
still close with 1008. Both handoff controls return 503, including spoofed local
update headers and malformed bodies. Direct activation, pool/SQL recovery,
reader-creation admission, update start and gate resume refuse before their effects.
Stop/drain remain available, but neither is a global writer or resource proof.

Constructors and existing standby OCR/map warming still run against private state.
An Event-held warm-task fixture with actual Runtime/stores and ASGI requests tests
closure both while readiness is false and after readiness becomes true. Account
transport and native OCR are authored fixtures there; it is source behavior proof,
not an ordinary frozen startup or Windows OCR result. The fresh marker-only profile
still lacks native OneOCR prerequisites, and this unit supplies no assets, rights
approval or readiness exception.

Monotone closure does not make this a usable A/B candidate: there is deliberately
no supported transition that opens it. Coherent final-copy/store rebind, retained
OCR warmth, stable routing, WS/chunk continuity, keeper-loss/global-writer closure,
physical resource cleanup, recovery, source/rights eligibility and Win11 remain
open. A private port, 503 or readiness response confers no takeover authority. No
installer, migration, activation or capture start is part of this building block.
The inherited production updater still uses HTTP activation and warms a different
candidate instance after the final copy. Parent-held activation authority and a
retained warm instance rebound to the final stores remain unverified R19 work.
PR #59 was merged externally with its protected head unchanged; this task did
not change or merge it.
