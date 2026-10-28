# Persona 5 Royal language and dialogue audit

Reviewed 2026-10-28. Game ID: `persona5royal`; Steam application `1687950`;
Windows process: `P5R.exe`. This is **partial native dialogue coverage**, not a
claim that every displayed line has a resolved original recording.

## Official languages and installation

The [English Steam matrix](https://store.steampowered.com/app/1687950/Persona_5_Royal/)
and [Japanese Steam matrix](https://store.steampowered.com/app/1687950/Persona_5_Royal/?l=japanese)
list English and Japanese full audio. English, Japanese, French, Italian,
German, Spanish (Spain), Korean, Simplified Chinese and Traditional Chinese have
interface and subtitle support. No Mandarin, Korean or European-language dub is
advertised. The [ATLUS product site](https://persona.atlus.com/p5r/) identifies
the Steam release; [SEGA's regional site](https://asia.sega.com/p5r/cht/) also
documents the Japanese cast and the social/battle content, but its PS4 edition
must not be treated as proof of another PC voice pack.

Both official voiced languages remain implemented choices when their files are
absent. The native installation had `EN.CPK`, `SOUND_E.CPK`, `SOUND_J.CPK`,
`BASE.CPK` and `MOVIE_JE.CPK`. Each voice CPK has 3,352 members, including 1,786
ACB cue banks; the two packs use the same virtual paths and cue schemas, with
different original recordings and durations. Japanese text was not installed.

| Study/audio locale | Text CPK | Original voice CPK | Native evidence |
| --- | --- | --- | --- |
| `en` | `EN.CPK` | `SOUND_E.CPK` | Complete installed-text index; representative story and battle recordings decoded |
| `ja` | `JP.CPK` | `SOUND_J.CPK` | Voice banks inspected and representative story/battle recordings decoded; text indexing requires the absent Japanese pack |

The other text paths are `FR`, `IT`, `DE`, `ES`, `KR`, `SC`, and `TC`, followed by
`.CPK`. These identifiers are documented in the
[Persona Essentials locale mapping](https://github.com/Sewer56/p5rpc.modloader/blob/master/p5rpc.modloader/Mod_Merging.cs).
Their shared message schema and locale-specific character metadata are
implemented, but their native text has not been tested here. A missing target
translation is reported separately from the selected study/audio language.

Select the study text language in Steam Properties → Language, let Steam finish
the download, and run Prepare again. Choose the matching original voice language
inside the game. A missing study text pack produces an actionable error; a
missing dub remains missing/unavailable rather than silently selecting the other
recording. Verify game files to repair incomplete downloads. Do not rename or
modify game archives to change language.

## Authored formats and bindings

The reader accesses named CPK members through bounded CRI UTF tables and
CRILAYLA decompression. It reads big/little-endian MSG1 messages, their authored
speaker table, separate pages, selection records, FLW0 embedded message sections,
and nested PAK/PAC messages. It does not execute game scripts. Counts include
alternative resources, duplicated messages, debug remnants and system text;
they are not a count of unique dialogue heard during a playthrough.

The message voice instruction is table 3, function 1 with six encoded arguments.
The current implementation resolves the event-context selectors `(1|6|8,0,0)`
against the exact matching event bank, and `(1|6|8,0,2)` against the exact battle
event bank. It reads the fourth argument as an ACB cue ID, then follows the ACB
reference through one sequence, one track, one synth and one waveform. Direct
wave/synth references are also supported. The AFS2 table supplies the exact AWB
ID and bounded ADX extent. It never substitutes the nearest cue, waveform index,
file order, a different event or the other language's recording.

Index version 2 also reads constant `SND_VOICE_DLYEVT_SETUP` (`0x180`) and
`SND_VOICE_DNGEVT_SETUP` (`0x140`) calls in FLW0 scripts. A later message call
within the same straight-line block may bind selector `(1|6|8,0,0)` to that
explicit event bank. Procedure calls, branch boundaries, label entry points,
unknown native calls, conflicting uses of a message and runtime-selected message
IDs invalidate the binding. The reader does not execute scripts or infer a bank
from a nearby setup call in another procedure. The
[P5R native function schema](https://github.com/tge-was-taken/Atlus-Script-Tools/blob/05483fe12f9c482ee17f38ded2e115f4c55015b3/Source/AtlusScriptLibrary/Libraries/Persona5Royal/Modules/Common/Functions.json)
documents these setup and message calls. Installed scripts establish the
constant major/minor event IDs and exact cue IDs.

The message format and voice instruction are documented by
[Atlus Script Tools](https://github.com/tge-was-taken/Atlus-Script-Tools/tree/05483fe12f9c482ee17f38ded2e115f4c55015b3/Source/AtlusScriptLibrary/MessageScriptLanguage)
and its
[Persona 5 Royal function metadata](https://github.com/tge-was-taken/Atlus-Script-Tools/blob/05483fe12f9c482ee17f38ded2e115f4c55015b3/Source/AtlusScriptLibrary/Libraries/Persona5Royal/MessageScriptLibrary.json).
The event/cue relationship is additionally evidenced by the installed tables and
the [format researcher's event-audio workflow](https://github.com/lraty-li/Persona-Modding/tree/main/classify_sound_file).
That workflow's order-based or ambiguous fallbacks are not used.

Every indexed voiced page plays its complete authored cue. ACB sample count,
sample rate and channels are retained and checked after decoding; ACB cue length
is retained as metadata. There are no inferred word timings or guessed cuts.
Complex, random, delayed and multi-note cue graphs are unresolved. A text page
containing multiple voice calls is unavailable rather than assigned one of them.

Confirmed unvoiced entries are selection options with no voice instruction, and
event pages explicitly invoking cue zero whose installed ADX is demonstrably
silent: all decoded residual nibbles are zero. Many such cues are in `BASE.CPK`.
The base archive is consulted only for this proof of silence when the localized
bank is absent. It is never a source of fallback speech. Missing recordings,
unknown selectors, ordinary messages with no voice instruction, and failed
decoding are not proof of silence.

## Presentations and remaining gaps

| Presentation | Implemented evidence | Remaining limitation |
| --- | --- | --- |
| Story, social/confidant scenes, in-engine cutscenes | Event messages, speaker names, exact event cues, authored pages and verified silent cues | Some event bank contexts remain unresolved; no chronological reconstruction or confidence about resource reachability |
| Battle event conversations | Exact event-bank cue IDs and original ADX | Combat/navigator barks and negotiation messages can use runtime-selected or shared banks; many are unavailable or unknown |
| Response options and thought/selection UI | Selection format establishes text-only options; shared capture toggle applies | Short choices may match later voiced dialogue, so they must veto voiced matching even with text-only capture disabled |
| Phone conversations | Text and selection pages indexed; 92 spoken companion-comment pages have explicit flow setup/cue bindings | Ordinary phone pages without explicit silence evidence remain unknown; shared reactions and setup across procedures/branches remain unresolved |
| NPC/ambient speech, greetings, field conversations | Authored message pages and speakers indexed | Shared selector families, field bank setup and runtime-dependent scripts are not yet bound; non-subtitled barks cannot be matched from OCR |
| Books, descriptions, tutorials, minigames, Thieves Den | BMD/BF messages, including nested packages | 26 FTD/TBL/binary sources and 12 nonbinary tutorial source files remain unparsed; ordinary nonvoiced-looking text is kept unknown |
| Animated movies | 103 USM members inventoried in the movie CPK, plus one in the installed text CPK; stream directories and subtitle placeholders inspected | No exact localized movie-caption/audio binding is established; no movie dialogue recording or timing is claimed |

[Message-window documentation](https://docs.shrinefox.com/flowscript/library-functions/persona-5)
distinguishes regular speech, thought windows, system messages, choices and phone
windows. This corroborates the distinct presentation families found in the
installed scripts. Some voice calls play a short reaction alongside a longer
text page; unresolved shared reaction calls are not presented as full spoken
performances of that text.

The follow-up movie inventory found 43 resources with two audio streams, 26 with
one audio stream, 30 with no audio stream, and five with one audio stream plus a
subtitle stream. Every one of those five subtitle streams contains a single
`Dummy` placeholder, not dialogue. Representative regular movies use VP9 video
and encrypted six-channel HCA audio. Their stream directories identify channel
numbers without language tags; even both audio filenames can carry a Japanese
build-directory label. Channel order therefore does not establish voice locale.
One legacy movie directory contains non-UTF-8 filename metadata. No complete
localized movie subtitle/timing table was identified in the locale archive or
the inspected executable data. Full-track playback support cannot fill in a
missing caption identity or choose a language without that evidence.

The executable additionally contains 33 embedded MSG1 resources of 1,281 battle
navigator messages each. They use selector `(8,1,65535)` and character families
3, 8 and 9. Their locale/character dispatch and original bank association remain
unverified, so they are not added as guessed voices or folded into the archive
page counts below. Resolving them requires the executable's resource-selection
tables and voice-bank dispatch, not choosing a table by its apparent language.
Shared selector families such as `(8,2,1)` also remain unresolved: the large
singleword bank contains short reactions, and a cue-number match alone does not
prove that it performs the displayed paragraph. More complete field coverage
requires branch/call-aware bank state and cross-script resource references.

Ordinary portrait balloons occupy the lower part of the image with variable
width and angle. Thought bubbles and choices can be central; phone conversations
use a central/right panel; world NPC bubbles move with their characters; battle
navigator text can be near the upper right. A bottom-only crop is insufficient.
The integration keeps the primary subtitle crop and uses an independently stable,
exact full-frame pass for sufficiently long, unique verified dialogue. Confirmed
text-only choices block ambiguous voiced hits. Short/ambiguous bubbles are
deliberately skipped. Asset extraction does not prove physical capture, Windows
DPI, OCR, portrait positioning or every resolution; those native checks remain
outstanding. Calibrate independent regions for unusual layouts.

## Native evidence

The version 2 installed English index completed in approximately 79 seconds. It
read 7,382 message sources, 1,187 localized banks and 498 shared silence banks.
Of 191 field/chat scripts containing explicit event-bank setup calls, 57 yielded
59 unambiguous constant message bindings under the conservative rules. These
resolved 94 additional voiced pages. Four further pages require runtime text
substitution and remain unknown; two authored cues are absent from their bank.

| Category | Voiced | Confirmed unvoiced | Unavailable | Unknown |
| --- | ---: | ---: | ---: | ---: |
| Story/social event | 28,352 | 32,182 | 32,576 | 7,717 |
| Battle dialogue | 1,930 | 0 | 683 | 9,795 |
| Choice | 0 | 25,160 | 0 | 5 |
| Phone message | 92 | 0 | 2,754 | 21,227 |
| Field dialogue | 2 | 0 | 42,323 | 36,447 |
| Ambient/NPC | 0 | 0 | 26,008 | 4,633 |
| Readable/system text | 0 | 0 | 296 | 9,968 |
| Other message | 0 | 0 | 740 | 2,136 |
| **Total** | **30,376** | **57,342** | **105,380** | **91,928** |

Unavailable pages break down as 87,997 unresolved bank selectors, 14,904 absent
context banks, 2,383 missing authored cue IDs, 93 multi-voice pages, and 3
non-silent/unverified zero cues. No installed voice pack was missing in this
audit. Another 4,771 pages require runtime substitutions and are kept unknown.
Five unsupported ACB cues were inventoried; none was guessed into a binding.

Representative event cue 1 decoded to 126,029 frames at 24 kHz in English and
120,332 frames at 24 kHz in Japanese. Representative battle cue 1001 decoded to
130,396 frames at 48 kHz in English and 150,163 frames at 48 kHz in Japanese.
All were mono and matched their ACB waveform dimensions. These are original
recordings extracted from the installed voice packs. This proves extraction and
decoding of these samples, not complete-game playback or Japanese-text indexing.

Newly resolved phone/social bank `e487_003`, cue 1, decoded to 33,335 frames in
English and 52,809 frames in Japanese, both mono at 24 kHz. The ACB dimensions
matched the decoded WAVs. All 94 new bindings were checked against the installed
wavebank and native byte extents; the original event/battle samples were not
retested during this follow-up.

Raw indexes, sample audio and detailed probes stay under ignored
`output/checks/persona5-native/`; subsequent movie/flow probes, updated aggregate
counts and phone-audio samples are in the private follow-up artifact directory
on the designated generated-artifacts drive. No game dialogue, audio, archive, account data
or machine-specific installation path belongs in the repository.

## Tools, metadata and regression checks

The existing verified vgmstream decoder handles the original encrypted ADX;
the adapter's `decode_voice_source` hook validates the resulting WAV before the
shared export pipeline proceeds. A missing decryption key is a decoding failure.
No game modifications, external process injection, accounts or online writes are
required.

The game uses custom character indices rather than Unicode. Prepare downloads
only SHA256-pinned TSV mapping data from Atlus Script Tools commit
`05483fe12f9c482ee17f38ded2e115f4c55015b3`, plus its
[GNU GPL v3 license](https://github.com/tge-was-taken/Atlus-Script-Tools/blob/05483fe12f9c482ee17f38ded2e115f4c55015b3/LICENSE.txt).
Tables and license/notice are cached privately under `persona5-charsets` in the
language data directory. No downloaded code is executed. The first preparation
requires internet; a checksum-verified cache supports subsequent offline runs.
Failure to acquire that metadata produces a specific retry message.

`backend/tests/test_persona5_assets.py` uses tiny generated fixtures for UTF/CPK
bounds, both MSG1 byte orders, distinct pages/choices, CRILAYLA, both package
layouts, cue graphs, AFS2 limits, missing locale packs, offline metadata failure,
explicit silence versus missing speech, unsafe paths and decoded dimensions.
Additional generated FLW0 fixtures check both byte orders, constant setup,
branch/call barriers, conflicting and dynamic message uses, wide constants and
invalid label targets. A synthetic phone-message index exercises the complete
setup-to-original-audio path. Eight focused tests passed after this expansion.
These tests do not need a game, network access or the decoder. Broader regression
coverage and capture/export integration belong to the shared change and hosted CI.
