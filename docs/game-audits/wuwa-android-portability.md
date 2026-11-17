# Wuthering publisher preparation on Android

This November 17, 2026 audit concerns independent on-device downloads from the
publisher. Importing a PC-prepared library is not acceptance for this flow.
The current publisher route reads the evidenced PC release format; this does
not assert support for extracting an Android installation's different archives.

## Existing components and remaining platform work

| Stage | Existing implementation | Android status |
| --- | --- | --- |
| Regional release discovery | `wuthering_release.launcher/discover`: HTTPS, regional launcher checksums, current resource/dub manifests, immutable snapshots and final-pointer checks | Python logic is portable. Verify device TLS, HTTP range responses and cancellation/byte limits through the app downloader. |
| Initial/archive parameters | Official APK-v2/AXML/ELF static default producer, original UUID-owned KeyLists/PakData, exact FGuid and complete original indices; separately retained historical legacy provenance | The current original Android module actually opens both complete Global bootstrap indices without legacy key inputs. This Python/cryptographic logic needs device crypto/protected-store acceptance. Actual default rotation is unverified; encrypted manifest JSON still has a frozen/protected `ENTRY_KEY`/`ENTRY_IV` dependency. |
| Publisher archives | Owned Python v12 PAK reader, encrypted/aligned ranges, complete index SHA-1s, native member checksum coverage, uncompressed/Zlib/Oodle entries | No IoStore or C# reader is needed for the evidenced publisher PAK lane. Raw `custom=2` entries checksum only their 2,048-byte encrypted prefix; do not call selective reads whole-member/PAK hash verification. Unsupported archive formats remain explicit errors. Installed-file `NteReader` is a separate desktop lane. |
| Package decompression | Uncompressed and Zlib use Python; Oodle currently runs the pinned desktop Node/ooz tool | `PortablePackage` takes explicit range and Oodle providers. It cannot fall back to desktop processes. Android still needs an actual packaged Oodle provider and original-file parity proof. |
| Text and authored bindings | SQLite ConfigDB, redirected locale shards, FlatBuffer fields, original story/movie/music caller graphs, selected-dub/Rover ownership | Reuse these joins rather than generating Android-only mappings. Verify SQLite read-only URI and deserialize support, AES and the exact module closure on-device. |
| Wwise sources | Authored bank/media relationships and source shape checks | Bank parsing is Python. All eight inspected current originals use RIFF/Wwise Opus format tag `0x3041`, stereo 48 kHz; this finite sample is not a complete codec census. Existing standard 5.1 ownership/mapping guards must also survive. |
| Audio probing and decoding | Desktop `vgmstream` probe/full/window subprocesses | Needs the shared app-native audio runtime. Revalidate rate, channels, complete frame count, source layout and seek origin using the same admission policy. A missing decoder cannot become unvoiced or silently remove film/song coverage. |
| Waveform matching | NumPy/SciPy matching against original recordings | Requires compatible packaged runtime support or an explicitly reviewed shared implementation. Pure ConfigDB parsing does not establish this numerical/audio capability. |
| Playback/export | Original WEM validation, complete scene contexts, disclosed surround stereo presentation, desktop ffmpeg encoding | Needs native device playback/encoding and full-frame/utterance parity. This audit adds neither a new codec family nor a substitute recording. |

`PortablePackage` is a bounded adapter, not a completed Android downloader.
The constructor still requires authenticated archive inputs and complete
index validation. Its explicit providers are responsible for transport and
Oodle implementation; a missing Oodle provider gives `missing_decoder`.
Synthetic checks forbid desktop network/process fallbacks and exercise exact
source framing, padding, hashes and callback output sizes.

## Preflight before large payloads

Preflight has two stages because a release manifest lists package sizes but
does not list the sizes of each selected ConfigDB/audio member.

1. **Bounded release/index metadata.** The Settings service reserves an explicit
   metadata cap before discovery. Original manifests establish the selected
   release, region, dub revisions and owner sizes. `manifest_upper_bound`
   deduplicates those owners and reports a conservative archive/index ceiling,
   explicitly leaving installed disk size unknown. Footer/main/directory reads
   remain bounded and attributed to those owners. If the next complete index
   cannot fit the approved metadata reservation, stop before reading it and
   show the additional bound. Do not download whole game packages merely to
   estimate selective payloads.
2. **Selected member payloads.** Once complete indices authenticate, use
   `Package.member_plan(position)` for the same entry parser that extraction
   uses. It provides original header, padded/encrypted stored-body ranges,
   plaintext length and compression requirements without reading member bodies.
   Deduplicate exact owner/entry identities. `selection_plan` returns a cold
   body-byte maximum plus separate, mandatory metadata and derived-output
   reservations. Verified cache reuse can reduce transfer; a changed owner or
   unverified cache cannot reduce the estimate.

The estimate must state its scope. HTTP/TLS overhead and retries are separate
from downloaded response-body bytes. Extracted original payload bytes are not
the final installed-size total: cache envelopes, SQLite/JSON indices, retained
previous versions, pending atomic writes, decoded PCM, encoded clips and file
system overhead need their own enforced disk reservations. In particular,
`largest_member_body_and_plain_bytes` is not a process-memory or disk-peak
guarantee. If text/output size or source duration has not been inspected, show
a configured maximum and enforce it rather than presenting an invented exact
number. Settings must refuse/stop work that exceeds the approved reservation.

Cancellation, failed verification and an unavailable codec retain the previous
complete library. Delete must be scoped to the selected game and its managed
cache/outputs, coordinated with active downloads/readers; it must not remove
the app's shared runtimes, other games, credentials or saved user transcripts.
The shared Settings/data service owns that lifecycle and used-byte accounting.

## Finite evidence

A cache-only original-data check reused the complete authenticated indices and
saved footer/sample receipts for four current localized owners. With all
network and desktop processes forbidden, the portable reader's eight member
plans exactly matched the previously verified download ranges: **391,744 body
and header bytes**, producing **435,484 original WEM bytes**. The members use
uncompressed or Oodle PAK storage. No body was read to create these plans and
no new bytes were downloaded. The zero metadata/derived-output reservations
in that narrow arithmetic check describe its already-retained inputs; they
are not valid reservations for a cold complete game download.

This is original-index/preflight evidence, not Android Oodle/audio playback or
a complete cold on-device update. Device-native runtime integration, protected
storage, full selected-language download/update/cancellation/delete and actual
device playback remain required before claiming independent Android support.
