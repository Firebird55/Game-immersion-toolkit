# Native desktop delivery acceptance

Updated 2026-10-31. This is remaining implementation and acceptance work under
[R19](r19-completion-plan.md) and the
[desktop delivery plan](desktop-delivery-completion-plan.md). The owner's current
request authorizes installer development and local replacement. It does not turn
missing native results or redistribution evidence into a pass.

## Implemented construction

- An exact inventory is checked before packaging: every file, hash, size,
  platform architecture and embedded source identity must agree. Extra files,
  missing files and escaping links fail. Contained inventoried POSIX links are
  retained for native libraries/frameworks.
- Windows Inno Setup installs immutable version folders under Program Files,
  offers a custom destination and independent Start menu/Desktop shortcuts,
  and launches the native executable as the original user. Upgrade requests
  graceful shutdown through the prior executable and waits for its state lease;
  a failure stops Setup. Uninstall removes recorded installation files, never
  user data or game installations.
- Linux packages contain a native executable and an optional install script with
  a destination override, application launcher and Desktop choice. macOS bundles
  contain a native executable in an `.app`, with optional drag-to-Applications DMG.
- Python, Qt status/tray dependencies, OCR and the isolated ASR process are frozen
  using the R19 spec. Build-host Python, Node, PyInstaller and Inno are not user
  installation prerequisites. Missing game helper/codec capabilities still need
  closure before a dependency-free release can be claimed.
- Qt/PySide sources are collected by `scripts/build-qt-resources.py` from the
  exact hashes in `packaging/desktop/qt-sources.json`. The build checks installed
  PySide/Shiboken versions, retains unmodified source archives and complete
  license/attribution files, and includes them through `--resources-root`.
  Missing or changed inputs fail; this collection is not final approval of the
  frozen native dependency inventory or unrelated bundled components.
- The release workflow invokes native construction on Windows x64, Ubuntu 24.04
  x64 and macOS 15 arm64. It checks the frozen host with a reduced
  PATH and uploads construction metadata only. Unreviewed binary candidates are
  not uploaded, signed or published.

## Build and package a private candidate

Run `npm run dev:doctor -- --full` before acquiring dependencies. Use the locked
Python and build-host manifests on the target OS; PyInstaller is not a cross
compiler. Then run:

```text
npm run desktop:build -- --output-root output/desktop-frontend
python scripts/build-desktop-runtime.py --frontend-root output/desktop-frontend --output output/native-candidate
python scripts/package-desktop.py --runtime-root output/native-candidate/runtime/GameImmersionToolkit --provenance output/native-candidate/CANDIDATE-PROVENANCE.json --target windows-x64 --output output/native-distribution --candidate --iscc <verified-build-host-ISCC.exe>
```

