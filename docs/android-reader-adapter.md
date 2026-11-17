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

## Screen reception

The shared reader exposes **Connect screen**, **Reconnect** and **Stop screen**
only for the native `remote-stream` capability with `leased-frames-v1` ownership.
It reuses the reviewed VDO.Ninja frame transport. The private viewer link remains
in memory; the native API receives bounded PNG frames, never that link. OCR,
confirmation, matching and recording stay in the shared native host.

Each document caches its owned epoch once. Source changes, changed geometry,
backgrounding and Stop invalidate the current generation. Frames carry the
receiver ID and revision; old requests cannot restart a stopped source or adopt
a newer document. Changing the selected game or imported library disposes the
previous receiver. A failed Stop response is shown as uncertain rather than
claiming capture ended. The shared capture dialog retains its existing game
regions and player-voice choices.

Android refreshes the native snapshot while visible and after foregrounding;
it does not retry the desktop WebSocket transport, which this host does not
provide. Node race fixtures cover source ownership, late encoding, reconnection,
rotation, backgrounding and refused controls. These are control-plane checks;
native OCR, actual WebView integration and an actual iOS broadcast require their
separate runtime evidence. This screen-reception implementation does not claim
physical sender acceptance.

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
matcher contract. The automatic queue also writes the complete prepared Android
contract. Its existing per-PC rules, pause state, languages and destination stay
in place. The export format participates in job identity, so an unchanged game
is re-exported after migration. Android ZIPs have distinct names; old browser
archives and revision folders remain available for recovery. Each updated ZIP
must be imported in the Android app. Export does not establish autonomous
publisher preparation on the phone or iOS frame transport acceptance.

The capability policy has authored regression fixtures. Type checking and the
actual static desktop frontend build cover these shared components. Android
embedding, import cancellation, local voice playback and lifecycle acceptance
also require the native host's actual tests; browser or build results alone are
not physical Android or iOS-sender evidence. No Android release is declared here.
