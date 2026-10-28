# METAL GEAR SOLID V: THE PHANTOM PAIN

Audit date: 2026-10-28. Steam app **287700**, game ID `mgsvtpp`, executable
`mgsvtpp.exe`. The adapter reads the local installation; it never changes game
files or executes its Lua scripts. Metal Gear Online uses `mgsvmgo.exe` and a
separate content tree, and is outside this adapter.

## Official languages and edition selection

| Locale | Official voice | Official interface/subtitles | Implementation and verification |
| --- | --- | --- | --- |
| English (`en`) | Yes | Yes | Original installed English edition indexed; representative native audio decoded and converted through the production MP3 path. |
| Japanese (`ja`) | Yes | Yes | Implemented from the shared Fox schemas, `JpnVoice/JpnText` identifiers and synthetic archive/media tests. Japanese text was read from the English installation; the Japanese voice edition was absent and has no native playback claim. |
| French (`fr`), Italian (`it`), German (`de`) | No | Yes | Original installed text read as translation targets. |
| Latin American Spanish (`es-419`) | No | Yes | Original `SpaText` text read; Steam specifies the regional label. |
| Brazilian Portuguese (`pt-BR`) | No | Yes | Original UTF-8 `PorText` text read; Steam specifies the regional label. |
| Russian (`ru`) | No | Yes | Original ISO-8859-5 `RusText` subtitles read. This is not a complete Russian dub. |

