# Infinity Nikki: official-source discovery

Audited November 17, 2026. Implementation ticket:
[#145](https://github.com/Firebird55/Game-immersion-toolkit/issues/145).
This is an incomplete new integration. The discovery reader follows current
official regional launcher pointers and the Global anonymous SDK's base/hotfix
manifest pointers; it does not yet prepare game dialogue on PC or Android.
No game-data playback, installed-pack validation, full-story
denominator or autonomous game update has passed for this game.

## Official regions and language evidence

The publisher's [Global homepage](https://infinitynikki.infoldgames.com/en/home)
and [mainland China homepage](https://infinitynikki.nuanpaper.com/home) expose
their current Windows launcher links in the website's `__NEXT_DATA__`
`props.pageProps.pageData.page.windowsUrl` field. Global points directly to
the publisher's `x6oversea-game-package.infoldgames.com` CDN. Mainland links
through `ays.cn` to `x6cn-game-package.papegames.com`; the reader checks every
redirect before following it. The separate mainland Android download pointer
uses `x6cn-game-apk.papegames.com`.

The Global [publisher Steam language matrix](https://store.steampowered.com/app/3164330/Infinity_Nikki/)
lists English, French, Italian, German, Indonesian, Japanese, Thai, Simplified
Chinese, Traditional Chinese, Brazilian Portuguese, Latin American Spanish and
Korean for interface/subtitles. Full audio is listed for English, Japanese and
Simplified Chinese. The original Global hotfix descriptor independently lists
`VOICE_EN`, `VOICE_JA` and `VOICE_ZH` story/event resource groups. This establishes
the original pack-family names, not individual dialogue/audio bindings or
playback. Mainland voice/resource inventories still need independent
verification; the Global matrix cannot rule out additional regional content.

The publisher's [mainland launch FAQ](https://infinitynikki.nuanpaper.com/news/76)
confirms PC, Android, iOS and PS5 editions and separate PC/Android packages.
The [Version 2.8 update guide](https://infinitynikki.infoldgames.com/en/news/559)
distinguishes launcher pre-download and mobile partial-resource updates. These
platforms cannot be assumed to use interchangeable containers or manifests.

## What discovery currently proves

`backend/infinity_nikki_release.py` reads the exact bounded publisher website
field, rejects duplicate metadata, and follows changed launcher filenames without
a version allowlist. It rejects foreign, mixed-region and unsafe redirects.
It does not execute downloaded launcher or game code. The current observation
is launcher 1.3.1, which is a launcher version, not a game-resource generation.

Static inspection of bounded official installer ranges found a non-solid NSIS
archive with independent Deflate members. One complete 6,849,415-byte compressed
Global `xstarter.exe` member decoded to 10,816,688 bytes with exact Deflate EOF
and size bounds. Windows validated the complete extracted PE's Authenticode
signature from Suzhou Nikki Co., Ltd. The extracted file's SHA-256 is
`3a64a573b6d64abc625ba894fe68960a05e0dcbfe8e23f5c97a1ec53887cebff`.
This authenticates that component; it is not a whole-installer hash check.
No client code was executed.

The signed component contains updater paths including
`/v1/accessories/gameconfig/patchlist`, `checklauncherpkgupdate` and `parameter`,
and `/v1/user/resource_entry`. Its encoded `common.json` resource was decoded as
data after inspecting the complete 358,576-byte `libnetwork.dll` member, also
with a valid publisher Authenticode signature. The config cipher derives from
the launcher's own identity resource; the owned decoder requires no hardcoded
publisher key or protected key cache. This static discovery does not execute
client code.

The decoded Global production host is `https://passport.infoldgames.com`, with
independent test and preproduction hosts excluded from production discovery.
The normal patch-list request uses POST with `channel`, `region` and `env`;
launcher-package checks also include launcher identifiers and version. The SDK
transport adds application metadata, a form signature and encoded payload. The
owned reader reproduces the timestamp/identity-derived DES/AES, ECB/CBC and
HEX/Base64 transport choices. Its live anonymous request passed with `code: 0`
and a successfully decoded response. No account, installed game, community key,
protected key cache or real device diagnostics were used. Earlier partial
transport probes returning `args_error` are superseded by this successful test.

The response selected base manifest `PC_Smallest_Version_2828_O.json` and hotfix
`BuildVersion_2872.24.json` on separate original Global CDNs. The 629-byte base
manifest names a 1,093,871,896-byte original 7z bootstrap, with its 32-character
MD5 and an extraction-space field. The 9,806-byte hotfix descriptor confirms
IoStore and CMS, Windows, Region 1 / Channel 3 / Role 0, and base/default version
2872. These are source observations, not a whole-current-story count. No game
archive body was downloaded. The 7z's size and extraction hint are not a
selected-dialogue size plan.

The owned bootstrap planner now reads only PE/NSIS metadata first and reports
the exact selected launcher member's transfer bytes before downloading it.
All ranges bind to one strong publisher response validator. Its data-only
Unicode NSIS/Deflate and Qt resource readers reproduced the exact original
component and config from the privately retained official source ranges, without
7-Zip, capstone, pefile, client execution or fixed link addresses. Format details
were checked against the upstream [NSIS structures](https://github.com/NSIS-Dev/nsis/blob/master/Source/exehead/fileform.h).
The parser's structural checks do not independently verify Authenticode; the
separate native signature observation above remains distinct.

Cold HTTP orchestration and native Android acceptance still need end-to-end
verification on both runtimes, followed by original bootstrap/hotfix inventories,
actual text/voice package readers and required-file selection. The successful
metadata request does not prove full current-story, regional voice bindings or
availability of original recordings. No keys or client payloads belong in this
repository.

## Original game-bootstrap archive metadata

A bounded header-only probe of the publisher-selected 7z read 32 bytes of start
header, 39 bytes of next header and 7,045 bytes of encoded header. The source
CRCs and declared 70,370-byte decoded metadata length passed. The archive
structure follows the upstream [7z format](https://github.com/ip7z/7zip/blob/main/DOC/7zFormat.txt).
This initial inventory probe read no archive content stream.

The inventory has 466 entries, including 357 content files in two solid streams
of 616,011,349 and 477,853,431 compressed bytes. Its 13,536-byte
`HotUpdateBuildVersion.json` starts 58,797,864 decompressed bytes into the first
stream. It therefore cannot be treated as an independent 13,536-byte download.
The archive also contains localization, Lua, movie and IoStore containers, which
still require current inventory/format/binding work. The normal update source's
`Rel_2.8` bootstrap path is not proof of stale game coverage: the same current
descriptor explicitly contains a `Protect_2_11_2` resource group.

A subsequent explicitly bounded stream probe acquired only the original
13,536-byte updater file, verified its source CRC `d292a3e6`, and stopped at the
58,811,400-byte decoded boundary before the first game PAK. Earlier decoded data
were discarded. The retained target's SHA-256 is
`b180d285fbfb0cb2d3530eb84a0b4b3b2e478a2675dff9dbdc6f66bc0c214017`.
The successful probe counted 18,561,605 HTTP-body bytes, including 14,917 bytes
drained from known HTTP/TLS buffers. Its requested 64 MiB interval remains a
conservative wire upper bound for unread transport buffers. These are partial
archive observations: the publisher's whole-archive MD5 was not independently
verified. Only the selected updater file and private evidence were retained;
no native component was loaded or executed.

The selected file has an `_XYLUAP_` wrapper followed by Base64 data. Removing
that outer encoding yields 10,144 bytes, not direct JSON/zlib/gzip. A later
authenticated native-source probe, described below, resolved this file's
decoder and original key derivation. A 16-byte multiple alone did not establish
its cipher. The complete acquired
launcher/network components have no direct marker reference in ASCII or either
UTF-16 byte order. The two source-authored SDK parameter keys concern process
cleanup and GPU-driver configuration; the cleanup response has no wrapper/key
reference and the driver key reports absent. None of this proves that official
derivation is unavailable or permits a community-key fallback.

The publisher-authored launch configuration delegates update work to
`PaperHotUpdateRuntimeBG` with the `UnLuaCommandlet` flag in the original game
component. Further targeted source-owner work remains necessary. No game/client
code may be executed to replace the missing reader.

Preparation must offer **text only** and **text plus audio** on Android and PC.
Required-file selection, download size and local size must follow that choice;
text-only preparation must not silently obtain or retain voice packs. A solid
bootstrap archive is not sufficient evidence for a selective plan. The current
overall dialogue download/storage sizes remain unknown.

The upfront dialogue download/storage estimate remains **unknown**. Neither the
installer's size nor the publisher's whole-game free-space recommendation is a
valid substitute. A preparation plan must come from the current regional game
inventory, include required tables/bindings and selected original voice assets,
and account for cache, retained recordings and temporary extraction space.

## Original Android source-integrity boundary

The mainland homepage points to the publisher's
[Android APK](https://x6cn-game-apk.papegames.com/x6cn/adapk/ad_package_offcialweb.apk).
The observed generation is 625,323,294 bytes. Its central directory contains
1,395 entries, including 66 Deflate-compressed native modules. The selected
`lib/arm64-v8a/libUnreal.so` is 76,697,538 compressed bytes and 213,538,488 decoded
bytes. It cannot be range-read as an uncompressed ELF section. This is mainland
source evidence, not proof of Global Android compatibility or dialogue coverage.

A bounded 1 MiB compressed prefix establishes ELF64/AArch64 and GNU build ID
`2688ff5e9076a2fb028ff5bebdac3f014efbbaf6`. The resulting 3,541,389 decoded
bytes do not contain the targeted wrapper/commandlet markers in ASCII or either
UTF-16 byte order. Those markers may occur outside this prefix; this does not
establish a missing or impossible official decoder. The dynamic table and
section table are near the end of the full module, beyond that initial probe.

`backend/publisher_apk.py` implements the observed APK v2
RSA/PKCS1-SHA256 source-integrity profile without installing or executing the
APK. It checks the leaf certificate's exact public-key encoding, signature and
ordered algorithm lists. Unknown algorithms, v3/v3.1 blocks and additional
attributes fail closed. A metadata signature alone never marks APK content
verified. Following Android's [v2 specification](https://source.android.com/docs/security/features/apksigning/v2),
the streaming reader verifies every protected section in separate 1 MiB chunks,
patches the EOCD central-directory offset for the digest, compares all cached
metadata against the stream, rejects truncation/trailing data and retains only
an explicitly selected compressed member. A valid self-signed package signer
does not independently pin that certificate to a publisher.

The original 1,682-byte signing block contains v2 and one vendor metadata pair,
with no v3 block or v1 certificate entries. Whole-content verification requires
all APK bytes, not just the signer block or the selected native module. It is
research bootstrap overhead, not a valid text-only dialogue download estimate.
Synthetic APK fixtures exercise chunk boundaries, metadata/content corruption,
generation mismatches, short reads, unsupported signing profiles and bounded
member selection. This integrity reader alone prepares no game dialogue.

The complete original APK was subsequently streamed once: all 625,323,294 body
bytes, the v2 signature and 599 protected-content chunks passed verification.
The official URL, strong ETag and length matched before/after the request; the
whole-APK SHA-256 is
`1dc7f77e285aff522d191e6bc17f86ee7dd09210ab8b7f7cbc321366c36aa208`.
Only the selected compressed native member and small metadata/receipts were
retained. Its complete Deflate EOF, 213,538,488-byte decoded length and original
ZIP CRC `e3bc3d0b` passed. The decoded ELF SHA-256 is
`bd6ae5fe02b59362ee362d3a8915a7f5c66957703219a556b751eb74462f9dcf`.
The package's self-signed certificate was not independently pinned to a
publisher identity; original publisher URL/TLS provenance and verified package
integrity are distinct observations. No original module was loaded or executed.

Targeted native references now prove that the full module contains both the
wrapper and original commandlet markers. Following the wrapper's actual
consumer establishes Base64 decoding, an authored SHA-1-based derivation and
AES-256-ECB; the caller explicitly trims after the first NUL. Reimplementing
that data transformation decodes the existing original Global bootstrap to a
10,131-byte JSON object with base/delay-group/voice-family fields. No key is
stored in this repository or obtained from a community source. This proves
compatibility for that one Global descriptor, not every regional package.
`backend/infinity_nikki_native.py` now extracts that authored material without
fixed addresses, a key list, a disassembler or loading the original module. The
caller must supply the verified native generation's SHA-256. The reader follows
the wrapper literal's AArch64 references, a matching caller/builder path, the
original SHA-1 initialization and authored immediate-byte append operations;
ambiguous/unknown paths fail instead of guessing a key. The exact owned reader
successfully replays the original 83-field Global descriptor. Synthetic fixtures
relocate both virtual/file addresses, rotate authored material across source
generations, reject changed sources and ambiguous paths, and exercise original
NUL-boundary/invalid-wrapper behavior. Discovery integration and downstream
containers remain required. Internal build-only roots in the bootstrap are not network sources;
public resource discovery must use the publisher SDK's current CDN descriptors.

The generic verifier retains a strict default. A separately evidenced source
may opt into `allow_signed_zero_tail=True`, which permits exactly four zero
bytes after the three canonical signed-data fields. Android's
[original v2 verifier](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/java/android/util/apk/ApkSignatureSchemeV2Verifier.java)
verifies the entire raw signed-data signature and does not require that those
three parsed fields consume all signed data. The narrow opt-in still verifies
the complete raw signature and rejects partial, nonzero, repeated or unsigned
tails. It does not accept unknown attributes or a stripped v3 declaration. This
is a source-integrity subset, not complete Android installation acceptance.

## Original updater framework and PAK boundary

A further bounded, generation-pinned metadata probe identified the APK's
STORED embedded OBB and its 70 ZIP entries using 74,676 bytes. This is not a new
whole-OBB CRC or APK-v2 check. The exact original Lua framework PAK (525,276
bytes) and companion signature (564 bytes) were subsequently obtained in
526,114 bytes including local-header metadata. Both complete inner ZIP-member
lengths/CRCs passed; source URL, strong ETag and length matched the previously
verified APK generation before/after the request.

The framework uses a v12 encrypted PAK index with the default zero key GUID.
Following the actual native footer/index consumer, zero-GUID getter, delegate
storage/setter and startup registration identifies its original key callback.
Reading that callback's two authored vector loads as data resolves this index's
key without scanning for candidate keys. The consumer explicitly enables an
additional XOR on the first/last byte of each AES block. Reimplementing that
exact transformation passes the original main/directory index SHA-1 checks.
This is a separate source chain from the metadata-wrapper derivation.

The startup-bound signing callback supplies a public RSA-4096 key. Its byte
ordering follows Epic's [IEngineCrypto contract](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Core/IEngineCrypto).
The complete v1 companion signature has valid PKCS#1 type-1 padding, and the
recovered payload's final SHA-1 matches the nine CRC32 words, exactly as the
original native consumer checks. All nine 64 KiB PAK chunks match that signed
checksum list. This verifies the signature on the list; CRC32 is not a
collision-resistant whole-PAK hash. No new independent whole-OBB or APK hash is
claimed for these later partial ranges.

The original entry schema has two 20-byte hash fields. Its 175 framework script
entries total 1,154,031 decoded bytes; every uncompressed SHA-1 matches. The
existing pinned source-built Oodle decoder processes the compressed data; no
original game library or Lua VM runs. Script headers recover original source
names from the otherwise hashed filenames. Only the identified updater sources
are retained for deeper static metadata analysis. Their framing follows Lua
5.4-style sizes/varints despite the original `0x53` tag; assuming a standard
Lua 5.3 bytecode reader would be incorrect.

The actual `PaperHotUpdateMgr` constants establish resource-inventory URI
templates under the current SDK-provided resource root, including
`HashFiles/{Platform}/{Version}/PaperHashFiles_{Version}.json`, `.bin`,
`PaperHashFiles_{Version}.{FastPatchVersion}.bin` and
`PaperFilePakHashMap_{Version}.bin`. The original chunk-install route also
names `HttpChunkInstall/{Platform}/{Version}`, `CloudDir` and
`PaperHttpChunkInstall.manifest`. Their downstream response formats and active
selection branches still require verification; a literal URI template is not
a completed downloader or current-content inventory.

Exactly four source-derived Global HEAD/prefix probes (eight requests, 128 body
bytes total) confirm those current inventory objects exist with strong ETags.
The observed base JSON is 427,186,330 bytes; the base binary is 75,806,853 bytes,
the selected hotfix binary is 1,428,020 bytes and the file/PAK map is 17,115,624
bytes. The binary prefixes have an original `0x20240418` marker, flag/declared
expanded-length fields and Oodle framing. These are metadata sizes, not selected
dialogue/audio sizes. Only prefixes have been acquired; no complete resource
inventory is established by those prefix probes alone.

The exact 1,428,020-byte hotfix object was subsequently obtained with unchanged
strong ETag/length before and after, preserved before parsing and hashed in full.
Its SHA-256 is
`6d6af52fff9dc50a53fe8c602ee9ac96ea5f02ac7c3b64c5c084437169d8998e`.
The ETag is an object identity, not automatically a declared publisher MD5; no
separate publisher checksum for this metadata object was supplied. The actual
native consumer proves the nine-byte version/flag/expanded-size envelope and
payload start. The owned decoder reads exactly 5,691,995 expanded bytes and the
original inner serializer's complete 43-record array to EOF. The records have
three strings and three maps: 15,657 opaque-12-byte-key/string pairs, 21,598
string/string pairs and 16,332 further opaque-key/string pairs. Unresolved map
meanings remain opaque; empty values are not guessed to mean deletion or silence.

`backend/infinity_nikki_inventory.py` now supplies that portable owned reader,
the current SDK-derived URI templates and compressed/temporary-decode size
planning. It requires a source-generation hash and an injected portable codec,
rejects mismatched sources, duplicate keys, invalid counts and trailing bytes,
and follows normal version/patch changes without a fixed URL revision. Original
current hotfix replay and synthetic format fixtures pass. The untouched base
inventory was initially outside that probe; package selection and end-to-end
normal updates remain unverified.

The exact official cold-base binary was subsequently obtained in its own
bounded acquisition: 75,806,853 body bytes, unchanged strong ETag/length before
and after, and an exact match to the previously retained 32-byte prefix. Its
local whole-object SHA-256 is
`9933508aae458840a4eb3cab41bc394ee8a9f287c595c00f18d534cd94ac563f`.
This binds the retained bytes to the recorded source generation; the ETag is
not automatically a publisher MD5 and no separate authored checksum was found.
The same owned inventory reader decodes exactly 271,792,142 bytes and parses
101 records to EOF, containing 1,116,852 map-A, 536,864 map-B and 1,117,247 map-C
entries. Original authored package names include `Default_Loc`, `L10N`, Lua and
EN/JA/ZH voice groups with story/event variants. These names do not prove
dialogue extraction, active scene coverage or playback. Map semantics, actual
resource/package URI ownership and selection sizes still need their original
consumers. The retained compressed and decoded base metadata together use
347,598,995 bytes; this is bootstrap metadata cost, not a text/audio quote.

`backend/infinity_nikki_pak_material.py` now implements the default PAK producer
discovery without fixed addresses, keys or a disassembler. It follows the proven
index/GUID/SHA-1 consumer to the getter's writable storage, matches the setter's
callback capture into that same delegate object, then follows the actual startup
binding to a complete static-copy producer in read-only source data. It does not
scan for key literals or use ciphertext as a candidate-key oracle. Its bounded
AES/XOR index reader requires the default zero GUID explicitly and verifies the
plaintext hash. The exact owned reader passes the original CN Framework index;
synthetic fixtures relocate code/data, rotate source material, vary linker/BTI
forms and reject unbound producers, wrong receivers, overwritten arguments,
unsupported copies, changed source hashes, nondefault GUIDs and bad indices.

`backend/infinity_nikki_pak.py` now supplies the bounded original v12 directory,
compact-entry and two-hash full-entry reader. It checks the compact location
against the original on-disk header, bounds every encrypted/compressed block,
verifies both index plaintexts and every selected decoded member's authored
SHA-1, and rejects unsafe paths, duplicate names, unknown GUIDs, nonencoded
variants and unresolved deletion positions. Its injected codec contract has no
original-library execution or Windows-specific runtime dependency. Replaying
the exact current CN Framework archive reads all 175 members and verifies all
1,154,031 decoded bytes using the toolkit's existing source-built desktop codec.
That replay does not establish an Android codec or a complete game provider.

The current Global Loc index exposed two independent compact-entry flags that
the original Framework sample could not distinguish: the native decoder uses
bit 22 for the compressed-size field's width and bit 29 for member encryption.
Both were set in the verified Framework members. The owned reader now follows
the original decoder's separate width load and flag capture; synthetic fixtures
exercise all four independent width/encryption combinations and full-entry
checks. This is a reader correction, not a publisher format-change conclusion.
The Loc footer, main index and full-directory index have passed complete
manifest-chunk and plaintext-index hashes without downloading the entire
280,653,147-byte PAK. The reader enumerates 183,718 locations, including 180,246
game locres files across the twelve original locale folders (`de`, `en`, `es`,
`fr`, `id`, `it`, `ja-JP`, `ko`, `pt`, `th`, `zh`, `zh-Hant`). These are resource
counts, not an active story denominator. No locres body or original voice has
been extracted by that index-only proof. All retained carrier/cache bytes are
counted; an unused 8,584,496-byte path-hash index was not fetched.

`backend/infinity_nikki_lua_metadata.py` parses the source-owned updater's
prototype, constant and debug framing without a Lua VM. Its original 0x53 tag
does not imply stock Lua 5.3 framing. Four current updater chunks parse to exact
EOF: 387,434 bytes and 644 prototypes. Synthetic fixtures cover source inheritance,
changed generations, all observed constant kinds including nonfinite number bit
patterns, bounded recursion/counts and malformed or truncated data. Lua string
constants may contain arbitrary bytes: invalid UTF-8 stays opaque bytes instead
of causing a false format-change failure. Source/debug names keep their text
validation. Parsed strings remain metadata, not automatically trusted download
destinations. The four current Global updater chunks also parse to exact EOF;
original utility chunks independently demonstrate the need for opaque binary
constants. No original VM runs.

A separately bounded four-member format probe retrieves only the English,
Japanese and Chinese versions of one named dialogue resource plus an English
settings resource: 2,030,376 complete carrier bytes, 4,361 selected original
member bytes and 8,068 decoded bytes. All four source chunks and decoded PAK
members pass their authored SHA-1 checks on frozen corrected-reader code.
Only the four authorized resources and verified carrier cache are retained.
`backend/infinity_nikki_locres.py` reads their stock-v3 key tables and string
pools completely: 150 entries, with identical namespace/key/source-hash
identities across the three dialogue translations. The source hash describes
the authored source string, as represented by the engine's
[localization entry](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Core/FTextLocalizationResource/FEntry);
it must not be recomputed from a translated value or discarded when joining
languages. The owned reader bounds both table regions, preserves Unicode and
opaque key hashes, rejects duplicate identities and stale-identity joins, and
uses no client library or Lua VM. A localization row alone is not marked as a
verified caption, unvoiced dialogue or an original voice binding. Original
caption/voice consumers and patch-priority semantics remain separate gates.

The original updater's captured URL templates lead to the current Global
`CloudDir/PaperHttpChunkInstall.manifest`. Its complete 41,972,123-byte JSON
response has unchanged strong ETag/length before and after and a verified
original prefix. Its local SHA-256 is
`64a8e94b45da46a3d75248d4a96e7e9732116a44aef49790dc2f9a40a6f52a52`.
This source-generation identity remains distinct from a publisher signature or
declared checksum. The typed owned `backend/infinity_nikki_chunks.py` reader
validates 507 file records and 125,590 matching chunk descriptors. It reads the
original decimal-encoded byte fields, actual file/part ownership and declared
SHA-1 values, and quotes complete deduplicated carriers, retained file bytes,
temporary decode space and shared-carrier presence. It does not infer audio or
deletion semantics. The original native directory selector maps this manifest's
feature 13 to `ChunksV3`; the reader does not assume the latest `ChunksV4` name.
The [engine's feature-level documentation](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/BuildPatchServices/BuildPatchServices__EFeatureLeve-)
also distinguishes fixed-window chunks from later variable-window formats.
The initial FastPatch substitution omitted the default-version prefix and
returned HEAD 404. The complete current Global getter's original register
dataflow explicitly concatenates default version, an underscore and fast-patch
version. The corrected source therefore uses `CloudFastPatchDir/2872_24`, not
the bare patch number. Its independently obtained 476,738-byte manifest passes
unchanged ETag/length, prefix and complete local SHA-256
`bde1e8a862e4807908024e395835cd1b0c491fa4090184f63456fd3a6bf7118e`.
The owned URI reader derives both version components for normal updates and
checks that the repeated default version agrees with the source family. Typed
metadata contains 188 files and 1,273 matching chunk descriptors. Authored
custom fields remain opaque until their actual consumers establish overlay
priority; neither the field names nor the earlier 404 establish deletion,
silence or a publisher format change. No guessed endpoint variants were used.

All five current Global Framework files occupy one 941,200-byte shared carrier.
The carrier also contains a movie fragment, so its complete verification cost
is explicit bootstrap overhead; no zero-media-transport claim is made. The
owned v2-header/zlib reader verifies the full 1,048,576-byte decoded chunk's
authored SHA-1. Each selected file is reconstructed through its declared parts
and independently passes its manifest SHA-1: the 657,642-byte PAK, 572-byte
signature, 1,297-byte UTOC, 48-byte UCAS and 28-byte directory-hash file. Only
these 659,587 bytes are retained; the transient complete carrier is removed.
The exact carrier was obtained again in a separately bounded product-reader
replay, with unchanged source generation and whole local hash, to verify the
actual owned reader and range edges. Original-source metadata and product
replay evidence remain distinct.

The registered default material derived from the authenticated official CN
native owner also passes the current Global Framework's complete 3,360-byte
zero-GUID index hash. The owned PAK reader then verifies all 176 member hashes,
totalling 1,169,896 decoded bytes. This proves this particular current Global
Framework/default-key compatibility; it does not establish other Global
archives, nonzero/dynamic keys or future rotated material by assumption.

Other Global PAK/key-GUID compatibility, nonzero/dynamic keys, production
signature registration/verification and complete fresh preparation remain separate work.
No key values or source assets are
committed. Fresh production native-owner acquisition also needs an explicit
bootstrap plan: the embedded OBB contains a 78,866,565-byte movie PAK. Full mixed
APK verification remains a possible route if its entire carrier cost and reason
are quoted as required bootstrap overhead, only native bytes are retained and
its mixed content is described honestly. Prefer a separately authenticated
native-only source when available. The research stream must not silently become
a runtime text-only plan that pretends no audio/video-containing carrier bytes
were transferred. A failed source/key check is not automatically evidence of a
package-format change or official-source impossibility.

## Shared APK metadata boundary

`backend/publisher_apk_zip.py` now locates classic single-disk APK entries through
a bounded exact-range callback. It has no network, extraction or execution
effects and delegates signer metadata to the single `publisher_apk.py` verifier.
Its optional keyword-only `crypto` capability is passed only to validation and
is never serialized into a layout or handle. The exact shared portable verifier
also passes the cached original RSA-2048 signer metadata with strict framing;
that offline check does not revalidate the whole APK's content digest.
Selected local headers, original encoded names, compression/CRC/size fields and
carrier bounds must agree; ZIP64, encrypted/descriptor selected entries and
unsupported compression are explicit gates. Small metadata-member inflation is
bounded before reading. Original local-header witnesses must also match the
subsequent complete carrier before accepting the selected native owner.

An offline replay of already retained official CN metadata reads 126,205 bytes,
parses all 1,395 entries and locates the same 76,697,538-byte compressed /
213,538,488-byte native owner. It performs no network acquisition and does not
repeat the earlier full-APK v2 verification. Authored APK fixtures separately
exercise the walker and canonical whole-stream verifier together, including
split directory/tail reads, CP437/UTF-8 names, misleading comment signatures,
pre-read budgets, local/CD disagreement, invalid paths, compression/CRC failures
and the explicitly opted-in signed-zero-tail dialect. This is shared format
infrastructure, not an executable Nikki preparation stage or dialogue coverage.

## Canonical native-bootstrap preparation stage

`backend/infinitynikki_game_data.py` implements the shared plan/download/restore
contract on PC and through an explicit Android cryptography capability. It reads
the exact mainland website `android` field, follows its direct original APK
family, pins actual size/strong ETag and quotes the complete integrity carrier
before transfer. Selected native ownership uses the evidenced original
`lib/arm64-v8a/libUnreal.so` member and its actual wrapper/index consumer chains;
it does not invent AndroidManifest provenance or import another game's runtime.
The module name is a source-owned format selector, not a frozen release URL,
address, key or payload hash. Global requests disclose use of this mainland
bootstrap source; each Global resource still requires compatibility verification.

The consented stage streams the complete APK through the single shared v2
verifier, checks selected local-header witnesses against that same stream,
bounds Deflate/size/CRC and follows the owned address-independent native producer.
It retains the authenticated native module and private integrity receipts, never
derived key material or ignored media members. Required disk space includes the
compressed native member, decoded module, planning metadata and receipt overhead.
The full carrier contains unused media even for text-only requests; it is quoted
as necessary bootstrap overhead and no optional voice pack is fetched.

Metadata, source-generation, mode/locale or estimate changes, damaged content,
unbound native consumers and cancellation stop preparation while retaining old
game data. The returned value is only a `PreparationStage`. Restoring that stage
is local and reports the unresolved content-reader gate; it cannot activate a
matcher, blank snapshot or unverified voice source. Shared cache accounting and
deletion include its retained source bytes.

Authored APK/HTTP fixtures exercise the actual shared transport and contexts,
whole signing/member checks, staged continuation, both content modes, explicit
crypto propagation and failure retention. A fresh process also imports the
factory and derives authored native material while Crypto and desktop service
imports are blocked. The wrapper/default-index decoders now accept the explicit
shared crypto capability and preserve their original ECB/NUL/XOR/hash rules;
their desktop default is lazy. This does not establish the Android native
manifest/ABI implementation, actual device acceptance, a fresh end-to-end game
library, current patch precedence, caption/voice ownership or future-generation
coverage. Those remain acceptance gates, not package-format-change assertions.

Offline original-source replay binds this stage's code hashes to the retained
official homepage, APK metadata and earlier complete carrier receipt. The
metadata-to-quote path reports 625,323,294 download bytes and 290,470,325 required
disk bytes for that recorded generation. Its original native consumer gate
passes the authenticated 213,538,488-byte module. This uses existing cached data;
it is not a fresh source-generation check, a complete new network plan, a new
whole-APK verification or Android/device acceptance.

## Dialogue-container and dynamic-key ownership checkpoint

Two separately approved footer-only probes now bind the original
`Default_Lua_2872_P.pak` and `Delay_Base_Bin_2872_P.pak` metadata to their original
BuildPatch carriers. Both complete decoded-chunk SHA-1 checks and strict
HEAD/ETag/If-Match/post-HEAD generation checks pass. The selected output is only
221 footer bytes per package. The Lua footer has the evidenced encrypted v12
zero-GUID format; the Bin footer uses the same framing with a nonzero encryption
GUID. The default-key reader deliberately does not try that nonzero GUID. It
requires an independently evidenced source producer, not a guessed default key
or a package-format-change/impossibility conclusion.

One additional approved 1,030,282-byte carrier supplies the Lua main index;
its complete plaintext SHA-1 passes with the native-derived default material.
The 720,944-byte full directory is reconstructed entirely from two retained,
authenticated carriers with zero new network bytes. Its expected SHA-1 comes
directly from the verified main-index descriptor. The owned reader reaches
directory/index EOF and validates all 14,688 directory/compact-entry references.
It reads no script, configuration-table, full member-header or audio bodies in
this phase. Neither resource counts nor hashed script paths establish active
dialogue, full-package integrity or a text/voice binding.

These footer/main-index acquisitions total 2,974,109 new body bytes, including
941,200 explicitly disclosed bytes to reobtain the previously discarded
Framework carrier. All three authenticated compressed carriers are retained for
exact subsequent metadata reuse. Related original source, selected metadata,
receipts and private probe scripts total 5,027,322 bytes within the approved
5 MiB phase cap; other carrier contents are not extracted as members. An invalid
41-hex manual transcription was rejected before directory decryption, explicitly
corrected against the original 20-byte descriptor, and preserved in the private
receipt. Subsequent comparisons use parsed digest bytes directly.

The already retained Global updater supplies a concrete official dynamic-key
route: version/platform `PACDKCINFO_` parameters, followed by native Base64
keychain creation, group refresh/deserialization and registration. Its referenced
`PaperKVMgr` calls `/v1/gameconfig/parameter` through the original URL/signature
builder and remote-JSON consumer. That builder consumes
`UX6PackageSettings.CMSApiUrl`, `ClientID` and `ClientKey`. The original SDK manager
explicitly overrides the baseline SDK configuration from these native fields;
launcher values and baseline SDK values therefore cannot be substituted without
proving ownership. Effective regional selection, final protocol validation and
the dynamic-chain deserializer remain open. No request using guessed
client material, community key, Lua VM or original game execution is made.

## Passive Android relocation metadata

The authenticated native owner's settings-function registration uses packed
`SHT_ANDROID_RELA` / `APS2` metadata. No maintained toolkit APS2 parser was found;
the existing other-game helper covers ordinary RELA only. The new neutral
`publisher_android_relocations.py` validates the complete bounded section and
returns only specifically selected offsets/addends, never a full pointer map.
It applies or executes no relocation or original code and proves no CMS setting
or regional client identity by itself.

Group/additive state follows AOSP's
[original relocation iterator](https://android.googlesource.com/platform/bionic/+/refs/heads/main/linker/linker_reloc_iterators.h).
An explicitly enabled source dialect also accepts exactly bounded, ten-byte
zero-extended 64-bit delta words, consistent with AOSP's
[word-width decoder](https://android.googlesource.com/platform/bionic/+/refs/heads/main/linker/linker_sleb128.h).
Only offset/addend deltas can use that option; count, flag, info and initial
offset framing stays strict. Integers wider than the word, malformed LEBs,
arithmetic overflow/underflow, excess groups/matches and trailing bytes fail.

Thirty-nine authored cases cover every group-flag combination, cross-group
state, signed/zero-extended equivalence, sparse selection, truncation, malformed
integers and resource bounds. A source-hash-bound offline replay validates the
entire original 11,274,727-byte section twice: 1,868,734 records and 66,808 groups
per pass. Sparse results locate the reflected `GetX6PackageSettings` name in its
original registration metadata. No native method body or original code is read
or executed by that format proof. The source is the previously authenticated CN
module; this does not establish Global settings, settings values or a complete
fresh native preparation. Further owner-specific semantic work remains separate.

## Original settings owner and regional-selection gate

Separately approved, bounded static inspection follows that exact reflected
registration through the native result store, class factory and default-object
getter. The factory identifies `/Script/X6Game`, `X6PackageSettings` and the
`X6PackageSettings` configuration category. Argument roles are checked against
Epic's [class-factory declaration](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/CoreUObject/UObject/GetPrivateStaticClassBody?application_version=5.5):
the fourth argument registers native methods; the constructor is a later stack
argument. An earlier registration-callback/constructor interpretation is explicitly
corrected in the private proof. The actual constructor initializes storage and
calls a base helper; the inspected instructions do not provide regional CMS
values. This remains a CN/common native owner, not proof of a Global default.

The matching Global publisher inventory independently identifies the original
`Default_Ini_2872_P.pak` configuration family. One approved 958,806-byte BuildPatch
carrier supplies five complete selected files totaling 510,135 bytes, including
the 508,202-byte PAK. Strict generation checks, complete chunk integrity and all
five manifest-declared file SHA-1 checks pass. The companion signature's eight
CRC blocks also agree with the complete PAK; that CRC check is not a new RSA
signature verification. Native-derived default material verifies both complete
plaintext indices and all 232 compact-entry references.

Exactly nine source-owned settings INIs are then decoded from that verified
whole PAK with zero new network bytes. Their combined 16,726 decoded bytes pass
member-header, bounds, decoding and member-SHA-1 checks. Ordered sections,
assignments and operators are preserved privately; application credentials and
their values are not published. The relevant section is
`/Script/X6Game.X6PackageSettings`. Each file explicitly assigns `CMSApiUrl`,
`ClientID` and `ClientKey` once. The nine files form two different equivalence
groups, so they cannot be treated as universally interchangeable:

| Explicit source fields | Checked settings variants | CMS host and equality |
| --- | --- | --- |
| `GameArea=Cn`, `RegionId=1` | Default and `Area_CN`, `Area_CNB`, `Area_CNS` | `api-infinity.papegames.com`; the three CMS fields agree within this group. |
| `GameArea=Oversea`, `RegionId=4` | `Area_ASG`, `Area_ENG`, `Area_OS`, `Area_OSE`, `Area_OSS` | `api.infoldgames.com`; the three CMS fields agree across all five variants. |

These are literal source fields and directory names, not inferred meanings for
the area abbreviations. Channel values differ; `OverseaRegion` is explicit in
only two of the five latter variants. The retained successful anonymous Global
launcher response reports `(region, channel, role)=(4, 3, 0)`, which matches one
of these profiles by values. Original Global `FirstLoginViewModel` metadata
independently maps `RegionId`, `ChannelId` and `Role` to those three patch-list
request fields. That method has platform/audit predicates and is not claimed to
run on PC. Other updater methods read `CMSConfig.Region/Channel` from
`UPaperHotUpdateRuntimeSettings`; the build-version field named `Region` is not
silently equated with `X6PackageSettings.RegionId`.

Epic's [configuration hierarchy](https://dev.epicgames.com/documentation/en-us/unreal-engine/configuration-files-in-unreal-engine?application_version=5.5)
defines later-layer overrides, and its [target reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-build-tool-target-reference)
identifies `CustomConfig` as an additional build-selected configuration folder.
Those generic rules do not identify Nikki's actual selected Global build or
prove every game-specific merge/override. The current source-owned selection
and effective-setting chain must still be bound before making a CMS request.
Agreement within the RegionId-4 group narrows that question; it does not justify
using default/CN values or launcher credentials. No CMS request, original-code
execution, nonzero-GUID default-key attempt, caption/voice binding or Ready
snapshot is claimed by this checkpoint.

The retained Global request builder now supplies its exact static signature
dataflow: the settings object's `ClientKey` followed by the formatted timestamp
feeds `UX6BlueprintLibrary.GetStringMD5`. Fixed query fields are `clientid`,
`timestamp` and `sig`; string parameter values use the original percent-escape
rule. The single-chain parameter is `<platform>_PACDKCINFO_<version>`; a group
uses `<platform>_<group-id>_<version>`. These orders come from instruction
operands, rather than concatenating a guessed URL from constant names.

The same authenticated native source's reflected string-parameter/result edge
reaches a concrete hash and conversion owner. Bounded passive inspection proves
ASCII byte preservation in scalar, 32-byte SIMD, 8-byte SIMD and remainder paths
for the nine checked settings' ASCII signature inputs. The output formats 16
digest bytes with `%02x`. The algorithm profile independently matches the
[MD5 reference](https://www.rfc-editor.org/rfc/rfc1321.html): four initial state
words, all 64 round constants, all 64 rotations in their canonical order,
padding/length framing and little-endian digest serialization. This is stronger
than a function name or IV alone; it is not a complete proof of every transform
Boolean expression/message-word selection or execution of the original code.

The final completion phase stops at its eight approved windows and 3,324 new
instruction bytes, below the 4,096-byte cap, with zero network bytes. Its private
ledger explicitly invalidates one 64-byte off-owner data read caused by a manual
padding-pointer transcription. The corrected comparison derives the pointer
from original instructions; no value from the mistaken range is published or
used. The CMS response envelope exposes `gameConfigParameter.key/value`, not an
independent current-edition assertion. Exact requested-key equality, native
keychain/group framing and compatibility with the current Global package GUID
and full plaintext index hash remain required before acceptance. No CMS request
or new preparation capability is delivered by this static protocol checkpoint.

The shared `publisher_pe_signature.py` now isolates the existing Windows offline
Authenticode verifier behind explicit publisher identities and a selected-file
size bound. It preserves locked-handle, reparse, offline trust, signer and
post-verification hash checks. Endfield's wrapper retains its existing publisher,
16 MiB limit, API, receipt and unavailable-host failure. This adds no Android PE
chain capability; the shared APK/JCA RSA primitive is not a substitute.

The ordinary Nikki provider now continues from the verified native stage to a
context-owned Global launcher-source quote. It discovers the current official
website/NSIS metadata, pins actual source size and strong ETag and quotes the
complete selected member plus its final generation check before transfer. Disk
requirements bound the temporary decode; an upper-bound label remains explicit.
The consented download checks framing/Deflate EOF and complete PE publisher
trust, retains the verified original source and a hashed receipt, and returns
only `global-sdk-source`. Requote rediscovers changed validators; cancellation,
source/signature failure and damaged receipts preserve prior data. Restore is
local and reports the next SDK reader gate. Android's missing PE verification
capability is disclosed before the native bootstrap download and cannot fall
back to a verifier running on the development PC.

Launcher config/SDK ciphers now accept the explicit shared cryptography object;
their default desktop implementation is lazy. Pure anonymous SDK request and
response functions are also used by the retained legacy discovery entry point;
the next ordinary continuation still has to wire these through context-owned
transport. `infinity_nikki_build_stage.py` now supplies that ordinary continuation:
it reconstructs the anonymous request from the verified PE, uses only
context-owned POST/GET operations and follows the returned Global build pointer.
The current original BuildVersion response is plain UTF-8 JSON; bounded unique
fields, finite values and the source-owned version/path schema are checked.
An actual wrapped response instead needs material freshly derived from the
retained, verified native source. A directory name does not imply a wrapper.
It quotes both actual manifest sizes/strong ETags before
whole transfer. Complete local SHA-256, authored JSON/chunk/file ownership and
final generation-prefix checks bind the retained base/FastPatch manifests.
These local manifest hashes are not separately published publisher signatures.
Requote reads fresh SDK/build identities; modified consent, damaged sources or
interrupted updates retain old data. Local restore reports the explicit
configuration-reader gate. SDK region/channel values and `build.Region` stay
separate; patch precedence is not inferred from role labels or `CustomFields`.

The next ordinary stage now selects the manifest-owned current
`Default_Ini_<DefaultVersion>_P` package and all five companions as a single
verified source group. Missing companions or multiple base/FastPatch owners
stop before acquisition; overlay precedence is not guessed. The quote includes
complete shared carriers, unused mixed content, temporary storage and generation
checks. Complete chunk SHA-1 and all five file SHA-1 checks are required before
retention; a companion file's checksum is not independent signature acceptance.
Requote, interruption cleanup, modified consent and offline retained-file
checks use the ordinary preparation contexts. The next ordinary plan now derives
the zero-GUID material afresh from the retained authenticated native consumer,
checks this complete Global PAK's main/directory plaintext hashes, and sizes
only index-owned settings-category members. Nonzero GUIDs stop before trying
the default producer. CustomConfig variants are discovered from the directory,
without a regional-label allowlist or profile selection. Members remain inert:
the required decoded disk size and compression names are shown, but no neutral
owned Oodle capability has been accepted for this provider. No member decode or
desktop fallback occurs during that plan. Ordered INI preparation is still open.
The nine private research INIs cannot supply that missing preparation. CMS
construction must consume its future verified source receipt and keep the
response/keychain gate explicit.
The PAK reader now accepts the same explicit platform cryptography object;
desktop cryptography is lazy, and absent-pack fixtures distinguish encryption
from stored-size width. This removes that import barrier without proving an
Android device runtime or admitting a nonzero-GUID archive.
Separately bounded native registration work identifies two original
consumers: creation receives `(chainName, Base64value)` and group serialization
receives `(chainName, groupID, Base64value)`, both with no result. Their concrete
native call edges are identified; their bodies and serialized schema remain
unread. Neither a cache-getter's direction nor a UClass owner is inferred from
adjacency alone. No extra remote source bytes or CMS requests are acquired.

A frozen ordinary launcher-stage replay uses the actual previously retained
official NSIS/PE bytes, the normal provider and preparation contexts, the actual
Windows PE trust verifier, and local restore. Its quote is 6,849,423 bytes,
including the final four-byte generation check, with a 74,217,459-byte disk
upper bound. Peak additional files are 229,713,140 bytes, below the approved
230 MiB replay cap; exact temporary native/PE copies are then removed. Original
source and complete earlier APK-v2 receipt hashes remain unchanged. The native
input is explicitly adapted from that historical complete receipt and passes
the native consumer/retained-source checks again. The missing old launcher ETag
is replaced only by an explicitly authored offline HTTP validator. This proves
the frozen source-stage boundary, not a fresh server generation, real original
ETag exchange, repeated cold APK stream, current SDK server reply or game data
readiness. It fetches zero new source bytes and uses no research INI shortcut.

A subsequent frozen metadata probe obtains one real anonymous SDK response,
the source-returned plain BuildVersion JSON and two 32-byte manifest prefixes:
11,522 new response bytes in total, with no software, PAK or voice acquisition.
The current manifest pins match both earlier completely verified source files.
Those whole manifests are replayed through ordinary contexts from retained
bytes, checking 507 base and 188 FastPatch file owners. The manifest quote is
42,448,925 bytes, including generation checks, with 42,597,252 bytes of additional
disk. The final generation checks in this replay reuse the captured fresh
prefixes; this is not a fresh whole-manifest download or an independent
post-download server check. The prior native receipt and authored old launcher
validator retain their qualifications. Peak additional files are 272,206,692
bytes, below the approved 300 MiB cap; exact temporary copies are removed and
original hashes stay unchanged. The initial wrapper-only assumption safely
stopped on the original plain document and was corrected before replay; the
actual SDK response and request timestamp were retained without a second POST.
No snapshot, selected profile, dynamic keychain or language readiness is proved.

The frozen configuration-carrier continuation also passes from the normal
retained parent receipts with zero new response bytes and no research INI input.
It reconstructs all five complete source files and verifies the same manifest
SHA-1 values. Its quote is 958,838 bytes / 2,649,484 additional disk bytes; peak
temporary files are 272,730,445 bytes, below 300 MiB. Only exact temporary copies
are removed. This replay uses the carrier's historical original ETag and does
not establish a fresh configuration-server generation or companion RSA trust.

The separately frozen ordinary index continuation also passes from those normal
source receipts: freshly derived RAM-only native material verifies this Global
configuration PAK's full indices and discovers nine settings members, 16,726
decoded bytes, all Oodle. The inactive next plan shows zero additional download
bytes and 16,726 bytes of member storage. No member is decoded and no profile is
selected. This phase acquires zero new response bytes, retains the same historical
source qualifications, stays below 300 MiB of temporary files and removes only
its exact temporary copies. An accepted owned Oodle capability remains the next
concrete runtime requirement.

## Presentation inventory and finite completion boundary

| Presentation | Primary evidence and remaining work |
| --- | --- |
| Story conversations and cinematic captions | The official update notices and sound-design report describe story dialogue and cutscenes. Original tables, authored display boundaries, speaker/voice ownership and capture regions remain unverified. |
| Graphic/text reading material inside dialogue and History | The [Version 2.3 notice](https://infinitynikki.infoldgames.com/en/news/447) describes independent layouts, a full-screen view and History review. A bottom-only subtitle crop cannot establish this coverage. Original text and voice state remain unverified. |
| In-world musical performances, boss performances and cinematic song/narration | The publisher's [Music Season sound-design report](https://infinitynikki.infoldgames.com/en/news/319) describes independently positioned NPC vocals and a final cinematic musical, including French pieces. Original performance language must be retained; a vocal's language is not necessarily the selected dialogue dub. Subtitle availability and source ownership remain unverified. |
| Choices, ambient captions, messages, documents and other active layouts | Inventory current official resources and representative online gameplay before marking these supported or absent. Do not infer silence from a missing pack or unresolved binding. |

Prioritize demonstrated current subtitle presentations. Unreferenced historical
or event resources are research inventory until current use is shown; they are
not automatically missing active dialogue, cut content or unvoiced lines.
Sounds with no on-screen subtitle do not block subtitle coverage.

## Remaining acceptance work

1. Complete fresh official Global/mainland bootstrap and current game
   inventories, original text/binding/voice containers, integrity fields and all
   voice locales. Global anonymous manifest-pointer discovery is implemented;
   the original native wrapper owner/decoder is now evidenced, and its
   address-independent reader has passed original-source replay. Independent
   mainland SDK acquisition and downstream current resource inventories remain
   open. Automatic native-owner acquisition now has a canonical quoted stage;
   a fresh end-to-end original-source run and actual Android runtime/device
   acceptance remain open.
2. Implement bounded manifest-based text-only versus text-plus-audio selection,
   size planning and download/deletion through the shared game-data manager on PC
   and fully independent Android. Preserve history, recordings and user settings
   when deleting prepared game data.
3. Validate Android-compatible owned readers and codec runtimes from actual
   format evidence; a Windows-only extractor or a community-prepared library
   does not meet the requirement.
4. Resolve authored text/translation/voice bindings for demonstrated current
   presentations and distinguish voiced, confirmed unvoiced, missing-pack and
   unknown entries. Verify all official dubs without inventing bindings.
5. Run changed-resource discovery and two consecutive official-generation
   preparation, interrupted-update retention, retry, offline restart and
   playback checks on PC and Android.
6. Register the completed game in the support matrix, generated language guides,
   installation/setup/capture/export surfaces and capability regressions. No
   supported-game registration or completed-game claim is made by this discovery
   stage. Keep #145 open until those acceptance conditions pass.
