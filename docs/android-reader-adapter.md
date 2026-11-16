# Shared reader on the Android host

The Android host serves the existing desktop `Companion` and reading components.
An owned `toolkit-host-platform=android` HTML meta marker selects device controls;
it is a presentation hint, not authentication. The host must protect its local
HTTP API independently. Ordinary desktop and connected iOS readers keep their
existing controls and same-origin transport.

`GET /api/platform` reports supported library import, protected accounts and
capture source. Missing or invalid capability reports leave device actions
unavailable. Authored observations are a prototype input, not proof of receiving
game frames. Device capture controls remain disabled for that input mode.

## Library import and cancellation

The device picker posts a prepared ZIP to `/api/library/import`, with a fresh
`X-Toolkit-Import-Id`. The host owns validation, storage bounds and publication.
The reader refreshes the actual snapshot after a successful import or an
uncertain connection result; a lost HTTP response does not imply rollback.

Cancellation posts the same `import_id` to `/api/library/import/cancel`.
Only a successful response with `cancelled: true` permits the reader to state
that the previous library was kept. A 409 response must explicitly identify
`state: already_committed` before the reader reports an already completed import.
Aborting a fetch or closing the panel alone is not server-side cancellation.
Late callbacks are scoped to their original request and cannot replace a newer
panel's result.

The account entrypoint follows the host's protected-account capability. Browser
extension compatibility is not implied by reusing the reader in a WebView.
Private library import does not automatically migrate another browser origin's
history, credentials or preferences. See [migration](android-migration.md).

## Evidence boundary

The desktop's manual **Export Android library** action uses the same supervised,
account- and learning-language-scoped worker as existing exports. It requests
the complete prepared format-2 contract and writes `toolkit-prepared-library-v1`
through the shared portable writer. Conditions, authored predecessors, player
variants and voiced/unvoiced/unknown distinctions survive the transfer. Audio
decoding uses each exact source binding rather than the default player-ID view.
The worker rechecks source/account identity before atomically replacing the last
completed ZIP. The original game files and credentials are not serialized.

Older browser archives require a new export; they do not contain the full native
matcher contract. Existing automatic browser exports remain a separate legacy
path pending migration. This manual export connection does not establish
autonomous publisher preparation on the phone or iOS frame transport acceptance.

The capability policy has authored regression fixtures. Type checking and the
actual static desktop frontend build cover these shared components. Android
embedding, import cancellation, local voice playback and lifecycle acceptance
also require the native host's actual tests; browser or build results alone are
not physical Android or iOS-sender evidence. No Android release is declared here.
