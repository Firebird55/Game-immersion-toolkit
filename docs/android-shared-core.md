# Android shared-core host

Issue [#81](https://github.com/Firebird55/Game-immersion-toolkit/issues/81) requires
an installed Android host, the existing desktop reader, and shared production
matching, confirmation and transcript behavior. It does not permit a hosted-page
wrapper or an Android-only matcher.

The platform-independent [confirmation policy](../backend/capture_confirmation.py)
is used by desktop capture and the [prepared session](../backend/prepared_session.py).
Both use `MultilingualTextIndex`, the official locale/voice contracts,
`SettingsStore` and `TranscriptStore`. No desktop capture or account transport is
imported to bootstrap the local session.
The desktop and portable hosts also use the same
[floating-caption policy](../backend/floating_caption_policy.py) for Endfield
top/film/tutorial and Wuthering song admission, exact authored occurrence
selection, complete-source alias equivalence, menu reset and voiced two-frame
confirmation. PlayerName templates use the maintained Wuthering index helper;
the APK ships that actual module.

## Private prepared libraries

[The portable writer and importer](../backend/prepared_library.py) use
`toolkit-prepared-library-v1` STORE ZIPs. A checksum/size manifest covers the full
format-2 text snapshot and content-addressed, already-decoded MP3/WAV clips.
Original archive references are replaced with local clip references. Account
credentials, executable code and arbitrary paths are not importable members.
The writer preserves only bounded source fingerprint, regional edition, source
mode and reader revision as source provenance. It does not copy URL collections,
account diagnostics or arbitrary snapshot metadata. Immutable generations retain
that source identity; existing transcript models do not expose all of it per line.
Verified original full-WEM SHA/speaker fields remain untouched when a prepared
clip is missing. They are then provenance on an explicit unavailable row, never
authorization for original-voice equivalence or a fabricated audio asset.
Publisher top/song/film counts, including an explicit zero playable-song count,
retain the same admission meaning after portable export/import.

The writer accepts a source snapshot, destination and decoded clips supplied by
the existing original-voice services. It preserves official texts, voice state,
context/paragraph labels, player branches, capture channels, authored predecessor
links and OCR anchors. Clips can be selected by a callback for branches sharing a
text ID. It verifies audio again while writing before replacing the destination.
Export has its own cancellation callback and optional atomic publication guard;
cancelled writes retain the previous completed archive. This is separate from
the HTTP import cancellation protocol.

Import validates checksums, bounds, the complete `LocalDialogue` contract and the
actual production index before publishing a pointer. Previous generations remain
available to saved history/favorites and recordings. Long validation does not
hold the capture lock. Only final publication/activation is serialized.
The format allows up to one million dialogue records, 512 MiB of UTF-8 text,
256 MiB of checksum manifest, 128 MiB per clip and 64 GiB per library. The earlier
250,000-record prototype cap excluded ordinary publisher inventories; the new
bounded capacity leaves room for current ZZZ/Genshin inventories and normal
updates. These are format ceilings, not a claim that every phone has sufficient
memory/storage. Import streams files, frees its validation table before building
the shared index and checks actual free storage before staging. Target memory,
large-library indexing and fuzzy performance still need device measurements.

The earlier `proxy-mobile-bundle-v1` browser export is a different format. It
omits some production status/context metadata. It is not silently treated as a
full prepared-core snapshot: desktop export integration or explicit conversion
is required before migration is complete.

## Evidence and limits

Authored desktop fixtures cover stable confirmation, rejected replay/late frames,
wrong player branches, source gaps, separate missing-audio capture, corrupt and
cancelled imports, and retained history/favorites/old clips after an update and
restart. The shared session never resumes capture automatically after restart.

The native host now constructs a signed, installable debug APK for both ABIs.
The reader is the byte-identical maintained desktop frontend in an opaque
`reader.bundle`; Android's asset merger otherwise discards `_next` paths and
changes gzip filenames. Native extraction verifies the shared manifest and
atomically publishes a build-identity directory. The local HTTP origin retains
its first allocated port in private storage so the existing reader preferences
and storage keys survive process death. An occupied port causes an explicit
startup failure instead of silently creating a different preference origin.

The host provides SAF ZIP selection, private storage, lifecycle pause and bundled
MLKit text recognition. Remote frames are bounded, newest-pending-only, and
generation checked after OCR. A dimension change invalidates confirmation and
requires reconnecting. Local Android game capture/MediaProjection is unavailable;
protected account activation requires the matching scoped frontend. The remote iOS screen
transport is a separate shared frontend capability, not desktop capture.

The common Capture setup preview reads only the most recently admitted native
frame, in memory. Its normalized crop and explicit centered 16:9 picture use the
same physical geometry helpers as desktop capture and native OCR admission.
The JPEG encoder is serialized, bounded to 1280 pixels and one MiB, and its result
is checked again against the current document, receiver lease and generation
before publication. Pause, settings, import, rotation, stop and document changes
discard that frame; preview GETs never restart capture or change its scope.
HTTP tests exercise actual image crops and delayed-encode invalidation. The
debug Android self-test additionally decodes native JPEG crops of authored
letterboxed/ultrawide color quadrants; target execution is separate evidence.

Native OCR also exposes a bounded optional `presentation_lines` evidence lane
without changing ordinary block matching. Each original MLKit line keeps its
own text and physical rectangle; its score is the minimum genuine line/element
confidence. Missing, invalid or unavailable values remain zero or are rejected;
no default confident score is substituted. The pinned common API 19.1.0 exposes
these methods; [Google documents their range and unavailable-zero behavior](https://developers.google.com/android/reference/com/google/mlkit/vision/text/Text.Element).
This supplies input for a separately validated game presentation classifier;
the evidence lane alone does not authorize a new text/voice binding.

`AccountProtection` supplies a native-only AndroidKeystore AES-256-GCM blob
primitive with randomized nonces, app/blob-format-bound associated data, a
non-exportable OS key and bounded authenticated envelopes. Missing keys or
tampered blobs fail without plaintext/key-file fallback. The Python platform
adapter accepts the maintained account store's protection-call shape and never
imports desktop credentials. The debug native
self-test uses a separate authored alias and saved ciphertext, checks new-instance
reopening, tamper rejection, randomized output and key non-exportability, and
reports whether a previously saved blob reopened. A process restart/upgrade must
be established by the runtime harness, not the new-instance check alone.
Normal native startup now enables the maintained account services with their
request pinning and transcript/library isolation. Provider-backed
storage follows the [Android Keystore system](https://developer.android.com/privacy-and-security/keystore);
no claim of hardware backing is made for an emulator or untested device.

Prepared Endfield libraries now retain only the canonical, bounded original
world-dialogue UI descriptor. Full-frame voice admission recognizes that
validated descriptor even without film/top counts. Its stateless original
speaker/control/complete-caption proof runs after predecessor observations and
cannot feed predecessor state. Unknown native line confidence, missing controls,
profile overlays or unmatched extra caption sentences retain the shared veto.

NTE uses the same `NteDialogueContext` as desktop for a directly preceding
original speech node. Its native lane requires genuine positioned line geometry
and confidence; it reuses desktop subtitle/menu filtering and also sees choices
outside the configured crop. Short right-panel labels which the maintained
filter cannot distinguish from options disable native context too. This can
conservatively suppress context with top controls until their ownership is
evidenced; it does not assert a clear menu state. Missing/uncertain evidence disables that context,
and a resolved successor cannot arm another graph edge. Generic Endfield
predecessor handling is excluded for NTE. Normal independent captions keep their
existing matcher. The authored target fixture reports these source-policy cases
separately as `authored-positioned-spans-not-sdk-gameplay`; actual native game OCR
and physical sender acceptance remain separate evidence.

The account-session component reuses `AccountStore` and `PreparedCaptureSession`
with independent app-private settings, library pointers and SQLite histories.
Selection stages a candidate outside the common session lock, then publishes
only if its intent and credential generation still own activation. Source
generation increases across replacements; an A→B→A switch cannot revive an old
import or source callback. Native HTTP DTO line IDs reserve a bounded activation
epoch above the unchanged uint32 SQLite ID, remaining safe JavaScript integers;
all native line routes must validate and decode them before use. This component
is enabled by normal native startup through the existing protected provider and
shared account interface. An empty account store keeps the existing toolkit
root's local library/history usable without a connection. A previously saved
owner reopens its own local data and retains permission for ordinary read-only
settings/language requests; constructor/snapshot restoration is local-only and
network failure does not block local capture or import. Account writes still
require explicit user actions. No reconnect gate is added on every launch.
Maintained account/reader transports accept explicit environment/protected-root
policy; desktop defaults remain unchanged, while Android disables environment
and desktop credential fallback.

The native transport advertises `account_protocol: scoped-accounts-v1`. Account
selection/registration, library import/cancellation, settings, source controls
and frames require `X-Toolkit-Account-Generation` captured from the rendered
context. Preview image requests carry the same integer as the readonly
`account_generation` query parameter. Epoch-qualified IDs bind audio/ranges,
favorites, reading and exports to the exact account activation. Old A requests
remain invalid after switching through B back to A. Import receipts retain weak
session references so completed jobs cannot keep obsolete full game indices.

The shared React reader now pins these headers and preview queries to its
rendered native generation. An account change retires detached audio, pending
settings/export UI ownership, private screen links and old transcript views.
Conditional account discovery prevents mixed account/settings reads. Android
does not expose the desktop-only TextMap update button. Default native account
activation remains off pending recovery and native UI acceptance.

`scripts/android-account-ui-e2e.mjs` runs the actual frontend against the
maintained Android HTTP/session services in Chromium and Firefox at 412×915.
Authored account transport and desktop credential protection are explicit
mocks. Registration, import, capture, favorite, separate empty second-owner
library and A→B→A history restoration pass; stale generation mutations reject.
This establishes browser/service behavior, not Android Keystore or device OCR.

The same two browser scenarios now corrupt their authored protected store,
verify that private history and imports lock, explicitly re-enter the verified
owner and restore the existing library/history/favorite. The original unreadable
store remains byte-identical after recovery. Account status reads permit the
locked state while retaining generation checks. Device capabilities refresh
after account/recovery changes and native resume, so successful recovery restores
import/screen controls without adopting a replacement document nonce. This
recovery UI remains separate from actual Android target acceptance.

The authored browser/service flow also saves capture preferences, explicitly
creates the owner's sentence destination and exports the retained original
recording through the maintained service and immutable mocked remote transport.
The second owner starts with independent preferences and no export ledger;
switching back restores the first owner's favorite, settings and qualified
export reference. No real account is mutated by this acceptance scenario.

The API delegates settings, destination ownership/selection, word/grammar
reading and sentence/original-audio exports to the maintained services. Requests
pin credentials, local line identity and account session before network work and
recheck ownership before responding. The official translation-field projection
is shared with desktop presentation and leaves canonical stored rows unchanged;
an absent selected translation stays absent. All remote test writes use mocked
transports. The native core fixture additionally exercises maintained account
registration, scoped import/capture, A→B→A guards and encrypted-store reopening
using an authored Keystore alias; it reports the provider separately from its
deterministic desktop comparison results.

Build with the owned SDK/wheelhouse, Python 3.12 and Java 17 or later:

```text
pwsh scripts/build-android-app.ps1 -SdkRoot <sdk> -Wheelhouse <wheelhouse> \
  -Frontend <verified-desktop-frontend> -BuildRoot <private-build-directory> \
  -Python <build-python> -JavaHome <jdk> -DownloadGradle
```

The script verifies the pinned Gradle archive and offline wheels, constructs the
actual frontend/core APK, audits native ABIs and 16-KiB load alignment, verifies
APK signatures and ZIP alignment, and emits candidate provenance. Its persistent
host-local debug key supports local candidate upgrades; it is not a production
update identity. No production key or workflow secret is used.
The separate [owner-host signing path](android-owner-signing.md) creates a
durable protected identity for update-in-place candidates without CI secrets;
its actual APK version and certificate are checked and recorded in provenance.

The manually dispatched `android-shared-core.yml` workflow builds on Windows
(the pinned NDK compiler supplier), then transfers the checksum-bound APK to a
Linux KVM Android emulator. `scripts/probe-android-runtime.mjs` exercises the same
authored desktop fixture, actual native media playback, bundled native OCR,
WebView import/frame/OCR/transcript flow, audio range requests and favorites.
It disables network before first launch and force-stops/restarts the app to
check the actual shared reader's mode, playback speed, font and pinyin settings,
history and original clips. A green archive/build audit is not a substitute for
this runtime job. Until the job passes, target runtime acceptance is unverified.
The isolated continuity checkpoint `3e7ba322` passed the actual emulator workflow
in [run 44028898025](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/44028898025),
including native OCR into the shared reader, real audio/background handling,
offline restart and a same-signer APK update. This does not establish acceptance
of newer account/game cohorts or physical devices.

The workflow also has an explicit authored-account scenario. It launches the
existing DEBUG-only startup mode in its separate app-private root and Android
Keystore alias, and uses the immutable two-owner mock transport. Actual shared
UI controls import a generated library, capture through the native frame/OCR
path, favorite a line, save owner preferences and export its original recording
to the mock service. A→B→A checks reject stale import/settings/receiver/audio
requests and retire real detached playback. A guarded fixture corrupts only the
isolated authored credential store, then requires explicit verified-owner UI
recovery while preserving the unreadable store, library, transcript and voice.
Restart and APK-update checks reopen the recovered protected store. The existing
offline/native checks remain
mandatory. An authored File payload exercises the import handler; physical SAF
picker and real-account writes are not established by this scenario. Its native
acceptance requires a successful matching workflow run and runtime proof.
The authored protected-account UI/recovery scenario passed on actual Android in
[run 44038164999](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/44038164999)
at `cc0bf061`. Normal protected-account startup and the ordinary shared-UI history
migration subsequently passed at `ea395b1f` in
[run 44050647499](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/44050647499),
including retained original voice/favorite, offline restart and an actual
same-signer APK update. Both cohorts used API 34 x86_64; real account writes,
native document-picker behavior and physical devices remain separate.

The normal-startup cohort additionally uses the real browser-history exporter
whitelist to create a bounded, mixed-language authored backup. Actual shared UI
controls preview without changing existing rows, import, page to older history,
show the oldest favorite and repeat the import without duplicates. Native
process-restart and APK-update checks must retain both that history and the
original voiced favorite. This exercises the import path; it does not establish
physical mobile bookmark execution or restore recordings absent from the backup.

The native document chooser follows the actual shared file input's ZIP or JSON
accept declaration. Unsupported declarations cancel safely; both importers still
validate the selected bytes independently. The hosted native probe now opens
Android's DocumentsUI, selects each disposable authored file from Downloads and
returns its content URI to the real WebView import control. This additional SAF
scenario needs matching target evidence; direct File injection from earlier
cohorts did not establish native picker behavior.

## Recent Android compatibility

Reviewed 2026-11-17: the host uses standard Android APIs, with no device-model
branch. Its compile/target SDK is now 36 with AGP 8.10.1 and checksum-pinned
Gradle 8.11.1, the combination supported by the
[Android plugin compatibility table](https://developer.android.com/build/releases/agp-8-10-0-release-notes).
[Chaquopy 17.2](https://chaquo.com/chaquopy/doc/current/android.html) supplies Python
3.12.15 for arm64-v8a and x86_64; both native dependency sets are built from the
same pinned source. The dependency floor remains API 24, and does not establish
runtime acceptance on old Android versions. No 32-bit variant is provided.
The four [bundled ML Kit 16.0.1 recognizers](https://developers.google.com/ml-kit/vision/text-recognition/v2/android)
cover Latin, Chinese, Japanese and Korean without a model download.

Targeting current Android requires handling
[enforced edge-to-edge layouts](https://developer.android.com/develop/ui/views/layout/edge-to-edge).
The native parent applies current system-bar, display-cutout and keyboard insets
around the shared WebView after layout changes. The authored native probe checks
actual portrait/landscape/portrait reader bounds and uses the real DocumentsUI
picker for both ZIP and JSON. These new cases have no target pass until their
matching workflow completes.

| Runtime | Evidence |
| --- | --- |
| API 34 / x86_64 | Earlier continuity, protected-account and normal-startup/migration cohorts passed; SDK-36 host changes require a fresh pass. |
| API 36 / x86_64 | New hosted matrix entry; runtime, insets, picker, offline capture, accounts and updates pending. |
| arm64-v8a | Actual APK/native-source/ELF/signature audits; physical ARM64 runtime pending. |
| Physical recent Android | Pending device acceptance; an emulator profile is not a manufacturer certification. |

The official stable Google APIs emulator feed currently supplies API 36; it has
no API 37 x86_64 entry in that feed. The candidate therefore tests the available
stable image rather than claiming an unavailable image. The probe records the
actual device API and native page size. Every APK retains the existing
[16-KiB native ELF and ZIP checks](https://developer.android.com/guide/practices/page-sizes),
including bundled SDK libraries; x86_64 execution does not prove ARM64 execution.

Recovery reference evidence distinguishes the actual Windows build host
(Python 3.12.10 / SQLite 3.49.1) from the local reference interpreter
(Python 3.12.2 / SQLite 3.43.1) and embedded Android Python 3.12.15. The newer
host engine creates its own `sqlite_stat1` planner table during the maintained
store's `PRAGMA optimize`; the retained authored evidence proves all existing
schema entries and complete application rows stay identical. Successful reopen
checks therefore preserve every application schema entry, row/sequence, index,
integrity check and non-database file byte, with an exception only for that
proven internal statistics table. Locked-state file inventories and original
credential bytes remain exact. Mutation regressions cover transcript fields,
favorites, sequences, schemas/indexes, extra tables, original clips, settings and
library pointers. The [SQLite pragma documentation](https://www.sqlite.org/pragma.html#pragma_optimize)
describes the engine's analysis maintenance; these references do not infer the
Android SQLite version from the Windows build host.
The native shared fixture executes prepared import, production matching,
confirmation and original clip lookup for all six live-service games, including
an actual Wuthering PlayerName template. The APK audit additionally checks its
exact delivered `app.imy` namespace and current source receipts.
`scripts/probe-android-closed-core.py` imports that **actual packaged bytecode**
in an isolated host Python process with desktop dependency wheels, rejects
repository backend masking/desktop platform imports and compares the six-game
results with the maintained desktop source. This is owned-source delivery and
reference-behavior evidence; Android ABI execution still requires the emulator.

Physical Android/iOS sender tests, long-session fuzzy-match performance, audio
focus, protected-account UI/native acceptance, complete desktop migration/export UI,
stable production signing/update identity and full issue #81 acceptance remain
open. No release is made by this change. Bundled libraries retain their upstream
notices; production distribution still requires the complete Android dependency
license/source inventory, including the embedding runtime and native OCR SDKs.

Build/runtime references reviewed November 16, 2026:
[Chaquopy embedding](https://chaquo.com/chaquopy/doc/current/android.html),
[bundled MLKit text recognition](https://developers.google.com/ml-kit/vision/text-recognition/v2/android),
[Android WebView debugging](https://developer.android.com/develop/ui/views/layout/webapps/debugging),
and the [emulator action](https://github.com/ReactiveCircus/android-emulator-runner).
