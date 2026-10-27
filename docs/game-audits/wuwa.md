# Wuthering Waves dialogue audit

Audit date: 2026-10-27. Installed resource version: 3.7.0. Adapter schema
version: 3. This inventories authored content and parser boundaries; it does
not certify every gameplay scene or capture presentation.

## Evidence and sources

The installed client was inspected read-only using the toolkit's pinned
FModelCLI 1.0.2. Its checksum matched the configured pin. The installation
contained 466 official PAKs: 55 base archives and 411 downloaded resource
archives. The virtual inventory included 967 ConfigDB paths and 93,609
Wwise external-source paths. SQLite tables contain FlatBuffer records;
`FlowState.Actions` contains JSON inside a FlatBuffer string. These formats
were checked against the installed generated readers and runtime consumers,
including `PlotAudio`, `PlotAudioModel`, `FlowState`, `FlowConfig`,
`MultiTextLang`, `VideoCaption`, `InfoDisplay` and `PhoneMsgModel`.

Primary online references establish important distinctions and update risks:

- Kuro's [2.2 patch notes](https://wutheringwaves.kurogames.com/en/main/news/detail/2381) describe replay of voiced lines and subtitles through Story Review, separate from the larger story gallery.
- Kuro's [3.0 patch notes](https://wutheringwaves.kurogames.com/en/main/news/detail/3920) introduce WavesLine messages from characters and organizations, and explain separately downloaded/removable cinematic resources.
- Kuro's [official Steam announcements](https://steamcommunity.com/app/3513350/announcements/) describe 3.7's additional quest type and limited Main Quest Replay. They also announce a planned 3.8 Steam launcher replacement and tiered resource downloads. This audit verifies the installed 3.7 layout, not the unreleased replacement layout.
- The pinned [FModelCLI source](https://github.com/Herselfta/FModelCLI/blob/v1.0.2/FModelCLI/Program.cs) preserves the highest-priority archive entry during extraction. The corresponding [upstream changelog](https://github.com/Herselfta/FModelCLI/blob/main/CHANGELOG.md) explains why exporting duplicate base entries could overwrite patch text. The pinned reader already contains that fix.

Raw inventories, extracted schemas/databases, logs and voice samples remain in
ignored `output/checks/audit-wuwa/`. No dialogue, media, archive extraction
metadata, install paths or account data is part of this public audit.

## Presentation inventory

“Indexed” means the adapter emits a record when the selected locale contains
the authored text. It does not mean every record appears in the current save,
or that its UI crop has passed desktop/mobile OCR replay.

| Presentation | Installed evidence and current handling | Remaining gap |
| --- | --- | --- |
| Normal story, companion, side, exploration and event conversations | 21,156 `flowstate` rows contain 20,672 `ShowTalk` actions and 111,390 talk references. The adapter traverses nested actions/options and joins exact `TidTalk` keys. | Quest-type classification and complete branch reachability are not resolved against a save. Numeric legacy text references are separate. |
| Original spoken performances and Rover variants | 42,584 `PlotAudio` rows define exact filenames, global-language handling and per-dub gender flags. Existing audio identities remain unchanged. | Dynamic parameters, global creature sounds and missing locale sources remain unavailable; filenames are never guessed. |
| Choices and player responses | 19,541 nested `TidTalkOption` references plus `Option`/`SystemOption` talk items were observed. Choice labels are retained as text-only unless another context establishes a voice or unresolved speech. | Option-region capture and timed/QTE choice layouts need independent replay. A choice label is not the later spoken response. |
| Ambient and walking conversations | `Prompt` plot modes produce an ambient category; other world conversations can use normal flow dialogue. | Entity-only bubbles and level-specific interactions are not exhaustively traversed. Simultaneous speakers and top-right crops remain separate capture concerns. |
| Combat, idle, reaction and boss speech | Installed `db_audio` contains 62 `roleaudio` rows; `db_audio_interjection` contains 360 interjections. Flow actions also contain 1,466 `PostAkEvent` references. | These are not one-row-per-caption tables. Event-to-WEM ownership and subtitle visibility are unresolved; no complete combat coverage is claimed. |
| Real-time cinematics | Flow dialogue retains exact existing audio bindings. The flow inventory includes 416 `PlaySequenceData` actions. | Animation/sequence-only dialogue and timed caption segmentation require further authored joins. |
| Pre-rendered movie captions | `db_cgVedio` contains 1,313 `videocaption` rows, 342 video definitions and 171 video-sound rows. Caption text keys are now indexed as cinematic. | Locale-specific timing and embedded movie audio are not converted into per-caption clips. `IsPlaySubtitleVoice=false` does not establish silence. |
| Centered story cards and narration | 945 `CenterText`, 122 `AvgNarration`, eight `AvgCenterText` references and 107 `ShowCenterText` actions were observed. Their authored text keys are retained. | Some cards use independent audio events or background narration. Missing `PlayVoice` alone stays unknown; multi-page segmentation is unverified. |
| Illustrated dialogue and event story panels | 99 `AvgTalk` references, background configuration and event audio fields occur in flow scripts. Their text is retained. | No exhaustive art-embedded text/comic extractor is established. Rich layout, ruby/variable rendering and event-specific panels need replay and additional schema mapping. |
| WavesLine text conversations and reply choices | The phone table contains 290 short-message records. Flow `PhoneMessage` mode uses ordinary `Talk` items for plain text. Runtime `SetDialogChatData` proves that modality; its text is certified unvoiced when no conflicting voice evidence exists. | All branches are retained, rather than selecting the player's unlocked messages. Phone-panel OCR is not newly validated. |
| WavesLine voice messages | 191 `PhoneMessage` items explicitly have `MessageType.Type=Voice` and `PlayVoice=true`. Exact PlotAudio binding remains eligible. | An absent selected-dub source is unavailable, not a silent message. |
| WavesLine system notices and attachments | 88 system-tip items are text-only. The 118 emoji and 36 attachment items are excluded from narrative text; 35 attachment metadata rows were inventoried. | Attachments may open another presentation. No image transcription, account messages or server mail is read. |
| Books, letters, notes and readable information panels | `InfoDisplay` has 803 rows with explicit text and optional audio fields. Localized body references are now retained as readable. | Empty audio alone cannot certify silence. Long pages, authored audio events and other handbook/event/book schemas remain only partially covered. |
| Floating 2D/3D captions | `db_FloatingSubtitle` contains 11 two-dimensional and 37 three-dimensional entries, with distinct text keys and an audio field in the 3D schema. | Dedicated table ingestion, world-space bounds and camera movement are not implemented by this change. |
| Legacy numeric subtitles/options and song lyrics | `SubtitleText` contains 1,262 rows with five subtitle/option/audio slots; `MusicSubTitle` contains 253 rows. These differ from MultiText string-key joins. | Not newly ingested. Numeric localization joins and song timing need their own verified adapters. |
| Story review, replay, summaries and ordinary UI | Review can reuse supported flow/audio identities. Handbook and other display tables exist separately. | Review-mode order, summary text, quest instructions, loading tips and general UI are not bulk-imported as dialogue. |

Counts describe source references, not unique spoken sentences. Reused keys,
multiple branches and gender variants make these totals intentionally different
from the final localized record counts.

## Current-format correction and voice evidence

Each inspected main MultiText table has 326,831 rows. Of these, 2,417 use
`RedirectDbIndex=1`. Every one of those base values differs from its selected
`lang_multi_text_1sthalf.db` value, despite the base value being nonempty.
The shipped `MultiTextLang` reader explicitly resolves that redirect. The
adapter now reads the shard and never treats the base placeholder as final text.
Existing caches acquire the shard when needed. Unknown redirect indices,
missing shards and missing redirected identities fail preparation with an
actionable format/data error; another locale is never substituted.

The emitted voice states have these meanings:

- `voiced`: an authored PlotAudio filename resolves to an installed resource
  in the selected dub, with the correct Rover variant.
- `unavailable`: there is authored voice/event evidence without a safe installed
  binding, or a movie may carry speech in its embedded soundtrack.
- `unvoiced`: an explicit false voice flag without another audio event, a
  text-only choice, or a verified plain-text phone modality establishes silence.
- `unknown`: ordinary talk, narration or readable text lacks enough evidence.
  Missing audio alone never becomes certified unvoiced.

If one text key occurs in both a silent and an unresolved context, the more
conservative status wins. An existing verified audio binding wins over a
text-only reference. The shared capture setting keeps certified unvoiced
capture opt-in and exact-only; unknown/unavailable records do not become
silent fallbacks. Category labels describe the strongest observed presentation,
not an exhaustive list of every reuse of the text.

## Validation

The real metadata pass exercised all five supported study locales with English
and Simplified Chinese translations, checked every row against `LocalDialogue`,
and found zero duplicate record identities. It completed in 30.74 seconds.

| Selected text/dub | Records | Bound voices | Certified unvoiced | Unavailable | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| English | 132,394 | 46,461 | 20,074 | 2,118 | 63,741 |
| Simplified Chinese / Mandarin | 134,024 | 46,293 | 20,452 | 2,125 | 65,154 |
| Japanese | 132,463 | 0 | 20,079 | 48,636 | 63,748 |
| Korean | 132,261 | 0 | 20,082 | 48,399 | 63,780 |
| Traditional Chinese / Mandarin | 133,157 | 46,280 | 20,336 | 2,118 | 64,423 |

Japanese and Korean voice packs are absent in this installation. Their zero
bound counts do not mean the game lacks those dubs. Locale differences also
reflect missing/empty localized entries and authored per-language variants.
No complete gameplay or native playback coverage follows from inventory counts.

Four installed original clips were separately extracted and decoded to nonzero
16-bit PCM: English female/male Rover samples lasted 2.569/1.849 seconds and
Mandarin samples lasted 2.573/2.888 seconds. This bounded smoke check took
46.86 seconds. It proves those source/decoder paths, not every indexed voice.

Synthetic regressions cover current text redirects, missing/new shards,
cached-base shard acquisition, normal versus silent versus unavailable dialogue,
phone voice/attachment distinctions, conflicting uses of one key, movie/readable
audio, disabled actions, malformed metadata and changed flow containers. Run
`python -m pytest backend/tests/test_wuthering.py
backend/tests/test_wuthering_languages.py backend/tests/test_wuthering_narrative.py`.
These complement the prior [presentation evidence](../game-ocr-presentations.md),
which does not verify newly indexed phone, choice and readable surfaces.
The targeted suite passed 26 cases in 1.91 seconds; documentation checks passed.

## Updates and remaining limits

The fingerprint includes official PAK paths, sizes and modification times under
both base and downloaded resource roots, including optional official video PAKs.
Thus observed text/config-only PAK hotfixes invalidate the cache as well as voice
downloads. It is a metadata fingerprint, not a full hash of every game byte.
Unsupported mod archives remain rejected. Schema bounds and flow containers are
validated before replacing a completed index. Coverage warnings accompany the
snapshot so a large record count is not presented as full support.

Future launcher roots, additional localization shards, IoStore containers,
changed script layouts and new event modalities require inspection when they
appear. The 3.8 launcher announcement warrants a fresh discovery/update audit;
this change does not claim support for files that are not installed yet. No game
was launched, account written, save modified or live installation updated.
