# Neverness to Everness audit

## Publisher Setup and immutable voice snapshots

Checked November 16, 2026. The Windows publisher route now connects the ordinary
language-preparation adapter and voice service to original regional resources,
without an installed game. Setup offers Global and mainland China alongside
the installed fallback. Text availability follows the selected edition; a
missing study-text language produces an actionable state rather than borrowing
another region's localization.

`backend/nte_publisher.py` records one immutable snapshot containing the selected
branch, release, resource/section identities, reader identity and exact archive,
localization and type-metadata revisions. All PAK locations are inventoried,
including patch deletions. Numeric `_P` precedence follows the referenced
Unreal/CUE rule; equal-priority overlapping claims fail rather than choosing a
filename. The current global import context and all nonempty checked IoStore
indexes are registered, including containers holding dependencies outside the
table directories. Package bytes are downloaded only when needed.
[Read-order reference](https://github.com/FabianFG/CUE4Parse/blob/4d2301a8eb129f593f1c76ff82612400801f1a94/CUE4Parse/UE4/VirtualFileSystem/AbstractVfsReader.cs)

The pipeline reads original localization, dialogue aliases, sequence clocks,
both movie tables, SRT cues and the selected dub's event banks. Translation rows
must match the source namespace, key and source hash. Stale rows are excluded;
missing and partial translations are reported. Media selection uses authored
bank events, language IDs and numeric Wwise sources. Unresolved or ambiguous
performances stay unavailable. Ordinary preparation does not download all WEMs;
playback retrieves the requested original from that immutable snapshot.

### Current regional preparation and playback

The source-development Windows adapter prepared Global **1.5.4** and mainland
**1.5.6** through the normal route. The following inventories include UI strings and cinematic/player
variants; they are not chapter totals or completion percentages. The playback
column describes the independently checked Blackbird sample, not playback of
every indexed recording.

| Edition / study and original dub | Prepared records | Resolved voice records | Sample WEM bytes | Voice-service playback after offline restart |
| --- | ---: | ---: | ---: | --- |
| Global / English | 122,386 | 19,398 | 22,148 | Passed |
| Global / Japanese | 122,366 | 19,308 | 43,538 | Passed |
| Global / Korean | 122,305 | 19,323 | 23,066 | Passed |
| Global / Simplified Chinese and Mandarin | 122,364 | 19,540 | 15,472 | Passed |
| Mainland / Simplified Chinese and Mandarin | 122,381 | 19,540 | 15,472 | Passed |

The WEM hashes match the independently checked original recordings below. The
ordinary voice service produced MP3 audio, reopened the prepared snapshot with
publisher networking prohibited and produced identical decoded PCM. Mandarin
preparation transferred 30,670,848 additional publisher range bytes against an
already partly warmed shared metadata cache; that is not a cold-install cost.
An earlier English run took 488 seconds. Batching small compressed banks reduced
the subsequent warmed English preparation to 197 seconds, with no publisher
range transfers. These timings use the development machine and different cache
states; they do not isolate a controlled performance benchmark.

The mainland preparation began with an empty publisher-resource cache and
already prepared reader tools. It read 28,973 Chinese event banks and reported
the requested English translation as unavailable. The selected mainland
localization resources supply Chinese study text; the route does not substitute
Global English text into that different generation. Other mainland study-text
languages remain edition-dependent. Earlier four-dub mainland acquisition
probes below are separate from this normal Chinese-study playback check.

### Type-data updates and retained history

Publisher preparation selects compatible public type data from the immutable
commit of the [NTE-usmap index](https://github.com/555me/NTE-usmap/blob/1b92d5267092dac6bcfec605bcaf6ae05b664746/index.json),
instead of requiring the installed reader's fixed 1.4 profile. The current run
used `mapping/HT-1.5-153.usmap`, SHA-256
`b198e62ad29a1f6d2141797edfcef2cfa6c832bdf07d82df1f96a98e62144120`.
The helper checks the selected type-data digest before parsing. Community index
entries cannot choose arbitrary repositories: the reader derives the
immutable URL from the allowlisted repository and path. This consumes data only.
New compatible mappings can be adopted without a toolkit release. Historical
snapshots retain their exact metadata and never substitute the latest profile.

Shared publisher HTTP handling revalidates metadata with conditional requests
when validators are available. Preparation rechecks the complete selected
regional discovery before returning an index. A changed release or edition
fails before activation. The existing preparation manager owns staging and
atomic activation; saved indices and historical originals keep their source
identities. Synthetic regressions cover an actual changed text/voice fixture,
stale translations, mid-preparation changes, historical playback without current
discovery, conflicting overlays and partial batch decompression.

### Remaining acceptance

The three voiced `DeadNumber` movie aliases still need an authored StringTable
ownership binding. Complete chapters, conditional/bark/phone/comic presentations,
all cue windows, real upstream-only update adoption, download-cost/resume/metered
behavior and each claimed native host remain open in #88. The live Windows
source flow and separate compiler-free authored-helper checks are distinct
evidence; neither proves full frozen-image, Linux, macOS or Android acceptance.
No release is made as part of this change.

The dated acquisition stages below retain the evidence and limits of each
earlier implementation stage. Their former Setup gaps are superseded only by
the specific current preparation/playback results above.

## November 16, 2026 · Verified regional archive metadata

The former GitHub-issue provider currently returns no usable archive entry.
Fresh preparation now reads the explicitly named Global and Chinese entries
from the public UnrealExporter data file. It resolves the current file commit
before fetching immutable data. A GitHub API outage can use the independently
checked fallback revision; that value still has to verify the selected archive.
No upstream application or downloaded code is executed.
[Checked source revision](https://github.com/luk-gg/UnrealExporter/blob/7f3fb1dee733d36338766467b0c54cbd47d58851/UnrealExporter/aes.txt)

The production reader was checked without a game installation against current
publisher files in both regions. The selected file is
`Client/WindowsNoEditor/HT/Content/PatchPaks/pakchunk2-Windows_0_P.pak`.

| Publisher region | Branch / release | Whole file bytes | Publisher file MD5 | Verified index bytes |
| --- | --- | ---: | --- | ---: |
| Global | PC_150 / 1.5.4 | 23,475 | `09dc1d0a352e2490e3e0e4d37da66d45` | 160 |
| Mainland China | PC_150 / 1.5.6 | 23,492 | `9786d72ed0bf09bdbb8dbbee0763297b` | 160 |

Both complete small archives passed their publisher size and MD5 checks.
The production range reader then verified each encrypted index using two
requests totalling 672 bytes per region. It validates object offsets, exact
HTTP ranges and index SHA-1 before accepting a regional parameter. Each
regional release identity was checked again after acquisition. Partial reads
do not establish the checksum of an entire large PAK. The v12 index offset
adjustment follows the public format reference.
[Global release](https://ntecdn1.perfectworld.com/clientRes/PC_150/Version/Windows/config.xml)
· [Mainland release](https://yhcdn1.wmupd.com/clientRes/PC_150/Version/Windows/config.xml)
· [NTE package format](https://github.com/FabianFG/CUE4Parse/blob/4d2301a8eb129f593f1c76ff82612400801f1a94/CUE4Parse/UE4/Pak/Objects/FPakInfo.cs)

The normal installed reader uses this verified selection and keeps its existing
protected cache behavior. Synthetic tests also cover regional mismatch,
changed metadata without a toolkit change, malformed ranges, damaged indexes
and an unavailable metadata API. This removes the missing fresh metadata
source; it does not yet connect the online file lists to complete localization,
dialogue-table and per-line voice acquisition. Full online Setup, current
release-wide text/voice coverage and the presentation/update/platform work in #88 remain
open. No real parameter values or game files are distributed.

## November 16, 2026 · Publisher text, four-dub sample and runtime videos

A separate read-only source probe recovered the English localization directly
from the published **Global PC_150 / 1.5.4** snapshot. It did not use an
installed game or a community text export. The resource-list SHA-256 is
`13c0469b1eb5f5994b309c763eacf24aba6f340840709df44681a01beebd5a7c`.
The selected member is `HT/Content/Localization/Game/en/game.locres` in
`pakchunk0-Windows_0_P.pak`.
[Publisher resource list](https://ntecdn1.perfectworld.com/clientRes/PC_150/Version/Windows/version/1.5.4/ResList.bin.zip)

The authenticated encoded index supplies the compression-block lengths.
The duplicated entry header does not supply usable block offsets or a
matching member hash in this sample. Reading its offsets instead of the
encoded index would give inconsistent ranges. The existing pinned Oodle
decoder recovered **18,445,451 bytes** from 9,751,183 compressed bytes.
The locres SHA-256 is
`1810d431b0710c9c4ab1a28d34e5b75564a354a8141f40c96479506719e1506d`.
Parsing the NTE 10100 string-array format recovered **121,528 English
entries in 195 namespaces**, including UI; these are not dialogue counts.
`ST_Main_BlackBird` contains 2,438 entries. Public format parameters were
read as data from the pinned reference, without executing downloaded code
or including their values in the repository.
[Encoded entries](https://github.com/FabianFG/CUE4Parse/blob/4d2301a8eb129f593f1c76ff82612400801f1a94/CUE4Parse/UE4/Pak/Objects/FPakEntry.cs)
· [Locres format](https://github.com/FabianFG/CUE4Parse/blob/4d2301a8eb129f593f1c76ff82612400801f1a94/CUE4Parse/UE4/Localization/FTextLocalizationResource.cs)
· [NTE string-array format](https://github.com/FabianFG/CUE4Parse/blob/4d2301a8eb129f593f1c76ff82612400801f1a94/CUE4Parse/GameTypes/NTE/Encryption/NevernessToEvernessLocresEncryption.cs)

The publisher also supplies a companion `.sig` file for each of the twenty
game-content PAKs. The complete companion file passed its manifest MD5.
Its chunk table then verified **150 contiguous 64 KiB blocks** covering the
English locres range, totalling 9,830,400 bytes. The small patch PAK also
matched its companion's single chunk CRC. Integrity evidence here is the
manifest-verified companion and its per-block CRCs; the large PAKs were read
selectively. This does not claim independent RSA-signature validation.
[Publisher chunk-check format](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/PakFile/FPakSignatureFile?lang=en-US)

The same snapshot supplied the named bank
`Play_Vo_BBlackbird01_NPC1064_007` in all four original voice languages.
Each bank's Wwise 154 event and language IDs match its declared name and
locale. The existing bank reader resolves one source with zero gain and
delay. Complete companion files passed publisher MD5 checks, and the bank
and recording ranges passed their chunk CRCs before decompression. Each
original WEM decoded to nonzero PCM with the prepared voice decoder.

| Original language | Media ID | WEM bytes | Decoded duration | WEM SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Mandarin | 58185411 | 15,472 | 1.204603 s | `9fb5c7242fa13a63b467e14962b6845e85f9c4af3c56fd3b839ea3d74c828be7` |
| Japanese | 875594697 | 43,538 | 5.137392 s | `a80a4880c245fd541aae7f47d0ee92f766fe9764346a22aa680b7d991aab4c16` |
| English | 529528553 | 22,148 | 1.864989 s | `df9fea4eb39d2227cd77726255b5fd2192c30905ca1f484dd5a4eef84ed588ee` |
| Korean | 523829702 | 23,066 | 1.821338 s | `320071d81087d3361194c6c37e03f7fd253cc17c5038ab1adc30fceee9229e0c` |

These initial source probes are separate from normal Setup. The owned reader
and historical metadata lookup are now implemented below. Complete locale/patch
selection and normal voice-service integration still need implementation.
Full dialogue aliases, sequence/movie bindings, rolling updates and platform
acceptance remain open.

### Owned selective archive reader

`backend/nte_publisher_pak.py` now reads publisher archives without a game
installation. It checks the complete companion file against the manifest MD5,
validates every selected or cached 64 KiB PAK block, and verifies decrypted
primary/directory index SHA-1 values. Missing contiguous blocks are coalesced
into requests of at most 4 MiB. A damaged cached block is fetched again; a
partly invalid response does not activate its other chunks. No independent
RSA-signature verification or whole-large-PAK checksum is claimed.

The reader uses encoded entry locations, handles compressed and encrypted
members and nonencoded entries, and retains explicit deletion records. An
invalid location listed by a patch is a deletion: it cannot fall through to
an older recording. The overlay helper requires evidenced mount priority
from its caller; it does not guess precedence from PAK filenames.
[Engine deletion semantics](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/PakFile/FPakFile/GetPakEntry/2?application_version=5.5)

Encrypted compressed members can declare either the sum of compressed block
lengths or the sum including AES padding. The reader accepts those two forms,
checks physical bounds and decodes only each block's actual compressed bytes.
The Global 1.5.4 base/patch engine and game configuration resources exercise
the aligned-size form; all eight selected resources were recovered through
the checked reader. Synthetic checks retain rejection of inconsistent sizes.

Archive metadata can also be reopened by its exact source commit and SHA-256,
including from a checksum-verified private cache without a network connection.
It never substitutes the latest parameters for an explicitly historical source.
Synthetic checks exercise corruption, bounds, case ambiguity, regional mismatch,
single/multiple compression blocks, AES padding and deletion versus historical
retrieval. Original regional parameters and game assets are not bundled.

The owned reader retrieved the four sample banks and recordings listed above
from both Global 1.5.4 and mainland China 1.5.6. All eight recordings decoded;
their bytes match the independently checked Global originals. Recreating the
archive and metadata readers with network access prohibited retrieved identical
cached bytes. Separate empty-cache runs transferred 7,481,874 Global and
7,610,758 mainland publisher bytes for the four examples, including the used
indexes and companion files. These are sample costs, not whole-game estimates.

### Original localization through the owned reader

`backend/nte_locres.py` reads the original 10100 localization format, including
shared localized strings, namespaces, authored keys and source hashes. Public
format parameters are fetched strictly as data at an identified source commit;
the localization marker proves their applicability. Explicit historical source
commit/checksum references retain the old parameters after an upstream change.
Unknown headers, invalid offsets, duplicate keys, missing string references and
truncated resources fail instead of yielding a partial table.

Using the signed archive layer, all five Global study-text resources (`en`,
`zh-CN`, `zh-Hant`, `ja`, `ko`) were acquired directly from the selected
Global 1.5.4 patch. Each contains **121,528 entries in 195 namespaces**,
including UI. All five have exactly the same authored key set and source
hashes. The English resource also matches the independently recovered SHA-256
above. This checks translation identity within the selected regional snapshot;
it does not make all those entries voiced dialogue. Mainland patch contents
and base-file fallback require independent selection; the Global files must
not be substituted into a different regional generation.

The owned reader also parsed the original mainland 1.5.6 `zh-CN` patch
resource: **121,545 entries in 195 namespaces**, including 2,438 Blackbird
keys. Its 17,691,445 bytes have SHA-256
`bfd7c1722af7503a629d820b40f359205755b565367f699381455c8a98725a76`.
This checks that original resource independently of the community export.
The inspected mainland base and patch PAK directories list only `zh-CN`
for this resource; that observation alone does not establish the complete
regional text-language scope across other containers.

The archive and localization acquisition layers are implemented. Ordinary
Setup, complete authoring-table extraction, evidenced patch precedence and
update activation remain open in #88. The public support matrix is unchanged.

### Original IoStore authoring resources

The original dialogue and sequence tables are in IoStore containers rather
than the ordinary PAK directory. `backend/nte_publisher_iostore.py` implements
a bounded signed-v8 reader for one selected container. It verifies the complete
TOC against the publisher manifest MD5 and each selected stored UCAS block
against the TOC's SHA-1 before decrypting or decompressing. Cached blocks are
rechecked. Adjacent downloads coalesce up to 4 MiB; an invalid response publishes
none of its blocks. The seekable-stream interface returns only checksum-covered
bytes and refuses gaps, unknown formats and mismatched regional cipher proofs.
There is no independent RSA or whole-large-UCAS checksum claim.
[Primary IoStore format reference](https://github.com/FabianFG/CUE4Parse/blob/4d2301a8eb129f593f1c76ff82612400801f1a94/CUE4Parse/UE4/IO/Objects/FIoStoreTocResource.cs)

In Global 1.5.4, the owned reader recovered the complete original bytes of
`DialogSoundTable`, `BubbleVoiceMsgTable`, `DT_VoiceCaptionDataTable` and
`DT_StorySequenceData` from `Paks/pakchunk1-Windows`, plus
`DT_StorySequenceData_World` and `DialogSoundTable_Favor_QQ` from
`PatchPaks/pakchunk0-Windows_0_P`. All six SHA-256 values match the independent
range probe. The two complete TOCs contain 19,767 and 17,591 file entries.
No installation, game process or community table export supplied these bytes.

These are original Zen package resources, not extracted JSON or legacy loose
Unreal packages. The managed parser still needs to consume them through checked
streams with the appropriate global container, type schema, imports and mount
priority. The resource reader alone does not establish dialogue aliases,
complete current movie timing or normal publisher Setup. Thirteen synthetic
tests cover partial stream reads, unsigned gaps, corruption, AES padding,
compression output bounds, unsafe directory graphs and historical cache
isolation; the archive/localization group totals 57 passing tests.

### Managed authoring through verified publisher streams

The owned managed reader can now consume temporary private publisher streams
instead of an installation directory. `run_publisher_reader` stages the verified
type schema and passes registered loopback sources and archive metadata through
stdin. The child permits only those bounded loopback endpoints, uses independent
seek positions when cloning streams, and cannot redirect requests to another
host. The broker exposes neither a directory listing nor arbitrary file paths.
Failed source verification, incomplete output and stale staging files cannot
become a completed authoring extraction.

The global IoStore resource needs special treatment: the managed parser reads
aligned padding beyond its final block hash. The complete small global UCAS
therefore passes its publisher MD5 before the broker serves it. Other UCAS
streams continue to require checked compression blocks and refuse unsigned
gaps. Large unselected chunks remain in the inventory without relaxing the
512 MiB selected-resource limit; the current base inventory includes a
3,300,228,421-byte non-authoring chunk.

A Global 1.5.4 run through this API read the original current base and patch
tables. It produced **22,894 dialogue aliases**, **21,767 declared event names**
and **87 sequence event groups**. Of those groups, 67 have a resolved caption
table with **429 cues**; all 429 retain original StringTable namespace/key
ownership. The Blackbird sample above resolves to its expected original event.
These counts describe authoring, not verified playback for every entry. The
current aliases require the patch tables as well as the base tables.

The same publisher API also reads the original `DT_MediaFFmpegInfo` and
`DT_MediaFFmpegInfo_Quest` tables. They contain 225 rows in this snapshot;
the existing reviewed namespace rules resolve 42 movie bindings. Other
StringTable aliases remain to be resolved. This exports the current authored
movie configuration without depending on an older community table snapshot;
it does not establish all movie speech or timing.

The managed stream's source-build probe also passed with authored reflection
types: reads spanning the 4 MiB request limit, clone/seek isolation, wrong-host
refusal and a failed source. The hosted compiler-free helper probe exercises
the same transport without real game assets. This fixture is distinct from the
live original-table result and does not establish native game acceptance.

Ordinary publisher Setup still needs manifest-driven container and patch
selection, index activation, localized bank/media acquisition and voice-service
integration. Full movie/presentation coverage, immutable update/history replay
and each claimed host remain separate acceptance requirements in #88. The
installed reader and public support matrix are unchanged.

### The five Global HPW resources are video files

All five `.hpw` resources in this Global 1.5.4 snapshot were downloaded and
checked against their complete publisher MD5s. Restoring their byte encoding
and top-level box identifiers yields valid MP4 containers with `ftyp`,
`moov`, `free` and `mdat` boxes. Each has exactly one H.264 video track and
zero audio or subtitle tracks. Three last 4.000000 s; two last 2.366667 s.
They do not supply the missing sentence audio or localization overlays.
The earlier description of HPW files as hotpatches was unsupported. This
result covers these five files; other HPW inventories and referenced story
movies still require their own checks.

## November 13, 2026 · Regional update and Blackbird dialogue

The ordinary update discovery advanced to Global PC_150 1.5.4 (374 files) and mainland PC_150 1.5.6 (366 files). The mainland localization source matched the publisher's resource list checksum `0d2a993be258446172af9aa2257a0b0f` and logic build 597365. It contains 121,545 Simplified Chinese strings across 195 namespaces. The Global list has a different checksum, `f370641c5faa61efee0b0a89765d3cfe`. [Global release](https://ntecdn1.perfectworld.com/clientRes/PC_150/Version/Windows/config.xml) · [Mainland release](https://yhcdn1.wmupd.com/clientRes/PC_150/Version/Windows/config.xml) · [Matching mainland export](https://github.com/555me/NTEData/tree/4a0f58143001a2b0d33860da15c3feedb1e21c0f)

The mainland source command can include the published event object for a selected dialogue key. It checks the immutable export's entire dialogue StringTable against the same-version localization, and only accepts keys unique across localization namespaces. On 1.5.6, all 2,438 Blackbird entries match and 1,599 keys name an event (1,587 distinct event paths). The event is a lookup reference. Per-language banks, external media and playable audio remain open. [Current mainland event table](https://github.com/555me/NTEData/blob/4a0f58143001a2b0d33860da15c3feedb1e21c0f/DataTable/DialogSoundTable.json)

```text
python scripts/nte_regional_text.py --cache private-cache --output blackbird-voices.json --namespace ST_Main_BlackBird --voice-events
```

In Global English PS5 gameplay, the two `Blackbird01_NPC13201_045` and `_046` lines occur at 2:02:28.6–2:02:30.9 and 2:02:32.8–2:02:35.6. The first asks about being freed from the curse. A different speaker responds before the second line answers. `Blackbird01_Player_293` is spoken at 2:39:16.6–2:39:26.0. These approximate spoken intervals were checked against the matching English dialogue text. They locate the scene in this recording. [Two NPC lines](https://www.youtube.com/watch?v=rrEpbAfpPMk&t=7348s) · [Player reply](https://www.youtube.com/watch?v=rrEpbAfpPMk&t=9556s) · [English localization sample](https://github.com/Waifus-Grace/NTE_Assets/blob/cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7/Localization/en/game.json)

## Released file acquisition across regions · November 9, 2026

The source command now follows each regional branch, decodes the updater resource list and checks its plaintext MD5 against the active launcher. It records independent files and the exact byte ranges of files stored inside aggregate packages. Global PC_140 1.4.11 listed 552 files and mainland PC_150 1.5.4 listed 366. Both included 77 PAK files. The updater format references are pinned by commit and SHA-256. The Global and mainland distributions use different public updater parameters. [Global launcher](https://ntecdn1.perfectworld.com/clientRes/publish_PC/Version/Windows/config.xml) · [Mainland launcher](https://yhcdn1.wmupd.com/clientRes/publish_PC/Version/Windows/config.xml) · [Global patcher integration](https://github.com/Tobiichi-Origuchi/nte_patcher/blob/1135247b3a21ac72304b8bd9f5aa548994f7a8ef/tests/test_integration.rs) · [Mainland downloader reference](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/scripts/nte_downloader.py)

Two empty-cache checks retrieved the same game path from different regional package objects. The Global member was 22,423 bytes, the mainland member 23,485 bytes. Each matched its own publisher checksum. The regional source command can save a selected file without installing or downloading a full game. The archive contents still require compatible game archive metadata and verified localization and Wwise bindings before normal Setup can play a sentence. [Source command](../../scripts/live_game_sources.py)

Direct range reads of all 20 game-content PAK footers and 22 IoStore headers in **each region** established the same layout. Every PAK uses version 12 and marks its index encrypted, including the two small patch samples. Twelve IoStore containers per region mark their content encrypted. Each of the other ten holds one chunk. The two `global.utoc` files point to UE5 `ScriptObjects`; the eight optional-language UTOCs point to `ContainerHeader` chunks with 64-byte companion UCAS files. The public container headers therefore do not supply localized sentences or Wwise media. [PAK footer](https://github.com/trumank/repak/blob/355b5f62f51959c7cc6dd5a51708646ef483065d/repak/src/footer.rs#L22-L32) · [IoStore flags](https://github.com/FabianFG/CUE4Parse/blob/613a67310ebc058f4f5cf207b1fe96c10d7af882/CUE4Parse/UE4/IO/Objects/FIoStoreTocHeader.cs#L24-L33) · [UE5 chunk identifiers](https://github.com/FabianFG/CUE4Parse/blob/613a67310ebc058f4f5cf207b1fe96c10d7af882/CUE4Parse/UE4/IO/Objects/FIoChunkId.cs#L34-L49)

Track headers in all eleven loose Global MP4s and five mainland MP4s yielded no subtitle tracks. The five mainland movies and eight Global movies contained video only. The only loose Global movies with an audio track were the three studio/game logos. This check concerns the `.mp4` entries in the Windows releases; the `.hpw` runtime files and separately referenced story audio still need their own verification. [Global release list](https://ntecdn1.perfectworld.com/clientRes/PC_140/Version/Windows/version/1.4.11/ResList.bin.zip) · [Mainland release list](https://yhcdn1.wmupd.com/clientRes/PC_150/Version/Windows/version/1.5.4/ResList.bin.zip)

```text
python scripts/live_game_sources.py nte-global --cache private-cache --output nte.json --resource Client/WindowsNoEditor/HT/Content/PatchPaks/pakchunk2-Windows_0_P.pak --save selected.pak
```

### Mainland Chinese text without an installation

`scripts/nte_regional_text.py` follows the mainland launcher's release pointer and checks the exact MD5 of the text source's `ResList.xml` against the publisher's `listHash`. It pins the source commit before reading the localization export and checks the active release again before writing the output. If the mirror has moved ahead, the command checks recent release-manifest commits for a unique match. When the mirror has no matching export, retry after it updates. The JSON keeps the namespace and key of each text, including keys reused by different tables. [Mainland launcher](https://yhcdn1.wmupd.com/clientRes/publish_PC/Version/Windows/config.xml) · [Regional text command](../../scripts/nte_regional_text.py)

```text
python scripts/nte_regional_text.py --cache private-cache --output mainland-text.json
python scripts/nte_regional_text.py --cache private-cache --output blackbird.json --namespace ST_Main_BlackBird --key BBlackbird01_NPC1064_007
```

The November 9 check matched mainland 1.5.4, logic build 594078. Its 84,805-byte manifest had MD5 `95588bbea8dfbefa15aea48bf2549032`. Global 1.4.11 declared `24053e7ac1f850cab87b84a16e13657b`. The matching mainland export contains 121,753 Simplified Chinese strings across 195 namespaces, including UI. All 2,438 entries in its Blackbird StringTable agree with the corresponding localized strings, and 1,599 of their keys have explicit event declarations in `DialogSoundTable`. These declarations identify events; the corresponding mainland localized banks and WEMs still need verification. This source publishes Chinese text only. [Matched source commit](https://github.com/555me/NTEData/tree/fe531251f0c618796bf989cbc08dbdbf63055d76) · [Blackbird StringTable](https://github.com/555me/NTEData/blob/fe531251f0c618796bf989cbc08dbdbf63055d76/Text/Dialogue/ST_Main_BlackBird.json) · [Event declarations](https://github.com/555me/NTEData/blob/fe531251f0c618796bf989cbc08dbdbf63055d76/DataTable/DialogSoundTable.json)

## November 8, 2026 · Localized performances and sequence timing

The cooked Global dialogue and bubble sound tables contain explicit aliases
for text keys whose recording has a different name. The installed census
found 21,248 dialogue/bubble keys. Of these, 2,028 had eligible unambiguous
aliases. A native English probe found the indicated localized Wwise media
for 1,458 rows. The reader now looks up these declarations before using
the conventional event name. Conflicting declarations or ambiguous
localization namespaces keep the original voice unresolved.
[Pinned Unreal type schema](https://github.com/555me/NTE-usmap/blob/1b92d5267092dac6bcfec605bcaf6ae05b664746/mapping/HT-1.4-1413.usmap)

The reviewed movie catalog contains 218 definitions. Its explicit voice,
subtitle and StringTable fields yield 42 distinct movie paths across four
tables. In addition to 23 Sequence definitions, the reader recognizes 10
Wuchao, seven Blackbird and two Legend definitions. The installed subtitle
key, localized event bank and media must still resolve for an individual
caption to acquire audio. [Movie tables](https://github.com/Waifus-Grace/NTE_Assets/tree/cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7/DataTable/Skill)

Story sequences use a separate chain from the sequence's caption group to
the Unreal StringTable, dedicated voice event and locale-specific start and
end times. The pinned schema decoded all 177 nested sequence entries in the
inspected main scene table. The reader checks the playback rate, start offset,
unique event, localized media and overlap with surrounding cues. Synthetic
fixtures cover dub-specific clocks, repeated captions and ambiguous audio.
The final end-to-end count of playable sequences on Global remains unverified.
During the November 8 check, the pinned type schema downloaded successfully,
but the then-used archive metadata provider no longer supplied a usable entry.
The type schema and the archive metadata are separate prerequisites. [Global release resources](https://ntecdn1.perfectworld.com/clientRes/PC_140/Version/Windows/version/1.4.11/ResList.bin.zip)

Reviewed on 2026-10-27 against the locally installed client, using discovery from
`backend.game_paths`. This is an asset/adapter audit, not a complete playthrough
or evidence that every visible layout works in OCR. Game files, extracted text,
audio, credentials and machine paths remain in private ignored storage.

2026-10-30 runtime update: [compiler-free desktop dispatch](../nte-runtime.md)
now resolves the self-contained bridge and exact separately inventoried native
dependencies. This changes installation/runtime mechanics, not language or
presentation coverage. Supplier redistribution and full frozen-image acceptance
remain explicit remaining work.

## Installed evidence

The installation contains 20 PAK files, 22 UTOC/UCAS pairs and 178 HPW runtime
files. Fresh native extraction enumerated 805,652 unique virtual paths, including
113,044 localization rows in each of English and Simplified Chinese. Both
localization resources have locres version 3. The initial key-selected extraction
read 18,828 Mandarin event banks, all with Wwise version 154. There are 26,905
Mandarin event banks overall; event availability is not proof of a matching
visible subtitle. Four voice-language media inventories are present.

The updated adapter, with the locally reviewed movie catalog revision
`1816e237ffe9edf687dd6942d028e89cce121381`, produced 113,218 Mandarin-source records:
16,416 with verified voice bindings, 1,861 verified written records, 4,126 authored
voice references whose playback is unavailable, and 90,815 unknown records.
The total includes localization/UI strings and authored player-voice variants;
it is not a dialogue count or a completion percentage. The catalog supplied
23 movie bindings; the installation contains 41 story SRT files.

## Presentation inventory

| Presentation | Installed evidence | Adapter behavior and remaining gaps |
| --- | --- | --- |
| Main, side, legend and bond conversations | Main/side/legend dialogue string tables; dialogue sound tables; localized Play_Vo events | Exact namespace/key text plus a uniquely resolved event/media pair supplies original audio. New or ambiguous mappings remain unknown/unavailable. Some new quest table families remain uncategorized. |
| Ambient NPC, street and world bubbles | `ST_AmbianceDialogue`, `ST_Bubble_*`, `ST_StoryBubble`, bubble voice tables | Classified as ambient dialogue. A visible bubble does not establish silence; only resolved events supply audio. Timing and overlapping bubbles need gameplay captures. |
| Combat barks and shouts | Character, shouts, skill and attack event families; 2,772 Mandarin bank names contain `Vo_Char` | Audio-only events do not establish a subtitle identity. General combat bark/subtitle coverage is incomplete; no guessed text or voice link is created. |
| Realtime cutscenes | `ST_Sequence`, `ST_Sequence_Legend`, story/world sequence tables | Directly keyed voice events work. Dynamic sequence tracks without a reviewed binding remain unknown/unavailable. |
| Prerendered movies | Story SRT keys, FFMpeg movie catalog, CG events, loose movies and packaged media | Reviewed namespace, cue interval and deterministic voice variant are required. All 41 SRT files are inventoried; 23 catalog bindings are not complete movie coverage. Packaged USM or embedded captions have no general new mapping in this audit. |
| Comics and illustrated scenes | 106 unique comic-named assets, including textures and quest blueprints | Existence is verified; panel text ownership and per-panel original voices are not. No generic comic capture claim. |
| Bagel posts and replies | `ST_Bagel_TitleContent`, `ST_Bagel_Reply`, Bagel post/chat/comment tables | 1,536 nonempty written records are unvoiced and eligible only for opt-in exact capture. Server/user-generated posts are outside the installed authored corpus. An authored voice event always overrides the text-only inference. |
| Phone/bond chats | `ST_Likeability`, chat-group/chat-item tables and phone interactions | 7,877 bond-table records remain unknown in this installation. The mixed table needs row-level ownership before distinguishing text messages, voiced calls and choices. |
| Mail | Scheduled/model/birthday mail tables and `ST_PlayerBirthdayMail` | 45 nonempty birthday-mail body records are proven written content. Titles, other mailbox templates and server-delivered mail are not automatically admitted. |
| Response options | 104 ambient rows with authored `option_Player` keys, plus other dialogue branches | Classified response options retain unknown voice status when no event is established. A choice can be spoken after selection; absence of a bank alone never proves silence. |
| Narrative reading and recaps | `ST_DialogueSumUP`, character files, notebook article tables and world descriptions | 280 scene-summary records are written narrative. Character files mix profiles and voice lines, so missing-audio entries remain unknown. Notebook/other reading ownership and layout coverage remain incomplete. |

## Changes and update behavior

The native reader now records authored event presence across available dubs and
event assets. A missing selected voice pack therefore yields `unavailable` when
the authored event exists, not `unvoiced`. It also exposes a complete virtual-file
inventory for private audits and localization header versions. Verified written
content is retained in both legacy bilingual and language-specific preparation.

A fresh installed run found a movie with a two-digit millisecond field. The old
parser silently discarded all 16 cues. The bounded parser now accepts one to three
digits as integer milliseconds, matching
[FFmpeg's SRT demuxer](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/srtdec.c).
All 16 installed cues now have verified voice bindings. Milliseconds are not
rescaled as decimal fractions.

Newer recognized locres headers, unsupported Wwise bank versions and unsupported
reviewed SRT layouts raise `PreparationFailure('unsupported_game_format', ...)`
with recovery guidance. Files changing during preparation raise
`game_files_changed`. Completed caches are published by atomic rename; failed
preparation does not replace the last good index. Unresolved supported-version
event trees remain unavailable and contribute a coverage warning.

The fingerprint now includes every file in installed Content and Config, the
game executable, native reader sources, reader package pin, index version and
movie baseline. It catches added/removed loose localization, configuration,
movies and hotpatches without requiring an audio-bank change. Installed files
use path/size/mtime metadata: an external rewrite that preserves both size and
timestamp is not detected by this fingerprint. No archives were found outside
Content in this installation. Unknown future archive locations or encryption
changes still require a reader update. Language index version is 4.

## Primary-source cross-check

The [publisher's Steam listing](https://store.steampowered.com/app/4508340/NTE_Neverness_to_Everness/)
describes story encounters, side stories, Bagel connections and the independently
listed subtitle/full-audio languages. Its language list is storefront evidence,
not proof that this adapter supports every study locale.

The [developer's version 1.1 notes](https://nte.perfectworld.com/de/article/news/gamebroad/20260602/262480.html)
explicitly add Bagel social features, character messages, story-skip summaries,
dialogue interaction changes and a story voice-mute option. These support the
presentation inventory and the need to separate authored voice status from a
user's current mute setting.

[UEExtractor's upstream documentation](https://github.com/SolicenTEAM/UEExtractor)
identifies NTE's custom archive offsets and encrypted localization.
[CUE4Parse's localization reader](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Localization/FTextLocalizationResource.cs)
contains the NTE-specific string-table path and rejects unsupported newer
localization versions. This audit keeps the pinned reader rather than silently
upgrading native dependencies or importing a remote text corpus.

## Verification and remaining acceptance

Focused synthetic regressions cover voice-state precedence, opt-in exact-only
written capture, missing-dub provenance, ambiguous voice keys, typed format
failures, last-good-index preservation, loose-content invalidation and short
millisecond timing. Existing five-locale and cinematic branch regressions remain
enabled. The modified .NET reader built and freshly extracted the installed
English/Chinese resources; the final binding pass completed in 11.2 seconds.
Private summaries and raw evidence are under ignored `output/checks/nte-audit/`.

No live gameplay, account writes, new audio decoding, desktop/mobile screenshot
matrix, zoom/DPI or full chapter traversal was performed for this audit. Those
remain separate acceptance checks. Full preparation and native OCR should be
rechecked after an actual game update, especially new phone, comic, reading and
sequence presentations.
