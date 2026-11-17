# Desktop publisher preparation

The desktop API uses the same bounded game-data service and request contract as
the Android host. Settings can plan either **Text only** or **Text + audio** for a
selected region, source language and translation languages. The plan reports
download and required disk bytes before consent; unknown sizes cannot download.
Bootstrap results remain preparation stages requiring another explicit estimate.

The local routes are `GET /api/game-data`, `POST /api/game-data/{game}/plan`,
`POST /api/game-data/{game}/download`, `POST /api/game-data/{game}/activate` and
`DELETE /api/game-data/{game}/data`. Writes require the existing `setup` action
header and local-origin checks. Account headers are checked before profile I/O;
the generation also invalidates an A-to-B-to-A account transition. No account lock
is held while invoking service methods. Existing runtime admission and request
drain middleware cover these routes, including DELETE preflights.

Validated text-only snapshots activate the existing desktop matcher. The host
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
Runtime pause cancels preparation and drains the actual executor before SQL
handoff; resume constructs a fresh service and restores the selected sources.

This is a host integration, not an eight-game content-completion claim. Each
packaged provider must independently supply a bounded plan and verified snapshot.
Absent providers report unavailable. A new game also needs its desktop capture
profile. The desktop original-recording adapter is still missing: a proposed
ready Text + audio snapshot therefore fails explicitly and preserves the prior
selection. Bootstrap-only providers remain usable as stages in either mode.
No game is marked fully supported from a successful bootstrap or authored test.

Verification uses authored publisher-shaped snapshots through the real shared
service, FastAPI middleware, matcher publication and fresh-host offline restore.
These tests cover transport consent, intentional omission, stage/failure
retention, account generations, deletion boundaries and worker drain. They do
not demonstrate real publisher corpus preparation, desktop OCR or native audio.
