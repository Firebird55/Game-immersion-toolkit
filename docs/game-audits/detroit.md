# Detroit: Become Human narrative and language audit

Audited 2026-10-28 against the installed Windows Steam edition (app 1222140),
the [Steam language matrix](https://store.steampowered.com/app/1222140/Detroit_Become_Human/)
and [Quantic Dream's PC language specification](https://shop.quanticdream.com/collections/detroit-become-human/products/detroit-become-human).
The inspection reads the owner's installation; game files, accounts and settings
are unchanged. No original game text, recordings or assets are published.

## Official language matrix

Steam and the publisher agree on twelve full-audio languages and twenty-four
interface/subtitle languages. All twelve official dubs remain selectable even
when their local files are absent. The installed edition bundles the twelve
dubs; there is no separate regional dub in these two PC specifications that is
missing from the implementation.

| Language | Locale | Native code | Interface/subtitles | Full audio | Reader implementation |
| --- | --- | --- | --- | --- | --- |
| English | en | ENG | Yes | Yes | Supported |
| French | fr | FRE | Yes | Yes | Supported |
| Italian | it | ITA | Yes | Yes | Supported |
| German | de | GER | Yes | Yes | Supported |
| Spanish, Spain | es-ES | SPA | Yes | Yes | Supported |
| Arabic | ar | ARA | Yes | Yes | Supported |
| Japanese | ja | JPN; legacy JAP | Yes | Yes | Supported |
| Polish | pl | POL | Yes | Yes | Supported |
| Portuguese, Portugal | pt-PT | POR | Yes | Yes | Supported |
| Portuguese, Brazil | pt-BR | BRA | Yes | Yes | Supported |
| Spanish, Latin America | es-419 | MEX | Yes | Yes | Supported |
| Russian | ru | RUS | Yes | Yes | Supported |
| Czech, Danish, Dutch, Finnish, Greek, Hungarian, Korean, Norwegian, Swedish, Turkish, Traditional Chinese, Simplified Chinese | cs, da, nl, fi, el, hu, ko, no, sv, tr, zh-Hant, zh-Hans | CZE, DAN, DUT, FIN, GRE, HUN, KOR, NOR, SWE, TUR, CHI, SCH | Yes | No | Official translation text |

The installed localization tables also contain a `CRO` field and empty legacy
locale fields. Their presence is not an official PC language announcement, so
they are not advertised as additional supported languages. Japanese `JAP` and
`JPN` are evidenced old/current identifiers for the same locale. Missing Arabic
or Japanese fields in an old resource never trigger an English voice fallback.

## Native format and binding

The installation contains one version-18 BigFile index with 373,748 resources,
thirty archive data parts, 1,327 standalone localization resources, 80,976
FlowDialog resources and 80,976 original sound resources. The sound total is
6,748 performances per official dubbed language and includes nonverbal or empty
subtitle resources. It is not a count of capture-ready sentences.

All 3,265 data-container dependency headers were inventoried: none supplies an
embedded localization reference. The reader therefore traverses every standalone
localization resource. Of these, 1,266 use localization version 6 and 61 use
version 5; the latter also include legacy component versions 4 and 5.

Audio uses this explicit authored chain:

1. A locale's localization key names an external type-4091 FlowDialog dependency.
2. That FlowDialog names one external type-1033 sound dependency.
3. Its `CSNDDATA` resource contains original Wwise RIFF audio and subtitle timing
   pairs. The sound's authored name must agree with both key and native locale.

The key/name check verifies an existing dependency; it never guesses a recording
from a similar filename. Extraction rechecks the complete chain. Timed cue
identities, numeric cue ranges and explicit millisecond timecodes are preserved.
Repeated markers, missing cue timings and subtitle holds outside the recording
use the complete verified performance with authored OCR pages. They never create
an invented cut. Translation joins use the same resource/key/cue identities.

## Presentations and capture coverage

| Presentation | Implemented behavior and remaining limits |
| --- | --- |
| Main, optional and branching conversations; alternate endings | Every discovered localization resource is indexed independently of the player's current branch. Exact original performances are retained. The reader does not reconstruct branch reachability or certify every branch through gameplay. |
| In-engine cinematics, phone conversations and narration | Covered through the same explicit subtitle/performance schema. A camera cut does not change the audio binding. |
| Passersby, background conversation and television dialogue | Authored passersby/TV keys receive an ambient category; other original speech remains in the subtitle category. Nonverbal audio without subtitle text cannot produce a transcript. |
| Dialogue choices | Chapter text-only fields with flag 2 and no speech pointer are unvoiced. A choice label never inherits the voice of its later response. |
| Thought/action prompts | Authored `THOUGHTS` and `GUI_ACTION` text widgets with no speech pointer are unvoiced choices. These are on-screen prompts; they are not classified as a spoken inner monologue. |
| Investigation clues | Authored observation widgets are retained as unvoiced readable text. |
| Magazines and news pages | Native magazine/news titles, subtitles and article fields are retained as unvoiced readable text. Page fragments still need a unique exact text match; a fragment does not invent a shortened article. |
| Moving choices, world labels and full-page writing | Keep capture on the complete game window. Spoken subtitles use the subtitle capture path; the opt-in unvoiced path scans the full frame. A bottom-only source crop cannot cover these presentations. Native DPI, unusual aspect ratios, physical mobile capture and every moving layout still require acceptance checks. |
| Menus, flowcharts and unrelated interface strings | Excluded from narrative capture. |
| Image-only writing, bonus-video soundtracks and distinct comic panels | No verified independent per-caption text/audio join. They are outside the supported text/audio schema; complete videos or synthesized speech are not substituted. |

Repeated short wording remains subject to the toolkit's ambiguity safeguards.
Unknown or missing voice pointers never establish silence. Shipped text with an
unresolved performance stays unavailable, including potentially unused resources;
the reader does not claim that every such record is reachable during gameplay.

## Verification

Complete native preparations and one production-decoder sample in each of these
five languages passed:

| Source | Total records | Voiced cues | Authored unvoiced records | Unavailable speech | Validated nonempty performances |
| --- | ---: | ---: | ---: | ---: | ---: |
| English | 17,821 | 11,001 | 5,634 | 1,186 | 4,806 |
| French | 17,758 | 10,999 | 5,621 | 1,138 | 4,806 |
| Italian | 17,417 | 11,004 | 5,556 | 857 | 4,806 |
| German | 17,415 | 11,002 | 5,556 | 857 | 4,806 |
| Spanish, Spain | 17,418 | 10,998 | 5,556 | 864 | 4,809 |

The English voiced total includes 459 explicitly categorized ambient cues. Its
text-only total contains 4,536 choices and 1,098 readable fields. Nineteen English
paragraphs require complete performances rather than individual cue cuts.
Of its 1,186 unavailable records, 857 have a declared performance absent from
the archive index and 329 have no verified voice alias. No missing sound target
was found for the resolved English performance resources.

One explicitly bound original recording also decoded successfully in **each of
all twelve official dubbed languages**, including Arabic, Japanese, Polish,
both Portuguese variants, Latin American Spanish and Russian. Every sample
produced nonzero 48 kHz mono PCM, lasted 35.468771 seconds and retained three
authored timing pairs. All twelve pack probes reported present. These are actual
installed-file checks, while full native index counts above cover five languages;
the remaining seven do not have a claimed complete native preparation run.

Focused [synthetic regressions](../../backend/tests/test_detroit_assets.py)
exercise every official dubbed locale, original audio extraction, authored
timings and ranges, legacy Japanese identifiers, missing/absent packs, malformed
archive bounds, inconsistent locale bindings, unsupported metadata, unresolved
speech, text-only narrative categories and system-menu exclusion. Synthetic
fixtures contain no game text or audio. The reader and bounded format helpers
are [detroit_assets.py](../../backend/detroit_assets.py) and
[detroit_format.py](../../backend/detroit_format.py).
The 25 focused synthetic tests passed in 0.69 seconds. Comprehensive regression
and packaging checks belong to GitHub-hosted CI.

Private snapshots, decoded probes, counts and timings remain under ignored
`output/checks/detroit-native/`. Native asset checks and representative decoding
are distinct from complete gameplay, listening acceptance, browser/mobile
capture and release CI.

## Missing packs and updates

A missing locale table reports `missing_voice_pack` with a Steam install/verify
action. If text exists but its recording does not, the text remains unavailable
and preparation gives the same corrective instruction; certified text-only
choices remain usable. A bounded probe that cannot establish a pack reports
unknown, never a fabricated missing or installed result.

Unknown index/localization/voice schemas report `unsupported_game_format` with
update-and-verify guidance. Archive fingerprint changes during preparation report
`game_files_changed`. Bounds, duplicate identities, pointer scope, locale names,
finite timing values and trailing metadata are validated before publication.
