# Genshin Impact narrative audit

## Regional Windows Setup, November 13, 2026

Setup can acquire the active Global or mainland China launcher release. It follows
the selected regional HoYoPlay branch and downloads original voices from that
region. For the Global base it first requests the exact OSRELWin text extraction.
A CNRELWin extraction can supply the same text only when both independently
released game builds agree on the version, revision markers and complete
AssetBundles inventory by relative path, size and publisher checksum. Setup
also compares the resource, data and silence indexes, content table and service
catalog. A mismatch requires a matching Global extraction. Each voice binding
keeps its original region's immutable Sophon build and selected package.
[Global launcher](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8)
· [Mainland launcher](https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?launcher_id=jGHBHlcOq1)

Global 7.2.0 build `msj5r4DqSLOw` and mainland build `asDgc67wRUeO`
shared all 2,031 AssetBundles blocks, the three revision files, all three
streaming indexes, the content table and service catalog. On Windows the
language worker used the Global publisher channel with an empty game-folder
setting and the matching immutable text revision. It prepared 464,300 English
records with Simplified Chinese translations requested. Of these, 160,654
had verified original audio. LocalVoice exported one story line and one
profile line to MP3. From distinct Global publisher packs the story line
`80030105` decoded to 8.263 s in English, 6.093 s in Japanese, 5.048 s
in Korean and 6.267 s in Mandarin. This comparison covers launcher bases.
In-version Global hotfix discovery and region-specific replacements remain open.
[Matching text extraction](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca)

## Character triggers in gameplay, November 13, 2026

The reader follows each authored AnimatorEvent, WeatherMonologue, JoinTeam,
Costume and Gacha trigger's original WEM, actor switch and player condition.
A trigger can carry several eligible performances. When the same performance
has one unique subtitle hash in the character profile table, its existing
profile row also supports gameplay capture. The selected audio binding
records the originating trigger types and IDs. Different texts attached to the
same performance remain ambiguous. Sources without a mapped actor, a unique
profile subtitle or a matching dub recording do not acquire a spoken line.

| Trigger family | Matched English profile performances on 7.1 | Matched English profile performances on 7.2 |
| --- | ---: | ---: |
| AnimatorEvent | 1,701 | 1,733 |
| WeatherMonologue | 453 | 461 |
| JoinTeam | 365 | 371 |
| Gacha | 122 | 124 |
| Costume | 0 | 0 |

On 7.2 the normal Windows language worker verified the selected English
recording for every counted performance. One line per matched family was
exported through LocalVoice. The four samples also decoded in each of the four
original Global dubs. The 7.1 column counts actor, media and text joins.
Of 31 distinct 7.2 Costume actor/file combinations, eight also occur among
Fetter's source candidates. None supplies a unique profile sentence through
its actor and trigger. The outfit name or inventory description cannot identify
the words in its original performance.
[Publisher text and playback metadata extraction](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice)
· [Outfit configuration](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/AvatarCostumeExcelConfigData.json)

## Character profile and combat performances, November 9, 2026

Normal preparation joins the profile's avatar ID, Fetter voice trigger and
subtitle hash to the actor's configured voice switch. The avatar's numeric
`combatConfigHash` also resolves newly numbered configuration files. Original
media comes from the selected publisher dub. Separate male and female takes
use each source's gender field. Across 11,869 Fetter GUID/file pairs shared by
7.1 and 7.2 the named and obfuscated actor fields agreed. The corresponding
gender fields agreed for all 32 pairs with an explicit gender.
[Character configuration](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Avatar)
· [Profile text and triggers](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/FettersExcelConfigData.json)

| Publisher release | Distinct Fetter rows | Rows with original audio |
| --- | ---: | --- |
| Mainland 7.1.0 | 9,183 | 9,182 English |
| Mainland 7.2.0 | 9,330 | 9,329 English, all 9,330 in Japanese, Korean and Mandarin |

The same reader resolved all 147 newly added character entries. A profile
performance and a combat performance for Valeriy decoded in each dub. The
English samples lasted 24.505 and 1.120 seconds. The selected English
packages lacked Kachina's source for Fetter 100024. Her three other dubs
contained the source. The normal English desktop worker exported Valeriy's
two samples and Venti's two protagonist takes, then reproduced the four MP3s
offline using a fresh output directory. Independent AnimatorEvent, WeatherMonologue, JoinTeam,
Costume and Gacha triggers still need their own text and media evidence.

