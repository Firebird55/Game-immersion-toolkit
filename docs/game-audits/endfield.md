# Arknights: Endfield presentation audit

## Selecting the publisher edition

With the game folder empty, Windows Setup offers Global and Mainland China.
Each uses its own launcher, app ID, channel, resource manifests and CDN. The
edition applies to all study languages. A switch schedules the previously
prepared languages for refresh. Saved voice references continue to read from
their original release and edition. The radio and whole-film commands accept
`--region global` or `--region cn`.

On November 13, 2026, both official launchers returned Windows 1.6.4 and
initial/main resource revision `11529267-11` under separate regional URLs.
A clean mainland preparation returned 53,711 English rows, including 25,985
voiced rows and 408 timed clips. One conversation WEM decoded to 2.644 s.
The selected timed film clip resolved its original 77.014 s source recording.
The 28 open film configurations and the two unresolved radio observations
are tracked below. [Global launcher](https://launcher.gryphline.com/api/game/get_latest?appcode=YDUTE5gscDZ229CW&launcher_appcode=TiaytKBUIEdoEwRT&channel=6&sub_channel=6&launcher_sub_channel=6&disk_type=0&patch_encrypt=1) · [Mainland launcher](https://launcher.hypergryph.com/api/game/get_latest?appcode=6LL0KJuqHBVz33WK&launcher_appcode=abYeZZ16BPluCFyT&channel=1&sub_channel=1&launcher_sub_channel=1&disk_type=0&patch_encrypt=1)

## Installation-free publisher updates, November 9, 2026

The [inventory of the 28 unresolved films](endfield-film-configs-1.6.4.csv) distinguishes a
movie's screen time from each spoken interval. Of the 28 movie configurations
without a verified sentence interval, 25 have no authored caption (one is
null). The other three contain 11, 14 and 21 Chinese subtitle clocks. The
[46 historical intervals](endfield-legacy-film-clocks-1.6.4.csv) match the
2023 technical test. None of their keys occurs in any of the 14 current
translations. Eighteen of the 28 have a matching video. Ten have a directly
resolvable whole voice track and two more have a voice track in their caller.

The Global `VideoData.asset` lists 106 video names and durations, including
seven of the older `fmv_` identities. Its durations for `fmv_e0m1_1`,
`fmv_e0m1_3` and `fmv_e0m1_4` are 89.300, 145.000 and 148.960 seconds.
All 46 caption intervals fit those durations. The Technical Test table links
each caption ID to Chinese source text. Its five separate localization files
are empty. A fresh byte-range check of the 18 matching Global USMs read the
first 4 KiB of each container. Each CRID directory lists a single `@SFV`
video stream on channel zero. Sentence audio and subtitle timing for these
movies require an external source.
[Archived Technical Test subtitles](https://github.com/lsy-404/EndfieldGameData/blob/89ba7929f7fa64579852326b2bed0e679c3ccf49/TableCfg/SubtitleTable.json)
· [Archived localization files](https://github.com/lsy-404/EndfieldGameData/tree/89ba7929f7fa64579852326b2bed0e679c3ccf49/TableCfg)
· [Global publisher resources](https://launcher.gryphline.com/api/game/get_latest_resources?appcode=YDUTE5gscDZ229CW&game_version=1.6&version=1.6.4&platform=Windows&rand_str=O0xruPqxQxZ9aEYl)

Publisher group 19 contains 5,561 level scripts and 28 string-pool shards.
Resolving the 277,949 pool entries exposed eight movie names in the first
constant argument of the same serialized action (`0x0372`, 14 members).
Three names match a single configuration exactly. Five are shared base names
of the female and male movie configurations. The inventory gives each script
ID, argument and byte offset. For example, script `2100060031` contains
`cs_video_dlg_e1m2_1` at offset 107. These fields establish a game reference.
They contain no dialogue timecodes. The separate Unity actor-track callers
and their movie windows appear in the same inventory.

Two current strings bearing the movie name `cs_video_e0m0_3` actually play
in the in-engine scene `cutscene_e0m0_5`. Both hero variants use the following
localized subtitle intervals, in seconds from the start of their respective
performance. The original sound was checked for each of the 16 combinations.

| Dub | First sentence | Second sentence |
| --- | ---: | ---: |
| Mandarin | 11.900–13.817 | 14.883–16.767 |
| English | 12.000–14.233 | 14.233–17.050 |
| Japanese | 11.667–14.367 | 14.367–17.050 |
| Korean | 12.050–14.400 | 14.400–17.067 |

The publisher clocks describe how long the text is shown. Within those
windows, the English PCM crosses the activity threshold at 12.040–14.230 s
for the first line in both performances. For the second line it crosses at
14.253–16.263 s (female) and 14.243–16.513 s (male). These are acoustic
measurements on the identified lines. A quiet consonant or reverb can move a
threshold boundary relative to the words.

These bring verified localized intervals to 1,629, comprising 1,613 movie
intervals across 52 of 80 configurations and 16 in-engine intervals. Setup
and MP3 export were exercised for all five study languages, including both
Chinese scripts. Revalidation also selected the two scenes and their original
audio on the earlier Global 1.6.4 resource revision `11343132-9`.

Setup follows the released Global Windows launcher version and both resource
indexes. It reads original SparkBuffer localization and narrative tables from
group 18 and resolves the authored voice in the initial, selected-dub and hotfix
packages of that generation. Per-file hashes protect the original tables. An
update to either resource index creates a new generation. Previously downloaded
recordings retain their generation and dub. The earlier mirror comparison below
provides an independent reference for this reader.

The same worker was exercised with the archived Global 1.5.3 resource selection
and the current 1.6.4 release. It retrieved all table and speech bytes used for
these builds from GRYPHLINE. The earlier build produced 22,497 English voice
records and exported the opening conversation. The current build produced
25,981 English voice records including 404 timed film clips. In all five study
selections, the desktop service recreated both an ordinary line and a trimmed
film MP3 offline after deletion of the encoded outputs. The audited film profile
requires matching resource evidence. Unknown clocks remain unavailable.
[Publisher launcher](https://launcher.gryphline.com/api/game/get_latest?appcode=YDUTE5gscDZ229CW&launcher_appcode=TiaytKBUIEdoEwRT&channel=6&sub_channel=6&launcher_sub_channel=6&disk_type=0&patch_encrypt=1)
· [Historical resource listings](https://github.com/daydreamer-json/ak-endfield-api-archive/tree/538b29bee72a7bc42a30966d1e39a98a6c621a90/output/raw/beyond.hg-cdn.com/YDUTE5gscDZ229CW/1.5/resource/Windows)

Global revisions `11343132-9` and `11529267-11` have different release
indexes. In both releases the current Unity registry selected identical film
configurations and localized subtitle bundles for 53 Mandarin, 52 English,
50 Japanese and 52 Korean performances. The selected dub bank, hotfix packages
and 200 original speech files also matched. English preparation retained all
404 film intervals on the earlier revision. When a required asset changes,
the toolkit omits the affected film until its new timing or voice binding can
be verified. Other dialogue still follows the current release's own tables.

For the two in-engine scenes, the desktop reader checks the active subtitle
configuration, director prefabs, master timeline, regional subtitle track,
audio track, Wwise event and recording. A repacked bank can pass if its event
still selects the verified recording. Reading newly authored or retimed
subtitle clips requires decoding the Endfield bundle wrapper and Unity
serialized objects in the distributed runtime. The current timeline importer
reads these objects during an audit. Setup omits a changed clock until its
caption, regional recording and interval have been verified.

## Publisher resources and story coverage, November 8, 2026

The Global Windows 1.6.4 updater returned resource revision `11529267-11`. Follow
the released regional launcher into `get_latest_resources`, then the main and
initial resource URLs. Their `index_main.json` and `index_initial.json` identify
the VFS group indexes and chunk checksums. The audit checked the selected group
indexes against their published MD5 values and read only the listed byte ranges.
The November 8 worker used the matching community text snapshot and obtained
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
131 specify an emotion present in EmotionVoiceConfig. One of those entries
has both an empty interjection and an empty list. Three rows specify type 0,
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

The [per-line inventory](endfield-mission-radio-1.6.4.csv) lists **every row**
in those 89 groups. The other 291 mission groups supply 509 direct sentence
bindings and 35 rows with separate protagonist performances. Among the 134
unresolved rows, 77 have a named-actor interjection in all four publisher
dub indexes. The publisher's NpcInfoTable maps another 44 NPCs' lines to
their performer through `voActor`. For example, `yingge` uses
`lady_30_01` and `jite` uses `man_30_13`. Across **121 rows**, 50 have one
four-dub candidate and 71 have several. Nine have configured interjections
but no verified actor recording. Runtime actor selection and skip state can
affect playback. The four rows without a configured interjection are
`radio_e10m1_11_001`, `radio_e10m1_11_002`, `radio_m1m6_1_001` and
`radio_gm02m27d5_1_001`. The last uses emotion type 13 with empty values.
No row in this inventory had a separate audio event.
None is marked confirmed silent in capture.

For Chen's `radio_f1m29d1_4_002`, the named neutral reaction decoded to
0.831 seconds in English, 1.415 in Japanese, 1.065 in Korean and 1.022 in
Mandarin. Playback of that candidate at a specific in-game occurrence depends
on controller state. A separate empty-cache check downloaded the original
English sentence for `radio_e12m5_2_001` and decoded 5.241 seconds.

[Playback checks for the thirteen unresolved rows](endfield-radio-observations.md) identify the exact mission triggers and distinguish ambient or combat sounds from attributed character speech. The observations are separate from the live source used by the toolkit.

The [radio command](../../scripts/endfield_radio.py) and desktop preparation
use the current publisher RadioTable, AudioDialog, NpcInfoTable, EmotionVoiceConfig and
selected dub index. To list a group, run the following from the source checkout.

```text
python scripts/endfield_radio.py --cache private-cache --locale en --group radio_e12m5_2
```

Add `--line endfield:radio_e12m5_2_001 --target zh-Hans --wem sentence.wem`
to export its original audio and report the selected translations. A group
with an unresolved override still appears in the inventory. For an explicitly
requested candidate, use its own listed name with `--reaction`, `--line`
and `--wem`. The command checks the release again before writing the output.

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

A second pass recovered three further configurations. The English caption in
both versions of `cs_video_e9m3_2` begins at 57.279 seconds. The authored event
sets `_stopEventAtClipEnd` to zero and has no exit event. Speech continues past
the timeline block's end at 56.933 seconds in the 60.184-second recording.
In `cs_video_e11m1_2`, the Common group carries the four shared captions.
The other groups reference separate `CheckNarrativeGender` assets that select
the female or male event. Both conditions and all 16 localized recordings for
these three configurations were checked. This adds ten performances per dub.
The resulting 437 distinct film/caption pairs span 52 of the 80 configurations.
339 pairs have intervals in all four dubs. Counting each protagonist's
performance separately gives 441 pairs and 1,613 localized intervals.

| Original voice | Films with accepted intervals | Verified playable intervals |
| --- | ---: | ---: |
| Mandarin | 52 | 400 |
| English | 51 | 404 |
| Japanese | 49 | 417 |
| Korean | 51 | 392 |

Short or repeated desktop captions can use a stable preceding observation in
the same radio sequence or localized film. Matching checks the selected
performance and exact current text. A confirmed caption can then identify
its own successor. Repeated observations of identical text retain the same
occurrence until a distinct subtitle provides evidence of a transition.
The standalone phone library omits
occurrences that require an observed predecessor.

The 80 film configurations also include tracks without a matching subtitle
and voice. The eleven Mandarin caption IDs for
`fmv_e0m1_1` have no matching entry in the reviewed TextTable. Neither case
can supply a verified translated recording. A film with no accepted interval
can still contain speech.

The [inventory of the other 28 configurations](endfield-film-configs-1.6.4.csv)
records the default pointer, timed captions, current TextTable matches, voice
event and presence of a same-name video in publisher group 13. Eighteen have
a same-name video. One configuration has a null playable pointer. The three
`fmv_e0m1` tracks have 11, 14 and 21 timed captions respectively, all absent
from the released TextTable. Inspection of 90 candidate scene prefabs and
audio/other tracks also found separate in-engine events such as
`au_vo_cs_e2m8_1_f`. Similar scene names do not establish a film clock.

**Ten configurations now have downloadable whole-event voices.** The two
`c35m4_liinoshow` films share one event. The female and male variants of
`e12m5_3`, `e12m5_4`, `e2m8_2` and `e6m1_1` each select their own event.
All nine event identities resolved to single localized media and decoded
with nonzero PCM in Mandarin, English, Japanese and Korean. These 36
performances are separate from the 1,613 timed intervals. No new subtitle
interval is established by the whole-track result.

The [film voice command](../../scripts/endfield_film_voice.py) looks up the
given event in the active release's initial, selected-dub and hotfix package
indexes, requires a unique in-dub single-source playback definition and
downloads the selected original WEM. For example, the following command
retrieved the Japanese performance from an empty cache.

```text
python scripts/endfield_film_voice.py au_vo_csv_e12m5_4_f --locale ja --cache private-cache --wem film-ja.wem
```

The same reader retrieved `au_vo_csv_e2m8_2_f` and `au_vo_csv_e6m1_1_m`
from both Global 1.5.3 and 1.6.4 in English. It also follows the
`hotfix_<language>_bNN.pck` shards in the older release. A new event name
requires its current authored identity. Subtitle capture still requires
an independently verified clock for the individual line.

### Measurements of the 44 whole-event performances

For the nine direct movie events and two parent events, the audit measured
all four dubs from the separately downloaded voice recordings. The 44 rows
give the original WEM checksum, duration and every detected activity region
in recording-relative milliseconds. They cover 546 regions, including 145
English regions. This measures signal level. Assigning a subtitle or speaker
requires additional evidence. [Recording activity table](endfield-film-recording-activity-1.6.4.csv)

- The two Liino variants use the same song event. The English game edit has
  one sustained region at 3.230–90.840 s. The publisher also released the song
  in English, Japanese, Mandarin and Korean. [English EP](https://www.youtube.com/watch?v=B8bFWp5TkUw)
  · [Japanese EP](https://www.youtube.com/watch?v=uDbAt39Sb7E)
  · [Mandarin EP](https://www.youtube.com/watch?v=rnd3MwKvFY4)
  · [Korean EP](https://www.youtube.com/watch?v=QfLBLqgLsz8)
- For `e12m5_4` the English female track contains a single region at
  26.770–27.330 s and the male track at 26.770–27.160 s. An independent
  audio-event classifier tagged both as a sigh. Other short regions in
  `e2m8_2` and `e6m1_1` received breath, gasp and speech labels.
  The reviewed game tables provide no caption ID for a sentence in these
  films. These classifications are machine observations. [Audio tagging model](https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/audio-tagging/pretrained_models.rst)
- In `e12m5_3` the English signal at 75.850–77.650 s (female) and
  75.850–77.320 s (male) was classified as speech. Running recognition on the
  isolated regional clips gave inconsistent results across dubs. The current
  TextTable has no matching film-caption IDs. Both English intervals remain
  available for listening in the whole event, with the wording unresolved.
- For the English `e0m0_3` parent events, each recording has seven regions.
  Four start inside the 0.000–59.750 s movie window and three start after it.
  A parent recording can contribute audible material beyond the end of its
  movie. Matching those later sounds to an on-screen movie sentence requires
  a separate source.

To reproduce a row, fetch its event with `endfield_film_voice.py`, compare the
reported SHA-256, decode it with `vgmstream-cli -o event.wav event.wem` and
run `python scripts/endfield_film_activity.py event.wav`. The measure uses the
loudest channel's RMS per 10 ms window at −48 dBFS. It joins gaps of up to
250 ms and keeps regions of at least 70 ms. The optional `--start-ms` and
`--end-ms` restrict the measurement to an authored subtitle window.
[Activity reader](../../scripts/endfield_film_activity.py)

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

With no game folder, the language worker produced 25,981 voiced records in English,
25,994 in Japanese, 25,970 in Korean and 25,976 for each Chinese script. Each
count includes the verified film cues available in that dub. The playback service exported a conversation and
a timed MP3 for each of the five study selections. All 1,613 cinematic
intervals passed bounds and nonzero PCM checks against 200 distinct localized
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
| Pre-rendered cinematics, movies, media cards | Global 1.6.4 localized FMV timelines and speech-bank bindings | Desktop preparation imports 437 distinct film/caption pairs across 52 of 80 film configurations. Of these, 339 have verified clocks in all four dubs. Other video or media-card presentations still require verified bindings. |
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
