# R19 — Windows runtime-bundle prototype

Status: **active implementation; full R19 acceptance incomplete**. This task
starts from R18 commit `8369c9534762cd2232fb44424772bd6b5a72b6d2` on
`codex/r19-runtime-bundle`. The dependency remains [PR #59](https://github.com/Firebird55/Game-immersion-toolkit/pull/59).
It is not changed or merged by this work. The actual target is
`Firebird55/Game-immersion-toolkit:main`; freshly fetched `upstream/main` was
`ba0b7c34c358f1664220674e5ff8bb7f30502e5f` on 2026-10-29.

This implements the source/frozen host boundary, static frontend and integrated
quarantined runtime experiments needed for the
[R18 acceptance plan](r18-runtime-inventory.md#r19-acceptance-plan). It retains
the Python runtime, normal browser, existing public origins and all 25 active
game/language choices. R14 onboarding, an OCR rewrite, R20 installation and live
data migration are outside this task. No release, tag or Pages publication is
authorized. Engineering evidence below distinguishes source contracts,
synthetic probes, a diagnostic executable and the accepted product candidate.

## R02b method fixed before optimization

No optimization or speed/size claim is proposed. Native measurements require
Windows 11 25H2 x64 and the same machine, power mode, selected browser/profile,
Snipping Tool build, selected game/locale, model and tool bytes for both source
and candidate. Record OS edition/build, architecture, CPU/GPU/RAM, storage,
display/DPI, runtime/CRT versions and a random private installation identity.
Do not publish usernames, absolute paths, account or game-derived contents.

Freeze source commit, requirements/npm locks, packaging-input receipt, candidate
SHA-256, tool/model/fixture digests and selected cases before recording timings.
Use authored Chinese/non-Chinese captions, synthetic catalogs/owned audio and
protected **TEST** credentials. Installed-game probes are separately private;
their absence cannot be replaced by a synthetic pass.

Measure one cold start after reboot and five warm starts for each adapter.
Start the clock immediately before process creation; stop only when both the
frontend and `/api/runtime/ready` (including OCR and the preselected prepared
language) succeed, followed by a usable browser page. Record each sample,
median/range, time to first usable caption, process-tree peak private bytes/RSS,
CPU time and 60-second idle CPU. Record extracted/compressed size and peak disk
usage during preparation and failed update. Account login/network time is a
separate observation; never silently omit a timeout or failure.

Preselected correctness criteria: exact retained origins and local-access
policy, unchanged synthetic transcript/favorite/locale/export identities, zero
competing capture owners, no app-tree writes and no user development-tool
dependency. Preselected recovery budget: a 30-second bounded quiesce attempt
must either confirm all owned processes stopped or refuse takeover and retain
recoverable state. A timeout is a failed recovery probe. There is no performance
pass threshold until these initial source measurements exist; report numerical
comparisons without retrospectively selecting favorable samples. Retain all
failed starts in the denominator.

The current development host is macOS arm64 with Node 22.22.2 (package-engine
supported; CI recommends 24). It cannot establish the Windows baseline, native
OCR/capture/DPI, DPAPI or installed-game playback. Those measurements remain
**unavailable**, not zero and not a pass.

## Ownership and evidence boundary

The initial runtime/frontend/helper phases used two GPT-6.1 Sol agents with xhigh
reasoning in nonoverlapping lanes and reciprocal reviews. The integrator owned
composition, consumer adapters, Git and combined checks. The 2026-10-29 integrated
runtime continuation is implemented and reviewed by the integrator without
additional agents. The [host experiment](r19-host-experiment.md) records static-host and
synthetic recovery results. This task keeps the source Vinext host until an
equivalent replacement is proved.

The copy prototype accepts explicitly marked synthetic fixtures only. It must
retain originals, audio aliases, reading grammar choices, export ledgers,
previous libraries and encrypted fallback bytes; named-store repair, same-user
DPAPI, browser IndexedDB/OPFS and actual launch-pointer recovery remain distinct
gates. Preparation/readiness is not a global writer barrier. The current nested
PowerShell updater is never run under a lifetime guard or given a bypass flag.

## Remaining acceptance gates

The [completion plan](r19-completion-plan.md) turns the remaining R18 acceptance
rows into ordered implementation, component-review and native-validation work,
with per-toolchain cases, dependencies and explicit completion criteria. It does
not change the acceptance contract or approve production activation.

The continued [compiler-free helper experiment](r19-compiler-free-helpers.md)
separates authored packaging probes, the owned NTE bridge and blocked game chains.
It does not convert unresolved helper rights or native evidence into approval.
The [first codec step](r19-codec-experiment.md) adds one pinned experimental
FFmpeg artifact, fixed FLAC-to-PCM dispatch and an independently authored decode
case. General game FFmpeg, redistribution and Windows 11 gates remain open.

All [R18 component gates](r18-runtime-components.md) remain binding for the
actual shipped bytes. Exact maintained CPython supplier, Windows wheels and
native closure, models/fonts/WASM, FFmpeg configuration/source obligations,
vgmstream codec closure, GPL integrations, PRAGMATA REE rights, Oodle and
game-derived constants require evidence before inclusion in an approved distribution. Snipping Tool's OCR
DLL/model files and Death Stranding's install-local DLL are never collected.
Persona's pinned character metadata remains separately acquired private state.

A diagnostic subset or core startup does not pass the all-toolchains gate.
Every active game retains its R18 per-game row, including Half-Life's current
unvoiced-only capture boundary and the separate global setup/audio conditions.
Unprobed installed packs, codecs, helpers and unknown bindings remain explicit.

## Integration checks and review

The two implementers reviewed each other's actual files and check outputs. Fixed
findings included a disabled-profile bootstrap bypass, raw symlink/reparse roots,
settings overlapping disposable storage, build-doctor CWD dependence, expired
copy barriers resuming writers, incomplete quiesce not persisting recovery,
linked checkpoints and unexpected resumed snapshot files. Source-only legacy
root arguments remain authoritative: the source adapter rejects new nondefault
frozen-root environment overrides rather than splitting export/index state.
The standalone ZZZ source reader retains its legacy-directory bridge; frozen
execution is gated before reaching it. Optional ASR keeps a separate process.

On macOS with task-local Python 3.12.13, pinned pytest 9.1.1 and the applicable
platform-independent lock packages:

| Command / scope | Outcome and evidence limit |
| --- | --- |
| `npm run dev:doctor -- --base upstream/main` | **Unavailable (2)**: Node/npm metadata, Python 3.12, generated assets and installed browser binaries observed; full product Python distribution metadata and Windows host unavailable. Node 22 differs from recommended CI 24. |
| Focused runtime/composition/host/migration tests | **57 passed**, independently repeated after review; about 0.61 seconds. Synthetic/source contracts only. |
| Integrated affected Python selection (25 test modules) | Final run: **243 passed, one Windows-only skip**, about 2.94 seconds. An initial failure exposed a Windows-only constant used by a mocked agent worker; `getattr(..., 0)` preserves Windows flags and allows the synthetic test. Its eight-test module and the integrated selection were rechecked. Native startup flags remain unavailable. |
| `npm run typecheck`; `npm test` | Typecheck passed; Node tests: 260 passed, one skipped, zero failed, about 14.85 seconds. This does not establish the full aggregate or browser scenarios. |
| `npm run build` | Existing Vinext build passed. The static experiment rejects client-only desktop hosting; it does not prove static hydration or storage equivalence. |
| Existing router HTTP/WS tests | Two passed with synthetic loopback services. Initial sandbox listener denial was resolved by running the same owned-listener probe with the required host permission. |
| `npm run docs:check`; `npm run audit:public`; `git diff --check` | Passed. New docs were staged before the final link check. Public scan covered the sanitized history and working source. |
| `npm run check:changed -- --base upstream/main` | **Failed/incomplete**, not a full pass. Evidence `a446cfba-de08-4526-a734-b9016b8621f3`: resolved base `ba0b7c3`, available unchanged source snapshot, failed `npm:check` because `pyaudiowpatch` is unavailable during Python collection. Browser/Windows/docs/audit commands later in that aggregate are **not run**; separate successful checks above do not rewrite its status. |

The standard aggregate record and additional private probe reports live under
ignored `output/checks/`. The record identifies the precommit source snapshot;
the final Windows-constant correction is separately rechecked. Full product
browser/package checks belong to hosted CI, while native Windows 11 25H2,
protected TEST credentials and real game/playback evidence remain independent.

### Frontend phase continued on 2026-10-28

The [static adapter and comparison contract](r19-host-experiment.md#explicit-static-desktop-adapter)
now have an actual client-rendered build, pinned local fonts, a stdlib-only Python
loopback host and a restricted frozen `frontend-experiment` profile. Source Vinext
remains available and default. The new profile permits only the frontend child;
the stdlib diagnostic still permits none, and the full runtime remains disabled.
No installer is built. PR #59 and its dependency branch are unchanged.

Focused host/runtime/local-access checks: **227 passed** on task-local Python
3.12.13, including real owned loopback listeners, startup and per-request file
verification, malformed Host/Origin, route isolation, retained immutable chunks,
empty/private tree rejection, MIME and profile dispatch. Six build/comparison
unit tests and typecheck passed. These are separate source/contract checks; the
browser report and hosted frontend executable evidence must be assessed on their
actual source/build identities before claiming those gates passed.

The actual local Chromium/Firefox comparison subsequently passed for build
`3332793ef3e6f75b0ff0039d4d9df8c3082f9a4cd086d2cc10d861ed259ad551`,
including same-origin host swap and browser restart with authored persistent
localStorage/IndexedDB/OPFS, actual worker/WASM English OCR and old chunks.
Both viewport/zoom and lookup pixel comparisons were exactly equal. This is a
temporary synthetic profile observation, not a real-user extension/profile or
Windows 11 pass. Detailed versions and limitations are in the host experiment.

The continued Node run passed **266 tests with one skip** after granting the
owned process/loopback probe its required host permission. The preceding
`check:changed -- --base upstream/main` record
`1b509abb-f236-4478-a0e4-1adcec1112b7` remains **invalid/incomplete**: its aggregate
failed in the sandboxed Node run and source changed during execution. Later
commands were not run by that aggregate; separate successful checks do not amend it.
The stable-source repeat `29b5ec73-d344-48de-93d1-9948e3e6da6f` is **failed**,
with available source/base evidence: typecheck and 266 Node tests passed (one skip),
then Python collection stopped because macOS lacks `pyaudiowpatch`. Remaining
aggregate commands were not run. Full browser/package validation remains hosted.

The first continued hosted run `40761371026` at `50ca8a0` passed the stdlib
diagnostic and protected TEST state jobs. Its frontend build failed before browser
or frozen-host validation because Windows Git converted the pinned OFL notice to
CRLF. Explicit `-text` attributes now retain the exact upstream notice bytes in
both source locations; their original license hash is unchanged. This failed run
does not establish frontend acceptance. The affected Windows job must be repeated.

That repeat, [hosted run 40762619844](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40762619844)
at exact commit `96ed0df69533a72257869a10b4d3b0ecd2183ca6`, passed all three jobs.
The frontend observation contains Chromium 156.0.8078.4 and Firefox 157.0 with
zero pixel differences, actual worker/WASM OCR, persistent synthetic browser state
and confirmed cleanup. The relocated frozen frontend served manifest-exact bytes
without developer PATH and observed no application/data writes. Its frontend build
identity was `22d0f0cf26d8216cd1573adbef9b273ef1267ecc4d61d10aac85f71489c24435`;
the executable SHA-256 recorded by the job was
`caeaf47095f9c30dd1141ea79815c6a9590c26f243978915f8e6487b6d8b418c`.

Downloaded metadata artifact `12848857172` was verified against GitHub's ZIP digest
`efb08a55548f2028641fafc3b6fe3081cb21493bbd05f5768b670016ae9d7192`,
then checked for exact source/build identity, passing owned cleanup and incomplete
rights/native scope. The binary is deliberately not uploaded, so its recorded
executable/provenance hashes are job observations, not independently downloaded
binary verification. The old Python supplier, exact-output redistribution, full
game toolchains and Windows 11 acceptance remain unapproved; `r19_complete` is false.

### Continued integrated source candidate

[Full hosted run 40765392618](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40765392618)
at `8c8a4e90a1337ff82b8150c80487b7ac7042c730` passed source audit, the complete
source check (**1736 Python tests passed, one skipped**), all five browser groups
(desktop/setup/capture/offline/OCR), `required-checks`, packaging and extracted
source-ZIP validation. Publish was skipped. This is the existing source-style
candidate, not an accepted full frozen runtime or installer.

Downloaded source artifact `12851521128` matched ZIP SHA-256
`27db246196994a088509dd62fcc5ae1c74836522710b3fee0bf24e8193796c2b`.
Every `SHA256SUMS` entry matched downloaded bytes; `PROVENANCE.json` identified
the exact `8c8a4e9` source and shared **1.0.12** revision
`2e84f74cf77ea4773463331c7ecde0b05faf31f8`. Downloaded gate artifact `12851955008`
matched `dd2f7564f0f20240661a36902f35b7f23f84894bc12321f73098ee8814291f51`
and reported success, verified identity, full/valid scope, equal tested/workflow
commits and no errors. Its event was manual dispatch; PR base freshness is not
applicable, so this fork evidence does not replace the upstream PR required context.

Subsequent commits change only managed build/probe/workflow isolation and its
documentation, with actual helper validation at `d297b42` recorded in the
[helper experiment](r19-compiler-free-helpers.md). Production UI/API code is unchanged
from the fully checked source candidate. Freshly fetched `upstream/main` and PR #59's
head remained `ba0b7c3` and `8369c953` respectively. Full R19 rights, native Windows
11, serviced Python supplier and supervised-update gates remain explicit and open.
The frontend/stdlib/protected-TEST workflow also passed again at `d297b42` in
[run 40768109482](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40768109482).

The quarantined Windows diagnostic workflow builds from an observed official
3.12.10 installer and exact recorded packaging wheels. That old installer is
deliberately **not** an accepted maintained-runtime supplier. It validates its
publisher signature, relocates the onedir executable to a Unicode/spaces path,
removes developer PATH entries, observes candidate/data writes and uploads only
sanitized metadata. It does not upload binaries, private receipts or caches.
Windows Server bootloader evidence cannot replace Windows 11 acceptance.

### Hosted diagnostic observation

[Diagnostic run 40749551495](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40749551495)
passed on Windows Server 2025 at `09df6c7c533563af0948f0ac8b52defa651caf01`.
It built and started the relocated stdlib-only onedir diagnostic, with developer
PATH removed and no observed application/data writes. The first attempt had
failed before building because setuptools' nested vendored metadata was counted
as a second wheel identity. The corrected parser accepts one top-level identity
and rejects genuinely duplicated top-level records; 34 focused tests and an
independent review passed.

Downloaded **metadata only** was verified against GitHub's artifact digest:
`1a46b62c9ee1727316df52c3b85893b6666a870612af3ad45b690f489a8eb24e`.
Its tested executable SHA-256 is
`239d070bbfd3d151d809d2db018cfcfc3091e045ffd0a15f9050d9ec2348c1a2`;
the candidate-provenance file SHA-256 is
`346a785c7aca179d3b4a8905d63546afa966b94da997a48a91550ed724e8c15a`.
The metadata binds the exact source and explicitly retains `r19_complete: false`,
doctor exit 2, pending exact-output redistribution review and unavailable full
toolchain/native acceptance. No candidate binary or private input receipt was
published or downloaded, so this is not independent verification of a delivered
runtime artifact, signing or attestation.

The first separate full source candidate check at `d2ff584` ran 1,682 Python
tests successfully, skipped one and failed cleanup of one newly added migration
fixture on Windows. SQLite's transaction context does not close its connection;
the assertion reads now use explicit `closing`, including failure paths. The
production verifier already closed connections and was unchanged. Both reviewers
rechecked the eighteen host/migration cases without skipping or weakening
cleanup. The latest hosted rerun and the separate upstream PR gate are tracked
in [draft PR #60](https://github.com/Firebird55/Game-immersion-toolkit/pull/60).
Upstream fork workflow approval requires a repository admin; the current account
received HTTP 403. A manual fork candidate run is additional evidence and cannot
replace that PR's required check context.

## Integrated extracted runtime continuation (2026-10-29)

The new `runtime-experiment` build profile composes the static frontend with
the complete backend/dynamic-reader import closure, workers, reviewed-in-source
FireRedVAD resources and a separately collected ASR executable/native tree.
Credential-writing prompts and the source updater remain disabled. All existing
frozen game-helper/codec rights refusals remain in force. The production
`runtime` profile remains hard-disabled; approval-like strings cannot enable it.

The observed supplier is [Astral's immutable 20261026 release](https://github.com/astral-sh/python-build-standalone/releases/tag/20261026),
CPython **3.12.16**, Windows x64, source revision
`fa506e0858ac9f2cc5b289c137b888a2aa24d1ee`. Its install-only archive SHA-256 is
`590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5`,
independently downloaded and matched against GitHub's asset digest. The
[Python release](https://www.python.org/downloads/release/python-31216/)
is a source-only security release; the Astral binary is a distinct supplier,
not a new PSF Windows installer. Exact-output incorporated notices, CRT/native
closure and supplier acceptance remain open. Existing diagnostic observations
using 3.12.10 remain historical and do not establish maintained-runtime acceptance.

Before collection, `record_runtime.py` compares actual installed interpreter and
wheel payloads against their archives and records exact artifacts, installed
hashes and actual notices. Missing standalone notice text retains complete
METADATA as explicitly incomplete evidence, never an inferred license approval.
The frontend, required application resources and source-pinned VAD model hashes
are bound to the same clean commit. The complete extracted file inventory is
checked again after relocation; binaries are not published.

Fixed frozen probes use new build-bound synthetic roots and an allowlisted OS
environment without inherited developer/loader/account variables. They exercise
actual native imports and all 25 registry adapters, VAD on authored silence,
separate ASR native loading, real index/language workers on authored GoldSrc
fixtures, catalog-library export, and frontend plus real API HTTP/WS together.
API background updates, game discovery and OCR warmup are mocked in that probe
process. No account writes or installed game files are used. The ASR import
probe does not establish model inference; catalog-library export and worker help
do not establish full game export. Loaded native images must originate in the
selected application tree or Windows; main/ASR families remain separate.

Local development doctor returned 2 for unavailable macOS native dependencies.
The focused source contracts passed **101 tests** after granting the owned
loopback tests their required host permission. A sandboxed first attempt passed
93 and failed eight loopback binds; it is not a pass. Windows build/probe results
must be recorded after the integrated workflow executes. Local `check:changed`
record `70735e9b-3fc3-4c89-8a3b-95cea5a231c1` remains failed: typecheck and
271 Node tests passed (one skip), then Python collection lacked macOS
`pyaudiowpatch`; subsequent aggregate checks did not run. The preceding sandboxed
aggregate also failed on process/loopback restrictions. Neither is a full pass.
No installer, release,
tag, Pages publication, live migration or change to PR #59 is part of this phase.

Public compatibility watch returned 2 on 2026-10-29: docs/UI changed, with no
endpoint additions or removals. Public API/settings/language documentation and
the public landing page were inspected without an account. Full live lookup/UI
compatibility remains open; the baseline is unchanged.

### First integrated Windows observation

[Integrated run 40844344068](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40844344068)
passed at clean commit `cb6a3addcd9abf0b941aebf4cb7a506ca29e0099` on hosted
Windows Server 2025 with the pinned CPython 3.12.16 supplier. The relocated
application had only `ProxyTranscriptRuntime.exe` and its separate
`asr/ProxyTranscriptAsr.exe`; no external Python/Node/npm/dotnet/compiler was
discoverable in the cleared child environment. Application files were read-only;
content hashes were unchanged and owned process/fixture cleanup passed.

The actual runtime imported all **25** registry readers, ran FireRedVAD inference
on authored silence, executed game-index and language workers on authored
GoldSrc fixtures with retained Chinese translation, exported an authored catalog
through the library, and passed frontend/API HTTP plus a complete WebSocket
snapshot. Main and ASR processes observed **211** and **59** loaded images,
respectively, all originating inside their application tree or Windows. This
proves observed native loading, not complete CRT/native or Windows 11 acceptance.
ASR model inference, native OCR/frame capture, voice refresh, installed-game
formats/playback and full game-export execution remain unrun.

Downloaded metadata artifact **12883719274** matched GitHub ZIP SHA-256
`4a462a8c0c653f3ffb15a3a4bc54279c258fa080996b46494004f8f9c0996e58`.
Its source/build/scope/cleanup fields were checked. The independently hashed
inventory matched the probe's
`8329ecdb64b7f48df6b267cc5d0f33fa4dbaa37b10e268e8e1a3bba44efe9be8`:
**1,301 files**, **540,463,762 bytes**, **57 component identities**, all rights
gates still pending and `r19_complete: false`. Recorded executable hashes are
`a082adde39246f2c73cddd79103c964e0adb6e2c4f59723132f3d5e9ef2f255d`
and `79d37668d05223b50b612418beb573f88854e834fed8223734978538dfbae040`.
Those match inventory entries, but remain job observations: no binary was
uploaded or independently downloaded. Size is an inventory observation, not an
R02b optimization result.

Earlier integrated attempts failed closed: `40841870506` compared pip-rewritten
RECORD metadata as immutable payload; `40842311387` found non-JSON UTF-8 email
headers in license metadata; `40842833946` found the generic PyInstaller hook's
wrong `webrtcvad` distribution identity; `40843631872` collected unused OpenCV
Haar-cascade examples under `cv2/data`. The corrections preserve actual payload
hash checking, full available notice bytes, the pinned `webrtcvad-wheels`
distribution and the private-tree gate. No failed attempt counts as a pass.

### Integrated follow-up with Setup and directory verification

[Run 40845350877](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40845350877)
passed at clean `63d0602aa7a2f1e0f0aefeb1e834f60e92583b47`, including **104
affected contracts** and the complete extracted probes. Frozen Setup no longer
requires Node/npm or recommends an Endfield SDK/source installer; it reports
explicit pending runtime/codec/OCR/toolchain gates. Source Setup is unchanged.
The actual frozen API's Setup response is checked. The pre/post inventory now
includes directories, detecting directory-only application writes as well as
file creation, deletion, renaming and content changes.

Downloaded artifact **12885490202** matched ZIP SHA-256
`e43844daea4fae794b2588a5fe808764e2e55cd18186c082b33be4144b6630ab`.
Its matching source/build identity, incomplete acceptance, successful cleanup,
two executable entries, **1,301 files**, **628 directories**, **540,464,283
bytes**, 57 components and all pending rights gates were verified. Inventory
SHA-256 `96abce9641e7e9419dc4cd6540e791f3ce60b29e4713012673e843643239b063`
matches the probe receipt. Main/ASR executable hashes are respectively
`b2c3cc4cc31bd2a0b218772835653db9e5377625085bda078de329e7e045a0d1`
and `da41b4fb76a0881a48e816b4fe0e309f15c47737510812f2374bc7837924abe2`.
They remain job observations, not verification of downloaded binaries.

At the same exact source, all three frontend/stdlib/protected-TEST jobs passed in
[40845350966](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40845350966),
and both authored managed/Node helper jobs passed in
[40845350864](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40845350864).
These preserve their existing narrower scopes. Local affected setup/runtime
contracts also passed **65 tests** (one existing deprecation warning).

PR #59 remains open and unchanged at `8369c9534762cd2232fb44424772bd6b5a72b6d2`.
The upstream required PR context at this head remains `action_required` in
[40845361053](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/40845361053).
Current-account admin approval was previously refused; manual fork observations
do not replace that context. No ready-for-review transition, merge, installer,
release or production migration is enabled.

### Full source/browser candidate

[Run 40842180569](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40842180569)
at `1fdf1608d4a6a1a460a7528d316d3514b95a568f` passed source audit, full source
checks (**1,746 Python tests passed, one skipped**), all five browser groups,
`required-checks`, packaging and extracted source-ZIP validation. Publish was
skipped. Setup's first attempt failed a 30-second page navigation in the React
fixture; that job was repeated unchanged and passed. The original failure is
retained; no test, timeout or threshold was relaxed. Other successful groups
were reused by the workflow's aggregate.

Downloaded source artifact **12885241570** matched GitHub ZIP digest
`ca9342b3b2ec69480c550f98f97d9f6512899cf8c6022d99b60a282e524506e3`.
All **12** SHA256SUMS entries matched actual downloaded bytes. PROVENANCE binds
the exact source and shared component **1.0.12** revision
`2e84f74cf77ea4773463331c7ecde0b05faf31f8`.
Downloaded gate artifact **12884817934** matched
`afa0dfc8379bfe1e79c9020e8f43625d6c0e8314764baaadf0f7dd9b9d533f47`
and confirmed success, verified identity, full valid scope, equal tested/workflow
commits and no errors. Its manual event has no PR base-freshness evidence.

Later changes affect frozen packaging/probes/Setup and their evidence; the
affected contracts and actual frozen Setup are verified at `63d0602` above.
This source-style ZIP remains separate from the quarantined extracted runtime.
Neither observation completes R19 rights, Windows 11 or supervised-update gates.

The final documentation-only `check:changed` invocation
`ab57f584-42c8-4e37-93d2-f6f694f1bbaf` conservatively selected full checks for
the packaging README, then again stopped at unavailable macOS `pyaudiowpatch`.
It is not a full pass. Documentation links/generated guides, public audit and
diff checks were run explicitly for the evidence-only changes.

### Integrated owned NTE bridge

[Run 40877210344](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40877210344)
passed **112 affected contracts** and the extracted runtime probes at clean
`d6e593ad2853b155ea2ed9faae7c25cceb31387a`. Collection now requires the owned,
self-contained NTE bridge and verifies its exact current source inputs, nested
manifest, runtime-package payloads and notices. The frozen native probe executes
only its fixed read-only runtime identity operation: app-local CoreLib
**10.0.14**, SHA-256
`69d56e12535d3a8f2f8f89ac8f97577e6dc788d26f2e7b69be8fb5f6ff17ff28`.
Normal NTE game execution remains blocked; external UEExtractor/CUE4Parse/Oodle
files are rejected from this owned subtree. Endfield and REE blocked build
manifests cannot be collected as NTE resources.

Downloaded metadata artifact **12899640632** matched GitHub ZIP SHA-256
`5e21d09c92fe3643093384876d15c127edbfbae7b079236a8f90349a5919244d`.
The inventory digest independently matched the frozen receipt:
`a416000639832711cd43bd24606acbdab7504d4366443e476fd011292a15f1bf`.
Source/build identity, **1,502 files**, **633 directories**, **622,316,061 bytes**,
57 Python/build component identities and the separate NTE helper identity were
checked. Its four executable entries are the main runtime, isolated ASR,
`NteReader.exe` and the pinned .NET runtime's `createdump.exe`. No SDK/compiler
is collected. These sizes and hashes are metadata observations; no binary was
uploaded or independently downloaded, and no R02b size/performance pass is claimed.

The actual native/registry/VAD/worker/ASR/frontend/API/WS/Setup probes passed
with cleared developer/loader/account environment, read-only application files,
unchanged file/directory inventory and confirmed owned cleanup. The receipt keeps
all rights gates pending, native Windows 11 acceptance unavailable,
`game_execution_approved: false`, `r19_complete: false` and `installer: not-built`.
Previously unrun native/game/model/export scopes remain unrun.

At subsequent clean `a72c703`, the actual owned NTE reflection fixture and private
precompiled Endfield/selective x86 REE probes passed. Endfield/REE remain excluded
from runtime collection and distribution. Their exact scopes, digests, original
failure/correction and remaining rights/Windows gates are recorded in the
[compiler-free helper evidence](r19-compiler-free-helpers.md#continued-windows-evidence-2026-10-29).
That REE-only build/probe correction did not modify the integrated runtime code
or NTE builder tested at `d6e593a`. Frontend/stdlib/protected-TEST jobs also passed
at `a72c703`; this does not claim a new full source/browser/package run.

### Critical recheck of collection and Windows inventories

Review reproduced a destination-link failure in the NTE collector: an existing
private evidence `helpers` junction could receive copied bytes before validation
failed. `06eeb97` checks that ancestry before any destination write. Both authored
external-tree preservation regressions now pass. Review also found that several
Windows probes omitted Hidden/System entries; the shared scanner and actual
Windows attribute/mutation fixture are recorded with the original fixture failure
and correction in the [helper recheck](r19-compiler-free-helpers.md#critical-recheck).

[Integrated run 40892020624](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40892020624)
passed **114 affected contracts** at clean `3837b6dd6222ab3a2fd057e498ea8a847fc45547`, including the corrected
Windows inventory fixture and the extracted native/worker/ASR/frontend/API/WS/Setup
probes. Downloaded artifact **12906455506** matched GitHub ZIP SHA-256
`01d416893fcf4f86ddc1260ff31777e5c1f650c9d0cc44e91ed43fa39da49593`.
Its inventory digest independently matched the frozen receipt:
`2a8c34f1eed254050c79d58fd7184e36c9ef02078825af85f8ddd612bc995cbf`.
The same four executable roles, **1,502 files**, **633 directories** and
**622,316,065 bytes** were recorded. The four-byte difference from `d6e593a`
is an inventory observation, not a measured optimization. Source/build identity,
app-local NTE identity, passing cleanup, no observed application writes and all
pending rights/native/full-R19 gates were checked. No binary was downloaded.

Managed/NTE/Node, frontend equivalence, frozen frontend and protected-TEST jobs
also passed at that same clean source. Endfield/selective REE retain their separate
private blocked scope. The [recheck metadata table](r19-compiler-free-helpers.md#critical-recheck)
records all exact ZIP digests. Native Windows 11 25H2, real games/voices, model/codec
closure and owner-aware update/recovery remain unaccepted; no installer is built.

The fresh [full source/browser candidate run 40888558019](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40888558019)
at `06eeb9790ef7f2103343327a3ee64f6e5001c766` passed source audit, full source
checks (**1,759 Python tests passed, one skipped**) and all five browser groups.
Desktop first failed a 30-second click because the account-preferences dialog
remained open. The failed group passed on one unchanged repeat in Chromium and
Firefox across its complete viewport/zoom matrix; the original timeout is retained,
and no assertion, retry, timeout or threshold was changed. The other successful
groups were reused by the aggregate, not silently rerun or relabelled.

Downloaded successful gate artifact **12905408338** matched ZIP SHA-256
`74922230ef97cf4d043c7348be1e025f24668e32b14cfc65afe3258ef0c8791c`.
Its verified identity, full/valid scope, equal tested/workflow commits, passing
audit/check/browser jobs and empty errors were checked. The manual event has no
PR base-freshness evidence and cannot replace the upstream PR required context.
Later commits change only the Windows probe inventory and its authored fixture;
their native execution is independently verified at `3837b6d` above.

Packaging and extracted source-ZIP validation also passed in that full run;
publish was skipped. Downloaded artifact **12905867145** matched GitHub ZIP SHA-256
`cc8d1aff6b3b2671e9912067c2b27a3a39208bbda04a86f20730d88575611f0a`.
All **12** SHA256SUMS entries matched downloaded bytes, including the actual
distribution ZIP. Outer and nested PROVENANCE agreed on exact source `06eeb97`
and shared **1.0.12** revision `2e84f74cf77ea4773463331c7ecde0b05faf31f8`.
This remains the existing source-style distribution, separate from the quarantined
extracted runtime and its narrower native/rights evidence. No installer, tag,
release, merge or Pages publication occurred.

## Continuation and rollback

Use the integrated workflow for the extracted runtime/native/ASR observations,
keeping the production runtime profile disabled until required helper/host and
exact-output rights/native evidence exist. The static CSR frontend removes
end-user Node/Wrangler in the observed experiment; real browser-profile/update
continuity and the native acceptance gates remain open. Prebuild NTE/Endfield
helpers only with complete runtime/NuGet/source evidence; keep PRAGMATA/Oodle/GPL
and metadata rights gates explicit. Execute every toolchain's R18 functional
protocol against the same accepted extracted artifact, then the native and R02b
measurements above. Implement and prove the supervising global writer barrier,
continuous legacy exclusion, owner-aware updates and launch-pointer recovery
before any live migration activation.

The branch is reversible independently of R18. No live user data, credentials,
source installation, R18 branch or dependency PR is changed by these probes.
