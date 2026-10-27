# Arknights: Endfield presentation audit

Audited 2026-10-27. Coverage is **partial**, with explicit per-record voice status
and aggregate preparation warnings. This is a local asset/schema audit and
synthetic regression result, not a completed native OCR acceptance run.

## Evidence and provenance

The installed VFS was inspected read-only through the existing pinned
[EndfieldStudio reader](https://github.com/EIHRTeam/EndfieldStudio). The audit
enumerated 361,098 entries across base and persistent indexes, including 770
installed table assets and 687 video assets. Selected SparkBuffer tables and UI
Lua were decoded into ignored local evidence. Duplicate base/hotfix references
are included in the inventory count; this is not a count of unique stories.

The runtime metadata source is the **third-party**
[rmxlinux/EndfieldData mirror](https://github.com/rmxlinux/EndfieldData), revision
`a0ed1dac31c502f636c70cee4e3010ca69562a70`, titled `Update 10/22`. Its README
describes manual updates and Endfield 1.6 support. It is not a publisher API.
The installed DialogTextTable, RadioTable, DialogOptionTable, Dialog2DTextTable,
RichContentTable and CharacterTable match that snapshot exactly. AudioDialog
has 13 differing metadata rows, but all 33,273 resolved source paths match.
One SNS group, 11 TextTable rows and parts of the English localization differ;
the runtime therefore warns that the mirror can lag the installed game.

Publisher evidence independently establishes the presentation families:

- The [March update notes](https://endfield.gryphline.com/en-us/news/8907)
  describe main, side and exploration missions, operator-switch voice lines,
  database entries, clue dossiers and changes to story cutscenes.
- The [June update notes](https://endfield.gryphline.com/en-us/news/0758)
  identify narrative events, NPC voice improvements and Baker messages.
- The official [Against the Tide cutscene](https://www.youtube.com/watch?v=OYv6yJUgTQk)
  and [The Bloodening cutscene](https://www.youtube.com/watch?v=7o_9-z1_XzU)
  establish cinematic presentation. They are not audio-binding sources.
- The publisher's [The Promise comic](https://endfield.gryphline.com/en-us/news/0753)
  establishes external comic publication. It does not prove that those web
  pages are installed in the client. In-client two-dimensional panels and
  document artwork were established separately from local files.

No game dialogue, media, extracted tables, credentials, account state or personal
paths are included in this document or committed fixtures.

## Presentation inventory and implementation

Counts in the last column are nonempty English records from the audited mirror.
They include authored but potentially locked/unreleased content; they are not
counts of scenes observed during play. Blank localization/sentinel entries are
excluded. Main/side/event/NPC coverage shares tables; no per-mission completeness
claim is made.

| Presentation | Installed evidence and binding | Result / English records |
| --- | --- | --- |
| Main, side, event and NPC conversations | 24,081 DialogTextTable rows; text ID → audioOverride → AudioDialog → selected-locale external hash | 23,100 conversation records. Missing paths or recordings remain unavailable; blank overrides remain unknown. |
| Radio, ambient and field speech | 3,336 RadioTable groups containing 5,613 rows; explicit radioText/audioOverride/audioEvent | 5,516 records; dialogue and gameplay channels. Generic unresolved events do not become silent. |
| Narration and black-screen/cinematic text | 269 TextVoIdTable references into TextTable | 269 narration records; cinematic and dialogue channels. This does not cover entire movie soundtracks. |
| Choices | 5,707 DialogOptionTable rows | 5,462 text-only choice records. Choosing a line is distinct from a later voiced response. |
| Two-dimensional story panels | 34 Dialog2DTextTable rows; installed Dialog2DCtrl renders narrative body separately from spoken DialogTextTable text and selected options | 34 text-only story-panel records on the cinematic channel. Image-only text is not inferred. |
| Baker messages | 377 SNSDialogTable groups; installed SNSContentText and SNSContentVoice render separate text and voice widgets | 5,463 text messages, 2 voice-message transcripts. Voice events require exact source bindings; 239 media/system/unsupported cells are explicitly excluded. |
| Baker choices and topic starters | SNSDialogOptionTable and SNSDialogTopicTable | 1,598 text-only message-choice records. No friend/account chat is queried. |
| Narrative documents, clues and terminal readings | 783 RichContentTable entries / 4,397 paragraphs; installed RichContent, ReadingCtrl and ReadingPopUp controllers separate text, artwork and radio | 4,166 readable paragraphs; 140 image-marked paragraphs excluded. Popup/PRTS references are checked, with 9 unresolved bodies reported. |
| Narrative terminology notes | 38 NarrativeNoteEntryTable rows | 38 text-only note descriptions. |
| Operator archive and voice viewer | CharacterTable has 35 operators, 2,698 profileVoice rows and 198 profileRecord rows; installed CharInfoProfileCtrl separately renders recordDesc and plays voId with voiceDesc | 2,698 authored voice descriptions and 198 text-only records. Every profile voId resolves to an AudioDialog path in this snapshot. |
| Combat barks | 1,250 AIBarkText rows plus AIBark trigger rules | 1,250 gameplay text records, voice status unknown. No guessed trigger/voice join. |
| Pre-rendered cinematics, movies, media cards | Local Video/IV groups, CinematicCtrl FMV handling and SNSContentVideo | Inventoried, but no verified per-line timing/audio join. Whole movies are never substituted for a line. |
| Comics, storyboards and illustrated documents | Local two-dimensional narrative UI plus RichContent image rendering; publisher comic pages separately | Authored text fields covered as above; embedded artwork text, video captions and image-only bubbles remain gaps. |

Reading references provide a second coverage check: ReadingPopUpTable resolves
745 entries to rich content and 31 to radio, with one unresolved; PrtsReading
resolves 28 entries to rich content with eight unresolved; all 80 PrtsDocument
entries resolve to rich content. InstructionBook/tutorial text, inventory stats,
generic UI strings and friend chat are outside narrative capture.

## Installed audio and language result

At the initial audit, the install had no selected-language audio VFS groups. Both base and
persistent initial-audio inventories expose the same 56 entries. An additional
bounded header inspection of four main stream packages found 59,932 SFX entries,
all 32-bit IDs, and **zero** authored voice-hash matches across all five study
locales. The audit-stream prefix could not be parsed by this bounded probe; no
claim is made about its full contents. The adapter continues to use the existing
selected-language/initial/hotfix inventory rather than treating SFX as voices.

English preparation against that captured local inventory produces **49,794
records**: 16,959 verified text-only, 31,400 unavailable authored voices and
1,435 with unknown voice status. There are zero verified playable original
voices in this installation. Preparation tells the user to install the chosen
voice package in the game, then refresh; it does not change game/account settings.

Using independently decoded installed localization tables validates the same
typed joins for all study languages: English 49,794; Simplified Chinese 51,049;
Traditional Chinese 49,773; Japanese 49,794; Korean 49,773. These counts prove
text joins, not playback. Locale routing and exact authored voice bindings are
also covered with synthetic entries for every supported study locale.

## Later installed voice-pack verification

A second read-only check on October 27 observed a changed installation
fingerprint and a newly reachable Chinese audio group. The current reader found
35,067 entries in the selected Chinese group, alongside initial/hotfix entries.
English, Japanese and Korean groups remained absent. These are inventory entries,
which can include repeated base/hotfix references, not unique dialogue totals.

Joining the new inventory to the same explicitly recorded metadata revision
resolved **21,389 Simplified Chinese original-voice records**, with 17,196
confirmed text-only records, 11,029 unavailable and 1,435 unknown. A conversation
was extracted through the production voice service and decoded to a non-silent
three-second clip. The result verifies Chinese pack access and one original
performance; it does not establish that all missing mappings or gameplay layouts
are resolved. Aggregate evidence is under ignored
`output/checks/endfield-live-recheck/`.

## Update resilience and validation

Language index version is 2. Additive metadata fields are tolerated. Changed
required table shapes, missing core conversation data, malformed inventory
structures and changed localization structures return `unsupported_game_format`
with an actionable toolkit-update message. Missing optional categories produce
coverage warnings. Unknown SNS types are excluded and counted. The archive
fingerprint covers both VFS layers, case-insensitively; a concurrent game update
fails preparation while leaving the previous snapshot untouched.

The adapter never infers silence from a missing recording or an empty override.
Only verified text-only modalities receive `unvoiced`; generic events and
authored but missing recordings receive `unavailable`; uncertain barks and
default/blank voice references receive `unknown`. Ambiguous, placeholder and
unsafe source paths cannot bind recordings. Capture of text-only records remains
subject to the user's opt-in and exact-match safeguards.

Focused regression command:

```text
.venv/Scripts/python.exe -m pytest backend/tests/test_endfield_audit.py backend/tests/test_new_rpg_languages.py -k "endfield or declared_translation" -q
```

Result: **35 passed, 17 deselected in 0.73 seconds**. The dedicated cases cover
voice-state evidence, operator bindings, media exclusion, missing reading links,
schema drift, optional-category warnings, missing packs and snapshot retention.

The audit evidence and timings are retained privately under
`output/checks/endfield-audit/`, including inventory, decoded schema evidence,
bounded audio-header inventories, adapter/locale summaries and JUnit results.
No full suite or publication audit was run by this game-specific audit.

Native acceptance still requires actual game playback with a downloaded voice
pack, independently verified clip extraction, screenshots across each narrative
layout, desktop/mobile crop behavior, windowed/fullscreen capture, zoom and
Windows DPI bounds. Current file evidence does not establish that every
presentation appears inside the default dialogue crop.
