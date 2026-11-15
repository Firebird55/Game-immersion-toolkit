# Original Global Technical Alpha soundtracks

Checked November 15, 2026. A publicly archived January 2024 Global client contains the original English aircraft, bedside and Talos-II briefing recordings. Each independently matches KyoStinV's Global Technical Test playthrough. Acquisition used HTTP byte ranges and read-only package parsing, without installing or executing the archived client. [Client archive](https://archive.org/details/arknights-endfield-technical-alphawith-hotfix) · [Archive file identities](https://archive.org/metadata/arknights-endfield-technical-alphawith-hotfix) · [Global gameplay](https://www.youtube.com/watch?v=5wJdbAkjKlE)

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

The complete archived bedside movie was also retrieved. Its SHA-256 is `5c9e47bb0af3c55a10858c3715c22099f86499ba85281090b27f384f5e4ab23f`, with 61,960,960 bytes. The internal CRI directory identifies `fmv_e0m1_3.usm`. Traversal of the complete file found one CRID directory and 4,355 video packets, with zero audio packets. The separate Wwise recording above supplies its English soundtrack.

The installation-free archive command still needs these package identities, original English text bindings and per-caption export windows. Chinese package retrieval succeeded, but the corresponding Mandarin scene identities and gameplay matches remain unverified. The archive's availability and integrity checks establish a recoverable historical source. Current publisher update discovery remains independent.
