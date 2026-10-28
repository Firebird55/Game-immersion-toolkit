# Portal 2 language and dialogue audit

Reviewed 2026-10-28. Game ID `portal2`; Steam application `620`; Windows process
`portal2.exe`. This is partial native dialogue coverage. Unresolved recordings,
absent language packs and confirmed text-only content remain distinct states.

## Official languages and installation

[Valve's Steam matrix](https://store.steampowered.com/app/620/Portal_2/), checked
on the review date, lists five full-audio languages and 27 interface/subtitle
languages. All five spoken languages remain supported choices when their packs
are absent. No extra regional spoken edition was established by these sources.

| Spoken locale | Native identifier | Interface / subtitles / audio | Verification |
| --- | --- | --- | --- |
| English `en` | `english` | Yes / yes / yes | Installed text, bindings and representative original recordings decoded |
| French `fr` | `french` | Yes / yes / yes | Installed text; absent voice-pack schema tested synthetically |
| German `de` | `german` | Yes / yes / yes | Installed text; absent voice-pack schema tested synthetically |
| Spanish (Spain) `es-ES` | `spanish` | Yes / yes / yes | Installed text; absent voice-pack schema tested synthetically |
| Russian `ru` | `russian` | Yes / yes / yes | Installed text; absent voice-pack schema tested synthetically |

The additional interface/subtitle locales are Bulgarian `bg`, Czech `cs`,
Danish `da`, Dutch `nl`, Finnish `fi`, Greek `el`, Hungarian `hu`, Italian `it`,
Japanese `ja`, Korean `ko`, Norwegian `no`, Polish `pl`, Portuguese (Portugal)
`pt-PT`, Portuguese (Brazil) `pt-BR`, Romanian `ro`, Simplified Chinese
`zh-Hans`, Spanish (Latin America) `es-419`, Swedish `sv`, Thai `th`, Traditional
Chinese `zh-Hant`, Turkish `tr` and Ukrainian `uk`. All 27 text resources were
read locally. Their identifiers agree with the installed resources and
[Steam's language identifiers](https://partner.steamgames.com/doc/store/localization/languages).
Text-table presence does not guarantee a translation for every retained line:
the English merged table has 3,303 tokens, whereas Japanese has 3,259,
Norwegian 3,240, Thai 3,246 and Traditional Chinese 3,287.

Select the desired language in Steam Properties → Language, finish its
download, then Prepare again. Verify files to repair an incomplete pack. The
reader never changes Steam settings or downloads game assets. A matching,
completed Steam `MountedConfig` language is required before shared English
recordings can be used. A requested `UserConfig` change alone is insufficient.
Moved English installations without the matching manifest need Steam file
verification.

The installed `gameinfo.txt` documents adding `_<language>` mounts ahead of
each game mount. Official localized directories use this schema, including
`portal2_french` and `portal2_dlc1_french`. The adapter supports their `pak01`
VPKs and loose voice/media resources with the same authored event names. A
non-English request searches only its explicitly identified localized mounts;
shared English dialogue, commentary, movies and music cannot fill a missing
dub. The four non-English voice packs were absent on the audited PC. Their
container, mount and binding schemas have synthetic coverage; their playback
has not been natively verified.

## Mounts, captions and original recordings

The native effective order is `update`, `portal2_dlc2`, `portal2_dlc1`, then
`portal2`. The reader validates application identity and reads the highest
official DLC's `SearchPaths`, retaining priority across VPK and loose files.
It never follows arbitrary external/custom paths. Sound manifests and scene
images use replacement semantics; caption and UI tables merge base-to-DLC so
new captions do not hide the original campaign. Peer Review and Perpetual
Testing Initiative resources are included. Valve's
[official update history](https://www.thinkwithportals.com/blog.php) also
documents co-op, intro movies, the credits and Cave Johnson's Workshop-queue
dialogue; presence in the index does not prove that every retained resource is
reachable in the current game.

Named tokens from `subtitles_<language>.txt` and
`closecaption_<language>.txt` identify the matching compiled VCCD entries.
The compiled `.dat` text is authoritative. Duplicate source tokens in the
base closed captions and DLC1 are not treated as conflicting spoken variants.
The layout follows
[Valve's caption compiler header](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/captioncompiler.h).
English reference rows in localized text never fill untranslated entries.
Korean accepts the evidenced `koreana` filename / `korean` header alias.

The shipped Latin-American text sources have an additional byte-level carriage
return before every line-feed byte in UTF-16LE data. The adapter reverses only
that specific, validated signature for `latam`; compiled captions are intact.
Other malformed text retains the unsupported-format error. The test fixture
reproduces this transformation with synthetic text.

VPK member bounds, numbered-chunk availability and CRC32 are checked. The
latest scene image contains 4,891 VSIF version 3 entries with binary VCD version
4 choreography. Compared with
[Valve's published VSIF version 2 layout](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/scenefilecache/SceneImageFile.h),
the native version 3 summary has an additional last-speech-time integer before
the sound count. The dedicated reader validates that layout and reuses the
bounded raw/LZMA binary choreography reader. All 5,862 sound events were read
with no missing manifest scripts. Unique event-to-WAV bindings, active scene
caption overrides and commentary filename bindings are preserved. Distinct
randomized performances and unresolved events are never selected arbitrarily.
The shared caption matcher also rejects identical visible wording associated
with different original recordings; separate sound-event IDs alone cannot
disambiguate such OCR observations.

Extraction re-resolves the original binding and compares locale, member,
mount, timing and binding signature before reading audio. There is no filename
similarity search, translated substitute recording or account write.

## Presentation inventory and limits

The English index contains 3,116 records: 2,873 with original audio, 85
confirmed text-only records and 158 unavailable recordings. These are indexed
resource rows, not a claim of 3,116 distinct playable conversations.

| Presentation | Indexed rows | Coverage and capture region |
| --- | ---: | --- |
| Campaign, PA, recorded Cave Johnson, Wheatley/GLaDOS/cores and co-op speech | 2,589 | Native subtitle/event bindings, including both DLCs; usually lower HUD captions, separately in each split-screen viewport |
| Turret and ambient caption families | 281 | Exact events supported; captions shared by different randomized recordings remain unavailable |
| Developer commentary | 82 | Original filename-bound recordings and localized captions; large commentary panel needs full-frame or independent calibration |
| Commentary titles | 83 | Explicit `commentary_title_` text-only headings, available through the unvoiced capture toggle |
| Prerecorded ending captions | 38 | Individual authored movie cues; never an entire future conversation |
| End-credit song lyric groups | 41 | Separate visible English lyric groups; playback is explicitly the complete original song |
| Credits report headings | 2 | Literal English text-only headings; capture the terminal area, not only the lower subtitle band |

There are 268 excluded SFX/nonverbal captions. Music, sound effects, a missing
recording and a failed voice lookup are not classified as unvoiced dialogue.
Of the 158 unavailable voice rows, 127 have no unique resolved sound binding;
the remaining 31 have an authored path without an installed original recording.
An additional 33 voice-directory paths lie outside resolved caption bindings;
that is an asset diagnostic, not an invented transcript.

The base co-op ending, single-player ending callback and Peer Review ending
have `media/*_captions.txt` files containing stable `cheaptitles_` identifiers,
color and start/end seconds. Text comes from the exact UI key or the associated
compiled subtitle token. Where the token identifies a unique original sound
event, that recording is used. Otherwise only its own timed Bink segment is
decoded. Thirty-eight of 40 authored cues have independently identifiable text.
Two DLC cues have `a`/`b` suffixes but only a combined unsuffixed subtitle; those
two movie text splits are unresolved and are not guessed from punctuation.

The native Bink files contain four audio tracks with channel counts 2/1/1/2.
The reader validates their IDs, sample rates and topology and mixes all tracks
to stereo; selecting the first track alone can omit speech. This is an original
movie mix, not an isolated dialogue stem. Header decoding follows the
[FFmpeg Bink demuxer](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/bink.c);
[RAD's Bink documentation](https://www.radgametools.com/binkhmab.htm) explains
why multiple tracks can be speaker stems rather than alternative languages.
Different unverified track layouts fail closed. Native verification covered
the installed English layout only.

`scripts/credits.txt` contains literal English text and typewriter/display
durations, not localized lyric IDs. Consecutive displayed fragments form 41
lyric groups separated by authored pauses/control markers. A group does not
expose later groups. The `music.sp_a5_credits` event supplies the complete
original English song, labelled `song_full_track`; display timings are not
asserted to be exact sung-line cut points. Other study locales do not relabel
these English-only lyrics or headings as translated dialogue.

| Other mode | Evidence and remaining boundary |
| --- | --- |
| In-engine cinematics and prerecorded announcements | In-engine speech shares subtitle/event resources; only movies with an authored caption timeline are included in the movie reader. |
| Conversation choices | No branching dialogue-choice text schema was established. Generic tutorial, menu, puzzle-editor, achievement and chat UI is not imported as dialogue. |
| Radio, turret opera and other music | Captioned verbal events can resolve normally. Instrumental loops, nonverbal captions and unsubtitled performances have no invented text binding. |
| Environmental readables | Wall writing, graffiti, test-chamber signs and screens baked into textures lack native localized text bindings here; they remain unsupported. No independent interactive document database was established. |
| Comics | Valve's external Lab Rat comic is separate from the installed game's text/voice resources and is outside this reader. |
| Workshop and custom content | Official PeTI Cave Johnson recordings are included. User-authored maps, custom mounts, map-packed speech, mods and fan dubs require separate compatibility evidence. |

## Checks and capture acceptance

Enable the game's subtitles/captions. Use full-frame matching or independent
regions for gameplay subtitles, each split-screen viewport, commentary and the
credit terminal. A bottom-only crop is incomplete. Short repeated phrases,
partially visible commentary and short lyric fragments can remain ambiguous.

Read-only native checks loaded all 27 text locales and decoded representative
English GLaDOS, Wheatley, Cave Johnson, turret and commentary WAVs, one timed
four-track movie cue and the full credit song. The four absent localized packs
retain translated records with zero original-audio bindings. Synthetic tests
cover all five audio locales, additive DLC tables, mount priority, missing
packs, compiled duplicate tokens, the Latin-American encoding signature,
VSIF3 bounds, Bink topology, cue isolation, full-track credits and extraction
reference tampering, normalized snapshot loading, identical-caption ambiguity
and the unvoiced capture toggle. Compact evidence stays in ignored
`output/checks/portal2-native`; large generated audio and screenshots stay
outside the repository. Tracked fixtures contain no game text or recordings.

This asset audit does not establish live OCR accuracy, physical mobile capture,
Firefox/Chromium rendering, ultrawide, zoom, Windows DPI or actual capture
bounds. Those remain capture acceptance checks. Regional non-Steam editions,
future formats and the unresolved presentations above are not claimed complete.
