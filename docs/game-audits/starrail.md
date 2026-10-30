# Honkai: Star Rail dialogue audit

Audit date: 2026-10-27. Installed client: 4.6.0. Adapter schema version: 2.
This is an inventory of dialogue presentations and their current parser support,
not a claim that every screen has passed OCR replay.

## Evidence and provenance

The installed client was inspected read-only. It contained 825 Wwise PCKs,
all with `AKPK` headers; the four installed voice languages were Chinese,
English, Japanese and Korean. Audio uses
`Audio/AudioPackage/Windows` beneath the base and persistent asset layers.
The installation also contained 1,184 USM files, binary `DesignData/Windows`
tables and encrypted `.block` assets. These are distinct from ZZZ's resource
catalog format. No Star Rail evidence warrants applying ZZZ's catalog decoder.

Text and authoring relationships were inspected at
[catalog revision 74a7b96fba32f00cf495a5c00b0311bd02207aaf](https://gitlab.com/Dimbreath/turnbasedgamedata/-/tree/74a7b96fba32f00cf495a5c00b0311bd02207aaf).
Its commit identifies production Windows 4.6.0 and is dated 2026-10-19.
This is a third-party mirror of game-authored data, not a HoYoverse-hosted API.
Installed PCK identities independently verify the audio bindings; matching
version labels alone does not prove every mirrored string is present locally.
The audit enumerated 2,253 Excel table names and inspected 32 relevant table
schemas. It did not decode every local binary table or inspect every story script.

Primary product references establish the presentation categories:

- [Official 3.4 update](https://hsr.hoyoverse.com/en-us/news/157441): distinguishes Trailblaze, Continuance, Companion and Adventure conversations from cutscenes and exploration, and introduces dialogue summaries and language switching.
- [Official 4.6 update](https://hsr.hoyoverse.com/en-us/news/166468): identifies messages, readables, data-bank entries, loading text, narrated stories, ambient voices and the Interastral Peace Broadcast as separate content.
- [Official 2.2 update](https://www.hoyolab.com/article/28286762): separately lists story dialogue, messages, readables, character stories and Simulated Universe text.

Private probes and downloaded metadata live only in ignored
`output/checks/audit-starrail/`. No game dialogue, media, local install paths,
credentials or account information belongs in the public audit.

## Presentation inventory

“Indexed” below means that the adapter now emits an authored record when the
selected localization contains its text. It does not establish successful OCR
for that presentation, nor that every branch is reachable in a particular save.

| Presentation | Authored evidence and current handling | Remaining gap |
| --- | --- | --- |
| Trailblaze, Continuance, Companion and Adventure dialogue | `TalkSentenceConfig` joins exact `VoiceID` to `VoiceConfig`; ordinary lines and player variants remain indexed. Rows without a voice reference now retain their text with unknown voice status. | Mission/script traversal has not classified every sentence by quest type or checked all branches. |
| Dialogue choices and player responses | Sentences without voices are no longer discarded. | Choice presentation is not encoded in the sentence table alone; choice/script joins and choice-region OCR remain unverified. No claim that every choice string lives in this table. |
| Optional NPC conversations, object interaction, inspections and legacy daily content | `DialogueNPC` has 1,725 script references; `DialogueProp` has 378. Their sentence-table content can now survive without audio. | References were inventoried, not exhaustively traversed. Selection conditions and historical/removed content are not resolved against an account. |
| Ambient NPC speech and proximity barks | Authored `NPC_*` voice types retain exact audio and are labelled ambient. | Overhead bubbles, simultaneous speakers and capture crops need separate image replay. |
| Walking conversations, mission chatter and broadcasts | `MissionTalk_3d` and `Broadcast*` records are present; exact authored paths remain usable. | Floating captions, remote voices and overlapping dialogue are not individually replay-verified. |
| Multi-performance sentences | `TalkSentenceMultiVoice` contains 1,044 rows; 1,009 refer to present sentences, including 1,006 without a primary `VoiceID`. Text is retained as audio unavailable. | Selection semantics must be established before choosing or combining performances. List order is not a binding rule. |
| Real-time cinematic captions | 689 sentence rows reference `VoiceType=Cutscene`; captions are now retained. | No per-caption audio timing/segment binding. A whole cutscene track is never substituted for one caption. |
| Pre-rendered movies | Installed USM containers and `CutSceneConfig` establish separate cinematic assets. | `CutSceneConfig` has 41 rows and caption-path fields, but this audit does not establish exhaustive movie-caption coverage or extraction. |
| Narrated storybook content | 1,437 `TarotBookSentence` records directly reference `VoiceConfig`. Player variants produce 2,586 exact bindings in each installed voice language. | UI association, timing and full-screen text capture still need replay. |
| Character profile/voice archive | 5,445 `VoiceAtlas` rows; `AudioID`, not the menu's `VoiceID`, is the voice-config key. Exact `AudioID` records are indexed with original audio where installed. | 3,614 rows use Wwise `AudioEvent` instead; their text is indexed but event-to-media binding is unavailable. |
| Combat, idle and character reaction lines | `VoiceAtlas.IsBattleVoice` identifies 2,506 battle entries; their localized text is retained. | Not all combat audio displays subtitles. Event-driven playback is unresolved; no inference from filename or voice title. |
| Phone messages and reply choices | `MessageItemConfig` has 13,779 rows, including 13,057 typed `Text` items. Plain-text bodies/options and the 26 conditional text overrides are indexed. | Phone-panel OCR is not newly verified; all conditional variants are retained rather than selecting the player's current branch. |
| Message attachments and media | The schema distinguishes `Text`, `Sticker`, `Image`, `Raid`, `Video` and `Link`. | Attachment labels are excluded from dialogue; no attempt to transcribe images, video or stickers. Player-to-player chat and server mail are not read. |
| Event chat panels | Plain text from `RestaurantMessageConfig` (154 rows) and `IdleLiveMessageContent` (110 rows, 100 with text) is indexed. | Other event-specific panels and new event schemas require explicit adapters. |
| Event stories, minigame speech, puzzles and scene overlays | Additional schemas include `ActivityHipplenSentence` (371), `ClockParkTalkText` (251), `IdleLiveEventSentence` (5), `ChimeraTalk` (295), plus talk/assistant/bubble tables. Some refer back to shared sentences; others hold separate hashes or audio events. | Separate hashes/events are not imported by this change. Obfuscated `FateMasterTalk` and `LimaoNewsMessageItem` fields remain unmapped. |
| Simulated/Divergent Universe narrative and choices | Shared sentence content is retained. `RogueCommonDialogue`, rogue story tables and `RogueDialogueOptionDisplay` (2,302 rows) establish additional paths and option text. | Dedicated option/result presentation, parameter substitution and complete script traversal are not implemented. Gameplay descriptions are not bulk-imported as dialogue. |
| Books, readables, data-bank prose and audio collectibles | `LocalbookConfig` contains 1,121 content records; `AudioBookData` has 12 event references. | These long-form fields are outside the current sentence adapter. Page/paragraph segmentation and authored audio-event mapping are needed. |
| Full-screen narration, storyboards and comics | Text already referenced by supported sentence/storybook tables can be indexed. | No dedicated comic-caption extractor or complete art-embedded text mapping is established. Absence of a table named “Comic” is not evidence that the presentation does not exist. |
| Story summaries, loading tips and general UI | Separate `StoryAtlasTextmap`, `LoadingDesc` and other text schemas were located by name. | Not ingested as spoken dialogue. Table-name discovery alone does not validate field mappings; these additional downloads hit upstream rate limiting. |

## Voice-state rules

The record's voice state describes evidence, not merely whether an audio file
was returned:

- `voiced`: the authored locale source hash resolves to an installed PCK entry.
- `unvoiced`: explicit `VoiceType=NoVoice`, or a verified plain-text message
  modality. Message `ItemType=Text` and its reply choices are structurally
  separate from media attachments; only text items and their overrides qualify.
  The event message adapter similarly admits only `DisplayText`/`Reply` content.
- `unavailable`: an authored voice is unresolved/missing, an audio event has no
  media binding, or multi-voice/cutscene semantics prevent safe playback.
- `unknown`: a general sentence has no primary voice reference. Absence of
  `VoiceID` alone cannot certify silence, as the multi-voice table demonstrates.

The 244,380-row sentence table contains 159,646 rows without a primary voice ID,
53 with an unresolved nonempty ID and 272 using explicit `NoVoice`. The parser
keeps existing spoken identities and gender variants. Additional sources use
separate identity prefixes; conditional message variants include their text hash.
It does not guess genders, combine performances or choose a branch from account
state. Missing localized text remains absent rather than falling back to another
language.

## Validation results

The real-data pass used integrity-checked cached Chinese/English Main and
ordinary textmaps at the same immutable revision and read all installed locale
PCK external tables. Every resulting Chinese/English record passed the shared
`LocalDialogue` contract; each locale had zero duplicate record identities.

| Selected text/voice | Localized records | Bound original voices | Certified unvoiced | Unavailable audio | Unknown voice status |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simplified Chinese / Mandarin | 273,850 | 93,564 | 16,566 | 5,492 | 158,228 |
| English / English | 273,854 | 90,616 | 16,566 | 8,440 | 158,232 |

These are metadata records, not a count of unique spoken sentences or completed
missions. Alternate player voices and conditional text are separate records.
Differences between locales are not classified as a corrupt install without
additional evidence. Japanese and Korean source-hash checks also succeeded,
with 91,957 and 92,043 bound links respectively before localization filtering;
their full textmaps were not part of this pass. Traditional Chinese and all
translation combinations retain their existing parser contract but were not
newly exercised against real localization tables.

The previous sentence-only Mandarin parser resolved 89,147 of 89,274 candidate
voice links. The largest new exact bindings are narrated storybook and character
archive records. This audit did not decode/listen to every voice, run the game,
change a save or perform account writes.

Synthetic regressions cover missing primary voices versus multi-voice metadata,
explicit silence, missing voice records, unsafe paths, player variants, cutscene
caption retention, typed phone items/overrides, archive `AudioID` semantics and
changed table schemas. Run `python -m pytest backend/tests/test_starrail_assets.py
backend/tests/test_new_rpg_languages.py` for these contracts and the existing
locale bindings. New presentation-specific desktop/mobile OCR replay, zoom/DPI
and live device acceptance remain unverified; the prior opening-dialogue replay
in [presentation notes](../game-ocr-presentations.md#starrail-genshin-endfield)
does not prove the newly added surfaces.

## Update and format limits

The adapter rejects unexpected table containers or renamed required schemas,
so an unsupported format cannot quietly look like an empty successful import.
Wwise header/table bounds and extraction identities retain their existing
validation. Metadata/network failures propagate to preparation, which preserves
the previous completed index. A rate-limited upstream is not proof of missing
installed dialogue.

The current shared install fingerprint includes audio-package metadata,
`BinaryVersion.bytes` and `config.ini`. It does not independently fingerprint
all persistent design-data manifests or poll the remote metadata revision.
A text-only hotfix that changes none of those inputs can therefore require an
explicit refresh. Stronger revision detection and version-paired local subtitle
extraction remain follow-up work.

Future additions should traverse authored script references, resolve event/media
relations and add independently annotated replay cases for the corresponding
presentation. Adding every localization string, selecting a multi-voice entry by
ordinal or guessing caption timing would not establish coverage.
