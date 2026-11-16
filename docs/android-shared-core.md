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
requires reconnecting. Local Android game capture/MediaProjection and protected
account storage are not implemented by this prototype. The remote iOS screen
transport is a separate shared frontend capability, not desktop capture.

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

The manually dispatched `android-shared-core.yml` workflow builds on Windows
(the pinned NDK compiler supplier), then transfers the checksum-bound APK to a
Linux KVM Android emulator. `scripts/probe-android-runtime.mjs` exercises the same
authored desktop fixture, actual native media playback, bundled native OCR,
WebView import/frame/OCR/transcript flow, audio range requests and favorites.
It disables network before first launch and force-stops/restarts the app to
check the actual shared reader's mode, playback speed, font and pinyin settings,
history and original clips. A green archive/build audit is not a substitute for
this runtime job. Until the job passes, target runtime acceptance is unverified.

Physical Android/iOS sender tests, long-session fuzzy-match performance, audio
focus, protected Android account storage, complete desktop migration/export UI,
stable production signing/update identity and full issue #81 acceptance remain
open. No release is made by this change. Bundled libraries retain their upstream
notices; production distribution still requires the complete Android dependency
license/source inventory, including the embedding runtime and native OCR SDKs.

Build/runtime references reviewed November 16, 2026:
[Chaquopy embedding](https://chaquo.com/chaquopy/doc/current/android.html),
[bundled MLKit text recognition](https://developers.google.com/ml-kit/vision/text-recognition/v2/android),
[Android WebView debugging](https://developer.android.com/develop/ui/views/layout/webapps/debugging),
and the [emulator action](https://github.com/ReactiveCircus/android-emulator-runner).
