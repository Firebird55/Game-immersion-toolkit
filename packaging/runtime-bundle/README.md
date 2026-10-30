# Native desktop runtime construction

The current desktop builder collects the static frontend, backend readers,
OCR/VAD resources, Qt status/tray host, native setup and an isolated ASR process.
Users launch the native executable; no Python, Node, compiler or SDK installation
is required on their computer. Optional game capabilities are represented by the
same resource-backed availability checks for every game.

`runtime.spec` constructs both `runtime` and `runtime-experiment` profiles. A
profile selects code collection, not release approval. Every new build starts
with `release_eligible: false`; only an exact target acceptance receipt permits
public installer packaging. The broader R19 completion flag remains independent.
See [target acceptance](../../docs/desktop-target-acceptance.md).

## Build

Run `npm run dev:doctor` before preparing dependencies. Provision the maintained
Python 3.12 interpreter and exact locked wheels, then build from a stable source
commit. The frontend must have the same version and source identity as the native
runtime. The build verifies installed wheel payloads against their wheelhouse,
validates every added resource inventory, and rejects source changes during the
build. All collected files and directories are recorded in candidate provenance.

```powershell
npm run desktop:build -- --output-root output/desktop-frontend
& $Python -I scripts/build-desktop-runtime.py `
  --frontend-root output/desktop-frontend --output output/native-candidate `
  --wheelhouse <exact-wheelhouse> --python-archive <pinned-Windows-Python-archive> `
  --resources-root <native-audio-resources> --resources-root <native-node-resources>
```

`--python-archive` compares the provisioned Windows CPython 3.12.16 standard
library and shared runtime with the exact archive in `python-supplier.json`.
The builder installs nothing. Additional native resource roots may be repeated;
collisions, links, missing files and changed hashes are rejected. Frontend source
paths, developer installations and mutable caches are never runtime fallbacks.

The ordinary host selects platform user-data roots outside its application tree.
Its console and native status window expose startup, worker status, recovery and
shutdown. Native account setup uses the fixed account-key child and the operating
system's protected credential storage. The historical source updater is refused
by frozen runtimes; the host owns verified immutable-slot updates and recovery.

## Native evidence and delivery

Run `scripts/probe-desktop-host.py` against the exact extracted frozen tree. Its
headless checks cover actual service startup, stable-origin frontend/API routes,
owned crash recovery and cleanup with the developer PATH removed. A separate
visible native probe must establish browser launch, status window and tray icon;
headless/offscreen checks cannot establish these observations.

`accept-desktop-runtime.py` accepts only reports bound to the original candidate
receipt, source commit, build identity and target, together with the exact input,
notice and corresponding-source review. It writes a new external receipt and
never changes tested payload bytes. `package-desktop.py` then produces Windows
Setup, a Linux install archive, or a macOS application/DMG plus a common update
ZIP. Unsigned artifacts say so explicitly. Candidate construction and source
unit tests do not establish native acceptance on another operating system.

The main process excludes ASR's sherpa native runtime. ASR has its own Analysis,
executable and `_internal` tree; workers reset the PyInstaller environment before
launch. Actual loaded-module isolation still needs frozen native evidence.
Proprietary oneocr DLL/model files and installed game Oodle libraries are never
redistributed. Their absence does not disable the bundled portable OCR engine.

## Game tools

Endfield and selective RE archives use owned Python readers. NTE uses an owned
self-contained bridge where its complete verified dependency resources exist.
Node grammar readers use an app-local pinned Node runtime. Audio uses the common
maintained FFmpeg/vgmstream capability resolver. Game readers share repair and
missing-pack states; game names are not a reason to quarantine otherwise valid
resources. Unsupported native dependencies remain explicit capabilities until
functional and distribution evidence is complete.

See [native audio delivery](../../docs/audio-runtime-delivery.md),
[immutable updates](../../docs/desktop-update-verification.md), and
[remaining native acceptance](../../docs/desktop-native-acceptance-plan.md).

## Historical diagnostic experiments

`record_diagnostic.py`, `record_runtime.py`, `closure.py` and
`build-runtime-bundle.ps1` retain the earlier Windows-only diagnostic/extracted
experiment protocol. They are not the current desktop delivery entrypoint.
Their older strict gates and historical results are documented in
[R19 runtime evidence](../../docs/r19-runtime-bundle.md) and
[compiler-free helper experiments](../../docs/r19-compiler-free-helpers.md).
The diagnostic profile exposes no API, account, extraction or updater children;
it cannot substitute for an accepted desktop runtime.
