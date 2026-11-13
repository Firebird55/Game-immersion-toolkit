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

The measurements above cover one English male playthrough of the two Si
scenes and a sampled English Liino performance. The female Si recordings
and other dubs still need independent gameplay observations for their own
onscreen presentation. No sentence-level subtitle binding follows from
these three reviewed examples.

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
Global 1.5.3 and 1.6.4. The 1.6.4 Japanese and Korean recordings also have
four resolvable captions. Two of the four Mandarin captions overlap in an
audible part of the recording. The first and last Mandarin clips can be
exported with their own intervals. The other two still lack separate verified
cuts. [Publisher scene and recording checks](endfield.md)

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
