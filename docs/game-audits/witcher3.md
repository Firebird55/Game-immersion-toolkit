# The Witcher 3: Wild Hunt narrative audit

Audited 2026-10-27 against the installed Windows executable version
`5.0.0.1048522`. The installation has 31 `POTATO70` version-5 bundles,
18 localization tables, English and Simplified Chinese speech containers, and
20 loose USM movies. Expansion resources with `dlc/ep1` and `dlc/bob` virtual
paths are present inside the merged bundles; the absence of a physical `dlc`
directory does not establish that expansion assets are absent. This inventory
does not check the user's entitlement or completion of every game download.

All game files were read in place. No game content, audio, personal paths,
recordings or account data is included in the repository.

## Narrative presentations

| Presentation | Installed evidence | Reader behavior and remaining limits |
| --- | --- | --- |
| Conversation, quest dialogue and branching scenes | 6,380 `.w2scene` resources; 67,696 nonzero `CStorySceneLine.dialogLine` references | Joins the authored localization ID to the selected language's exact CPSW speech record. Missing or ambiguous speech is unavailable. `isSilent=true` establishes silence only when no other occurrence requires voice. |
| Ordinary and injected quest choices | 7,897 references in `CStorySceneChoiceLine.choiceLine` and `CStorySceneQuestChoiceLine.commentText` | Choice labels are an explicit text-only presentation. Ordinary `CStorySceneComment` direction text is excluded. A verified voice binding takes precedence for an ID used in more than one context. |
| Ambient NPC chatter and gameplay dialogue | 925 authored `isBackgroundLine` references | Included by the same localization/speech join and labeled NPC chatter. Many other spoken scene lines do not carry this flag; the category is not an exhaustive ambient/combat classification. |
| In-engine cutscenes | 493 `CStorySceneCutsceneSection` objects and players | Scene dialogue with an exact localization/speech binding remains supported. Animation, sound-event and cutscene-player objects are not presumed to contain subtitle identities. No separate coverage claim for all embedded sounds. |
| Prerendered cinematics, flashbacks, storyboards and final boards | 261 video sections/elements; 1,122 `.subs` files, including storybook, finalboard, flashback, gamestart and expansion paths | Sidecars are inventoried, not mislabeled as silent text. Frame-based subtitle timing and USM language-track extraction still need a verified per-cue join. The reader does not play an entire movie track for one subtitle. |
| Storybook journal narration | 30 `CJournalStoryBookPageDescription.description` references; this type also has a video filename | Marked cinematic and unavailable unless an exact speech record exists. A visible paragraph is not evidence that its associated narration is unvoiced. |
| Quest journal, profiles, bestiary and glossary | 1,466 quest-description, 536 character-description, 279 creature-description and 52 glossary/place references | Only named `LocalizedString` body fields are accepted as text-only presentations. Titles, objectives, tutorials and general UI labels are not automatically made capturable. |
| Books, letters and notice items | 1,692 distinct authored readable-key hashes; 843 resolve to selected-language IDs | Reads `ReadableItem` XML definitions. The installed inventory script derives the body key from `localisation_key_name + "_text"`; the RTSW secondary key table resolves that exact key hash. 849 unresolved or ambiguous keys remain warnings. The dynamic Gwent Almanac is excluded. |
| Other UI, untranslated content and nonverbal sound | Remaining localization entries and non-dialogue assets | Retained as unknown unless supported metadata or an exact voice binding establishes their status. Missing speech is never the reason a row becomes unvoiced. Long readable bodies still require enough visible text for exact matching; paragraph timing, scrolling and live OCR coverage were not validated. |

The official [scene authoring guide](https://cdprojektred.atlassian.net/wiki/spaces/W3REDkit/pages/28770374/HOW-TO+Create+a+scene)
describes the scene screenplay, graph and timeline. The separate
[context dialogue guide](https://cdprojektred.atlassian.net/wiki/spaces/W3REDkit/pages/1182400521/HOW-TO+Create+a+context+dialogue)
documents quest choices injected from other scenes; that is why both choice
classes are read. CDPR's
[localization ID guide](https://cdprojektred.atlassian.net/wiki/spaces/W3REDkit/pages/6328202/HOW-TO+Use+ID+spaces+for+localization+modding)
explains the identity boundary used for localization.

Typed field and format behavior was cross-checked against the primary
[WolvenKit REDengine 3 implementation](https://github.com/WolvenKit/WolvenKit-7),
including `CStorySceneLine`, `CStorySceneQuestChoiceLine`,
`CJournalStoryBookPageDescription`, `LocalizedString` and `W3StringBlock2`.
The installed `inventoryComponent.ws` and `glossaryBooksMenu.ws` independently
establish the readable-item key contract. The new reader is limited to these
documented fields, not arbitrary numeric values found in resource bytes.

## Update resilience

The reader accepts the legacy version-3, 320-byte bundle table and the observed
version-5, 304-byte table. The latter contains a full 64-bit resource offset.
It supports uncompressed, zlib and bounded raw LZ4 resources; LZ4 follows the
[format author's specification](https://github.com/lz4/lz4/blob/dev/doc/lz4_Block_format.md).
Other compression types fail explicitly. Unsupported bundle/CR2W versions,
unsafe paths, invalid table bounds, corrupt resources and XML declarations
produce a game-format error with an update/retry action. No new dependency or
full-game unpack is required. The selected reader does not load textures or
movies into memory while inspecting narrative metadata.

Bundle metadata now participates in the language fingerprint, so scene or
readable updates rebuild the inventory even when the text/speech files did not
change. Localization/speech format errors identify the game reader, and an
installation changing mid-preparation retains the previous complete snapshot.
The language reader revision advances to 3. Translation joins retain the
existing locale, patch and DLC identity boundaries; duplicate key hashes stay
ambiguous even when a patch replaces an older table.

## Verification

The final installed-language probes produced:

| Study locale | Records | Verified voices | Confirmed unvoiced | Voice unavailable | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| English | 96,913 | 64,705 | 10,427 | 163 | 21,618 |
| Simplified Chinese | 97,834 | 64,725 | 10,576 | 837 | 21,696 |

No duplicate record IDs were produced. The English probe retains all 64,705
voice bindings present before this change. The different language totals are
reported separately rather than assuming identical localization coverage.
The final probes took 24.45 and 24.22 seconds. Three original RIFF samples per
locale were read; an English sample and a Chinese sample beyond the four-GiB
speech offset decoded to nonzero PCM of 0.90 and 1.43 seconds respectively.

46 affected tests passed, with seven unrelated cases deselected, in 1.41
seconds. They cover legacy/new bundle layouts, decompression/checksums, unsafe
and incomplete formats, 64-bit offsets, explicit silence versus unavailable
voice, injected choices, readable joins, key collisions, update fingerprints
and the default-off exact-only capture toggle. Existing speech, locale, DLC,
modded subtitle and patch-refresh regressions remain included.

Private evidence is under ignored `output/checks/audit-witcher3/`:
`files.json`, `schema-summary.json`, `final-locales.json`, `audio-check.json`
and `targeted-tests.log`. These file probes do not establish physical game
capture, live OCR calibration, every optional quest, third-party mod load
order, or complete cinematic audio coverage.
