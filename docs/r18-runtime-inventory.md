# R18 — Runtime inventory and R19 prototype decision

Status: **completed research and design contract**, reviewed on 2026-10-28.
This delivers R18 and the storage/host design portion of R12c. It does not
implement R14, runtime adapters, R19's bundle or R20's installer, and establishes
no native Windows, installed-game, physical-mobile or performance validation.

## Scope and evidence

The baseline is toolkit **0.21.3**, freshly fetched `upstream/main`, commit
`4a4abfcee8d4fa87a8bfacdae12b6cef5284cad9`, targeting
`Firebird55/Game-immersion-toolkit:main`. Work belongs to
`codex/r18-runtime-inventory`; the original checkout and local application data
are outside this change. Two GPT-6.1 Sol agents, both using xhigh reasoning,
research components and storage/hosting respectively, then review each other's
actual documents. The integrator reviews the combined contract and source.

The deliverables are:

- [Component and redistribution inventory](r18-runtime-components.md): runtime,
  Python/native/JavaScript dependencies, every active game's tools, Windows
  requirements and bundle/download/prerequisite decisions.
- [Storage and host contract](r18-storage-host-contract.md): current ownership,
  proposed layout, source/bundle adapters, origins, update handoff and recovery.
- This decision, R19 acceptance plan and unresolved-work ledger, linked from the
  [roadmap](rework-roadmap.md).

Source references describe this baseline. Official sources are dated in the
component/host inventories; their upstream claims are distinguished from a
toolkit integration test. A dependency's top-level license, a downloaded tool's
checksum, or a successful import alone proves neither redistribution closure
nor functional compatibility.

## Prototype decision

