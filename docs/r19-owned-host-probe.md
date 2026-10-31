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

`ProxyTranscriptRuntime.exe --runtime-probe host` is accepted only by the
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
