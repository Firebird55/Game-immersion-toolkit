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
| Text and authored bindings | Shared `wuthering_tables` SQLite/FlatBuffer parser, redirected locale shards, selected-dub/Rover joins; later original movie/music enrichment | The actual ordinary reader reuses this pure parser and native table-name selection. Isolated-package and authentic old/current five-language parity pass on host Python; device SQLite/read-only URI and complete runtime closure remain required. |
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

## Settings bootstrap provider

`wuwa_game_data.create_provider(platform, native)` now implements the canonical
GameDataService planning/download interface for desktop and Android. It uses
the shared budget, account/cancellation fences and actual ETag/range transport,
the single shared APK ZIP reader, Wuwa AXML ownership reader, canonical
streaming APK-v2 verifier and bounded
Deflate/CRC/ELF reader. It does not call a desktop preparation subprocess or an
invented native preparation callback. Missing cryptographic support is an
explicit runtime error. The canonical Windows/Linux/macOS host names pass
through unchanged; the older direct `desktop` alias maps only to the process
host. Android obtains the maintained host's explicit `publisherCrypto()`
capability and validates it through the shared crypto interface. An absent,
invalid or failed Android capability stops before publisher metadata or asset
requests. It cannot silently select desktop cryptography.

The first plan reads bounded original metadata and quotes the complete APK
carrier transfer plus the selected compressed module, decoded module and
metadata disk reservation. Whole-carrier verification streams through a bounded
reader, retains only the selected member, and discards other carrier bytes.
The installer contains unused packaged media even in text mode; the plan
discloses that cost and the known unresolved next language-preparation gate
before download consent. No optional voice pack is fetched by this bootstrap stage.
This is not a claim that a text-mode installer carrier contains zero audio
bytes.

Successful verification returns `PreparationStage`, not a complete content
`SourceProof` or ready matcher. A restart restores the module identity locally;
the next plan reports the unresolved release-manifest key/IV gate with Download
and activation unavailable. Delete removes this game's managed cache while
preserving other games and saved history. The shared service keeps the previous
working content pointer when a stage is incomplete or verification fails.
A metadata-only quote handle cannot restore as a verified module: it reports
`publisher_bootstrap_incomplete`. Only a locally revalidated completed bootstrap
stage reports the unresolved manifest-format gate. Ordinary compatibility
preparation likewise distinguishes missing, invalid, wrong-generation and
source-authentication ENTRY failures while keeping prior text/audio available;
none of those states automatically means the game package format changed.

Synthetic complete signed-APK tests exercise the actual shared service and
transport on both logical platforms, text/text-audio selections, cancellation,
corruption, size limits, restart, the format gate and scoped deletion. A separate
cache-only replay of actual original metadata used 258,012 retained bytes for
each logical platform: **1,396,149,288 bytes** of carrier transfer and
**425,527,457 bytes** of additional disk were quoted. An already authenticated
native module was hardlinked and revalidated for the retained-stage gate. No
new body was downloaded. Both logical-platform runs used Windows Python; they
are not Android-device execution or a second cold carrier acquisition.

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

## Pure source import boundary

The staged provider's language validation and managed-file publication now use
small stdlib-only locale and atomic-file modules. The ordinary source-cache and
PAK readers use the same publication primitive without importing desktop tool
or installation discovery. Complete sibling staging, bounded Windows sharing
retries and preservation of the previous file remain enforced. Source-cache
ownership, original-byte hashes and PAK index authentication are unchanged.

An isolated-package regression copies the actual source modules, denies desktop,
registry, process and network access, and exercises official-language validation,
managed metadata publication and exact-reference source-cache round trips. The
full reader reuses the identical locale objects, including both Chinese scripts
and their shared Mandarin dub. These are import-boundary checks on host Python;
they do not establish Android native cryptography, codecs or a completed language
preparation path.

