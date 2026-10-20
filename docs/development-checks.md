# Faster development checks

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

Unchanged browser bundles are reused only when both source fingerprints and
output hashes match. A local no-change browser build took 0.04 seconds on the
maintainer's machine; this is a cache-hit measurement, not a clean-build promise.
Checks record elapsed time under ignored `output/checks/`.

Update the capability catalog in `public/mobile-capture/games-data.json`, then
run `npm run docs:generate`. All four README and language-matrix versions are
generated together; `npm run docs:check` detects drift. Keep storefront language
availability separate from reader implementation and expected support.

`npm run ocr:manifest` is an explicit maintainer operation that verifies pinned
model downloads and records sizes and SHA-256 hashes. Normal builds do not fetch
optional language models. Browser users download only their chosen OCR packs.
