# R19 quarantined Windows onedir prototype

This directory defines a Windows x64 PyInstaller **onedir** build of the existing
Python runtime. It does not release, tag, install, alter Pages, acquire games or
write accounts. R19 remains incomplete: no clean Windows 11 25H2 acceptance,
maintained Python binary supplier decision, complete collected-file license/native
closure, compiler-free game-helper inventory, static frontend equivalence or
supervised frozen update has been established. Source adapters remain available.

`runtime.spec` contains an explicit backend/dynamic-reader closure and separate
ASR executable/native tree. Every one of the 25 active games remains mapped in
`toolchains.json`; shared toolchain results never imply an unprobed game's native
playback. Half-Life's text-only reader and global setup requirements are separate.
Persona's pinned GPL character tables remain a separately acquired private cache.
Neither proprietary oneocr DLL/model files nor the installed Death Stranding
`oo2core_7_win64.dll` may enter a candidate. Actual loaded-module origins and native
DLL dependencies remain Windows probes, including the install-local Decima path.

## Inputs and build

Run `npm run dev:doctor -- --base upstream/main` before preparing a build host.
Provision a precise Python 3.12 x64 distribution and packaging wheels on Windows;
this build script never installs or downloads them. Runtime dependencies still
use `requirements.lock.txt`; that file pins versions, not artifacts or rights.
`build-inputs.example.json` is deliberately incomplete and fails closed. Populate
an ignored/private input manifest with the exact source commit, portable build ID,
interpreter hash and these records for **each** Python/packaging/runtime component:

- `name`, exact `version`, HTTPS `source`, `architecture`, `license_expression`;
- `artifact: {path, sha256}` relative to the private evidence root;
- `licenses: [{path, sha256}]` with the actual complete license/NOTICE bytes;
- `installed_files: [{path, sha256}]` relative to that interpreter's prefix
  (`sys.base_prefix` for CPython), binding the actual build environment;
- `review_status: approved` and `native_closure: reviewed` for runtime builds.

