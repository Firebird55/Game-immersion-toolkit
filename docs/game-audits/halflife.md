# Half-Life — original GoldSrc edition

Reviewed 2026-10-28. **Spoken-dialogue capture is not ready.** The implemented
scope is confirmed unvoiced screen messages, language-pack detection and an
original-audio inventory. Reading a WAV or recognizing its waveform cannot
create a publisher-authored transcript.

This adapter identifies Steam app **70**, `hl.exe` and `valve/liblist.gam`.
Half-Life: Source (app 280), Black Mesa, Blue Shift and Opposing Force are
separate editions/products and are not substituted for it.

## Official language availability

The [publisher's Steam language matrix](https://store.steampowered.com/app/70/)
lists interface and full audio for all eight languages below. Its subtitle
column is empty. This differs from the Source games' caption systems.

| Locale | Official interface/audio | Independent GoldSrc mount | Native verification |
| --- | --- | --- | --- |
| English (`en`) | Yes / yes | `valve` | Installed files, indexing and sample decode |
| French (`fr`) | Yes / yes | `valve_french` | Shared schema and synthetic encoding/mount tests |
| German (`de`) | Yes / yes | `valve_german` | Shared schema and synthetic encoding/mount tests |
| Italian (`it`) | Yes / yes | `valve_italian` | Shared schema and synthetic encoding/mount tests |
| Spanish, Spain (`es-ES`) | Yes / yes | `valve_spanish` | Shared schema and synthetic encoding/mount tests |
| Simplified Chinese (`zh-Hans`) | Yes / yes | `valve_schinese` | Shared schema and UTF-16 tests |
| Traditional Chinese (`zh-Hant`) | Yes / yes | `valve_tchinese` | Shared schema and UTF-16 tests |
| Korean (`ko`) | Yes / yes | `valve_koreana` | Shared schema and UTF-16 tests |

The seven absent packs remain selectable. Choose the corresponding language in
Steam game Properties, wait for the download, then prepare it. Missing packs
produce an actionable state; another language's WAVs or title strings never
replace them. Installing a pack does **not** resolve the absent official speech
transcript. There is no claim of native playback validation for absent packs.

Valve's issue tracker documents the localized title mounts and UTF-16 title
files for Chinese/Korean, and records game-side rendering failures. The reader
decodes those authored resources, but cannot repair glyph rendering or promise
successful OCR of text the game does not display correctly. See
[Valve issue 3456](https://github.com/ValveSoftware/halflife/issues/3456) and
[the underlying localization issue](https://github.com/ValveSoftware/halflife/issues/2490).

## Dialogue presentations and provenance

| Presentation | Authored evidence | Implemented behavior |
| --- | --- | --- |
| NPC conversations and ambient barks | Original WAVs, sentence groups and monster/script references | Inventory only; no official transcript binding |
| Soldiers, radio-like speech, suit and facility announcements | Ordered samples plus pitch, trim, time and pause controls in `sound/sentences.txt` | Inventory assembled/parameterized speech; never turn sample names into text |
| Scripted conversations and in-engine scenes | `scripted_sentence`, `scripted_sequence` and sample/group references | Count and retain the coverage gap; no invented cutscene captions |
| Intro cards, chapter names, credits/instructions represented as HUD text | `titles.txt`, `env_message`, `game_text`, world `chaptertitle` | Confirmed sound-free bindings are unvoiced records, with authored line anchors |
| Messages with an attached sound | `env_message.messagesound` | Unknown voice status, including when its WAV is missing |
| Unreferenced title/localization entries | Authored title table without a verified display/sound binding | Unknown; excluded from the unvoiced toggle |
| Signs and other world/model/sprite texture text | Raster textures rather than a verified text/voice table | Unsupported; no OCR-generated transcription represented as an official string |
| Choices, journals, tapes and comic panels | No separate structured authored dialogue tables established in this audit | No invented coverage claim |

Valve's [sound implementation](https://github.com/ValveSoftware/halflife/blob/master/dlls/sound.cpp)
loads sentence names/groups and selects their playback. Its
[scripted-entity implementation](https://github.com/ValveSoftware/halflife/blob/master/dlls/scripted.cpp)
describes scene control. Neither makes a sample filename a transcript.

The silent classification follows the explicit text presentation: `game_text`
emits a HUD message; `env_message` displays its named title and plays sound only
when its optional sound field is set. A title used by any sound-bearing
`env_message` remains unknown. These are sound-free **text entities**, not a
claim that the surrounding scene has no music or concurrent speech. The
relevant primary implementations are
[maprules.cpp](https://github.com/ValveSoftware/halflife/blob/master/dlls/maprules.cpp),
[effects.cpp](https://github.com/ValveSoftware/halflife/blob/master/dlls/effects.cpp)
and [world.cpp](https://github.com/ValveSoftware/halflife/blob/master/dlls/world.cpp).

Enable **Include unvoiced dialogue** to capture confirmed messages. Titles can
appear in the center, at the bottom or toward a corner; full-window exact
matching and the original line anchors are required. The usual bottom subtitle
crop cannot detect ordinary speech because original Half-Life has no such
subtitle track. No microphone, headset, audio loopback, injection or mod is
required by this limited message reader. Live OCR/DPI acceptance remains
separate from the file and synthetic checks.

## Native evidence

The installed English Steam build produced these counts:

| Evidence | Count |
| --- | ---: |
| BSP maps inspected | 125 |
| Title entries, including empty entries | 160 |
| Confirmed unvoiced message records | 97 |
| Unknown/unreferenced nonempty title records | 58 |
| Original WAV files, including effects | 2,542 |
| Sentence definitions | 1,065 |
| Direct single-sample definitions | 561 |
| Assembled/parameterized definitions | 504 |
| Repeated sentence identifiers | 4 |
| Direct definitions without installed selected sample | 4 |
| Scripted sentence / sequence entities | 203 / 512 |
| Announcement / ambient-sound entities | 33 / 2,018 |
| Scientist / guard / soldier / G-Man entities | 115 / 47 / 179 / 15 |
| Verified speech-to-authored-text bindings | **0** |

Message records deduplicate title identities, and chapter titles also have
world bindings; these counts are not a count of distinct spoken lines. The
index and original-sample check took about 7.4 seconds. One checksum-bound
original sample was extracted unchanged and decoded successfully through the
installed vgmstream decoder: mono, 11,025 Hz, 2.973 seconds. This proves sample
access and decoding, not dialogue-text or gameplay-capture coverage.

The optional installed Half-Life: Source content was inspected for an official
text bridge. Its own VPK had no close-caption resource. Of 2,521 WAVs sharing
original GoldSrc names, 2,463 had identical PCM data and parameters, while 58
differed; 21 original WAV names were absent. Sampled speech WAVs had no
transcript chunk.

Its `gameinfo.txt` also mounts shared Half-Life 2 resources. Those compiled
captions contain **101 HEV suit sentence identifiers**, all with the same
original/Source sentence control sequences after ignoring Source's duration
metadata. Of 98 distinct referenced samples, 97 have exact PCM identity and one
sample is missing. This establishes a potential partial suit-announcement
bridge, not an NPC conversation transcript library. Complete assembly timing,
locale-specific evidence and an original-game audio capture path still need
implementation and verification. These research candidates are not emitted as
voiced records. No Source audio, caption, translation or game edition is
silently substituted.

Private evidence is stored in ignored `output/checks/halflife-native`. It is not
distributed with the toolkit. No game resources, recordings, account metadata
or personal paths are committed.

## Bounds, changes and regression coverage

The reader implements bounded GoldSrc PAK directories, BSP v30 entity lumps,
localized title encodings and sentence inventory. Steam's audited files were
loose; synthetic PAK fixtures exercise the legacy archive layout. The
[publisher's BSP header](https://github.com/ValveSoftware/halflife/blob/master/utils/common/bspfile.h)
defines version 30 and the entity lump used by this reader. Current loose BSPs
are read only for that lump, not loaded wholesale. Untrusted member paths and
out-of-bounds data fail closed.

Fingerprints cover each supported locale's relevant maps, titles, sentence
tables, WAV metadata and PAK files. Saved games and user configurations are not
indexed. Files changing during preparation preserve the prior snapshot and
request another preparation after Steam finishes. Future incompatible formats
remain actionable reader errors.

The 39 focused synthetic cases cover all eight language mounts, Latin/UTF-16
encoding, missing-pack isolation, sound-bearing versus sound-free titles,
unvoiced toggle behavior, absent original samples, repeated sentence names,
PAK and BSP bounds, path traversal, exact original extraction and update
fingerprints. The outstanding requirement is official text for original-game
speech and a validated capture path for it; this audit does not mark that
requirement complete.
