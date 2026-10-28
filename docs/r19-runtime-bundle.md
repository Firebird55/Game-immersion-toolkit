# R19 — Windows runtime-bundle prototype

Status: **active implementation; full R19 acceptance incomplete**. This task
starts from R18 commit `8369c9534762cd2232fb44424772bd6b5a72b6d2` on
`codex/r19-runtime-bundle`. The dependency remains [PR #59](https://github.com/Firebird55/Game-immersion-toolkit/pull/59).
It is not changed or merged by this work. The actual target is
`Firebird55/Game-immersion-toolkit:main`; freshly fetched `upstream/main` was
`ba0b7c34c358f1664220674e5ff8bb7f30502e5f` on 2026-10-28.

This implements the source/frozen host boundary and an opt-in static frontend experiment needed for the
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

Exactly two GPT-6.1 Sol agents with xhigh reasoning implement nonoverlapping
runtime/packaging and host/frontend/recovery lanes. The integrator owns shared
composition, consumer adapters, Git and combined checks. Each agent reviews the
other's actual changes before integration is committed. No nested agents are
used. The [host experiment](r19-host-experiment.md) records static-host and
synthetic recovery results. This task keeps the source Vinext host until an
equivalent replacement is proved.

The copy prototype accepts explicitly marked synthetic fixtures only. It must
retain originals, audio aliases, reading grammar choices, export ledgers,
previous libraries and encrypted fallback bytes; named-store repair, same-user
DPAPI, browser IndexedDB/OPFS and actual launch-pointer recovery remain distinct
gates. Preparation/readiness is not a global writer barrier. The current nested
PowerShell updater is never run under a lifetime guard or given a bypass flag.

## Remaining acceptance gates

The continued [compiler-free helper experiment](r19-compiler-free-helpers.md)
separates authored packaging probes, the owned NTE bridge and blocked game chains.
It does not convert unresolved helper rights or native evidence into approval.

All [R18 component gates](r18-runtime-components.md) remain binding for the
actual shipped bytes. Exact maintained CPython supplier, Windows wheels and
native closure, models/fonts/WASM, FFmpeg configuration/source obligations,
vgmstream codec closure, GPL integrations, PRAGMATA REE rights, Oodle and
game-derived constants require evidence before inclusion. Snipping Tool's OCR
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

## Continuation and rollback

Run the new diagnostic workflow on this branch, inspect actual job and metadata
results, then keep the full runtime profile disabled until the required
helper/host artifacts and exact-output rights/native evidence exist. A static
prerender/export implementation or an explicitly reviewed app-local server
runtime is required to remove end-user frontend tooling. Prebuild NTE/Endfield
helpers only with complete runtime/NuGet/source evidence; keep PRAGMATA/Oodle/GPL
and metadata rights gates explicit. Execute every toolchain's R18 functional
protocol against the same accepted extracted artifact, then the native and R02b
measurements above. Implement and prove the supervising global writer barrier,
continuous legacy exclusion, owner-aware updates and launch-pointer recovery
before any live migration activation.

The branch is reversible independently of R18. No live user data, credentials,
source installation, R18 branch or dependency PR is changed by these probes.
