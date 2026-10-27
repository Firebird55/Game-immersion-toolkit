# Arknights: Endfield presentation audit

Audited and rechecked 2026-10-27. Coverage is **partial**, with explicit per-record
voice status and aggregate preparation warnings. The Chinese pack and production
clip decoding are now verified; native gameplay/OCR acceptance is still incomplete.

## Evidence and provenance

The installed VFS was inspected read-only through the existing pinned
[EndfieldStudio reader](https://github.com/EIHRTeam/EndfieldStudio). The audit
initially enumerated 361,098 entries across base and persistent indexes, including 770
installed table assets and 687 video assets. Selected SparkBuffer tables and UI
Lua were decoded into ignored local evidence. Duplicate base/hotfix references
are included in the inventory count; this is not a count of unique stories.

The runtime metadata source is the **third-party**
[rmxlinux/EndfieldData mirror](https://github.com/rmxlinux/EndfieldData), revision
`a0ed1dac31c502f636c70cee4e3010ca69562a70`, titled `Update 10/22`. Its README
describes manual updates and Endfield 1.6 support. It is not a publisher API.
The installed DialogTextTable, RadioTable, DialogOptionTable, Dialog2DTextTable,
RichContentTable and CharacterTable match that snapshot exactly. AudioDialog
has 18 differing metadata rows after the voice-pack recheck, but all 33,273 resolved source paths match.
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
| Combat barks | 1,250 AIBarkText keys are exact AudioDialog voice IDs; installed AIBarkCtrl uses that ID for subtitle lookup and playback stop | 1,250 gameplay records, all bound to installed Chinese recordings. No guessed trigger/voice join. |
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

That original no-pack result is historical. The newly installed Chinese package
and the current mapping results are described below. No game/account settings
were changed by the audit.

Using independently decoded installed localization tables validates the same
typed joins for all study languages: English 49,794; Simplified Chinese 51,049;
Traditional Chinese 49,773; Japanese 49,794; Korean 49,773. These counts prove
text joins, not playback. Locale routing and exact authored voice bindings are
also covered with synthetic entries for every supported study locale.

The current [publisher Steam language table](https://store.steampowered.com/app/4732690/Arknights_Endfield/)
and [Gryphline's voice-language announcement](https://endfield.gryphline.com/en-us/news/0767)
identify four voiced languages: Mandarin Chinese, English, Japanese and Korean.
All four are implemented and exposed; Traditional Chinese text shares Mandarin
audio. English/Japanese/Korean compatibility uses the common installed schema,
explicit reader locale branches and synthetic hash/extraction/preparation tests.
Their absent packs were not natively decoded. The full capability-versus-proof
matrix is in [Endfield language preparation](../endfield-languages.md#voice-language-support-and-verification).

## Later installed voice-pack verification

A second read-only check on October 27 observed a changed installation
fingerprint and a newly reachable Chinese audio group. The current reader found
35,067 entries in the selected Chinese group, alongside initial/hotfix entries.
English, Japanese and Korean groups remained absent. These are inventory entries,
which can include repeated base/hotfix references, not unique dialogue totals.

The initial recheck resolved 21,389 Chinese voice records and decoded a
conversation through the production service. The subsequent mapping audit
independently decoded the installed AudioDialog and AIBarkText tables. All 1,250
bark text keys are exact audio-table keys; AIBarkCtrl resolves `barkTextId` and
uses the corresponding `voId` for playback-stop handling. Every one of those
1,250 selected-locale source hashes exists in the downloaded Chinese package.
The adapter now uses this primary-key join, separately from filename stems.

Current Simplified Chinese preparation contains **51,049 records**:

| Voice classification | Records | Evidence |
| --- | ---: | --- |
| Bound original voices | 22,639 | Exact authored source hashes in installed Chinese audio, including all 1,250 combat barks |
| Verified text-only | 17,196 | Separate authored text-only presentations |
| Missing source metadata | 11,025 | 9,637 conversations, 1,146 radio lines, 240 narration references and two SNS audio events have no usable AudioDialog source |
| Missing locale recording | 4 | Known AudioDialog paths absent from Chinese inventory; each has zero Chinese duration and a nonzero duration in another locale |
| Unknown | 185 | 158 blank conversation overrides and 27 blank narration voice references |

The four missing Chinese recordings remain unavailable; other locales are never
substituted. The 11,025 unresolved metadata references have no case-only filename
alias, and the installed VoiceIdConflictTable is empty. There is no proven
additional mapping for them. Neither group is relabeled silent. Diagnostics now
distinguish these cases, so missing metadata does not tell users to reinstall
voice packs. Absence of a full selected-language package still has its own warning.

Three newly mapped barks, covering male Endministrator, female Endministrator
and another operator, were extracted through `LocalVoiceAssetService`, decoded
and encoded through the production pipeline, then independently decoded back to
PCM. All were non-silent: 1.331–1.721 seconds, 14,084–24,380 MP3 bytes, and PCM
peaks 13,147–14,797. This verifies exact clip access and decoding, not physical
gameplay/crop behavior. The index join took 3.699 seconds using the captured live
inventory; the three production playback probes took 18.062 seconds.

Current private evidence is under `output/checks/endfield-voice-resolve/`, with
the earlier pack/ordinary-conversation proof in
`output/checks/endfield-live-recheck/`. Raw tables, subtitle text and clips stay
ignored and are not published.

## Update resilience and validation

Language index version is 3. Additive metadata fields are tolerated. Changed
required table shapes, missing core conversation data, malformed inventory
structures and changed localization structures return `unsupported_game_format`
with an actionable toolkit-update message. Missing optional categories produce
coverage warnings. Unknown SNS types are excluded and counted. The archive
fingerprint covers both VFS layers, case-insensitively; a concurrent game update
fails preparation while leaving the previous snapshot untouched.

The adapter never infers silence from a missing recording or an empty override.
Only verified text-only modalities receive `unvoiced`; generic events and
authored but missing recordings receive `unavailable`; default/blank voice
references receive `unknown`. Ambiguous filename stems, placeholder and
unsafe source paths cannot bind recordings. Capture of text-only records remains
subject to the user's opt-in and exact-match safeguards.

Focused regression command:

```text
.venv/Scripts/python.exe -m pytest backend/tests/test_endfield_audit.py backend/tests/test_new_rpg_languages.py -k "endfield or declared_translation" -q
```

Result: **48 passed, 17 deselected in 0.68 seconds** for the completed mapping
and language-capability changes.

The focused regression cases cover voice-state evidence, exact bark IDs across
all five study locales, ambiguous filename rejection, missing-metadata versus
missing-locale diagnostics, operator bindings, media exclusion, missing reading
links, schema drift, optional-category warnings, absent-pack preparation for all
four official voice languages/both Chinese scripts, and snapshot retention.

The audit evidence and timings are retained privately under
`output/checks/endfield-audit/`, including inventory, decoded schema evidence,
bounded audio-header inventories, adapter/locale summaries and JUnit results.
No full suite or publication audit was run by this game-specific audit.

Native acceptance still requires physical gameplay observation, screenshots
across each narrative layout, desktop/mobile crop behavior, windowed/fullscreen
capture, zoom and Windows DPI bounds. Chinese package presence and production
clip extraction/decoding are verified as described above. File and playback
evidence does not establish that every presentation appears inside a capture crop.
