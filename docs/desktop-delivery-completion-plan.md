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

PR #62 integrates the current branch with main and PR #60. Its first hosted
publication audit passed; the application job passed 270 JavaScript tests and
2,097 Python tests, but failed one cross-platform symbolic-link fixture. The
fixture now records the host's actual link bytes; a new hosted run must confirm
that correction before merge.

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
