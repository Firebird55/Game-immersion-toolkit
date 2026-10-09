# Install Game immersion toolkit

Windows companion for verified bilingual Hito, ZZZ, PRAGMATA and Cyberpunk 2077 transcripts, native OCR and Lexirise/Migaku reading.

## Installation

1. Download the latest private release ZIP and SHA256SUMS while signed in to GitHub. Verify the checksum before extracting to a writable folder.

2. Install Python 3.12 with its Windows launcher, Node.js 24 (npm 10+) and Windows Snipping Tool. Double-click Install.cmd. No administrator access is required for the app itself.

3. The optional popup lets you browse to installed game folders. Hito needs resources/app.asar; ZZZ needs ZenlessZoneZero_Data (StreamingAssets or Persistent); PRAGMATA needs PRAGMATA.exe and re_chunk_*.pak files. Cyberpunk needs bin/x64/Cyberpunk2077.exe and archive/pc/content language archives, including the official Mandarin voice pack. Select the installation folder, not an archive. Skip keeps automatic detection and existing preferences.

4. Launch Start Proxy Transcript.cmd. Set the Lexirise key with the protected local prompt documented in README.md, or use Migaku separately.

5. After moving or updating games, re-run Choose Game Folders.cmd and restart the toolkit. It reads assets in place; never put game archives or extracted assets into GitHub.

Game files are necessary for game-verified capture and original audio, but not for browsing saved transcripts. They are not bundled or uploaded. Per-PC locations live in LOCALAPPDATA/Proxy Transcript/game-paths.json. Capture calibration and DPAPI keys remain separate. Cancel or a blank picker field preserves existing locations.

## Agent and contributor instructions included in the installer

Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [RELEASE.md](RELEASE.md). Inspect status; preserve unrelated work and local data. Commit logical changes, run checks before pushing, edit shared code only in its source repository, and use the documented release command. No credentials or game assets belong in commits or installer bundles. Installer setup is not permission for an agent to publish or change account settings.

## Checksums and rollback

Download SHA256SUMS beside the release assets; compare SHA-256 hashes before running an installer. Use gh release download <tag> --repo Firebird55/Game-immersion-toolkit --dir <empty-folder> for authenticated downloads. Install an earlier immutable release to roll back, keeping local data, keys and userscript-manager storage. See [release runbook](RELEASE.md).