Exact packaging inputs include PyInstaller, pyinstaller-hooks-contrib, altgraph,
packaging, pefile, pywin32-ctypes and setuptools. The diagnostic direct pin is
PyInstaller **6.22.3**, identified in the [official release](https://github.com/pyinstaller/pyinstaller/releases/tag/v6.22.3)
and [published package](https://pypi.org/project/pyinstaller/6.22.3/) on 2026-10-28.
The observed resolved wheelhouse is the replay input; a later dependency resolution
is a new build input. Never describe version metadata as an artifact hash or license
approval. Pin a maintained supplier/security build before full runtime acceptance.

The full runtime profile is currently **disabled**, including direct spec use.
Approved strings in a manifest cannot enable it. The collection recipe records
the intended Python/ASR closure for later artifact review; it is not a runnable
full candidate. Enabling that profile requires actual prebuilt helper/host/update
artifacts, deterministic tools and exact collected-file evidence. It would also
need each named gate in `closure.GATES` approved, exact
resource/model source/version/hash/license records, all locked distribution records
and the required model/catalog/project notices. The gate rejects an incomplete
record before PyInstaller starts. The runtime collection recipe names package data/native libraries,
retains all registry-selected Python readers, and excludes sherpa from the capture
executable. ASR has a distinct Analysis, executable and `_internal` tree; workers
reset the PyInstaller environment, and ASR removes application-tree PATH entries.
No model is borrowed from a developer installation. Actual DLL isolation still
requires loaded-module and codec probes on the frozen Windows candidate.

```powershell
./scripts/build-runtime-bundle.ps1 -InputManifest <private-inputs.json> `
  -EvidenceRoot <private-evidence-directory> -Python <exact-python.exe> `
  -OutputRoot <new-output-directory>
```

The output is quarantined. `CANDIDATE-PROVENANCE.json` records every collected
file's hash/size and component source/version/license labels; complete supplied
notices are retained. This is observed provenance, not Authenticode, attestation
or legal approval. The file inventory still needs exact output/native/rights
review. `r19_complete` remains false. No release ZIP is produced. Changing source,
inputs, candidate bytes or build host invalidates affected evidence.

## Diagnostic build and host probe

A diagnostic has **no API, extraction, account, export or updater children**. It
tests bootloader execution, root/resource validation and sanitized diagnostics.
It does not require product audio/OCR/model dependencies. Its input recorder copies
the actual installed packaging notices and records exact local wheel/archive and
installed-file hashes as `observed-diagnostic`, with native/supplier/redistribution
review explicitly unverified. Those records cannot authorize a runtime build.
Supply the actual Python supplier archive that provisioned the interpreter;
an unrelated Python installer is not matching supplier evidence.

```powershell
& $Python -B packaging/runtime-bundle/record_diagnostic.py `
  --evidence <private-evidence-directory> --python-artifact <relative-archive-name> `
  --python-source <exact-https-supplier-url> --build-id <portable-build-id> `
  --output <private-inputs.json>
./scripts/build-runtime-bundle.ps1 -DiagnosticOnly -InputManifest <private-inputs.json> `
  -EvidenceRoot <private-evidence-directory> -Python $Python -OutputRoot <new-output>
```

`-DiagnosticOnly` may proceed when the application doctor returns unavailable
(exit 2), recording that outcome separately; invalid configuration/failure still
stops. The independent input gate must pass. It never converts unavailable
product prerequisites into a complete doctor or R19 pass. A hosted Windows Server
build is bootloader/synthetic evidence, not Windows 11 25H2 product acceptance.

The frozen candidate requires explicitly selected absolute environment roots:
`PROXY_TRANSCRIPT_DATA_ROOT`, `SETTINGS_ROOT`, `CACHE_ROOT`, `TOOL_ROOT`, `WORK_ROOT`,
`STATE_ROOT` and `DEFAULT_EXPORT_ROOT` (each with the same `PROXY_TRANSCRIPT_`
prefix). Keep data, tools, state and exports disjoint, with disposable cache/work
outside those roots and everything writable outside the application tree. No root
selection creates directories or copies data. For example, choose sibling data,
cache, tools, work, state and exports beneath a private temporary test root and
that parent as settings. Then run from a different CWD:

```powershell
& '<new-output>/quarantine/ProxyTranscriptRuntime/ProxyTranscriptRuntime.exe' --runtime-diagnose
```

Expected output: `mode: bundle`, `profile: diagnostic`, empty `children`,
`r19_complete: false`, `native_acceptance: unavailable`, without private paths.
Missing roots, invalid layouts and altered/missing allowlisted resources fail
actionably. Test Unicode/spaces and a read-only app tree. For a full candidate,
exercise every fixed dispatcher child and cancellation/owned cleanup against the
extracted artifact; source unit tests cannot establish frozen behavior.

## Helpers and remaining closure

See the [compiler-free helper experiment](../../docs/r19-compiler-free-helpers.md)
for exact managed/Node build inputs, fixed resource resolvers, quarantine scope and
the separate authored Windows probes. Full game-chain acceptance remains blocked
where rights, corresponding source, external DLLs or functional evidence are absent.

An independent `frontend-experiment` profile now includes only
`backend.desktop_frontend` and the closed static desktop tree. Build the frontend
with `npm run desktop:build`, then add `--frontend-root output/desktop-frontend` to
the recorder and use `-FrontendExperiment` instead of `-DiagnosticOnly`. The recorder
copies the verified tree into a fresh private evidence directory and requires its
source commit to match. Source paths beneath ignored output are never trusted as
ordinary runtime resources. The nested and outer manifests bind the same complete
frontend inventory; no mutable root is prepared at startup.

Run `ProxyTranscriptRuntime.exe --runtime-child frontend -- --port 3000` with the
explicit synthetic roots above. No Node/npm/Wrangler service is required by that
child. All application children remain unavailable in this profile. The hosted
workflow compares both source/static browser adapters, then probes the relocated
frozen host with developer PATH removed. These probes do not approve the old Python
supplier, exact collected-file redistribution, Windows 11 native behavior, update
supervision or the full runtime. Source Vinext remains the default route.

| Helper | Required treatment |
| --- | --- |
| Managed `ProxyTranscriptLauncher.exe` | Build/adapt on Windows; retain actual Framework/PowerShell requirements and source-pointer recovery. The prototype does not silently ship the old source launcher. |
| PowerShell `Add-Type` interop | Separate Windows system compilation dependency; precompile or declare and probe it. This is distinct from game SDK builds. |
| NTE/Endfield | Publish reviewed self-contained net10 helper directories on the build host, close runtime/NuGet/native notices and prove dynamic assembly/resource loading without SDK or restore. |
| PRAGMATA selective REE | Rights to modified x86 helper unresolved; no compiler or substitute all-files extraction is enabled for the user. |
| ZZZ Node/TypeScript/WASM | Prebuild app-local helper with exact Node/modules/WASM and copyleft closure; no runtime npm/transpilation hidden in the candidate. |
| FFmpeg/vgmstream/Unreal tools | Close each actual binary/archive, codec, source and native dependency independently; deterministic paths and functional probes are required. |

The old PowerShell source updater is refused by a frozen runtime before download,
setup, compilation or lock acquisition. Continuous legacy exclusion and an
owner-aware supervising update transaction need their own integrated acceptance.
Never temporarily release legacy exclusion to let a nonreentrant updater enter.
No launcher/pointer activation or existing installation migration is performed here.
