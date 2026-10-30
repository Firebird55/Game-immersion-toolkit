# R19 authored unvoiced export experiment

Status: **bounded source-worker and acc68be extracted Windows checkpoint passed**.
Reviewed 2026-10-30 against source checkpoint
`22d99059b88892f87bce0118fd5e15a556ed6459` plus this change.
This extends the [compiler-free helper experiment](r19-compiler-free-helpers.md)
and [R19 completion plan](r19-completion-plan.md). It closes neither the broad
B2 game-format matrix nor B3 voiced export acceptance.

## Fixed behavior

The original Half-Life reader already distinguishes confirmed sound-free
`screen_message` records from unknown titles and messages with attached sound.
Mobile preparation previously discarded every Half-Life row without an audio
binding and initialized a voice service unnecessarily. It now retains only
that adapter's explicit unvoiced screen messages, with no voice service or
decoder lookup. Source/translation identities and the installed-source
fingerprint remain checked. Legacy snapshots, claimed voiced capability and
unexpected audio bindings require preparation again. An absent voice binding
by itself never establishes silence.

Other games retain their existing verified-performance gates. All 25 game
entries, Half-Life's eight official locales and missing-pack states remain in
place. This creates no official original-speech transcript, voice export or new
language binding. [The Half-Life audit](game-audits/halflife.md) retains those
coverage limitations.

## Actual worker and consumer path

`backend/unvoiced_export_probe.py` authors a non-executable install marker,
GoldSrc BSP v30 entity lump and English/Simplified Chinese title tables. It
contains one sound-free bound title, one title with an absent attached sound
and one unused title. It invokes the real `game-index`, `language` and
`mobile-export` entrypoints. Normal export mode prepares the language table,
selects eligible records, verifies the source fingerprint and atomically
publishes the portable Mobile Library ZIP; it does not use `--catalog-only`
or call `export_library` directly with an invented record.

The probe verifies both `en` → `zh-Hans` and `zh-Hans` → `en` identities, one
eligible row, zero voice packs, exact catalog segment sizes/SHA-256, portable
bundle membership, unchanged completed-bundle reuse and unchanged fixture
bytes. Preparing absent German fails with
`halflife_language_pack_missing`; a failed normal export retains the previous
pointer and completed bundle. A missing attached WAV and an unused title remain
unknown and never enter the library. No account, installed game or network
source is required.

The source regression executes those actual isolated Python workers, then
opens both resulting ZIPs through the production mobile parser. Separate
tripwires prohibit account-store/voice-service initialization and verify that
changing the source invalidates preparation. Contradictory or stale snapshots
cannot promote unknown dialogue to unvoiced coverage.

## Evidence and remaining gates

The seven focused source checks passed locally using the selected Python 3.12
environment and Node 22. This is a source-only functional observation. The
development doctor still reports unavailable Windows host and nonmatching
applicable dependency metadata; it is not a full development/packaging pass.
The integrated `runtime_probe` now uses this real worker path and emits bounded,
sanitized counts, locale identities and bundle hashes.

The exact extracted checkpoint at `acc68be` passed in
[run 41144087092](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41144087092).
The downloaded [source/metadata review](r19-frozen-checkpoint-20261031.json)
verified both locale directions, actual index/language/mobile-export workers,
one unvoiced row and zero voice packs per case, missing-pack refusal, unchanged
export reuse and previous-bundle preservation. Application inventory and owned
cleanup passed. Native binaries remain runner-local; this is authored-format
Server 2025 evidence rather than installed-game or clean Windows 11 acceptance.

Clean Windows 11 25H2 ordinary-user operation, real OCR/capture/DPI, selected
installed language-pack operation and broader game/audio export remain open.
General game decoding still depends on a rights-reviewed codec chain; the
bounded Xiph FLAC experiment does not provide it. Source delivery, exact native
dependency closure and helper redistribution reviews remain independent gates.
The production runtime remains disabled and `r19_complete` remains false.
PR #59 is unchanged. No installer, release, tag or production activation belongs
to this experiment.
