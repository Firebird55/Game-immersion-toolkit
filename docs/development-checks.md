# Faster development checks

Use `npm run check:changed` for working changes. For a branch, fetch the actual
PR target and add `-- --base <target-remote>/<target-branch>`. A fork targeting
this upstream repository normally uses `upstream/main`; `origin/main` is correct
only when origin is the actual PR target. The report records the resolved base
SHA. An invalid or unavailable base fails without valid branch evidence.
Documentation changes check generated guides, links and publication
safety. Python, desktop and mobile changes select their relevant tests. Unknown
inputs and dependencies use the comprehensive gate. Mixed desktop/mobile edits
run unit tests once. Changes to the selector, evidence runner, shared test server,
Python resolver or CI gate select the full suite. Mobile companion and offline
update harness changes also select the offline update/restart scenario.

## Prepare the development environment

Run `npm run dev:doctor` (or supply the same `-- --base ...` / `-- --full`
scope) first. It checks only prerequisites for that scope: supported Node/npm
lock metadata, Python 3.12 and pinned distributions when needed, browser binaries
and generated assets. It never installs packages, downloads models, imports
native OCR, starts the app, or accesses game/account data. Exit 0 means required
prerequisites were observed, 2 means prerequisites are unavailable, and 1 means
invalid configuration. A passing doctor is not a passing test run.

Use Node 24, `npm ci`, and `npm run dev:prepare` to prepare JavaScript and
generated mobile assets. Install Playwright engines explicitly with
`npx playwright install chromium firefox webkit` when browser checks are needed.
For backend work create a project `.venv` using Python 3.12 and install the
locked requirements into it. Some packages and acceptance checks need Windows.
Development runners choose `PYTHON`, then this project's `.venv`, then PATH
(`python` on Windows, `python3` elsewhere). An incomplete project venv is an
error; a running companion's installed environment is never used as a fallback.
The production updater keeps its independent environment validation.

`npm run test:infra` runs dependency-light regression tests for selection,
evidence, environment detection, CI aggregation and preview isolation. It does
not replace selected application tests.

## Evidence and CI acceptance

Each executed check creates `output/checks/runs/<id>.json` before starting and
sets `output/checks/latest.json` to a pointer to that run. Progress and final
results update only the run file atomically, so an older run finishing cannot
overwrite the newer pointer. Records contain source HEAD,
resolved base, a hash of tracked changes and nonignored untracked content, command
statuses and elapsed times. Source changes during execution invalidate the run.
An interrupted run left `running` is unfinished, not a pass. A failed aggregate
`npm run check` does not claim its inner scripts passed.

Commands are recorded as passed, failed, not-run, delegated or unavailable.
Split browser jobs and the source-audit job supply separate evidence; delegation
alone proves no test passed. Windows-only checks remain unavailable locally on
other hosts. Exit 1 means command failure and exit 2 means invalid source/base
evidence. Delegation and unavailable native checks retain exit 0 for orchestration
but leave the report incomplete. Read the report status as well as the exit code.
JSON records omit command output, absolute interpreter paths, file contents
and environment values. Only these allowlisted metadata files are uploaded;
ignored raw logs, screenshots and fixtures are not automatically safe to publish.

PR publication audit checks submitted HEAD, while application/browser jobs check
GitHub's exact event merge SHA and verify both event parents. The stable
`required-checks` context fails on failed, cancelled, missing or invalid jobs.
The browser matrix may be skipped only for validated selective scope, whose
selected browser scenarios run inline. Maintainers must select `required-checks`
in branch rules and require an up-to-date base. Parent verification alone proves
only the event snapshot. Manual dispatch evidence does not replace this PR gate.

The desktop, setup, language/account and React-state preview harnesses use
OS-assigned ports retained by their own Wrangler listeners, unique temporary
registry/persistence directories and per-run `output/e2e/` artifacts. Cleanup
targets only owned processes. Offline update tests keep one origin through
update and browser restart, then remove their owned profile.
SIGINT/SIGTERM clean up owned previews. If a Windows parent has already exited,
its remaining descendants cannot be safely identified: cleanup fails explicitly
and retains the temporary runtime. Forced OS termination cannot run cleanup.

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