Proceed in R19 with a **Windows x64 PyInstaller one-directory prototype of the
existing Python runtime**. Build it on Windows with the selected Python 3.12
patch and pinned packaging tools; do not cross-build a Windows release on this
macOS research host. One directory makes collected resources and DLLs inspectable
and supports side-by-side versions without one-file extraction. PyInstaller
collects the interpreter, but dynamic imports and resources still need explicit
collection ([official operating model](https://pyinstaller.org/en/stable/operating-mode.html),
reviewed 2026-10-28). Its bundling exception does not grant rights to dependencies
([license](https://pyinstaller.org/en/stable/license.html)). Exact packaging pins
and artifact hashes are R19 inputs, not fabricated R18 measurements.

Keep the ordinary browser, existing FastAPI/capture implementation and current
reader modes. Introduce only the resource/storage/process composition needed
by the [host contract](r18-storage-host-contract.md); no OCR rewrite, generic
plugin framework, new webview or Rust/C# replacement is required. Preserve the
Job Object and publication/cancellation contracts in
[runtime context](runtime-context.md).

R19 also runs a bounded **local static-frontend equivalence experiment**. The
current Vinext/server output cannot simply be copied into a static file server.
Prove the desktop routes, hydration, assets and browser behavior first. Retain
`http://127.0.0.1:3000` for the desktop browser and the current API/WebSocket
public address at `127.0.0.1:8766`, including their existing access controls.
Private candidate ports are implementation details and must not become saved
browser origins. Mobile Pages keeps its separate established origin and asset
allowlist. Static hosting here means local desktop asset serving, not moving
desktop services or user data onto Pages.

The experiment's preferred result is static assets served by the local frozen
host/router without an end-user Node/npm/Wrangler installation. If equivalence
fails, retain the existing frontend host during investigation. A diagnostic
bundle that still needs the current external Node/npm/Wrangler setup is useful
evidence but **does not pass R19's no-development-environment gate**.
An app-local Node runtime for the separate ZZZ helper is allowed only under the
component inventory's license/functional gates. A proposal to ship an embedded
Node frontend/router host instead requires a recorded reason,
exact binary/license inventory and the same clean-machine/origin probes before
changing this decision. A source checkout remains supported through its current
adapter throughout; a failed experiment must not break it.

R20 may prototype per-user Inno Setup only after R19 establishes an acceptable
runtime. Inno's `PrivilegesRequired=lowest` provides the intended unelevated
mode ([official directive](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm),
reviewed 2026-10-28); R18 neither writes an installer nor proves that all selected
prerequisites can be acquired without elevation.

## Distribution rules

The component inventory is normative for each **bundle**, **separate download**
or **system prerequisite** decision. Apply these common rules:

1. Bundle original runtime code, the interpreter, selected locked Python/native
   dependencies and prebuilt frontend assets only after exact artifact and
   notice review. Keep development/test/compiler packages on the build host.
2. Download selected game tools separately where specified; record upstream
   URL/release or source revision, SHA-256, architecture, full notices, native
   closure and failure guidance. Downloads need an explicit user action and
   must be resumable/retryable without changing game files or deleting indexes.
   Separate acquisition does not settle copyleft obligations or grant missing
   redistribution rights. Unknown or incompatible terms block that component.
3. Treat Snipping Tool and its proprietary OCR DLL/model files as a user-owned
   system prerequisite. They must never enter an artifact, fixture, public cache
   or installer. Local initialization/repair still needs Windows evidence.
4. The user supplies installed games and official voice packs. Downloading a
   runtime tool never authorizes distribution of extracted text/audio, game
   decompression DLLs, metadata, private paths or account diagnostics.
5. The R19 acceptance target has no preinstalled Python, pip, Node, npm, Wrangler,
   Git, .NET SDK, separately installed C# toolchain or Visual Studio Build Tools.
   Current source setup still needs several of these. Publish/build reviewed
   self-contained helpers or carry a licensed runtime through the selected
   component's bundle/download policy. If a game-reader route still invokes a
   compiler/SDK, report that game/toolchain as blocked; do not hide it or weaken
   the acceptance target.
   The current PowerShell launcher's `Add-Type` compiles owned C# interop using
   Windows facilities. Prefer a precompiled owned helper for R19; if that source
   adapter is retained, declare and probe the exact PowerShell/Framework system
   dependency. An unchanged launcher is not evidence of zero runtime compilation.
   Setup separately compiles `ProxyTranscriptLauncher.exe` with Framework
   `csc.exe`; prebuild any retained managed wrapper on the Windows build host
   and adapt its source-path dispatch before including it in R19/R20.
6. Produce a runtime file manifest and complete notices for shipped artifacts,
   including transitive DLLs, models, fonts, WASM and external executables.
   Existing npm notice generation is a starting point, not a Python/native SBOM.
   Keep the project's custom attribution license separate from third-party terms.

## R19 acceptance plan

R19 owns an extracted **runtime candidate**, not an installed product. Before
building, freeze its source commit, tool/model/input digests, minimum Windows
image and preselected R02b measurement method. Use one reproducible artifact
through the functional probes; changing it invalidates affected evidence.
Reuse existing checks below and add only missing bundle-specific behavior tests.

| Probe | Independent success criterion | Failure/recovery evidence |
| --- | --- | --- |
| Clean host and architecture | Ordinary Windows x64 user starts the extracted candidate without development tools; declared OS/browser/Store/VC runtime conditions are checked and actionable | Missing prerequisite, wrong architecture, restricted Store, offline first start and insufficient space name the failing component; no partial ready state |
| Resources and child processes | Start from a path with spaces/Unicode and an unrelated working directory; immutable app tree is not written; retained prebuilt wrapper and all API, language, export, update and bootstrap children use the intended frozen entrypoints | No recursive bootloader launch, missing `.py` path, stale project pointer or hidden compiler dependency; inspect native DLL search isolation; later R20/R21 prove the actual installed shortcut transaction |
| Native OCR and capture | On declared Windows build, initialize the user's Snipping Tool OCR, read an authored Chinese and non-Chinese caption, select a window/monitor and verify crop bounds at relevant 125–200% DPI | Missing/stale OCR assets, unavailable capture surface, multiple monitors, negative display coordinates and capture permissions produce actionable states; confirmed transcript survives audio failure |
| Distinct game toolchains | Exercise every distinct chain in the component inventory on the extracted artifact, including PRAGMATA x86 helper on x64, Unreal/.NET helpers, Unity readers, CRI/Wwise/FFmpeg/vgmstream paths and pure-Python archive paths | Tool absent/corrupt/wrong architecture, unsupported game format, absent voice pack and interrupted extraction retain the previous complete index; no fallback to the wrong spoken language |
| Actual-format integration | Synthetic permitted archives/owned audio exercise real tool subprocesses and output parsing; separately record installed-game/locale probes where private inputs are available | Mocked process success proves orchestration only. Missing real game or voice packs remain unavailable for native playback; no archived game is re-enabled |
| Host and ordinary browser | Built desktop routes, CSS/fonts, setup, lookup, both reader modes, audio/export, API errors and WebSocket reconnect work in Chromium and Firefox at the retained origin and existing selected profile | Distinguish current Chrome-only auto-open from manual browser use; no fresh-profile data/extension loss, removed endpoint, permissive CORS/Host fallback, public listener or hidden development server; real extension compatibility is separately recorded |
| Static/mobile assets and caches | Desktop static spike meets route/hydration equivalence; packaged mobile preview retains workers/WASM/model URLs and existing allowlist/offline behavior | Service-worker scope, old/current cache activation, failed asset load and offline reopen retain browser stores; desktop assets are not assumed to share the mobile service worker |
| Data and origin | Opt-in old-ZIP copy migration preserves synthetic transcripts/favorites/settings/locales/archived data, export ledgers, grammar choices and export-volume work/complete previous libraries; same-user protected test credentials, IndexedDB registries and OPFS bytes remain usable | Copy interruption, locked SQLite/WAL files, no space, malformed manifest and unknown schema preserve originals; unreadable named credentials require an explicit preserving repair design, not the existing add-account prompt; a folder/registry copy alone is not browser/library migration |
| Update and rollback | Candidate verification, standby, readiness/warmup, bounded quiesce and takeover retain at most one capture owner; owner-aware updates work while the legacy migration guard remains held; previous compatible runtime can restart | Inject nested-lock/update contention, checksum/provenance failure, preparation crash, quiesce timeout, router/candidate failure and interruption at checkpoints; never briefly release exclusion, copy DPAPI across users or silently downgrade data |
| Baseline and delivery evidence | R02b records cold/warm start, CPU/RSS, sizes, disk peak and recovery for the same artifact and environment; compare to measured current runtime | Unavailable measurements remain open; no speed or size promise invented from PyInstaller choice. Checksums/provenance, signatures and attestations are reported separately |

The probes cover **toolchains**, plus selected language/voice bindings; they do
not demand every game × language × browser × DPI combination. Keep a per-game
mapping so a shared-chain pass does not conceal a game's different archive or
voice path. Native game probes use owned installations on the tester's PC;
public hosted checks use authored archives, catalogs and owned audio only.

Existing source checks to reuse include
[game tools](../backend/tests/test_game_tools.py),
[local access](../backend/tests/test_local_access.py),
[runtime handoff](../backend/tests/test_runtime_handoff.py),
[preparation process cleanup](../backend/tests/test_preparation_process_tree.py),
[Windows drain](../backend/tests/test_windows_preparation_drain.py),
[toolkit update verification](../backend/tests/test_toolkit_update.py),
[updater scenario](../scripts/update-companion-e2e.mjs),
[setup](../scripts/setup-e2e.ps1),
[browser storage update](../scripts/mobile-update-e2e.mjs) and
[publication boundaries](../tests/mobile-publication.test.mjs).
They must also run against the relevant extracted candidate paths; source tests
alone do not prove frozen execution. Existing package validation currently tests
the source-style ZIP, not this proposed runtime artifact. Full browser/package
validation belongs to the GitHub-hosted candidate/release gate; native capture,
OCR and physical-device evidence remain explicit independent work.

## Open points and ownership

These uncertainties do not prevent completing an evidence-based inventory. They
do prevent claiming that a redistributable, standalone R19 candidate already works.

| Open point | Owner and closure |
| --- | --- |
| Exact Python/native/WASM/codec/tool license closure, notably GPL dependencies, external decompression libraries and FFmpeg build configuration | R19 packaging owner: audit exact files and corresponding-source obligations; no unknown binary enters the shipped set |
| Maintained Windows Python 3.12 binary and packaging version pins | R19 build owner: record patch/source/build provenance, incorporated library notices and security-update policy; do not equate an old official installer with a current security build |
| Compiler-free NTE/Endfield/PRAGMATA and other .NET/external helper paths | R19 packaging owner: publish/build licensed helpers with complete architecture/runtime dependencies, then functional probes without SDK/Build Tools |
| Static desktop equivalence and replacement of the Node router/host | R19 host owner: prove preserved origins/API/WS/readiness; retain diagnostic source adapter if unsuccessful, explicitly incomplete acceptance |
| Frozen module dispatch, prebuilt launcher/pointer transition, data/resource paths and native loader isolation | R19 runtime owner: implement only required composition adapters and probe each child path; R20/R21 prove installed launch entries |
| Native Windows baseline, OCR files/build compatibility, CPU/GPU/DPI and installed-game evidence | R02b/R19 tester: name image, hardware, candidate and selected games/locales; missing inputs stay unavailable |
| Physical pack/candidate/preference schema and shared setup consumer adoption | R14/R17 owners: adopt this R12c storage/host boundary; this research does not implement their services |
| Existing ZIP/browser data, guarded updates and schema downgrade recovery | R19 proves bounded opt-in copy, continuous legacy exclusion with owner-aware update coordination and existing browser/profile continuity; R20/R21 prove installed migration, pointer/shortcut recovery, unreadable named-store repair and retained export-volume work. Keep old runtime/data until verified |
| Signing, full downloaded candidate verification and installed-product acceptance | R20–R22: existing clean-main release process and GitHub-hosted checks; checksums/JSON provenance alone do not establish Authenticode or attestation |

## Review and validation record

Both agents reviewed the other's actual document against source and official
references, including completeness, licenses, overlooked toolchains and migration
risks. The integrator reviewed the combined documents and roadmap. Findings
incorporated before the final re-review include:

| Review finding | Correction |
| --- | --- |
| A cache filename concealed durable state; browser registry was incomplete migration evidence | Preserve `grammar_choices` in the reading database and OPFS retained-library bytes as well as IndexedDB records |
| Frozen launch could recurse or mix incompatible ONNX libraries | Enumerate language/export/updater/bootstrap and optional ASR/fingerprint children; retain ASR process/DLL isolation and reject developer-file fallbacks for bundled models |
| New-root locking did not exclude an old ZIP launcher | Specify legacy-operation lock then target lease, lifetime exclusion and crash recovery; block migration activation until this is actually proved |
| Resources outside `data` and old frontend chunks could be lost | Name ZZZ tool/work roots and protected NTE metadata; retain compatibility assets for active/open-reader/rollback use; distinguish source-root legacy mapping from new target roots |
| Dependency labels obscured compiler, runtime and redistribution differences | Distinguish SDK/runtime/self-contained .NET, x86 PRAGMATA, launcher `Add-Type`, app-local ZZZ Node helper and conditional frontend-host alternative; keep unknown/GPL/native artifact closure open |
| Inventory count and Windows baseline needed correction | Verify 49 Python lock entries, 462 npm entries and 283 absent npm license fields; select a serviced Windows 11 25H2 x64 acceptance image without claiming it was run |

A further adversarial double-check of commit `cd8b403` on 2026-10-28 found and
corrected additional documentation gaps: the separate Framework-compiled managed
wrapper; its project pointer/Start menu transition; current Chrome-only opening
and browser-profile continuity; nested updater acquisition of the proposed
lifetime migration lock; export-volume work containing complete previous
libraries; and the existing prompt's inability to repair an unreadable named
account store. The component reviewer rechecked all 66 GitHub source links and
all 49 Python lock names/versions. These corrections specify missing R19–R21
adapters/probes; they implement none of them and grant no new redistribution
rights. The corrected diff receives another review and scoped check before commit.

Local validation is limited to this documentation change on macOS with Node
22.22.2/npm 10.9.7. The scoped doctor passes the package engine/lock checks and
reports CI's recommended Node 24 as an optional version difference. Delivery
checks use `npm run check:changed -- --base upstream/main` (generated-guide/local
link checks and publication audit), plus `git diff --check`. New documents are
staged before link checks. The final delivery reports the completed evidence
record against the committed source. No new runtime tests, bundle build,
installer, native capture/OCR or game/account operations are part of R18.

The read-only `npm run lexirise:watch` returned **exit 2: review advisory** on
2026-10-28: public documentation/UI hashes changed, with no endpoint additions or
removals. The sandbox's first attempt failed DNS; the normal permission-approved
network retry obtained the report. Inspection covered the public
[API/AI reference](https://lexirise.app/api-reference), partial/global versus
per-language settings, lookup tabs/definition sections and portal code, and
reading-aid/translation/interface-language handling. This is bounded inspection,
not a full shared-component compatibility pass; no account call or baseline
update was made. Keep the advisory and full compatibility work open separately
from R18. Check evidence lives in ignored `output/checks`; private raw logs,
downloaded review bundles and absolute profile paths stay out of Git.

Rollback of R18 is a documentation commit revert. It has no data/schema or
runtime effect. R19 must implement and verify the recovery contract before
switching any existing installation to a bundle.
