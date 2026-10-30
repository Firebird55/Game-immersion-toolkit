# Desktop executable host

The executable opens the user's default browser once the API, verified static
frontend and LAN gateway are ready. Startup progress, capture status changes,
child exit codes and bounded restart attempts appear in the visible log window.
Windows also keeps a console open. Tray/menu-bar actions open the transcript,
show logs and quit. Desktops without a tray service retain the log window.

Starting the executable again contacts the current owner and opens its reader
and logs. It does not start another capture stack or terminate a PID from a
saved file. The owner holds the existing `companion-operation.lock` continuously;
a legacy launcher or updater cannot enter during the session. An installer can
use `--request-quit`: success requires the owner to release that lease after
shutdown, within 45 seconds. An unknown/busy owner is left untouched.

Child services run on OS-assigned private ports. Their readiness messages name
the socket they actually bound; the stable gateway retains the public origin
when a child restarts. Confirmed transcript data remains in the user-data store.
The host resumes capture after an API crash when its last observed state was
running, with at most five automatic attempts per service in five minutes.
It does not repeatedly open browser tabs during recovery.

Quit asks the API to drain capture and writers before stopping its services.
If graceful drain times out, the host stops only its retained owned process
trees. Windows uses a Job Object joined before the real child starts. POSIX uses
a parent-liveness watchdog and a retained process-group leader. Failed cleanup
keeps the operation lease and a visible recovery state; it cannot silently start
a replacement. The POSIX implementation still requires native platform evidence.

Local logs rotate at 2 MiB with four backups. They contain status and child
diagnostics, with common credential headers/fields redacted and control codes
removed. Logs are private local diagnostics and must never be uploaded as public
CI artifacts. The GUI retains at most 2,000 lines.

## Developer and candidate entrypoints

From a prepared source checkout, build with `npm run desktop:build`, then run
`python -m backend.desktop_host`. `--frontend-root` selects an already built,
manifest-verified source frontend. No developer server is started by this host.
`--headless --no-browser` provides the same supervision without a display.

Frozen launches select platform user-data storage outside the immutable app
slot: LocalAppData on Windows, Application Support on macOS, and XDG data storage
on Linux. `--data-root` selects another absolute user-data folder. Source mode
retains the legacy installation-root interpretation of this option. Child roots
remain explicit through the fixed runtime layout; working-directory changes do
not redirect writes into the app.

`--host-check` validates the frontend and imports the GUI runtime without
starting services, opening a window or preparing user data. It explicitly reports
native acceptance as not run. A private `runtime-experiment` candidate may test
this host; that does not enable the production distribution gate or close R19.

## Evidence and remaining work

Windows source checks cover actual API/frontend/gateway startup in disposable
state, API-bootstrap termination, descendant cleanup, a new private API port,
retained public origin and graceful shutdown. Separate real-process tests cover
descendants after parent exit and unexpected owner death. Unit checks cover
instance reuse, browser-origin rejection on host control, log redaction,
single-browser startup, restart ordering and retained exclusion after a failed
cleanup. These are source-host results, not extracted-installer acceptance.

Automatic software updates remain explicitly unavailable in this host until
the owner-aware frozen transaction in [R19 C3](r19-completion-plan.md) is complete.
The source updater cannot be nested inside its continuous operation lease.
Game-data preparation continues through the normal shared runtime services.
Final frozen resource closure, ordinary browser profile continuity, platform
native capture and installed repair/update/uninstall remain in the
[desktop delivery plan](desktop-delivery-completion-plan.md).
See [desktop platforms](desktop-platforms.md) for the implemented discovery
backends, capture permission requirements and native verification limits.

POSIX service watchdogs retain a session identity; nested owned helpers use
separate groups inside that session. The outer watchdog stops every group before
reporting service exit. It also inherits the installation lease descriptor,
which is excluded from actual commands and retained by the watchdog until
verified cleanup. Unknown cleanup retains ownership and keeps reporting status.
This prevents a host crash from releasing the installation while nested writers
are still exiting. Native Linux/macOS failure acceptance remains required.

Windows top-level services have an outer guardian that inherits the exact
exclusive installation handle. The application joins its child Job before it
can spawn helpers; the guardian stays outside that Job and retains the lease
until all Job members have signaled exit. This closes the interval between host
death and completion of asynchronous Job termination. An actual source-process
test kills the host and proves a second owner cannot acquire before the writer
has exited. Extracted bootloader/installer acceptance remains a separate check.

Atomic route/control publication preserves the previous file and retries short
Windows sharing conflicts. Shutdown likewise retains ownership while a local
reader temporarily holds a state file. The local control token is written with
private permissions before publication.
