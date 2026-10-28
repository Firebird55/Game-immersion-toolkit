# R19 compiler-free helper boundary

Status: **active experiment; game toolchains and full R19 acceptance incomplete**.
This phase follows the [static frontend checkpoint](r19-host-experiment.md#explicit-static-desktop-adapter).
PR #59, the source adapter, every game/language choice and protected user data stay
in place. No installer, release, tag, Pages deployment or production activation is
part of this work. Build tools below run on a build host, not on the user's PC.

## Implemented boundaries and gates

| Helper | Implemented direction | Remaining gate |
| --- | --- | --- |
| Authored .NET probe | Fixed JSON stdin/stdout operation, self-contained `win-x64` directory, app-local runtime/resource identity and hash-bound inventory | Actual hosted execution and exact-output/runtime/native review; this probe authorizes no game |
| Owned NTE bridge | Self-contained publishing of the existing reflection bridge, with no trimming or single-file extraction; frozen source identity comes from verified resources | UEExtractor dynamic assembly/native dependency closure, Oodle rights and functional installed-game evidence; bridge publishing cannot authorize execution |
| Endfield | Frozen preparation refuses SDK/download/restore before reaching the source adapter | Selected upstream `Keys.cs` contains unreviewed game-derived constants; no Endfield artifact is collected |
| Authored Node probe | Exact app-local Node, module worker and authored WASM; absolute immutable entry/resource paths and private work | Hosted Windows execution and exact runtime/native/notices review; no real ZZZ extraction claim |
| ZZZ production reader | Separate build-only quarantine preparation with pinned source/module inputs; frozen production dispatch remains blocked | GPL/corresponding-source obligations, upstream custom terms, game-derived metadata and actual reader/codec probes |
| PRAGMATA selective REE | Existing frozen refusal retained | Modified x86 helper redistribution rights, prebuilt artifact and WOW64/native evidence |

The game resolvers never interpret an `approved` string, an authored probe or a
successful build as permission to run an incomplete game chain. Missing, changed,
unlisted, linked, wrong-platform or incompatible resources fail with an actionable
unavailable state. They do not discover an SDK/compiler/npm through PATH or start
a download on the frozen PC. The existing source SDK/TypeScript adapters remain
separate and retain their established behavior.

These boundaries do not claim that the launcher/PowerShell `Add-Type` path is
compiler-free. Its exact Framework/compiler requirements and precompiled host
replacement remain separate host/R20 work. The full runtime profile stays disabled.

## Managed build inputs

The dated observation in `packaging/game-readers/inputs.json` records exact
Microsoft release metadata, SDK **10.0.403**, runtime **10.0.14**, Windows x64 SDK
archive SHA-512 and the two exact runtime/host NuGet package SHA-512 values. The
build checks the selected SDK instead of accepting an arbitrary caller version.
Runtime and host packs are acquired and hash-checked on the build host; restore
uses an isolated cache and a local feed with remote/default sources cleared.
Restore locks and actual complete notices/receipt files belong to the output
inventory. Package license labels alone do not establish collected-file approval.

Use `scripts/build-game-reader-helpers.ps1 -Kind probe` or `-Kind nte` with a fresh
ignored output slot, the exact expanded SDK executable and its private evidence
directory. `endfield` is deliberately unavailable. No upstream game DLL, game
constant, account blob, recording or proprietary OCR/Decima file enters these
owned helper outputs. The NTE bridge is quarantined and is not executed on a game.

The probe checks its CoreLib origin under its own application directory and
reports logical runtime identity rather than a private path. Its authored resource
has fixed UTF-8 bytes. Malformed input and a missing/changed resource return distinct
nonzero statuses. It performs no filesystem writes or network/account operations.

## App-local Node inputs

The observed Node **24.22.1** Windows x64 archive and executable are pinned to the
official release and `SHASUMS256.txt`; complete archive LICENSE bytes are retained.
The build-only helper script uses a supplied matching archive. The fixed authored
probe exercises worker startup, actual WASM execution and Chinese JSON data using
that bundled runtime from an unrelated CWD. It clears inherited runtime options,
module search paths and developer-tool PATH rather than borrowing the build host's
Node executable. Production ZZZ preparation has a distinct blocked receipt and
cannot be selected as an authored probe.

## Evidence boundary

The dedicated `R19 compiler-free authored helper probes` workflow runs on hosted
Windows Server 2025. It downloads only the exact public build inputs, publishes
the owned managed probe/bridge and executes authored helper fixtures. The managed
probe runs with absent system `DOTNET_ROOT`, no SDK/compiler discovery, read-only
application files and before/after tree hashes. The Node probe uses its app-local
runtime with no system Node/npm/TypeScript dependency. Passing metadata is written
only after owned process and temporary-root cleanup succeeds.

Only sanitized versions, hashes, statuses and scope are uploaded. Executables,
SDKs, runtime caches, raw logs, game files and private receipts stay out of artifacts.
Windows Server evidence cannot establish Windows 11 25H2 OCR/capture/DPI, installed
voice playback, complete loaded-DLL/CRT closure or clean real-user acceptance.
Native Windows gates remain explicit; `r19_complete` stays false.

## Local checks before hosted execution

The combined affected Python selection passed **202 cases** on task-local Python
3.12.13. Five Node helper tests, typecheck, workflow YAML parsing, documentation and
public audit passed. Reciprocal reviews corrected raw-link roots, SDK extra-file
acceptance, loader environment inheritance, noncanonical private-work paths and
source-dirty evidence. A composition fixture was updated to inject bundle mode at
both actual gate owners while keeping its forbidden SDK/download assertions.

The real exact-archive macOS ARM64 Node 24.22.1 probe passed worker/WASM execution,
Chinese JSON preservation, app-local `execPath`, unchanged application files and
owned cleanup. It reports `source_dirty: true` because it observed the working
implementation before commit. It is local protocol evidence, not a clean-commit or
Windows result. Actual pinned upstream/npm inputs also produced the separate
blocked quarantine with both immutable extractor adaptations; upstream game code
was syntax-checked without execution or game access.

`check:changed -- --base upstream/main` record
`83504b43-5cf0-4f9d-af63-5194cb56a10d` remains **failed** with available unchanged
source/base evidence. Typecheck and 271 Node tests passed (one skipped); Python
collection then failed because macOS lacks `pyaudiowpatch`. Later aggregate commands
were not run. Native managed compilation and PowerShell execution are unavailable
on this development host and must be established by the hosted helper jobs.

The first [Windows helper run](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40765389636)
at `8c8a4e9` passed the actual app-local Node probe on Server 2025 build 26100.
It recorded clean source, Node 24.22.1, worker/WASM/Chinese JSON, no application
writes and confirmed cleanup. Downloaded metadata artifact `12850650842` matched
GitHub's ZIP SHA-256
`b642cf95b3a72e05fa3549ecedc5e6e242f2ac53431eaf87bba432bee058bbfb`.
Its source identity, clean flag and authored-only/incomplete acceptance scope were
checked after download. No runtime binary was uploaded.

The managed job in that run failed safely during offline restore: SDK transitive
framework discovery requested unused Windows Desktop and ASP.NET runtime packs
absent from the deliberately restricted local feed. The build now disables those
transitive framework-reference downloads for the two console helpers, retaining
their actual Microsoft.NETCore.App reference and the same two pinned package
inputs. It does not enable a remote/default feed or add unreviewed frameworks.
The failed run supplies no managed execution pass; the affected job must be repeated.
