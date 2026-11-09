# Zenless Zone Zero dialogue audit

## November 9, 2026 · Dialogue from one Global launcher release

The publisher's 3.3.0 base (revision 19316624) contains the Perform scene
references, their resource catalog, subtitle tables and original Wwise packages.
The Perform table named 31,069 dialogue scene paths. The resource catalog
resolved 30,736 paths across 18 blocks. The 48,849,768 bytes of selected
scene bundles contained 221,699 dialogue records, including 59,316 with an
authored voice reference. Of the 221,561 distinct subtitle IDs, 217,629 had
both English and Simplified Chinese, and 213,899 had text in all 13 locales.
These figures cover conversations, choices, ambient lines and narration
in the resolved dialogue scenes. The count of voice references precedes audio
package matching. [Publisher release manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)

The released scenes contained 1,619 chapter 240 records. In package 10126,
49 subtitle IDs resolved to an exact original file in every dub. None of those
49 had text in all 13 base locales. Three of the 49 were downloaded and decoded
in all four languages. Their Japanese recordings were already in the release,
while their Japanese subtitles first appeared in the inspected later override.
Fetching that Global hotfix on a fresh device remains open.
[Publisher chapter announcement](https://zenless.hoyoverse.com/m/en-us/news/166963)

From a source checkout, the following command follows the released Global
launcher branch, reads the checked scene and translation tables, and searches
every released package for the requested dub. Supply the compiled ZZZ reader
from the toolkit toolchain and choose private cache and output directories.
The result contains the available original translations, a WEM for each requested
dub and a receipt with build, package, file ID and SHA-256. Repeating `--dub`
selects multiple recordings. Omitting it requests all four. Both Chinese scripts
use the Mandarin recording.

```text
python scripts/probe-zzz-publisher.py Galgame_Chapter0_11_01_01 --reader <toolchain>/upstream/galgame-perform.mjs --cache <private-cache> --output <new-private-folder>
```

This query returned Nicole's authored source, all 13 translations, and four
complete recordings that decoded to nonzero PCM. Their durations were 4.700 s
in English, 6.556 s in Japanese, 4.700 s in Korean and 5.195 s in Mandarin.
The same command for `Main_GalGame_Chapter240_124000005_001` returned four
original recordings and 12 translated strings from the same build.

The command requires a unique authored scene source and a unique matching file
in the selected dub. It supports direct source paths and the evidenced GalGame
speaker directories. Conditional voices, comic panels and cinematic events
require their own bindings. Automatic desktop and phone setup from the publisher,
and acquisition of in-version Global overrides, remain open.

## November 8, 2026 · Publisher sources and subtitle variants

The released Global Windows 3.3.0 branch serves the game TextMaps directly.
Follow the HoYoPlay branch into its Sophon game manifest and read
`StreamingAssets/data_version`. For this release, the 25 listed
`Blocks/Data` files contained the 13 base locale tables. The check downloaded
those files from the publisher and verified the manifest, chunks and assembled
files against their MD5s. In each Unity bundle, the TextAsset name equals the
decimal xxHash64 of the lowercase table name. The FlatBuffer stores the authored
key and text. This also located the source objects for Perform, OngoingTips,
Tips, Message and Subtitle configuration. Their object names alone do not
decode the bindings. [HoYoPlay release branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=U5hbdsT9W7)
· [Audited publisher manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)
· [TextMap schema reference](https://github.com/Hiro420/ZZZ_TextMap/tree/499541c07d73216b4a3cd3ae1720a81597c17e6d/ZZZ_TextMap/Defs)

The base contained 439,660 English keys and 450,561 Simplified Chinese keys.
Of 224,387 distinct subtitle IDs from the audited scene, comic and cinematic
readers, 220,442 had both languages and 216,719 had text in all 13 locales.
The denominator includes choices and silent lines. It excludes presentations
outside those readers. The three checked chapter 240 lines were absent from
the older English 3.2 chapter inventory. For each, the game-authored scene
binding identified a complete WEM fetched from the publisher in Mandarin,
English, Japanese and Korean. All three had translations in 12 base locales.
The Japanese text for all three was in the installed 3.3 override table.
Across this chapter's GalGame IDs, the bilingual count rose from 1,744 in
the launcher base to 1,846 after applying the installed design update.
[Publisher chapter announcement](https://zenless.hoyoverse.com/m/en-us/news/166963)
· [3.2 text comparison](https://github.com/malu-no996/ZenlessData/tree/1277ebca4b8a7a6c3bcbaac6d5708dc9f4a55f23/TextMap)

For 1,509 distinct voiced GalGame references in the chapter 240 scene extraction,
the check computed exact external-media identities for the tested source paths.
Across all 313 publisher base voice indexes, 1,476 matched in Mandarin, 765 in
English, 195 in Japanese and 1,474 in Korean. Only 49 matched in all four base
indexes. Three of those were downloaded in full in every dub. The later
installed indexes matched 1,477 per installed language (Mandarin, English and
Japanese). These are directory joins. An unmatched path can reflect another
binding or a subsequent update. The audit did not have the later Korean pack.

The inspected launcher base had data revision `19316624`. The installed
Global revision `19916124` contained 13 base and 13 overwrite tables. An
older Global 3.2 hotfix manifest and its block were independently retrieved
from the publisher. Current Global 3.3 hotfix discovery from an empty device
remains open. The normal preparation path still requires an installation
and compatible scene metadata. [Historical publisher design manifest](https://autopatchos.zenlesszonezero.com/design_data/3.2_live/output_19159270_4529024a46/client/StandaloneWindows64/oversea/data_version)
· [Public release revision history](https://zzz.gachabase.net/changelog/release)

The 3.3 English base contains 2,355 gender-tagged entries with text outside
the tags and 200 entries with repeated male tags. The corresponding Simplified
Chinese counts are 2,627 and 198. The prepared and legacy readers now preserve
the surrounding words, resolve every inline group and align translations by
the authored M/F labels. Missing voice packs retain the two distinct performance
identities. Local design and silence manifest changes invalidate language
preparation even when audio stays identical. The legacy update status reports
an unavailable upstream and retains the last verified revision for retry.

Audit date: 2026-10-27. This is a format and coverage audit, not a claim that every
scene, language, or capture layout has passed native gameplay testing. Game
resources were read from the owner's installation. Extracted assets, dialogue,
audio, account details and installation paths stay in ignored local evidence.

Subtitle boundary review, 2026-10-31: story, comic, ongoing and cinematic readers
retain individual authored TextMap identities. The cinematic adapter joins each
`CS_` identity to its exact authored Wwise event; it does not concatenate a movie
or infer page timings from timeline position. Speaker/scene context joins OCR
rows visible in the same captured caption, not successive subtitle records.
A synthetic index-to-match regression verifies consecutive cinematic IDs preserve
their own source and translated text even when they reference the same recording.
This does not prove pagination inside an indivisible TextMap string: if a game
version dynamically subdivides such a string without an evidenced page schema,
that boundary remains unresolved. No sentence-length or punctuation split is
presented as game-authored pagination.

## Evidence and scope

The publisher explicitly describes cutscenes and motion comics as separate
production formats in its [cinematics-team ZTALK](https://www.youtube.com/watch?v=RC4XoA7dhf0).
The [3.1 update announcement](https://zenless.hoyoverse.com/en-us/news/165414)
separately lists story content, Trust Events and Quality Time Events, and reports
fixes to missing voice lines during accelerated story playback. The current
[3.3 announcement](https://zenless.hoyoverse.com/m/en-us/news/166963) reports
continued changes to localized text and older English, Japanese and Korean story
and combat voice-overs. These are reasons to invalidate prepared data after
updates; patch notes do not document the binary asset schema.

Schema evidence comes from installed resource catalogs, exact referenced bundle
ranges and serialized story objects. TextMap and configuration metadata are
game-authored data obtained through a community-maintained mirror, not a
publisher-operated API. The audited fresh metadata revision was
`c7551c3040a69ffc28c6b13cb75ee1f95dc2f9d2`. Additional table discovery used a
separate cached 3.2 metadata snapshot, `b084f66` dated 2026-09-09; those obfuscated
field names must be revalidated against the current version before use.

The original prepared snapshot contained 71,449 Chinese entries and 69,861
verified original voices. A successful typed extraction found 221,705 references
across 29,365 story assets. Its 31,072 requested paths had 333 unresolved entries
in the installed catalog. These are extraction counts, before TextMap joining,
gender expansion, language selection and voice resolution; they are not counts
of playable, unique or currently accessible dialogue.

The final Chinese preparation with English translations completed successfully:
237,096 records, 71,628 original voices and 118,187 certified unvoiced records.
All 69,861 previously verified voiced rows remained present with the same file
identity and package binding; 1,767 additional original voices were resolved.
The worker validated every prepared row against the shared dialogue contract.

A subsequent bounded message/tip pass used the same current metadata revision
and the existing scene cache. Its complete preparation produced 265,241 records,
77,148 original voices and 135,479 certified unvoiced records. It added 28,145
entries, 5,520 verified voices and 17,292 silent records while retaining every
previous voice binding and silent classification unchanged. No cinematic rescan
was needed. The nine `VO_Message` entries all matched the installed Chinese pack.

## Inventory and implemented coverage

| Dialogue presentation | Authored evidence | Coverage and limits |
| --- | --- | --- |
| Normal and visual-novel conversations | `GalPlayStoryNode`, `GalPlaySubStoryNode`, `MainCityChatPlayStoryNode`; `dialogueKey`, `externalVoiceKey`/`voiceKey` | Typed reader supports voiced and explicitly silent records. `GalGame`, `Chat` and `ChatAudio` asset families are selected. |
| ChatPlus conversations | `PlayChatPlusStoryNode`; capitalized `DialogueKey` and `ExternalVoiceKey` | Supported independently of the older lowercase schema. Installed samples verified the difference. |
| Illustrated, no-avatar and group dialogue | `GalPlayPictureStoryNode`, `GalPlayNoAvatarStoryNode`, `GalPlayStoryMultiSpeakerNode` | Supported through the owning typed object's text and voice fields; the initial voice-regression comparison exposed these additional forms. |
| Narration and scene-transition text | `GalSubNarratorNode`, `GalSwitchSceneNode`, `GalWhiteSwitchSceneNode`, `SwitchSceneConfig` | Preserved as `narration`; empty authored voice fields establish silence, while missing fields remain unknown. |
| Conversations during gameplay | `MainCityChatInLevelPlayStoryNode` | Supported with the gameplay channel as well as dialogue capture. |
| Dialogue response choices | `TransitionDisplayItem`, `MainCityChatTransitionDisplayItem`; `textKey` | Preserved as `choice`. Voice status stays `unknown`: the absence of a voice property alone does not certify silence. |
| City, NPC, Trust and Quality Time bubbles | `GalBubbleStoryNode`; `Text`, `Voice`; `Bubble`, `BubbleStory`, `BubbleNpc` families | Empty/null authored voice is `unvoiced`. Nonempty values may be short reaction pools; those remain `unknown`, with no fabricated sentence audio. |
| Motion comics | Exact GUID-to-voice dictionaries; `Comic_` TextMap identities | Original voice mappings remain supported. Empty entries are certified silent only inside a complete, otherwise verified voice dictionary. All-empty generic dictionaries or unmatched TextMap IDs remain `unknown`. No such silent comic entry was observed in this installed dictionary extraction. |
| Cinematic timelines and cutscenes | Typed `WwiseAudioClip`, owning track and authored `CS_` subtitle/event relationship | Supported for the known clip layout, including the auxiliary empty string variant. Existing locale/event resolution remains required. Cinematic text with unresolved authored audio is `unavailable`, not silent. |
| Gameplay and ongoing tips | `OngoingTipsConfigTemplateTb` text IDs and explicit male/female source fields | Preserves existing original voices and now retains records with both authored voice fields empty. The current metadata contained 1,466 such rows before TextMap filtering. Other tips tables are not implied by this support. |
| NPC greetings and ambient combat reactions | Some are present in supported ongoing/bubble records; other source-only tables exist | Only authored text/source relationships are eligible. Audio-only barks cannot be reconstructed as official dialogue from filenames. |
| Knock Knock messages and reply choices | Separate `MessageConfigTemplateTb`; text, options, emoji and occasional `VO_Message` sources | Current schema imported through exact TextMap joins. Empty authored message source columns establish silence. A message recording never becomes its reply-choice audio; reply-only evidence remains unknown. Image paths and literal content are excluded. |
| Clue recordings with timed subtitles | `SubtitleConfigTemplateTb`, `Clue_` IDs, locale, source and start/end timestamps | Inventoried; dedicated segmented-audio adapter is missing. Mapping every subtitle to the entire recording would be incorrect. |
| Other tips, TV/Hollow and event interfaces | `TipsConfigTemplateTb`, `HollowBottomMessageTemplateTb`, event-specific tables | Current `TipsConfigTemplateTb` is imported as `gameplay_tip`, including authored spoken guidance and silent instructions. Reaction pools never substitute for the main recording. Independent Hollow/event tables remain incomplete. |
| Journey UI, reading screens, messages, mail, summaries and tutorials | Separate UI/configuration references; `ChatJourney` sample invokes journey UI rather than containing dialogue text | No blanket TextMap import. UI labels, item descriptions and notification text must not become dialogue merely because OCR sees them. |
| Pre-rendered movies, baked text, songs and subtitles without a verified timeline event | Not established by the supported dictionary/timeline relationships | No completeness claim. Require a format-specific subtitle binding and timing/locale validation. |

The fresh typed extraction classified 98,759 conversation, 17,496 ambient and
2,356 narration references as explicitly silent. It retained 41,529 choice
references as unknown, 59,313 conversation/narration references with authored
voice sources, and 2,252 other references with unknown voice status. Reused lines
can have conflicting evidence; the prepared table does not promote such a
conflict to certified silence. Successful audio resolution always means `voiced`.

## Format handling and update behavior

The resource reader supports legacy gzip catalogs and the observed Unity v21
serialized `Res` catalog object with its asset, bundle, block and flat dependency
arrays. It follows authored dependencies and validates byte ranges. The new
story reader parses bounded Odin objects and their types and properties, including
empty strings and nulls. It does not pair adjacent strings or infer a voice from
matching filenames. The binary token definitions are documented by the
[Odin serializer project](https://github.com/TeamSirenix/odin-serializer/blob/master/OdinSerializer/Core/DataReaderWriters/Binary/BinaryEntryType.cs).

Installed blocks are opened read-only and only selected bundle ranges are read.
Preparation remains outside capture. Cache signatures include the installed
fingerprint, metadata and reader code; index reader revision 5 forces older
language snapshots to refresh. A malformed recognized Odin stream fails the
preparation instead of publishing its partial records. Every ongoing row is
checked against a supported schema, rather than trusting only the first row.
Known extraction failures retain the prior prepared index and return the
actionable ZZZ format/update error provided by the preparation layer.

Missing scene paths are reported as coverage notes, separately from preparation
failures. A follow-up compared all 31,072 authored dialogue paths with both
installed resource asset tables: the hotfix catalog has 570,614 asset identities
and the base catalog 565,107. None of the 333 hotfix-unmatched paths occurs in the
base table either. They cover 144 Bubble, 21 BubbleStory, 142 Chat, three ChatPlus
and 23 GalGame paths, referenced by 313 metadata rows. Case/prefix/extension
variants tested during diagnosis supplied no additional exact matches. No
filename similarity was promoted into a subtitle or voice binding. The reason
for each missing reference remains unestablished; it is not evidence that the
whole index failed or that the user's voice pack is absent.

That comparison exposed a separate catalog compatibility defect. Unity aligns
arrays after the packed nine-byte block records. The installed base catalog's
10,470 blocks require two padding bytes before its dependency array; the hotfix
catalog's 10,532 blocks happen to need none. The reader now validates and consumes
zero alignment padding before each array. Both complete native catalogs parse,
including all 778,848 base and 784,390 hotfix bundle dependency/reference slices
and their exact object boundaries. Existing synthetic catalog coverage now
exercises all four alignment cases and rejects corrupt padding. This fixes
catalog-format handling without inventing any of the 333 absent path mappings.

Unknown objects containing dialogue fields are counted and produce an explicit
format-update warning. No such unsupported node remained in this extraction.
Optional cutscene resources remain a limitation.

One performance follow-up remains: cinematic extraction hashes the entire
scene-catalog module, so a path-selection-only edit can unnecessarily invalidate
the expensive cinematic scan. Split decoding into a dedicated module before
narrowing that cache dependency; do not replace it with an unchecked version
number or fragile source slicing.

## Supplemental message and tip tables

The follow-up fetched the current tables at the same pinned revision as the
TextMaps. Their obfuscated field names differ from the older discovery snapshot.
The adapter checks the complete observed field set and the used value types for
every row; drift raises an actionable format-update error before replacing the
previous index. Supplemental downloads do not invalidate the scene cache.

- `MessageConfigTemplateTb`: 12,205 rows and 14,305 selected-Chinese text
  references, before deduplication and gender expansion. `LDHNMACDKLH` is the
  message identity; `BKAEOOPMGNC`/`GJNMPOBFICI` are the source columns. All nine
  observed nonempty pairs agree. Differing future pairs remain unresolved rather
  than guessing a gender or selecting whichever recording is installed.
  `FNOKFPDDECI`, `NAPGHEGEOOC`, `GGHOAADLHCF` and `EEJNOOGPFND` contain reply
  references; only exact textual IDs present in the selected TextMap are used.
- `TipsConfigTemplateTb`: 17,661 rows and 16,677 selected-Chinese references.
  `BHLFCEAPFIG` is the text identity, `NMMACKNBLKO` the main authored source,
  `FNHBBPCONOL` a separate reaction source/pool, `NPDBBLABDAK` an alternate
  source and `FFNNCACHDLN` additional sound events. Only the main supported
  sentence source is resolved. Silence requires empty main, alternate, reaction
  and event fields. Eighteen unequal alternate pairs and seven additional source
  names remain unresolved by this supplemental adapter; missing audio never
  changes those records to silent. The resulting new `gameplay_tip` records
  include 5,511 verified voices and 7,914 certified silent instructions.

The shared full-window exact-match capture can consume certified message/tip
records. These table checks did not constitute native UI or OCR-layout testing.

## Remaining table work

These field names are evidence from the separate cached 3.2 snapshot, not a
future-proof schema contract:

- `SubtitleConfigTemplateTb`: 992 rows, comprising 248 `Clue_` subtitles in each
  of four audio languages. `PMIKEPAJFKN` is the voice source, `APDFDBPICNM` the
  audio locale, `AFDMDFIHPMH` the text identity and `INPHPLFPOKF`/`GMHGKDKPKJB`
  the start/end timestamps. Add timestamp validation and segment extraction;
  preserve the per-language timings.
- `HollowBottomMessageTemplateTb` contains nine related text references. These
  may overlap imported tips, but no comprehensive independent adapter is claimed.
- `MainCityStoreVoiceConfigTemplateTb`: 262 source-only entries were observed.
  A text binding still needs to be established; the source name is not a subtitle.

## Verification

Focused regression checks cover typed silent objects, choices, ChatPlus,
cross-object voice isolation, reaction pools, malformed/truncated streams, both
Odin string encodings, path safety, comic ambiguity, supported ongoing schemas,
locale isolation and unknown/unavailable distinctions. The audit ran 17 JavaScript
tests and 25 Python tests successfully. The supplemental pass subsequently ran
31 Python tests successfully, including pinned downloads, schema drift, exact
message/choice separation, reactions and missing/ambiguous voices. Native Windows capture bounds, DPI,
desktop/mobile layout, Firefox/Chromium and all four installed audio languages
were not exercised by these parser checks; they remain separate acceptance work.

The [2026-11-01 packaged-reader verification](../zzz-runtime-acceptance-2026-11-01.md)
records the compiler-free production resource contract, Windows native checks
and a private installed-file comparison preserving all observed scene/cinematic
bindings. Other platform and final installer gates remain separate.
