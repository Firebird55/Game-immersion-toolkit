# Wuthering Waves dialogue audit

## November 16, 2026 · Long caption clocks are separate from audio limits

The current original `videocaption` table has seventeen positive display windows
that extend beyond five minutes: fourteen in `M2_12_07` and three in `M0355`.
They are ordinary frame values, not negative clocks, empty localized rows or a
different time unit. The original `VideoDefine` declares 30 frames per second;
`VideoView` compares the configured frame clocks with the movie's elapsed
milliseconds. Neither operation applies the toolkit's five-minute audio bound.
The longest checked caption ends at 461.833 seconds.

The caption selector now validates metadata against the signed frame domain,
independently of the bounded whole-track decoder and original-audio reference
validation. A direct check of the same publisher table returns all **1,353**
selected display cues in each of English, Japanese, Korean and both Chinese
study scripts, including these seventeen. The locale-selection and wholly empty
locale fallback rules are unchanged. Compatible later long scenes therefore do
not need an additional filename or caption-ID allowlist.

This does **not** make the seventeen long captions exportable audio. Whole-track
decoding and authorized publisher movie intervals retain their 300-second bound.
No clock becomes a voice binding, no new soundtrack is decoded merely to read
its caption, and no full spoken boundary is inferred from its display duration.
A regression accepts a later localized caption and its default-track fallback
while rejecting an audio export using those display times. Invalid, negative
and overflowing selected clocks remain excluded without borrowing another dub.
[Selected publisher launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json)
· [Publisher rolling configuration](https://cdn-akamai-hw-mc.aki-game.net/prod/client/zXGBurT1FHY5eBpEhgbCw7n85imvi3XR/Windows/config.json)

The ordinary Windows source-development publisher builder was run before and
after this correction for English study text with Simplified Chinese
translations. Both complete results are byte-identical after canonical JSON
serialization: 143,460 records, 48,856 voiced, 20,720 unvoiced, 2,167 unavailable
and 71,717 unknown, including both existing Jinhsi movie clips. The two warm-cache
runs took 14.688 and 13.328 seconds. None of the seventeen late caption IDs has a
numbered PlotAudio group, and both owning scenes declare mixed soundtrack
events outside the current single-voice clip adapter. Consequently no current
prepared record, voice, coverage warning or reader cache revision changes.

A separate cropped, unprompted English speech-recognition check of the existing
original `C3jiyanfight` and `LYSZW` tracks recovered words missed or badly aligned
by earlier whole-track recognition. The second `LYSZW` caption's wording is
spoken around 53 seconds in the original recording. The short General call has
unreliable word boundaries. These research estimates neither authorize a clip
nor resolve the other **seventeen** open spoken windows in those scenes and
`M0234`. Existing recordings and classifications remain unchanged.

## November 16, 2026 · Film performances versus ordinary PlotAudio sources

The 3.8.11 publisher table contains 311 movie captions whose text identity also
occurs in PlotAudio. Only 23 of those captions enable `IsPlaySubtitleVoice`.
The other 288 belong to 21 films and also occur in story-flow references.
The released `VideoView` posts the subtitle-triggered external recording only
when that flag is enabled. A false flag does not invalidate the ordinary
PlotAudio recording: the film may instead contain the same performance in its
separately authored track. A text-ID join and proof of the film performance are
therefore different evidence.

The November 16 comparison followed the six supported single-stream English
event banks below to their original publisher WEMs. The first four scenes use
separate voice events; the latter two use mixed soundtrack events. All six
events use the shared scene variant. Each standalone sample came from its exact
PlotAudio filename in the same selected English release, rather than from a
gameplay recording or a voice mirror.

| Film | Track duration | Standalone samples compared | Whole-sample correlation ≥ 0.4 | 0.19–0.4 | Below 0.19 |
| --- | ---: | ---: | ---: | ---: | ---: |
| C0001 | 193.490 s | 18 | 14 | 1 | 3 |
| C0002 | 185.544 s | 16 | 15 | 0 | 1 |
| C0003 | 99.473 s | 18 | 17 | 1 | 0 |
| C0004 | 117.971 s | 8 | 6 | 1 | 1 |
| M2_12_261 | 133.112 s | 10 | 10 | 0 | 0 |
| M3_2_13 | 94.176 s | 4 | 3 | 0 | 1 |

The comparison used 12-kHz mono PCM filtered at 280–4,500 Hz and normalized
cross-correlation. There were 65 strong whole-sample comparisons, three weaker
ones and six low results. The selected English caption windows were checked
independently using the game's per-scene language fallback. These are waveform
and source comparisons, not 65 verified full sentence-cut boundaries or a
new automatic acceptance threshold. They do not establish other dubs, complex
event graphs, gender-specific scene variants or the other 15 films.

Low whole-sample correlation is not proof of a different or missing performance.
For example, the existing ordered-section comparison recovers the six parts of
`Huanglong_main_1_4_199_53` in order around 110.439–117.366 s in C0002, despite
its low whole-sample score. In M3_2_13, `MAIN_YHX_53_4` is an active English
caption at 34.000 s. An unprompted speech-recognition pass recovers matching
wording in the standalone recording and estimates it around 33.760–38.940 s
in the film. Those estimates establish neither complete spoken boundaries nor
identical performance. This is not an example of an absent spoken sentence.

All six low-result standalone files were also retrieved from the retained
3.7.1 launcher snapshot's English base packages. Every file is byte-identical
to its 3.8 base counterpart, and none has a corresponding override in the
selected 3.7.6 or 3.8.6 English patch packages. This comparison supplies no
evidence of an old film take being replaced by a new ordinary recording.

No demonstrably wrong performance was established by this pass. The existing
ordinary PlotAudio sources are retained; no broad capture veto, voice rollback,
silence override or new film clip is introduced. Exact film performance and
presentation-specific capture remain separate coverage work. The 17 unresolved
spoken windows in M0234, C3jiyanfight and LYSZW remain open.
[Selected publisher launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json)
· [Publisher rolling configuration](https://cdn-akamai-hw-mc.aki-game.net/prod/client/zXGBurT1FHY5eBpEhgbCw7n85imvi3XR/Windows/config.json)

## November 16, 2026 · The game's per-scene subtitle-clock fallback

The current Global publisher source was inspected without installing or running
the game. Its launcher is 3.8.0 and its independently discovered core is 3.8.11;
the four dub revisions remain English 3.8.6, Japanese 3.8.5, Korean 3.8.8 and
Mandarin 3.8.5. The released
`Client/Content/Aki/JavaScript/Game/Module/Video/VideoConfig.js` has SHA-256
`63b0352b9ae0e0f685cec9b29f4512e3d9840a485e17b5fe3ff137596c608f76`.
It was read as static source, never imported or executed.
[Publisher launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json)
· [Publisher rolling configuration](https://cdn-akamai-hw-mc.aki-game.net/prod/client/zXGBurT1FHY5eBpEhgbCw7n85imvi3XR/Windows/config.json)

`VideoConfig.GetVideoCaptions` selects clocks for the current audio language,
independently for each complete scene. For English, Japanese or Korean, any
nonzero localized duration enables that scene's localized rows; individual
zero-duration rows are then omitted. Only a scene with no nonzero duration in
the selected dub falls back to the default clocks. Both Chinese study scripts
use the default track. The film matcher now uses that selected track's cue as
its search anchor, instead of always using the default-language start.

All **17** unresolved captions in M0234, C3jiyanfight and LYSZW have default
display windows selected by this fallback in every dub. Their zero localized
duration fields therefore do not mean the game has no caption clocks.
**These remain display windows, not verified full spoken intervals.** Selecting
a fallback clock does not itself establish a voiced caption or authorize an
export using its display times.
The existing original-media, overlapping-performance and acoustic-boundary
checks remain required.

The current publisher table contains 1,353 caption rows. The initial selector
retained 1,336 display cues per study locale, including the 17 unresolved cues
above. The long-clock correction described above retains the seventeen other
display windows independently of the film decoder's 300-second limit.
Nonzero localized timing occurs in 106 scenes for each non-Chinese dub;
no partially populated localized scene occurred in this particular release.
Synthetic regressions independently exercise that important partial-track case,
scene/locale isolation, invalid clocks and a localized anchor far from the
default start. Reader revision 6 refreshes previous language snapshots.

The original `VideoView` also confirms that subtitle-triggered external
PlotAudio playback requires `IsPlaySubtitleVoice`. The current table has 25
such captions, 23 sharing a PlotAudio identity. Another 288 captions share a
PlotAudio identity while that flag is false. This distinguishes the runtime
trigger from a text-ID join; it does not prove those 288 recordings differ from
their film performances. Their exact film/audio joins remain under review.

## November 13, 2026 · Global 3.8 launcher transition

The November 12 PC update moved the common game files and graphics tiers to a new official launcher index. The former Global endpoint still serves 3.7.1 while the active game resources use 3.8. Setup now reads the released common pack and checks its publisher checksum. It follows the pack's version, download directory and rolling game and dub manifests on subsequent preparations. [Kuro update notice](https://wutheringwaves.kurogames.com/en/main/news/detail/5705) · [Global PC launcher index](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json)

A fresh English preparation resolved 143,460 rows and 48,854 original-voice bindings from 44 launcher PAKs and the 3.8.9 core resources. The current English, Japanese, Korean and Mandarin dub revisions were 3.8.6, 3.8.5, 3.8.8 and 3.8.5. Each video quality tier advertised 236 packages. Setup retrieved an 8,484-byte English original for the trial line `ActivityRoleTrial_19_1`. It decoded to 118,903 non-silent mono samples at 48 kHz (2.477 seconds).

Mainland China Setup follows the separate G152/10003 common archive and its mainland configuration and resource servers. Its 3.8.0 common manifest lists 44 base PAKs. An installation-free mainland preparation returned 145,112 Simplified Chinese rows with 48,673 original performances. The Mandarin trial line from the mainland publisher was 9,528 bytes and decoded to 129,007 non-silent mono samples at 48 kHz (2.688 seconds). The selected region remains part of the saved publisher snapshot when rebuilding after an update. [Mainland launcher index](https://prod-volcdn-gamestarter.kurogame.xyz/launcher/game/10003_oLNgHF1CESo51DGHN2odtp40e3oI1HfZ/G152/official/index.json)

The source inventory tracks optional area and character package revisions in the same release snapshot. In Global 3.8 the 13 area groups supplied 26 base and patch PAKs with 680,487 directory entries under `Client/Content/Aki/`. None contained a ConfigDB table, an external voice path or a generated Wwise asset. The 236 localized character packages contained 34,267 numerically named WEM entries. They still need authored event-to-media mappings. Normal Setup follows these manifest versions and reads package contents selectively for supported rows. [Global release configuration](https://cdn-akamai-hw-mc.aki-game.net/prod/client/zXGBurT1FHY5eBpEhgbCw7n85imvi3XR/Windows/config.json)

### Jinhsi's origin film C0004

The released scene links music, effects and original voice to three separate events. Its SD movie package lists one MP4. The dedicated voice event, `play_vo_story_dtm_c0004`, resolves through the selected dub's bank to a 117.971-second, 48-kHz stereo recording. The opening and closing captions each have two numbered PlotAudio performances that overlap on this voice track. Both English takes speak the corresponding caption. The first and last lines can also be heard around 0:02–0:09 and 1:45–1:54 in the gameplay recording. [Global PC launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json) · [Jinhsi's opening narration](https://www.youtube.com/watch?v=4sQsSS4BZSU&t=2s) · [Closing narration](https://www.youtube.com/watch?v=4sQsSS4BZSU&t=105s)

Setup follows the current caption, numbered PlotAudio takes, event bank and streamed media in the selected publisher snapshot. It matches both takes against the voice track and extends the clip to a nearby quiet boundary. For a performance with shortened pauses, six independently matched portions must occur in the original order. Unresolved media and ambiguous matches leave the caption's audio unavailable. No scene IDs, media numbers or clip times are used as runtime lookup tables.

| Global 3.8 spoken language | Opening clip in the publisher track | Closing clip in the publisher track |
| --- | ---: | ---: |
| English | 1.175–9.538 s | 104.047–115.011 s |
| Japanese | 1.622–8.419 s | 103.280–114.633 s |
| Korean | 1.084–9.925 s | 103.239–113.251 s |
| Mandarin | 0.551–8.478 s | 103.836–114.224 s |

All eight clips were exported through the desktop service from the current Global launcher with no game installation. Individual playback and batch export of the same opening line produced identical MP3 bytes in each dub. English preparation now has 48,856 voice bindings. A second installation-free preparation on the mainland server yielded 145,112 Simplified Chinese rows and 48,675 voice bindings. Both Mandarin clips played and exported there. Global Traditional Chinese used the same two Mandarin performances. The remaining 17 dedicated-voice cues from the earlier four-scene audit still need exact original clips. English gameplay independently confirms one of them, the chapter-one storyteller's `Huanglong_main_1_7_178_3`, around 11:53–11:58. [Grand Warstorm gameplay](https://www.youtube.com/watch?v=qnIZlwn_A2o&t=713s)

### Three remaining films with separate voice events

The current Global launcher also supplies a separate original voice track for each of these scenes in every dub. The twelve streamed WEMs were selected by following each scene's authored event through the current localized bank and decoded to PCM. Track durations in seconds are:

| Scene | Open cues | English | Japanese | Korean | Mandarin |
| --- | ---: | ---: | ---: | ---: | ---: |
| M0234, the chapter-one storyteller | 12 | 87.744 | 89.000 | 89.500 | 88.524 |
| C3jiyanfight | 3 | 86.800 | 83.900 | 83.634 | 85.500 |
| LYSZW | 2 | 110.900 | 111.500 | 111.500 | 112.087 |

The English storyteller speaks the twelve caption texts in order. In the English C3jiyanfight recording, “General!” occurs around 51 seconds and the order to follow the Qingloong around 80 seconds. In LYSZW the repeated encouragement is audible within 18–23 seconds, followed by the call for help around 52–54 seconds. These clips need a repeatable per-language boundary before Setup can return just the selected caption. [Publisher configuration](https://cdn-akamai-hw-mc.aki-game.net/prod/client/zXGBurT1FHY5eBpEhgbCw7n85imvi3XR/Windows/config.json) · [Released scene captions and event definitions](https://github.com/Arikatsu/WutheringWaves_Data/tree/9218d612ad815e398e064e577e42aaf878899968/BinData/cgVedio)

## Global publisher updates and selective voice acquisition · November 9, 2026

From an empty private cache the source command followed the active 3.7.1 launcher to its base PAK, read the exact KuroPublicConfig entry by HTTP range, and selected the resource route declared inside it. The current core is 3.7.19. English, Mandarin and Japanese use 3.7.6 for voice overrides, and Korean uses 3.7.7. Each independently versioned core, voice and video index must match the digest in its publisher configuration. The SD, HD and UHD indexes each list 231 movie packages. The 1,549 receipt entries include base PAKs, resource and voice packages, movie packages and signature files. [Kuro Global launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json)

The same manifest reader verified 32 changed core entries between 3.7.17 and 3.7.18 and four between 3.7.18 and 3.7.19. The Korean 3.7.6 to 3.7.7 update changed two dub entries. The release command uses the bootstrap path in the current game package for later releases.

Replaying those publisher-listed revisions with the desktop table and audio
readers found four changed English/Simplified Chinese text records from
3.7.17 to 3.7.19. Their audio references were unchanged. Comparing all 46,336
Korean WEM paths across dub revisions 3.7.6 and 3.7.7 found the same paths.
The original `ko_vo_Side_FSCHPOI_11_13.wem` changed under its existing
name from 35,465 to 32,613 bytes. Both versions decoded to nonzero PCM at
48 kHz, lasting 8.500 and 7.885 seconds. Cached tables can be reused when
their containing package and entry are unchanged. Cached recordings retain
their release and spoken language.

The ordinary desktop refresh was also run against two previously prepared
language snapshots seeded from those published revisions. Without a forced
rebuild it activated the four text changes for English and the replaced
recording for Korean. Both versions of the Korean line remained playable
from the local cache after network access was disabled for that check.
Repeating the refresh on the current release reused the existing snapshot.

For an authored PlotAudio filename, the source command selects the chosen language's exact WwiseExternalSource path in the override, then consults the base if needed. It verifies the directory and the stored entry hash under the Kuro v12 layout. For partially encrypted WEMs that hash covers the encrypted prefix. Range responses must match the declared offsets and object size. The WEM framing and release pointers are checked before the selected output is saved. Two story filenames from the earlier PlotAudio audit were downloaded and decoded in all four dubs. For `vo_Main_Mengzhou_3_7_14_28` the English, Japanese, Korean and Mandarin durations were 9.678, 9.844, 9.409 and 8.675 seconds. [Regional source command](../../scripts/live_game_sources.py)

```text
python scripts/live_game_sources.py wuwa-global --cache private-cache --output wuwa.json --dub en --voice vo_Main_Mengzhou_3_7_14_28 --save line.wem
```

Windows Setup can prepare the current Global release with the game folder empty. Select the study language and translation in Games & Languages. The toolkit reads the publisher's story and localization tables, binds lines to exact paths in the chosen dub and retrieves the WEM for playback or a private library export. A prepared language is checked again when the launcher or resource manifests change. Each audio reference belongs to the same publisher snapshot as its text. Installed games still use their local archives.

A clean Windows language worker prepared 132,435 English rows with Simplified Chinese translations requested. It classified 46,461 as voiced, 20,074 as unvoiced, 2,119 as unavailable and 63,781 as unknown. Two short lines with translations decoded to non-silent MP3s through desktop playback. The private mobile library exporter produced byte-identical MP3s for those lines and included both translations. The sample covered about 1.83 and 0.91 seconds of speech.

All five study selections were prepared from released files with English and
Simplified Chinese requested as translations. Each selected an original WEM.
Counts include protagonist variants when the game supplies two performances.

| Study language | Prepared records | Records with an exact original voice |
| --- | ---: | ---: |
| English | 132,435 | 46,461 |
| Japanese | 132,504 | 46,518 |
| Korean | 132,302 | 46,281 |
| Simplified Chinese | 134,065 | 46,293 |
| Traditional Chinese | 133,198 | 46,280 |

The current four effective dub inventories include 185,918 external WEM paths.
Of these, 11,627 use Oodle compression, including 288 split across multiple
blocks. Fourteen real recordings covering the observed block counts and raw
storage decoded to PCM. The four-block English original was 204,483 bytes
and decoded to 2,533,115 frames at 48 kHz. The toolkit verifies the stored
entry, reads the game's block boundaries and uses its existing ooz-wasm
decoder for Oodle blocks. These inventories include sounds outside the
matched story records above.

The same 14 publisher samples produced byte-identical WEMs and decoded
PCM using the unchanged Node and ooz-wasm tools from the published Windows
v0.23.2 runtime. That check used cached package bytes, disabled network access
and an empty system PATH.

Conditional gender/choice selection, shared nonlocalized audio and per-caption film slicing still require their authored bindings. The reader uses the published Kuro catalogue format from mornye-tools, PAK format evidence from CUE4Parse and compatible archive parameters from wuwa-keys. [Catalogue format](https://github.com/Yumeo0/mornye-tools/blob/4591ef24949688ec9835bf910a204d6bbc4b339c/src-tauri/crates/game-client/src/discovery.rs) · [PAK entry layout](https://github.com/FabianFG/CUE4Parse/blob/6409f38e09e2a21aa839cd77b4515bca6c66f280/CUE4Parse/UE4/Pak/Objects/FPakEntry.cs) · [Archive format provider](https://github.com/yarik0chka/wuwa-keys)

## November 8, 2026 · Floating dialogue and film voices

The Global 3.7 floating subtitle database contained 46 distinct caption IDs
from its 2D and 3D tables. All had English and Simplified Chinese text.
Four IDs joined PlotAudio's exact localized sources, representing five
performances. The reader now indexes both tables and recognizes the
publisher's optional UHD movie packages during update detection.
Other named 3D sound cues retain an unresolved voice state until a localized
performance can be identified. [Kuro's Global update manifest](https://cdn-aws-hw-mc.aki-game.net/prod/client/TkSftmDssRx6BIKZBudzeoOHTnxjoL43/Windows/config.json)

Of 1,313 timed movie caption rows, 311 shared an identifier with PlotAudio.
The other 1,002 comprise 19 cues from four scenes with a dedicated voice
event, 528 with a full soundtrack, 431 with another scene event and 24 with
no such event. The 19 are in `M0234` (12), `C3jiyanfight` (3), `LYSZW` (2)
and `C0004` (2). All 19 have zero duration in the separate English, Japanese
and Korean timing fields. A scene event alone does not select a particular
dubbed line. The November 13 publisher preparation above resolves both C0004 cues.
The other 17 still need verified start and end points in the corresponding voice recording. The existing shared creature recordings also
remain separate from localized speech. [Publisher movie inventory](https://cdn-aws-hw-mc.aki-game.net/prod/client/TkSftmDssRx6BIKZBudzeoOHTnxjoL43/Windows/3.7.0/Video/VideoManifest_hd.json)
· [Caption and event tables](https://github.com/Arikatsu/WutheringWaves_Data/tree/9218d612ad815e398e064e577e42aaf878899968/BinData/cgVedio)

Audit date: 2026-10-27. Installed resource version: 3.7.0. Adapter schema
version: 3. This inventories authored content and parser boundaries; it does
not certify every gameplay scene or capture presentation.

Runtime update, 2026-10-31: the adapter now uses the shared owned managed Unreal
helper, preserving this audit's authored text/voice joins and patch priority.
All five study-locale production indexes passed against installed files;
English/Mandarin originals decoded, while Japanese/Korean packs remain absent.
See [runtime evidence and platform limits](../wuthering-runtime.md). The earlier
FModelCLI observations below remain the historical format evidence.

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
| Pre-rendered movie captions | `db_cgVedio` contains 1,313 `videocaption` rows, 342 video definitions and 171 video-sound rows. Caption text keys are now indexed as cinematic. | Publisher Setup clips both C0004 mixed performances in all four dubs. Other movie bindings and locale-specific timings remain incomplete. `IsPlaySubtitleVoice=false` does not establish silence. |
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
