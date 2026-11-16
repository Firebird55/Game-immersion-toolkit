# Original Global Technical Alpha soundtracks

Checked November 16, 2026. A publicly archived January 2024 Global client contains the original English and Mandarin aircraft, bedside, Talos-II briefing and motorcycle ambush recordings. All eight performances have independent gameplay evidence. Acquisition used HTTP byte ranges and read-only package parsing, without installing or executing the archived client. [Client archive](https://archive.org/details/arknights-endfield-technical-alphawith-hotfix) · [Archive file identities](https://archive.org/metadata/arknights-endfield-technical-alphawith-hotfix) · [Global gameplay](https://www.youtube.com/watch?v=5wJdbAkjKlE)

## Acquisition and integrity

The archive lists one 12,047,240,068-byte ZIP. Its ZIP64 central directory contains 862 members. All 519 VFS chunk prefixes were inspected. They include 67 CRI movies and eight original Wwise packages. The Wwise language tables identify separate English and Chinese packages. English and Chinese each have a localized bank package and a package containing 15 streamed recordings.

The English streamed package is the member ending in
`StreamingAssets/VFS/B4CBAFFFE1C9A3134EBABFED473658A5.chk`.
Its local ZIP header begins at byte 8,038,341,053. It uses DEFLATE with 119,094,478 compressed bytes and expands to 120,034,944 bytes. The complete member was decompressed and checked against the ZIP directory's CRC32, `fde75523`. Its SHA-256 is `8e1869fc60779648084aa2337d484f67e8710e77e3a2f822e217e03d4b890a6e`.

The existing Wwise package-table reader recovered each recording using its authored numeric media ID and byte range. All three decoded with the toolkit's VGMStream tool.

| Historical scene | English media ID | Original WEM bytes | Decoded duration |
| --- | ---: | ---: | ---: |
| Aircraft, `fmv_e0m1_1` | 575989014 | 4,879,398 | 89.862 s |
| Bedside, `fmv_e0m1_3` | 646125757 | 7,665,543 | 146.402 s |
| Briefing, `fmv_e0m1_4` | 351625180 | 4,686,446 | 152.683 s |

The respective WEM SHA-256 values are
`b3044d65ddbb58041382d868fe4df4421fb2f49be9b5a0ba289595b253bf0377`,
`40d8055a4eba246962f2f052941df42c768c9cea2958c86befb4fe0715b58c55` and
`710760c0684563f5169ece2c1cec6daed5b78cbb70452b4ba9a4d0f65fe83ab4`.

## Independent gameplay matches

The game recordings and gameplay soundtrack were decoded to mono 8 kHz PCM and filtered at 320–3,500 Hz. Three-second excerpts at the original recording times below were searched over the first 1,150 seconds of the complete Global walkthrough. Correlations use the excerpt and the corresponding target window's energy. Each scene has one consistent recording-to-upload offset.

| Scene | Original excerpt starts | Offset in upload | Normalized correlations |
| --- | --- | ---: | --- |
| Aircraft | 4, 20, 26, 67, 76 s | 15.5359 s | 0.923, 0.967, 0.891, 0.891, 0.971 |
| Bedside | 56, 67, 80, 90, 105, 117 s | 781.6799 s | 0.982, 0.987, 0.976, 0.985, 0.987, 0.983 |
| Briefing | 2, 15, 46, 91, 120 s | 928.3039 s | 0.917, 0.933, 0.744, 0.932, 0.912 |

These matches establish the original mixes used by that game performance, including sound effects. The bedside English conversation begins in the latter portion of its recording. English wording and speech timing differ from the earlier mainland test. The [previous mainland caption clocks](endfield-opening-gameplay.md) therefore require separate validation before use with these recordings. [Aircraft exchange](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=19s) · [Bedside exchange](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=837s) · [Briefing](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=930s)

### A second mainland aircraft playthrough

An independent November 2023 recording identifies the same original Mandarin
aircraft mix. Three-second source excerpts at 4, 20, 26, 67 and 76 seconds
match part 3 of the upload with a consistent 39.0539–39.0540-second offset.
The respective normalized correlations at 8 kHz, filtered at 320–3,500 Hz,
are 0.699, 0.778, 0.742, 0.729 and 0.873.
[Independent test walkthrough, part 3](https://www.bilibili.com/video/BV1tu4y187be/?p=3)

The recording's native Chinese subtitles also show each remaining aircraft
caption: `07` around 1:45, `08` at 1:48, `09` around 1:49, `10` at 1:58.8
and `11` at 2:02.8. The final two appear over the dark aftermath of the
crash. These observations independently confirm the displayed text and mix;
they do not establish complete spoken export windows.
Speech-recognition checks on the original mix and a comparison after reducing
the shared soundtrack did not yield reliable words for the five remaining
cuts. No extra recording, silence classification or additional playable
caption is inferred from that failure. The six unresolved Mandarin cuts and
English text/cuts remain open below.

The complete archived bedside movie was also retrieved. Its SHA-256 is `5c9e47bb0af3c55a10858c3715c22099f86499ba85281090b27f384f5e4ab23f`, with 61,960,960 bytes. The internal CRI directory identifies `fmv_e0m1_3.usm`. Traversal of the complete file found one CRID directory and 4,355 video packets, with zero audio packets. The separate Wwise recording above supplies its English soundtrack.

## Original motorcycle ambush scene

The same verified English package contains media **52120711**, a
1,355,937-byte original WEM with SHA-256
`0f4f62358e0efc1731744f662b327092977db9980dbebb5132f6d9ead40ae30c`.
One playback pass lasts **23.962 s**. The WEM carries a loop flag; the
research decode explicitly disabled looping rather than measuring repeated
playback and the decoder's fade-out as part of the scene.

Seven separate 1.5-second excerpts at source times 0.5, 2, 5, 10, 15, 19
and 21 s all match the Global walkthrough with the same **1,153.1999 s**
offset. Their normalized correlations are 0.953, 0.914, 0.778, 0.772,
0.672, 0.621 and 0.782 at 8 kHz, filtered at 320–3,500 Hz. These include
the opening calls, intervening effects and the final instruction. The three
displayed captions have the historical IDs `timeline_e1m1_1_01` through
`_03`. Their parent `timeline_e1m1_1` is the command's scene label; it is
not a claimed archive filename or a current-release event binding.
[Ambush and opening calls](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=1153s)
· [Final instruction](https://www.youtube.com/watch?v=5wJdbAkjKlE&t=1172s)

The Mandarin counterpart is media **375522099**, with 1,376,668 bytes and
SHA-256 `9ee710f45f91ea64209d1bd563bbf773057374dbeb65e2cb45ccc16d0f9f7839`.
Both original Wwise 140 banks bind event `1475494453` through Play action
`909589639` and Sound object `411909712` to the respective localized media.
The same bank comparison independently recovers the already verified
aircraft, bedside and briefing pairs. The English bank-package SHA-256 is
`6546be152af280a1cc107cb44ec1c919b992ae69e3f2a5470db48020809ced49`;
the Mandarin bank-package SHA-256 is
`fe882430d1ceac06bb6fa474f70e80eeafe3a7216ab2f1993eb15fa3e39d56c3`.

The Mandarin recording independently matches part 4 of the November 2023
mainland walkthrough. All seven source excerpts above locate the same
**90.4733 s** offset, with correlations 0.927, 0.940, 0.873, 0.727, 0.664,
0.453 and 0.779. Native Chinese captions reproduce the first call around
1:31, the second around 1:35 and Perlica's instruction around 1:51.
[Mainland ambush](https://www.bilibili.com/video/BV1tu4y187be/?p=4&t=91)
· [Perlica's instruction](https://www.bilibili.com/video/BV1tu4y187be/?p=4&t=111)

The normal archive command retrieves either complete original scene without
a game installation, verifies the existing package hash and checks the
individual WEM hash. Both live commands recovered the declared bytes from
their respective verified package caches and decoded to 23.962 s without
looping. The two verified Mandarin caption exports are described below.
The second Mandarin call, English per-caption text and spoken boundaries,
and the exact relationship to each movie file remain open. No translated
transcript, silence override or guessed movie filename is introduced.

```text
python scripts/endfield_film_voice.py --archive-film timeline_e1m1_1 --locale en --cache private-cache --wem motorcycle-ambush-en.wem
python scripts/endfield_film_voice.py --archive-film timeline_e1m1_1 --locale zh-Hans --cache private-cache --wem motorcycle-ambush-zh.wem
```

## Mandarin recordings

The separate Chinese streamed package ends in `3F4A536996369BBDA4AA64B4AD5996D2.chk`. The complete 105,863,503-byte member passed its ZIP CRC check. Its SHA-256 is `51be530994d9bbc2f6e8253a63f9129a4477a6510a3c8b112b59b8b95bfed1eb`.

| Scene | Mandarin media ID | Original WEM bytes | Decoded duration |
| --- | ---: | ---: | ---: |
| Aircraft | 1046408181 | 4,817,946 | 89.862 s |
| Bedside | 945985728 | 7,492,874 | 142.504 s |
| Briefing | 780870713 | 4,290,068 | 151.552 s |

Five aircraft excerpts at 4, 20, 26, 67 and 76 s independently match DragonGJY's November 2023 mainland playthrough at an offset of 1.8317–1.8318 s, with correlations 0.931–0.992. Six bedside excerpts at 56, 67, 80, 90, 105 and 117 s independently match at 544.5095 s, with correlations 0.971–0.989. The original aircraft and bedside mixes therefore remain present in the January Global client's Chinese package. [Mainland aircraft](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=5s) · [Mainland bedside](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=601s)

A further bedside comparison sampled 55, 61, 63, 68, 70, 75, 89, 110, 120, 124, 126, 129, 132, 135 and 138 s. All fifteen independently returned the same 544.5095 s offset, with correlations 0.977–0.993. This extends the waveform verification through the five additional subtitle displays and the end of the conversation. [Later dialogue in the mainland recording](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=663s)

Five briefing excerpts at 2, 15, 46, 91 and 120 s match the publisher's full Mandarin film at an offset of 3.0212–3.0214 s, with correlations 0.758–0.842. The existing publisher-film export and the newly recovered original WEM have different time origins. [Full publisher film](https://web.hycdn.cn/upload/video/20251030/d836cdada37b16eabbbdd372ed3cf809.mp4)

The respective Mandarin WEM SHA-256 values are
`cc5acb17c7789874963fc93ef5d1fddd8aed90b9aaed2b15ef4dd5b53ad7bccc`,
`b98ebbf70afbdea8785362a189854c2fcf3592b5f40336f891f4d9579350a6e0` and
`fe11338ddcae3c9b016f2349235004662503de5c37b56bb2954b2b5b05b6565e`.

## Installation-free acquisition

The film command can list and retrieve eight verified original WEMs: four scenes in English and Mandarin. It reads the selected locale's compressed package range from the archive, verifies the expanded package size and SHA-256, then resolves the original media ID and checks the recording's SHA-256. A verified package is cached for other scenes in that dub. A truncated response, changed bytes or an unexpected HTTP range fails before an output recording is written. Traditional Chinese selects the same Mandarin recordings.

```text
python scripts/endfield_film_voice.py --archive-film list --locale en --cache private-cache
python scripts/endfield_film_voice.py --archive-film fmv_e0m1_1 --locale en --cache private-cache --wem aircraft-en.wem
python scripts/endfield_film_voice.py --archive-film fmv_e0m1_3 --locale zh-Hans --cache private-cache --wem bedside-zh.wem
```

The first request transfers approximately 119 MB for English or 105 MB for Mandarin. The cache uses approximately 120 MB or 106 MB respectively. These are whole scene recordings with the original mix. Original English text bindings and English per-caption archive windows remain open; the supported Mandarin caption cuts are listed below. Current publisher update discovery is independent of this fixed historical source.

Subtitle display times cannot establish complete spoken intervals. Short replies can begin before their display cue, and neighboring utterances can form one continuous exchange. The sentence-export follow-up must compare the original acoustic boundaries with the corresponding displayed text before assigning cuts.

## Mandarin archive caption exports

The caption command exports eighteen bedside entries and six aircraft entries from their respective original Mandarin WEMs. The bedside suffixes are `01`, `02`, `03`, `04`, `05-1`, `05-2`, `05-3`, `06`, `07`, `08`, `09`, `10`, `11-1`, `11-2`, `12`, `13`, `14` and `15`. The aircraft suffixes are `01` through `06`. Text comes from the checksum-pinned historical subtitle table. The intervals use each WEM's own time origin and include the utterance lead-in and decay. Neighboring bedside exports share boundaries at 70.050, 90.550 and 100.800 s.

The short `02` reply exports 61.700–62.550 s. The existing display cue begins at film time 62.200 s, and the original audio has a different offset. Simply copying that display cue would omit the spoken lead-in. Original waveforms, gameplay captions and offline speech alignment were compared when selecting these intervals. The remaining bedside caption `20` needs further verification. Their whole scene recording is available.

The opening bedside greeting `01` exports 55.400–58.200 s. Its visible Chinese caption and the original recording identify the same greeting. Vocal separation made the words easier to identify; the analysis also retained the existing `02` and `03` replies as controls. The cut includes the introductory sound and voice decay, with a gap before `02`. The exported audio is the checksum-verified original mix; the separation model is used only for private timing research. Text remains the archived game caption. [Greeting in recorded gameplay](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=600s).

The eight additional cuts were compared with the original Chinese captions in the public gameplay. An independent speech-recognition pass on the original recording, without a speech detector discarding quiet radio voices, located the first aircraft call at approximately 2.74–4.76 s, its reply at 5.52–11.60 s and the altitude instruction at 12.98–15.86 s. The aircraft exports include padding around those utterances. The receipt and next question meet at 20.550 s. Bedside `03` exports 63.000–65.400 s; its last words extend beyond the earlier alignment estimate. Bedside `15` exports 126.200–131.900 s, before the next introduction. Recognition is timing research; exported text remains the original subtitle table. The uncertain bedside entry `20` and aircraft `07` through `11` are excluded.
[Aircraft exchange](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=5s) · [Bedside reply](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=608s) · [Bedside closing conversation](https://www.youtube.com/watch?v=jCcaIyTgo-U&t=671s)

```text
python scripts/endfield_film_voice.py --test-caption list --locale zh-Hans --cache private-cache
python scripts/endfield_film_voice.py --test-caption fmv_e0m1_3_02 --locale zh-Hans --cache private-cache --mp3 bedside-reply.mp3
python scripts/endfield_film_voice.py --test-caption fmv_e0m1_1_02 --locale zh-Hans --cache private-cache --mp3 aircraft-reply.mp3
```

The list contains 47 captions: eighteen bedside, six aircraft, twenty-one briefing captions and the two motorcycle ambush captions below. Original voice decoding requires the prepared VGMStream tool, and MP3 encoding requires FFmpeg. The five remaining aircraft cuts, one bedside cut and English archive text/cuts remain open.

All 24 aircraft and bedside captions were exported through this command without a game installation. Each resulting MP3 decoded successfully with FFmpeg. The regression fixture also checks that a failed original-voice decode preserves an existing destination and that aircraft and bedside exports request their own WEM.

### Two Mandarin motorcycle ambush cuts

The original Chinese subtitle table supplies `timeline_e1m1_1_01` and
`timeline_e1m1_1_03`, independently visible in the mainland gameplay above.
Their exports use the original Mandarin WEM at **0.000–2.400 s** and
**18.700–22.400 s**. Independent speech recognition locates the first call
at 0.76–1.66 s and the final instruction at 19.10–21.92 s. Character
alignment of the original game wording puts them at 0.826–1.753 s and
19.345–21.954 s, with mean token probabilities 0.595 and 0.728. The exports
retain the initial reaction, lead-in and decay; they do not copy subtitle
display times. The decoder disables the WEM's loop flag before cutting.
[Alignment model used for private research](https://huggingface.co/parseh/aligner-zh/tree/920ed68179700a9380364a119744e046e04fb14d)

Both cuts exported through the normal command from the verified archive
cache and decoded as nonzero 2.400 s and 3.700 s PCM. The text remains the
checksum-pinned original subtitle data. The intervening `02` caption is
visible but its speech could not be confirmed: recognition disagrees with
the caption, and forced character alignment has a mean probability of
0.055. It remains excluded even though the original text is available.

```text
python scripts/endfield_film_voice.py --test-caption timeline_e1m1_1_01 --locale zh-Hans --cache private-cache --mp3 ambush-call.mp3
python scripts/endfield_film_voice.py --test-caption timeline_e1m1_1_03 --locale zh-Hans --cache private-cache --mp3 ambush-instruction.mp3
```
