# R19 guarded cold-slot recovery experiment

`probe-frozen-slots.ps1` is an opt-in **Windows build-host experiment**, using
the existing fixed frozen C1 host and the explicit strict C2 writer protocol.
It creates two complete, verified, read-only copies of the same experimental
candidate and independent, newly authored private state for each copy. It does
not update a real installation, copy a live store or change the production host.

The guardian is build-host PowerShell 7. It is not shipped as a user runtime
prerequisite and adds no runtime child target, resource allowlist or manifest
schema. The target processes are the existing frozen frontend/API probe with
OS essentials and authored roots only; they inherit no development-tool PATH
or real account/profile roots. The frontend and process tree are real. The API
uses C1's existing mocked external account/game/OCR/background startup behavior.
There is no installed-game, native capture or protected TEST credential claim.

## Ownership and transaction

The guardian imports only the named existing C1 harness function definitions
from the checked-out `probe-frozen-runtime.ps1` AST. It does not execute that
script's probe body, duplicate its observer policy, or introduce another router
or updater. It retains the actual host creation handles and every registered
Job-member observation handle, including verified OS console helpers. Those
handles remain retained until confirmed exit, and public output contains no
process IDs, handles, root paths or raw control messages.

The old-root fixture's `data/companion-operation.lock` and the separate target
runtime lease are opened in fixed order using the existing source launcher's
`FileMode.OpenOrCreate`, `FileAccess.ReadWrite`, `FileShare.None` semantics. The
open handles stay in the outer guardian while C1 hosts start, drain, exit,
restart and crash. No source updater, nested lock request, `already-held` flag,
lease handoff or temporary release is used.

An independent fixed PowerShell contender verifies writable baseline access,
then requires the exact Windows sharing-violation error 32 while each lease is
held, and successful access after explicit release. Access denied or an absent
path cannot be counted as exclusion. A second fixed mode invokes the actual,
unmodified `Enter-CompanionOperation` definition from `companion-runtime.ps1`
on the authored legacy root, using its existing zero-second timeout for a
bounded attempt. That source operation must enter before acquisition and after
release, and report its own fixed busy outcome throughout every held phase.
Only that named source function is evaluated; the source launcher/updater is
not executed. Its checked-out source file SHA-256 is bound into the receipt.
This verifies interoperability with that exact source operation, not every
historical launcher. The contender accepts no arbitrary command/script input.

The authored roots are distinct: `legacy/data/companion-operation.lock` is the
source-compatible lease; `private-target/host-v1/migration-runtime.lock` belongs
to the outer guardian. Its private journal sits in the same guardian `host-v1`
folder. Per-slot C1 settings roots are separately created under
`authored-state/A` and `authored-state/B`; their `host-v1/synthetic-probe.json`
markers are not the target lease and cannot establish ownership.

The fixed attempt performs:

1. Verify the original candidate and both physical copies against the complete
   provenance inventory, including hidden/system files and empty directories.
   Reject unknown files, case aliases, unsafe names and reparse points. Keep
   writable state outside both immutable application trees.
2. Acquire both guardian leases and start A with the actual C1 owner. Invoke
   `/api/runtime/quiesce?writers=true`, require paused capture, and verify ordinary
   application requests become 503 while health/control remain available.
3. Stop A and require all retained child objects to be signaled before releasing
   its ports or starting B. Start B cold and strictly activate its paused capture
   handoff. Verify session identity, standby and reopened request admission.
4. Strictly drain/reap B, restart A and restore the paused handoff, demonstrating
   code/lifecycle rollback without opening another version's writable schema.
5. Start B's real C1 negative-index fixture, observe its actual owned HTTP service
   remain unready for the absent selected index, and reap it before restoring A.
6. Terminate the actual A host through its retained creation handle while the
   guardian keeps both lease handles. Wait for every registered child object to
   become signaled, retain exclusion through that observation, then verify the
   final independent-open success only after explicit guardian release.

The two copies initially contain identical candidate bytes and versions. This
proves a cold lifecycle primitive, not a genuine version/schema upgrade. Each
slot receives independently authored empty state; there is no migration,
credential snapshot or raw SQLite/WAL/SHM copy between slots.

## Failure boundary

Normal operations have bounded startup, API, host-exit and child-exit waits.
Strict C2 retains its existing 30-second runtime quiesce deadline; the HTTP
client's 35-second timeout allows transport/response overhead and does not extend
that runtime budget. Host and retained-child exit observation share one
15-second wait budget. These constants are reported separately and are not
performance or production recovery acceptance measurements.
Unconfirmed registered cleanup retains its observation context and leases.
Unknown early registration cannot be repaired from a PID file, port availability
or journal. In that case the experiment reports a fixed recovery-required
message and keeps its guardian alive with the leases instead of releasing
exclusion. It cannot produce a passing receipt. A monitored CI job must bound
this failure externally; terminating the guardian is an explicitly unverified
boundary, not successful recovery.

The private journal records logical phases and build identity for diagnostics;
it grants no ownership or restart authority. The first slice does not prove
survival of guardian death or crash before all child handles are registered.
Application processes inheriting a lease, or a copied live-process record, do
not close those gaps. Production activation remains unavailable.

## Hosted invocation and evidence

Run from the exact checked-out build commit after the normal extracted C1 probe
passes. The required inputs are the complete quarantined `runtime-experiment`
application tree and its matching `CANDIDATE-PROVENANCE.json`. The script requires
`GITHUB_SHA` to match that candidate, verifies complete file/directory inventory,
and budgets room for both copies plus private state. Both canonical ports must
be available. No live/source installation root is an input.

```powershell
& $env:PYTHON -B -m pytest --noconftest -q backend/tests/test_guarded_slot_probe.py
if ($LASTEXITCODE -ne 0) { throw 'Guardian source contracts failed.' }
./scripts/probe-frozen-slots.ps1 `
  -RuntimeRoot (Join-Path $env:GITHUB_WORKSPACE 'output/runtime-bundle/quarantine/ProxyTranscriptRuntime') `
  -Provenance (Join-Path $env:GITHUB_WORKSPACE 'output/runtime-bundle/quarantine/CANDIDATE-PROVENANCE.json') `
  -Output (Join-Path $env:GITHUB_WORKSPACE 'output/checks/r19-guarded-slots.json')
```

The source contracts exercise independent real Windows file exclusion and
complete inventory refusal using authored bytes. Their cleanup-order fixture
uses fake process objects and replaces the port check, so it cannot touch a
running companion. The actual frozen two-slot/Job/retained-handle cases require
the hosted invocation above. No native success is recorded until that exact
artifact executes and its downloaded sanitized receipt is verified.

Only `output/checks/r19-guarded-slots.json` may be uploaded. Its separate
`proxy-r19-guarded-cold-slot-probe-v1` schema records actual phases, paused strict
API use, real process-tree scope and explicit unverified gates. Raw journals,
application copies, account-like state, observer/control records and child logs
stay private. The successful attempt removes its private trees. A failed attempt
preserves private evidence. Neither receipt nor successful cold replacement is
a production writer-stop/store-copy capability.

## Separate C3/C4 gates

B is verified while A serves, but is started only after A exits: the existing
C1 probe uses canonical ports. Warming the selected candidate/index/OCR before
draining A remains unproved. Stable routing, old Vite `assets/*` retention,
frozen retained-root handling, browser reconnect/profile continuity, real
capture ownership, protected credentials and schema-aware data rollback remain
separate requirements. The source router's `/_next/static/*` retention alone
cannot supply frozen Vite chunk continuity. No R19 gate, rights approval,
release, installer or automatic frozen update is enabled by this experiment.