## Installation-free launcher release, November 9, 2026

Without a game folder the Windows language worker follows the released mainland
HoYoPlay branch into its Sophon build. It reads the Windows resource, silence and
data revision markers from the game manifest and selects the immutable CNRELWin
extraction matching all three. For 7.2.0 the matching markers were 49008628,
48722240 and 49008628. Two later 7.2 text snapshots already described hotfixes.
The worker verifies the decompressed checksums of manifests and audio chunks,
uses each localized PCK's own bounds, and fetches the original WEM for the
selected authored path. Existing prepared recordings keep their immutable
build identity. The updater can adopt another launcher build when the same
formats and matching text snapshot are available.
[Mainland released branch](https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?launcher_id=jGHBHlcOq1)
· [Matching text revision](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca)

The Global and mainland manifests had matching file checksums for all 178
localized PCKs in each of the four dubs. The text comes from the mainland
catalog. Independent Global hotfixes and historical performances still have the
separate coverage described below.


Audited 2026-10-27 against an installed Windows 7.1.0 client and its English
voice pack. No account, game files, settings or live companion data were changed.
The read-only inventory found 1,985 asset BLKs, 275 USM movies and 310 audio PCKs.
The existing external-table reader resolved 169,523 English entries in 176 PCKs.
These are resource counts, not a claim that every resource is dialogue.

The metadata reference was Dimbreath's community mirror at
`792978e5503ecfba73dcb3562ed44a0d35a2abe2`, titled
`CNRELWin7.1.0_R48379043_S48511369_D48533839`. This is a third-party snapshot
of game data, not an official publisher API. The installed BLKs were inventoried
but their encrypted narrative data was not independently decoded. Matching the
release number does not establish that every server hotfix or optional asset is
present. Playback additionally requires the exact source hash and bounds in an
installed locale package.

## Presentations and limits

| Presentation | Observed evidence | Adapter behavior and remaining gap |
| --- | --- | --- |
| Quest and ordinary conversations | 23,208 Quest Talk files; 203,908 global DialogExcel rows; several coexisting Talk schemas | Parses supported authored ID/hash pairs. Runtime Talk records take priority; the global table fills absent IDs. Conflicting identities are excluded. |
| Optional NPC, gadget, furniture and hangout interactions | 16,927 Npc, 1,473 NpcOther, 1,485 Gadget, 1,287 Coop and associated group configurations | Supported Talk content is included regardless of whether it has audio. Group/routing configuration alone is not dialogue. Missing voice metadata stays unknown. |
| Events | 2,107 Activity Talk files, 105 ActivityGroup files, many dedicated event Excel tables | Supported event Talk content is indexed. Event-specific UI formats and expired/removed assets do not acquire coverage merely because ordinary event Talk works. |
| Ambient dialogue and reminders | 18,541 ReminderExcel rows; 1,798 BubbleTalkData rows; global dialogue fallback | Supported reminders use their own Medium-first text hash space and dialogue/tip/gameplay channels. `hasAudio: true` with missing audio is unavailable; omitted flags remain unknown. The separate BubbleTalk schema is inventoried but not mapped. |
| Character/profile and combat voices | 9,183 FettersExcel rows on 7.1; voice triggers include Fetter, AnimatorEvent, WeatherMonologue, JoinTeam, Costume and Gacha | The November 9 profile audit above covers the Fetter trigger and actor join on two releases. Other trigger families and combat sounds without authored subtitles remain open. |
| Card-game dialogue and tutorials | 1,256 GCGTalkDetail rows with parallel content/voice arrays | Nonzero voice IDs are paired with the original array position, including gaps. Conflicting IDs are excluded. Zero-voice slots and emoji-only messages remain outside this import. |
| Choices and black-screen narration | 23,483 global forced-choice rows; explicit black-screen role types | Retained and tagged by authored modality. A player role, blank audio filename or missing voice does not establish silence. Exact voice bindings still take precedence. |
| Storyboards, comics and cinematic dialogue | 242 Storyboard Talk files, 159 StoryboardGroup files and 37 Cutscene Talk files | Supported Talk rows are retained; explicit storyboard/narration types receive cinematic channel coverage. No claim of complete comic layout or sequence recognition. |
| Prerendered cinematics | Version-matched SRT subtitles and regional Windows USM inventory | Exact movie names yield timed subtitles and predecessor context. Locale recordings and isolated spoken performances remain unresolved. |
| Books, notes and readables | 1,919 English Readable text files; localized file identities | Version-matched book assets are indexed by paragraph as text-only content. Translations require the same file identity and paragraph count. Other readable assets and exact overlaps with known authored voice text remain unknown. This is not blanket support for voiced Travel Log archives. |
| Mail, messages and glasses chat | Mailbox templates, system notifications, Eye of Graeae messages, replies, topics and attachments | Setup imports authored text, translations and identified senders from the matching public version. Mailbox templates and system UI support unvoiced capture. Chat performances have unknown voice status. |

