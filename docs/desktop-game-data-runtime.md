# Desktop publisher preparation

The desktop API uses the same bounded game-data service and request contract as
the Android host. In Settings, choose **Text only** or **Text + audio**, the
region and languages, then select **Download**. One job discovers and runs the
required stages. Settings shows downloaded bytes and completed steps next to
**Stop download**. The size of the current step is shown separately while the
full size is still being calculated. The bar tracks preparation steps until
the publisher reader can price the final transfer. It reaches 100% after the
selected source has been verified and activated. **Continue download** keeps the last
reported progress and reuses verified files and saved stages, including after
an app restart. Each stage checks its transfer limit and required free space.
For the installed selection, **Check for updates** starts the same bounded job.
It checks the publisher before replacing the active generation. ZZZ recognizes
an unchanged compatible snapshot without rebuilding the dialogue index. On a
new generation it reuses verified original chunks and complete files by
checksum. Up to six missing independent originals can transfer concurrently.
Whole updater files still require the full official file checksum.

Once ZZZ has saved prepared text, publisher confirmation is a separate
resumable step. A temporary network failure during that step is retried within
the job's metadata budget. Continuing later reuses the saved dialogue and
original files. A previous source stays active until its replacement passes
verification.

The requested selection is separate from the accepted downloaded selection:
changing mode, source, targets or region needs a new preparation even when the
publisher revision is unchanged. The old selection remains usable. A completed
old job cannot report the proposed request ready; Settings identifies the
contents actually downloaded.
The live-service desktop Settings dialog uses the same game-data component as
the Android host. Its selected download mode is independent of account features;
an optional reading account is not required to download or use game data.
Linking a reading account can reuse completed publisher files and their matching
active source from the local profile. History and recordings stay in their
existing profile storage.

The local routes are `GET /api/game-data`, `POST /api/game-data/{game}/start`,
`POST /api/game-data/{game}/stop`, `POST /api/game-data/{game}/activate` and
`DELETE /api/game-data/{game}/data`. Writes require the existing `setup` action
header and local-origin checks. Account headers are checked before profile I/O;
the generation also invalidates an A-to-B-to-A account transition. No account lock
is held while invoking service methods. Existing runtime admission and request
drain middleware cover these routes, including DELETE preflights. The previous
`/plan` and `/download` routes remain available to clients that approve
individual stages.

Validated snapshots activate the existing desktop matcher. The host
binds the publisher generation and complete request hash before publishing the
index. Individual authored occurrences retain their own hash in transcripts.
Text-only capture never schedules original audio or changes an authored voiced,
unknown or missing status into unvoiced. The normal legacy capture interfaces
remain available for existing prepared data.

Accepted selections are private, per-profile descriptors. Offline startup and
runtime resume restore those exact selections without transfers. A newer
bootstrap stage or failed download cannot replace the working selection.
Explicit activation can select the latest downloaded ready revision. Deletion
disables that game's downloaded matcher; it removes only the service-owned game
cache. Existing history and recordings outside that cache remain intact.
For Text + audio, the provider must first certify all requested originals are
locally materialized. Capture resolves the exact authored occurrence and saves
a hashed original reference before decoding. Decoded WAV/MP3 recordings live
outside the game cache; playback and Lexirise export resolve the retained
reference, rather than accepting a path from a request. Generation, request,
occurrence and immutable transcript stamps prevent a late decoder from
publishing against a different line or account generation. Historical repair
reopens the recorded source with every network transfer forbidden.

Before deletion the host pauses that game's downloaded matcher and retains
every referenced current-profile original outside the cache. Decode failure
refuses deletion and restores the previous matcher and selection. This work
runs outside the account/capture lock. History already carrying a retained
recording remains playable after cache deletion and a fresh host restart.
Runtime pause cancels preparation and drains the actual executor before SQL
handoff; resume constructs a fresh service and restores the selected sources.

This is a host integration, not an eight-game content-completion claim. Each
packaged provider must independently supply a bounded plan and verified snapshot.
Absent providers report unavailable. A new game also needs its desktop capture
profile. The host's original-recording adapter requires a provider implementing
the shared locally materialized voice contract and the relevant packaged codec.
It does not supply missing game bindings or codecs. Bootstrap-only providers
remain usable as stages in either mode.
No game is marked fully supported from a successful bootstrap or authored test.

Verification uses authored publisher-shaped snapshots through the real shared
service, FastAPI middleware, matcher publication and fresh-host offline restore.
These tests cover transport consent, intentional omission, stage/failure
retention, account generations, deletion boundaries, actual authored WAV playback,
delayed decoder cancellation and worker drain. They do not demonstrate real
publisher corpus preparation, desktop OCR or original-game audio decoding.
