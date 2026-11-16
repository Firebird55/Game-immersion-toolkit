# Android app-local host boundary

The native app embeds the shared Python core and serves the existing desktop
reader over app-local loopback HTTP. It never starts a desktop capture adapter,
development Node server or remote OCR service. The stable app-local origin keeps
the reader's existing storage keys across offline restarts.

API requests require the app's private, process-random HttpOnly/SameSite cookie,
the exact local Host and a matching Origin when supplied. Native frames have a
10 MiB encoded limit and a separate generation/sequence boundary. Native OCR
decodes only bounded images; the receiver does not grant iOS screen capture.

## Import cancellation

`POST /api/library/import` carries a UUID in `X-Toolkit-Import-Id` and a bounded
raw prepared-library ZIP body. `POST /api/library/import/cancel` carries JSON
`{"import_id":"…"}`. Cancellation has a separate lock, so it can settle while
upload/validation runs without blocking pause or the old complete library.

Cancellation and atomic publication share the same final guard. A successful
cancel returns `state: "cancelled"`, `cancelled: true` and the original
`source_generation`. Once the pointer has committed, cancellation returns HTTP
409 with `state: "already_committed"` and `cancelled: false`. An interrupted
response is never described as a rollback. The UI must refresh current state.

Cancel-before-register requests become tombstones. At most 128 IDs are retained
per app process; they are never evicted in a way that resurrects a cancelled
upload. After that limit the app requires a restart before a new import. At most
two upload workers may settle concurrently, and only one noncancelled import
may prepare at a time. Restart changes the private cookie, invalidating all
old-process requests.

Real local HTTP tests cover early cancellation, cancellation during a partial
upload, cancellation racing the actual pointer replacement, and late committed
responses. Authored tests also verify origin/cookie enforcement and cancellation
receipt bounds. These tests do not establish Android native runtime, physical
screen transport or account-keystore acceptance.