`wuthering_bootstrap_source` now contains the identical source-reference,
AXML application/module ownership, bounded Deflate/CRC/hash and pure ELF reader
functions used by ordinary preparation. Its isolated two-module test derives a
synthetic registered native output while transport, cryptography packages,
protected storage and other backend imports are denied. The ordinary native
orchestrator retains all source-owner, protected-cache, revision, package-index
and revocation checks. Moving these pure functions does not authorize a
candidate or bypass those checks.

The staged provider now consumes these pure functions directly and delegates ZIP
metadata to `publisher_apk_zip`, also used by ordinary acquisition. Its explicit
crypto capability is passed to metadata and whole-stream verification; no runtime
object enters a persisted handle. An isolated eleven-module package completes a
synthetic signed APK stage through the real transport and readers with desktop,
registry, `Crypto`, `certifi` and Java imports denied. That test supplies an
explicit public-RSA fixture capability; it is not Android/JNI execution. Retained
format-gate checks remain local even when that capability is unavailable.

A zero-transfer replay of retained original Wuwa signing metadata through the
reviewed canonical verifier matches the previously recorded certificate identity
and payload digest metadata. The canonical ZIP walker separately replays
257,581 retained original metadata bytes and produces the exact earlier selected
entry, local-header witnesses and signing layout. Neither replay repeats
whole-carrier integrity, establishes an independent certificate pin or proves
Android package-install acceptance.
Actual native runtime packaging/device validation and the unresolved
release-manifest ENTRY key/IV gate remain separate work.

## Portable table parsing and a future continuation

The actual ordinary `_read_tables` selection and `build_language_records` joins
now share `wuthering_tables`. It contains the existing SQLite/FlatBuffer, locale
shard, narrative-status and original dub/Rover logic, with the ordinary assets
module reexporting the same functions. There is no second Android mapping or
CLI invocation. Display cleanup is the identical shared stdlib-only
`text_display` function, reexported by `textmaps`; default audio-locale resolution
no longer imports the desktop Steam registry when no game is passed.

A minimal continuation after a **future independently owned ENTRY descriptor**
can reuse these boundaries. This is a continuation design, not an implemented
ENTRY resolver or complete Settings content stage:

1. Bind the selected region/revision and all original resource/dub pointers to
   the descriptor. Use the same complete original index checks and
   `required_tables` selection, retaining patch/base/launcher precedence and
   tombstones. All IO must use the context's consent, limits, cancellation and
   original-owner transport; no protected-format or desktop-tool fallback may
   enter this path.
2. Quote the exact indexed table/member plan and enforce the context's separate
   metadata, original-body, pending-output and derived-index reservations.
   Gate AES, SQLite and every selected compression before acquisition. Publish
   a table artifact only after its original checks and full local SHA-256;
   validate the retained descriptor and those exact source identities again on
   restore. The pure parser does not authenticate a publisher source by itself.
3. Parse text/bindings with the same shared functions. Text-only work can pass
   an empty voice inventory and performs no audio/body/probe IO; authored
   missing/unknown voices retain their existing status. Movie/music caller,
   player/locale and source-clock enrichments remain the same separate
   admissions. They cannot be replaced by filename or preceding-line guesses.
4. For text plus audio, materialize and validate the selected originals through
   the exact authored owner/member/depot cache contract before Ready. A local
   source miss needs a new approved plan, not an unbounded restore download.
   The existing pure owned-source cache can be reused only under its complete
   identity and full recording hash. Old retained descriptors/recordings stay
   usable independently; a failed or incomplete continuation preserves the
   previous content pointer and never publishes a partial snapshot.

The actual current five-language table selection contains sixteen members:
fourteen newly acquired in the earlier proof and two already retained. Their
combined plaintext is **322,056,192 bytes**; all sixteen use uncompressed,
encrypted `custom=2` PAK storage. The largest is **60,698,624 bytes**. That finite
cohort does not need Oodle. A future indexed Oodle member needs an explicitly
packaged native provider before body acquisition; `PortablePackage` must not
select the desktop Node decoder. Current PAK AES still needs the explicit
Android crypto seam before this proposed continuation can acquire archives;
the APK-signature capability alone does not establish PAK extraction.

