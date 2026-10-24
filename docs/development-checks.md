# Faster development checks

The [rework roadmap](rework-roadmap.md) defines three parallel workstreams, task dependencies,
acceptance criteria and shared milestones for the proposed rework. Its [AI development workflow](ai-development-workflow.md)
describes bounded tasks, independent review and evidence handoff; implementation
has not started merely because these planning documents exist.
The [architecture research](rework-architecture.md) documents current boundaries,
proposed migrations and the limits of existing runtime and artifact evidence.

Use `npm run check:changed` for working changes, or add `-- --base origin/main`
for a branch. Documentation changes check generated guides, links and publication
safety. Python, desktop and mobile changes select their relevant tests. Unknown
inputs and dependencies use the comprehensive gate. Mixed desktop/mobile edits
run unit tests once.

`npm run check:full` is available when a comprehensive local run is useful.
Release tags run the full suite and packaging on GitHub-hosted Windows. Release
pushes are atomic: the main run delegates comprehensive tests to the tag for the
same commit, while retaining documentation and publication checks. Normal branch
pushes do not duplicate pull-request checks. Pages retains browser smoke tests,
Mac WebKit transport verification and publication validation; the release gate
owns the full browser matrix.

Release checks build the frontend once, then run desktop, setup, capture, offline
storage and OCR checks in separate Windows jobs using that same build. All groups
must pass before packaging. A failed group can be retried without rerunning the
successful groups. Manual **Checks and release** runs exercise this complete gate
on a branch without publishing a release. Local `check:full` still runs every group.

For Windows-specific offline failures, run the **Online companion** workflow
manually with `check: offline` and the branch being investigated. This exercises
the production build and browser cache activation, offline reloads and updates
without running unrelated browser matrices. Firefox uses a fresh owned profile
and also verifies reopening after a real browser restart. Browser caches follow the pinned
Playwright runtime, so an application version bump does not invalidate them.
Offline checks log their current operation and report errors before browser
cleanup, so a stalled WebKit process cannot hide the original failure.

Unchanged browser bundles are reused only when both source fingerprints and
output hashes match. A local no-change browser build took 0.04 seconds on the
maintainer's machine; this is a cache-hit measurement, not a clean-build promise.
Checks record elapsed time under ignored `output/checks/`.

Mobile frame-source changes also select the native frame bridge and complete
receiver/OCR/reader scenarios, alongside the retained browser pairing and
recovery checks. `scripts/mobile-vdo-source-e2e.mjs` uses deterministic synthetic
cross-origin viewers in normal CI; `scripts/mobile-source-e2e.mjs` exercises real
OCR and catalog matching in Chromium, Firefox and WebKit. Private live-device
checks are opt-in and must never publish viewer links or captured game images.
See [the native source decision](mobile-vdo-decision.md) and
[physical acceptance protocol](mobile-capture-verification.md).

The native scenario separately probes real MP4/WebM playback before exercising
the existing browser-video adapter. Only the known Windows/WebKit runtime with
both codecs explicitly unsupported may leave that subcase unverified; timeouts,
unexpected playback failures and adapter/OCR failures still fail the check.
The complete native PNG, English/Chinese OCR, slow-result, explicit-Stop and
automatic-recovery scenarios continue on Windows/WebKit. Real browser-video
adapter coverage remains required on macOS/WebKit and Linux/Chromium/Firefox/WebKit.

Update the capability catalog in `public/mobile-capture/games-data.json`, then
run `npm run docs:generate`. All four README and language-matrix versions are
generated together; `npm run docs:check` detects drift. Keep storefront language
availability separate from reader implementation and expected support.

`npm run ocr:manifest` is an explicit maintainer operation that verifies pinned
model downloads and records sizes and SHA-256 hashes. Normal builds do not fetch
optional language models. Browser users download only their chosen OCR packs.
