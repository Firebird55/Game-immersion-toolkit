# Rework roadmap

Status: **R18 research and storage/host design completed; implementation tasks
remain planned**. The [R18 inventory](r18-runtime-inventory.md), reviewed on
2026-10-28 against upstream `ba0b7c3` (0.22.0), defines component acquisition,
Windows targets and the R19 prototype/acceptance decision. It builds no bundle
or installer and establishes no native Windows validation. Its initial 0.21.3
review was refreshed for all 25 active games before the PR. The original research on
2026-10-24 used version **0.19.1**, commit
`16d17f782e3e1d2fbfbd45c624cfe9613e78363a`. The subsequent
[architecture study](rework-architecture.md) examined upstream `387631f`, including
PRs #34 and #35. This revision incorporates the owner's review of PR #36 and the
choice of screenshots, sampled language combinations and game-specific regressions.
It changes documentation, not application behavior, workflows or tests.

## Direction and scope

Deliver independently verifiable improvements to recognition, transcript identity,
companion UX, onboarding and Windows installation. Retain Python and the ordinary
browser for now; investigate another runtime only for a measured, bounded problem.
Keep shared reading components in Lexirise-shared-components. No new repository,
task database or orchestration platform is required.

Write engineering documentation, task descriptions, reviews and delivery reports
in English even when instructions arrive in another language. Multilingual product
strings, game text and language fixtures retain their intended language. Do not
introduce mixed-language explanatory prose.

Treat supported games equally. Existing ZZZ-specific logic and an available ZZZ
package make useful examples, not a priority order. Inventory every active game's
presentation gaps and choose cases by observed defects, missing behavior and user
impact. Use screenshots as primary regression inputs. Sample a few supported
language combinations; exhaustive coverage is not a release requirement.

Read [AGENTS.md](../AGENTS.md), [RELEASE.md](../RELEASE.md),
[runtime contracts](runtime-context.md), [development checks](development-checks.md)
and the [AI workflow](ai-development-workflow.md) before implementation. The
[screenshot regression plan](screenshot-regression-plan.md) is the detailed
acceptance contract for corpus, package import, sampling and hosted execution.

### Invariants

- Preserve Chinese transcripts, favorites, calibration, game paths, archived data,
  userscript storage keys and independent Browser Extension mode. Labels may change;
  the internal `migaku` value and existing preferences must remain compatible.
- Source/runtime/account/language switches invalidate old asynchronous work.
  Updates leave at most one capture owner. Failed preparation retains the last
  complete index. Cancellation, lock order and atomic publication remain intact.
- Text, translation and voice identities come from verified catalog bindings.
  Never invent uncertain matches, original audio or speaking order. Audio failure
  does not erase confirmed text. Preserve explicit unvoiced comic support without
  broadly allowing unmapped dialogue or weakening ambiguity rules.
- Real accounts are read-only during verification; account writes use mocks.
  Credentials remain in protected host storage, not workflow secrets.
- Do not modify game files or publish extracted libraries, original audio, private
  screenshots/recordings, personal paths or account diagnostics. Pages remains
  restricted to allowlisted static assets. Apply the screenshot plan's separate
  public-fixture and private-input evidence rules.
- Shared changes require upstream tests, version publication, `shared:update` and
  checked commits in both consumers. Never patch consumer vendor source.
- Use GitHub-hosted Actions and the existing release process. No cluster dependency.
  Windows is the supported desktop target; relevant mobile-browser checks may use
  macOS/WebKit. Linux product/browser validation is not required and should be
  removed from the test plan. Static publishing infrastructure is a separate concern.

## Research baseline and limits

Historical findings included spatial ordering of ZZZ comic groups, differences
between legacy and multilingual matching, a single-match mobile scan, and replay
that compared sets without checking order or duplicates. PR #34 subsequently
added independent multi-bubble recognition and voice recovery. PR #35 added
account-aware language/game selection and persistent translation targets. Preserve
those solutions and inspect current code before treating a historical issue as open.

