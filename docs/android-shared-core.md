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

The earlier `proxy-mobile-bundle-v1` browser export is a different format. It
omits some production status/context metadata. It is not silently treated as a
full prepared-core snapshot: desktop export integration or explicit conversion
is required before migration is complete.

## Evidence and limits

Authored desktop fixtures cover stable confirmation, rejected replay/late frames,
wrong player branches, source gaps, separate missing-audio capture, corrupt and
cancelled imports, and retained history/favorites/old clips after an update and
restart. The shared session never resumes capture automatically after restart.

This foundation alone does not prove an installable APK, Android dependency
loading, physical-device OCR/playback, an iOS screen sender, protected Android
account storage, desktop-export UI integration or complete issue #81 acceptance.
Native build, source transport, lifecycle, migration and physical tests remain
separate acceptance requirements. No release is made by this change.
