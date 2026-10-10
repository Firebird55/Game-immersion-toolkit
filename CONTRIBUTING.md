# Contributing

Issues and pull requests are welcome. Describe the problem and expected behavior, use synthetic examples, and remove personal paths and account information from reports. Report vulnerabilities privately through the repository's Security tab rather than a public issue.

Fork the repository, create a focused branch (agents use `codex/`), and install Node.js 24 with `npm ci`. Use a GitHub noreply commit email. Read AGENTS.md and RELEASE.md, preserve unrelated work, and commit each completed logical change after relevant checks.

Run `npm run check` and `npm run audit:public` before submitting. Account-write tests must use mocks; never include API keys or require another person's game installation. CI builds without credentials. Keep local data, game assets, recordings, screenshots of personal accounts and diagnostics outside Git.

Shared reader, lookup, reading settings and CSS are maintained in [Lexirise shared components](https://github.com/Firebird55/Lexirise-shared-components). Never edit consumer vendor copies. Propose shared changes there; the maintainer publishes a version and runs `npm run shared:update -- --version <version> --all` to test and commit both consumer integrations.

Changes to UI require Chromium/Firefox, desktop/mobile, keyboard, narrow containers, zoom and Shadow DOM checks as applicable. After the build, run node scripts/browser-e2e.mjs and node scripts/setup-e2e.mjs; native prompts and account writes use mocks in browser tests. Toolkit capture changes require synthetic resolution/DPI and crop-bound regressions. Keep Chinese game transcripts and Migaku mode separate.

Game adapters must verify bilingual text IDs and original Mandarin sources from explicit game references. Add synthetic tests for language checks, ambiguity, malformed bounds, missing sources, and updates. Document limited coverage, particularly Honkai Impact 3rd's reviewed catalog 4.7 subset. Never replace missing mappings with OCR-only or guessed voice support. NTE native reader builds need the .NET 10 SDK; keep all compiled outputs in ignored local caches outside the game installation. See [adapter setup and verification](docs/nte-honkai-support.md).

By submitting original contributions you agree to license them under the included Firebird55 Attribution License. Retain upstream notices for third-party work and document its origin. No copyright transfer or CLA is required. This custom visible-attribution license is not MIT and makes no claim of OSI approval.

Maintainers release from clean main with the documented release command, verify hosted checks, download packages, and verify checksums/provenance. Releases use GitHub-hosted Actions. Previously published release assets and tags are immutable; fix regressions with a new version.
