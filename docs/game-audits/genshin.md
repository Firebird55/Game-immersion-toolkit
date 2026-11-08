# Genshin Impact narrative audit

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
| Character/profile and combat voices | 9,183 FettersExcel rows; voice triggers include Fetter, AnimatorEvent, WeatherMonologue, JoinTeam, Costume and Gacha | Not fully indexed. Fetter trigger arguments repeat across characters and need an exact character join. Filename or speaker guesses are not substitutes. Combat sounds without authored subtitles cannot be turned into transcript text. |
| Card-game dialogue and tutorials | 1,256 GCGTalkDetail rows with parallel content/voice arrays | Nonzero voice IDs are paired with the original array position, including gaps. Conflicting IDs are excluded. Zero-voice slots and emoji-only messages remain outside this import. |
| Choices and black-screen narration | 23,483 global forced-choice rows; explicit black-screen role types | Retained and tagged by authored modality. A player role, blank audio filename or missing voice does not establish silence. Exact voice bindings still take precedence. |
| Storyboards, comics and cinematic dialogue | 242 Storyboard Talk files, 159 StoryboardGroup files and 37 Cutscene Talk files | Supported Talk rows are retained; explicit storyboard/narration types receive cinematic channel coverage. No claim of complete comic layout or sequence recognition. |
| Prerendered cinematics | 319 English SRT files in the reference snapshot versus 275 installed USMs | Separately inventoried. The adapter does not decrypt USMs, bind their locale tracks or cut per-cue movie audio. SRT presence alone does not prove an installed playable clip; whole movies are never used as line audio. |
| Books, notes and readables | 1,919 English Readable text files; localized file identities | Version-matched book assets are indexed by paragraph as text-only content. Translations require the same file identity and paragraph count. Other readable assets and exact overlaps with known authored voice text remain unknown. This is not blanket support for voiced Travel Log archives. |
| Mail, messages and glasses chat | 323 MailExcel rows, three BirthdayMail routing rows, 421 obfuscated TpsGlassesChatMessage rows | Inventoried but not imported. Account mail and social chat are not accessed. The new glasses-chat fields need a verified text/voice schema before enabling that presentation. |

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
