# DEATH STRANDING — original PC edition

Reviewed 2026-10-28. Steam app **1190460**, executable **`ds.exe`**. This reader
targets the original 2020 PC release. **Director’s Cut is a different edition
and its voice resource layout is not supported by this adapter.**

The installed-file reader supports original voices for ordinary dialogue,
mission calls, radio, terminal holograms and ambient barks in all twelve official
audio languages. Authored mail and interview text supports the shared
**Capture unvoiced dialogue** toggle. Cinematic subtitle pages bind to complete
original scene voice tracks through the authored sequence graph. Some cinematic
bindings remain unavailable; this is partial story coverage.

## Official languages

The [original Steam language matrix](https://store.steampowered.com/app/1190460/DEATH_STRANDING/)
lists twenty interface/subtitle languages and twelve full-audio languages.
The publisher’s [PC launch FAQ](https://505games.com/death-stranding-pc-community-faq-guide/)
and [language support article](https://support.505games.com/support/solutions/articles/150000147330-which-languages-does-death-stranding-support-)
confirm the subtitle list. Sources checked 2026-10-28; the launch FAQ is dated
2020-07-13 and the support article was modified 2023-09-12.

| Toolkit locale | Official audio | Interface/subtitles | Original-PC voice identifier |
| --- | --- | --- | --- |
| `en` | Yes | Yes | `english` |
| `fr` | Yes | Yes | `french` |
| `es-ES` | Yes | Yes | `spanish` |
| `de` | Yes | Yes | `german` |
| `it` | Yes | Yes | `italian` |
| `pt-PT` | Yes | Yes | `portuguese` |
| `ru` | Yes | Yes | `russian` |
| `pl` | Yes | Yes | `polish` |
| `ja` | Yes | Yes | `japanese` |
| `es-419` | Yes | Yes | `latamsp` |
| `pt-BR` | Yes | Yes | `latampor` |
| `el` | Yes | Yes | `greek` |
| `ar`, `cs`, `nl`, `hu`, `ko`, `zh-Hans`, `zh-Hant`, `tr` | No | Yes | Text/translation only |

European and Brazilian Portuguese, and European and Latin American Spanish,
retain distinct recordings. The native `ELanguage` table has 25 slots; unused
engine slots are not additional supported languages. Empty slots retain their
positions. All twelve audio packages were installed in this acceptance run.
Synthetic fixtures also cover each individual language mask and absent packs.
A missing pack keeps the language selectable and produces unavailable audio
with instructions to select/download the language and verify Steam game files.

## Native format and binding

The reader loads only the engine’s named category/language BIN archives, applies
documented header/chunk transforms, decompresses bounded chunks using the
installation’s own `oo2core_7_win64.dll`, and reads the shipped prefetch manifest.
Patch archives override base archives. No extracted game files or DLLs ship with
the toolkit. Sizes, counts, resource extents and virtual paths are checked.

The binding is `SentenceResource.SimpleSound` UUID → original-PC
`LocalizedSimpleSoundResource` → selected language bit → authored stream path,
UUID, channel, offset and length. Extraction resolves and compares that binding
again before reading the recording. It returns the complete authored WEM; it
does not infer cuts from text length, filenames, subtitle display time or OCR.
Changed schemas fail with verification/update instructions and changed files
retain the previous snapshot.

Cinematics use `SequenceResource.SortedEvents`, the engine's flattened event
graph, to connect participating `KJPSubtitleEventResource` sentence references
with `WwiseWemEventResource` → `WwiseWemSoundResource` → the selected
`WwiseWemLocalizedResource` data source. Each resulting study entry contains
the ordered visible subtitle pages and the **complete original scene voice
track**. Missing sources still participate in overlap checks. Conflicting
tracks and ambiguous caption orders remain unavailable.

Format references reviewed at these revisions:

- [Decima-Explorer](https://github.com/Jayveer/Decima-Explorer/tree/f22ef4cc0696872c412a10ee7c6e36fba5ad1bdc), archive transform, path hashing and prefetch layout.
- [decima-workshop](https://github.com/ShadelessFox/decima-workshop/tree/59c6ea825021d0d150fe6ddd8f3181ddb8097c92), original-PC RTTI field layouts, locale enums and localized data-source serialization.

The toolkit contains an independent bounded reader; it does not distribute the
upstream game metadata, game texts, recordings or game assets.

## Dialogue presentations

The publisher’s [2019 gameplay breakdown](https://blog.playstation.com/2019/09/12/death-stranding-new-tgs-gameplay-video/)
documents delivery conversations with holographic facility representatives.
PlayStation’s [2021 comparison article](https://blog.ja.playstation.com/2021/09/23/20210923-deathstranding/)
explicitly describes the original PC crossover missions arriving through mail.
The installed original-PC sentence families and `DSMailResource` /
`DSInterviewResource2` supply the more detailed inventory below. These are
resource counts, not a claim that every entry is reachable in one playthrough.

| Presentation | Binding/status | Capture region |
| --- | --- | --- |
| Mission dialogue and ordinary NPC conversations | Exact localized sentence WEM | Visible subtitle area; full frame also works |
| Radio and remote conversations | Authored sentence delivery mode and WEM | Subtitle area; retain full frame for varying layouts |
| Delivery terminal / hologram dialogue | Exact terminal sentence WEM | Lower subtitles, possibly alongside terminal panels |
| Sam and common ambient barks | Exact sentence WEM where text exists | Subtitle area when the game displays text |
| Cinematics | Authored sequence graph → complete localized scene voice track; unresolved scenes remain **unavailable** | Cinematic subtitle area, including ultrawide/letterbox variation |
| Mail | Explicit title/body/sender text references; **unvoiced** | Cuff Links reading panel, throughout the frame; scrolling paragraphs |
| Interviews / readable archives | Explicit title/body/description and attribution text; **unvoiced** | Archive reading panel, throughout the frame; scrolling paragraphs |
| Other menu, tutorial, HUD, item, credits and chapter text | **Unknown**, not silently treated as dialogue | Various positions; inventoried separately |
| Sentences without a text reference | Counted, not OCR-matchable; no silence inference | No authored visible text to match |

Use full-frame matching for complete implemented presentation coverage, or
independently calibrate subtitles and reading panels. A bottom-only crop misses
mail/interviews and other text panels. Authored line/paragraph breaks are
additional OCR anchors; the complete text remains the study entry. Physical
desktop capture, Windows DPI, zoom, ultrawide layouts and mobile-camera capture
were not exercised during this archive-only acceptance run.

## Native verification

The manifest contained **201,861 paths**. The archive indexes contained
**530,588 entries**. Preparation read 273 sentence resources containing 25,624
sentences, 240 mail resources, 146 interview resources and 49 UI text resources.
There were 14,577 sentences without a text reference. Nineteen sentence paths
and four UI paths in the manifest had no installed entry; they are counted,
not fabricated. Eight trial/development sentence resources were excluded.

English inventory:

| Category | Voiced | Confirmed unvoiced | Audio unavailable | Unknown |
| --- | ---: | ---: | ---: | ---: |
| Ambient barks | 1,041 | 0 | 0 | 0 |
| Mission dialogue | 197 | 0 | 0 | 0 |
| NPC dialogue | 632 | 0 | 0 | 0 |
| Radio | 2,878 | 0 | 0 | 2 |
| Terminal / hologram | 3,129 | 0 | 0 | 2 |
| Cinematic | 155 complete tracks | 0 | 249 sentences | 0 |
| Mail fields | 0 | 482 | 0 | 0 |
| Interview fields | 0 | 685 | 0 | 0 |
| Other UI localization | 0 | 0 | 0 | 10,139 |
| **Total** | **8,032** | **1,167** | **249** | **10,143** |

The 155 cinematic records group **2,916 original subtitle sentences** and
retain their IDs and individual OCR pages. Thus totals count records after
grouping, not individual subtitle pages. There were 123 installed cinematic
graph resources and 31 sentence references with conflicting track sources.

Native sentence preparation and original WEM decoding were checked for every
official audio locale. Before adding cinematic grouping, each produced 7,877
voiced and 1,167 confirmed unvoiced entries. The final English grouped index has
19,591 records, all validated against the shared dialogue model and complete
production transcript index. Blank or markup-only localization is inventoried
separately and cannot invalidate an otherwise complete prepared language.
The preparation worker also rejects malformed locale/text records before
publishing a new snapshot. Greek local play is independent of Lexirise's
supported account-language list; account features retain their own capability
checks. One ordinary
voice sample and one complete cinematic track per locale were resolved from
the current authored graph and decoded with vgmstream to nonzero PCM. This
verifies extraction/decoding; it is not a physical speaker-listening or live-OCR
acceptance claim. Synthetic locale tests additionally cover missing recordings
without classifying them as silent.

The initial sentence-only English index/validation/decode took approximately
14 seconds; subsequent language runs reused archive metadata and took about
5 seconds each. The final grouped English index took approximately 24 seconds.
Fifty-eight focused synthetic tests passed in 0.61 seconds. Private indexes,
decoder logs, sample audio and summaries remain only under ignored
`output/checks/deathstranding-native`.

## Remaining limits

Original cinematic sentence resources have null direct sound references. The
flattened sequence graph resolves 2,916 English cinematic subtitle sentences
to 155 complete original voice tracks. **249 English cinematic sentences
remain without an unambiguous track binding and cannot provide original audio
or automatic voiced capture.** Subtitle pause frames are not audio-file cut
points: playback is the complete authored scene recording, which may include
silence and non-subtitled vocal sounds. Per-sentence cinematic clipping is not
implemented. `Movies/movies.mpk` is not indexed by this reader. No movie, music,
song or nonverbal recording is guessed.

Unreferenced UI text stays unknown. The capture-unvoiced toggle includes only
the proven mail/interview text fields. Four ordinary sentence rows have neither
a direct sound binding nor readable-only proof and stay unknown. Missing
recordings, missing text and unknown voice status remain separate states.

The native manifest has additional archived/trial content and unused locale
slots. Their presence does not establish supported narrative playback. Regional
and absent-pack behavior uses the same evidenced twelve-bit locale schema;
edition changes require a separate compatibility review.
