# Honkai: Star Rail dialogue audit

## Original hotfix discovery prototype · November 16, 2026

The standalone `starrail_original_discovery` API now discovers the current Global
4.7 routes through official public dispatch responses. It does not fetch PutraZC,
send account fields, log in or execute client code. **Production release
discovery still uses the existing provider.** A native-helper lifecycle and
automatically prepared descriptions are not enabled by this change.

The minimal original bootstrap consists of two files from the fully checksummed
launcher manifest:

| Original file | Bytes | Whole-file MD5 |
| --- | ---: | --- |
| `ClientConfig.bytes` | 201 | `bfed4c1f95a3f99f1c50b7cfb77d338a` |
| 4.7 `BinaryVersion.bytes` | 246 | `19e416ef427578caf0d73c4762f835df` |
| 4.6 `BinaryVersion.bytes` | 246 | `9f912acbfa508881ae6978f221b1f5d9` |

Native `ClientStartupConfig.Load` explicitly loads `ClientConfig.bytes`. Its
native deserializer establishes four strings, four counted string arrays and
the default-server integer. The supplied description consumes all 201 bytes.
The 4.6 and 4.7 client-config bytes are identical. Version data uses big-endian
integers, signed 16-bit UTF-8 byte lengths and booleans; both original 246-byte
files consume all 31 operations. The private diagnostic derives the version
operation order and named stores from native call signatures. Request version
and dispatch seed come from these original inputs; seed values are not stored
in the published discovery receipt or repository.

The larger original `data.unity3d` carrier independently corroborates ownership:
its fully verified 23,289,537-byte UnityFS file contains serialized-v21
`resources.assets`. The bounded object directory identifies object 455 as
TextAsset class 49, named `ClientConfig`, containing the JSON
`GlobalDispatchUrlList`. Every binary-config field matches that object. Only
52,690,944 bytes of relevant serialized metadata were expanded in memory; no
game binary was loaded or executed. The existing locked `ooz-wasm` decoder
handled payload compression. Normal standalone discovery needs the two small
bootstrap files, not this carrier.

The native diagnostic locates methods from managed type/signature metadata,
then reads their original method bodies as data. It joins semantic
`ServerDispatchData` fields to protobuf-object members through the original
parser's copies, and those members to wire tags through `WriteTo`. Global
region-list, name and primary/alternate gateway tags are independently joined
through the original repeated-field codec, region writer and
`SetDispatchUrls` caller. Method addresses, obfuscated protocol type names,
resource revisions and protobuf field numbers are discovered inputs; there is
no per-version address or tag list in that diagnostic.

| Native-derived resource field | 4.6 field number | 4.7 field number |
| --- | ---: | ---: |
| Design data | 5 | 5 |
| Asset bundles | 15 | 6 |
| Lua | 2 | 7 |
| Base asset bundles | 1,335 | 1,379 |

The same frozen extractor handles both generations' changed tags. The initial
4.6 diagnostic used authenticated Sophon chunks, which did not establish whole
file integrity. A subsequent bounded acquisition completed all three original
4.6 files from manifest MD5 `65fc23eec5dce74324cada65dc595341` and verified
their complete sizes and MD5 values:

| Original 4.6 input | Bytes | Whole MD5 |
| --- | ---: | --- |
| GameAssembly.dll | 543,701,808 | `d33cb7b0781287362e7f3d8571b520aa` |
| global-metadata.dat | 102,982,324 | `c255e9fee5d03234847feb4b38cfd4c3` |
| startup-metadata.dat | 4,091,208 | `16ebd221c3040a97210086ede71ab464` |

The frozen GPL metadata reader then regenerated both outputs from these complete
publisher inputs, reproducing the retained original-derived output byte for
byte. The fresh 182,828,387-byte dump has SHA-256
`990529a865cdb848b18ed253df5448ada0059916660396ec6bd2e0877d2424a8`;
the 12,024,282-byte literal output has SHA-256
`c6af79ee5c6fdcfe91f44586561a825822da342f6cdefbb1f276d6c6141824be`.
The same source/entrypoint also regenerated complete 4.7 inputs exactly.

Using the current original bootstrap and derived fields, the standalone API
obtains four Global regions, follows the publisher's default gateway and
resolves design/ASB/base/Lua routes. It validates HTTPS domains, required wire
types and unique fields, and verifies all five native revision markers. Their
complete revision/MD5/size tuples exactly match the 4.7 input generation in the
table proof below. A supplied description must match the actual launcher
`GameAssembly.dll` MD5; another client's description cannot silently replace it.
Bootstrap paths are supplied inputs too: the private probe resolves native
`Load` literals against the original launcher inventory, and synthetic renames
use the same standalone API.

The owned `starrail_native_description` API now derives the ClientConfig layout
from matching original metadata and decoded native instructions. It identifies
the binary reader through the unique dominant owner of no-argument primitive
calls in `VersionData.Deserialize`, then joins public config field names/types
and offsets to the native return stores in serialization order. String arrays
require count, allocation, indexed string-store and loop-branch evidence. Every
public field must be accounted for once, with consistent object registers,
primitive kinds and store widths. Missing, duplicate, unsupported or ambiguous
evidence fails closed. Scalar return aliases cannot be overwritten before the
matching store; the shared receiver register cannot be rebound while fields are
being read. Independent instructions and register reads remain allowed.
The implementation bounds method evidence to 8,192
instructions and a 64-KiB span, and config metadata to 256 fields. It contains
no release, address, field-offset or nine-field order list.

The same frozen owned API derives all nine fields for 4.6 and 4.7, despite their
different native offsets and parser bodies. Both original files consume exactly
201 bytes and yield the same canonical decoded-value SHA-256
`9e904d4efe0c9bde40b083d82fe0f0a3921669906f4d2dd1bd03babb0e131536`.
This description replay downloads no new native bytes. Synthetic evidence covers relocated
fields, new scalar fields, conflicting primitive owners, incomplete stores,
malformed bounds, missing array evidence and clobbered scalar returns.

This API takes metadata and disassembly as inputs; it does not authenticate or
generate them, load a native library, or prove arbitrary native control flow.
The retained `HSRGlobalMetadata` helper at frozen revision
`bb66f7c59d73cadcd026d817a011598ea23c5313` has fixed metadata codecs and string-key
formulas. Its successful extraction for these inputs does not prove recovery
after a key/layout change. A compiler-free, provenance-checked helper lifecycle,
automatic metadata codec derivation from original native data, and descriptions
for the additional catalog tables remain prerequisites for enabling production
discovery. No additional third-party helper or binary is shipped by this change.

The standalone owned API also exposes `string_key(instructions)` for the
evidenced masked-index string codec. It joins the original signed-index mask
selection, multiplier/add seed and scalar block-step operations, requiring unique
compatible instruction evidence. Its operands are derived data; there is no
known-key list or fixed native register. Synthetic tests change all arithmetic
operands, index masks and registers and reject incomplete or ambiguous joins.
The private 4.7 probe locates the native header pointer from its original
initializer and uses PE exception-directory entries for accessor bounds. The
4,571-byte string accessor has SHA-256
`bd68f13fa7a44b1fb6706810a3cea5116609de2507ea97a2d387e08c4960fa1d`.
The owned API's derived parameters decrypt 64 deterministic original metadata
namespace/type names exactly matching the retained helper output, with combined
verification SHA-256
`864f8f16f172e689ff133c23f8ea05cf370dbc081ea59058160a9699bd28ce1c`.
The native input's whole-file MD5 is `2db87084b0383dbe7ce3556bb33db662` and the
original global metadata MD5 is `ba110cdff0a1c2588333f7f2071e3ec6`, both checked
against the official 4.7 manifest. No native code is executed or downloaded by
this replay. Actual key bytes and native code remain private.

This string-key result still uses frozen semantic header slots, record layout
and the evidenced scalar codec shape. A separate bounded native probe recovers
arithmetic operands agreeing with 21 of the helper's 28 semantic header fields,
with zero conflicting recovered expressions; seven fields, table-record codecs
and string-literal codecs remain unresolved. It does not establish relocated
slot ownership, an actual changed-key release, configurable helper decoding or
normal-worker recovery. Production metadata preparation remains disabled.

The current public server rejects the 4.6 request with scalar field 1 equal to
4 and an update-required message, supplying no regions. The same standalone
API parses the old bootstrap, reports source unavailability and retains the
previous complete discovery receipt byte-for-byte. This is publisher retirement,
not evidence of an unsupported format. No successful old live gateway replay is
claimed. Strict synthetic tests also cover changed supplied tags, malformed
bootstrap/protobuf data, other URL destinations, native-identity mismatch and
incomplete marker responses without replacing a complete receipt.

These are discovery and parameter-recovery contracts. They do not prove the
normal production worker, every original catalog table, changed audio playback,
all regions, or full update/restart/interruption acceptance. The 4.6 → 4.7 text
and voice changes below remain valid original-package evidence, but the retired
old dispatch response does not turn that comparison into a complete autonomous
update trial.

