# Managed game data and retained recordings

The shared `GameDataService` owns bounded estimates, explicit download consent,
staging, local source validation and managed-cache deletion. Providers are
maintained first-party modules selected by `game_data_providers`, with platform
capabilities supplied by the host. A missing reader/runtime remains unavailable;
UI controls or a downloaded bootstrap archive do not establish readiness.

Every request binds region, study/source locale, requested translations and
`content_mode` (`text` or `text-audio`). A revision identifies an immutable
publisher generation, including manifest/source identity, rather than a marketing
version alone. Planning permits bounded metadata; unknown transfer or disk sizes
disable Download. Text-only requests reject audio transfers before connection.
Text + audio readiness requires every playable binding's original to be verified
and locally materialized. Local MP3/WAV conversion may finish later.

## Host ownership and HTTP

Android uses the current app-private profile's `game-data` directory. The owner
token includes runtime, account generation and the exact capture session. A normal
game/source activation does not change that token. Account selection, recovery or
session replacement revokes earlier operations, including an A-to-B-to-A cycle.

The HTTP adapter pins the owner under the session lock, releases that lock before
calling service methods, passes `expected_owner`, then checks again before
responding. This prevents a delayed A request from starting work in B's directory.
The lock order at publication is service lock followed by session/account lock;
provider I/O and decoding never run under the OCR/session lock.

Routes are `GET /api/game-data`, `POST /api/game-data/{game}/plan`,
`POST /api/game-data/{game}/download`, and `DELETE /api/game-data/{game}/data`.
Mutations require the existing app-origin/session checks, setup intent header and
captured account-generation header. Responses expose bounded state and sizes,
never private source handles, keys or provider diagnostics.

The maintained activation callback validates ownership and installs the actual
production `MultilingualTextIndex` under the session lock. Returning successfully
is its commit point: a subsequent account switch must not delete that already
committed source from the old profile. Callback failures restore previous pointer
bytes and the previous matcher. Startup restores only the persisted exact source
identity, locally, in the background. A delayed startup restoration cannot replace
a newer source. A broken pointer keeps history available without selecting a
different profile or falling back silently to an old backup library.

## Original recordings

`PreparedCaptureSession` can directly activate a validated publisher snapshot and
`OriginalVoiceSource`; it reuses the existing matcher, confirmation, positioned
presentation policies and SQLite transcript store. ZIP import remains a separate
compatibility path, not the direct-download requirement.

The capture lane only checks the source's pure local `has` predicate. After
confirmation it stores the complete authored occurrence plus opaque source
descriptor in `OriginalRecordings`, then queues local decoding outside OCR locks.
Provider `restore` and `resolve` are offline; absent original bytes require another
explicit download plan. A retained MP3/WAV is content-addressed, bounded and
hash-checked before its transcript receives playable audio. Generation changes
cancel pending work and prevent late history/audio publication. Unknown or omitted
voice intent is never relabeled unvoiced.

Retained clips live outside the deletable game-data cache. Delete first stops the
active source and preserves every still-referenced original, without holding the
OCR lock. If a decoder is busy or an original cannot be retained, deletion fails
and leaves the source cache intact. An older explicitly downloaded original may
be decoded locally after choosing text-only; this cannot trigger a new transfer.
Already retained recordings, history and favorites survive deletion and process
restart.

## Evidence boundary

Authored tests exercise actual local HTTP, provider protocol, shared index,
confirmation, SQLite, generated WAV hashes, range playback, favorites, source
deletion, fresh-host restart and account races. They also verify that direct
text-only capture invokes no decoder. These are host reference tests, not evidence
that any production publisher reader or native codec runs on Android. Actual
provider closure and fresh Android target acceptance remain separate requirements.
