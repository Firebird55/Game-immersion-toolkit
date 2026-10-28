# Spyro Reignited Trilogy dialogue and language audit

Reviewed 2026-10-28. Game ID: `spyro`. Steam application: `996580`.
The reader covers the PC trilogy's shipped dialogue schema for **Spyro the
Dragon**, **Spyro 2: Ripto's Rage!**, and **Spyro: Year of the Dragon**.

## Official availability and implemented locales

[Steam's publisher-maintained language matrix](https://store.steampowered.com/app/996580/Spyro_Reignited_Trilogy/)
marks interface, full audio and subtitles for every language below. The
[Activision FAQ](https://support.activision.com/spyro/articles/spyro-reignited-trilogy-faq)
confirms the PC/Steam release and its newly recorded voices and cinematics.
Both sources were checked on 2026-10-28. No additional regional PC voice pack
was established by those sources or the installed language directories.

| Language | Study locale | Unreal text directory | Wwise voice directory | Interface / subtitles / audio | Installed native check |
| --- | --- | --- | --- | --- | --- |
| English | `en` | `en-US` | `English(US)` | Yes / yes / yes | Parsed; original audio decoded |
| French | `fr` | `fr` | `fr` | Yes / yes / yes | Parsed; original audio decoded |
| Italian | `it` | `it` | `it` | Yes / yes / yes | Parsed; original audio decoded |
| German | `de` | `de` | `de` | Yes / yes / yes | Parsed; original audio decoded |
| Spanish (Spain) | `es-ES` | `es` | `es` | Yes / yes / yes | Parsed; original audio decoded |
| Arabic | `ar` | `ar` | `ar` | Yes / yes / yes | Parsed; original audio decoded; one unavailable event |
| Danish | `da` | `da` | `da` | Yes / yes / yes | Parsed; original audio decoded |
| Dutch | `nl` | `nl` | `nl` | Yes / yes / yes | Parsed; original audio decoded |
| Finnish | `fi` | `fi` | `fi` | Yes / yes / yes | Parsed; original audio decoded |
| Norwegian | `no` | `nb` | `no` | Yes / yes / yes | Parsed; original audio decoded |
| Polish | `pl` | `pl` | `pl` | Yes / yes / yes | Parsed; original audio decoded |
| Portuguese (Brazil) | `pt-BR` | `pt` | `pt` | Yes / yes / yes | Parsed; original audio decoded |
| Spanish (Latin America) | `es-419` | `es-419` | `latam` | Yes / yes / yes | Parsed; original audio decoded |
| Swedish | `sv` | `sv` | `sv` | Yes / yes / yes | Parsed; original audio decoded |

All 14 packs were present in this native audit. The supported-language list is
independent of local pack discovery. Synthetic tests also remove a selected
voice pack: its voiced rows become **unavailable**, with Steam language/download
repair guidance, while explicitly text-only rows remain unvoiced. A missing text
pack produces a missing-pack preparation error. The game has no established
Chinese or Japanese PC localization in this matrix; those are not invented.

## Authored formats and bindings

The installed game uses three unencrypted Unreal pak version 4 archives,
compressed with zlib, under `Falcon/Content/Paks`. The native reader checks the
archive index checksum, file/header boundaries, compression bounds, package
version, property sizes and localization string indexes. It reads assets in
place and never writes into the game installation. No extractor download is
required for this adapter.

`VoiceLocalizations` and `MenuLocalizations` use locres version 1. Dialogue is
serialized as tagged `TfbDialogueTableRow` DataTables with `Text`, `DisplayName`,
`VoicedLine`, `LipSyncAnim` and `IsSubtitle`. Translation joins use the authored
FText namespace/key and matching source hashes, consistent with
[Epic's localization identity model](https://dev.epicgames.com/documentation/unreal-engine/text-localization?application_version=4.27).
No ordinal or similarity-based translation pairing is used.

The Wwise version 128 banks bind each supported event through its serialized
single Play action to one localized Vorbis source. Explicit voice object names,
or cinematic row event names, identify the event; the reader verifies that event
in the selected-language bank before making a binding. Resident media uses the
bank's DIDX/DATA offsets; streamed media uses its exact source ID. Switches,
random containers, multiple-action events and prefetched fragments are not
misrepresented as complete performances. Extraction revalidates the selected
locale, event, source ID and media location. Original WEM playback uses the
existing [vgmstream Wwise decoder](https://github.com/vgmstream/vgmstream/blob/master/src/meta/wwise.c).

Separate `tfbSubtitleDataTableRow` tables contain cinematic DataTable references,
row names, split indexes and scene timeline times. All 640 installed references
resolve to their dialogue rows. Localized `{N}` pages become OCR alternatives
for the complete utterance. Scene timeline times are **not** offsets into each
individual voice file; playback preserves the complete original utterance.

## Native inventory and coverage

The audit found 129 dialogue DataTables and 114 cinematic subtitle DataTables.
The following are English baseline counts; every official locale has all 2,286
dialogue texts and the same 421 explicitly text-only rows.

| Game | Dialogue rows | Original voices | Explicitly text-only | Cinematic rows included |
| --- | ---: | ---: | ---: | ---: |
| Spyro the Dragon | 249 | 249 | 0 | 201 |
| Spyro 2: Ripto's Rage! | 864 | 681 | 183 | 124 |
| Spyro: Year of the Dragon | 1,173 | 935 | 238 | 162 |
| Total | 2,286 | 1,865 | 421 | 487 |

The cinematic classification follows `IsSubtitle` and explicit cinematic table
references; it includes authored in-engine scenes. The other 1,378 voiced rows
remain ordinary dialogue. This preserves tutorials, repeated interactions,
NPC dialogue and short utterances without guessing a more specific bark,
quest or collectible category from a filename.

Each locale has 129 localized voice banks. Thirteen locales expose 1,894
supported voice events and bind all 1,865 voiced dialogue rows. Arabic exposes
1,893 events: one Spyro 3 ordinary-dialogue event is absent, so **1,864 rows are
voiced and one is unavailable**. No alternate language is substituted. Of the
English dialogue recordings, 45 reside inside banks and 1,820 are streamed WEMs.

The shipped `tx_` row family explicitly has null `VoicedLine` and contains the
421 text-only dialogue rows. In contrast, 206 voiced cinematic rows also have a
null object field but resolve to authored `vo_` bank events. Null audio fields
alone therefore never establish silence. Missing `vo_` events or recordings
remain unavailable; unrecognized relationships remain unknown.

Another 2,054 nonempty menu/epilogue localization entries are retained with
**unknown** voice status, separate from confirmed unvoiced dialogue. Localized
banks also contain 29 supported events without corresponding dialogue text.
These are counted in the inventory; they cannot be captured from on-screen
text without an authored transcript. Nonverbal vocalizations and sound effects
do not receive fabricated sentences.

## Verification and capture limits

Native read-only verification parsed the installed text and localized bank
schemas for all 14 locales, resolved their event/media bindings and decoded one
original recording in each locale. The sample set covers all three games and
both embedded and streamed media. The 14 clips decoded as nonempty 48 kHz mono
audio. This is representative playback validation, not an assertion that every
recording was listened to. The all-language inspection and sample decode run
took approximately 10 seconds on the audit PC; ordinary English index creation
took approximately four seconds.

Synthetic regression tests cover pak compression and corruption, UTF-16 locres,
tagged tables, all locale directories, all three games, cinematic page matching,
embedded/streamed voice binding, missing packs, graph ambiguity and extraction
reference tampering. Test data is generated in the test directory. Native
evidence, local paths, game text and decoded clips remain only in ignored
`output/checks/spyro-native`; none is distributed with the toolkit.

Installation validation uses root `Spyro.exe`; the actual gameplay process is
`Spyro-Win64-Shipping.exe`. Ordinary dialogue uses a lower-screen dialogue box;
cinematics use lower-screen subtitles with speaker headers. Enable subtitles
in the game's Options menu and use capture preview to include both forms.
Window capture, Arabic OCR rendering, ultrawide, Windows DPI and physical mobile
capture were not validated by this archive audit. Capture defaults remain
starting regions requiring the normal per-PC preview/calibration workflow.

## Remaining limitations

- One installed Arabic voice event is unavailable; verification can rule out a
  damaged download, but the reader never substitutes another language.
- Twenty-nine localized events have no authored dialogue text in these tables;
  ambient speech without visible text cannot be matched by OCR.
- UI/epilogue localization is unknown voice status, not confirmed silence.
- Only the evidenced PC pak/locres/Wwise formats are implemented. Console packs,
  unsupported mods and future format revisions require a compatibility review.
- Native OCR, capture bounds and device/DPI acceptance remain separate checks.