The [Steam language matrix](https://store.steampowered.com/app/287700/METAL_GEAR_SOLID_V_THE_PHANTOM_PAIN/)
lists eight interface/subtitle languages and English/Japanese audio. KONAMI's
[PC voice-language FAQ](https://www.konami.com/mg/mgs5/tpp/faq/item.php?id=49&lang=en&region=ac)
explicitly confirms both English and Japanese PC versions; its
[support specifications](https://eu-support.konami.com/hc/en-gb/articles/9666546497047-Metal-Gear-Solid-V-The-Phantom-Pain)
confirm that distinction. These sources were checked on the audit date.

Select the voice edition in Steam Properties → Language and finish its download
before preparation. The adapter checks the selected edition's exact `common.subp`
marker, rather than treating Japanese text in an English installation as a
Japanese voice pack. Missing Japanese audio produces an actionable missing-pack
failure while retaining Japanese as a supported choice. English recordings are
never substituted for that choice. A mixed edition with both markers is rejected
because its original audio language cannot be established safely.

For display text, KONAMI documents Title Menu → OPTIONS → Display Settings →
Language Settings in its [display-language FAQ](https://www.konami.com/mg/mgs5/tpp/faq/item.php?id=25&lang=en&region=ac).
Regional console dictionaries containing Chinese, Korean or Arabic identifiers do
not establish PC availability or additional complete voice editions. Character
speech in Russian, Afrikaans and other story languages remains part of the chosen
original edition; it does not establish a full dub in those languages.

## Native formats and binding rules

- Read-only SQAR v1 directory/deobfuscation, bounded zlib decompression, FPK/FPKD
  children, and patch precedence. Filename/substring matching does not replace a
  verified archive hash. Unrelated hexadecimal runtime `.dat` files are excluded.
- SUBP packages carry IDs, authored text pages, character IDs and timing fields.
  Native header variants `0x12`, `0x13`, `0x1b`, and three legacy Japanese tables
  are covered. Language tags select UTF-8, Latin-1 or ISO-8859-5 decoding. LANG
  tables include little-endian `.lng` and big-endian `.lng2` variants.
- SBP contains BNK, STP and SAB. Both complete embedded BNK media and streamed STP
  Wwise RIFF media are enumerated. Original `labl` values join to Fox's legacy
  CityHash64 1.0.3 `StrCode32` subtitle IDs, including evidenced lowercase ID
  normalization for uppercase audio labels. The original label is retained and
  revalidated during extraction. Conflicting text IDs are not guessed.
- Cassette tracks require both their exact `tp_*` archive path hash and their
  exact subtitle ID. All 190 subtitle-bearing cassette tracks found in the
  installed build bind this way. Music-only tracks without matching subtitles
  do not become dialogue records.
- Cinematic audio is reconstructed from FSM `SND` packets while animation packets
  stay untouched. SAND metadata supplies scene names. An existing exact
  movie name plus an exact subtitle ID provides one binding route. The full original
  scene mix is retained, including music/effects and multichannel audio. FOX2
  `DemoData` entities also provide an explicit `demoStreamPath` and original
  `audioPath`; the latter's identifier establishes the subtitle identity even
  when the streamed movie was renamed. These typed fields must belong to the
  same entity and their local strings must reproduce their Fox hashes. The
  relationship is revalidated during extraction and takes precedence over a
  coincidentally matching movie filename. Each authored page keeps a separate
  caption identity, so Current line never reveals the rest of a scene or tape.
  Translations join only single-page performances or identical authored subtitle
  intervals, never page order alone. Playback of multi-page dialogue is labelled
  as the full original track and its encoding is shared across captions. No audio
  cuts are inferred from subtitle length, page order or unverified timing units.
- LANG-only UI/readables/choice labels are `unknown`. Subtitle rows with no
  recording or conflicting identity are `unavailable`. Every distinct conflicting
  source text is retained separately; no ambiguous audio or translation is attached.
  The audit establishes
  **no confirmed unvoiced rows**; missing audio never implies silence.

The adapter and shared helper follow these primary format implementations:
[GzsTool](https://github.com/Atvaark/GzsTool/tree/384cb81155ada82716c21b95035b5306b1c0d9cf),
[FoxEngine.TranslationTool](https://github.com/Atvaark/FoxEngine.TranslationTool/tree/7ba31f92c9d3f7d309c9caaa01d2ed6da386a57b),
[legacy CityHash](https://github.com/Atvaark/CityHash),
[StpTool](https://github.com/kapuragu/StpTool/tree/f7438b5d1153c1ae71f4a7a584b12d33f8aa2778),
and [FsmTool](https://github.com/BobDoleOwndU/FsmTool/tree/a3e9ec0fd6c4c043a56a38e82d6da9754c0ed6b2).
The typed scene metadata reader follows
[FoxTool](https://github.com/Atvaark/FoxTool/tree/be69b04acfaa26725864de1908e2059e7b923676).
The implementation incorporates native format differences explicitly, including
TPP's stored-length-first SQAR entry header. No tool binaries or game assets are
redistributed with the adapter.

## Coverage and native evidence

The read-only English install audit used Steam build **24176213**. A complete
index with all eight text languages and scene entities took approximately **46 seconds** with warm
filesystem caches; this is not an installation-time performance guarantee.

| Installed inventory | Count |
| --- | ---: |
| Selected archive entries | 38,629 |
| SUBP packages inspected, including duplicated FPK residents | 1,209 |
| Localization tables inspected | 328 |
| SBP packages / BNK packages / STP packages | 215 / 216 / 188 |
| Streamed / embedded / standalone media entries | 30,896 / 6,521 / 255 |
| Prefetch fragments excluded from playback | 69 |
| Embedded non-RIFF media inventoried separately | 10 |
| Unique source subtitle IDs | 23,771 |
| Original voice caption records | 31,725 |
| Subtitle records with unavailable or conflicting audio | 5,642 |
| Source IDs with conflicting text, all distinct variants retained | 103 |
| Localization-only unknown records | 16,024 |
| Bound cassette tracks | 190 |
| Authored FOX2 movie/audio relations inspected | 230 |
| Bound cinematic streams / inventoried FSM streams | 133 / 235 |
| Renamed cinematic variants bound through authored audio identifiers | 73 |

The final 53,391-record page index passed the complete shared model and production
matcher. These caption counts replace the earlier performance-group counts;
they do not mean additional recordings were discovered. Of the voiced English
captions, 2,379 lack an exact French page interval in the inspected tables and
retain no guessed French translation.

Radio, mission/base dialogue, enemy conversations, ambient barks, character orders
and isolated cinematic dialogue all pass through the same complete soundbank
enumeration. Classification is retained where source packages or a named original
bank establish it; shared IDs can have multiple dialogue channels. Inventory
counts are not a claim that every game utterance has an official caption.

Five original recordings passed archive extraction, vgmstream decoding, nonzero
PCM checks, and the production FFmpeg/MP3 conversion path:

| Example class | Decoded format | Duration |
| --- | --- | ---: |
| Bark/order | Mono, 48 kHz | 3.002 s |
| Radio | Mono, 28 kHz | 3.883 s |
| Cassette | Stereo, 48 kHz | 299.004 s |
| Cinematic scene mix | Eight channels, 48 kHz | 107.000 s |
| Cinematic with an authored movie/audio alias | Eight channels, 48 kHz | 15.667 s |

Private indexes, byte hashes, PCM checks and original media remain under ignored
`output/checks/mgsvtpp-native/`. No audio, transcripts, installation paths or
account diagnostics belong in this report. Automated synthetic regressions cover
both voice locales, all text encodings, exact extraction, missing packs, complete
paging, case normalization, tapes, packetized scenes, typed FOX2 aliases,
conflicting subtitle variants, prefetch exclusions, archive traversal/bounds,
truncation and big-endian localization.

## Capture and remaining gaps

Use `mgsvtpp.exe` as the capture target. Start with full-frame matching to cover
gameplay/radio/barks, cinematics and cassette/iDroid presentations. Independent
calibrated regions can reduce noise once each presentation is measured; a
lower-center crop alone is not complete coverage. Include two-line captions and
speaker labels, and measure the cassette/iDroid panel separately. UI choice labels and tape titles are
not assumed to be spoken merely because they appear on screen. Each scene/tape
subtitle page advances Current line independently.

This audit did not launch the game or validate a physical capture window, Windows
DPI, ultrawide framing, UI zoom or mobile screenshot geometry. These are
calibration starting points, not measured native acceptance results. Validate
both displayed English and Japanese captions and the active game's independent
calibration in the capture preview.

Remaining gaps are explicit: Japanese voice playback is unverified without its
official pack; 102 cinematic streams still have no established subtitle binding
(some can contain no captioned dialogue); 9,198 Wwise labels have no matching indexed source
subtitle ID; 6,150 complete media entries have no subtitle label; and some
duplicate subtitle IDs have conflicting official text. The adapter does not
assign arbitrary FSM event hashes or remove filename suffixes to manufacture a
cinematic match. It also does not invent subtitles for nonverbal audio, include
Metal Gear Online, or call ambiguous localization confirmed silent.
