# Endfield mission radio playback observations

Checked November 9, 2026. Thirteen radio rows in the [Global 1.6.4 inventory](endfield-mission-radio-1.6.4.csv) have no bound sentence or named reaction recording. All thirteen also exist in Global 1.5.3. Running the same reader on each publisher release and each of the four dubs found nine rows with a configured interjection and no mapped performer, plus four rows without a configured interjection. All thirteen have an empty separate audio-event field.

## Gameplay evidence

The times below refer to the public player recordings. The on-screen text matched the corresponding publisher localization. The recordings predate 1.6.4. They document individual playthroughs, including environmental sounds and combat.

| Mission and radio rows | Observations |
| --- | --- |
| Where Art Thou My Love, `radio_gm01m10_5_001` and `_002` | Both captions appear around 1:00–1:09. English combat calls overlap the encounter. Speech recognition did not reproduce either caption. Waveform comparison against the 185 available English `negative_02` reactions did not identify a corresponding recording for either Landbreaker. [Gameplay](https://www.youtube.com/watch?v=XMId1vTVV88&t=59s) |
| Illusion, `radio_gm01m16_2_001` and `_002` | Both captions appear around 4:06–4:14. The Japanese gameplay soundtrack continues underneath both. A speech detector found no speech in the caption window. A comparison with 737 available reactions for the first emotion and 186 for the second did not establish a matching performance. [Gameplay](https://www.youtube.com/watch?v=OGKyAE4pN0Y&t=245s) |
| Divvy Up the Trouble, `radio_gm02m14_2_001`, `radio_gm02m14_3_001` and `_002` | All three An Yu captions appear around 3:30–3:40. The soundtrack contains audio throughout. Neither the speech detector nor automatic transcription identified speech over these captions. A search across English and Japanese reaction recordings for the configured emotion types yielded no verified match. [Gameplay](https://www.youtube.com/watch?v=4reYDXGS8lI&t=209s) |
| Daily: Spray and Clean, `radio_m1m73_5_001` and `_002` | Both Japanese captions appear around 0:11–0:20. Before Chen's captions appear, Fiona's Japanese `au_dlg_commvo_fiona_positive_03` matches the original publisher audio at **0:05.739**, with normalized correlation 0.91. None of the 476 Japanese recordings matching Chen's configured emotion yielded a comparable match during either caption. A second playthrough shows Chen's first caption around 1:16. [Both captions](https://www.youtube.com/watch?v=6dBfutWjbgY&t=5s) · [Second playthrough](https://www.youtube.com/watch?v=tq9nTZ-uT-o&t=74s) |

The comparison used publisher WEMs from the active dub, including other actors' candidates for the configured emotion. It compared the band-limited decoded waveforms with the player recording and checked the strongest candidates across separate frequency bands. Short, pitched combat sounds can give a partial correlation in one band. The search cannot exclude a short sound under the mix. The toolkit continues to require an authored binding before exporting an original recording.

## Four rows without a configured interjection

| Mission | Rows | Reproduction point in the publisher's mission script |
| --- | --- | --- |
| A Breach Starts with a Crack | `radio_e10m1_11_001`, `_002` | The start action for `e10m1_q#1` plays the Endministrator's two radio lines before contacting Zhuang. Walkthroughs starting in the message thread skip this trigger. |
| Alluvial Cleaning | `radio_m1m6_1_001` | The hidden initial step `m1m6_q#5` has no objectives. Its completion action plays Fiona's warning before the first visible objective. The tutorial dialogue at the alluvium uses different lines. |
| Bell of Recollection: Afternotes | `radio_gm02m27d5_1_001` | The start action for `gm02m27d5_q#1` references the radio group. The first row has emotion 13 with an empty list and empty single reaction. The second row has its own configured reactions. |

The four rows have no identifiable sentence, separate audio event or configured interjection in the inspected publisher data. They remain unresolved for the actual gameplay mix. None of the thirteen literal overrides or their male/female suffixes appears in the Global 1.6.4 `AudioDialog` or `AudioVoiceExtraData` tables. The radio controller calls the duration lookup before selecting a fallback and may skip a fallback after successful playback. [Radio controller](https://github.com/rmxlinux/EndfieldData/blob/d847759f71d4549aba4727b3b0ac1a1ad0e37742/LuaScripts/LuaSystem/RadioSystem.lua#L880-L960)

The [publisher radio command](../../scripts/endfield_radio.py) reports `reaction_status` for rows lacking a resolved sentence source and `audio_event` when the row posts a separate event. Both fields follow the selected release and dub. The gameplay links provide audit evidence and have no role in acquisition or playback.
