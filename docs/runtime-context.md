# Runtime and reader context

The companion uses small, explicit ownership boundaries. Request sequence numbers
are local cancellation tokens; they are never backend state versions.

## Snapshot and event contract

`context` contains `runtime_id` (an opaque per-process incarnation),
`state_version` (a monotonically increasing publication revision in that runtime),
and `account_generation` (including A → B → A transitions). A complete HTTP
snapshot takes this stamp **before** reading its payload. A WebSocket publication
increments the revision before sending. A delayed payload must never be relabelled
with the current revision after its work finishes. Consumers commit a snapshot as
one unit and reject it if a newer event was accepted while it was in flight.

A connection or account reset invalidates all outstanding requests. Only the
current connection/request scope may adopt a different runtime ID. Revisions from
different runtimes cannot be compared. Polls are single-flight with one coalesced
follow-up; abort also invalidates result publication when a transport ignores it.
Unmount removes subscriptions and invalidates callbacks. Account and language
setup reads follow the same cancellation boundary.

## Reader and preparation context

A reader session/cache key includes account generation, game/source locale (and
its study language), effective translation language and settings version. Resolve
the per-language effective target before constructing a session. Settings version
is a fingerprint of the adopted settings, not the latest HTTP request number.
Lock, account replacement and target changes retire old sessions and their async
results. Keep the original transcript text and independent Migaku mode.

Language preparation owns each worker and its extraction process tree. On Windows,
a bootstrap joins a kill-on-close Job Object before launching the extractor. The
backend retains the job handle, reaps the bootstrap, terminates the job, and
confirms zero active processes before reporting successful shutdown. Unconfirmed
cleanup remains a quiesce failure after a worker exits or updates restart, and
blocks new preparation until the backend is restarted. Restarting preparation
after close creates a fresh cancellation event/generation. Close cancels and joins owned
work with a deadline; failure to stop is an explicit quiesce failure, never a
successful handoff. Check ownership under the publication lock before atomic
index replacement, metadata updates and activation. A restarted generation must
not clear the cancellation token of an older job. Existing complete indexes are
retained until a valid replacement is ready. The publication gate also guards
generation changes. Metadata uses a separate data lock, released before external
activation; this avoids reversing the account → language order of Setup/export
readers.

## First-round integration ownership

Runtime process recovery owns the PowerShell launcher/updater/helper and their
Windows fixtures. Language-worker cancellation owns the language-preparation
module and the builder/stop-updates sections of `backend/api.py`. UI state owns
snapshot/event transport and account/language read sections of that API; those
changes are integrated sequentially with the worker changes. Mobile reader
context stays in consumer code. Shared vendored source is not edited.

Targeted check selection names concrete browser and Windows scenarios. A local
run reports Windows fixtures as unavailable when it cannot execute them; only a
Windows run supplies that evidence. Candidate/release CI retains the complete
browser and package gates.
