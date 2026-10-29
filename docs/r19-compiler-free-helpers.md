# R19 compiler-free helper boundary

Status: **active experiment; game toolchains and full R19 acceptance incomplete**.
This phase follows the [static frontend checkpoint](r19-host-experiment.md#explicit-static-desktop-adapter).
PR #59, the source adapter, every game/language choice and protected user data stay
in place. No installer, release, tag, Pages deployment or production activation is
part of this work. Build tools below run on a build host, not on the user's PC.

## Implemented boundaries and gates

| Helper | Implemented direction | Remaining gate |
| --- | --- | --- |
| Authored .NET probe | Fixed JSON stdin/stdout operation, self-contained `win-x64` directory, app-local runtime/resource identity and hash-bound inventory; hosted Server probe passed | Exact-output/runtime/native Windows 11 review; this probe authorizes no game |
| Owned NTE bridge | Collected self-contained bridge with exact source/resource identity; app-local runtime and actual reflection/protocol fixture passed on Server 2025 | Actual UEExtractor/CUE4Parse/native dependency closure, Oodle rights and installed-game evidence; authored stand-ins cannot approve that chain |
| Endfield | Actual selected reader prebuilt in separate blocked quarantine; app-local runtime/hashing and empty/malformed-input probes passed | Embedded game constants, file-level port provenance, real VFS/audio and Windows 11 acceptance; no Endfield artifact is collected |
| Authored Node probe | Exact app-local Node, module worker and authored WASM; absolute immutable entry/resource paths and private work; hosted Server probe passed | Exact runtime/native/notices and Windows 11 review; no real ZZZ extraction claim |
| ZZZ production reader | Separate build-only quarantine preparation with pinned source/module inputs; frozen production dispatch remains blocked | GPL/corresponding-source obligations, upstream custom terms, game-derived metadata and actual reader/codec probes |
| PRAGMATA selective REE | Actual modified x86 helper precompiled in blocked quarantine; authored uncompressed PAK selection and oversized-table rejection passed | Modified helper/native redistribution, compressed/encrypted formats, clean Windows 11 WOW64/Framework and installed-game evidence; frozen dispatch stays blocked |

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

### Owned NTE bridge continuation (2026-10-29)

The integrated runtime now requires the owned self-contained NTE bridge as a
closed `helpers/nte` resource subtree. Its manifest, build receipt, exact current
source inputs, runtime files and notices are checked before collection. External
UEExtractor/CUE4Parse/Oodle files are rejected from that owned subtree. A fixed
read-only `--runtime-identity` operation reports app-local CoreLib identity;
normal game dispatch stays blocked independently of receipt approval strings.

The new Windows probe compiles two authored reflection stand-ins on the build
host, then runs the actual owned bridge's inventory, localization, subtitle,
bank/media, single-voice and batch-voice paths with developer discovery removed.
It selects all four voice-language identifiers and five authored text locales,
checks missing dependencies and unsupported localization version rejection, and
keeps application/tool/install trees unchanged. The stand-ins contain no actual
UEExtractor, CUE4Parse, Oodle or game data; their JSON payload is not a real locres
format fixture. This tests reflection/protocol and compiler-free execution only.
The exact Windows execution and downloaded metadata are recorded below.

NTE outputs must also stay outside the immutable helper/tool trees. The source
adapter retains its established SDK build path; no live game or user state is
used by these probes. The integrated frozen probe will execute only the owned
bridge's runtime identity operation, never an unapproved game chain.

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
directory. `endfield` is unavailable to the runtime; its explicit blocked build
mode is described below. No upstream game DLL, game constant, account blob,
recording or proprietary OCR/Decima file enters these owned helper outputs.
The NTE bridge is quarantined and is not executed on a game.

The probe checks its CoreLib origin under its own application directory and
reports logical runtime identity rather than a private path. Its authored resource
has fixed UTF-8 bytes. Malformed input and a missing/changed resource return distinct
nonzero statuses. It performs no filesystem writes or network/account operations.

## Private real-reader preparation (2026-10-29)

Endfield's actual selected 14-file source subset can now be prepared and
self-contained-published on a Windows build host with explicit
`-Kind endfield -BlockedQuarantine -PreparedRoot <private-source-root>`.
The build rehashes every selected source before/after compilation, rejects
unlisted sources, restores from a closed local feed and retains the exact replayed
lock and complete available notices. System.IO.Hashing **9.0.0** is separately
pinned to its official NuGet catalog SHA-512. The selected implementation's MIT
notice does not establish publisher rights to embedded constants or resolve
file-level port provenance. Its assembly remains private and unapproved.

The actual modified selective REE reader is separately precompiled as x86 using
the build host's publisher-verified Windows Framework compiler. The exact source
and native/reference ZIP hashes are retained. An adapter permits private project
lists outside the immutable helper directory; dependency checks use its absolute
application directory. The original source SDK adapter is unchanged. The authored
uncompressed PAK fixture contains independently generated
path hashes, one requested and one unrequested resource, plus an oversized header.
This exercises real selection and rejection, not a stock all-files unpacker.

Both preparations emit a **different blocked manifest schema**, no runtime
entrypoints, and `runtime_collection_allowed: false`. Frozen readers and the
runtime collector cannot accept those artifacts as owned NTE helpers. No binary,
selected source, embedded constant, archive cache, raw compiler log or game input
is uploaded. Only sanitized execution metadata may leave the runner. Compiler
failures disclose diagnostic codes without source excerpts or constant values.

The private Windows job is bounded to 25 minutes per distinct reader, with no
browser/full-suite expansion. Endfield's probe checks actual app-local CoreLib
and hashing identities, empty-pack behavior for all four voice choices and
malformed/missing-voice rejection. It does not prove actual encrypted VFS/audio
formats. REE's probe checks actual x86 execution with cleared developer environment
on the authored uncompressed PAK; compression/encryption, WOW64/Framework on clean
Windows 11 and installed-game playback remain separate gates. The local source
preparation verified all 14 Endfield files and 17 adapted REE files; 85 affected
pure contracts passed.

The selected REE commit has no established license grant in an accessible
`LICENSE` file; its README documents Framework 4.7.2/build prerequisites but is
not treated as a redistribution license. Third-party native/source obligations
remain unapproved. This work does not close that gate or approve shipping it.

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

## Continued Windows evidence (2026-10-29)

[Helper run 40882378706](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40882378706)
passed both jobs at clean `a72c703dbb592b9ba4f6b701d1b1911715f7948c`.
The actual NTE bridge passed `inventory`, `index`, `voice` and `voices` with
authored reflected assemblies, all four voice-language identifiers and five
text locales. Its runtime identity reports app-local **10.0.14** CoreLib.
Malformed inputs, absent dependencies and unsupported localization version
were rejected, immutable trees were unchanged and owned cleanup passed.
This is an actual bridge/protocol execution pass, not a real locres parser,
UEExtractor/CUE4Parse/Oodle or installed-game pass. The independent managed and
Node probes also passed within their existing authored scopes.

[Private reader run 40882378766](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40882378766)
passed both actual precompiled readers at that same clean source. Endfield
confirmed app-local CoreLib **10.0.14** and the exact System.IO.Hashing DLL,
empty-pack inventory for all four voice choices and malformed/missing-voice
rejection. PRAGMATA confirmed x86 execution, exact requested resource bytes,
skipping the unrequested resource and rejecting an oversized PAK table.
Both cleared inherited developer/loader/account variables, retained unchanged
application/input trees and confirmed cleanup. Their receipts retain
`runtime_collection_allowed: false`, `game_execution_approved: false`,
`redistribution_review: not-established`, open embedded-constant review and
unavailable native Windows 11 acceptance. No real game or account was accessed.

Downloaded metadata ZIPs matched GitHub's published SHA-256 digests. Their exact
clean source identity, scope, successful status/cleanup and incomplete acceptance
fields were checked independently. The metadata ZIPs contain no private binaries
or selected upstream source; binary hashes remain runner observations.

| Metadata artifact | ZIP SHA-256 |
| --- | --- |
| Managed/NTE `12900463381` | `0b2a1469bf64cab6ac206a7512204a1cc7051e8803a677a5a903b87259455fa9` |
| Endfield `12901146838` | `f23d344815f38ee9f1435a5541f4cd6d032f1fcf92cc9a096c9b6fc85b5ebd94` |
| PRAGMATA `12901146607` | `650f0b3a5659c6b00ef004f5bc5739e6f1b957f7e490e14b9beba303286d8996` |

The preceding private-reader run `40877210584` built both helpers and passed
Endfield, but PRAGMATA failed its first extraction because upstream checked for
reference DLLs relative to the unrelated working directory. The private adapter
now resolves those checks from the immutable application directory and retains
the exact Framework configuration. The corrected actual fixture passed above;
no selection, rejection or output assertion was relaxed.

The [frontend/stdlib/protected-TEST run 40882378852](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40882378852)
also passed all three jobs at `a72c703`. An earlier frontend comparison at
`d6e593a` failed the existing 1.8% pixel criterion in `40877210472`; the failed
job passed on an unchanged repeat, with no threshold, retry or assertion change.
That failure remains part of the evidence. Integrated collection and runtime
identity passed separately at `d6e593a` with **112 affected contracts**; exact
inventory and receipt evidence are in the
[runtime observation](r19-runtime-bundle.md#integrated-owned-nte-bridge).
The subsequent REE-only correction did not change that runtime or NTE builder.

Local affected pure contracts passed **85 tests**. Stable-source aggregate
`check:changed -- --base upstream/main` record
`9eeb2302-38b4-4f27-8b3c-dfd895b3fc95` remains **failed/incomplete**: typecheck
and 271 Node tests passed (one skipped), then collection lacked macOS
`pyaudiowpatch`; later aggregate commands did not run. Workflow parsing,
documentation links, public audit and diff checks passed separately. The public
compatibility watch returned 2 on 2026-10-29 for docs/UI changes with no endpoint
additions/removals; its baseline remains unchanged pending full lookup/UI review.
No full source/browser/package pass is claimed for this helper commit; the
previous full candidate retains its exact source identity in the runtime report.

## Earlier local and hosted checks

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

The next run at `74c5a2c` successfully restored, replayed the lock and published
the actual self-contained authored probe. Its second bridge build then rejected
SDK state added by the first build. Each helper now starts from a fresh expansion
of the same verified SDK archive; no exception weakens the supplier-tree check.
Compilation intermediates and regular build output are redirected to private
evidence storage, and shared compiler-server reuse is disabled. Actual probe
execution is a separate step before the optional owned bridge build; a passing
metadata file can describe only that independently completed scope.

The final [helper run 40768109512](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40768109512)
passed both jobs at exact clean commit
`d297b4224002e85e20aa7db0e3469ab9c109135a`. The actual managed probe ran with
developer PATH removed, absent system `DOTNET_ROOT`, stripped loader hooks,
read-only application files, app-local CoreLib/runtime **10.0.14**, rejected malformed
input/missing resource, no observed application writes and confirmed cleanup.
The separate NTE bridge then published successfully from a fresh exact SDK
expansion. It was not executed on a game and contains no UEExtractor/Oodle chain.
The Node job independently passed its actual worker/WASM/Chinese JSON protocol with
app-local **24.22.1**, no inherited loader flags and confirmed cleanup.

Downloaded metadata artifacts were checked against GitHub's ZIP digests and then
for exact clean source identity, success, cleanup and incomplete game/full-runtime
scope:

| Artifact | ZIP SHA-256 |
| --- | --- |
| Managed `12852275531` | `244793f304476dffc7558e2c52588a966cc4e796d067b04dde3dc30b7c76da87` |
| Node `12850219886` | `cde8c34953c2afc81b9a74d930b6b0dcd6351d522d0f7cc3fba5a0ed9ac90658` |

Only metadata was downloaded/uploaded. This proves the stated authored helper and
owned bridge build scopes on Server 2025, not independently downloaded binaries,
game extraction, closed redistribution obligations or native Windows 11 acceptance.
