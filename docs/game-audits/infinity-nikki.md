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
   mainland SDK acquisition, automatic authenticated native-owner acquisition
   and downstream current resource inventories remain open.
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
