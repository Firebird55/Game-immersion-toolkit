# Desktop integration compatibility review

The public Lexirise watch returned advisory exit 2 on 2026-10-30: document and
website hashes changed, with no additions or removals among its 47 endpoints.
The review used the [official API reference](https://lexirise.app/api-reference)
and the public website's settings/lookup modules, without account writes.

The documented writable settings still match the consumer allowlists. Native
language remains read-only; per-language effective translation takes precedence
over a global fallback. Analysis retains token offsets, pending morphology and
grammar states; contextual questions retain their offset-based request and
meaning/reading response. Dictionary translation readiness remains distinct
from an empty result. These contracts match the existing shared client and
backend reading adapter.

The public popup module retains nine tab identities, four definition sections,
the fixed Definition tab and first/last opening preference. Its settings module
retains normalized reading aids and tone palettes. The integration preserves
the shared renderer, popup placement and independent extension mode; this task
does not copy or modify vendor code. Public module URLs, hashes and inspected
bytes remain in ignored review output.

This bounded review found no required shared-component change. The baseline is
intentionally unchanged, so the watch remains advisory rather than concealing
upstream changes. Authenticated account behavior and physical mobile devices
are not established by a public-document review. Reader/browser evidence is
recorded separately in the [reader and LAN plan](reader-lan-completion-plan.md).

The integration retains the pre-existing local-work stash and its private
inventory. Most files already matched the fetched main branch. Remaining
differences include older game-picker removals and account-language restrictions,
older version metadata and check-runner variants; they were not blindly applied
over the current language picker, independent reading mode, or newer CI merge
verification. Their original bytes remain recoverable locally. No stash or
private diagnostic inventory is included in the public repository.
