# Endfield mission radio playback observations

Checked November 13, 2026. Thirteen radio rows in the [Global 1.6.4 inventory](endfield-mission-radio-1.6.4.csv) have no bound sentence or named reaction recording. All thirteen also exist in Global 1.5.3. Running the same reader on each publisher release and each of the four dubs found nine rows with a configured interjection and no mapped performer, plus four rows without a configured interjection. All thirteen have an empty separate audio-event field.

## Gameplay evidence

The times below refer to the public player recordings. The on-screen text matched the corresponding publisher localization. The recordings predate 1.6.4. They document individual playthroughs, including environmental sounds and combat.

| Mission and radio rows | Observations |
| --- | --- |
| Where Art Thou My Love, `radio_gm01m10_5_001` and `_002` | English combat calls overlap the captions at 1:00–1:09 in one recording. In a second playthrough, Fiona's English `au_dlg_commvo_fiona_neutral_04` matches the publisher waveform at 1:11.353 (correlation 0.93). During the subsequent Angry and Lazy Landbreaker captions, around 1:23–1:33, game audio continues. Neither speech detection nor transcription identified speech in that window. Comparing the 185 available English `negative_02` reactions found no verified match in either encounter. [First playthrough](https://www.youtube.com/watch?v=XMId1vTVV88&t=59s) · [Second playthrough with Fiona control](https://www.youtube.com/watch?v=FjnMPmvBkfM&t=71s) |
| Illusion, `radio_gm01m16_2_001` and `_002` | Fiona's Japanese `au_dlg_commvo_fiona_negative_03` matches at 3:48.949 (correlation 0.57) before both captions at 4:06–4:14. A second playthrough matches the English recording of the same reaction at 2:01.890 (0.64). The Greedy and Alert Landbreaker captions follow around 2:18–2:27. The game mixes contain audio, but speech detection found no speech during either pair of captions. Comparison with the configured reactions in the respective dubs yielded no verified performance for either NPC. [Japanese playthrough](https://www.youtube.com/watch?v=OGKyAE4pN0Y&t=228s) · [English playthrough with Fiona control](https://www.youtube.com/watch?v=I5HIk_BoM9U&t=121s) |
| Divvy Up the Trouble, `radio_gm02m14_2_001`, `radio_gm02m14_3_001` and `_002` | All three An Yu captions appear around 3:30–3:40. The soundtrack contains audio throughout. Neither the speech detector nor automatic transcription identified speech over these captions. A search across English and Japanese reaction recordings for the configured emotion types yielded no verified match. [Gameplay](https://www.youtube.com/watch?v=4reYDXGS8lI&t=209s) |
| Daily: Spray and Clean, `radio_m1m73_5_001` and `_002` | Both Japanese captions appear around 0:11–0:20. Before Chen's captions appear, Fiona's Japanese `au_dlg_commvo_fiona_positive_03` matches the original publisher audio at **0:05.739**, with normalized correlation 0.91. None of the 476 Japanese recordings matching Chen's configured emotion yielded a comparable match during either caption. A second playthrough shows Chen's first caption around 1:16. [Both captions](https://www.youtube.com/watch?v=6dBfutWjbgY&t=5s) · [Second playthrough](https://www.youtube.com/watch?v=tq9nTZ-uT-o&t=74s) |
| A Breach Starts with a Crack, `radio_e10m1_11_001` and `_002` | Both lines appear at the end of the preceding mission. Neither speech detection nor transcription found speech during either caption in two playthroughs. In the preceding scene, Zhuang Fangyi's original `au_dlg_e9m4_19_019` matches the **English** recording in one video (correlation 0.75) and the **Japanese** recording in the other (0.79). Both recordings therefore include dialogue audio in the respective dub. [English at 43:34](https://www.youtube.com/watch?v=D31_Ccpoz7c&t=2614s) · [Japanese at 31:48](https://www.youtube.com/watch?v=JmQGmO1a25o&t=1908s) |
| Alluvial Cleaning, `radio_m1m6_1_001` | The Russian subtitle matches the publisher's hidden entry warning from approximately 0:03 to 0:06.5. This recording begins before the warning. Music and movement continue through the caption. Speech detection flagged a brief sound at 0:05.9–0:06.2, and transcription did not identify a spoken sentence. The following tutorial has a separate English Fiona reaction matching the publisher waveform at 0:07.515 (correlation 0.94). A second recording opens with the Portuguese warning already visible through 0:02.5. Its Japanese tutorial reaction matches at 0:16.389 (0.99). The missing start of the second recording limits what can be inferred there. [English dub with Russian subtitles](https://www.youtube.com/watch?v=Dy1iO0XBEDc&t=2s) · [Japanese dub with Portuguese subtitles](https://www.youtube.com/watch?v=er5mD2v5okk) |
| Bell of Recollection: Afternotes, `radio_gm02m27d5_1_001` | The first Endministrator caption appears after collecting the last Suiming research material, at 7:00 and 3:01 in two independent guides. In both mixes the guide's narrator is talking during the caption. A third, continuous playthrough shows the exact first caption at about 16:58–17:03 with Traditional Chinese subtitles. No spoken words were detected across the first caption. The second caption follows at 17:03, and its Japanese male Endministrator reaction `au_dlg_commvo_endminm_sigh_03` matches the publisher waveform at about 17:03.22 (normalized correlation 0.93). The first caption has no configured reaction and the second has its own reaction choices. [Continuous gameplay with original-audio control](https://www.youtube.com/watch?v=r6OxrWFyCGM&t=1017s). [First recording](https://www.youtube.com/watch?v=emR-SCTq8vw&t=419s) · [Second recording](https://www.youtube.com/watch?v=GV7EFBuBN8A&t=180s) |

The comparison used publisher WEMs from the active dub, including other actors' candidates for the configured emotion. It compared the band-limited decoded waveforms with the player recording and checked the strongest candidates across separate frequency bands. Short, pitched combat sounds can give a partial correlation in one band. The search cannot exclude a short sound under the mix. The toolkit continues to require an authored binding before exporting an original recording.

### An Yu in two additional playthroughs

The publisher's `gm02m14_name` localization key identifies this mission as
*分忧解难* (Chinese) and *お悩み解決* (Japanese). On-screen text in two
independent version 1.2 walkthroughs matches the three Global 1.6.4 radio
rows. These times are approximate subtitle starts in each video.

| Radio row | Japanese subtitles | Chinese subtitles |
| --- | --- | --- |
| `radio_gm02m14_2_001` | [2:21](https://www.youtube.com/watch?v=zPSDg2DKQNw&t=141s) | [3:01](https://www.bilibili.com/video/BV1mK5Q6cE38/?p=4&t=181) |
| `radio_gm02m14_3_001` | [2:25](https://www.youtube.com/watch?v=zPSDg2DKQNw&t=145s) | [3:05](https://www.bilibili.com/video/BV1mK5Q6cE38/?p=4&t=185) |
| `radio_gm02m14_3_002` | [2:33](https://www.youtube.com/watch?v=zPSDg2DKQNw&t=153s) | [3:11](https://www.bilibili.com/video/BV1mK5Q6cE38/?p=4&t=191) |

The Japanese-subtitled mix contains game audio at all three captions. Speech
detection and transcription found no spoken words during the sequence.
Comparison with 476 candidate Japanese recordings for emotion 41 and 186
for emotion 37 yielded no verified match. In the Chinese video a guide
speaks Mandarin over all three captions, giving directions about spraying
the cores and opening a door. Searching the complete Japanese walkthrough
for audio shared with the Chinese and English-subtitled recordings did not
identify a sound specific to An Yu. One short sound heard in the Chinese
second-caption window matched the Japanese playthrough more closely
outside the encounter (5:27) than during that caption.

In both Global 1.5.3 and 1.6.4 An Yu's NPC row has an empty `voActor`.
Its NPC and Wwise identifiers are `gm02m14hsstudent1`, and its template is
`npc_girl_hsstudent_a_24`. None of the six configured reaction suffixes
combined with either name occurs in the releases' voice-duration tables.
The controller passes the result of `GetRealActorNameId` into
`TryGetCommonEmotionVoiceId`. It only posts a voice when that method
succeeds. The published controller does not show how that method chooses
an actor for an NPC with an empty voice field. These three rows still have
no verified performance or proof of a permanently silent fallback.
[Released radio playback controller](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L922-L946)

## Four rows without a configured interjection

| Mission | Rows | Reproduction point in the publisher's mission script |
| --- | --- | --- |
| A Breach Starts with a Crack | `radio_e10m1_11_001`, `_002` | The start action for `e10m1_q#1` plays the Endministrator's two radio lines before contacting Zhuang. Walkthroughs starting in the message thread skip this trigger. |
| Alluvial Cleaning | `radio_m1m6_1_001` | Entering `m1m6_000` in `map01_lv001` starts the mission. The trigger has radius 40 around game coordinates (−364.81, 95.00, −439.53). The hidden initial step `m1m6_q#5` has no objectives. Its completion action requests Fiona's warning before the first visible objective. The later alluvium tutorial contains a different conversation. The two recordings above show the warning and independently identify the dub of the following tutorial. [Mission trigger](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/Json/MissionRuntimeAsset/m1m6_meta.json) · [Trigger geometry](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/Json/GameplayConfig/MissionAreaTable.json#L14723-L14754) |
| Bell of Recollection: Afternotes | `radio_gm02m27d5_1_001` | The start action for `gm02m27d5_q#1` references the radio group. The first row has emotion 13 with an empty list and empty single reaction. The second row has its own configured reactions. |

The four rows have no identifiable sentence, separate audio event or configured interjection in the inspected publisher data. None of the thirteen literal overrides or their male/female suffixes appears in the Global 1.6.4 `AudioDialog` or `AudioVoiceExtraData` tables. The radio controller calls the duration lookup before selecting a fallback and may skip a fallback after successful playback. [Radio controller](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L880-L960)

### Publisher duration and radio playback on November 13

The four rows above enter the text-only branch in the Global 1.5.3 and 1.6.4
releases. For all 30,180 and 34,194 entries respectively, the signed 32-bit
Wwise short ID of the recorded filename stem equals the `AudioDialog` key.
This includes extensionless internal events. Both releases' `AudioVoiceExtraData`
tables have exactly the same keys as their duration tables. All four literal row
overrides and their female/male forms are absent in both. The two duration
overloads and their Lua call read the dub-specific duration from `VoiceData`.
[Runtime per-language voice duration](https://github.com/Dr-hydra/Better-Endfield/blob/26430566b98f1d97d0d156bc8e73f8671b496e1c/docs/voice/VOICE_CUSTOM_LANGUAGE_SYSTEM.md#L85-L101)

When the duration lookup fails, the controller clears the override, looks up an
emotion recording and posts the row's separate event if present. All four have
an empty separate event. Three specify emotion 0, and the fourth specifies an
explicitly empty emotion 13. Their group/row IDs have no custom event and the
voice conflict table is empty. The two Breach lines request resumption after
interruptions. That flag queues a continuation at the row index. An additional
spoken continuation in 1.6 requires an interrupted voice and a nonzero
continuation type. The Breach group sets that type to zero.
[1.5 controller](https://github.com/rmxlinux/EndfieldData/blob/6e7185011c8e5739737f4a651a9b32c8314e6355/LuaScripts/LuaSystem/RadioSystem.lua#L860-L945)
· [1.6 continuation](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L535-L571)
· [Dialog interruption](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L1032-L1058)

Windows Setup using publisher data makes all four eligible for the existing
unvoiced capture option. The diagnostic reports `text_only`. The nine other
mission rows have configured interjections and remain unresolved. Both
outcomes were reproduced in English, Japanese, Korean and Mandarin on both
releases. Across the complete radio table, 190 rows in 1.5.3 and 187 rows in
1.6.4 met these conditions before localization filtering. Each new preparation
checks the selected release's tables. A new recording, event or emotion
prevents the text-only classification.

The [publisher radio command](../../scripts/endfield_radio.py) reports `reaction_status` for rows lacking a resolved sentence source and `audio_event` when the row posts a separate event. Both fields follow the selected release and dub. The gameplay links provide audit evidence and have no role in acquisition or playback.

The radio controller resolves the player's actor before selecting an emotion. For the male Endministrator heard on the second Afternotes caption, use `--reaction-player male`. This command fetched the 0.800-second Japanese performance from the Global publisher. The decoded samples were identical to the reference used for the gameplay match. Each run checks the selected release's actor table, emotion choices and dub inventory. [Publisher radio controller](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L922-L932)

```text
python scripts/endfield_radio.py --cache private-cache --locale ja --reaction-player male --line endfield:radio_gm02m27d5_1_002 --reaction au_dlg_commvo_endminm_sigh_03 --wem afternotes-reaction.wem
```

## Fiona's Alluvial Cleaning tutorial reaction

The tutorial's opening caption “Endmin, please clean up this Energy Alluvium quickly.” is conversation `dlg_m1m6_1_001`. Its row names Fiona, requests emotion 4 and has an unresolved sentence override. The active NPC and emotion tables map that row to a single `neutral_04` reaction. Matching the released `au_dlg_commvo_fiona_neutral_04` WEM against unmodified-speed gameplay audio placed the English reaction at 1:17.914 (normalized correlation 0.91), Japanese at 0:17.049 (0.94), and Mandarin at 0:38.491 (0.90). The publisher recordings last 0.485, 0.571 and 0.443 seconds respectively. The English recording also matches the separate *Where Art Thou My Love* encounter at 1:11.353 (0.93). The opening row supplies its own binding and needs no preceding caption. [English tutorial](https://www.youtube.com/watch?v=OLDehlt0hxk&t=76s) · [Japanese tutorial](https://www.youtube.com/watch?v=gz-IDjR049E&t=16s) · [Mandarin tutorial](https://www.bilibili.com/video/BV13LznB3EJU?p=18&t=38) · [English reuse](https://www.youtube.com/watch?v=FjnMPmvBkfM&t=71s)

The Korean performance of the same reaction lasts 0.502 seconds. It matches a third *Where Art Thou My Love* playthrough at 1:17.956 (correlation 0.925). Fiona's on-screen caption translates to “Endmin, someone has fled up there!” Its Korean text identifies `radio_gm01m10_8_001`. Both that radio row and the tutorial opening select Fiona's `neutral_04`. The Korean recording exported from the Global 1.6.4 publisher package for this radio row. [Korean gameplay at 1:17](https://www.youtube.com/watch?v=Cbp1xuoa_-w&t=77s)

The hidden radio warning `radio_m1m6_1_001` has its own wording, an empty actor mapping and emotion 0. The two entry recordings above locate that warning independently of the tutorial reaction. No full sentence or identifiable Fiona reaction was established during the warning. The source command can list or explicitly export the opening conversation's reaction in the selected dub. Its default sentence export still requires a verified sentence recording.

```text
python scripts/endfield_radio.py --cache private-cache --locale en --line endfield:dlg_m1m6_1_001
python scripts/endfield_radio.py --cache private-cache --locale en --line endfield:dlg_m1m6_1_001 --reaction au_dlg_commvo_fiona_neutral_04 --wem fiona-reaction.wem
```
