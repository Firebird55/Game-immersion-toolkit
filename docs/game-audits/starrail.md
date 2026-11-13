# Honkai: Star Rail dialogue audit

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
paths across chapters 3, 4 and 5 returned HTTP 404. Two published scripts,
CS_Chap02_Act610 and CS_Chap04_Act781_2, contain 10 and 59 cues respectively
and still lack a matching VideoConfig movie or directly bound timeline WEM.
The ten Act610 text IDs were absent from the English, Japanese, Korean,
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
individual VideoConfig paths and movie audio remains open.
[Global 4.7 DesignV marker](https://autopatchos.starrails.com/design_data/V4.7Live/output_17180467_2b67443267a6_475611c71617ea/client/Windows/M_DesignV.bytes) ·
[Mainland 4.7 DesignV marker](https://autopatchcn.bhsr.com/design_data/V4.7Live/output_17180467_2b67443267a6_dc848fdaa66f47/client/Windows/M_DesignV.bytes)

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
| Pre-rendered movies | Regional VideoV and VideoConfig bind 153 scripts with 801 intervals to 242 movie files. Direct publisher caption records add 996 intervals. Five Serval and two Acheron fragments play in all four dubs and eleven Silent Galaxy lines also play in Korean and Mandarin. | Exact playback for the other captions and identifying the additional publisher records by their declared movie paths remain open. |
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
