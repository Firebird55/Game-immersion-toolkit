# Public launch audit — 10 October 2026

The owner authorized public toolkit/shared repositories, sanitized history with private backups, and retirement of old hosted releases and Actions history. Emulingo remains public with its existing storage and update identity.

## Publication boundaries

Publication scans cover main, task branches, tags and origin tracking refs, author/committer/tagger identities, reachable source blobs, tracked files, and decompressed ZIP/tar packages. Local Codex checkpoint refs and the old private archive remote are excluded from publication and never pushed. GitHub forks and independent prior downloads cannot be recalled.

Verified Git bundles, old release packages, checksums, Actions artifacts/logs and commit maps are retained in a private backup directory outside the repositories. Final anonymous checks showed that GitHub could still serve superseded commits after a force-push, so the original hosted repositories were made private and renamed as private archives. The public repository names were recreated from clean fast-export/fast-import copies containing only sanitized reachable objects; pre-sanitization commit IDs must not resolve there. Personal profile paths and contact identities were sanitized; private scratch/data paths and personal documentation screenshots were removed from published history. Unknown historical icon payloads were removed; current original geometry is reproducible through scripts/generate-project-icons.py.

The remote pre-publication audit inspected 9,042 entries. No supported credential pattern was found; personal paths were found in old hosted packages/output. The approved toolkit v0.2.0–v0.2.4 and shared v1.0.0–v1.0.6 releases and pre-publication Actions output were retired before visibility changes. New releases include licenses, full bundled dependency notices, source provenance and checksums.

## Application behavior

Reading preferences are local and share controls/CSS with Emulingo. The toolkit exposes account preferences and game-deck destinations separately. Existing user colors and Chinese transcripts retain their meaning; Migaku reading mode remains separate.

Exports use credential-scoped local destinations and state. Selecting or finding/creating a deck is explicit; existing destinations and ownership are verified before upload. Legacy ledger files remain local; completed records are reused only after verified ownership/membership. The owner's prior destinations were verified with read-only requests and saved as local selections. No real-account writes were performed during implementation.

## Verification and limitations

Shared contracts, toolkit types/JavaScript/Python checks, mocked account isolation, Chromium/Firefox responsive settings, Emulingo Shadow DOM/isolated-world behavior, zoom/DPI/capture scenarios and mobile WebRTC tests are required. Public packages and fresh publication clones must pass privacy checks and downloaded checksums/provenance verification.

Dependency scans are not a guarantee that all secrets or copyright issues can be detected. FireRedTeam model hashes were compared with a pinned upstream revision and Apache-2.0 notices are included. Proprietary OCR binaries, game assets, local captures and credential files are excluded. SECURITY.md tracks the remaining upstream braces build-tool advisory.

The public Lexirise API documentation fingerprint and documented endpoints are unchanged. The website bundle fingerprint changed; the compatibility watcher continues to report that advisory rather than silently accepting an unverified UI baseline.

Mobile layout checks run in emulated browser viewports. Actual iPad background screen capture and mobile OCR feasibility still require the manual two-device test; public hosting does not establish that result.

The first toolkit release candidate was blocked because browser tests had produced a Wrangler runtime database beneath dist. Packaging now excludes runtime state and logs while retaining deployable assets; the regression test exercises this exact boundary. No installer artifact was published from that failed candidate.

The final frontend audit identified Geist font files downloaded by next/font outside the npm tree. Their full copyright/OFL notice is retained in source and the bundled license aggregate; artifact validation checks both notices when fonts are present. Toolkit v0.2.7 supersedes v0.2.6 with this notice correction.
