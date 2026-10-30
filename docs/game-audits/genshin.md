# Genshin Impact narrative audit

Audited 2026-10-27 against an installed Windows 7.1.0 client and its English
voice pack. No account, game files, settings or live companion data were changed.
The read-only inventory found 1,985 asset BLKs, 275 USM movies and 310 audio PCKs.
The existing external-table reader resolved 169,523 English entries in 176 PCKs.
These are resource counts, not a claim that every resource is dialogue.

The metadata reference was Dimbreath's community mirror at
`792978e5503ecfba73dcb3562ed44a0d35a2abe2`, titled
`CNRELWin7.1.0_R48379043_S48511369_D48533839`. This is a third-party snapshot
of game data, not an official publisher API. The installed BLKs were inventoried
but their encrypted narrative data was not independently decoded. Matching the
release number does not establish that every server hotfix or optional asset is
present. Playback additionally requires the exact source hash and bounds in an
installed locale package.

## Presentations and limits

| Presentation | Observed evidence | Adapter behavior and remaining gap |
| --- | --- | --- |
| Quest and ordinary conversations | 23,208 Quest Talk files; 203,908 global DialogExcel rows; several coexisting Talk schemas | Parses supported authored ID/hash pairs. Runtime Talk records take priority; the global table fills absent IDs. Conflicting identities are excluded. |
| Optional NPC, gadget, furniture and hangout interactions | 16,927 Npc, 1,473 NpcOther, 1,485 Gadget, 1,287 Coop and associated group configurations | Supported Talk content is included regardless of whether it has audio. Group/routing configuration alone is not dialogue. Missing voice metadata stays unknown. |
| Events | 2,107 Activity Talk files, 105 ActivityGroup files, many dedicated event Excel tables | Supported event Talk content is indexed. Event-specific UI formats and expired/removed assets do not acquire coverage merely because ordinary event Talk works. |
| Ambient dialogue and reminders | 18,541 ReminderExcel rows; 1,798 BubbleTalkData rows; global dialogue fallback | Supported reminders use their own Medium-first text hash space and dialogue/tip/gameplay channels. `hasAudio: true` with missing audio is unavailable; omitted flags remain unknown. The separate BubbleTalk schema is inventoried but not mapped. |
| Character/profile and combat voices | 9,183 FettersExcel rows; voice triggers include Fetter, AnimatorEvent, WeatherMonologue, JoinTeam, Costume and Gacha | Not fully indexed. Fetter trigger arguments repeat across characters and need an exact character join. Filename or speaker guesses are not substitutes. Combat sounds without authored subtitles cannot be turned into transcript text. |
| Card-game dialogue and tutorials | 1,256 GCGTalkDetail rows with parallel content/voice arrays | Nonzero voice IDs are paired with the original array position, including gaps. Conflicting IDs are excluded. Zero-voice slots and emoji-only messages remain outside this import. |
| Choices and black-screen narration | 23,483 global forced-choice rows; explicit black-screen role types | Retained and tagged by authored modality. A player role, blank audio filename or missing voice does not establish silence. Exact voice bindings still take precedence. |
| Storyboards, comics and cinematic dialogue | 242 Storyboard Talk files, 159 StoryboardGroup files and 37 Cutscene Talk files | Supported Talk rows are retained; explicit storyboard/narration types receive cinematic channel coverage. No claim of complete comic layout or sequence recognition. |
| Prerendered cinematics | 319 English SRT files in the reference snapshot versus 275 installed USMs | Separately inventoried. The adapter does not decrypt USMs, bind their locale tracks or cut per-cue movie audio. SRT presence alone does not prove an installed playable clip; whole movies are never used as line audio. |
| Books, notes and readables | 1,919 English Readable text files; localized file identities | Version-matched book assets are indexed by paragraph as text-only content. Translations require the same file identity and paragraph count. Other readable assets and exact overlaps with known authored voice text remain unknown. This is not blanket support for voiced Travel Log archives. |
| Mail, messages and glasses chat | 323 MailExcel rows, three BirthdayMail routing rows, 421 obfuscated TpsGlassesChatMessage rows | Inventoried but not imported. Account mail and social chat are not accessed. The new glasses-chat fields need a verified text/voice schema before enabling that presentation. |

