# Language preparation and toolkit release updates

The old “Automatic updates” banner read the legacy ZZZ update manager. Language-aware startup no longer started that manager, leaving its initial checking/2% value permanently visible. The banner now reads `LanguagePreparation` jobs across all configured games. A percentage is not available while reading arbitrary game archives; stage, elapsed time and queue are reported instead.

Automatic language refresh previously returned early when table headers matched the installed-file fingerprint, reader revision and requested targets. It did not validate the table contents. A manual rebuild bypassed that shortcut. Refresh now validates a fresh table instance before reusing it, rejecting empty or invalid records and incorrect locales. The failed user's pre-rebuild snapshot is unavailable, so this establishes a reproducible failure mode rather than claiming forensic proof of that particular snapshot.

All prepared game/language entries run at startup and every two minutes, independently of the active game. Explicit saved selections with a remembered target can recover missing registration. The service does not guess a first-time language, change account preferences, install game packs or modify game files. Failed candidates retain the prior complete snapshot. Setup distinguishes missing prerequisites from active preparation and retrying failures.

The software updater is separate. It reads only the fixed public toolkit release repository. It checks asset origins and sizes, checksums, immutable tag commit, archive paths and packaged provenance before invoking the normal Windows updater. An OS-held lock prevents simultaneous installations; an independent launcher lets installation survive retirement of the old backend. Candidate dependencies and warmup complete before handoff. Private logs and progress stay under `data/toolkit-updates`, excluded from publication. The displayed installed version comes from the active code directory rather than the original launcher folder.

## Upstream and existing-work review

The toolkit already pins shared components 1.0.12, the latest published shared release at review time. No vendored files were edited. The toolkit's Account settings button was still unconditional in that upstream version; its visibility and entry flow are consumer changes. The public Lexirise compatibility watch reported changed documentation/bundle hashes but no added or removed API endpoints. The [official settings API](https://lexirise.app/api-reference) still separates global and per-language preferences and effective translation targets. These fixes do not change that contract or write live account settings. The shared watch baseline is deliberately retained for a separate complete bundle review.

The original checkout was preserved. Its modified/untracked source contents were compared against public main and repository history: 165 already matched main and the other 45 matched older tracked versions. No unique uncommitted source content needed to be copied into this release. Restoring those older files would undo newer game-picker, account and mobile-export work.

## Test coverage review

| Coverage | Existing hosted execution | Decision |
| --- | --- | --- |
| Python backend and export regressions | `npm run test:python` over `backend/tests` and `tests` | Keep the same source tests; add only reported failure cases |
| JavaScript contracts and update logic | `npm test` | Keep; do not duplicate in a new workflow |
| Desktop, setup, capture, offline and OCR browsers | Five existing browser jobs | Keep; reuse their existing account/settings scenarios |
| Windows process identity and update rollback | Full check selector on Windows | Keep; run without a production service occupying fixture ports |
| Extracted distribution | Package job and candidate validation | Keep as the release gate |

Tests are source files shared by local development and GitHub, not separate local-only copies. Removing them would remove hosted coverage. Routine development uses affected checks; release CI owns the comprehensive browser/package gate. Timing and raw local diagnostics remain in ignored `output/checks`.
