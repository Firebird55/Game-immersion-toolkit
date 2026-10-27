# Zenless Zone Zero dialogue audit

Audit date: 2026-10-27. This is a format and coverage audit, not a claim that every
scene, language, or capture layout has passed native gameplay testing. Game
resources were read from the owner's installation. Extracted assets, dialogue,
audio, account details and installation paths stay in ignored local evidence.

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
fingerprint, metadata and reader code; index reader revision 4 forces older
language snapshots to refresh. A malformed recognized Odin stream fails the
preparation instead of publishing its partial records. Every ongoing row is
checked against a supported schema, rather than trusting only the first row.
Known extraction failures retain the prior prepared index and return the
actionable ZZZ format/update error provided by the preparation layer.

Missing scene paths are reported in preparation coverage and its user-facing
message. They may represent optional resources, stale metadata or a version
mismatch; the audit did not prove which explanation applies to each missing path.
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