Complete original indices retain SHA-1 validation. These `custom=2` raw members
have the native 2,048-byte encrypted-prefix checksum, then exact original
HTTPS/owner/length/ETag binding and a complete local plaintext SHA-256. No whole
publisher-member or PAK hash is claimed from selective reads. Voice preparation
additionally needs the shared native Wwise/codec probe, complete frame/rate and
channel-layout checks, scoped seek/context policy, required matching numerics
and output encoding. The evidenced RIFF/Wwise Opus `0x3041` sample and guarded
standard 5.1 whole-scene presentation are requirements to preserve, not a claim
that an arbitrary on-device decoder satisfies them. A missing capability keeps
the typed gate and the previous library.

An isolated six-module parser package exercises all five study languages,
Mandarin sharing for both Chinese scripts, official target text, redirected
Japanese text, and female/male source bindings while desktop/tool registry,
model/fuzzy/crypto imports and network/process/registry operations are denied.
An empty voice inventory returns missing audio rather than fabricating speech.
Rich-text and explicit locale regression cases retain existing behavior.

Read-only actual 3.8.11 and 3.8.12 fixtures separately pass all five selections:
every base text/binding record exactly equals the previous ordinary parser,
and direct dub/Rover depots match the saved actual workers. Their confirmed
unvoiced, unknown and unavailable counts are unchanged. This comparison covers
the base joins, not a new complete movie/song enrichment or device playback
claim. Original-source fixture envelopes, immutable owner/position/path and
current local hashes were checked before making 311,582,720 bytes of local
headerless copies; seven exact matching members were hardlinked. No new
original bytes were downloaded. Ten old/current retained recording fixtures
also retain their complete source hashes and snapshot/depot bindings without
network, protected-key access or a repeated decoder run.

This checkpoint implements the ordinary/portable parsing and table-selection
seam. It leaves the Settings ENTRY gate in place and creates no content
`SourceProof`, complete `SnapshotSource` or Ready state. Future app source
bundles must include `text_display` wherever they include `textmaps`, and the
pure Wuwa parser closure before using this continuation; a host regression is
not proof those modules/runtimes have shipped or executed on Android.

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
a complete cold on-device update. Device-native runtime packaging and validation, protected
storage, full selected-language download/update/cancellation/delete and actual
device playback remain required before claiming independent Android support.


## Bounded Android bootstrap continuation

The canonical provider accepts the maintained Android host's explicit
`publisherCrypto()` capability and can consume a caller-supplied transport
factory for an authored, bounded source fixture. The ordinary default remains
`PublisherTransport`; injection changes neither the APK signature/content
checks nor selected-member, source-generation and ELF registration checks.
No crypto registry, desktop fallback or independent ENTRY input is introduced.
The source fixture path is for host/device validation, not supplier acquisition
or proof that a generated fixture is an original game package.

The passive ELF reader now validates unconsumed section bounds without copying
whole mapped sections. Dynamic symbol names are located in the read-only map,
with the same bounds, terminators and exact target-name admission. Context
cancellation reaches retained-source hashing, member hashing, symbol/relocation
and initializer scans. Cancellation closes mappings, cleans provisional output
and preserves the existing retained module and library. These changes reduce
avoidable heap allocations; they do not set a whole-device memory guarantee.

Host regressions exercise the explicit Android capability selection, shared
transport, complete synthetic APK integrity and native registration to the
`PreparationStage`, then the honest unresolved ENTRY gate. Original cached
module comparison verifies identical derived output and registration without
new transport. Actual APK source closure, mmap operation and authored fixture
execution on Android remain separate app/device acceptance work. The stage
still supplies no content `SourceProof`, language library or Ready state.
