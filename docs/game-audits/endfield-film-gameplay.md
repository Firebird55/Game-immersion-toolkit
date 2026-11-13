# Endfield cinematic gameplay checks

The English 1.6.4 quest text identifies `e12m5` as **Paint with Fresh Ink**
and `c35m4` as **Brightest Star Above**. The original voice events and the
video timestamps use different clocks. The offsets below come from comparing
the actual publisher recordings with the English gameplay mix. They should
be used to review the footage. They are specific to the linked uploads.
[Publisher Windows release](https://launcher.gryphline.com/api/game/get_latest_resources?appcode=YDUTE5gscDZ229CW&game_version=1.6&version=1.6.4&platform=Windows&rand_str=O0xruPqxQxZ9aEYl) ·
[Released film IDs and quest triggers](endfield-film-configs-1.6.4.csv) ·
[Released dub recordings and activity intervals](endfield-film-recording-activity-1.6.4.csv)

| Quest and event | English publisher clock | Gameplay clock | Visible caption evidence |
| --- | --- | --- | --- |
| Brightest Star Above, `au_vo_csv_c35m4_liinoshow` | Song activity 3.230–90.840 s | [3:13.58–4:41.19](https://www.youtube.com/watch?v=OXL-sPrANQw&t=193s) | Liino performs onstage. Samples seven seconds apart throughout the act show stage artwork, including the performer's name, without lyric subtitles. A speaker label and dialogue reappear after the performance. |
| Paint with Fresh Ink, `au_vo_csv_e12m5_3_m` | Previously speech-tagged region 75.850–77.320 s | [1:10.72–1:12.19](https://www.youtube.com/watch?v=gN9SJP5rJyw&t=70s) | Si and the male Endministrator sit at a table. Full frames sampled every 0.25 s around the sound show no subtitle. Its spoken wording is unresolved. |
| Paint with Fresh Ink, `au_vo_csv_e12m5_4_m` | Isolated breath-like sound 26.770–27.160 s | [6:41.32–6:41.71](https://www.youtube.com/watch?v=gN9SJP5rJyw&t=401s) | The unmasked male Endministrator is shown in close-up. The full-frame sequence sampled every 0.25 s around the sound has no subtitle. The earlier classifier labelled this isolated sound a sigh. |

## Checking the alignment

The comparisons used mono PCM at 4 kHz, a 180–1,640 Hz band-pass and
normalized waveform correlation. The Liino edit starts its source recording
at **3:10.354**. Four separate eight-second windows beginning at source times
8, 28, 63 and 77 seconds independently recovered the same offset, with
correlations of 0.830, 0.892, 0.800 and 0.848 respectively. The editor's
chapter marker appears at 3:12. A small offset in this video corresponds to
several seconds of silent or very quiet material at the beginning of the
publisher recording. [Gameplay chapter](https://www.youtube.com/watch?v=OXL-sPrANQw&t=192s)

The edit of `e12m5_3` begins 5.135 seconds into the publisher recording.
Separate windows of the male recording at 6.9–9.2, 29.6–31.8, 58.5–64,
75.2–78 and 79–81.6 seconds recovered the same offset. The last three
correlations were 0.697, 0.477 and 0.629. Portions of the female recording
also match shared sounds in this footage. The male-specific windows and
the on-screen protagonist identify the run. [Opening fight](https://www.youtube.com/watch?v=gN9SJP5rJyw)

For `e12m5_4`, the male voice track contains only one short active region.
The released film timeline also names `au_sfx_csv_e12m5_4`. Its original
media ID 360391605 independently yields a start at **6:14.549–6:14.551**
across five nonoverlapping windows at 1–5, 7–11, 14–18, 20–24 and 26–30
seconds. The male voice match gives 6:14.553. This independent longer track
disambiguates the short breath from superficially similar sounds elsewhere
in the gameplay mix. [Transition into the film](https://www.youtube.com/watch?v=gN9SJP5rJyw&t=374s)

A separate English playthrough matches the female `e12m5_3` recording.
Its start aligns to 5:42.598–5:42.608. Independent windows beginning at
source times 29.6, 58.5, 75.2 and 79 seconds correlate at 0.390, 0.780,
0.672 and 0.671 for the female recording, and 0.035, 0.529, 0.444 and
0.245 for the male one. The female protagonist is visible. The samples
over the painting fight and the voiced activity at 6:58.45–7:00.25 show
no readable dialogue. The uploaded video ends before the final two seconds
of the 116-second original recording. [Female fight](https://www.youtube.com/watch?v=zJ8rtHGIXsg&t=343s) · [Voice activity](https://www.youtube.com/watch?v=zJ8rtHGIXsg&t=418s)

The later `e12m5_4` transition has a single short reaction in each original
dub. Five separate windows of the original effects track locate its start
at 21:45.146 in an English female playthrough, 13:10.402 in a Japanese
female playthrough and 2:43:34.231 in a Japanese male playthrough. The
selected Japanese recordings also match independently at exactly the same
offset (0.802 and 0.867 at original seconds 26.84–27.01). The English
female comparison is weaker (0.345 for that interval), agrees with the
effects track, and the protagonist is visible. In both inspected female
clips the protagonist's face is revealed without a readable caption at
the reaction. The male Japanese comparison here is audio-only.
[English female reaction at 22:12](https://www.youtube.com/watch?v=hn35k4KVScs&t=1331s) ·
[Japanese female reaction at 13:37](https://www.youtube.com/watch?v=ZbJXvV_QG9w&t=817s) ·
[Japanese male reaction at 2:44:01](https://www.youtube.com/watch?v=WsxMqvNWq8U&t=9841s)

## A Glance of Astonishment and Cradle of the Ages

**A Glance of Astonishment (`e6m1`).** Two English playthroughs use the
female and male 104.434-second `au_vo_csv_e6m1_1` recordings. Five
one-second windows spread over each recording independently align to 3:52.576
in the female playthrough (correlations 0.710–0.993) and 3:42.700 in the male
playthrough (0.779–0.990). Shared sounds also match parts of the other
performance. The actor-specific windows distinguish the two. Half-second
subtitle-area samples and a full-frame montage showed the Wuling battle and
Zhuang Fangyi's appearance without a readable dialogue caption in the film.
The preceding Watchguard line has its own conversation ID `dlg_e6m1_1_003`.
The question “Who is she...?” first appeared in our samples around 5:42.5
(female) and 5:33 (male), after the corresponding recording had ended.
[Female playthrough](https://www.youtube.com/watch?v=98TczT1iH6w&t=232s) ·
[Male playthrough](https://www.youtube.com/watch?v=dL6HOQ4UwgA&t=222s)

**Cradle of the Ages (`e2m8`).** The English female `au_vo_csv_e2m8_2_f`
recording starts at 9:12.979 in one playthrough. Three independent one-second
windows near source times 0.9, 5.3 and 21.2 seconds recover the same offset
(correlations 0.406, 0.805 and 0.627). Its 76.774-second recording ends
at 10:29.753. Reviewing the sampled frames and reading the subtitle area
every half-second found no readable dialogue in the film. Chen Qianyu's
first dialogue about the sapling appears at approximately 10:30 and has its
own published conversation and audio override, `dlg_e2m8_4_001` and
`au_dlg_e2m8_4_001`. A second player's audio independently aligns to
10:44.674 across the same three windows. The visual subtitle check here
applies to the first playthrough. [Film](https://www.youtube.com/watch?v=QDHS296vAg8&t=552s) ·
[Following conversation](https://www.youtube.com/watch?v=QDHS296vAg8&t=630s) ·
[Second playthrough](https://www.youtube.com/watch?v=t5KmOLvr05o&t=644s)

An English male recording of the same quest aligns at **10:33.122**. Three
independent windows at source 1.0–2.7, 4.0–6.5 and 16.0–22.5 seconds
distinguish his recording from the female one. Later shared sounds match
both. The half-second samples show no dialogue caption between the start
of his recording and its end at 11:49.896. Chen's own subtitle is visible
at 11:50. A Japanese run with English screen text also shows the transition
at 11:32. Its soundtrack aligns to the female Japanese performance at
10:14.772. The image shows the female protagonist and the original
37.5–39.5 and 60–66 s windows correlate at 0.425 and 0.706 respectively.
[English male](https://www.youtube.com/watch?v=DGVNOZ6WoZo&t=633s) ·
[Chen after the film](https://www.youtube.com/watch?v=DGVNOZ6WoZo&t=710s) ·
[Japanese performance](https://www.youtube.com/watch?v=esErRcR3xqI&t=615s)

## Rally and Unite

The distressed call in `cs_video_e1m3_3` appears on a screen inside the
larger scene. Its own movie track contains no caption cues. Both protagonist
versions of the enclosing `cutscene_e1m3_2` activate separate audio and
localized subtitle tracks. The audio event `au_vo_cs_e1m3_2` selects English
recording 580671651. Four separate regions of those original audio bytes
align to the linked player's soundtrack at 39:48.990–39:48.991
(correlations 0.762–0.976). The game shows the following captions there.
The intervals are the game's caption windows relative to that recording.
[English gameplay](https://www.youtube.com/watch?v=2_oILfhbqnM&t=2401s)

| Caption suffix | What the player sees | Original recording (seconds) | Gameplay |
| --- | --- | ---: | --- |
| `03` | Comment on the incoming messages, before the movie | 12.365–15.365 | [40:01](https://www.youtube.com/watch?v=2_oILfhbqnM&t=2401s) |
| `04` | First plea for rescue | 19.848–20.997 | [40:08](https://www.youtube.com/watch?v=2_oILfhbqnM&t=2408s) |
| `04d5` | Caller identifies the fort and its attackers | 20.997–23.997 | [40:10](https://www.youtube.com/watch?v=2_oILfhbqnM&t=2410s) |
| `05` | Shouted interruption | 31.704–34.704 | [40:20](https://www.youtube.com/watch?v=2_oILfhbqnM&t=2420s) |

The toolkit sourced and exported the four English clips independently from
Global 1.5.3 and 1.6.4. The Japanese and Korean recordings also have four
resolvable captions. [Publisher scene and recording checks](endfield.md)

Two independent Mandarin playthroughs match the publisher’s original voice
track. Four excerpts per playthrough each locate its start at 29:51.126 on
YouTube and 36:45.017 on Bilibili (correlations 0.810–0.904 and 0.807–0.896).
The first plea and the report from the fort appear in that order on the screen.
The game’s Mandarin caption windows overlap for 6.23 ms. A character alignment
of the original audio puts the last syllable of the plea near 21.58 s and
the first syllable of the next sentence near 22.34 s. The first line trails
off after 21.75 s. The 22.170 s cut falls in the low-level decay before the
second speaker is audible. The exported intervals are **19.620–22.170 s**
and **22.170–24.627 s**, retaining the lead-in to the plea and the interrupted
last syllable of the report. The four authored caption intervals, both
protagonist scene routes, audio event and recording checksum identify this
performance. Changes to those inputs require fresh evidence. The reference
videos and speech model are only used for this audit.
[Mandarin call on YouTube](https://www.youtube.com/watch?v=zpdQ1uUmjBo&t=1811s) ·
[Mandarin call on Bilibili](https://www.bilibili.com/video/BV11bzpBuEBQ/?t=2225) ·
[Character alignment model](https://huggingface.co/parseh/aligner-zh/tree/920ed68179700a9380364a119744e046e04fb14d)

## Five quest films compared frame by frame

The comparisons used the selected release's video stream and an independent
playthrough. The observations below apply to the visible text in the sampled
English playthroughs. Technical numbers and interface labels also occur.

| Quest and movie | Gameplay window | Observation |
| --- | --- | --- |
| Valley Reboot, `cs_video_e1m3_1` | [8:16](https://www.youtube.com/watch?v=h2ZVpWZDrX0&t=496s), 20.950 s | Five separated image matches locate the first core landing during Valley Reboot. No readable dialogue caption appeared in the half-second subtitle-area samples. The movie name alone suggests a different mission. |
| Valley Reboot, `cs_video_dlg_e1m2_1` | [14:01](https://www.youtube.com/watch?v=h2ZVpWZDrX0&t=841s), 46.367 s | Eleven four-second excerpts of the original sound-effects recording align at 14:01.309. The sampled film shows technical labels. |
| Ready the Easterlies, `cs_video_e6m2_2` | [8:59](https://www.youtube.com/watch?v=Y23Z-lJngnQ&t=539s), 19.633 s | Five image comparisons locate the orbital drop. Lifeng comments on it after the movie. |
| Spring’s Return I, `cs_video_dlg_sm2l5m1_10` | [36:50](https://www.youtube.com/watch?v=HCn2RHZZG9g&t=2210s), 30.317 s | The film is visible even though its own subtitle configuration has an empty playable reference. Lu Lingxiang speaks before it and Chen comments afterwards. |
| Tremors of the Crashing Tide, `cs_video_dlg_e9m2_3` | [17:59](https://www.youtube.com/watch?v=6_cYhEKCGR4&t=1079s), 28.167 s | The uploaded sequence aligns with five separated original images. No readable dialogue caption appeared in the half-second subtitle-area samples. |

The [three historical opening films and the current Ereignis encounter](endfield-opening-gameplay.md)
have separate gameplay comparisons for their original versions and performances.

## Which of the 28 film configurations occur in the game?

The Global 1.6.4 Windows movie index contains 18 of the 28 names. The table
counts female and male movies separately when the game lists both. The
published subtitle and voice tracks determine which lines can be exported.
The upload clock is only a way to find the performance in a playthrough.
[All 28 configurations and their exact identifiers](endfield-film-configs-1.6.4.csv)

| Configurations | Count | Evidence for speech and availability |
| --- | ---: | --- |
| `cs_video_e1m3_3` | 1 | Four captioned lines in the enclosing scene, including three over the in-world film. See [Rally and Unite](#rally-and-unite). |
| `cs_video_e1m3_1`, `cs_video_dlg_e1m2_1`, `cs_video_e6m2_2`, `cs_video_dlg_sm2l5m1_10`, `cs_video_dlg_e9m2_3` | 5 | Five published movies matched to the [quest footage](#five-quest-films-compared-frame-by-frame). Adjacent dialogue and interface text are identified there. No independent sentence recording has been established inside these films. |
| Female and male `cs_video_e0m0_3` | 2 | Separate English original recordings and gameplay matches for each protagonist. Breath-like activity continues into the parent scene. [Ereignis encounter](endfield-opening-gameplay.md#current-english-prologue-before-the-ereignis-fight) |
| Female and male `cs_video_e12m5_3` and `cs_video_e12m5_4` | 4 | Two Si scenes with separate protagonist recordings. The inspected English footage has no readable subtitle at the short vocal activity. The later reaction also matches both Japanese performances. [Paint with Fresh Ink](#checking-the-alignment) |
| Female and male `cs_video_e2m8_2` and `cs_video_e6m1_1` | 4 | Both English performances of each movie align to gameplay. Chen’s sapling line and the Watchguard exchange have separate game records. [Both quests](#a-glance-of-astonishment-and-cradle-of-the-ages) |
| Female and male `cs_video_c35m4_liinoshow` | 2 | Both use the same Liino song event. Gameplay confirms the song and sampled frames show no lyric subtitles. [Onstage performance](https://www.youtube.com/watch?v=OXL-sPrANQw&t=193s) |
| `fmv_e0m1_1`, `fmv_e0m1_3`, `fmv_e0m1_4` | 3 | 46 retained captions are identified in the [Technical Test footage and publisher film](endfield-opening-gameplay.md#the-three-technical-test-films). Original downloadable test audio remains unverified. |
| `fmv_e1m1_1`, `fmv_e1m1_2`, `fmv_e2m8_1`, `fmv_e2m8_2` | 4 | Four original test files are catalogued. The motorcycle ambush has three separately identified timeline captions. The final boss footage includes dialogue around the movies. Current downloads for the original test files remain unverified. [Test walkthroughs](endfield-opening-gameplay.md#other-films-preserved-in-the-technical-test-catalogue) |
| Female and male `cs_video_e4m2_1`, and `cs_video_e5m2_3` | 3 | The retained tracks reference music and effects and contain zero caption cues. None of these three movie names occurs in the eleven Global release indexes checked below. An active quest trigger or a recording under another name remains unverified. |

The Windows launcher archive provides the publisher resource address for
each checked release. The eleven publisher movie indexes yielded these
counts of named USMs: 336 in 1.0.13 and 1.0.14, 373 in 1.1.9, 424 in
1.2.4 and 1.2.5, 478 in 1.3.3, 590 in 1.4.4 and 1.4.5, 636 in 1.5.3,
and 710 in 1.6.3 and 1.6.4. None listed any of the final ten names in
the table. For the two 1.0 versions, the archive comparison used the
checksum-validated filename records. Their identical 14-byte footer
is outside the toolkit’s supported index format. This check covers the
Global movie indexes; it cannot identify a renamed or regional performance.
[Archived Windows launcher responses](https://github.com/daydreamer-json/ak-endfield-api-archive/tree/538b29bee72a7bc42a30966d1e39a98a6c621a90/output/akEndfield/launcher/game_resources/6/Windows)
