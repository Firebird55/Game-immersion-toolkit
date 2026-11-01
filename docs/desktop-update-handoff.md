# Desktop update handoff

Implemented 2026-10-31. The desktop host performs the service switch while
retaining the same installation lease, log window, tray and public gateway.
The API forwards Settings requests through a private loopback capability; it
does not start an independent updater or send that capability to a browser.
Repeated update requests are coalesced. Automatic checks run in the host at
startup and every six hours when enabled; disabling automatic checks preserves
manual checking. Source checkouts and experimental artifacts remain ineligible
for automatic installation.

The [release verifier](desktop-update-verification.md) downloads and checks the
new immutable slot while capture continues. The candidate frontend starts on a
private port and checks its complete public inventory before the handoff. The
host then asks the old API to drain requests, capture, background preparation,
exports and native setup within its 30-second drain budget. A failed drain does
not cancel the worker and does not authorize a second writer.

Before copying any state, the host stops the old API's entire retained process
tree and verifies descendant exit. This stronger barrier also covers nested
POSIX process groups and Windows Jobs. The reader shows a pause while the host
copies settings and data into separate private test roots. Copied SQLite stores,
prepared indexes, favorites, account selections and protected credential blobs
stay isolated from the live installation. Export libraries, cached tools,
state/control files and disposable work are not copied into those test roots.
The copy is bounded in total size and file count, rejects links and special
files, and never hard-links mutable stores. Failed private copies remain in the
work directory for local diagnosis; they must not be uploaded.

The new API first opens the copied stores in standby and warms OCR and the
selected game index. After that owned test process exits, a new API opens the
actual roots in standby and repeats readiness. Only then does the host transfer
bounded capture state and activate workers. The host persists the verified slot
selection, atomically changes the stable gateway's route and stops the previous
frontend. Existing WebSockets reconnect at the same origin. Old immutable
frontend chunks from the most recent sixteen builds remain available; their
slots are reverified on subsequent launches. A reader left open across more
than sixteen updates may need a reload. Installing a newer release normally
takes precedence over an older saved automatic-update selection.

Before selection commits, a failure stops and verifies every candidate process
before restarting the previous API. If any descendant cannot be verified dead,
the host retains ownership and reports recovery is required. After selection
commits, cleanup failures keep the selected runtime and drain all services;
they never restore old data or start an overlapping writer. Restart revalidates
the OS-protected release ticket and every selected/retained payload byte before
starting services. Route records and transaction journals never authorize
process termination.

Only storage epoch `1` and host protocol `1` are accepted. The user-data root
records this contract independently of the executable. A mismatched candidate
or saved contract is rejected before service startup. This implementation does
not perform schema migrations, automatic data restoration or compatibility
guesses based on SQLite's `user_version`. An incompatible future storage change
requires an implemented migration/recovery protocol and a new epoch.

## Evidence and remaining acceptance

Source tests exercise real SQLite copies containing authored favorites and
protected TEST blobs, private HTTP update controls, concurrent-request
coalescing, selected-index warmup requests, bounded capture transfer, rollback
ordering, failed descendant cleanup, storage-contract rejection and offline
slot revalidation. These use authored service adapters and mocked release
verification where explicitly stated; they are not frozen integration proof.
Separate Windows source-process checks cover actual API/frontend/gateway
startup, guardian termination and recovery at the same origin, graceful drain,
and exclusive ownership after host and guardian failures.

Remaining work for [R19 C3/E1](r19-completion-plan.md): run the final extracted
runtime on Windows, Linux and macOS through successful updates, failed
activation, interrupted/full-disk preparation, owner death, protected TEST
credential reopening and offline restart. Verify the same ordinary browser
profile and retained chunks, installer repair/uninstall, and native OCR plus
the selected prepared index on each final artifact. A source test pass or an
eligible-looking local receipt cannot substitute for that evidence.