Other findings remain investigation leads: coarse mobile source status, reading
controls outside their mode, update UI, launcher discovery, physical pack status,
source-ZIP distribution, Node/Wrangler hosting and native worker cleanup. See the
[architecture evidence](rework-architecture.md#current-boundaries-and-evidence).

The historical research counted 36 video clips without ZZZ, and an older browser
report recorded 35/54 passing cases. Neither is a current coverage score. No new
native Windows, physical iOS or performance verification is established here.
Existing videos are optional supplementary evidence; the revised work does not
require a video corpus or live YouTube playback. A screenshot establishes visible
content; temporal claims require independently annotated screenshot sequences.

## Three workstreams

Each workstream has an owner and independently deliverable tasks. Research,
implementation, necessary tests and review belong inside each task. There is no
project-wide R00/F0 phase. Only concrete interface dependencies block work.

**P0** protects correctness or necessary evidence; **P1** improves the product;
**P2** is a conditional experiment. These are priorities, not calendar promises.

| Workstream | Owner | Independent outcome | Starting work |
| --- | --- | --- | --- |
| W1 — Companions and UX | UX owner | Clear, compact desktop/mobile controls | R03, R04 or R05; coordinate shared files |
| W2 — Recognition and transcripts | OCR owner | Correct identities and supported presentations, with screenshot/package regressions | R01; prepare the R02a measurement plan only where needed |
| W3 — Installation and game management | Installation owner | Discovery, onboarding and self-contained Windows installation | R14 and R18; prepare R02b |

All implementation tasks below remain **planned**; R18 is a completed research
deliverable, including the R12c storage/host design, rather than a running bundle.
R02a/b/c are separate
measurements. R07a characterizes production before R13c extraction; R07b then
uses the extracted controller. R12/R13 identify concrete boundaries, not a fourth
refactoring workstream. R25 is incremental test reduction owned by the integrator
with the relevant workstream owners, not a global prerequisite.

At task start, record the intended behavior, owner, current baseline, relevant
acceptance cases and exact checks. Reproduce bugs; characterize behavior before
risky extraction. Distinguish desktop legacy, prepared-language desktop, mobile
OCR and paired-PC routes. Simple documentation/copy edits need no new test suite.
Missing device access blocks only claims that depend on it.

## W1 — Companions and UX

W1 owns presentation, including the consumer behavior required by R09/R10.
W2 supplies event semantics and independent fixtures; R03–R06 can finish without
waiting for all recognition work. Only one task writes a shared UI file at a time.

| ID | Delivery | Dependency | Acceptance evidence |
| --- | --- | --- | --- |
| R03 | Preserve source status through the header; clickable subsystem diagnosis | Relevant start check; R12a/R13d only when that boundary changes | First frame, still image, pause, reconnect, missing library and account lock have correct explanations; existing OCR events remain usable |
| R04 | Browser Extension/Lexirise API labels and mode-specific reading options | Relevant current behavior | Both modes, both mobile reading-option entry points and persisted `migaku` preferences work after reload; preference contract handed to R17 |
| R05 | Remove the update banner while retaining safe activation and offline cache | Existing update scenarios | No banner or automatic reload during play; safe activation/reopening preserves data on the current host |
| R06 | Compact primary flows with accessible contextual help | Relevant R03/R04 controls only | Help is discoverable, dismissible and works with keyboard, focus, hover and touch; blocking errors remain visible |

Acceptance:

- Frame receipt, freshness, OCR, library and account state are distinguishable.
  An unchanged image is not proof of network failure, and a selected game is not
  a detected running process. Do not label receipt time as end-to-end latency.
- Status explains connecting, first frame, still image, interruption, pause,
  missing library, no match and locked account, without exposing private links.
- Browser Extension mode offers selectable text without a Lexirise account.
  Preserve its independence and existing preferences. Extension examples may
  include Migaku, Yomitan and Lexirise with accurate platform limits.
- Both mobile Reading options entry points are hidden outside Lexirise API mode;
  general font size and translation display remain available.
- Waiting updates activate on a safe next start or explicit Settings action.
  Offline reopening preserves history, favorites and calibration.
- Relevant desktop/mobile, Chromium/Firefox/WebKit, narrow layout, zoom and Shadow
  DOM checks pass. Select cases by the affected boundary rather than multiplying
  every layout by the full screenshot/language matrix. Physical iOS claims need devices.

## W2 — Recognition and transcript reliability

Use two complementary tracks: **presentation regressions for game-specific gaps**
and **a small sample of language combinations**. R01 inventories every supported
game. Gather screenshots for uncovered layouts, including non-comic cases, and
preserve confirmed fixes as regressions. Three to five fixed language combinations
across the initial corpus are sufficient to start; choose only actual supported
package locales. Pin known regressions and rotate a small supplemental sample.

The owner's ZZZ package is an initial candidate, not a verified artifact or a
priority over other games. Inspect its format, locales and accessibility before
using it. Public CI uses authored images and synthetic packages; real package and
screenshot validation follows the private-input rules in the
[screenshot plan](screenshot-regression-plan.md#github-execution-and-private-inputs).

| ID | Delivery | Dependency | Acceptance evidence |
| --- | --- | --- | --- |
| R01 | Active-game presentation inventory, annotated screenshots/sequences, package-input manifest and small language sample | Relevant start check; independent of W1/W3 | Every active game has explicit coverage/gaps; selected positives and negatives have independent identities and locale expectations; input provenance/hashes recorded; missing inputs visible. Product recognition need not pass yet |
| R02a | Targeted recognition/performance baseline before tuning | Plan can start directly; R01 and R07b for measurements of that route | Commit, corpus, package, model, environment and preselected quality/time limits recorded; missing measurements stay open. No benchmark on every image/PR |
| R07a | Characterize current production with controlled screenshot/clock/I/O input | R01; minimal injection boundary if needed | Actual scan, confirmation, history and publication execute; each applicable special game route is asserted; stop/source-change/stale results and existing defects recorded |
| R07b | Screenshot/sequence runner using the same production controllers and actual-format mobile package importer | R07a; mobile after R13c; desktop may proceed independently | Before/after characterization agrees; real OCR lane separated from controlled temporal lane; wrong identities, omissions, duplicates, stale events and wrong locales are detectable; no duplicate decision loop |
| R08 | Shared fragment/identity/occurrence/order contract and targeted matching fixes | Relevant R07b, R12b and R02a limits before tuning | Preserve ambiguity and voice rules; legacy/prepared routes handle the affected fragments; W1/W2 agree display, persistence and favorite semantics. Consumer evidence follows in R09/R10 |
| R09 | Fix demonstrated desktop presentation/temporal gaps | Relevant R08/R12b; R13b when activation changes | Selected game-specific screenshots and critical sequences pass; movement/repetition/unknown order are distinct; desktop, restored history and paired-PC reconnect preserve semantics |
| R10 | Fix demonstrated mobile presentation/temporal gaps through the packaged app | R13c, relevant R07b/R08/R12b; R03 agreement for changed status | Selected game-specific cases pass through production package import/OCR/matching; retain existing multi-bubble support; history, translation and voice recovery remain correctly scoped |
| R11 | Evaluate presentation regressions and sampled language combinations across supported games | R07b per route; relevant R08–R10 fixes and R02a criteria | Report exact game/presentation/pair/package/route coverage, held-out cases, failures and unavailable inputs. Require the bounded selected set, not every possible combination; GitHub synthetic and real-input evidence remain distinct |

### Recognition acceptance

- Expected text/IDs/order come from independent annotations or verified authored
  metadata, never from the recognizer or its current sorting function. Include
  positives and relevant HUD/menu/choice/ambiguity negatives. Required lines must
  appear; rejecting everything cannot pass on precision alone.
- Exercise the built mobile artifact and normal ZIP import, not only an in-memory
  catalog. Check source/study, on-screen OCR, translation, audio locale and player
  variant independently. Verify actual voice binding or explicit unavailability,
  manual playback where applicable, and representative reload/offline behavior.
- Never infer a supported pair from storefront languages or browser locale.
  Missing targets and mismatched/unprepared packages do not fall back to another
  language. Mock account cases preserve per-language effective targets and isolation.
- Keep game-specific route selection explicit. Examples include light/dark comics,
  overhead captions, centered cards, wrapped/legacy panels and context-dependent
  pages. Document uninspected or unsupported presentations rather than silently
  labelling the whole game covered. Preserve optional-channel defaults.
- Critical temporal cases include right/bottom observed before left/top, movement,
  scrolling fragments, simultaneous bubbles, a persistent old line, typewriter
  text, overlap, dropout, late OCR, source/scene change and genuine repetition.
  Retain ZZZ dark bubbles, more than eight visible lines and multi-bubble cases
  as relevant regressions, not the definition of the whole corpus.
- Duplicate delivery of a frame is not independent confirmation; genuinely new
  observations may have identical pixels. A still image or repeated synthetic
  frame proves neither real chronology nor physical capture stability.
- A narrow-crop suffix must not emit an unrelated line when the wider presentation
  identifies another complete utterance. A later independent utterance remains
  recognizable. Preserve confirmed Chinese text on audio failure and explicitly
  supported unvoiced cases; do not broadly admit unmapped content.
- Movement retains an occurrence; an annotated later repetition can create a new
  occurrence for the same text ID. Use validated authored order, then reliable
  first observation; otherwise retain unknown order. Coordinates, dictionary order,
  completion times and language models must not invent chronology or audio order.
- W1/W2 agree favorite identity in R08 while preserving existing favorites.
  Display, persistence and paired-PC reconnect preserve occurrence counts and
  groups with unknown order. A stable UI placement must not imply speaking order
  or introduce artificial timestamp differences. R09 proves desktop/paired-PC;
  R10 proves local mobile OCR and restored history.
- Critical synthetic sequences require every expected line and zero incorrect
  identities, unintended duplicates, stale publications or order inversions.
  Negative cases emit no forbidden lines/voices. Real OCR thresholds are fixed
  before tuning; failures are not hidden by deleting difficult screenshots.
- Hold-out scenes are not used for tuning. If promoted to a regression, version
  the set and replace the independent evaluation sample. Record game patch,
  image/package/model digests and annotation version; resized input is labelled.
- Measure latency only where the input supplies a valid source timeline, with
  explicit source/processing clock correlation. Single-image processing duration
  is not gameplay latency. Physical phone endurance and native Windows capture
  remain separate checks.

R07a/R07b can finish as trustworthy infrastructure while explicitly tracked product
failures remain. That does not complete R08–R11. Missing real inputs are `unavailable`,
not synthetic passes. A bounded passing sample proves only its stated coverage.

## W3 — Installation and game management

Discovery/onboarding and bundling can progress independently before integration.
Agree the R14/R18 storage boundary early. Bundle the existing runtime without
waiting for an OCR rewrite or optional language experiment.

| ID | Delivery | Dependency | Acceptance evidence |
| --- | --- | --- | --- |
| R14 | Candidate, physical pack and preference contracts; one service for installer/WebUI | Current runtime requirements; early R18 findings | Schema, owners, paths, migration, precedence and failure behavior defined; consumer contract checked |
| R15 | Steam manifest, Epic/GOG and validated HoYoPlay discovery, bounded fallback and manual paths | R14 candidate contract | Nonstandard drives, stale/corrupt/missing records and cancellation tested; invalid input preserves a valid manual selection |
| R16 | Physical voice-pack probes separate from reader/index readiness | R14; game probes can progress independently | Claimed game/locales distinguish present, incomplete, missing and unknown; no wrong-language fallback |
| R17 | Reusable games → languages/packs → reading mode → ready onboarding | R04 preference contract; R15/R16; R14/R18 storage boundary | WebUI/test host uses real discovery/probes; skip/resume and preference precedence work; installer host evidence follows in R20 |
| R02b | Windows cold/warm start, CPU/RSS, recovery and bundle baseline | Plan first; current runtime and Windows for measurements | Commit, environment, method and preselected criteria recorded before optimization; missing measurements remain open |
| R18 — completed research | [Runtime/tool/redistribution and Windows inventory; storage/host contract](r18-runtime-inventory.md) | Refreshed at upstream `ba0b7c3` (0.22.0, 25 active games); supplies R12c design for R14 adoption | Per-component bundle/download/prerequisite decisions, ownership, limits and R19 acceptance plan recorded; native/artifact evidence remains open |
| R19 | Windows runtime bundle and functional probes; investigate static frontend | R18; R02b for comparison; R12c/R14 storage boundary | Extracted bundle starts without a development environment; relevant game/OCR probes and origin/API/cache behavior verified |
| R20 | Per-user installer, integrated onboarding, repair and uninstall | R17 and R19 | Actual installed candidate passes functional probes, ordinary-user setup, cancellation, no-space and locked-file cases |
| R21 | ZIP migration, upgrade, interruption and rollback | Shared storage contract; integrated evidence with R20 | Synthetic data/preferences survive; failed update preserves recovery and at most one capture owner; origin storage and protected test credentials checked |
| R22 | Candidate artifact verification in hosted CI; checksums and signing decision | R20/R21 and applicable gate G | Actual candidate validated; downloaded checksums/commit verified; native evidence and signature/attestation status explicit |

R18 selects a Windows x64 PyInstaller one-directory prototype of the existing
Python runtime, plus a bounded local static-frontend equivalence experiment.
Retain the ordinary browser and current desktop origin/API addresses; source
hosting remains the diagnostic fallback until equivalent behavior is proved.
R19 acceptance still requires an extracted candidate without preinstalled
Python/Node/npm or SDK/compiler toolchains. The
[component inventory](r18-runtime-components.md) tracks unresolved redistribution
closure (including GPL/WASM, FFmpeg and decompression binaries), .NET/native helper
dependencies and Windows/OCR constraints. The
[host contract](r18-storage-host-contract.md) defines opt-in ZIP copy migration,
protected credentials and recovery; R14 consumer adoption, static-host behavior,
native measurements and actual migration/rollback remain unverified. A fallback
that still requires development tools does not pass R19. R20–R22 remain planned.
The follow-up R18 review also requires a prebuilt/adapted managed launcher,
pointer/shortcut and existing browser-profile continuity, owner-aware updates
under continuous legacy exclusion, preservation of export-volume work/previous
libraries, and explicit unreadable-account-store recovery. These remain design
and candidate/installed acceptance work, not implemented guarantees.
The 0.22.0 refresh additionally inventories the twelve Steam readers, Decima's
game-owned native DLL, Persona's separately downloaded GPL character tables and
incorporated reader notices. These acquisition/format/capability probes join
R19; a package-manager graph with no new packages does not prove resource closure.

Installation acceptance:

- Installer/WebUI show identical candidates and errors. A launcher entry or folder
  name alone does not establish a valid installation. Cover spaces/Unicode,
  multiple/moved installs, unavailable drives, stale records and incomplete packs.
  Discovery is bounded and cancellable; no full-disk scan or launcher login.
- Keep physical presence, reader support and prepared-index readiness separate.
  An old index does not prove a voice pack is still installed. The toolkit does
  not install/change game files or voice packs. Unknown formats allow manual paths.
- Skip/resume works. Preserve existing reading preferences unless the user makes
  an explicit replacement choice. Initial browser launch follows that precedence.
- Prototype per-user Inno Setup with the existing runtime; a PyInstaller directory
  bundle is an option to prove. Alternatives require a concrete need. Do not
  assume Snipping Tool OCR components can be redistributed.
- The candidate works on clean Windows without preinstalled Python, Node/npm or
  .NET SDK, subject to declared system prerequisites with recovery guidance.
  Probe every distinct required extractor/toolchain, not only one game or a build.
- Repair/uninstall/update preserve user data by default. Separate application and
  data migration. Do not copy DPAPI material blindly across Windows users.
  Preserve browser origin or prove transfer of localStorage/IndexedDB; copying
  a data folder alone does not establish browser history/preference migration.
- Failed preparation leaves the previous runtime usable; takeover has one capture
  owner. Hosted artifact checks do not replace clean native Windows capture/OCR,
  launcher, multiple-monitor, crop-bound and relevant 125–200% DPI checks.
- Distinguish checksums, JSON provenance, Authenticode and cryptographic build
  attestations. Claim signing only after verifying signature/timestamp; use
  protected key storage. No Linux installation/support matrix.

## Architecture tasks within the workstreams

The [architecture study](rework-architecture.md) explains these boundaries. Assign
only the extractions needed by a concrete change; no general refactoring phase.

| ID / priority | Owner and scope | Dependency | Acceptance and rollback |
| --- | --- | --- | --- |
| R12a / P1 | W1: status/UI read model and changed HTTP/WS fields | Relevant R03 path | Reuse StateVersion/StatePoll and pairing validation; preserve generations, late snapshots and independent event domains; adapter rollback without storage migration |
| R12b / P0 | W2: context, active game binding and observation/content/occurrence/order semantics | R01 and relevant R07a | Coherent catalog/locale/voice and explicit unknown order; handoff preserve/reset/version policy; no universal replacement generation counter |
| R12c / P0 — design delivered | W3: [resource/data/cache/credential layout and runtime/frontend host contract](r18-storage-host-contract.md) | R18 design completed; R14 adoption and R13a adapters remain planned | Owners, schema, migrations, source/bundle paths, origin/API/assets/cache and readiness/quiesce/rollback recorded; adapter implementation and bundle validation follow |
| R13a / P1 | W3/integrator: extract necessary setup use case and host/composition boundary | Relevant endpoint/lifecycle behavior; R12c for host changes | Preserve endpoints/status codes, LocalAccessMiddleware, account pinning, standby/close and lock order; source uses the boundary; actual bundle follows R19; reversible without data changes |
| R13b / P0 | W2: public game/locale activation with coherent binding | R12b and affected desktop R07a | Replace external `_scan_epoch` mutation with one owner; stale work cannot publish; retain last complete index and explicit legacy/prepared paths; facade first, no matching change |
| R13c / P0 | W2: mobile controller factory with source/clock/OCR/library/store/output injection | Mobile R07a; existing receiver/worker contracts | Same production scenarios before/after extraction; single-flight, stop/close/pagehide/source/locale switches reject late successes/errors; resources released; shell and direct harness use one factory; replay follows R07b |
| R13d / P1 | W1: relevant subscriptions/transport/read model out of presentation | R12a and current UI characterization; R13c only for new controller use | No recognition decisions from mutable DOM text; preserve reader/account/locale ownership, extension independence and mount cleanup; UI-local state stays local |
| R13e / P1 | W2: separate desktop observation, game policy and publication one affected route at a time | That route's R07b/R12b; R13b if binding changes | Observation does not write transcript; one publisher validates context; preserve match/voice/channel/unvoiced/error policy; functional fixes separate, rollback per route |

R04/R05 need not wait for controller work. R13c does not depend on finished R07b.
Characterization records defects without turning them into desired invariants.
Functional fixes and pure extractions get separate commits. Recheck new state
across runtime handoff. R19 may package the existing runtime while OCR work continues.

## R25 — Reduce test cost and keep necessary coverage

**Owner:** integrator with each affected workstream owner. This is planned work,
not a claim that tests have already been deleted or workflows changed here.

Review the thousand-plus Python tests and overlapping browser/CI scenarios.
Record each reviewed group's unique failure, supported behavior, layer and measured
cost. Keep useful tests; consolidate duplicates; remove obsolete, unsupported or
implementation-mirroring cases. For every removal, identify retained equivalent
behavior coverage or the explicit retirement of the behavior. Do not prune simply
to reach a count, and do not delete a failing regression to make a run green.

Acceptance:

- A bounded, reviewed keep/consolidate/remove mapping and before/after timing
  evidence for the affected areas; no loss of distinct account isolation, data
  preservation, language/voice identity, migration, lifecycle or publication checks.
- No Linux product/browser test jobs in the resulting plan. Preserve relevant
  Windows and mobile WebKit evidence on supported hosts before moving coverage.
  Linux used only for static publishing does not establish a support claim.
- New tests name the concrete failure they detect and why an existing cheaper
  test is insufficient. Prefer unit/contract checks for logic and a few actual
  OCR/package browser checks for integration. Simple copy/style edits add no tests.
- Build once, share fixture/model setup, deduplicate selected tests, and measure
  wall-clock time in ignored `output/checks/`. Set budgets from measurements before
  expanding expensive cases; do not invent a universal runtime promise.
- PRs select affected regressions and a small stable sample. Manual/candidate runs
  can rotate a bounded supplemental sample. No exhaustive language/browser/size
  product and no repeated full suite across multiple jobs for the same artifact.
- Update the selector and necessary CI assertions alongside removals. Check the
  changed selection behavior and affected suites; reserve complete packaging and
  supported-target acceptance for the candidate/release gate.

## Optional native experiment

P2 work starts only with a concrete problem and owner; it blocks no other stream.

| ID | Delivery | Dependency | Acceptance evidence |
| --- | --- | --- | --- |
| R02c | One hypothesis, baseline and success threshold | Reuse applicable R02a/R02b evidence | Same-input comparison and criteria fixed before experimentation |
| R23 | Compare current runtime, managed Python worker and only justified Rust/C# alternatives | R02c; affected contracts/regressions; R19 if bundling is part of the experiment | Same environment, correctness/recovery and performance measurements; no language-only speed claim |
| R24 | Retain/migrate decision with maintenance and rollback | R23 | Measured outcome, compatibility and maintenance costs; retaining Python is a valid completed result |

Compare identical frames, engine/model, catalog, hardware and build settings.
Separate capture/OCR/matching/publication time, cold/warm start, RSS and recovery.
Preserve identity, data integrity and Browser Extension behavior. A new webview
needs its own extension-compatibility evidence and cannot silently remove the
ordinary-browser route. A successful experiment does not authorize a rewrite.

## Gate G — Evidence, integration and release

Apply the relevant criteria to each task; complete packaging belongs to the
candidate/release gate in RELEASE.md.

- Relevant checks pass on the delivered source and artifact. Record selected cases,
  commands, fixtures, environment, durations and pass/fail/not-run/unavailable.
  Missing device/platform evidence does not count as a pass.
- Fetch the actual PR target repository/branch and record the base SHA. The push
  remote is not necessarily the comparison base; follow the
  [verification rules](ai-development-workflow.md#verification-and-evidence).
- Capture/account/migration/lifecycle changes receive independent review against
  criteria, diff and actual output. Resolve or substantiate findings. Reviews do
  not replace tests. Documentation-only changes need proportionate review.
- Integrate overlapping changes and check the combined result. Independent green
  runs on older baselines do not prove integration.
- Required native Windows and physical iPhone/iPad evidence names the candidate
  and tested configuration. Browser automation does not establish physical USB,
  ReplayKit/background capture, real extension compatibility or phone endurance.
- Keep local/external data boundaries and rollback current. A stateless gateway
  may still process request content. Never publish private inputs or diagnostics.
- Publish only through the existing public audit, clean-main release and hosted
  checks; verify downloaded checksums/provenance. No release is authorized here.

## Ownership and milestones

| Shared boundary | Integration owner | Handoff |
| --- | --- | --- |
| `mobile/companion.jsx`, `app/companion.tsx` | W1 | W2 supplies identity/order fixtures for R09/R10; W3 supplies onboarding preference bridge |
| Mobile source/controller/OCR events | W2 | W1 supplies targeted status changes; retain adapters until consumers migrate |
| Setup UI/API and installation storage | W3 | R04 preference contract precedes R17 integration; contextual help can follow independently |
| Capture policy versus runtime hosting | W2 for algorithms, W3 for lifecycle/bundle | Agree worker/API boundary; packaging does not silently change recognition policy |
| `backend/api.py`, shared schemas and release configuration | Integrator | One writer per change, with affected consumers/artifacts and checks identified |

A changed producer contract carries consumer adapters/migration and regression
proof. Stubs allow development but do not prove integration. Isolate conflicting
writers in appropriate worktrees; one owner integrates the combined result.

| Milestone | Acceptance | Owner |
| --- | --- | --- |
| M1 — Independent result | W1: R03–R06; W2: R01/R02a/R07a/R07b/R08–R11 for the declared bounded scope; W3: R02b/R14–R22. Include applicable R12/R13 and R25 work. Evaluate each stream independently | Workstream owner and reviewer |
| M2 — Integrated rework | On one candidate: select/detect game → check packs → choose reading mode → start companion → use source/OCR/transcript; restart preserves preferences and switches reject stale work. Verify both modes and declared desktop/mobile routes | Integrator and stream owners |
| M3 — Release ready | M1 for the release scope, M2 and gate G; actual installer on clean Windows, relevant devices, migration/rollback, checksums and remaining limits documented | Integrator/maintainer |

Completed bounded improvements can ship through the normal authorized release
process without waiting for every stream. M3 means ready, not automatic permission
to publish. Assign one concrete task at a time using the
[task contract](ai-development-workflow.md#task-contract); reading this roadmap
alone does not start parallel implementation.

## Traceability

| Owner request | Tasks |
| --- | --- |
| English-only engineering prose, even after Dutch instructions | This documentation set and AI workflow |
| Equal treatment of games and discovery of game-specific holes | R01, R08–R11 |
| Screenshots and mobile-package regression infrastructure | R01, R07a/R07b, R13c, R11 |
| A few sampled language combinations, not every permutation | R01/R11; screenshot plan |
| Necessary, faster checks; prune redundant Python tests; no Linux product tests | R25 and development checks |
| Compact controls, useful status, mode-specific options, no update banner | R03–R06 |
| Game discovery, voice-pack checks and shared onboarding | R14–R17 |
| Standalone Windows installer, data preservation and verified delivery | R18–R22 |
| Justified runtime choices | R02a–c and R23/R24 |

## Decisions requiring evidence

| Decision | Current direction | Evidence point |
| --- | --- | --- |
| Core runtime | Retain Python; targeted alternatives only | R24; no installer dependency |
| Runtime bundle | R18 selects Windows x64 PyInstaller one-directory prototype; exact pins/collection and native dependencies still need proof | R19 and R02b; [acceptance plan](r18-runtime-inventory.md#r19-acceptance-plan) |
| Frontend host | R18 selects local static equivalence experiment; retain current origin and diagnostic source-host fallback until proved | R19, with origin/storage/API/cache compatibility; a development-tool fallback does not pass standalone acceptance |
| Installer | Per-user Inno Setup after an acceptable R19 runtime; no installer built in R18 | R20 and clean Windows |
| Recognition order | Verified authored order, then observation, otherwise unknown | R01/R07/R08/R12b |
| Corpus/pairs and runtime budget | Small reproducible sample selected for distinct risks | R01/R02a/R11/R25 |
| Real input on hosted runners | Conditional on permitted access, trusted code and private-output restrictions | Screenshot plan; otherwise local validation |
| Distribution signing | Separate from existing checksums/provenance | R22 and protected key provision |

The original research references remain useful options, not proof of a working
prototype: [Inno Setup](https://jrsoftware.org/ishelp/topic_scriptpages.htm),
[PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html),
[Python futures](https://docs.python.org/3.12/library/concurrent.futures.html),
[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [accessible contextual help](https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html).