The reference contains 55,891 Talk files and 9,677 Voice files in total; many
are routing, lookup or emotion records. Counts overlap the presentation rows and
must not be summed as independent dialogue totals. Unrecognized content schemas,
missing localized text and unresolved performances produce public coverage
warnings rather than silently implying completeness.

## Update and voice safety

`LANGUAGE_INDEX_VERSION` is 2. The adapter checks the metadata release title
against the installed launcher configuration. A known version mismatch or wholly
unrecognized voice schema produces `unsupported_game_format` with a refresh/update
instruction. Unknown version provenance blocks text-only readable imports.
The common fingerprint includes text/config manifests and authored design data
where present, so voice-package stability alone is insufficient to reuse an index.

Voice paths must match an installed locale's hashed external entry. Missing
packages and ambiguous performances are retained as unavailable, not silently
unvoiced. Multiple performances are accepted only as one distinct male/female
pair; two same-gender candidates cannot produce duplicate IDs. Traversing or
absolute source paths are rejected. No audio is synthesized and no missing text
is translated or transcribed from sound.

Readable downloads are immutable-revision archives parsed in memory. The parser
rejects traversal, links, foreign directories, duplicate identities and excessive
file/expanded sizes. It never extracts upstream paths. Book capture remains the
global opt-in exact-match behavior; partial page text and unknown voice status
do not gain fuzzy unvoiced capture.

## Verification

Synthetic regressions cover schema drift, global fallback precedence, conflicts,
parallel card arrays, reminder hash collisions, player variants, missing versus
explicitly silent voices, version mismatch, typed modalities, paragraph alignment
and hostile text archives. See
[the dedicated tests](../../backend/tests/test_genshin_audit.py).

The local pinned-metadata probe completed in 30.94 seconds and retained 441,130
records: 146,834 with installed English audio, 43,431 unavailable, 245,679 unknown
and 5,186 verified text-only book paragraphs. The 8,071 readable paragraphs
include conservative unknown rows. These totals are not counts of
capture-eligible lines. Three bounded sample reads returned valid RIFF payloads
without exporting media. Private aggregate evidence and timings are retained
under ignored `output/checks/audit-genshin/`. The final targeted run passed 36
tests with 10 unrelated Endfield cases deselected.

GitLab REST/raw requests returned HTTP 429 during this audit. The schema and
binding probe used a local Git snapshot at the same immutable revision. It did
not prove production HTTP download availability. There was no live quest replay,
OCR/DPI run, movie decryption, non-English installed pack or controller/mobile
capture acceptance test in this game-specific audit.

## Primary references

- [HoYoverse developer discussion: dialogue playback, choices and Travel Log](https://genshin.hoyoverse.com/en/news/detail/7170).
- [HoYoverse 1.1 details: Books and Archive presentation](https://genshin.hoyoverse.com/en/news/detail/103763).
- [HoYoverse 1.4 notice: Hangout Events and event quests](https://genshin.hoyoverse.com/en/news/detail/9254).
- [HoYoverse published cutscene animation](https://genshin.hoyoverse.com/en/news/detail/165844).
- [Upstream reader implementation](https://github.com/simon300000/genshin-voice/blob/master/update.ts), inspected for authored joins and Medium text-map behavior; reader code is evidence of that implementation, not publisher documentation.
- [Upstream Talk reader](https://github.com/mrzjy/GenshinDialog/blob/main/extract_talks.py), inspected for NPC/gadget/event/hangout Talk handling.
- [Versioned metadata reference](https://gitlab.com/Dimbreath/animegamedata2/-/tree/792978e5503ecfba73dcb3562ed44a0d35a2abe2).
