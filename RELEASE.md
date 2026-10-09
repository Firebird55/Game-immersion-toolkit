# Game immersion toolkit release runbook

Install Node 24; npm ci; npm run check. Install Python 3.12 dependencies with python -m pip install -r requirements.lock.txt. CI runs on Windows without live games or native OCR.
The shared package in vendor is pinned by version and sourceCommit. Edit shared source in the sibling lexirise-shared-components repository, publish there, then run npm run shared:update -- --version <version> --all from that repository.
GitHub-hosted Actions only, never Argo or cluster dependencies.

## Explicit release
From clean main: npm run release -- --version 0.2.0 (increment for later releases).
Stop the running companion with scripts/stop-companion.ps1 before local checks/releases: Windows locks the built frontend while it is serving. Restart it after verification.
The command runs integration checks, validates the vendor pin, scans secrets/history, updates metadata, commits and pushes an annotated version tag.
Monitor gh run list and gh run watch <id> --exit-status. Tag workflow rebuilds and tests before publishing.
Download using gh release download <tag> --repo Firebird55/Game-immersion-toolkit --dir <empty-folder>.
Verify each SHA256SUMS entry and PROVENANCE sourceCommit against the release tag before installation.

## Installation and updates
Extract the distribution ZIP to a new folder, stop the old companion, and run scripts/setup.ps1. Setup uses npm ci and locked Python dependencies; node_modules from the old ZIP is never required. Windows Snipping Tool supplies native OCR files during user setup, not CI. Preserve the old data directory (databases/game indexes/audio) and local DPAPI key; never delete them. Per-PC capture settings remain in LOCALAPPDATA/Proxy Transcript/settings.json. Existing game lines remain Chinese. Use the capture preview to calibrate unusual layouts; Hito automatic box detection follows current game resolution and zoom.
For guided setup, double-click Install.cmd instead. Its optional game-folder popup saves validated locations in LOCALAPPDATA/Proxy Transcript/game-paths.json, separately from capture settings/keys. Choose Game Folders.cmd can reopen it later. See INSTALL.md and the included CONTRIBUTING.md/AGENTS.md before agent work. Game assets are read from the user's own installation, never redistributed.
Use Reload from Lexirise to read account preferences. Only Save to Lexirise writes remote settings; legacy local display preferences are not automatically uploaded.

## Compatibility watch for agents
npm run lexirise:watch reads public API/AI docs and website bundles, without a key. Exit 2 flags changes for review; .watch/report.md and .json summarize endpoint changes and settings/lookup/language review areas.
It does not silently update code or account settings. Follow AGENTS.md, update the shared source and baseline after review, synchronize both apps and run Firefox/Chromium/mobile/zoom and capture regression checks.

## Rollback
Download and install a prior release using the same steps. Keep user data, local preferences and keys. Do not rewrite tags. For dependency rollback, import the prior shared release using shared:update, then publish new consumer versions.
