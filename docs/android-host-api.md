# Android app-local host boundary

The native app embeds the shared Python core and serves the existing desktop
reader over app-local loopback HTTP. It never starts a desktop capture adapter,
development Node server or remote OCR service. The stable app-local origin keeps
the reader's existing storage keys across offline restarts.

All reader and API requests require the app's private, process-random
HttpOnly/SameSite cookie. Native code installs it in the WebView before first
navigation; unauthenticated loopback clients cannot mint a session by opening
the root page. Requests also require
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

## Screen receiver ownership

`POST /api/capture/receiver` accepts `{id, revision, action}` where `id` is a
per-controller UUID, `revision` is a positive safe integer and `action` is
`start` or `stop`. Start additionally requires the current `expected_generation`.
The response contains `generation`, the caller's `receiver_id` and
`receiver_revision`, and actual capture `running`. Conflicts return HTTP 409,
the current generation, a bounded state/message, and no other receiver's ID.
`/api/platform` advertises `receiver_protocol: "leased-frames-v1"`.

Controls and frame admission share the production session lock. Every valid
newer action is recorded before deciding ownership/generation; reused/lower
revisions cannot win later. A stop received before its older delayed start
fences that start. A foreign stop never stops another active receiver. Successful
start/owned stop changes the generation, so already queued OCR loses scope.
At most 128 controller IDs are retained per process without eviction; exhaustion
requires reopening the app and cannot resurrect a retired/stopped receiver.

The owned main HTML includes `meta[name="toolkit-document-epoch"]`. Capture
this value **once per document**, then send `X-Toolkit-Document-Epoch` on receiver
controls and leased frames. Never refresh an old controller's token from a later
snapshot/platform response. A main HTML navigation (document destination, or an
older client without that header) stops capture, releases ownership, retires all
registered old IDs and rotates the token. Assets, API reads and fetches marked
with a non-document destination do not replace this scope. Old-document controls
cannot claim a newly created document even if their first start was delayed.

Leased `POST /api/capture/frame` also carries `X-Toolkit-Receiver-Id` and
`X-Toolkit-Receiver-Revision` alongside the existing generation/frame headers.
All must match the active accepted lease before native OCR is queued. Legacy
start/stop/source/frame requests remain available only without an active lease.
Native pause stops/releases the owner without retiring its document/ID; explicit
resume needs a larger revision and a fresh generation. Shared native resume hints
wait behind earlier native pause fences and stale queued hints are discarded.

`status.capture.library_revision` is the validated private library generation
SHA or null. Source UI can reset on a real library replacement, including a new
library for the same game/locale. It must not use `source_generation` as the
library identity: each accepted receiver start/stop changes that generation.
Atomic library activation invalidates capture and releases the receiver before
the new index activates. No stop response claims that a request abort rolled
back a previously accepted start.
