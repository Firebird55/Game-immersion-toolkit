# R19 quarantined Windows onedir prototype

The `runtime-experiment` profile now assembles the static frontend, backend,
dynamic game readers and workers, VAD resources, the owned self-contained NTE
bridge and a separate ASR native tree.
It uses the exact observed CPython 3.12.16 Windows archive in
`python-supplier.json`. `record_runtime.py` compares installed Python/wheel
payloads with their actual archives, records notices (explicitly marking
metadata-only notice evidence as incomplete), and binds the frontend and model
bytes to the clean source commit. This is a quarantined extracted experiment,
not an approved complete R19 distribution. The `runtime` production profile
remains hard-disabled. Neither credential-writing prompts nor the source updater
are enabled by the experimental child manifest.

CPython notice delivery also retains the exact supplier full archive's twenty
raw license texts and [provenance](python-notices/PROVENANCE.json). Runtime
preflight requires matching source/evidence hashes and byte lengths; finalized
THIRD_PARTY includes them. This closes notice delivery only. See the
[A2 component review](../../docs/r19-python-component-review.md) for remaining
native ownership, incorporated notices, Microsoft terms and source mappings.

On a Windows build host, provision the pinned archive and locked wheels, build
the desktop frontend and publish the owned NTE bridge from the exact pinned SDK
on that build host. Then run `record_runtime.py --evidence <private-evidence>
--frontend-root <built-desktop> --nte-helper-root <owned-nte-directory>
--codec-root <prepared-experimental-codec>
--build-id <identity> --output <private-inputs>`
and `scripts/build-runtime-bundle.ps1 -RuntimeExperiment` with its mandatory
input/evidence/Python arguments. The integrated experiment workflow performs
this preparation on GitHub-hosted Windows and uploads sanitized metadata only.
Raw executables, private receipts, native outputs and caches stay quarantined.
The exact output inventory remains a rights-review input, not an approval.

`probe-frozen-runtime.ps1` compares the relocated candidate with that complete
inventory, marks application files read-only, clears inherited developer and
credential environment variables, and selects new synthetic roots. Fixed probes
exercise actual native imports, all active registry readers, real VAD inference
on authored silence, isolated ASR imports, real index/language worker fixtures,
catalog-library export, and actual frontend/API HTTP and WebSocket routes.
The API probe mocks background updates, game discovery and OCR warmup; it never
loads real accounts or installed games. Export-worker help is narrower than
end-to-end game export. ASR model inference and native OCR/capture remain unrun.
Every passing receipt requires owned process and fixture cleanup.
The owned NTE bridge adds only a fixed read-only app-local runtime identity
operation to the frozen probe. Normal game dispatch remains blocked until its
external assembly/native chain and rights are accepted. Private Endfield/REE
builds use a distinct blocked manifest and cannot enter this collection.
The current [Xiph codec integration](../../docs/r19-frozen-xiph.md) requires its
exact prepared executable/DLL/notice/source subtree. Build-host preparation uses
scripts/prepare-runtime-codec.py --reference-root <verified-source-build> --output <fresh-directory>;
only the fixed bounded FLAC-to-PCM operation is permitted in this profile.
The reference root is produced by scripts/build-reference-codec.ps1 from the
exact source pin. Its selected Xiph executable/DLL, full notices and complete
source ZIP are verified before collection; the old wheel/binary is rejected.
See the [frozen Xiph integration](../../docs/r19-frozen-xiph.md).
Ordinary game FFmpeg remains unavailable and distribution/servicing/native gates
remain open. No imageio wrapper, package manager or runtime download is enabled.

The integrated workflow and extracted probes must actually pass before claiming
this scope. Local source tests alone cannot establish a Windows frozen build.
That scoped observation, including owned NTE collection, passed at `d6e593a` in
[Windows run 40877210344](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40877210344):
112 affected contracts, relocated native/worker/frontend/API/WS/Setup probes,
complete pre/post file and directory inventory, and owned cleanup. The downloaded
metadata ZIP and its source/build/inventory identities were independently checked;
all redistribution/native Windows 11 acceptance gates remain pending. See the
[R19 evidence](../../docs/r19-runtime-bundle.md#integrated-owned-nte-bridge)
for exact digests and unrun scopes. No binary or installer was published.

This directory defines a Windows x64 PyInstaller **onedir** build of the existing
Python runtime. It does not release, tag, install, alter Pages, acquire games or
write accounts. R19 remains incomplete: no clean Windows 11 25H2 acceptance,
maintained Python binary supplier decision, complete collected-file license/native
closure, complete compiler-free game toolchains or supervised frozen update has
been established. Static frontend and authored helper experiments have separately
scoped evidence; they do not approve the full runtime. Source adapters remain available.

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
| NTE | Owned self-contained bridge is collected with exact identity; authored reflection protocol passed. Actual external assemblies/native rights and game loading remain open. |
| Endfield | Actual self-contained reader passed bounded empty/malformed probes in private blocked quarantine; constants/provenance/format/rights gates prevent collection. |
| PRAGMATA selective REE | Actual precompiled x86 reader passed authored selection/rejection probes in private blocked quarantine. Modified helper/native rights and clean Windows 11 acceptance remain unresolved. |
| ZZZ Node/TypeScript/WASM | Prebuild app-local helper with exact Node/modules/WASM and copyleft closure; no runtime npm/transpilation hidden in the candidate. |
| FFmpeg/vgmstream/Unreal tools | Close each actual binary/archive, codec, source and native dependency independently; deterministic paths and functional probes are required. |

The old PowerShell source updater is refused by a frozen runtime before download,
setup, compilation or lock acquisition. Continuous legacy exclusion and an
owner-aware supervising update transaction need their own integrated acceptance.
Never temporarily release legacy exclusion to let a nonreentrant updater enter.
No launcher/pointer activation or existing installation migration is performed here.
