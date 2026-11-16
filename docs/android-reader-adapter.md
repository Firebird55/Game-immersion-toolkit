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

The capability policy has authored regression fixtures. Type checking and the
actual static desktop frontend build cover these shared components. Android
embedding, import cancellation, local voice playback and lifecycle acceptance
also require the native host's actual tests; browser or build results alone are
not physical Android or iOS-sender evidence. No Android release is declared here.