Sources: [official public Global dispatch](https://globaldp-prod-os01.starrails.com/query_dispatch),
[official launcher manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD/manifest_08c01a4f44bfa674_38615c5752d4bdeb90700ad54e5a54b1),
[official earlier launcher manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20260918/4.6.0/5ojqcjYEliu4/manifest_edb916e5a1ca140c_65fc23eec5dce74324cada65dc595341).

## Original text and voice-table prototype · November 16, 2026

The standalone `starrail_original_tables.OriginalTables` reader now reads native
`TalkSentenceConfig`, `VoiceConfig` and full/startup `Textmap` resources directly
from official DesignV packages. Its `file(relative)`, `table(name)` and
`textmap(code)` interfaces do not access a text mirror or require a game folder.
**The production `ReleasedCatalog` has not switched to this reader.** Production
integration of independent discovery, metadata preparation and automatically
generated complete catalog descriptions remains work for #84. This prototype
does not complete autonomous updates or current subtitle coverage.

The format descriptions were established from the original publisher client's
native `FromBinary` methods and managed field metadata. They are serialization
descriptions, without a version list, method-address list or dialogue ID list.
`TextID` contains a legacy signed hash and a current unsigned 64-bit hash.
Native masked rows, canonical integers, booleans, UTF-8 bounds, row counts,
unique identities and complete resource consumption are checked. New fields
require a newly derived description; the reader accepts supplied descriptions,
but does not yet derive them automatically. Unknown voice-type values remain
numeric and are never promoted to `NoVoice`.

The standalone reader also accepts a complete supplied `descriptions` mapping.
Each table describes its ordered fields, optional single/composite identity,
native hash-byte prefix and enum values. Explicit unkeyed descriptions preserve
the original sequence; the reader does not guess an identity column. Supported
array elements are unsigned integers, strings and finite little-endian floats,
with signed zigzag array counts. Unknown description keys, unknown field kinds,
noncanonical numbers, negative/oversized counts, malformed values, duplicate
declared identities and trailing bytes are rejected. Unknown enum values retain
their numeric value. A supplied generation replaces the default descriptions
completely, so missing descriptions cannot mix an older table into preparation.

The current original native probe derives filename-to-row bindings for all 21
tables actually requested by the catalog, including nine obfuscated containers.
It follows original filename literals into typed path arrays and their static
fields, and uses typed row dictionaries rather than a class-name suffix or
rename list. Static field representation is inferred across constructors.
Original `FromBinary` bodies establish all 109 serialized field-bit positions.
The native loader call establishes the additional one-byte hash prefix for
ordinary tables; the three LRU tables use their direct counted row resource.
Native shared helpers establish signed array lengths and enum serialization.

The owned preparation adapter now regenerates the metadata from complete
publisher inputs and derives these descriptions through the managed decoder.
It does not consume retained research dumps, a Python disassembler or a newer
third-party data snapshot. Managed identities distinguish duplicate display names
and nested method/field scopes. Typed arrays must reach original global/member
static storage; heap element stores and clobbered receivers cannot establish a
filename binding. Each serialized field requires a masked, owned native read or
field-address argument, with complete and unique bit positions. Inline text IDs
require the recognized signed legacy-hash expression and the later unsigned
current-hash read in the same field, rather than accepting arbitrary overwritten
registers.

Bootstrap derivation includes the native string-to-enum conversion for package
type: original label/constant pairs, string argument flow and enum return flow
must agree. Its bounded static branch graph handles the guarded compiler jump
table without running native instructions. The complete current pipeline derives
nine ClientConfig fields, 31 version-reader operations, the resource wire tags,
21 filename/row bindings and all 109 serialized fields. Field order, prefix and
enum descriptions agree with the independently validated original-resource
descriptions. A descriptor generation is cached only after all required schemas
pass; helper, input or derivation changes invalidate it. An incomplete attempt
preserves the previous receipt and complete generations.

Using those descriptions, this reader consumes all 21 original resources to EOF
and matches 368,989 semantic rows against the frozen verification snapshot, with
zero missing or extra rows. All resources come from the already whole-MD5-checked
common package below; this adds no downloads. Float comparisons use float32
values and treat positive/negative zero as the same JSON number; decoded values
retain their sign. Enum descriptions and managed metadata are still supplied
from the retained original-derived metadata output. This proves the table
reader contract, not ordinary worker, restart or recovery acceptance.

The separate [metadata helper](../../packaging/starrail-reader/README.md) now has
a source-pinned build and compiler-free resource contract. Its metadata-only
GPL entrypoint regenerates the needed dump without Mono.Cecil or dummy assembly
export. Its pinned MIT managed decoder reproduces all nine ClientConfig fields
through the unchanged owned description API for both versions, and the native
string codec description for 4.7. Exact corresponding compiler source, build
material and full licenses travel with the executable and are checked at
runtime. Functional local builds used SDK 10.0.302; they are not pinned delivery
acceptance. The shared builder requires SDK 10.0.403/runtime 10.0.14 and runs
authored malformed-range/output-preservation probes. Ordinary provider
integration and full update recovery remain unfinished. The
complete current native-description preparation adapter is implemented; its
ordinary two-version worker acceptance and pinned distributable still need their
own checks. The GPL metadata decoder continues to use its frozen software
profiles; the separately demonstrated owned native-key derivation is not yet a
complete metadata-profile recovery fallback. A newer third-party game-data
publication is not needed for this frozen software path.

The complete current adapter also succeeds against the live public dispatch
using its freshly generated description. All five resource index identities
match the original 4.7 generation below. Passing its generated table descriptions
directly to `OriginalTables` consumes all 21 original resources and 368,989 rows.
An authenticated descriptor cache skips metadata indexing and disassembly on a
repeat attempt. This is original route/table preparation evidence; it does not
yet establish the ordinary setup worker, regional editions, playback or recovery
acceptance for the new provider.

The current proof uses Global 4.7.0, launcher build `8Mu3l7s23x8Q`, and DesignV
revision `17180467`, index MD5 `5e340a3628885b9fde90bdd2d15ce3ee` (2,307,298
bytes; SHA-256 `5284b90a06258fd816002e9a8c1acc8ef7abc551e953420c22278943cc963b4f`).
The original native client identity is GameAssembly MD5
`2db87084b0383dbe7ce3556bb33db662`; its metadata MD5 is
`ba110cdff0a1c2588333f7f2071e3ec6`, both acquired through the checksummed
launcher manifest. No game, Lua or downloaded native code was executed.

The index tail is significant: full localized packages live under its locale
folder, such as `en/<package-md5>.bytes`. It must not be discarded or inferred
from a translated string. The common package
`2c0856f09fbc10734c0f146a92a0a6e7` is 33,508,837 bytes. All 248,809 original
sentence rows and 92,131 voice rows match the already frozen
`dad9155eb00fdeda31fb8456507c53590d49071f` extraction for IDs, subtitle/speaker
hashes, authored voice paths, player involvement and voice type, with zero
field differences. That extraction is a verification oracle only; acquisition
and parsing do not read it.

| Official text locale | Full native rows | Full package MD5 |
| --- | ---: | --- |
| `cn` | 495,527 | `2992a81e50e9f57b177c31317600ada3` |
| `cht` | 492,796 | `fbd9aede173c6888ab5aaacdb508ef14` |
| `en` | 492,775 | `8f2f7a1ecaaa1925379866fd7af4fc6f` |
| `jp` | 492,775 | `e730127b7487b045ea30fd421a86fb6d` |
| `kr` | 492,767 | `22f4cc5390208f911a0b6d05a0020207` |
| `de` | 492,772 | `53dac0a9818d262ac7bd35908240ed5b` |
| `fr` | 492,771 | `22786333eda53e63c0b9b93b4476c7e7` |
| `es` | 492,771 | `3c138a185e8f9131f29b6c064478ae68` |
| `pt` | 492,772 | `f1bd2cf8cb461e996fda5841900c00df` |
| `ru` | 492,769 | `53de262b7c092e946ef42c9820d36b5d` |
| `th` | 492,772 | `c8a692590fbdae07d012bec285f45325` |
| `vi` | 492,772 | `3e2d4c5212c3bf02f7759e91637f50d2` |
| `id` | 492,774 | `1c9cd6b0ceca400f810c173a25e77a90` |

All fourteen complete packages total 1,004,288,509 bytes and pass their whole
publisher MD5, taken from the fully MD5-verified official DesignV index. Earlier
range probes alone had only HTTP range/ETag checks and private SHA-256 receipts;
they were not whole-package verification. The reusable reader now gates every
package on complete MD5 before parsing or atomically caching it. A failed new
download leaves previously complete packages intact.

The frozen prototype structurally parsed all 6,408,813 full text rows against
their original header IDs, offsets and lengths. It then resolved the same 64
deterministically selected sentence IDs, comprising 111 subtitle/speaker hashes,
in every locale: 1,443 strings, zero missing and zero differences against the
frozen extraction. The standalone reader independently parsed all thirteen
complete tables. Textmap row totals include interface and inactive strings;
they are **format evidence, not an inventory of active subtitle presentations**.
This Global result does not independently verify mainland package bytes.

The same reader and descriptions also parse an earlier official 4.6.0
generation, DesignV `16854589`, index MD5
`a7312833dc866a77217b1c26ef9bc0eb` (2,262,050 bytes). Its common package
`1efaad7a4e7c92a8a12c66cffbe3b50a` and English/Japanese full Textmap packages
`fc21263410cd08ba5f5ac5ff280c1582` / `2b654227cd0aec5f517143f926880c96`
also pass complete publisher MD5. Together these three packages add 164,241,325
bytes. The reader code and descriptions stayed byte-identical between the
4.6 and 4.7 reads, and the comparison reads no third-party text/voice rows.

| Original input comparison, 4.6 → 4.7 | Added | Removed | Changed existing |
| --- | ---: | ---: | ---: |
| Sentence rows, 244,380 → 248,809 | 4,429 | 0 | 16 |
| Voice rows, 90,284 → 92,131 | 1,847 | 0 | 0 |
| English strings, 474,199 → 492,775 | 18,912 | 336 | 262 |
| Japanese strings, 474,199 → 492,775 | 18,912 | 336 | 265 |

Of the new sentence rows, 1,805 join an original voice path and original
English/Japanese text. This demonstrates content changes rather than a version
label change. It does not establish which rows are active subtitle
presentations or prove changed audio playback. Both route sets were supplied
explicitly: the older set came from the already documented frozen
`8fe88ba411d4` route directory. Production still obtains current routes from
PutraZC and most catalog tables from Dimbreath. Therefore this is a frozen-reader
data replay, **not the full autonomous update acceptance test**. Original audio,
production preparation/restart/recovery, every required catalog dependency and
independent route discovery still need their own combined evidence.

Sources: [official 4.7 DesignV marker](https://autopatchos.starrails.com/design_data/V4.7Live/output_17180467_2b67443267a6_475611c71617ea/client/Windows/M_DesignV.bytes),
[official DesignV index](https://autopatchos.starrails.com/design_data/V4.7Live/output_17180467_2b67443267a6_475611c71617ea/client/Windows/DesignV_5e340a3628885b9fde90bdd2d15ce3ee.bytes),
[official launcher manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD/manifest_08c01a4f44bfa674_38615c5752d4bdeb90700ad54e5a54b1),
[official 4.6 DesignV marker](https://autopatchos.starrails.com/design_data/V4.6Live/output_16854589_26047487232d_c2f00471f3ad4c/client/Windows/M_DesignV.bytes),
[frozen older route directory](https://github.com/PutraZC/HSR-Data/blob/8fe88ba411d4/hotfix.json).

## Battle College tutorial captions · November 16, 2026

Schema 25 adds the separate `Config/BattleCollegeCaption/<name>.json` family.
Current `LoopCGConfig` declares eighteen such paths and their actual movie
paths. All eighteen native resource hashes and complete caption hash/clock
sequences match the revision-paired extracted scripts: 45 cues total.
Names, movie IDs and package locations are data inputs, without an eighteen-file
allowlist or a guessed `CutSceneCaption` alias. Three numbered tutorial movies
use differently numbered caption files; the authored joins are preserved.

Two original Lua resources in current LuaV revision `17175930` establish the
presentation: `BattleCollegeDetailPanel.play_video` and
`BattleCollegeDetailVideoTabItem.play_video` read `LoopCGConfig.GetData(videoID)`,
pass that row's `CaptionPath` to `GameCoreConfigLoader.LoadVideoCaptionConfig`,
and pass the resulting config to the bound `CaptionComponent`. The same input
`videoID` goes to `ManaVideoPlayer.SetLoopCGID`. Both serialized prototype
containers were parsed completely as data, with bounded string/constant/prototype
references. The straight register/field/call joins use the shared early
[Luau instruction layout](https://github.com/luau-lang/luau/blob/c87565b8b0db5d5d5bfd2b8b00ad6573e5d06d9f/Common/include/Luau/Bytecode.h).
This is not a claim to reconstruct every custom game opcode or conditional.
No downloaded Lua, native client or patch was executed.

The fourteen original Lua packages total 54,375,173 bytes and all pass their
publisher MD5. Both relevant resources are in package
`9dcff474da9788d7a8ee73371914c509`:

| Caller resource | Bytes | Original resource SHA-256 |
| --- | ---: | --- |
| `b83a1ba5ba3d33be` · detail panel | 4,571 | `69cb014ba78d4bd0352af97eb7173b806d07da61f70c91e8b9614c648000c01a` |
| `0b4401db80f3d824` · video tab | 3,629 | `82b0d1e21515f86fe7d7e21dc1676cd87c053de8ee286a175db6ec0882c9be36` |

The matching original native `LoadVideoCaptionConfig` body at RVA `1e910050`
uses the same case-preserving `JsonToBinaryPath` and DesignV reader established
below. `CaptionComponent.SetCaptionConfig` owns the loaded caption list;
`TickCaption` compares its start/end clocks with the bound movie player's
loop-relative playback clock, and `_ShowCaption` calls `SafeSetTextID`.
Those are subtitle display clocks, without authority to cut spoken audio.

All thirteen text tables contain 38 of the 45 declared cues. The same seven
hashes are absent in every locale: three cues in tutorial 4, two in 12 and two
in 13. They remain missing; no neighboring prose or other language is inserted.
The new native anchors also discover two further caption cues at resource
`3254a8030939a1c7`. These remain anonymous unavailable neighbors without an
authored movie owner. They do not resolve the three older anonymous resources
listed below. The retained inventory is now 333 files / 1,989 cues, including
these four anonymous resources / 24 cues.

**Audio remains unavailable for the tutorial captions.** The authored LoopCG
rows expose only `VideoID`, `VideoPath`, `CaptionPath` and `IsPlayerInvolved`;
they declare no dub, Wwise recording or separate sentence audio. All eighteen
movie identities have matching optional format metadata. However, bounded
publisher reads of their complete CRID stream directories show video streams
and **zero `@SFA` audio streams** in all eighteen movies. Only 18 × 64 KiB of
movie headers were fetched, with exact range/size/publisher-MD5-ETag checks.
This proves absence of embedded tracks in those directories, not silence of
the entire tutorial interface or absence of a separate sound-event route.
No complete tutorial audio was decoded and no tutorial line is marked unvoiced.

Ordinary installation-free Global 4.7 preparation adds forty unavailable rows
in both English and Japanese: 38 localized declared tutorial cues and the two
unowned neighbors. English now has 307,464 records / 98,693 voiced; Japanese
has 307,455 / 100,170. Every pre-existing record, including audio and player
selection, remains byte-for-byte equal as structured data. The existing twelve
English and nine Japanese reviewed movie clips remain the playable movie set.
Both the new preparation and unchanged schema-24 snapshots reopen in fresh
offline converters. All 21 existing clips export twice with networking blocked,
nonzero decoded PCM, matching spoken durations and identical restart hashes.

[Revision-paired LoopCG declarations](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/LoopCGConfig.json)
· [Revision-paired tutorial captions](https://github.com/DimbreathBot/TurnBasedGameData/tree/dad9155eb00fdeda31fb8456507c53590d49071f/Config/BattleCollegeCaption)

## Declared caption resources resolved · November 16, 2026

All 138 previously unnamed, declared movie-caption files are now identified in
the current publisher directory. Their 974 cues already had retained text;
this correction establishes their actual caption paths, movie associations
and authored player branches. A caption's display clock alone does not
authorize a spoken audio cut. These files therefore keep unavailable audio
until the matching original performance and spoken window are verified.

The current Global 4.7 launcher supplies these three matching originals. Each
complete file passed its manifest MD5 and an independently recorded SHA-256;
the files were parsed as data. The implementation uses the ordinary resource
directory and release-paired translation catalog during preparation.

| Original file | Bytes | Publisher MD5 |
| --- | ---: | --- |
| `GameAssembly.dll` | 564,008,240 | `2db87084b0383dbe7ce3556bb33db662` |
| `global-metadata.dat` | 106,856,312 | `ba110cdff0a1c2588333f7f2071e3ec6` |
| `startup-metadata.dat` | 4,228,712 | `ef1d483fdd35702f8a8423b861fc7acc` |

[Official Global 4.7 game manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD/manifest_08c01a4f44bfa674_38615c5752d4bdeb90700ad54e5a54b1)
· [Static metadata inspection source](https://github.com/im-remi/HSRGlobalMetadata/tree/bb66f7c59d73cadcd026d817a011598ea23c5313)

Native method ownership and bounded body inspection establish the route:
`GameCoreConfigLoader.LoadVideoCaptionConfig` calls `JsonToBinaryPath`, then
the binary reader reaches `AssetLoader.LoadBinaryFromFile` and
`DesignDataMgr.SyncLoadBytesFromFile`. Both design-data providers construct
`DesignDataShortNameHash` from the complete path using UTF-8 and seed-zero
standard XXH64. `JsonToBinaryPath` preserves case, prepends `BakedConfig/`
and replaces the last filename extension with `.bytes`. Thus an authored
`Config/CutSceneCaption/<scene>_Caption.json` resolves through
`BakedConfig/Config/CutSceneCaption/<scene>_Caption.bytes`.
The small shared checksum helper implements the
[public XXH64 specification](https://github.com/Cyan4973/xxHash/blob/d66a9cb6f223b1f15cceebee39bc07ed0bd4ad3d/doc/xxhash_spec.md#xxh64-algorithm-description).
Production preparation needs no installed client or native metadata extractor.

The four initial reference paths match their existing resource IDs exactly.
All 173 independently published scripts, including the other 169 held-outs,
then match every one of their 946 text hashes and start/end clocks at toolkit
millisecond precision. The 309 unique `VideoConfig`/`CutSceneConfig` paths,
together with the published scripts, identify 311 current resources with
1,920 cues. All 311 keys exist and decode strictly; none of those declared
paths remains unresolved. This includes the 138 newly named files and their
974 cues. Names and package locations are read again for normal content updates;
resource resolution has no per-movie hash allowlist.

Ordinary publisher preparation independently selected the same 4.7 build
`8Mu3l7s23x8Q`, fingerprint
`sophon-2d949d4141f326b6d2d4a4df774bbb8788ed42c52300fb3a45249b1f9cef65e8`
and catalog `dad9155eb00fdeda31fb8456507c53590d49071f`, titled
`OSPRODWin4.7.0_D17180467_A17176203_L17175930`. All 974 newly named cues
have text in twelve of the thirteen supported text locales. Korean retains
three absent strings: `CS_Chap04_Act640` cues 6 and 28, and
`CS_Chap04_Act680` cue 49. No neighboring translation is substituted.
An independent mainland-China request for build `55EjVJ7DGGpF` read all
311 resources from the CN CDN; all 1,920 cues and every raw resource byte
were identical to Global. Both use DesignV revision `17180467`, directory
MD5 `5e340a3628885b9fde90bdd2d15ce3ee`.

Schema 24 retains anonymous resource identities separately from the newly
verified scene name. The one lyric scene named by an earlier reader retains
its existing canonical ID through an identity-only compatibility rule.
Previously unscoped player captions now have explicit male/female branches:
672 unavailable rows become 1,344 unavailable variants in each EN/JA probe.
Their display text follows the existing gender-template renderer. All other
existing records, including every playable audio binding, remain identical.
English now has 307,424 records with 98,693 voiced; Japanese has 307,415
with 100,170. These are extra actor-scoped caption records, not newly voiced
sentences. The twelve English and nine Japanese reviewed movie clips retain
their existing IDs, original recordings and spoken windows.

Three anonymous resources remain independently retained: `9d08b0c771adc0d9`
has thirteen cues, `dd207c8af15b4c72` has two and `95f542bc08cb0ea0`
has seven. Their 22 cues bring the complete discovered inventory to 314
scripts and 1,942 cues. They have no established caller or movie path.
The ten `CS_Chap02_Act610` text IDs remain absent in all thirteen text
locales, with no original movie/timeline binding. Korean also still lacks
`CS_Chap02_Act3020` cue 2, separately from the three newly named Korean gaps.
Other MultiVoice selection and spoken movie cuts remain open.

## Unnamed MultiVoice descriptions corrected · November 16, 2026

Two Benny descriptions were incorrectly offered with an NPC greeting as their
sentence audio. The original `TalkSentenceConfig` rows `413071601` and
`413071801` have neither a primary `VoiceID` nor an authored speaker name.
`TalkSentenceMultiVoice` separately references `424030190` and `424030196`,
whose `VoiceConfig` paths are `vo_ambient_w3_greeting_benny_104_calm` and
`vo_ambient_w3_greeting_benny_110_joyful`.

The released callers distinguish the presentations. `Act424030715` shows the
first description in an ordinary `PlayAndWaitSimpleTalk` list;
`Act424030716` separately calls `PlayMultiVoiceTalk` for that same text ID
before another dialogue list. `Act424030717` and `Act424030718` repeat the
pattern for the second description. A global table join had applied the
MultiVoice source to the description without preserving that distinction.
[Calm ordinary presentation](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/Level/Mission/4240307/Act/Act424030715.json)
· [Calm MultiVoice caller](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/Level/Mission/4240307/Act/Act424030716.json)
· [Joyful ordinary presentation](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/Level/Mission/4240307/Act/Act424030717.json)
· [Joyful MultiVoice caller](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/Level/Mission/4240307/Act/Act424030718.json)

The ordinary publisher reader retrieved both complete original WEMs in all
four dubs without a game installation. All eight decoded to nonzero mono
48 kHz PCM. Unprompted English and Mandarin recognition independently
recovers a short first-person utterance in each take, rather than the
third-person description. These are positive observations of different
spoken content, not an inference of silence from failed recognition.

| Dub / original source | Duration | Original WEM SHA-256 |
| --- | ---: | --- |
| English / calm | 2.900 s | `e178ef0b98b0dd456429cfbd7062a73fe7fd0779446fdaa2794540d4cf52518b` |
| English / joyful | 3.000 s | `d5d0a7e5eec7b3b4070284c3cfb9569b622d580113f6cea37acfdb16092b927e` |
| Japanese / calm | 2.795 s | `3e9971be9800b698db9a922f7e76d67060064bd4a82107239296f8ffdece3fa9` |
| Japanese / joyful | 3.172 s | `50788e6d99b6ff4727acdbdb528cb80f05d75352afe0f6d43ad5739d2223b720` |
| Korean / calm | 3.115 s | `e18e3d62076c6049a1189a2170a644dd60b22d078d46dcc7a39d5705cbd851a5` |
| Korean / joyful | 2.966 s | `0a3b68facb82e7c315afdd3f3a5ec60cf2effd5c4530193ec70dd4b484643607` |
| Mandarin / calm | 2.316 s | `ecf5e2a97b78939367deb00c8829a7355aa255ae99c35b9bee0165caa0191b0b` |
| Mandarin / joyful | 2.288 s | `b1b0d06ca4e3f9a71dddb338ab02d4eeecf999df903cc9efcf380c77ee46aec8` |

Schema 23 keeps unnamed MultiVoice entries without a primary sentence voice
`unknown`, including a singleton candidate. Explicit `NoVoice`, named-speaker
singletons and primary voiced narrator bindings retain their existing behavior.
The rule reads the selected release's fields on every normal preparation;
new IDs and changes to those bindings require no hardcoded character list.
Existing cached originals remain stored.

The current authoring has 99 entries matching the uncertainty guard. Two
Benny rows change from `voiced` to `unknown`; the other 97 were already
`unavailable`. Their general presentation kind is preserved. Missing names
alone do not establish narration, silence or a reaction role for all 99.
The four Mullich descriptions `413021201`, `413021501`, `413021801` and
`413022001` also retain unresolved audio, even though their pairs of numeric
voice IDs alias identical source paths. A shared NPC recording is not evidence
that it speaks the description.

Normal English preparation now retains 306,752 records with 98,693 voiced
rows; Japanese retains 306,743 with 100,170. Both contain the same 99 guarded
unknown entries. The twelve English and nine Japanese reviewed movie clips
remain available. Reopening each corrected index with network access prohibited
rejects both descriptions as playable entries. All 21 movie clips still export
into two fresh conversion directories with identical nonzero decoded PCM across
the reopen. This is source-development verification with prepared decoder tools,
not a packaged native acceptance claim. Earlier schema-22 counts below describe
the snapshot before this correction. These are two corrected false bindings,
not 99 newly completed lines or confirmed unvoiced entries.

## Protagonist movie clips · November 16, 2026

The normal movie reader now resolves the selected Trailblazer's authored
movie file independently. Each branch must have its own verified original
recording and reviewed spoken window. A missing counterpart stays unavailable;
two plausible movies for the same player remain ambiguous. Source text and
translations use that branch's existing gender-template renderer. Schema 22
refreshes older prepared indexes without changing their saved recordings.

Both Global 4.7 Boarding movies were fetched from the released publisher
VideoV routes and checked against the complete declared size and MD5:
`CS_Chap00_Act310_m.usm` has 34,690,432 bytes and MD5
`dde5d9622f780ff537e673a90909d89b`; the female movie retains the previously
verified 34,696,032 bytes and MD5 `dae38a58976a0e370a1eebff21a73da9`.
The directory names each of the four dubs explicitly. All eight original ADX
streams decode to 28.715 seconds; this does not verify every caption in every
dub. [Original male movie](https://autopatchos.starrails.com/asb/V4.7Live/output_17006872_6d1b44a7ab74_04464e14b93253/client/Windows/Video/CS_Chap00_Act310_m.usm)
· [Original female movie](https://autopatchos.starrails.com/asb/V4.7Live/output_17006872_6d1b44a7ab74_04464e14b93253/client/Windows/Video/CS_Chap00_Act310_f.usm)

| Boarding caption hash | Dub | Recording-relative export window | Applicable movies |
| --- | --- | --- | --- |
| `12917693302615549427` | English | 8.500–10.400 s | Male and female, separately verified |
| `6728848531281631178` | English | 21.750–23.150 s | Male and female, separately verified |
| `11614536872574131062` | Japanese | 4.300–6.200 s | Male and female, separately verified |
| `12917693302615549427` | Japanese | 8.600–10.850 s | Male and female, separately verified |

The four original recording SHA-256 identities are:

| Dub / movie | Original ADX SHA-256 |
| --- | --- |
| English / male | `7a457f3fa183b50f94c88ed2c17545826812ba8beedd89ce806c1199aaf14dd8` |
| English / female | `001c4dd819a2055b36d8276e19c72aa8419429fb2e594f0fa9b4c6c45725be28` |
| Japanese / male | `520161aa3a50e13d4042ef1e0c71ad2d27cc0cc408ad170b7bc2a39095e17b16` |
| Japanese / female | `982fae1cb161c3fa4afd86a51e976d68ce72b0a95670668a1a924d64ae1fd9e7` |

Unprompted speech recognition on the original English mix recovers the two
exported lines. A second model independently recovers their wording. The song
obscures Japanese dialogue in unseparated recognition. A private comparison
subtracting the median of the four original dub mixes recovers the first two
Japanese phrases from the publisher text. This is timing research only:
exports retain the original mix, and all text comes from the released caption
and localization tables. Corresponding male/female original excerpts correlate
at 0.997/0.958 for the English exports and 0.996/0.983 for Japanese at
16 kHz, filtered at 400–3,400 Hz. Neither branch borrows the other's ADX.

A fresh search independently located Aruki's June 6, 2023 Japanese-dub
recording. Four separated original excerpts at 4.3, 8.6, 19.1 and 21.1 seconds
match the upload at consistent offsets of 0.9959–0.9964 seconds, with
correlations 0.463, 0.768, 0.541 and 0.246 at 8 kHz, filtered at
320–3,500 Hz. These identify the scene and original mix; publisher stream
labels establish the dub. The Japanese second export retains the complete
phrase beyond its 10.083-second subtitle disappearance. Other Boarding
captions and Korean/Mandarin cuts remain unresolved. Short or ambiguous
caption capture still needs separately verified context.
[Independently found Boarding gameplay](https://www.youtube.com/watch?v=e3_kpHh_nqE&t=5s)

Silent Galaxy additionally exports Japanese hashes `10860693209200705991`
and `14960296995890117809` at 41.650–48.800 and 48.800–52.650 seconds.
Independent small/medium recognition recovers the final two original Japanese
lines; their shared boundary retains the second line's introductory reaction
after the preceding sentence. The original recording hash remains
`1101f64927bfc5cc5874b16564fc01c1a80153398ab8c6f56bcaba0ad13d58d9`,
already matched by six independent gameplay excerpts below. This brings movie
clips to eight English and five Japanese Silent Galaxy entries, plus the
eight Boarding protagonist bindings above. Unreviewed captions remain unavailable.

Normal installation-free English preparation produced 306,752 records and
98,695 voiced rows; Japanese produced 306,743 and 100,172. Their movie subsets
contain twelve and nine original clips respectively. Totals include unavailable
movie variants and other UI/presentations; they are not a full story or capture
acceptance claim. All 21 clips exported through the normal Windows
source-development voice service with networking prohibited throughout service
startup and export. Closing/reopening the service into fresh output folders
reconverted all 21 to identical nonzero PCM, with the declared clip durations.
These warm-cache checks do not establish cold acquisition costs. Broader
changed-game-data and native-host acceptance remain open.

Preparation builds both player choices, so the two complete Boarding source
movies together require 69,386,464 bytes before metadata and other dialogue
resources. It does not fetch only the currently selected player movie. Saved
original ADX tracks are reused for subsequent exports.

## Released 4.6 chapter packages rechecked · November 15, 2026

The two Japanese chapter packages and the second Korean chapter package are
available from both publisher regions. A fresh check fetched the released
AudioV markers and index bodies, then read all six complete package bodies
through the normal ranged publisher reader. Every full file matched its
released size and MD5. The regional indexes both identify audio revision
16781679, with a 112,742-byte AudioV body and MD5
`f4e0fbb3ae338c02662c48a07a95226c`.

| Released package | Bytes | MD5 | External entries | Decoded sample | Publisher sources |
| --- | ---: | --- | ---: | ---: | --- |
| Japanese/External_del_4.6_chapter5_0.pck | 103,835,810 | `21aeb1c1691f162f1b505b55f60c411e` | 770 | 6.186 s | [Global](https://autopatchos.starrails.com/asb/V4.6Live/output_16566615_0c4dcd9ce0fa_fe1337388fb7ac/client/Windows/AudioBlock/Japanese/External_del_4.6_chapter5_0.pck) / [Mainland](https://autopatchcn.bhsr.com/asb/V4.6Live/output_16566615_0c4dcd9ce0fa_5e2c76c57a3c3d/client/Windows/AudioBlock/Japanese/External_del_4.6_chapter5_0.pck) |
| Japanese/External_del_4.6_chapter5_1.pck | 100,040,916 | `7f35079e4f1593abf0de71a70da22423` | 749 | 4.041 s | [Global](https://autopatchos.starrails.com/asb/V4.6Live/output_16566615_0c4dcd9ce0fa_fe1337388fb7ac/client/Windows/AudioBlock/Japanese/External_del_4.6_chapter5_1.pck) / [Mainland](https://autopatchcn.bhsr.com/asb/V4.6Live/output_16566615_0c4dcd9ce0fa_5e2c76c57a3c3d/client/Windows/AudioBlock/Japanese/External_del_4.6_chapter5_1.pck) |
| Korean/External_del_4.6_chapter5_1.pck | 82,896,166 | `8fbb5c41e40e54dca1e7bb0b75358e87` | 749 | 3.601 s | [Global](https://autopatchos.starrails.com/asb/V4.6Live/output_16566615_0c4dcd9ce0fa_fe1337388fb7ac/client/Windows/AudioBlock/Korean/External_del_4.6_chapter5_1.pck) / [Mainland](https://autopatchcn.bhsr.com/asb/V4.6Live/output_16566615_0c4dcd9ce0fa_5e2c76c57a3c3d/client/Windows/AudioBlock/Korean/External_del_4.6_chapter5_1.pck) |

One original WEM from each of the six independently fetched packages decoded
to nonzero 48 kHz mono PCM. Matching regional packages produced identical
sample hashes. This verifies acquisition and a representative decode from
each package. It does not establish every sentence's text or movie binding.
These are released 4.6 files; the different public preload identities are
excluded. Acquisition uses the selected region's released AudioV routes and
requires no game installation. The remaining film, presentation and update
acceptance work is tracked separately.

## Original movie audio recovered · November 15, 2026

The earlier distorted ADX attempt omitted the USM packet-level audio mask.
A separate format check now recovers complete original soundtracks from two
Global 4.7 publisher movies without a game installation. The complete bodies
passed the VideoV byte-size and MD5 checks. The CRI directory explicitly names
CN, EN, JP and KR audio streams; no language was inferred from track order.
Each stream's `@SFA` payloads were processed separately before concatenating
the ADX data. All eight results decoded with FFmpeg to nonzero stereo PCM at
48 kHz, with no clipped samples in these checks.
[Packet-format reference](https://github.com/Furina1027/hoyo-files/blob/a0774e9ddf72ead835846bf03f4a08c0cae406f0/src/utils/usm_demux.ts)

| Publisher movie | Original bytes | VideoV MD5 | Decoded duration per dub |
| --- | ---: | --- | ---: |
| `CS_Chap00_Act310_f.usm`, boarding | 34,696,032 | `dae38a58976a0e370a1eebff21a73da9` | 28.715 s |
| `CS_Chap01_Act3020.usm`, Silent Galaxy | 65,392,224 | `f0db051bd87897609601fde6672b8b2f` | 53.433 s |

[Original boarding file](https://autopatchos.starrails.com/asb/V4.7Live/output_17006872_6d1b44a7ab74_04464e14b93253/client/Windows/Video/CS_Chap00_Act310_f.usm)
· [Original Silent Galaxy file](https://autopatchos.starrails.com/asb/V4.7Live/output_17006872_6d1b44a7ab74_04464e14b93253/client/Windows/Video/CS_Chap01_Act3020.usm)

Independent waveform comparisons identify four of these soundtracks in
public gameplay. Offsets relate the original audio's zero to the upload's
zero. The source excerpts were filtered at 320–3,500 Hz and compared at
8 kHz using normalized waveform correlation.

| Performance | Original excerpt starts | Consistent upload offset | Correlations |
| --- | --- | ---: | --- |
| Boarding, Japanese | 4, 8, 19, 21, 25 s; 2 s each | 553.359–553.362 s | 0.384, 0.504, 0.529, 0.554, 0.744 |
| Silent Galaxy, English | 1, 8, 17, 27, 37, 46 s; 3 s each | 6.434 s | 0.994, 0.989, 0.986, 0.978, 0.986, 0.990 |
| Silent Galaxy, Korean | 1, 8, 17, 27, 37, 46 s; 3 s each | 593.303 s | 0.908, 0.952, 0.921, 0.910, 0.945, 0.906 |
| Silent Galaxy, Japanese | 1, 8, 17, 27, 37, 46 s; 3 s each | 770.149 s | 0.986, 0.985, 0.984, 0.987, 0.988, 0.987 |

[Japanese boarding gameplay](https://www.youtube.com/watch?v=L6wGHwWxnk8&t=557s)
· [English Silent Galaxy gameplay](https://www.youtube.com/watch?v=kbMz5JbShYA&t=7s)
· [Korean Silent Galaxy gameplay](https://www.youtube.com/watch?v=y_HNFpFop6s&t=594s)
· [Japanese Silent Galaxy gameplay](https://www.youtube.com/watch?v=yoNYBnZ8w8w&t=771s)

The normal publisher preparation now uses an owned Python reader for this
masked-ADX format. It checks the complete movie MD5 and size, authored dub
label, packet bounds, declared ADX sample count and absence of premature EOF.
Format parameters are downloaded as data from an immutable
[hoyo-files revision](https://github.com/Furina1027/hoyo-files/tree/a0774e9ddf72ead835846bf03f4a08c0cae406f0/pkg_version/usm).
They must name the exact movie MD5, size and applicable generation. Downloaded
code is never executed. Saved bindings retain the source generation, format
revision, complete metadata digest and original recording SHA-256.

Eight English and three Japanese Silent Galaxy captions have reviewed spoken
windows tied to the original recording hash. These windows differ from the
subtitle display clock: for example, one English line continues beyond the
caption's disappearance. The other English/Japanese captions remain unavailable;
the existing exact Korean/Mandarin sentence recordings remain preferred.
Japanese window alignment was checked against the decoded original speech;
six independent excerpts now identify the original Japanese mix in public
gameplay, including the later exchange containing the two other exported cuts.
Boarding audio is readable but its individual caption windows remain unresolved.

A fresh run of the actual English language worker prepared 306,267 records,
including eight new movie bindings. All eight exported through the ordinary
voice service to nonempty MP3s of the expected durations with network access
disabled. Japanese preparation produced 306,258 records and three movie
bindings; all three also exported through the same service offline. A worker
regression test covers a discovered contract failure:
film route/display provenance now lives in the snapshot's `film_captions`
inventory instead of being passed as an unsupported dialogue-model field.

The periodic publisher check also follows the external format-data revision,
so a metadata update can trigger preparation without a toolkit update. A
temporary format-service outage retains its last verified revision and reports
the limitation. Previously cached original recordings remain usable offline.
A changed recording cannot inherit old spoken windows. New scenes and changed
performances still require verified boundaries; this is not complete automatic
future-film coverage. First preparation of this reviewed Silent Galaxy source
fetches its approximately 65 MB movie plus format metadata; subsequent exports
reuse the verified original ADX. Newer movie formats and other protagonist
movies remain unverified. No game media or format-key values are distributed
in the repository.

## Released regional hotfixes, November 13, 2026

The Windows publisher reader now resolves the current release and in-version
ASB, DesignData, Lua, Audio and Video indexes for the selected region. The
community-maintained release directory provides versioned path names. The
reader obtains each marker and all five index bodies from the official
regional CDN and checks size, revision and MD5. The dialogue catalog must
match the resulting exact Windows design, asset and Lua revisions. A mainland
release can reuse the Global text extraction when all five regional index
checksums and sizes agree. Each edition has its own snapshot identity, also
covering updates within the same launcher version. Previously prepared audio
uses its stored generation. Changed index bodies require verification.
For film captions the catalog can recover from two busy directory APIs via the
author's ordinary repository listing at the same commit. The fallback checks
the repository, exact revision, directory, names and complete item count.
A fresh cache obtained all 173 scripts for this release through that path.
When a mainland audio package times out or has been removed from its CDN,
the reader can retry the verified Global equivalent. It stores the Global
directory only after all five regional index identities agree and requires
the same package digest and exact byte range on the alternate host.
[Release directory](https://github.com/PutraZC/HSR-Data/blob/main/hotfix.json) ·
[Global launcher](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=4ziysqXOQ8) ·
[Mainland launcher](https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?launcher_id=jGHBHlcOq1&game_ids%5B%5D=64kMb5iAWu)

On November 13 both 4.7.0 launchers carried base revision 17006872. The
in-game CDN markers independently selected Design 17180467, ASB, Audio and
Video 17176203, and Lua 17175930. All five index bodies matched across editions.
The subtitle extraction identified those exact revisions. AudioV lists 177
packages per dub. The regular launcher set contributes 175, and the selected
region's publisher directly supplies two more chapter packages per dub.
Playback reuses a Sophon file only when its released size and content digest
match. For direct packages, bounded reads verify the source ETag, range and
total size. A private cache checks its saved bytes for offline reuse.
The 4.6 release directories also still serve both Japanese chapter packages
and the second Korean chapter package. The complete files were downloaded in
both editions and matched the active 4.6 AudioV checksums in all six checks.
The two Japanese files were 103,835,810 and 100,040,916 bytes. The Korean
file was 82,896,166 bytes. The earlier observations below describe the
previous launcher-only acquisition route.
[Verified 4.7 release directories](https://github.com/PutraZC/HSR-Data/blob/6a31cad76bd8aa2b250a71905ee573de37edc642/hotfix.json) ·
[Matching 4.7 dialogue catalog](https://github.com/DimbreathBot/TurnBasedGameData/tree/dad9155eb00fdeda31fb8456507c53590d49071f) ·
[Verified 4.6 release directories](https://github.com/PutraZC/HSR-Data/blob/8fe88ba411d4/hotfix.json)

A real text-only change to published dialogue occurred within Global 4.4.0.
Between the July 14 and July 16 release directories, the design revision
changed from 15749062 to 15785787. Both official AudioV bodies have the same
108,092 bytes and MD5 `d45b24c7160d556166367cc708292b67`. Preparing the
published English tables at each matching catalog revision yielded 234,180
talk rows. Both protagonist variants of sentence 154170809 changed a pronoun
in the same existing line. Its male version now renders “he” and its female
version “she”. The reader applies the selected player's text template to
each translation before capture or export.
[July 14 release directory](https://github.com/PutraZC/HSR-Data/blob/2f0b87ea827be620d631e38b4ac0c48ffbdc0ab1/hotfix.json) ·
[July 16 release directory](https://github.com/PutraZC/HSR-Data/blob/c28ef63744d832f1b29d7b40900946f06debd4c9/hotfix.json) ·
[Earlier English text](https://github.com/DimbreathBot/TurnBasedGameData/blob/557a5d39bf66315cdabccca84828be8cdf181824/TextMap/TextMapEN.json) ·
[Updated English text](https://github.com/DimbreathBot/TurnBasedGameData/blob/fd978d6ef09f941fba644c731ab54abd6f7c3568/TextMap/TextMapEN.json)

## Per-line companion cutscene audio

The 4.7.0 TalkSentence and VoiceConfig tables identify separate
`companion<chapter>_<character>_<line>` external recordings for 689
cutscene-classified sentence rows. Nine source names are shared by distinct
text hashes, affecting 18 captions. The reader keeps those ambiguous. For the
other 671 captions the selected actor takes give 730 independently resolved
recordings per dub in the Global publisher indexes, 2,920 bindings across
the four spoken languages. Twelve original WEMs were retrieved and decoded
from those named sources, including the two protagonist takes in each dub.
The English opening sample lasted 7.722 seconds, Japanese 5.990, Korean
4.351 and Mandarin 6.115. The named whole-film events in VoiceConfig and
subtitle clocks for pre-rendered movies require their own audio sources.
[Released sentence table](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/TalkSentenceConfig.json) ·
[Released individual source paths](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/VoiceConfig.json)

## In-engine cinematic caption clocks

The 4.7 community directory has 173 caption scripts with 946 entries. Each entry
identifies the localized subtitle, its display start and its display end.
Eighteen in-engine timelines also associate the caption script with a
CutSceneConfig voice ID. The corresponding VoiceConfig entry selects a
locale-specific external recording, including separate protagonist takes.
The reader checks the start and end against the Wwise sample count before
offering a timed clip.

The release-paired VideoConfig links 153 published caption scripts to
242 physical movies (89 with two player variants, 64 with one file).
Preparation kept 801 subtitle intervals, each with its video ID, applicable
actor variants, filename, byte size and digest from VideoV. Global and
mainland 4.7 each yielded the same 801 intervals. A video-only update
changes the snapshot identity independently of the dialogue and audio
indexes. An inspection of the movies' CRI stream directories
found 229 files with four language labels, one with Mandarin alone, and
12 without language labels. Three sampled English tracks produced heavily
distorted audio from a plain ADX demux and decoder, so they have no playback
binding in the toolkit. The caption does not establish silence.

The game's boarding film (video 310) displays four captions at
4.516–5.950, 8.983–10.083, 19.600–20.366 and 21.450–23.300 seconds.
A recording of Japanese gameplay shows the four English captions at
9:18, 9:23, 9:33 and 9:35. The last two Japanese calls are audible.
For *Silent Galaxy*, the departing mission triggers performance 101150200,
which plays video 101, with eleven captions. Its first cue runs
0.333–6.633 seconds. Eleven consecutive TalkSentence records describe
that same exchange. Korean and Mandarin each contain all eleven original
recordings. Each complete decoded waveform independently matched the
corresponding film in recorded gameplay, including the short reaction.
The Korean matches fall between 9:53.380 and 10:42.480 (normalized
correlation 0.446–0.965), the Mandarin matches between 7:41.761 and
8:30.594 (0.503–0.928). Their closest competing peaks were lower for
every take. Both language choices for Mandarin use the same recordings.
The English and Japanese packages contain none of these eleven named
external recordings. Published gameplay also shows Bronya and Cocolia
in video 1160, whose seven caption intervals start at 5.400 seconds.
Publisher byte ranges for these three films, including both boarding
variants, returned valid CRI container headers on both editions.
[Boarding gameplay](https://www.youtube.com/watch?v=L6wGHwWxnk8&t=557s) ·
[Silent Galaxy gameplay](https://www.dailymotion.com/video/x8pn5xc?start=2518) ·
[Korean gameplay](https://www.youtube.com/watch?v=y_HNFpFop6s&t=593s) ·
[Mandarin gameplay](https://www.youtube.com/watch?v=Y2S0YsUFJ8k&t=461s) ·
[Cocolia gameplay](https://www.dailymotion.com/video/x8pn5xd?start=2703) ·
[Mission video action](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/Level/Mission/1011502/Act/Act101150200.json) ·
[Released video configuration](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/VideoConfig.json)

Another 144 video records declare 138 distinct caption paths absent from
the same revision's published caption directory. Six individually checked
paths across chapters 3, 4 and 5 returned HTTP 404. CS_Chap02_Act610 still
lacks a matching movie or timeline WEM. Its ten text IDs were absent from the English, Japanese, Korean,
both Chinese, French and German text tables.

The regional publisher's DesignV directory for 4.7 supplies 141 additional
distinct caption records with 996 timed entries. All 996 localization IDs
resolved in English, Japanese and both Chinese scripts, and 993 resolved
in Korean. The toolkit reads the selected release's member offsets and
compares the entire cue sequence of named captions before reading adjacent
caption records. It fetches only the relevant pages of the design package.
Original resource IDs provide stable identifiers for entries whose movie
name remains unverified. Repeated copies of the same text and clocks are
deduplicated. Both regional releases returned the same 141 records. The
4.6 and 4.7 indexes from both regions retained the three reference resource
IDs while changing their package digest. Mapping these new resources to
individual VideoConfig paths and movie audio is ongoing.
[Global 4.7 DesignV marker](https://autopatchos.starrails.com/design_data/V4.7Live/output_17180467_2b67443267a6_475611c71617ea/client/Windows/M_DesignV.bytes) ·
[Mainland 4.7 DesignV marker](https://autopatchcn.bhsr.com/design_data/V4.7Live/output_17180467_2b67443267a6_dc848fdaa66f47/client/Windows/M_DesignV.bytes)

Both player variants of *Ripples of Past Reverie* identify mission 1043710.
Its performance 104371098 plays video 4781 with two different lyric tracks.
The Mandarin dub selects the default Act781_1 script. Its published design
resource contains the Chinese song's distinct ending, which also appears in
the publisher's lyrics. The other three dubs select Act781_2 via the mission's
explicit caption override. Each script has 59 cues. Their last two entries
start at 227.916 and 229.500 seconds for Mandarin and 228.083 and 229.666
seconds for the other dubs. The reader resolves the current mission's
language condition, regional movie files and caption clocks on each update.
Across both editions, this brings the total per selected dub to 154 movie
scripts with 860 intervals and 244 files. Playback from these two movie files
remains open.
[Released mission action](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/Level/Mission/1043710/Act/Act104371098.json) ·
[Publisher's Mandarin lyrics](https://sr.mihoyo.com/news/160771?type=news) ·
[English vocal recording](https://www.youtube.com/watch?v=LdFYCWEp8no)

After a normal update the reader resolves the reviewed caption IDs and
current sentence recordings again. It checks the publisher movie's MD5 and
the individual original recording's SHA-256 before offering the complete
take. Moving an unchanged recording into a new package preserves playback.
Changing the specific movie or re-recording the line requires a fresh
comparison. A text update retaining its caption ID uses the current translation.

Video 102, *Only A Child*, cuts Serval's farewell into five short captions.
Each fragment independently matched its original individual WEM in all four
dubs, including the one-word middle cues. The first matching recording
starts at 1:34.200 in English, 33:56.466 in Japanese, 47:52.716 in Korean
and 37:08.477 in Mandarin. The toolkit retrieves the five complete takes
in each dub from the selected region's release.
[English gameplay](https://www.youtube.com/watch?v=D2ghbhM2CPY&t=94s) ·
[Japanese gameplay](https://www.youtube.com/watch?v=Z6acDJFztXg&t=2036s) ·
[Korean gameplay](https://www.youtube.com/watch?v=jbkWEfXZjFM&t=2872s) ·
[Mandarin gameplay](https://www.youtube.com/watch?v=-jUrr3nAm-0&t=2228s)

In *The Devil in Velvet* (video 3190), Acheron's final two captioned lines
use the same recorded performances as the two sentences in a later
recollection. Eight complete individual WEMs matched four independent
recordings of the original encounter. The first match starts at 5.213
seconds in English, 4.770 in Japanese, 9.963 in Korean and 11:44.799
in Mandarin. SAM's preceding two lines remain unavailable in this film.
[English gameplay](https://www.youtube.com/watch?v=1khoGeARkzw&t=5s) ·
[Japanese gameplay](https://www.youtube.com/watch?v=K0REbaGg1iw&t=4s) ·
[Korean gameplay](https://www.youtube.com/watch?v=EbD7xTtl-8M&t=9s) ·
[Mandarin gameplay](https://www.youtube.com/watch?v=bbKnx4IneG4&t=704s)

Video 3550, Rappa's recollection in *The Men Who Tread on the Monkey's
Tail*, has 21 captions. Fifteen physically present English TalkSentence
recordings from the adjoining sequence (103448009–103448023) were compared
with the complete in-game scene. The first subtitle is audible at 8:34
in the replay. The next caption has similar wording to 103448009, yet its
strongest normalized correlation within the scene is only 0.151 and
occurs at 10:14, well outside the subtitle. Other differences include a
longer response from the Galaxy Ranger in the film. None of the fifteen
recordings produced a match at its corresponding caption. The movie
therefore retains its own text and timestamps without a per-line audio link.
[Rappa gameplay](https://www.youtube.com/watch?v=sr6T9MldK9I&t=514s) ·
[Released subtitle sequence](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/Config/CutSceneCaption/CS_Chap03_Act3070_Caption.json)

On Global 4.7, all 28 directly bound in-engine WEM tracks per dub were
retrieved and decoded. Their durations covered the 124 authored caption
intervals, including player takes. Speech recognition on the original
opening station and Express tracks reproduced the corresponding dialogue.
The clips follow the game's subtitle display times, which can differ from
the start or end of individual words.
[Released cinematic configurations](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/CutSceneConfig.json) ·
[Released caption scripts](https://github.com/DimbreathBot/TurnBasedGameData/tree/dad9155eb00fdeda31fb8456507c53590d49071f/Config/CutSceneCaption) ·
[Released voice paths](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/VoiceConfig.json)

## Character archive and battle voices

Global 4.7.0 contains 3,686 localized VoiceAtlas rows referencing 3,678
distinct events. The launcher's SoundBankLookUp maps each event to its
neutral bank and localized sound bank. The publisher reader verifies the
lookup against the actual Wwise 135 event, its Play action and the target
sound in the selected dub. Embedded sounds, streamed sounds and streams with
a bank prefetch use their authored media IDs. Duplicate or missing sources
remain unavailable. A random/sequence container can contribute a recording
when both its child table and its playlist name the same sole sound.

The 3,502 single-source events add 3,510 archive rows. The 172 switch
events reference 344 additional media banks across their states. The reader
joins each switch's group, state, selected child, parent and media bank to the
regional launcher's state dependency table. All 29 protagonist switches have
explicit male and female states. For example, the source text for Aventurine
contains both forms of address. The English export independently played
“Mr. Stellaron” and “Miss Stellaron” according to the selected protagonist.

The other 143 switches control collaboration character voices. HoYoverse
documents the per-character option for original Japanese voice. The reader
chooses Japanese for Japanese study and the locale's default state for other
dubs. It requires a credit for the selected language in the current
`AvatarAtlas` before exporting a collaboration performance. The four characters
have Mandarin, Japanese and Korean credits in 4.7. All 142 English default
recordings with a single source decoded to digital silence. The 143rd event
has two English sources, which both also decoded to silence. In Japanese,
Korean and Mandarin, 142 switches produced one recording each.
[Character voice options](https://hsr.hoyoverse.com/en-us/news/158598) ·
[Released character credits](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/AvatarAtlas.json)

The complete Global Japanese preparation produced 305,316 text rows and
100,146 playable rows across presentations. Normal export decoded male and
female Aventurine and Saber's idle recording to MP3. Regional English
checks also decoded both protagonist recordings and three direct events
from the mainland CDN.

All five multi-part events have continuous, forward, resetting Wwise
sequence playlists and two separate speaker captions. Three are Huohuo
and Tail, one is Starblazer and Himeko, and one is Rin and Ishtar inside
the collaboration switch. The reader checks playlist order, the parent of
each sound, the exact source in the selected dub and the number of speaker
lines before splitting the text. In Huohuo's precious-chest interaction the
playlist puts the second child first. Export followed that order, playing
Huohuo's remark and then Tail's response. The review fetched all 40
individual media sources for these five events across four dub packages,
including the two silent English Rin/Ishtar sources.

With these sequences, the current Global bank structures account for all
3,678 distinct VoiceAtlas event names. The 3,686 base archive rows produce
3,720 playable performance rows in each of Japanese, Korean and Mandarin
(either Chinese script). English produces 3,576 playable performance rows
and 143 collaboration entries without an English dub. The complete English
worker built 305,330 rows across presentations, including 98,676 playable
rows. The separate film, mission-branch and capture gaps in this audit
still apply.

Independent mainland-region playback of the saved publisher generation also
decoded both of Huohuo's speaker parts, both of Rin's, both Aventurine
variants, Saber and a direct Jing Yuan voice in Japanese, Korean and Mandarin
(both Chinese text choices). Regional English playback used the separately
verified English sources.
The full mainland archive inventory produced the same counts in every study
choice as the Global inventory. Twenty-nine representative original mainland
snapshot bindings were decoded across the five choices during that run.

The reader groups selected bank ranges by package and validates the published
package digest, size, returned range, Wwise language and embedded/streamed
identity. The complete game is not required. A changed launcher lookup that
lags behind the hotfix's banks can leave individual names unresolved. The
loader requires the lookup's bank pair to agree with the actual Play action.
[Released VoiceAtlas](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/VoiceAtlas.json) ·
[Official launcher](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=4ziysqXOQ8)

## Event panels, choices and books

The 4.7.0 Windows reader resolves 922 localized dialogue entries from the
Hipplen, Clockie, Idle Live and Chimera event tables and 2,224 authored
Simulated Universe choice titles. Each entry resolved in all five study
choices. Of 264 distinct Chimera event names, 249 use language-neutral
sound banks, 12 reference localized banks and three are absent from this
release's bank lookup. Six localized events have a single authored sound.
All six English recordings are short character reactions, including laughter
and exclamations displayed alongside longer translated sentences. All six
were also retrieved and decoded from the other three dub packages. The
reader retains the display text without exporting these reactions as spoken
sentences. Other Chimera presentations need playback verification.

The 1,144 LocalbookConfig entries produce 22,162 English, 22,151 Japanese,
22,149 Korean and 22,152 paragraphs in each Chinese script. The 12 books
listed in AudioBookData contribute 48 English paragraphs with an authored
sound event. Only translations with the same paragraph boundaries accompany
a study paragraph. English aligned with 21,356 Japanese, 21,468 Korean and
21,695 Chinese paragraphs in each script. All 12 collectible events resolve
to individual embedded sources in language-neutral SFX banks. All 12 played
as regular decoded audio and none produced a speech segment in the sampled
release's voice-activity/transcription check. The event points to the whole
collectible. It supplies no per-paragraph narration binding. Capture replay
for these panels remains open.
[Book contents](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/LocalbookConfig.json) ·
[Audio collectibles](https://github.com/DimbreathBot/TurnBasedGameData/blob/dad9155eb00fdeda31fb8456507c53590d49071f/ExcelOutput/AudioBookData.json)

## Global publisher playback, November 9, 2026

Before selecting a translation snapshot, Setup follows all four SRMI revision
markers to their respective DesignV, AsbV, LuaV and AudioV indexes. Each
marker carries the size and MD5 of its index. Setup checks its complete path,
size and MD5 against the same publisher build. This works on the 4.4.0 and
4.5.0 mainland releases and both independently discovered 4.6.0 releases.
The 4.6.0 regions share revision numbers, while the DesignV and LuaV index
contents differ. The Global launcher AudioV contains 131 base bank and sound
effect entries. The two optional Japanese chapter packages and the second
Korean chapter package still require a source matching the in-game manifest.

The desktop worker prepared all five study choices with an empty toolkit cache
and no game path. The Global 4.6 regular packages produced 90,630 English, 91,966 Japanese, 92,052
Korean and 92,057 Mandarin voiced records in each Chinese script. The service
exported Leonard's sentence 200070401 in all four dubs. Each publisher WEM
was byte-identical to its installed counterpart. The offline reader reproduced
the MP3 from its private cache in a fresh output directory for all five choices.
All prepared voiced records resolved to the same package name and file ID in
the independently indexed installed dub.

HoYoPlay's four regular voice manifests each contain 173 PCKs. All 692
whole-package checksums match the updated AudioV manifest for audio 16781679.
The latter also lists two optional chapter-5 PCKs per dub. The booted client
identified design 16854589, ASB/audio 16781679 and Lua 16781679, matching
the pinned text revision. Its ordinary player log supplied no public hotfix
manifest URL. Setup recognizes the exact audited launcher generation and
checks the actual revision markers for subsequent releases. A later release
needs matching published text. Independent hotfix discovery and ambiguous
performances remain open.
[Global launcher](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=4ziysqXOQ8)
· [Matched Global text revision](https://github.com/DimbreathBot/TurnBasedGameData/tree/74a7b96fba32f00cf495a5c00b0311bd02207aaf)

Five chapter-5 packages in the public Global 4.7 preload are byte-compatible
with the active 4.6 AudioV. Preparation requires the complete original file path,
size and MD5 in the matching manifest. It accepts both Mandarin and English
packages and the first Korean package. Both Japanese files and the second Korean
file have different checksums in both the Global and mainland China preloads.
Those three remain unavailable from this source. The earlier 4.3–4.6 mainland
launcher manifests contained none of the eight current optional checksums.

The normal preparation worker now resolves 93,578 Mandarin records in each
Chinese script, 92,151 English, 92,819 Korean and 91,966 Japanese. Both the
Mandarin and English chapters contribute 1,521 additional records. Korean gains
767. The two Mandarin packages contain 1,519 WEMs, of which 1,514 have an
exact supported text binding, including two broadcasts. Sample original WEMs
from both Mandarin packages matched the installed bytes. The selected records
from every compatible package also exported as MP3s and replayed offline.
[English publisher manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD/manifest_4ea0efd4ec903433_17e27e86e8c125fe5fdf0654cfe9d913)
· [Mandarin publisher manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD/manifest_d661cb6b87d9177d_538657f961efa5766813f93b24963fb4)
· [Korean publisher manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20261030/4.7.0/83LId4LQZKoD/manifest_c0431fe18031980c_841f5ca2186abebbcf3bd8854a9af42b)

Initial audit on October 27, 2026 with installed client 4.6.0 and adapter
schema 2. The November 8 multi-voice check below used adapter schema 3.
This is an inventory of dialogue presentations and their current parser support,
not a claim that every screen has passed OCR replay.

## Evidence and provenance

The installed client was inspected read-only. It contained 825 Wwise PCKs,
all with `AKPK` headers; the four installed voice languages were Chinese,
English, Japanese and Korean. Audio uses
`Audio/AudioPackage/Windows` beneath the base and persistent asset layers.
The installation also contained 1,184 USM files, binary `DesignData/Windows`
tables and encrypted `.block` assets. These are distinct from ZZZ's resource
catalog format. No Star Rail evidence warrants applying ZZZ's catalog decoder.

Text and authoring relationships were inspected at
[catalog revision 74a7b96fba32f00cf495a5c00b0311bd02207aaf](https://gitlab.com/Dimbreath/turnbasedgamedata/-/tree/74a7b96fba32f00cf495a5c00b0311bd02207aaf).
Its commit identifies production Windows 4.6.0 and is dated 2026-10-19.
This is a third-party mirror of game-authored data, not a HoYoverse-hosted API.
Installed PCK identities independently verify the audio bindings; matching
version labels alone does not prove every mirrored string is present locally.
The audit enumerated 2,253 Excel table names and inspected 32 relevant table
schemas. It did not decode every local binary table or inspect every story script.

Primary product references establish the presentation categories:

- [Official 3.4 update](https://hsr.hoyoverse.com/en-us/news/157441): distinguishes Trailblaze, Continuance, Companion and Adventure conversations from cutscenes and exploration, and introduces dialogue summaries and language switching.
- [Official 4.6 update](https://hsr.hoyoverse.com/en-us/news/166468): identifies messages, readables, data-bank entries, loading text, narrated stories, ambient voices and the Interastral Peace Broadcast as separate content.
- [Official 2.2 update](https://www.hoyolab.com/article/28286762): separately lists story dialogue, messages, readables, character stories and Simulated Universe text.

Private probes and downloaded metadata live only in ignored
`output/checks/audit-starrail/`. No game dialogue, media, local install paths,
credentials or account information belongs in the public audit.

## Presentation inventory

“Indexed” below means that the adapter now emits an authored record when the
selected localization contains its text. It does not establish successful OCR
for that presentation, nor that every branch is reachable in a particular save.

| Presentation | Authored evidence and current handling | Remaining gap |
| --- | --- | --- |
| Trailblaze, Continuance, Companion and Adventure dialogue | `TalkSentenceConfig` joins exact `VoiceID` to `VoiceConfig`; ordinary lines and player variants remain indexed. Rows without a voice reference now retain their text with unknown voice status. | Mission/script traversal has not classified every sentence by quest type or checked all branches. |
| Dialogue choices and player responses | Sentences without voices are no longer discarded. | Choice presentation is not encoded in the sentence table alone; choice/script joins and choice-region OCR remain unverified. No claim that every choice string lives in this table. |
| Optional NPC conversations, object interaction, inspections and legacy daily content | `DialogueNPC` has 1,725 script references; `DialogueProp` has 378. Their sentence-table content can now survive without audio. | References were inventoried, not exhaustively traversed. Selection conditions and historical/removed content are not resolved against an account. |
| Ambient NPC speech and proximity barks | Authored `NPC_*` voice types retain exact audio and are labelled ambient. | Overhead bubbles, simultaneous speakers and capture crops need separate image replay. |
| Walking conversations, mission chatter and broadcasts | `MissionTalk_3d` and `Broadcast*` records are present; exact authored paths remain usable. | Floating captions, remote voices and overlapping dialogue are not individually replay-verified. |
| Multi-performance sentences | Of 1,044 `TalkSentenceMultiVoice` rows, 1,009 refer to present sentences and 14 of these identify a single performance. | The new reader resolves the 14 unique performances through VoiceConfig. The remaining 995 present sentences retain their text and unavailable audio. |
| Real-time cinematic captions | 689 sentence rows reference `VoiceType=Cutscene`; captions are now retained. | No per-caption audio timing/segment binding. A whole cutscene track is never substituted for one caption. |
| Pre-rendered movies | Regional video and mission data bind 154 scripts with 860 intervals to 244 movie files per dub. Direct publisher records contain 996 additional subtitle intervals, including the 59 Mandarin cues for video 4781. Five Serval and two Acheron fragments play in all four dubs and eleven Silent Galaxy lines also play in Korean and Mandarin. | Exact playback for the other captions and identifying the remaining publisher records by their declared movie paths remain open. |
| Narrated storybook content | 1,437 `TarotBookSentence` records directly reference `VoiceConfig`. Player variants produce 2,586 exact bindings in each installed voice language. | UI association, timing and full-screen text capture still need replay. |
| Character profile/voice archive | 5,445 `VoiceAtlas` rows; `AudioID`, not the menu's `VoiceID`, is the voice-config key. Exact `AudioID` records are indexed with original audio where installed. | 3,614 rows use Wwise `AudioEvent` instead; their text is indexed but event-to-media binding is unavailable. |
| Combat, idle and character reaction lines | `VoiceAtlas.IsBattleVoice` identifies 2,506 battle entries; their localized text is retained. | Not all combat audio displays subtitles. Event-driven playback is unresolved; no inference from filename or voice title. |
| Phone messages and reply choices | `MessageItemConfig` has 13,779 rows, including 13,057 typed `Text` items. Plain-text bodies/options and the 26 conditional text overrides are indexed. | Phone-panel OCR is not newly verified; all conditional variants are retained rather than selecting the player's current branch. |
| Message attachments and media | The schema distinguishes `Text`, `Sticker`, `Image`, `Raid`, `Video` and `Link`. | Attachment labels are excluded from dialogue; no attempt to transcribe images, video or stickers. Player-to-player chat and server mail are not read. |
| Event chat panels | Plain text from `RestaurantMessageConfig` (154 rows) and `IdleLiveMessageContent` (110 rows, 100 with text) is indexed. | Other event-specific panels and new event schemas require explicit adapters. |
| Event stories, minigame speech, puzzles and scene overlays | Additional schemas include `ActivityHipplenSentence` (371), `ClockParkTalkText` (251), `IdleLiveEventSentence` (5), `ChimeraTalk` (295), plus talk/assistant/bubble tables. Some refer back to shared sentences; others hold separate hashes or audio events. | Separate hashes/events are not imported by this change. Obfuscated `FateMasterTalk` and `LimaoNewsMessageItem` fields remain unmapped. |
| Simulated/Divergent Universe narrative and choices | Shared sentence content is retained. `RogueCommonDialogue`, rogue story tables and `RogueDialogueOptionDisplay` (2,302 rows) establish additional paths and option text. | Dedicated option/result presentation, parameter substitution and complete script traversal are not implemented. Gameplay descriptions are not bulk-imported as dialogue. |
| Books, readables, data-bank prose and audio collectibles | `LocalbookConfig` contains 1,121 content records; `AudioBookData` has 12 event references. | These long-form fields are outside the current sentence adapter. Page/paragraph segmentation and authored audio-event mapping are needed. |
| Full-screen narration, storyboards and comics | Text already referenced by supported sentence/storybook tables can be indexed. | No dedicated comic-caption extractor or complete art-embedded text mapping is established. Absence of a table named “Comic” is not evidence that the presentation does not exist. |
| Story summaries, loading tips and general UI | Separate `StoryAtlasTextmap`, `LoadingDesc` and other text schemas were located by name. | Not ingested as spoken dialogue. Table-name discovery alone does not validate field mappings; these additional downloads hit upstream rate limiting. |

## Voice-state rules

The record's voice state describes evidence, not merely whether an audio file
was returned:

- `voiced`: the authored locale source hash resolves to an installed PCK entry.
- `unvoiced`: explicit `VoiceType=NoVoice`, or a verified plain-text message
  modality. Message `ItemType=Text` and its reply choices are structurally
  separate from media attachments; only text items and their overrides qualify.
  The event message adapter similarly admits only `DisplayText`/`Reply` content.
- `unavailable`: an authored voice is unresolved/missing, an audio event has no
  media binding, or multi-voice/cutscene semantics prevent safe playback.
- `unknown`: a general sentence has no primary voice reference. Absence of
  `VoiceID` alone cannot certify silence, as the multi-voice table demonstrates.

The 244,380-row sentence table contains 159,646 rows without a primary voice ID,
53 with an unresolved nonempty ID and 272 using explicit `NoVoice`. The parser
keeps existing spoken identities and gender variants. Additional sources use
separate identity prefixes; conditional message variants include their text hash.
It does not guess genders, combine performances or choose a branch from account
state. Missing localized text remains absent rather than falling back to another
language.

## Validation results

On November 8, 2026 each of the 14 singleton MultiVoice IDs resolved to an
original WEM in every installed 4.6.0 dub (56 file bindings). Three complete
WEMs per locale were read and checked for RIFF headers. Across the full
1,044-row MultiVoice table, all alternatives were present in all four archive
indexes for 1,040 IDs. Multiple variants under one sentence still require
evidence of which performance played. Another 35 IDs in the table have no
matching TalkSentence row in this snapshot. The October totals below predate
this correction.
[MultiVoice IDs](https://github.com/DimbreathBot/TurnBasedGameData/blob/74a7b96fba32f00cf495a5c00b0311bd02207aaf/ExcelOutput/TalkSentenceMultiVoice.json)
· [Authored source paths](https://github.com/DimbreathBot/TurnBasedGameData/blob/74a7b96fba32f00cf495a5c00b0311bd02207aaf/ExcelOutput/VoiceConfig.json)

The same revision contains 985 `PlayMultiVoiceTalk` calls across 64,281
non-layout `Config/Level` JSON files. Every call supplies only the sentence
ID. These calls cover 952 of the 995 ambiguous sentences. Another 30 appear
as ordinary dialogue or choice references. The remaining 13 had no explicit
sentence reference in the examined level files. None of the alternatives for
these 995 have `IsPlayerInvolved`. In one mission both outcomes of a mission
predicate call the same MultiVoice sentence. In another, two random branches
play distinct, named voices for earlier lines before reaching the same shared
sentence. Exact playback of an ambiguous subtitle requires the selected
runtime voice ID or another explicit binding.
[Mission predicate](https://github.com/DimbreathBot/TurnBasedGameData/blob/74a7b96fba32f00cf495a5c00b0311bd02207aaf/Config/Level/Mission/5011901/Act/Act501190102.json)
· [Branched sequence](https://github.com/DimbreathBot/TurnBasedGameData/blob/74a7b96fba32f00cf495a5c00b0311bd02207aaf/Config/Level/Mission/4340180/Act/Act434018013.json)

The real-data pass used integrity-checked cached Chinese/English Main and
ordinary textmaps at the same immutable revision and read all installed locale
PCK external tables. Every resulting Chinese/English record passed the shared
`LocalDialogue` contract; each locale had zero duplicate record identities.

| Selected text/voice | Localized records | Bound original voices | Certified unvoiced | Unavailable audio | Unknown voice status |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simplified Chinese / Mandarin | 273,850 | 93,564 | 16,566 | 5,492 | 158,228 |
| English / English | 273,854 | 90,616 | 16,566 | 8,440 | 158,232 |

These are metadata records, not a count of unique spoken sentences or completed
missions. Alternate player voices and conditional text are separate records.
Differences between locales are not classified as a corrupt install without
additional evidence. Japanese and Korean source-hash checks also succeeded,
with 91,957 and 92,043 bound links respectively before localization filtering;
their full textmaps were not part of this pass. Traditional Chinese and all
translation combinations retain their existing parser contract but were not
newly exercised against real localization tables.

The previous sentence-only Mandarin parser resolved 89,147 of 89,274 candidate
voice links. The largest new exact bindings are narrated storybook and character
archive records. This audit did not decode/listen to every voice, run the game,
change a save or perform account writes.

Synthetic regressions cover missing primary voices versus multi-voice metadata,
explicit silence, missing voice records, unsafe paths, player variants, cutscene
caption retention, typed phone items/overrides, archive `AudioID` semantics and
changed table schemas. Run `python -m pytest backend/tests/test_starrail_assets.py
backend/tests/test_new_rpg_languages.py` for these contracts and the existing
locale bindings. New presentation-specific desktop/mobile OCR replay, zoom/DPI
and live device acceptance remain unverified; the prior opening-dialogue replay
in [presentation notes](../game-ocr-presentations.md#starrail-genshin-endfield)
does not prove the newly added surfaces.

## Update and format limits

The adapter rejects unexpected table containers or renamed required schemas,
so an unsupported format cannot quietly look like an empty successful import.
Wwise header/table bounds and extraction identities retain their existing
validation. Metadata/network failures propagate to preparation, which preserves
the previous completed index. A rate-limited upstream is not proof of missing
installed dialogue.

The install fingerprint covers PCK and DesignData file metadata,
`BinaryVersion.bytes` and `config.ini`. It also hashes the small release
markers for DesignData, asset bundles, audio and video in the base and
persistent directories. A local text hotfix that replaces `M_DesignV.bytes`
at the same size and timestamp now triggers a rebuild. Online-only updates
still require remote revision polling and version-paired subtitle acquisition
in #84. The 4.6 publisher manifest lists the marker names and the installed
4.6.0 client contains the corresponding base and persistent design markers.
[Official Global 4.6 file manifest](https://autopatchos.starrails.com/client/sophon/manifests/cxi9x2wxybk0/20260918/4.6.0/5ojqcjYEliu4/manifest_edb916e5a1ca140c_65fc23eec5dce74324cada65dc595341)

Future additions should traverse authored script references, resolve event/media
relations and add independently annotated replay cases for the corresponding
presentation. Adding every localization string, selecting a multi-voice entry by
ordinal or guessing caption timing would not establish coverage.
