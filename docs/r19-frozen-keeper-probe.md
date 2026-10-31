# Restricted frozen keeper experiment

This experiment exercises guardian loss while a separate frozen keeper remains
alive. It is a build-host probe using fresh temporary authored roots, the
existing `FrozenProbeHost`, the existing directly suspended creation primitive,
and the existing frontend/API-probe entrypoints. It adds no installed launcher,
production caller, general child target, dispatcher or installer. The production
runtime profile remains disabled. Passing source fixtures do not establish
native Windows acceptance.

## Fixed ownership and lease lifetime

The keeper itself runs through `--runtime-probe host`. Its only additional case
names are `keeper-before-resume` and `keeper-after-ready`. Its bounded private
input accepts three literal phase controls: `start`, `lose-guardian` and
`release`. These select fixed authored behavior; they cannot supply a command,
image, PID, account, store or root. There is no separate drain command: observing
the retained guardian object's exit drives writer drainage.

The keeper creates a read-only frozen frontend on port zero as the guardian and
retains its real `Popen` creation object. The fault calls `kill()` on that object
and waits for it. A PID received in JSON never authorizes a process open or kill.
The listener table must identify that still-live creation object both before
and after an actual HTTP read of the pinned frontend index. Bounded process
snapshots must show no current guardian descendants at those observations.
Unexpected observations require recovery.

The keeper owns two genuine `CreateProcessW` records for the fixed frontend
port 3000 and API-probe port 8766. Both process/thread pairs are registered
while suspended, with an atomic Job List at creation and handle inheritance
disabled. Only after both are registered may the after-ready case resume them.
The before-resume case never resumes either writer. The after-ready case
requires the actual canonical HTTP endpoints, then uses the existing explicit
`writers=true` C2 quiesce protocol after guardian loss. Capture must remain
paused. Its runtime deadline is 30 seconds; the HTTP transport budget is
35 seconds. Account, game and OCR startup side effects remain mocked by the
existing API probe.

Writer authority comes from those two retained creation objects. Job census and
listener observations are checked against them using `CompareObjectHandles`,
including before and after HTTP readiness. Unknown or aliased members are never
adopted, killed by PID, or erased through a generic Job drain. The keeper stops
and waits for each retained writer object, rejects remaining Job members, and
only then closes their handles and the Job. A separate `release` observation
latch lets the harness check contention after writer exit but before lease
release.

The lease implementation is the existing `ExclusiveFileLease`. Its Windows
exclusive open matches the unchanged source `Enter-CompanionOperation` contract:

| Authored path below `keeper-fixture` | Purpose |
| --- | --- |
| `legacy/data/companion-operation.lock` | Existing legacy source exclusion |
| `private-target/host-v1/migration-runtime.lock` | Separate keeper-owned target exclusion |
| `authored-state/` | Fresh synthetic writer settings/data/cache/work/export roots |

The separate private target lease is not the writers' state root and is not a
real installation or migration target. The keeper holds both leases outside
the writer Job. The harness establishes successful native and actual source
operation baselines before acquisition, requires both independent contenders
to remain blocked before guardian loss and after retained writer exit, and
requires them to succeed only after explicit release. Native contention accepts
exact sharing violation 32; access denied or unavailable observations fail.

## Failure and evidence boundary

Unknown membership/lifetime, failed creation, resume, observation, strict
quiesce, stop, handle close or lease release produces a sanitized
`recovery-required` event and leaves the keeper alive holding whatever leases
and creation objects it still owns. No `finally` or context manager releases
leases on that path. There is no automatic restart, PID adoption, retry of an
unconfirmed raw handle or successful containment claim from process exit.
The live hold is independent of event/receipt transport: a broken output pipe
or receipt-write failure cannot bypass it, and diagnostics are best effort.
The build-host harness also remains alive on an unconfirmed live keeper so an
external job timeout can end the failed run. Such external keeper termination
is an unverified keeper-loss boundary, never a passing cleanup result.

This is a deliberately narrow fixed-role experiment. The current freezer uses
a Windows `onedir` `EXE` plus `COLLECT`. The pinned PyInstaller source selects
the Windows onedir main-process path; that source inference and finite Toolhelp
snapshots do not prove absence of transient or undiscovered children throughout
a lifetime. Unknown bootloader/console helpers fail this new cohort's exact
creation-object check. They do not inherit C1's separate helper allowance. The
ordinary C1 bootstrap route and its four-runtime/two-console expectation remain
unchanged. References:
[PyInstaller 6.22.3 bootloader](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/bootloader/src/pyi_main.c),
[CompareObjectHandles](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-compareobjecthandles),
[process snapshot API](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot).

The PowerShell harness imports only named existing harness functions through
their parsed AST, without executing their script bodies. It verifies the exact
quarantined candidate's complete inventory before and after the experiment,
uses temporary space/CJK paths and an environment without developer tools, and
publishes `proxy-r19-frozen-keeper-receipt-v1` separately from C1. Public metadata
contains fixed scope/status/count labels and candidate identity, not process
IDs, handles, paths, raw control events, native logs or account diagnostics.
A passing receipt is written only after successful lease postconditions and
temporary-tree cleanup. A failed receipt never upgrades partial observations.
The authored case roots are children of the harness-selected `empty-host` TEMP;
the frozen containment guard still rejects sibling roots outside that TEMP.

## Hosted invocation and remaining gates

After extracting and independently verifying the exact candidate, run on
Windows PowerShell 7 on the build host:

```powershell
./scripts/probe-frozen-keeper.ps1 -RuntimeRoot $candidateRoot `
  -Provenance $candidateProvenance -Output $separateKeeperReceipt
```

The harness needs the repository's existing `probe-frozen-runtime.ps1`,
`probe-frozen-slots.ps1`, `r19-runtime-inventory.ps1` and
`companion-runtime.ps1` alongside it. PowerShell is a build-host prerequisite,
not a tool shipped to the user. Hosted integration must bound the job and upload
only the separately allowlisted sanitized receipt. Source fixtures run with:

```sh
python -B -m pytest --noconftest -q backend/tests/test_runtime_host.py
```

Until the exact frozen Windows artifact produces a downloaded, verified receipt,
the autonomous frozen keeper result remains pending. Even a passing receipt
covers only these two fixed guardian-loss cases with a living keeper. Keeper
loss, general/dynamic writer admission and lifetime closure, replacement-host
transfer, warm private-port routing, retained Vite chunk/browser continuity,
real credentials/data, production activation, rights approval and installer
acceptance remain separate open gates. No store is copied and R19 remains
incomplete.
