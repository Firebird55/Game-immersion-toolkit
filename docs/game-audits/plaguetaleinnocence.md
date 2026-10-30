# A Plague Tale: Innocence language and narrative audit

Audit date: 2026-10-28. Scope: original Windows Steam game **752590**, with
`APlagueTaleInnocence_x64.exe`, `LangDef.tsc`, `TRTEXT`, `All.psc` and
`SOUNDBANKS`. Requiem and console editions are separate products.

## Official languages and installation

The [Steam language matrix](https://store.steampowered.com/app/752590/A_Plague_Tale_Innocence/)
lists English, French and German as full audio languages. Its fourteen interface
and subtitle languages are English, French, German, Italian, Spanish (Spain),
Spanish (Latin America), Czech, Polish, Brazilian Portuguese, Russian, Japanese,
Korean, Simplified Chinese and Traditional Chinese. The
[publisher's pinned launch FAQ](https://steamcommunity.com/app/752590/discussions/0/1795152172941160860/)
also identifies the three original voice languages. The current Steam text list
includes languages added after that FAQ. Both sources were reviewed on the audit
date. The [Japanese publisher's PlayStation listing](https://store.playstation.com/ja-jp/concept/231037)
also lists English, French and German audio, with Japanese display text; it does
not establish an additional Japanese dub. No additional official regional voice
pack was established, and console package formats were not tested.

The installed `LangDef.tsc` independently confirms this mapping:

| Study/original audio | Text file | Native Wwise language | Native verification |
| --- | --- | --- | --- |
| English (`en`) | `tt01.pc` | `English(US)` | Index and sample decoding passed |
| French (`fr`) | `tt02.pc` | `French(France)` | Index and sample decoding passed |
| German (`de`) | `tt04.pc` | `German` | Index and sample decoding passed |

The remaining text IDs are `05` Italian, `03` Spanish, `20` Latin American
Spanish, `11` Czech, `08` Polish, `14` Brazilian Portuguese, `17` Russian,
`00` Japanese, `09` Korean, `22` Simplified Chinese and `21` Traditional Chinese.
They are translation targets, not additional original voice selections. Their
manifest entries reference English audio; the adapter does not relabel it as a
local dub. Fan translations, AI narration and community voice replacements are
outside this audit.

Choose the original game's folder in Setup and prepare English, French or
German. Select the same voice and subtitle language in the game for spoken
capture; enable subtitles. The audited Steam installation contains all three
audio languages inside shared packages, rather than separate language folders.
Missing packages keep all three selections supported and report unavailable
recordings. Finish Steam downloads, verify the installed files, and prepare the
language again. No game files, settings, saves or accounts are modified.

## Authored bindings and coverage

`TRTEXT/tt*.pc` contains UTF-8 `TT` entries keyed by stable identifiers.
Identifiers are case insensitive, including mixed-case names in shipped files.
`VO__...` maps to the Wwise `play_<identifier>` event hash. The adapter validates
Wwise version 132, the bank ID and the language hash, then follows exactly one
event to one Play action and one localized streamed Vorbis source. Package
language numbers are resolved through each package's own UTF-16 language map;
they are not assumed to match between files.

`All.psc` contains a bounded raw LZ4 script bundle. Its `LoadFilePackage` order
loads `VO_D1_MEDIA` after the character packages. The last loaded package wins,
matching the Wwise packaged-file resolver. The native English inventory contains
900 media IDs per original language shared with this update package; sample contents differ from the
base recordings. The adapter honors that authored precedence and revalidates it
at extraction. It never selects an archive alphabetically.

| Presentation | Authored evidence and implemented behavior | Capture area / limitation |
| --- | --- | --- |
| Main conversations, interactions, commands, helpers | `VO__` text to verified original Wwise performance | Subtitle area; complete recording retained |
| Ambient conversations, patrol speech and barks | Same bindings; `CHATTER`, `PATROL` and other authored families | Only performances with actual subtitle prose can match OCR |
| In-engine cinematics | `RTC` dialogue identifiers share the same text/event/source graph; 79 RTC DPC archives inventoried | Uses subtitle matching; scene animation/timeline internals are not decoded |
| Prerendered video | Four installed Bink files are publisher/developer/startup logos | No separate narrative video subtitle track was found; no fabricated timings |
| Herbarium, gifts and curiosities | `AddLootItem` names and descriptions bound to codex fields, with the fixed pickup sound effect | Confirmed unvoiced menu prose; 50 collectibles, 100 name/description records |
| Inventory descriptions | Authored `AddLootItem` text fields | Confirmed unvoiced; 16 populated records |
| Crafting and upgrade lore | `AddRecipe` name, description and lore fields | Confirmed unvoiced; 63 populated records |
| Menus, credits, tutorials, objectives and loading text | Official localization retained | Voice status stays unknown unless an explicit narrative field establishes it |
| Non-subtitled speech and nonverbal performances | Voice event inventory retained in counts; identifier placeholders excluded from study text | No invented transcript or speech recognition substitute |
| Branching choices, comics, radio/tapes, textured world writing | No separate verified format or binding established in this installation | No coverage claim; lack of a recording never establishes silence |

The [publisher's gameplay material](https://www.focus-entmt.com/en/news/a-plague-tale-innocence-debuts-eight-minutes-of-new-uncut-gameplay-footage)
documents the adventure, exploration, crafting and companion interaction
context. The [developer's game page](https://www.asobostudio.com/games/plague-tale-innocence)
identifies the original game and its narrative/stealth presentation. These
sources support the presentation inventory; the bindings and counts above come
from the owner's installed files, not promotional video timing.

## Capture regions and verification limits

Use full-window capture, or independent calibrated regions for subtitles and
readable panels. A subtitle-only crop cannot cover codex and crafting prose.
Enable **Include unvoiced dialogue** for the confirmed menu narrative records.
Unknown UI rows remain excluded from that toggle.

The authored subtitle dialog places its `SlotRoot` at the property tuple
`(0.5, 0.9, 1, 0.1)` with reference point `(0.5, 1)`. The codex description has
parent-relative position/size `(0.5, 0.17, 0.85, 0.78)` and vertical clipping.
Crafting lore uses parent-relative `(0, 0.325, 0.7, 0.75)`. These are engine UI
properties, **not measured screen capture rectangles**; parent transforms,
wrapping, font overrides and viewport scaling still matter. Long descriptions
may need scrolling to expose all text.

No local game window was launched and no actual screen-region screenshot,
physical OCR, Windows DPI, ultrawide/letterbox or mobile-camera capture was
verified in this audit. Exact captured bounds remain a native acceptance task.
Native asset parsing and PCM decoding do not establish those results.

## Reproducible evidence

Each installed original language resolves 9,569 simple voice events and 9,569
effective media IDs across ten localized banks. There are 9,564 `VO__` text
identifiers; 1,161 contain identifier placeholders instead of subtitle prose.
Together with five events without a corresponding TT identifier, 1,166 events
have no usable selected-language subtitle prose. No unsupported event topology
or missing recording was found among the 8,403 voiced study records.

| Result | English | French | German |
| --- | ---: | ---: | ---: |
| Voiced records | 8,403 | 8,403 | 8,403 |
| Cinematic subset | 779 | 779 | 779 |
| Ambient subset | 6,742 | 6,742 | 6,742 |
| Other dialogue subset | 882 | 882 | 882 |
| Confirmed unvoiced records | 179 | 179 | 179 |
| Unknown UI records | 1,510 | 1,482 | 1,380 |
| Total normalized nonblank records | 10,092 | 10,064 | 9,962 |

All fourteen text tables were parsed and joined during each native language
probe. Indexing with those targets took approximately 1.4–1.9 seconds per
language on the audit host. Two distinct original performances per language
(a patched cinematic and an unpatched ambient line) decoded using the existing
verified vgmstream executable: six mono 48 kHz PCM samples, approximately
2.08–3.85 seconds. This verifies extraction and decoding, not listening or
physical playback.

`backend/tests/test_plague_tale_assets.py` passes fourteen focused synthetic
tests. They cover all official originals and translation identifiers, missing
packs and media, package-local language numbers, update precedence, malformed
containers, bounded LZ4, Unicode/case-insensitive TT identifiers, unsupported
event graphs, extraction revalidation, four voice states and the existing
`LocalDialogue` / `MultilingualTextIndex` contracts.

Compact private results live under ignored `output/checks/plaguetale-native`.
Native script/text/audio scratch stays outside the repository on the designated
artifact drive. Only synthetic fixtures and code are committed; no original
game text, recordings, archive dumps or personal installation paths are shipped.
