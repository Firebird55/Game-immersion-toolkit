# Host, installer and cross-platform completion plan

Status: remaining implementation, with native crash evidence recovered.
Tracks [issue #61](https://github.com/Firebird55/Game-immersion-toolkit/issues/61)
alongside the [R19 completion plan](r19-completion-plan.md). R19 A/B owns exact
runtime/helper closure; C owns supervision/handoff; D/E owns native and browser
continuity; F owns final artifact evidence. Installer transactions belong to
R20/R21 and release delivery to R22. The owner's request authorizes these later
slices; it does not automatically close R19 acceptance.

## Crash and host lifecycle

Windows Application Error event 1000 at 2026-10-29 18:40 Europe/Amsterdam records
an access violation (0xc0000005) in windows_capture.pyd in the toolkit's 0.20.1
runtime. This identifies the native failing component, not its precise trigger.
Raw event paths and machine diagnostics remain local and untracked.

- [x] Isolate Windows Graphics Capture in an owned child process so a native
  access violation cannot terminate the transcript API. Bound request size/time,
  close obsolete sessions on resize/window change, and reject stale frames.
- [x] Report native child failure, restart with bounded backoff and retain
  confirmed transcript state. Never capture an unrelated foreground window as
  an unnoticed fallback for an occluded game.
- [x] Implement visible timestamped startup/log/status output on Windows; provide an
  equivalent visible status/log window on Linux and macOS desktop launches.
- [x] Persist rotating logs, child exit status and recovery state without tokens.
- [x] Implement default-browser opening after readiness; reopening the executable reuses
  the running instance. Do not open another browser on every child restart.
- [x] Add tray/menu-bar Open transcript, Show logs and Quit; shut down only owned
  descendants. Reuse R19 C's real ownership and writer barrier instead of treating
  the synthetic host coordinator as production supervision.
- [x] Implement the production [writer barrier](runtime-writer-handoff.md),
  retaining executor and descendant ownership through timeouts and retries.
- [ ] Verify the final executable's ordinary-browser launch and native platform
  window/tray behavior; source and callback probes are not that acceptance.
- [ ] Keep the legacy operation lease, stable origin, atomic route activation,
  old asset chunks, schema compatibility and rollback guarantees for updates.

## Self-contained distribution

- [ ] Reuse record_runtime.py, closure.py, runtime.spec and fixed bundle dispatch.
  Include app-local runtime/frontend/OCR/codec/helper dependencies. Users must not
  separately install Python, Node, .NET, SDKs or package managers.
- [ ] Use one capability-driven helper/provisioning flow for all games. Resolve
  Endfield/PRAGMATA and other helper gaps through actual supported artifacts or
  replacements, not a permanent game-specific quarantine feature.
- [ ] Preserve exact source/notice/native dependency evidence. Do not collect
  Snipping Tool binaries, game DLLs, original audio or private metadata. A bundled
  portable OCR engine can supply baseline capture while native OCR stays optional.
- [ ] Build Windows installation with an executable entry point, architecture-
  appropriate Program Files default, changeable destination, independent Start
  menu/Desktop shortcut choices, repair/update/uninstall and tray support.
- [ ] Keep writable state in platform user-data directories, outside immutable
  installed application slots. The owner's disposable installation is not grounds
  to erase other users' stores during an upgrade.
- [ ] Add macOS and Linux launch/package paths and native capture discovery.
  Declare architecture, macOS permissions, Linux X11/Wayland behavior and any
  unsupported native feature accurately. A platform package alone proves no capture.
- [ ] Extend GitHub-hosted release CI for declared target architectures. Reuse
  each build across artifact probes; publish sums, provenance, notices and required
  corresponding sources. Report signing/notarization separately and accurately.

## Acceptance and delivery

### Checkpoint: 2026-10-31

PR #62 integrates the current branch with main and PR #60. Hosted validation
confirmed the symbolic-link, Windows recovery-fixture and Python provisioning
corrections. The hosted rerun passed all required application, browser and source
audit jobs. A later comprehensive local run passed core/browser/recovery checks
but reproduced the update scenario connection reset while streaming an upstream
response. The gateway had synthesized chunked bodies for bodyless requests;
those unread bytes can reset responses from HTTP/1.0 services. It now preserves
bodyless requests and still streams actual request bodies. The targeted gateway
tests and all five update scenarios pass; the earlier local run remains a failure.

Native executable and helper names now use `GameImmersionToolkit` throughout
packaging, shortcuts, updates and CI. The renamed Windows artifact from
`c583359` passes frozen host lifecycle and visible-UI probes. Its actual isolated
`GameImmersionToolkitAsr.exe` also imports the speech native API successfully;
the loaded-image check observes 59 application/Windows images without loading
the main runtime's ONNX family. Speech model inference remains untested by that
import probe. The Windows ZIP and Setup executable compile successfully, but
remain private candidates, not installed or published releases.

The naming fix passes the PR's hosted required checks. Native construction on
the preceding `4605d3f` passes on Windows. macOS exposed a missing Python 3.12
`waitid` API, and Linux exposed absent Qt xcb runner libraries. Commit `6c32c50`
adds a non-reaping macOS child-state observer and the Linux display dependencies
with an explicit missing-library diagnostic. Its comprehensive local checks,
including browser/LAN, recovery, installer/update fixtures and publication audit,
pass. Hosted application checks also pass, but native macOS tests still failed
and Linux identified one further xcb dependency (`libxcb-shape0`). The next fix
excludes macOS's kernel PID 0 from ownership enumeration: POSIX `getsid(0)` and
`getpgid(0)` query the caller, so treating PID 0 as a child falsely blocks cleanup.
Its regression and the other focused desktop tests pass on Windows (52 passed,
one platform skip); native macOS/Linux verification is pending. Native builds
now run alongside application checks after publication audit; release publication
still waits for every required check and native target.

Qt/PySide 6.12.0 source collection now retains the exact unmodified upstream
archives for PySide/Shiboken, Qt Base, SVG and image formats, alongside full
license and attribution files. Hashes bind these inputs to the resource inventory.
This closes the missing Qt source-file collection step; final selected native
dependency review and the other components' source/notice gaps remain open.
The resource collector and mobile export regressions pass together (76 tests).
The broad local run reproduced a Windows sharing error at final export publication;
bounded retries now preserve cancellation/source checks. A repeat passed Python
and the completed browser scenarios before being intentionally interrupted for
the platform fixes. That interrupted run is not full validation; hosted CI owns
the final combined gate.

The exact Windows candidate from `984cb51` now passes frozen host startup,
frontend/API access, API crash recovery, same-state restart, owned shutdown,
host-crash cleanup and immutable-inventory checks. Native visible-UI observations
also pass for status/log windows, tray actions and browser-handler requests.
These are actual frozen-process results, not synthetic executable fixtures.
Browser navigation and final installed-app acceptance remain open.

The `76e832e` hosted Windows candidate also passes frozen host and visible-UI
probes with the retained Qt sources. Its macOS owned-process tests pass (51
passed, two platform skips), and Linux native discovery, monitor bounds and
authored-pixel capture pass. macOS capture still failed because the authored
window was covered; its command-line probe now explicitly activates its own
application and centers within the available display. Native confirmation is
pending. Linux construction rejected a PySide wheel payload; verification now
reports the exact archive-relative file and reason, and runs immediately after
installation so failures do not wait for codec construction. Byte verification
remains mandatory. Local payload/capture regressions pass (21 passed, four
platform skips); these do not establish Linux or macOS native acceptance.

The follow-up Linux diagnostic identifies a bundled PySide `__pycache__` file
recompiled by pip. A generated cache is now accepted only when the installed
source matches the wheel byte-for-byte and its code object matches a fresh
compilation of that source with the same interpreter and optimization level.
Modified code and source-less caches remain rejected. The three optimization
levels have regression coverage (16 runtime tests passed, four platform skips).
macOS activation alone did not resolve the reported overlap; the authored probe
now records bounded layer/geometry diagnostics without other window titles or
process identities. Both native follow-up results remain pending.

Linux native UI construction now runs the same frozen status/log/tray probe in
an isolated X11 session with a real XEmbed tray service. Display authentication
is passed to the frozen child; its user data and profile remain isolated. The
probe stops only the tray process it started. Hosted X11 UI evidence is separate
from physical desktop/Wayland acceptance and browser-navigation evidence.

The first native build exposed an incompatible ICU DLL collected from an
unrelated developer tool on PATH. Restricting build discovery to the verified
interpreter and operating-system tools fixes startup. The native probe now
tracks fixed service entrypoints and their descendants, leaving the user's
browser outside cleanup authority.

The frozen-host probe covers startup, stable-origin API crash recovery, owned
shutdown and host-crash cleanup. The separate visible-UI probe observes status,
logs, tray availability and actual browser-handler requests. A successful handler
request does not establish browser navigation; that remains separate acceptance.

The NTE bridge now constructs the embedded CUE4Parse provider directly with its
managed codecs. The external OodleUE and Zlib DLLs are no longer downloaded or
accepted by the NTE dependency inventory. An installed-file probe reproduced the
previous Chinese original audio bytes and read all five text locales without
those DLLs. Full embedded dependency notices and a rebuilt frozen candidate are
still pending. Wuthering Waves and Cyberpunk packaged helper preparation, POSIX
codec closure, exact third-party notices and final platform acceptance remain
open; these are implementation tasks, not permanent game-specific restrictions.

Source validation: the frame/process tests exercise real child exit, hang,
truncated and oversized IPC, frame reuse, shutdown, resize replacement and
restart backoff. Windows Job Object descendants are reaped before replacement.
The native callback test checks copied pixels and expiration; a live GPU crash
and the final frozen executable still need the native R19 D/F checks below.

- [ ] Inject native-worker termination, hang, resize, stale-frame delivery and
  service crashes; verify recovery, one capture owner and preserved text.
- [ ] Test installed/extracted artifacts without developer dependencies: spaces
  and Unicode paths, unrelated working directory, read-only application tree,
  offline reuse, port collision, low disk, missing/corrupt resources and Quit.
- [ ] Run Windows monitor/DPI cases and real OCR with the final frozen candidate.
  Record macOS/Linux native results separately from hosted build/import tests.
- [ ] Verify upgrade, rollback and retained browser origin with copied synthetic
  stores and protected TEST credentials; real account writes are prohibited.
- [ ] Close required R19 rows with exact candidate evidence before claiming the
  production runtime complete. Keep unresolved gates explicit while independent
  UI, source capture and installer construction proceeds.
- [ ] Run branch checks/publication audit, merge verified work into main, release
  from clean main, monitor hosted Actions and verify downloaded checksums/provenance.
- [ ] Replace the owner's local installation as authorized after preserving crash
  evidence, and verify executable launch, logs, tray, browser and LAN connection.
