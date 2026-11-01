# Windows release metadata verification — 2026-11-01

Version 0.23.0 was tagged at `eb27e74e084dde6f4b2dab0a7b486838a8bcb781`,
but was not published. Its application tests, all five browser groups, extracted
source archive and Linux/macOS native targets passed. Windows rejected its
managed-reader probe on two runners before native construction completed.
The failed tag remains unchanged.

The same helper passed seven actual native checks when rebuilt locally from the
tagged source. The diagnostic branch also passed all three native targets in
[run 41332335598](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41332335598).
These passes did not substitute for the failing tag's acceptance.

## Reproduced cause

The original probe returned only a generic failure. Fixed, allowlisted phase and
reason codes now distinguish checkout, receipt, inventory and execution failures
without publishing paths, raw process errors or account diagnostics.

[Exact-tag diagnostic run 41334508105](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41334508105)
kept the original tag in a separate checkout and loaded only its backend. An
external reporter observed `checkout-cleanliness` / `source-checkout-dirty`.
Only `VERSION`, `package.json`, `package-lock.json` and `release-version.json`
were changed; `other_changed` was false. The original version-preparation step
rewrote those files on hosted Windows despite their already-correct version.
Their committed values matched the intended metadata; a local normalized-content
comparison alone had not exposed the hosted checkout difference.

The source-integrity gate therefore behaved correctly. Skipping that gate or
accepting an arbitrary dirty checkout would not fix this release failure.

## Correction and acceptance boundary

Preparation must retain the existing bytes when the requested metadata is already
correct, including Windows line endings. An actual requested version change still
updates metadata. Receipt, source-identity and immutable-input requirements remain.

The follow-up diagnostic first requires the known original failure, restores only
the four files changed by its own preparation step in the disposable CI checkout,
then exercises the corrected preparer and rebuilds clean helper/dependency
receipts in new output directories. Both original and corrected reports are
diagnostic-only and cannot authorize publication.

The next patch release still requires its own clean-main tag, full hosted gates,
exact native receipts, downloaded checksums/provenance and local installation.
Version 0.23.0 must not be retagged or installed as a verified release. This
correction does not establish additional physical-device or gameplay coverage.