Every output directory must be new. A supplied exact wheelhouse additionally
binds wheel hashes and verifies installed distribution files. No dependency is
downloaded by the runtime builder or packager. Windows compiler acquisition is
separate, pinned by SHA-256 and verified Authenticode publisher in
`scripts/prepare-installer-compiler.ps1`. Use `linux-x64`, `macos-arm64` or
`macos-x64` for corresponding native builds; `--dmg` requires macOS. The archive
formatter supports Intel Mac layout, but Intel native construction is currently
unavailable: [ONNX Runtime 1.24.4](https://pypi.org/project/onnxruntime/1.24.4/#files)
provides a macOS arm64 wheel and no Intel wheel. The initial Mac runtime target
is Apple silicon on macOS 14 or later; a maintained, verified Intel ONNX Runtime
build is required before adding Intel to the supported build matrix.

The construction receipt deliberately has `r19_complete: false`, pending
redistribution and unavailable native acceptance. Omitting `--candidate` fails
until all production fields and the production runtime profile are approved.
Neither installer compilation nor a successful import probe closes that gate.

## Remaining evidence and implementation

- [ ] Record a maintained, exact CPython supplier and complete wheel/native
  dependency closure for all three initial targets; retain required corresponding sources
  and full selected Qt/plugin/PySide/Shiboken notices and license choices.
- [ ] Close common game-helper and audio-codec delivery, including the owned Node
  grammar reader. All games use the same capability states; unsupported or
  unverified inputs cannot silently fall back to a developer SDK/compiler.
- [ ] Build and validate maintained ONNX Runtime for Intel macOS before enabling
  that native target. Do not substitute an old unsupported wheel merely to make
  the installer matrix green.
- [ ] Run the frozen executable and installer with developer runtimes absent,
  offline reuse, a read-only installation tree, unrelated working directory,
  spaces/Unicode, resource corruption, port collision and clean Quit.
- [ ] Verify Windows Program Files elevation, shortcut choices, custom location,
  upgrade, same-version repair, cancellation, uninstall, rollback and retained
  browser origin using copied synthetic stores and TEST credentials.
- [ ] Test actual Linux X11/Wayland capture and macOS screen-capture permissions,
  monitor selection and tray behavior. Hosted construction/import is not desktop
  capture or microphone/audio acceptance.
- [ ] Verify installed launch opens the browser and keeps console/status logs,
  including child crashes, restart backoff and capture-worker replacement.
- [ ] Verify downloaded native assets and their provenance before release.
  Publication now waits for native construction and verifies the source archive
  and all three target receipts/checksum inventories together. A missing target,
  candidate, changed asset or different source commit stops publication.
  Current candidates are unsigned; signing/notarization is recorded separately
  and is not an additional owner-approval requirement for an unsigned release.
- [ ] Close the exact R19 acceptance rows before describing the native packages
  as the final all-games, no-prerequisites release.

Local construction evidence so far: eleven authored-header packaging tests pass;
the verified Inno Setup 7.1.1 compiler compiled the fixture Setup executable.
These prove package rejection/structure and compiler compatibility. The fixture
is intentionally not an executable application and was never installed.

The 2026-10-31 macOS hosted capture probe discovered its authored window but
found a full-display layer-20 surface and a layer-8 panel in front of it. Raising
a normal window cannot override higher window levels; this is consistent with
[Apple's window-level ordering](https://developer.apple.com/documentation/appkit/nswindow/level-swift.struct).
The geometry alone does not identify a lock screen or a permission dialog.
The capture guard continues rejecting all overlapping foreground windows.

The probe now records only bounded geometry and an allowlisted system-owner
category. A category requires the actual resolved process image under the macOS
system library, not merely a window's claimed owner name. Only an independently
observed, nonowned, effectively opaque system surface covering the full display
and the entire authored window can classify that exact occlusion failure as
`native-desktop-system-obstructed` (unavailable, exit 2). Unknown owners, partial
panels, identity lookup failures, and unrelated capture errors still fail.
Unavailable capture permits independent build/lifecycle checks to continue; it
does not pass native capture or close the corresponding R19 acceptance row.

The subsequent [hosted run 41205179217](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41205179217)
passed application checks, supplied screenshot replay, all five browser groups,
and extracted source-package checks. Linux frozen startup and crash recovery
passed, but the visible-UI run retained a log pipe after shutdown. The POSIX
browser opener now detaches its standard streams as well as its session, so a
user browser cannot retain toolkit log pipes; seven new cases cover both desktop
openers, failures and a long-running browser. Navigation remains separate from
a successful opener request. macOS still reports unknown covering surfaces;
bounded identity-verification booleans now distinguish lookup, system-location
and owner-label mismatches without exposing process names or paths. This does
not change capture rejection or convert unknown surfaces to accepted evidence.
The combined host/capture-probe local suite passes 23 cases. Native reruns remain
required. Windows construction in this run stopped on an audio-source network
timeout before freezing; it is not a frozen-runtime regression result.

Primary references: [PyInstaller operating model](https://pyinstaller.org/en/stable/operating-mode.html),
[Qt licensing](https://doc.qt.io/qt-6/licensing.html),
[PySide licenses](https://doc.qt.io/qtforpython-6/licenses.html),
[Inno download verification](https://jrsoftware.org/isdl-verify.php),
[GitHub hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
