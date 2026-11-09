# Arknights: Endfield presentation audit

## Publisher resources and story coverage, November 8, 2026

The Global Windows 1.6.4 updater returned resource revision `11529267-11`. Follow
the released regional launcher into `get_latest_resources`, then the main and
initial resource URLs. Their `index_main.json` and `index_initial.json` identify
the VFS group indexes and chunk checksums. The audit checked the selected group
indexes against their published MD5 values and read only the listed byte ranges.
The toolkit uses the matching community text snapshot and obtains original
recordings from installed packages or the pinned Global publisher release.
[Global launcher](https://launcher.gryphline.com/api/game/get_latest?appcode=YDUTE5gscDZ229CW&launcher_appcode=TiaytKBUIEdoEwRT&channel=6&sub_channel=6&launcher_sub_channel=6&disk_type=0&patch_encrypt=1)
· [Inspected resource list](https://launcher.gryphline.com/api/game/get_latest_resources?appcode=YDUTE5gscDZ229CW&game_version=1.6&version=1.6.4&platform=Windows&rand_str=O0xruPqxQxZ9aEYl)
· [Resource index archive](https://github.com/daydreamer-json/ak-endfield-api-archive)

Group 18 supplied the original SparkBuffer `TableCfg` tables. Each of the 14
localization tables contained 167,266 keys. All 2,341,724 values, including
empty strings and UI strings, matched the pinned EndfieldData extraction.
The text locales are English, Simplified and Traditional Chinese, Japanese,
Korean, French, German, Italian, Latin American Spanish, Brazilian Portuguese,
Russian, Thai, Vietnamese and Indonesian. The authored dialogue, radio,
narration, summary and AudioDialog tables compared below also matched the
extraction. The direct publisher data can verify each future snapshot.
[Pinned extracted tables](https://github.com/rmxlinux/EndfieldData/tree/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg)
· [Reviewed SparkBuffer format](https://github.com/EIHRTeam/EndfieldStudio/blob/48c40a5e6a931b08223384077b74b41b484a540f/AnimeStudio.Endfield/Processors/SparkBuffer.cs)

### Dialogue and voice

Of 34,194 AudioDialog IDs, 32,371 name a WEM. For all 129,484 file/language
combinations, a positive authored duration exactly matched presence of the
locale-specific full-path hash in the publisher's external-media indexes.
32,321 files were indexed in all four dubs. The 50 partial files account for 19
missing Mandarin, 35 English, 42 Japanese and 37 Korean recordings. These
counts are index checks. Complete files for the opening line and both
Endministrator performances in a 1.6 mission were previously retrieved from
both regional publishers. [AudioDialog](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/AudioDialog.json)
· [Regional sample evidence](https://github.com/Firebird55/Game-immersion-toolkit/issues/86)

The other 1,823 rows all have `voType=2`, an extensionless event name and
zero durations in every dub. 1,056 names start with `chr_` and 767 with
`eny_`. ResponsiveDialog references 1,326 as combat responses. 1,333 match
Wwise event objects in the inspected publisher banks, with overlap between
these two counts. None is a direct override in conversation, radio, narration,
operator profile or AIBarkText. The reader excludes event names from its WEM
lookup. Their isolated media and any spoken content remain unresolved.
[Combat-response table](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/ResponsiveDialog.json)

The reader now joins exact `_f.wem` and `_m.wem` pairs under a dialogue or
radio override when both authored filenames resolve to the same directory.
It selects the corresponding text from `{F}…{M}…` where a translation has
two forms. Other locales can supply one shared wording. The 1,179 paired
lines below each had both recordings in every dub. The production record
builder reproduced all 1,179 for each of the five study locales. Dub selection,
text identity and missing-recording states remain separate for each performance.
[Mission with both Endministrator performances](https://warfarin.wiki/en/missions/c37m3)
· [Radio source table](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/RadioTable.json)

| Authored rows | Total | Direct WEM, four dubs | Paired performances, four dubs | Direct WEM, partial dubs | Nonempty override without a WEM | Blank override |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Conversations | 24,581 | 14,615 | 893 | 4 | 8,911 | 158 |
| Radio | 5,714 | 4,537 | 286 | 0 | 885 | 6 |
| Narration | 273 | 2 | 0 | 0 | 244 | 27 |

The 8,911 unmatched conversation overrides comprise 8,655 `au_dlg`, 165
`au_sim`, two `au_sr` and 89 literal `0` values. All 89 have an empty actor
ID. All 885 unmatched radio overrides use `au_radio`. Two of those rows
separately trigger identified Wwise signal effects. All 244 narration
overrides use `au_black` and have a TextTable entry. None of these unmatched
overrides has a corresponding AudioDialog ID, a file stem in any of the four
publisher lip-sync indexes, or a matching event ID among the 25,105 inspected
Wwise events. These rows have no published per-row silence or recording-duration
field in the inspected narrative tables. Their voice classification remains
unavailable pending scene-level evidence. [Dialogue text schema](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/DialogTextTable.json)
· [Narration bindings](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/TextVoIdTable.json)

### Mission radio playback, November 9, 2026

Following the game's `PlayRadio` mission references led to 380 radio groups.
In the 89 groups without verified line recordings, all 134 rows lack a
resolved line override. None has a separate audio event. Of the 134,
131 specify an emotion present in EmotionVoiceConfig; three specify type 0,
which has no entry in that table. The controller tries the override's voice
duration first. If that fails, it uses the real actor, emotion type, the
row ID's hash and the last reaction when selecting a common interjection.
After successful playback it skips the next fallback opportunity. Interrupts
and resumes also affect playback. The visible sentence and a possible
interjection have different identities. These 134 sentences remain unavailable
as exact recordings. The toolkit can use the preceding row to identify short
radio lines that already have their own original recording.
[Radio controller](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L880-L956)
· [Emotion configuration](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/EmotionVoiceConfig.json)

### Scenes, summaries and films

- The scene registry lists 3,106 scenes. 526 reference 533 distinct timelines.
  The publisher's group 19 contains 566 mission definitions and 566 companion
  metadata files. Explicit mission fields link 198 missions to 552 registry
  scenes, 169 missions to 380 radio groups and 130 missions to 134 SNS groups.
  Of the 380 linked radio groups, 291 have every referenced line indexed in all
  four dubs. The other 89 contain at least one unresolved line. Missions can
  also trigger scenes indirectly through level scripts and timeline actions.
  The remaining 2,554 registry scenes have no direct dialogue field in this
  mission census. A count of complete chapters requires those indirect links
  and the scene-to-line bindings. [Scene registry](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/Json/GameplayConfig/DialogIdTable.json)
  · [Mission definitions](https://github.com/rmxlinux/EndfieldData/tree/d847759f71d4549aba4727b3b0ac1a1ad0e37742/Json/MissionRuntimeAsset)
- The game's skip dialog displays a scene-linked summary in a text widget.
  1,274 summary references led to 1,270 existing entries. Two had no localized
  text, leaving 1,268 summaries with English and Chinese. The toolkit captures
  linked, localized summaries through the existing unvoiced-text option. Four
  missing table entries remain visible as a preparation warning. The audit
  excluded the 66 additional table entries without a scene-map link.
  [Scene-to-summary table](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/TableCfg/DialogSummaryMapTable.json)
  · [Summary widget](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/UI/Panels/DialogSkipPopUp/DialogSkipPopUpCtrl.lua)
- Publisher group 13 lists 710 USM containers, including 113 narrative
  cutscenes and 10 remote-communication videos. The CRID stream directory of
  each of these 123 narrative files contains exactly one video stream
  (`@SFV`, channel 0). All 123 therefore require an external binding for
  caption timing or voice. The game UI binds its timeline subtitle panels and
  video nodes separately. The 562 guide and 25 UI videos were outside the
  narrative header audit. [Timeline controller](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/UI/Panels/DialogTimeline/DialogTimelineCtrl.lua)

### External cinematic voices

The Global 1.6.4 film configuration supplies a default playable and a map
of localized subtitle tracks. Following the configured Unity object IDs and
the matching film/locale playable names joined 238 tracks across 80 film
configurations and 244 playable roots. These tracks contained 1,718 timed
caption occurrences. Fifteen Korean configuration pointers use the playable
suffix `_others_au_kr`; the rest of the matched Korean roots use
`_others_au_ko`. Accepting both names for the configured Korean object
resolved 65 additional Korean intervals against the Korean speech packages.
The Korean `cs_video_e0m2_6` opening caption exports 7.450–13.217 seconds
from its recording. The MP3 correlated 0.99928 with the original interval.

The audit found 1,636 distinct film/caption/dub combinations with text and
a localized event linked to a single zero-delay recording. There were 394
Mandarin, 415 English, 413 Japanese and 414 Korean candidates. Of these,
373 film/caption pairs in 48 films (216 subtitle IDs) had media in every dub.
The importer then verified each caption's time against its own decoded audio.
For example, the Korean subtitle in `m_cs_video_e3m5_4` ends at 74.407 seconds
and its sole speech recording ends at 74.400 seconds. The 48 kHz recording
has 3,571,200 frames. The exported 1.841-second Korean MP3 covers the final
recorded interval and correlated 0.99806 with the decoded original.

A November 9 recheck counted 431 distinct film/caption pairs in 49 films
with at least one playable occurrence. Of these, 333 pairs have a playable
occurrence in all four dubs. The desktop reader now also follows immediate
predecessors in the localized timeline. In each dub and both protagonist
versions of `cs_video_e3m5_3` it can identify the first of several identical
captions after the preceding distinct subtitle. The later identical occurrences
still require an independent scene-position observation. Ten other intervals
have a shared edge smaller than one millisecond. Both neighboring clips omit
the shared samples. Overlaps containing uncertain speech remain unresolved.

| Original voice | Films with accepted intervals | Verified playable intervals |
| --- | ---: | ---: |
| Mandarin | 49 | 390 |
| English | 48 | 394 |
| Japanese | 46 | 407 |
| Korean | 48 | 382 |

Short or repeated desktop captions can use a stable preceding observation in
the same radio sequence or localized film. Matching checks the selected
performance and exact current text. The standalone phone library omits
occurrences that require an observed predecessor.

The 80 film configurations also include tracks without a matching subtitle
and voice. In both versions of `cs_video_e9m3_2` the English subtitle begins
after the identified speech event ends. The eleven Mandarin caption IDs for
`fmv_e0m1_1` have no matching entry in the reviewed TextTable. Neither case
can supply a verified translated recording. A film with no accepted interval
can still contain speech.

For `f_cs_video_e7m4_2`, each localized track contained 18 subtitle cues.
Music, sound effects and speech had separate tracks. Its speech event
`au_vo_csv_e7m4_2_f` starts at 0.050 seconds. Following its bank graph
in each language produced one zero-delay WEM. The four complete WEMs
retrieved from the publisher decoded to 134.2036 seconds each.
For example, cue `cutscene_e7m4_2_07` starts/ends at 23.033/25.133 seconds
in Mandarin, 22.866/25.866 in English, 23.150/25.233 in Japanese and
22.850/25.017 in Korean. Each selected interval contained decoded audio after
subtracting the speech track's 0.050-second start. [Publisher release resources](https://launcher.gryphline.com/api/game/get_latest_resources?appcode=YDUTE5gscDZ229CW&game_version=1.6&version=1.6.4&platform=Windows&rand_str=O0xruPqxQxZ9aEYl)

### Desktop playback without an installation

The timeline importer reproduced the localized film/caption pairs from the serialized
Unity assets. The release profile contains package coordinates, digests,
identifiers and millisecond intervals. The selected text comes from the matching
revision of the localization tables. Normal preparation fetches three verified
package headers for the chosen dub. Playback reads the exact WEM by HTTP range.
A film's speech recording must match its SHA-256 digest before entering the
private cache. Each caption uses its own dub-specific interval.

With no game folder, the language worker produced 25,971 voiced records in English,
25,984 in Japanese, 25,960 in Korean and 25,966 for each Chinese script. Each
count includes the verified film cues available in that dub. The playback service exported a conversation and
a timed MP3 for each of the five study selections. All 1,573 cinematic
intervals passed bounds and nonzero PCM checks against 184 distinct localized
speech recordings retrieved through the publisher adapter. A sample MP3 in each dub matched the original
PCM interval with normalized correlation above 0.998. Cinematic OCR uses
full-frame, exact text matching and the configured Endministrator performance.
Live screen capture during each film has not been verified.

## Earlier installed-client audit

2026-10-30 runtime addendum: the normal VFS/PCK path now uses the built-in Python
reader without SDK compilation. The authored-language join reproduces the
coverage counts below; initial/hotfix clips match the legacy bridge exactly.
See [archive runtime evidence](../endfield-runtime.md). Presentation support and
absent-pack playback claims remain as documented here.

Audited and rechecked 2026-10-27. Coverage is **partial**, with explicit per-record
voice status and aggregate preparation warnings. The Chinese pack and production
clip decoding are now verified; native gameplay/OCR acceptance is still incomplete.

## Evidence and provenance

The installed VFS was inspected read-only through the existing pinned
[EndfieldStudio reader](https://github.com/EIHRTeam/EndfieldStudio). The audit
initially enumerated 361,098 entries across base and persistent indexes, including 770
installed table assets and 687 video assets. Selected SparkBuffer tables and UI
Lua were decoded into ignored local evidence. Duplicate base/hotfix references
are included in the inventory count; this is not a count of unique stories.

The runtime metadata source is the **third-party**
[rmxlinux/EndfieldData mirror](https://github.com/rmxlinux/EndfieldData), revision
`a0ed1dac31c502f636c70cee4e3010ca69562a70`, titled `Update 10/22`. Its README
describes manual updates and Endfield 1.6 support. It is not a publisher API.
The installed DialogTextTable, RadioTable, DialogOptionTable, Dialog2DTextTable,
RichContentTable and CharacterTable match that snapshot exactly. AudioDialog
has 18 differing metadata rows after the voice-pack recheck, but all 33,273 resolved source paths match.
One SNS group, 11 TextTable rows and parts of the English localization differ;
the runtime therefore warns that the mirror can lag the installed game.

Publisher evidence independently establishes the presentation families:

- The [March update notes](https://endfield.gryphline.com/en-us/news/8907)
  describe main, side and exploration missions, operator-switch voice lines,
  database entries, clue dossiers and changes to story cutscenes.
- The [June update notes](https://endfield.gryphline.com/en-us/news/0758)
  identify narrative events, NPC voice improvements and Baker messages.
- The official [Against the Tide cutscene](https://www.youtube.com/watch?v=OYv6yJUgTQk)
  and [The Bloodening cutscene](https://www.youtube.com/watch?v=7o_9-z1_XzU)
  establish cinematic presentation. They are not audio-binding sources.
- The publisher's [The Promise comic](https://endfield.gryphline.com/en-us/news/0753)
  establishes external comic publication. It does not prove that those web
  pages are installed in the client. In-client two-dimensional panels and
  document artwork were established separately from local files.

No game dialogue, media, extracted tables, credentials, account state or personal
paths are included in this document or committed fixtures.

## Presentation inventory and implementation

Counts in the last column are nonempty English records from the audited mirror.
They include authored but potentially locked/unreleased content; they are not
counts of scenes observed during play. Blank localization/sentinel entries are
excluded. Main/side/event/NPC coverage shares tables; no per-mission completeness
claim is made.

| Presentation | Installed evidence and binding | Result / English records |
| --- | --- | --- |
| Main, side, event and NPC conversations | 24,081 DialogTextTable rows; text ID → audioOverride → AudioDialog → selected-locale external hash | 23,100 conversation records. Missing paths or recordings remain unavailable; blank overrides remain unknown. |
| Radio, ambient and field speech | 3,336 RadioTable groups containing 5,613 rows; explicit radioText/audioOverride/audioEvent | 5,516 records; dialogue and gameplay channels. Generic unresolved events do not become silent. |
| Narration and black-screen/cinematic text | 269 TextVoIdTable references into TextTable | 269 narration records; cinematic and dialogue channels. This does not cover entire movie soundtracks. |
| Choices | 5,707 DialogOptionTable rows | 5,462 text-only choice records. Choosing a line is distinct from a later voiced response. |
| Two-dimensional story panels | 34 Dialog2DTextTable rows; installed Dialog2DCtrl renders narrative body separately from spoken DialogTextTable text and selected options | 34 text-only story-panel records on the cinematic channel. Image-only text is not inferred. |
| Baker messages | 377 SNSDialogTable groups; installed SNSContentText and SNSContentVoice render separate text and voice widgets | 5,463 text messages, 2 voice-message transcripts. Voice events require exact source bindings; 239 media/system/unsupported cells are explicitly excluded. |
| Baker choices and topic starters | SNSDialogOptionTable and SNSDialogTopicTable | 1,598 text-only message-choice records. No friend/account chat is queried. |
| Narrative documents, clues and terminal readings | 783 RichContentTable entries / 4,397 paragraphs; installed RichContent, ReadingCtrl and ReadingPopUp controllers separate text, artwork and radio | 4,166 readable paragraphs; 140 image-marked paragraphs excluded. Popup/PRTS references are checked, with 9 unresolved bodies reported. |
| Narrative terminology notes | 38 NarrativeNoteEntryTable rows | 38 text-only note descriptions. |
| Operator archive and voice viewer | CharacterTable has 35 operators, 2,698 profileVoice rows and 198 profileRecord rows; installed CharInfoProfileCtrl separately renders recordDesc and plays voId with voiceDesc | 2,698 authored voice descriptions and 198 text-only records. Every profile voId resolves to an AudioDialog path in this snapshot. |
| Combat barks | 1,250 AIBarkText keys are exact AudioDialog voice IDs; installed AIBarkCtrl uses that ID for subtitle lookup and playback stop | 1,250 gameplay records, all bound to installed Chinese recordings. No guessed trigger/voice join. |
| Pre-rendered cinematics, movies, media cards | Global 1.6.4 localized FMV timelines and speech-bank bindings | Desktop preparation imports 431 distinct film/caption pairs. Of these, 333 have verified clocks in all four dubs. Other video or media-card presentations still require verified bindings. |
| Comics, storyboards and illustrated documents | Local two-dimensional narrative UI plus RichContent image rendering; publisher comic pages separately | Authored text fields covered as above; embedded artwork text, video captions and image-only bubbles remain gaps. |

Reading references provide a second coverage check: ReadingPopUpTable resolves
745 entries to rich content and 31 to radio, with one unresolved; PrtsReading
resolves 28 entries to rich content with eight unresolved; all 80 PrtsDocument
entries resolve to rich content. InstructionBook/tutorial text, inventory stats,
generic UI strings and friend chat are outside narrative capture.

## Installed audio and language result

At the initial audit, the install had no selected-language audio VFS groups. Both base and
persistent initial-audio inventories expose the same 56 entries. An additional
bounded header inspection of four main stream packages found 59,932 SFX entries,
all 32-bit IDs, and **zero** authored voice-hash matches across all five study
locales. The audit-stream prefix could not be parsed by this bounded probe; no
claim is made about its full contents. The adapter continues to use the existing
selected-language/initial/hotfix inventory rather than treating SFX as voices.

That original no-pack result is historical. The newly installed Chinese package
and the current mapping results are described below. No game/account settings
were changed by the audit.

Using independently decoded installed localization tables validates the same
typed joins for all study languages: English 49,794; Simplified Chinese 51,049;
Traditional Chinese 49,773; Japanese 49,794; Korean 49,773. These counts prove
text joins, not playback. Locale routing and exact authored voice bindings are
also covered with synthetic entries for every supported study locale.

The current [publisher Steam language table](https://store.steampowered.com/app/4732690/Arknights_Endfield/)
and [Gryphline's voice-language announcement](https://endfield.gryphline.com/en-us/news/0767)
identify four voiced languages: Mandarin Chinese, English, Japanese and Korean.
All four are implemented and exposed; Traditional Chinese text shares Mandarin
audio. English/Japanese/Korean compatibility uses the common installed schema,
explicit reader locale branches and synthetic hash/extraction/preparation tests.
Their absent packs were not natively decoded. The full capability-versus-proof
matrix is in [Endfield language preparation](../endfield-languages.md#voice-language-support-and-verification).

## Later installed voice-pack verification

A second read-only check on October 27 observed a changed installation
fingerprint and a newly reachable Chinese audio group. The current reader found
35,067 entries in the selected Chinese group, alongside initial/hotfix entries.
English, Japanese and Korean groups remained absent. These are inventory entries,
which can include repeated base/hotfix references, not unique dialogue totals.

The initial recheck resolved 21,389 Chinese voice records and decoded a
conversation through the production service. The subsequent mapping audit
independently decoded the installed AudioDialog and AIBarkText tables. All 1,250
bark text keys are exact audio-table keys; AIBarkCtrl resolves `barkTextId` and
uses the corresponding `voId` for playback-stop handling. Every one of those
1,250 selected-locale source hashes exists in the downloaded Chinese package.
The adapter now uses this primary-key join, separately from filename stems.

Current Simplified Chinese preparation contains **51,049 records**:

| Voice classification | Records | Evidence |
| --- | ---: | --- |
| Bound original voices | 22,639 | Exact authored source hashes in installed Chinese audio, including all 1,250 combat barks |
| Verified text-only | 17,196 | Separate authored text-only presentations |
| Missing source metadata | 11,025 | 9,637 conversations, 1,146 radio lines, 240 narration references and two SNS audio events have no usable AudioDialog source |
| Missing locale recording | 4 | Known AudioDialog paths absent from Chinese inventory; each has zero Chinese duration and a nonzero duration in another locale |
| Unknown | 185 | 158 blank conversation overrides and 27 blank narration voice references |

The four missing Chinese recordings remain unavailable; other locales are never
substituted. The 11,025 unresolved metadata references have no case-only filename
alias, and the installed VoiceIdConflictTable is empty. There is no proven
additional mapping for them. Neither group is relabeled silent. Diagnostics now
distinguish these cases, so missing metadata does not tell users to reinstall
voice packs. Absence of a full selected-language package still has its own warning.

Three newly mapped barks, covering male Endministrator, female Endministrator
and another operator, were extracted through `LocalVoiceAssetService`, decoded
and encoded through the production pipeline, then independently decoded back to
PCM. All were non-silent: 1.331–1.721 seconds, 14,084–24,380 MP3 bytes, and PCM
peaks 13,147–14,797. This verifies exact clip access and decoding, not physical
gameplay/crop behavior. The index join took 3.699 seconds using the captured live
inventory; the three production playback probes took 18.062 seconds.

Current private evidence is under `output/checks/endfield-voice-resolve/`, with
the earlier pack/ordinary-conversation proof in
`output/checks/endfield-live-recheck/`. Raw tables, subtitle text and clips stay
ignored and are not published.

## Update resilience and validation

The October audit used language index version 3. The paired performances and
story summaries above use version 4. Additive metadata fields are tolerated. Changed
required table shapes, missing core conversation data, malformed inventory
structures and changed localization structures return `unsupported_game_format`
with an actionable toolkit-update message. Missing optional categories produce
coverage warnings. Unknown SNS types are excluded and counted. The archive
fingerprint covers both VFS layers, case-insensitively; a concurrent game update
fails preparation while leaving the previous snapshot untouched.

The adapter never infers silence from a missing recording or an empty override.
Only verified text-only modalities receive `unvoiced`; generic events and
authored but missing recordings receive `unavailable`; default/blank voice
references receive `unknown`. Ambiguous filename stems, placeholder and
unsafe source paths cannot bind recordings. Capture of text-only records remains
subject to the user's opt-in and exact-match safeguards.

Focused regression command:

```text
.venv/Scripts/python.exe -m pytest backend/tests/test_endfield_audit.py backend/tests/test_new_rpg_languages.py -k "endfield or declared_translation" -q
```

Result: **48 passed, 17 deselected in 0.68 seconds** for the completed mapping
and language-capability changes.

The focused regression cases cover voice-state evidence, exact bark IDs across
all five study locales, ambiguous filename rejection, missing-metadata versus
missing-locale diagnostics, operator bindings, media exclusion, missing reading
links, schema drift, optional-category warnings, absent-pack preparation for all
four official voice languages/both Chinese scripts, and snapshot retention.

The audit evidence and timings are retained privately under
`output/checks/endfield-audit/`, including inventory, decoded schema evidence,
bounded audio-header inventories, adapter/locale summaries and JUnit results.
No full suite or publication audit was run by this game-specific audit.

Native acceptance still requires physical gameplay observation, screenshots
across each narrative layout, desktop/mobile crop behavior, windowed/fullscreen
capture, zoom and Windows DPI bounds. Chinese package presence and production
clip extraction/decoding are verified as described above. File and playback
evidence does not establish that every presentation appears inside a capture crop.
