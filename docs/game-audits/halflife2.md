# Half-Life 2 language and dialogue audit

Reviewed 2026-10-28. Game ID `halflife2`; Steam application `220`; Windows
process `hl2.exe`, disambiguated by `hl2/gameinfo.txt` and the HL2 VPKs.
This is partial native dialogue coverage for Half-Life 2 and its installed
anniversary episodes, with unavailable recordings kept separate from confirmed
text-only messages. File inspection does not establish physical gameplay or
screen-capture acceptance.

## Official campaign and language scope

[Valve's anniversary announcement](https://www.half-life.com/en/halflife2/20th)
confirms that Episode One and Episode Two are included in Half-Life 2 and adds
base-game developer commentary. The installed `hl2`, `episodic` and `ep2`
mounts are indexed independently. This installation also contains `lostcoast`,
`hl1`, `hl1_hd` and `hl2mp` resources. Those belong to separate games/modes and
are not substituted for Half-Life 2. Half-Life: Source is not GoldSrc Half-Life.

The official matrices differ: [Half-Life 2](https://store.steampowered.com/app/220/HalfLife_2/)
advertises seven full-audio languages, [Episode One](https://store.steampowered.com/app/380/HalfLife_2_Episode_One/)
advertises ten, and [Episode Two](https://store.steampowered.com/app/420/HalfLife_2_Episode_Two/)
advertises five. The reader supports their union while enforcing the campaign
limits below. The older episode store pages do not mark the subtitle column;
installed caption resources supply direct evidence of their localized text.

| Study/audio locale | Native identifier | Base game audio | Episode One audio | Episode Two audio | Native playback verified |
| --- | --- | --- | --- | --- | --- |
| English `en` | `english` | Yes | Yes | Yes | Representative original audio in all three campaigns |
| French `fr` | `french` | Yes | Yes | Yes | No; pack absent |
| German `de` | `german` | Yes | Yes | Yes | No; pack absent |
| Italian `it` | `italian` | Yes | Yes | Not advertised | No; pack absent |
| Korean `ko` | `koreana` / `korean` | Yes | Yes | Not advertised | No; pack absent |
| Spanish (Spain) `es-ES` | `spanish` | Yes | Yes | Yes | No; pack absent |
| Russian `ru` | `russian` | Yes | Yes | Yes | No; pack absent |
| Simplified Chinese `zh-Hans` | `schinese` | Not advertised | Yes, regional/legacy episode scope | Not advertised | No; pack absent |
| Traditional Chinese `zh-Hant` | `tchinese` | Not advertised | Yes, regional/legacy episode scope | Not advertised | No; pack absent |
| Thai `th` | `thai` | Not advertised | Yes, regional/legacy episode scope | Not advertised | No; pack absent |

All ten remain supported study choices even without installed recordings.
Episode-only choices do not imply a base-game dub or guarantee that Steam offers
that legacy episode pack for every account/edition. An absent pack produces an
actionable missing-voice state. Select the official language for the relevant
campaign in Steam Properties → Language, finish the download, verify game
files, then prepare again. The reader never changes Steam/account settings.
[Steam documents this language-download workflow](https://help.steampowered.com/en/faqs/view/4984-C127-121D-B3F2).

The 27 official base-game interface/subtitle locales are `en`, `fr`, `de`,
`it`, `ko`, `es-ES`, `ru`, `zh-Hans`, `zh-Hant`, `nl`, `da`, `fi`, `ja`, `no`,
`pl`, `pt-PT`, `sv`, `th`, `bg`, `cs`, `el`, `hu`, `pt-BR`, `ro`, `es-419`,
`tr` and `uk`. All 27 caption tables were read in all three installed campaigns.
Their names agree with the installed resources and
[Steam's language identifiers](https://partner.steamgames.com/doc/store/localization/languages).
Korean resources contain both evidenced filename spellings. Vietnamese UI
files alone do not establish another official subtitle or voice locale.

`gameinfo.txt` explicitly mounts `hl2_sound_vo_english`,
`ep1_sound_vo_english` and `ep2_sound_vo_english`, with their appropriate parent
campaign mounts, and documents language-suffixed directories. The reader
accepts explicitly identified `<stem>_sound_vo_<language>_dir.vpk` archives and
their numbered chunks, including language-specific official mount folders.
These shared schemas and all ten locale identities have synthetic format tests;
the nine absent languages have no native playback claim.

English episode voices and commentary also reside in shared `ep1_pak`,
`ep2_pak` and `hl2_sound_misc` archives. Shared archives are used for English
only when a completed matching Steam `MountedConfig` identifies English.
Requested `UserConfig` language changes or incomplete downloads do not prove
that state. A moved installation may need Steam file verification. No localized
request falls back to shared English audio. English reference text embedded in
translated tables is likewise never a translation fallback.

## Authored bindings and formats

VPK directories/chunks are read in place with member-size, path and CRC32
validation. Ordered KeyValues sound manifests preserve repeated wave options;
only unique sound-event bindings resolve. Displayed caption text comes from
VCCD `.dat` entries joined to named `.txt` tokens by lowercase-token CRC32,
following [Valve's caption compiler layout](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/captioncompiler.h).

VSIF v2 scene images and raw/Valve-LZMA BVCD v4 retain active channel groups,
caption overrides, original sound identifiers and authored timing offsets.
The layouts are documented in
[SceneImageFile.h](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/scenefilecache/SceneImageFile.h),
[choreoscene.cpp](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/choreoscene.cpp)
and [choreoevent.cpp](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/choreoevent.cpp).
Both episode string pools contain two legacy Windows-1252 debug labels;
this reader explicitly selects that encoding. Other Source readers retain
strict UTF-8 by default. Disabled, relative or conflicting performances are not
guessed. Extraction reconstructs and compares the authored reference before
reading original audio.

Each caption retains its authored identity. Future scene dialogue is not
concatenated into the current study sentence. Synthetic delayed-caption pages
remain separate text records and share explicitly labeled `full_track` audio
when no per-page recording cuts are authored. No delayed-page caption was
needed by this native English corpus. Repeated inherited entries with identical
text and original recordings share one matching identity, with their other
authored IDs retained as aliases.

Commentary caption keys identify original filenames, including WAV and MP3;
[Valve's commentary client](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/client/c_point_commentary_node.cpp)
uses those names for playback and captions. WAV PCM is retained directly; the
existing installed media decoder handles MP3 and authored timed compositions.

Text-only HUD resources use the retained Source `titles.txt` grammar and
bounded VBSP v19/v20 entity lumps, whose header/lump layout is in
[Valve's BSP header](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/bspfile.h).
Chapter/game-over title references, `game_text` and `point_message` content are
resolved through exact localization tokens when present. Literal English map
text is never relabeled as another language. Legacy grammar helpers are reused;
no GoldSrc map or audio assets are imported.

## Native inventory and coverage

| Campaign | Compiled English caption tokens | Manifest sound events | Scene image entries | Parsed campaign maps |
| --- | ---: | ---: | ---: | ---: |
| Half-Life 2 | 3,970 | 5,140 | 1,837 | 69 |
| Episode One | 3,145 | 7,968 | 3,681 | 18 |
| Episode Two | 4,437 | 14,398 | 4,849 | 22 |

Inherited scene/event resources mean these are inventories, not unique story
scene counts. There were no missing sound-manifest files. The index excludes
1,498 SFX/nonverbal caption entries across these tables and skips empty compiled
captions. One shipped Episode One demo map, `ep1_citadel_00_demo.bsp`, has an
undecodable entity resource; its readable text is explicitly reported as an
unsupported gap without discarding valid campaign voice data. One unresolved
HUD message is also reported.

With all 27 text targets requested, duplicate coalescing yields:

| Presentation family | Voiced | Unavailable | Confirmed unvoiced | Total |
| --- | ---: | ---: | ---: | ---: |
| Story conversations and in-engine cinematic captions | 5,047 | 2,543 | 0 | 7,590 |
| Ambient/NPC captions | 362 | 528 | 0 | 890 |
| Breencast/radio/HEV caption family | 86 | 2 | 0 | 88 |
| Developer commentary | 540 | 6 | 0 | 546 |
| HUD chapter/game-over titles and map messages | 0 | 0 | 52 | 52 |
| Total | 6,035 | 3,079 | 52 | 9,166 |

These families classify authored tokens, not observed UI screenshots. Native
HUD titles include center-screen chapter and failure messages; some direct map
messages may be dormant development content. Presence in a shipped resource
does not prove player-visible reachability.

The 3,079 unavailable records include unknown/ambiguous bindings and uniquely
named recordings not present in the installed resources. The campaign tables
contain 622 unresolved caption bindings before cross-campaign coalescing.
`$gender` paths cannot identify the visible NPC's selected performance;
randomized sound events also remain unavailable. The installed sentence table
contains 864 definitions, including virtual/random Combine and Overwatch radio
fragments and HEV pitch/sample assemblies. Playback-control words are not
transcripts, and these dynamic assemblies are not reconstructed as guessed
dialogue. None of these cases is labeled unvoiced.

| Other presentation | Evidence and boundary |
| --- | --- |
| In-engine cinematics | Original caption/sound/choreography bindings are indexed; they do not require joining an entire cinematic into one current sentence. |
| Radio and video screens | Breencast and other uniquely captioned speech use authored sound events. Dynamic fragment radio and audio without a visible authored caption remain gaps. |
| Commentary | Exact caption filename bindings cover present English recordings. Translated captions do not establish dubbed commentary. |
| Conversation choices | No branching dialogue-choice schema was established. Generic menu labels are not treated as silent dialogue. |
| Readables, signs and posters | Authored HUD/map text is supported by the unvoiced toggle. Writing baked into textures, models or scenery has no native localized text binding here and remains unsupported. |
| Comics, audio logs and movies | No separate comic/collectible-log text database was established. Startup/pre-rendered media and unsubtitled speech are not claimed as caption/audio bindings. |
| Other installed games | Lost Coast, Half-Life: Source and Deathmatch are explicitly outside this reader, as are workshop/custom overrides. |

## Capture and verification

Enable captions/subtitles in the game's audio settings. Ordinary speech uses
the lower caption HUD; commentary has a distinct panel; chapter and failure
messages appear around the center of the screen. For example, authored chapter
title layout uses centered X and Y `0.58`; that value is script layout evidence,
not a measured Windows capture rectangle. Use full-frame matching or independent
calibration for these regions. A bottom-only crop cannot cover all supported
presentations. Texture readables do not become supported simply by expanding
the crop.

Read-only native verification built the full English index with every official
text target, constructed every `LocalDialogue`, and loaded both
`LocalGameTextIndex` and `MultilingualTextIndex`. Representative exact matches
passed for story, ambient, radio, commentary and readable families. Original
PCM decoded from each campaign; the base-game MP3 commentary sample decoded
to 89.005 seconds of stereo 44.1 kHz PCM. The native indexing/matching/decode
probe completed in approximately 29 seconds. Only English voice files were
installed; all other voice probes reported missing.

The 17 focused synthetic tests cover ten locale choices with campaign-specific
eligibility, missing packs, English isolation, caption pages, authored scene
offsets, both exact-match indexes, the unvoiced toggle, extraction-reference
tampering, PCM decoding, legacy scene encoding, bounded/malformed maps and
exclusion of other installed Source games. Together with the affected Portal
and Source format suites, 42 tests passed in 3.38 seconds. These fixtures contain
only synthetic material. Sanitized native counters/timings live in ignored
`output/checks/halflife2-native`; game text and decoded samples remain private
local artifacts.

Native OCR, real gameplay, Firefox/Chromium rendering, mobile capture, zoom,
Windows DPI and physical capture bounds were not verified by these file probes.
Those remain separate acceptance checks; no physical-play claim is made here.