The reference contains 55,891 Talk files and 9,677 Voice files in total; many
are routing, lookup or emotion records. Counts overlap the presentation rows and
must not be summed as independent dialogue totals. Unrecognized content schemas,
missing localized text and unresolved performances produce public coverage
warnings rather than silently implying completeness.

## Update and voice safety

`LANGUAGE_INDEX_VERSION` is 3. The adapter checks the metadata release title
against the installed launcher configuration. A known version mismatch or wholly
unrecognized voice schema produces `unsupported_game_format` with a refresh/update
instruction. Unknown version provenance blocks text-only readable imports.
The common fingerprint includes text/config manifests and authored design data
where present, so voice-package stability alone is insufficient to reuse an index.
The installed-file check hashes the three `AssetBundles/*_revision` markers,
the base text/resource manifests and the persistent `data_versions_persist`
and `res_versions_persist` indexes. A replacement with the same size and
timestamp now invalidates the prepared index. Remote-only changes still
require the regional online updater in #83.
[Global 7.2 base manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/msj5r4DqSLOw/manifest_92303edbe132c634_2b4ef596e7440779759717433d1c86d9)
· [Persistent index paths](https://github.com/CollapseLauncher/Collapse/blob/7d975a8ffec73c6790af5194655dbc3ce85fef67/CollapseLauncher/Classes/RepairManagement/Genshin/Fetch.Persistent.cs#L76-L109)

Voice paths must match an installed locale's hashed external entry. Missing
packages and ambiguous performances are retained as unavailable, not silently
unvoiced. Multiple performances are accepted only as one distinct male/female
pair; two same-gender candidates cannot produce duplicate IDs. Traversing or
absolute source paths are rejected. No audio is synthesized and no missing text
is translated or transcribed from sound.

The November 8, 2026 source check verified that Genshin's Mandarin packages
and Wwise paths use `Chinese` for both Simplified and Traditional Chinese.
Two Paimon lines matched the published 4.8 Mandarin index, one in `1001.pck`
and one in `External21.pck`. The alternative `Chinese(PRC)` hash matched
neither. The reader now probes and hashes the Genshin namespace and preserves
previously bound local recordings that use the older toolkit spelling. The
official server supplied the Mandarin evidence. The installed 7.1 client in
the original audit contained the English pack.
[Publisher 4.8 Mandarin file index](https://autopatchcn.yuanshen.com/client_app/download/pc_zip/20240705190726_7q0dq7IxqQEpugte/ScatteredFiles/Audio_Chinese_pkg_version)

In the 7.2 extraction, 4,545 reminder rows explicitly signal audio. Of those,
4,127 name a WEM through a recognized voice trigger. The other 418 remain
unavailable. One has a routing lookup without a source file, two share a
number with a different trigger type, and 415 have no matching trigger in the
reviewed metadata. The checked 7.1, 6.7 and 4.5 voice snapshots supplied no
additional exact paths for those IDs. Missing reminders still require a
different authored binding or historical source.
[Reminder flags](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/ExcelBinOutput/ReminderExcelConfigData.json)
· [Voice trigger lookup](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Voice/Lut/Lut.json)

Readable downloads are immutable-revision archives parsed in memory. The parser
rejects traversal, links, foreign directories, duplicate identities and excessive
file/expanded sizes. It never extracts upstream paths. Book capture remains the
global opt-in exact-match behavior; partial page text and unknown voice status
do not gain fuzzy unvoiced capture.

## Written mail and Eye of Graeae messages

On 7.2 the Global Windows preparation worker returned 469,879 English records.
Of the 1,044 authored mailbox and message records, 332 were mail bodies, 332
were mail subjects and nine were system notifications. The Eye of Graeae
interface provided 281 full messages, 51 choices, six attachment captions,
four location objectives and 29 thread titles. All 1,044 had Simplified
Chinese translations. The five supported study selections each exposed
these entries, with one additional mail subject and body in Simplified Chinese.
The same reader found 984 English records on 7.1.

The mailbox uses the Medium text namespace. System notifications and Eye of
Graeae use the ordinary namespace. The reader distinguishes the full message,
preview, attachment, option and identified sender fields. It recognizes
renamed fields by their uniquely preserved values across independent records.
In the 7.2 public client data, the chat body and option hashes have no exact
DialogExcel text-hash link. Sample sentences shared with other presentations
therefore retain unknown audio status. The Windows capture index recognized
mail 3, including its Chinese translation, with unvoiced capture enabled.
[7.2 mailbox](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/MailExcelConfigData.json)
· [7.2 Eye of Graeae messages](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/TpsGlassesChatMessageExcelConfigData.json)
· [7.1 Eye of Graeae messages](https://gitlab.com/Dimbreath/animegamedata2/-/blob/9587d1afbd9ab0419cdd00dc05ecd114b9e3fe99/ExcelBinOutput/TpsGlassesChatMessageExcelConfigData.json)

## Short conversation cues

The 7.2 Global English Talk graph provides 122,504 definite predecessor links
between playable conversations. Of these, 5,836 successors have fewer than
eight normalized English characters. Only a unique incoming edge from one
unconditional outgoing edge is used; disagreements, branching choices and
missing recordings are excluded. Capture requires a stable exact predecessor
inside the same window, crop, language, player variant and capture session.
Global Dialog `401860220` could not be selected from its short caption alone.
Replaying its authored preceding caption twice in the normal language index
selected the correct original performance. The 7.1 runtime successor field
also agreed with 165,503 nonempty Excel transitions. Four conflicting pairs
were excluded. Previous context never adds audio to a line with no binding.

## Cinematic subtitle timing

The November 13 cinematic check matched 252 of the 319 English subtitle files
to one of 279 Global 7.2 launcher movies. Four matching files contained no
caption text. The remaining 248 movies contributed 4,535 English cues and
4,283 immediate predecessor links. Japanese had 4,563 cues, Korean 4,538,
simplified Chinese 4,586 and traditional Chinese 4,580. Mainland 7.1 had
4,330 English cues from 240 of its 275 movies. Cue identities retain exact
start and end milliseconds. Languages may time dialogue differently, so an
ordinal-only match is insufficient. Translation joins use matching ordinal
and timestamps, or complete matching ordinal sequences with exclusive
overlapping intervals in both directions. This yielded 2,417 simplified
Chinese translations for the Global 7.2 English cues. The subtitle timeline
establishes the text's display time. Isolating a spoken recording and identifying
its locale track in the USM are still open. The records retain unknown voice status.
[7.2 movie subtitles](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/Subtitle)

## Historical quest and event audio

On November 8, 2026, the source audit compared the Global 7.2 Windows base
voice packs with 14 earlier mainland-China Windows releases. Each supplied
Mandarin, English, Japanese and Korean. The audit checked all four 7.2 Sophon
voice-manifest checksums and read the external Wwise directories from 178 PCKs
per dub. The historical checks used bounded requests to publisher packages
where individual files were available. For later releases, they followed the
archived branch and version through the publisher's Sophon build service to
the four locale manifests and their chunks.
[Global launcher branches](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8)
· [4.8 publisher package index](https://autopatchcn.yuanshen.com/client_app/download/pc_zip/20240705190726_7q0dq7IxqQEpugte/ScatteredFiles/Audio_Chinese_pkg_version)
· [3.8 distribution record](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/3.8.0.json)
· [2.8 distribution record](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/2.8.0.json)
· [Historical launcher records](https://github.com/kuaichu/game-cdn-archive/tree/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e)

The same 14 historical Windows builds are available on the Global CDN. For
each build and dub, the audit compared the Global and mainland inventories by
package path inside StreamingAssets, byte length and publisher MD5. All
**8,256 PCK entries across 56 release/language combinations** matched in both
directions. For Sophon releases the build, version tag and game manifest were
checked against the archived Global release and each voice manifest was
verified against the checksum from the publisher. This gives a Global source
for the 39,020 additional IDs recovered from historical editions below.
[Global release records](https://github.com/umaichanuwu/meta/blob/9019bb94f6dccb62bd11be734599644ed20e73b3/hoyodata.json)
· [Global 3.1 Mandarin package index](https://autopatchhk.yuanshen.com/client_app/download/pc_zip/20220917165430_NyMmj1Ta9KlZKgCZ/ScatteredFiles/Audio_Chinese_pkg_version)
· [Global 6.2 Japanese voice manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/b1yX8g30suHF/manifest_e6602b44c4d9a827_01aedf0468eb7ff42026a26d195e6447)

The comparison starts with 188,882 distinct 7.2 Dialog IDs with an
unambiguous text hash, English and Simplified Chinese text, and at least one
recognized authored Dialog WEM path. Of these, 36,120 occur in timed-event
quests via the quest's explicit `type: EQ`, its talk ID and the Talk record's
dialogue IDs. Each hit requires **every authored path in all four dubs of the
same release**. The rows count IDs once across releases, in the order shown.
[7.2 Talk records](https://github.com/DimbreathBot/AnimeGameData/tree/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Talk)
· [Quest assignments](https://github.com/DimbreathBot/AnimeGameData/tree/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Quest)
· [Authored voice paths](https://github.com/DimbreathBot/AnimeGameData/tree/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Voice)

| Windows release | Additional IDs with all four dubs | Of those, timed-event IDs |
| --- | ---: | ---: |
| 7.2 Global base | 149,737 | 6,241 |
| 4.8 mainland China | 16,520 | 12,574 |
| 3.8 mainland China | 0 | 0 |
| 2.8 mainland China | 11,889 | 9,112 |
| 1.6 mainland China | 0 | 0 |
| 5.8 mainland China | 6,628 | 5,288 |
| 6.4, 6.7 and 7.1 mainland China | 0 | 0 |
| 3.1 mainland China | 1,432 | 717 |
| 6.2 mainland China | 2,551 | 2,175 |
| 6.1, 6.0, 5.5 and 2.4 mainland China | 0 | 0 |
| **Present in at least one of the 15 releases** | **188,757** | **36,107** |
| **Still missing or incomplete** | **125** | **13** |

Of the remaining 125 IDs, 56 lacked a complete set of their authored paths
in any single dub, and 69 had at least one dub. For a playback check, the
publisher's 3.1 files supplied all four complete WEMs for Dialog `400790201`
in the event quest *Bonds of Melody*. The Mandarin, English, Japanese and
Korean recordings decoded to non-silent PCM lasting 4.544, 5.759, 7.560 and
5.575 seconds respectively. A second download from the Global 3.1 server
decoded to the same durations and had identical SHA-256 digests for all four
original WEMs. [Authored quest](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Quest/40079.json)
· [Audited 3.1 distribution](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/3.1.0.json)

The 13 incomplete event IDs were also checked in the releases that carried
their events. One ID in quest 40010 (1.6) and five in quest 40040 (2.4) had
Mandarin, English and Korean media in those releases. The authored Japanese
paths were absent. For seven IDs in quests 40177–40179 (5.5), the 7.2 paths
were absent from all four original release indexes. An alternative authored
binding or in-version update is still needed to resolve those performances.
[Quest 40040](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Quest/40040.json)
· [Global 2.4 Japanese package index](https://autopatchhk.yuanshen.com/client_app/download/pc_zip/20211225051318_JHACtHpvJ2yRaZH0/ScatteredFiles/Audio_Japanese_pkg_version)
· [Global 5.5 Japanese package index](https://autopatchhk.yuanshen.com/client_app/download/pc_zip/20250314110016_HcIQuDGRmsbByeAE/ScatteredFiles/Audio_Japanese_pkg_version)

The 3.8 indexes independently confirm 8,782 IDs missing from 7.2, including
7,206 event IDs. All also occur in 4.8. These are package-index matches for
the 7.2 metadata corpus. Lines removed from that metadata, historical script
changes, unnamed WEMs, movie cues, and regional 7.2 hotfixes require separate
evidence. A package hit establishes a source candidate for each dub. Historical
download, revision selection and per-take playback are still outside the
installed-pack adapter.

The installation-free reader keeps a regional record of verified performances
from each prepared release. When a later package drops a recording, the reader
can use the earlier publisher package if the current line ID, original path,
player variant and displayed study-language text still agree. Ambiguous current
package IDs are excluded. November 13 checks replayed the mainland 7.1 and 7.2
English builds in succession. All previously matched surviving lines already
had current recordings. A separate Global test prepared the 4.8 binding for
event Dialog `400810204` and recovered it under 7.2, where the recording is
absent. Normal playback exported 5.664 seconds from the publisher’s older file.
Fresh installations also import verified Windows 4.8 and 5.5 releases for the
chosen edition and dub. Global and mainland share all 1,193 narrative file entries
in 4.8, all 1,498 in 5.5, and the three revision values in each release.
Setup checks each immutable regional release
descriptor and reads only the selected audio pack directories. The archive is
limited to original Talk and voice metadata for lines still identifiable in
the current edition. GitLab provides the historical metadata. When unavailable,
Setup can fetch the same Git objects from GitHub with an existing Git installation.
Current-release preparation remains available if both archival routes fail.
On the Global 7.2 English build, 4.8 recovered 16,303 recordings and 5.5
supplied another 4,017. This raised the playable total from 160,654 to 180,974
among 464,300 indexed records. Global 5.5 Dialog `401730201` exported to a
9.120-second English clip through normal playback. The 4.8-only comparison
also recovered 16,285 Japanese lines, 16,290 Korean lines, 16,292 Mandarin
lines with simplified subtitles and 16,289 with traditional subtitles. For the
same event line the four Global 4.8 sources decoded to 5.619 seconds in English,
5.289 in Mandarin, 6.497 in Japanese and 4.521 in Korean.
[4.8 dialogue](https://github.com/DimbreathBot/AnimeGameData/blob/411376ae92931a04d41ae5a9386d45c0d2deb8a8/BinOutput/Talk/Quest/4008102.json)
· [4.8 original voice binding](https://github.com/DimbreathBot/AnimeGameData/blob/411376ae92931a04d41ae5a9386d45c0d2deb8a8/BinOutput/Voice/Items/3238191112.json)

## Verification

Synthetic regressions cover schema drift, global fallback precedence, conflicts,
parallel card arrays, reminder hash collisions, player variants, missing versus
explicitly silent voices, version mismatch, typed modalities, paragraph alignment
and hostile text archives. See
[the dedicated tests](../../backend/tests/test_genshin_audit.py).

The local pinned-metadata probe completed in 30.94 seconds and retained 441,130
records: 146,834 with installed English audio, 43,431 unavailable, 245,679 unknown
and 5,186 verified text-only book paragraphs. The 8,071 readable paragraphs
include conservative unknown rows. These totals are not counts of
capture-eligible lines. Three bounded sample reads returned valid RIFF payloads
without exporting media. Private aggregate evidence and timings are retained
under ignored `output/checks/audit-genshin/`. The final targeted run passed 36
tests with 10 unrelated Endfield cases deselected.

GitLab REST/raw requests returned HTTP 429 during this audit. The schema and
binding probe used a local Git snapshot at the same immutable revision. It did
not prove production HTTP download availability. There was no live quest replay,
OCR/DPI run, movie decryption, non-English installed pack or controller/mobile
capture acceptance test in this game-specific audit.

## Primary references

- [HoYoverse developer discussion: dialogue playback, choices and Travel Log](https://genshin.hoyoverse.com/en/news/detail/7170).
- [HoYoverse 1.1 details: Books and Archive presentation](https://genshin.hoyoverse.com/en/news/detail/103763).
- [HoYoverse 1.4 notice: Hangout Events and event quests](https://genshin.hoyoverse.com/en/news/detail/9254).
- [HoYoverse published cutscene animation](https://genshin.hoyoverse.com/en/news/detail/165844).
- [Upstream reader implementation](https://github.com/simon300000/genshin-voice/blob/master/update.ts), inspected for authored joins and Medium text-map behavior; reader code is evidence of that implementation, not publisher documentation.
- [Upstream Talk reader](https://github.com/mrzjy/GenshinDialog/blob/main/extract_talks.py), inspected for NPC/gadget/event/hangout Talk handling.
- [Versioned metadata reference](https://gitlab.com/Dimbreath/animegamedata2/-/tree/792978e5503ecfba73dcb3562ed44a0d35a2abe2).
