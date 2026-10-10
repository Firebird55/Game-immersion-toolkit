# Agent workflow

Read this file and RELEASE.md first. Inspect git status and preserve unrelated work, local data, capture calibration and credentials.
Commit each completed logical change; run relevant checks before committing and all checks before pushing. Do not leave completed changes uncommitted.
Use main for releases; task branches start with codex/. Keep all repositories private.
Shared component source is owned by the sibling lexirise-shared-components repository. Never edit vendor/lexirise-components in consumers.
For a shared change: test, commit, publish a new shared version, then in that shared repository run npm run shared:update -- --version <version> --all. Check and commit both consumer integrations before considering the change finished.
Never store keys in source, artifacts, logs or workflow secrets. Real account verification is read-only; test writes with mocks.
Use npm run release -- --version <semver>; monitor hosted Actions and verify downloaded assets/checksums before reporting released versions and URLs.
GitHub-hosted Actions only. Do not couple delivery to Argo or the cluster.
Mobile browser previews may be published publicly from this private repository through the dedicated GitHub Pages workflow, as authorized by the user. Publish only the mobile preview's allowlisted static files. Desktop services, credentials, local catalogs and reports stay private. Keep the fast preview workflow independent of release packaging and show the deployed commit in the page and reports.
Run npm run lexirise:watch to inspect public Lexirise changes. Exit 2 means review required, not permission to modify accounts. Review settings, lookup UI, AI docs/endpoints and language options; update the baseline only after reviewed compatibility changes.
Test desktop/mobile, Shadow DOM, Firefox/Chromium, browser zoom and Windows DPI/capture bounds. Preserve toolkit's Chinese game transcripts and separate Migaku mode.
Create new local project folders below %USERPROFILE%/Google Drive/Notities/claude, never Documents.
