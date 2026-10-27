# Agent workflow

Read this file and RELEASE.md first. Inspect Git status and preserve unrelated work, local data, calibration and credentials. Commit each completed logical change after relevant checks; run affected checks before pushing. Use `codex/` task branches and release from clean main.

This is an owner-authorized public repository with sanitized history. Never reintroduce the private backups or old private refs. Use a GitHub noreply author/committer email. Do not publish personal profile paths, keys, recordings, databases, game files or account diagnostics.

Shared component source belongs to Lexirise-shared-components. Never edit `vendor/lexirise-components` in consumers. For shared changes: test, commit, publish a new version, then run `npm run shared:update -- --version <version> --all` in the shared repository. Check and commit both consumers before considering the shared work complete.

Real account verification is read-only. Test all account writes with mocks. Store credentials only in host protected storage, never workflow secrets. Preserve toolkit Chinese transcripts, its independent Migaku mode, and userscript storage keys.

Run `npm run lexirise:watch` for public upstream changes. Exit 2 means inspect settings, lookup UI, AI/API docs and language capabilities, not permission to alter accounts. Record the baseline only after compatibility review.

Test desktop/mobile, Shadow DOM, Firefox/Chromium, zoom and Windows DPI/capture bounds as applicable. Run `npm run audit:public` before publication. Release through `npm run release -- --version <semver>`; monitor GitHub-hosted Actions and verify downloaded checksums and provenance. Delivery must not depend on Argo or a cluster.

Only allowlisted static mobile-preview assets may be published on Pages. Desktop services and local data stay on the PC. Follow host-specific workspace location instructions without copying personal paths into the public repository.

Routine development: read docs/development-checks.md. Use `npm run dev:doctor` before installing or preparing dependencies, and `npm run check:changed` for uncommitted changes. For branch checks, fetch the actual PR target and pass its remote ref with `-- --base <target-remote>/<target-branch>`; do not assume origin is the target. Check evidence lives in ignored output/checks. Incomplete, delegated, unavailable or source-invalid evidence is not a full pass. Full browser and packaging validation belongs to hosted CI.

## Adding games and languages

Every new game must support all of its official voiced languages, including regional editions and languages whose voice packs are not installed on the development PC. Research the publisher's documentation and Steam language matrix, then compare them with the installed game's language manifests and formats. Record dated source links and distinguish interface, subtitle and spoken languages; a global storefront may omit regional packs.

Implement absent-pack languages from evidenced shared schemas, locale identifiers and original-voice bindings, with representative format tests. A missing local pack must produce an actionable missing-pack state, not remove the language from supported choices. Never invent a voice binding or treat a missing recording as unvoiced. Distinguish implementation supported by format evidence from playback actually verified with installed files; do not claim native validation for an absent pack.

In the same change, update `public/mobile-capture/games-data.json`, the README support matrix, generated language guides (`node scripts/generate-language-docs.mjs`), installation instructions, the game's language/coverage report and `docs/game-audits/README.md`. Keep official audio/text availability, implemented coverage, regional limitations and remaining gaps explicit. Update detection, setup, capture, export and public-capability regression coverage, and run documentation checks before committing. A new game is not complete while its matrix or user documentation is stale.
