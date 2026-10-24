# Faster development checks

Use `npm run check:changed` for working changes. For a branch, fetch the actual
PR target and use `npm run check:changed -- --base <target-ref>`. Use `origin/main`
only when `origin` is the target repository; a fork may require `upstream/main`.
Record the base SHA and tested commit. See the
[verification rules](ai-development-workflow.md#verification-and-evidence).

The [rework roadmap](rework-roadmap.md) assigns independent workstreams and
[R25](rework-roadmap.md#r25--reduce-test-cost-and-keep-necessary-coverage) reviews
test necessity and cost. The [architecture study](rework-architecture.md) explains
the boundaries and the [screenshot regression plan](screenshot-regression-plan.md)
defines planned image/package tests. These documents do not implement the new
runner, remove tests or modify workflows. All engineering prose is in English,
regardless of the language used to request a change.

## Current check selection

Documentation changes check generated guides, links and publication safety.
Python, desktop and mobile changes select their relevant checks. Unknown inputs
and dependencies use the comprehensive gate; mixed desktop/mobile edits run unit
tests once. Stage new documentation before checking links so `git ls-files`
includes it. Do not run Python, OCR or full browser suites for documentation alone.

`npm run check:full` runs the comprehensive local gate when needed. Release tags
run full checks and packaging on GitHub-hosted Windows. Atomic release pushes
delegate comprehensive main-branch checks to the tag for the same commit while
retaining documentation/publication checks. Normal branch pushes do not duplicate
PR checks. Manual **Checks and release** runs validate a branch without publishing.

Release checks build the frontend once, then use that build in separate desktop,
setup, capture, offline-storage and OCR jobs. Every required group must pass before
packaging. A failed group can be rerun without repeating successful groups. Reuse
unchanged browser builds only when source fingerprints and output hashes match.
Checks record elapsed time under ignored `output/checks/`; a cache hit is not a
clean-build timing promise.

For a Windows offline failure, run **Online companion** manually with `check:
offline` on the relevant branch. It exercises cache activation, offline reloads
and updates without unrelated matrices. Firefox owns a fresh profile and tests
reopening after a browser restart. Browser caches follow the pinned Playwright
version. Log the failing operation before browser cleanup can obscure it.

Frame-source changes select native-frame and receiver/OCR/reader scenarios, plus
applicable pairing/recovery checks. `scripts/mobile-vdo-source-e2e.mjs` uses
synthetic cross-origin viewers; `scripts/mobile-source-e2e.mjs` runs real OCR and
catalog matching. Live-device probes are private and opt-in. See the
[source decision](mobile-vdo-decision.md) and
[physical protocol](mobile-capture-verification.md).

The source scenario probes MP4/WebM support separately. Only the known
Windows/WebKit runtime with both codecs explicitly unsupported may leave that
video-adapter subcase unverified; unexpected failures/timeouts still fail. Native
PNG, English/Chinese OCR, slow results, explicit Stop and recovery remain testable.
The screenshot plan does not need video decoding to test those image paths.

## Supported targets and proposed CI changes

Windows is the supported desktop target. Relevant macOS/WebKit checks provide
mobile-browser evidence; physical iOS and native Windows checks remain distinct.
**Do not add Linux product/browser verification.** Linux working incidentally
does not make it a supported platform or justify extra test jobs.

At this documentation baseline, the Online companion workflow still includes
Ubuntu browser checks, and earlier evidence includes Linux codec tests. R25 must
remove or relocate those test jobs to Windows and, where needed, macOS/WebKit,
preserving useful browser/codec coverage. This documentation does not claim that
migration has happened. Linux runners used solely for static publishing are
infrastructure, not Linux compatibility tests; do not remove publication machinery
just because its runner is Linux.

## Necessary tests and pruning

Review existing tests, including the thousand-plus Python cases, by the distinct
failure they catch, current supported behavior and measured runtime. Record a
small keep/consolidate/remove mapping for each reviewed area. Remove redundant,
obsolete and implementation-mirroring tests; identify equivalent retained coverage
or why the behavior is retired. There is no target test count.

Protect useful regressions and account/data/locale isolation, voice identity,
migration, cancellation, lifecycle and publication behavior. Never remove a
failing test, add a skip or relax a threshold to hide an unresolved defect.
Removing genuine duplication is planned maintenance, not a blanket prohibition
on deleting tests.

New tests must name the failure and explain why existing cheaper coverage is
insufficient. Test pure logic at unit/contract level, with a few real OCR/package
cases for integration. Avoid tests that restate implementation details or inspect
file layout instead of behavior. Simple reversible copy/style changes need no
new tests. Review expensive browser cases before adding overlapping coverage.

Build once, reuse fixture/model setup and deduplicate selected scenarios. Measure
before/after wall-clock time in `output/checks/` and set a realistic budget before
expanding a costly job. Run affected cases on PRs and a bounded supplemental sample
on manual/candidate runs. Repeat passed broad suites only for relevant changes,
failures or unresolved concerns. Full packaging remains a candidate/release gate.

## Planned screenshot and language regressions

Use fixed screenshots for game-specific presentation gaps, plus a few supported
language combinations through actual-format mobile packages. Do not prioritize
ZZZ or multiply every game by every language, browser and resolution. Inventory
all active games, then choose cases for distinct untested behavior or reported
defects. Keep known regressions fixed and record any rotating supplemental sample.

Use the built mobile artifact, normal ZIP import and production OCR/controller/
matching path. Independently annotated expected/forbidden identities prevent an
empty or wrong-locale result from passing. A single screenshot tests visible text;
ordered screenshot sequences and controlled observations cover timing and stale
work. Label injected OCR separately from real image OCR. Live YouTube playback
is not a required input source.

Public Actions jobs use authored screenshots, small synthetic catalogs and owned
audio. Real screenshots/packages stay private by default; optional trusted hosted
processing must satisfy the screenshot plan's access and output restrictions.
Never publish the supplied real package or private media through caches, traces,
failure artifacts or Pages. A synthetic pass cannot replace a missing real-input
result. Report exact commit/artifact/corpus/package/model versions and selected
game/presentation/language cases, elapsed time and pass/fail/not-run/unavailable.

R07a characterizes current production; R13c extracts the mobile controller; R07b
reuses it for screenshot replay. Keep extraction and behavior fixes independently
reviewable. Check affected consumers on the integrated commit. M2 is the combined
user flow; M3 is candidate/device evidence. A completed independent improvement
can ship through the normal authorized process without waiting for every stream.

## Generated guides and OCR model metadata

Update `public/mobile-capture/games-data.json`, then run `npm run docs:generate`
when changing capabilities. `npm run docs:check` detects generated-guide drift.
Keep storefront availability separate from actual reader and package support.
Existing localized product guides are intentionally multilingual; the English-only
rule concerns engineering prose, not removal of product localization.

`npm run ocr:manifest` is an explicit maintainer operation that verifies pinned
model downloads and records sizes/SHA-256. Normal builds do not fetch optional
language models; users download only chosen packs. Regression fixtures must select
their required verified models explicitly instead of downloading every language.
