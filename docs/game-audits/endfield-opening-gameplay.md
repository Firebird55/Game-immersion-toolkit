# Arknights: Endfield opening films in recorded gameplay

Reviewed November 13, 2026. All 46 retained Chinese caption cues can be identified in footage from the November 2023 Technical Test or its companion film. The playable prologue published for release uses a different story. Its female and male English event recordings can both be matched to the scene immediately before the fight with Ereignis. [Publisher film inventory](endfield-film-configs-1.6.4.csv) · [Historical caption IDs and film-relative display times](endfield-legacy-film-clocks-1.6.4.csv)

## The three Technical Test films

DragonGJY recorded the mainland PC test on November 10, 2023. The faint Chinese captions are part of the recording. The larger English captions are the uploader’s translation. The upload ends after the player-name prompt and its description links directly to the publisher’s film that follows. KyoStinV’s January 2024 Global Technical Test playthrough also shows the bedside scene and then Perlica’s briefing in the game. [Chinese prologue](https://www.youtube.com/watch?v=jCcaIyTgo-U) · [Global test transition at 15:10](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=910s) · [Original Chinese cue table](https://github.com/lsy-404/EndfieldGameData/blob/89ba7929f7fa64579852326b2bed0e679c3ccf49/TableCfg/SubtitleTable.json)

| Film and archived duration | What is visible | Video checkpoints |
| --- | --- | --- |
| `fmv_e0m1_1`, 89.300 s | All 11 caption IDs, from aircraft 33161’s status check to the emergency surgery order. The attack and Hawthorne’s exchange identify the second half independently of the opening number. | [Status check at 0:05](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=5s) · [Aircraft hit at 1:07](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=67s) · [Surgery at 1:25](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=85s) |
| `fmv_e0m1_3`, 145.000 s | All 14 retained caption IDs in the bedside exchange. At 10:07 the short original cue `02` is visible above the fan translation. The masked visitor later discusses the fall from 2,000 metres. | [Short cue at 10:07](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=607s) · [Visitor at 10:41](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=641s) · [Last retained cue at 10:55](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=655s) |
| `fmv_e0m1_4`, 148.960 s | All 21 retained cue IDs in the publisher’s Traditional Chinese edition of *Talos-II: Awakening*. Perlica covers the pioneers’ arrival, the hibernation pod and her role at Endfield. The publisher also released an English edition with its own edit. | [Pioneers at 0:20](https://www.youtube.com/watch?v=G2A5HAJFG7U&t=20s) · [Pod at 1:29](https://www.youtube.com/watch?v=G2A5HAJFG7U&t=89s) · [Perlica at 2:08](https://www.youtube.com/watch?v=G2A5HAJFG7U&t=128s) · [English edition at 2:10](https://www.youtube.com/watch?v=ntao9yWJcbo&t=130s) |

### Frame checks

Each value below is a seek time in seconds for a frame displaying the corresponding original Chinese caption or its Traditional Chinese counterpart. IDs are suffixes of the film name in the historical CSV, in CSV order. The intervals in the CSV use the start of the game film as zero. The seek times here use the start of each public upload.

| Film | Caption suffix → visible frame in the public video (s) |
| --- | --- |
| `fmv_e0m1_1` | 01 → 5.45, 02 → 9.80, 03 → 15.70, 04 → 20.60, 05 → 22.95, 06 → 27.60, 07 → 67.60, 08 → 70.10, 09 → 72.70, 10 → 81.95, 11 → 84.80 |
| `fmv_e0m1_3` | 01 → 601.50, 02 → 607.10, 03 → 608.30, 04 → 611.40, 05-1 → 614.10, 05-2 → 616.70, 05-3 → 620.45, 06 → 628.20, 07 → 634.00, 08 → 636.70, 09 → 641.85, 10 → 646.55, 11-1 → 650.95, 11-2 → 655.25 |
| `fmv_e0m1_4` | 01 → 6.60, 02 → 12.10, 03-1 → 20.50, 03-2 → 27.00, 04-1 → 33.90, 04-2 → 41.15, 05 → 52.60, 06-1 → 62.05, 06-2 → 69.45, 07 → 75.70, 08 → 81.60, 09-1 → 88.70, 09-2 → 94.00, 09-3 → 98.80, 10 → 105.10, 11 → 114.75, 13 → 122.25, 14 → 128.50, 15-1 → 136.20, 15-2 → 141.85, 16 → 147.80 |

A 25-frames-per-second comparison of the Chinese captions independently located the interval for `fmv_e0m1_1_07` at 66.56–69.76 s in the upload, against 64.80–68.00 s in the film. For `fmv_e0m1_3_02` it found 606.64–607.44 s against 62.20–63.00 s. The figures describe visible text on a 40 ms sampling grid. The English overlay sometimes combines two original Chinese cues. The Traditional Chinese trailer also splits some text differently from the archived table, including `04-2` and `10`. Each edition needs its own timing. [First exchange](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=67s) · [Bedside exchange](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=607s) · [Split trailer caption](https://www.youtube.com/watch?v=G2A5HAJFG7U&t=43s)

The November gameplay includes five additional archived bedside captions after the end of the 14 retained intervals. Measured Chinese subtitle windows in upload seconds are 658.24–663.48 (12), 663.48–664.76 (13), 665.16–669.44 (14), 671.24–676.76 (15) and 676.76–683.96 (20). Two different crops of the on-screen Chinese line returned the same boundaries at 25 frames per second. The video goes directly from 15 to 20. The archived text table also lists suffixes 16 through 19. Those four entries would give a false account of this performance. The current Global text tables contain none of the 46 retained historical IDs. These observations establish the old story and its cuts. The aircraft and bedside recordings still lack a verified publisher download. The Mandarin briefing is available from the publisher as described below. [Short reply at 11:03](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=663s) · [Transition at 11:16](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=676s) · [Global game-data audit](endfield.md)

### Obtaining the Mandarin briefing audio

The publisher’s mainland video catalogue supplies the full 151.960-second
Mandarin edition of *Talos-II: Awakening* with Simplified Chinese subtitles.
The MP4 is 196,340,927 bytes and its SHA-256 is
`11dfb2ff2735668f570e3b030b50cd3b18aaf7e14e274684ddc8fb76e405914f`.
In a mainland Technical Test playthrough recorded on November 10, 2023,
all 23 of its captioned audio excerpts independently match a single offset
of 920.351 s. Correlations range from 0.563 to 0.945. This identifies the
actual Mandarin film mix heard in the game, including music. The website
also lists separate Japanese, Korean, English and Traditional Chinese
editions on YouTube. Those listings and their nine-second previews do not
establish equivalent game recordings for the other dubs.
[Publisher’s full Mandarin film](https://web.hycdn.cn/upload/video/20251030/d836cdada37b16eabbbdd372ed3cf809.mp4) ·
[Test opening at 15:25](https://www.bilibili.com/video/BV1tu4y187be/?p=3&t=925) ·
[Test ending at 17:46](https://www.bilibili.com/video/BV1tu4y187be/?p=3&t=1066) ·
[Publisher video catalogue](https://endfield.hypergryph.com/video)

The 21 game caption IDs account for all 23 subtitle displays. The archived
IDs `04-2` and `10` each span two displays. The display transition for
`03-2` falls after the phrase about “this land” has started. The transition
between `09-2` and `09-3` falls inside a single display. The recording
cuts follow those spoken phrases. For example, the last word in the phrase
about activating the device has its syllable peak at 97.26 s. The next
sentence begins around 97.80 s. The two exports meet at 97.560 s.
The historical text table contains an extra line with suffix `12` after
`11`; it does not occur in this performance.
[Archived Mandarin text](https://github.com/lsy-404/EndfieldGameData/blob/89ba7929f7fa64579852326b2bed0e679c3ccf49/TableCfg/SubtitleTable.json) ·
[This exchange in gameplay at 16:57](https://www.bilibili.com/video/BV1tu4y187be/?p=3&t=1017)

The film command lists the 21 original game lines and their recording cuts.
An export downloads and checks the publisher film once and reuses the
verified file. It works without the game or a player video. These historical
IDs are absent from the current Global storyline, so they are available as
an explicit archive lookup.

```text
python scripts/endfield_film_voice.py --test-caption list --locale zh-Hans --cache private-cache
python scripts/endfield_film_voice.py --test-caption fmv_e0m1_4_09-3 --locale zh-Hans --cache private-cache --mp3 reawakening.mp3
```

## Other films preserved in the Technical Test catalogue

The original November 2023 distribution index identifies the two motorcycle
movies `fmv_e1m1_1` and `fmv_e1m1_2`, and the two movies `fmv_e2m8_1`
and `fmv_e2m8_2` surrounding the final boss. Each is a separate USM with
its own length and checksum. The current video registry retains durations
of 30.916, 21.983, 29.100 and 79.683 seconds respectively. The test index
identifies files but does not supply a working download address. The
publisher closed the Global test on January 21, 2024.
[Historical movie index](https://github.com/lsy-404/EndfieldGameData/blob/89ba7929f7fa64579852326b2bed0e679c3ccf49/VFBlockMainInfo/00B05BD957F256D9.json) ·
[Publisher closure notice](https://endfield.gryphline.com/en-us/news/1348)

The January 2024 Global walkthrough shows that an ordinary radio exchange
between Perlica and Fiona continues during the motorcycle ride. The ambush
then has three separate overlaid captions with IDs `timeline_e1m1_1_01`,
`_02` and `_03`. The English captions correspond to the archived Chinese
lines in that order. Half-second samples show the first at approximately
19:13–19:14, the second at 19:16–19:18, and Perlica's instruction to stay
close at 19:32–19:36. These are observed display times in this recording.
The three IDs belong to the timeline and have no demonstrated voice-file
binding in the current distribution. The earlier Fiona radio exchange has
different wording. [Radio during the ride](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=1098s) ·
[Two calls during the ambush](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=1153s) ·
[Perlica's instruction](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=1172s) ·
[Historical text](https://github.com/lsy-404/EndfieldGameData/blob/89ba7929f7fa64579852326b2bed0e679c3ccf49/TableCfg/SubtitleTable.json)

A separate January 2024 recording shows the Triaggelos arrival, the boss
fight and its aftermath. By 10:40 Perlica calls to the Endministrator.
Fiona and Angelina Ajimu have a separate conversation as control returns
to the characters. The archival subtitle table contains no key bearing
either of the two boss-movie IDs. The soundtrack in this video does not
identify a separate original sentence recording for either movie.
[Boss arrival](https://www.youtube.com/watch?v=2dX2GFG8dv8&t=127s) ·
[Aftermath](https://www.youtube.com/watch?v=2dX2GFG8dv8&t=640s)

## Current English prologue before the Ereignis fight

The publisher’s September 2025 PS5 demonstration shows the female Endministrator. The January 2026 version 1.0 recording by Maakuplays shows the male Endministrator. In both, the camera turns from the protagonist to Ereignis in a snow-covered area. The protagonist shields their face, the enemy extends a hand, and the scene continues into the boss encounter. These are the versions of `cs_video_e0m0_3` identified by their current Global 1.6.4 English voice tracks. [Female performance in the official demonstration](https://www.youtube.com/watch?v=2GjOGijE9fM&t=596s) · [Male performance in 1.0 gameplay](https://www.youtube.com/watch?v=59n93iqzIIM&t=40s)

| Current English event | Upload time corresponding to event start | Audio identification |
| --- | ---: | --- |
| `au_vo_cs_e0m0_3_f` | 556.56 s | Six separated excerpts from the event each located the same point, within 0.01 s, when searched across the full 14:39 official mix. |
| `au_vo_cs_e0m0_3_m` | 0.12 s | Five separated excerpts independently returned the same offset when searched across the full 5:14 gameplay mix. |

To reproduce the match, decode the original English WEM and the corresponding video audio to mono PCM at 8 kHz, apply the same 320–3,600 Hz band-pass, and correlate the non-silent excerpts against the full mix. At the derived offset, all seven published activity intervals in each event have a correlation peak within 10 ms. The seventh interval is the weakest in both performances. Four intervals begin during the 0.000–59.750 s game movie. Three begin after it, when the parent scene continues. [WEM checksums and activity intervals](endfield-film-recording-activity-1.6.4.csv) · [Female scene continuation](https://www.youtube.com/watch?v=2GjOGijE9fM&t=617s) · [Male scene continuation](https://www.youtube.com/watch?v=59n93iqzIIM&t=61s)

No dialogue subtitles appear at the matched activity in either video. The images show reactions and movement. Speech recognition with voice activity detection produced no words from either English track. Without the detector it also produced a word in a silent stretch. There is evidence for vocal reactions, including breath-like sounds, but no verified sentence to bind or export from this film. The original localized parent events remain available through the publisher. Two similarly named text lines belong to the later `cutscene_e0m0_5` and have their own verified timings. [Current dialogue and audio sources](endfield.md)
