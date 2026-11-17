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
adapter accepts the maintained account store's protection-call shape; it does
not import desktop credentials or enable account HTTP routes. The debug native
self-test uses a separate authored alias and saved ciphertext, checks new-instance
reopening, tamper rejection, randomized output and key non-exportability, and
reports whether a previously saved blob reopened. A process restart/upgrade must
be established by the runtime harness, not the new-instance check alone.
`protected_accounts` remains false until maintained account services, request
pinning and transcript/library isolation are actually integrated. Provider-backed
storage follows the [Android Keystore system](https://developer.android.com/privacy-and-security/keystore);
no claim of hardware backing is made for an emulator or untested device.

The account-session component reuses `AccountStore` and `PreparedCaptureSession`
with independent app-private settings, library pointers and SQLite histories.
Selection stages a candidate outside the common session lock, then publishes
only if its intent and credential generation still own activation. Source
generation increases across replacements; an A→B→A switch cannot revive an old
import or source callback. Native HTTP DTO line IDs reserve a bounded activation
epoch above the unchanged uint32 SQLite ID, remaining safe JavaScript integers;
all native line routes must validate and decode them before use. This component
is available behind an explicit native-host opt-in; production startup retains
the existing account-disabled mode until the matching frontend contract lands.
Maintained account/reader transports accept explicit environment/protected-root
policy; desktop defaults remain unchanged, while Android disables environment
and desktop credential fallback.

The opt-in transport advertises `account_protocol: scoped-accounts-v1`. Account
selection/registration, library import/cancellation, settings, source controls
and frames require `X-Toolkit-Account-Generation` captured from the rendered
context. Preview image requests carry the same integer as the readonly
`account_generation` query parameter. Epoch-qualified IDs bind audio/ranges,
favorites, reading and exports to the exact account activation. Old A requests
remain invalid after switching through B back to A. Import receipts retain weak
session references so completed jobs cannot keep obsolete full game indices.

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
