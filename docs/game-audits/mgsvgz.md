# METAL GEAR SOLID V: GROUND ZEROES

Audit date: 2026-10-28. Steam app **311340**, game ID `mgsvgz`, executable
`MgsGroundZeroes.exe`. The adapter reads the user's installed files without
changing them or executing their Lua scripts.

## Official languages and edition selection

| Locale | Official voice | Official interface/subtitles | Implementation and verification |
| --- | --- | --- | --- |
| English (`en`) | Yes | Yes | Installed original English edition indexed; representative field dialogue, radio, tape and cinematic audio decoded and converted to MP3. |
| Japanese (`ja`) | Yes | Yes | Implemented from `JpnVoice/JpnText`, localized `#jpn` cinematic events, shared native formats and synthetic original-media tests. Japanese text was inspected in the English edition; the Japanese voice edition was absent and has no native playback claim. |
| French (`fr`), Italian (`it`), German (`de`) | No | Yes | Original installed text available as translation targets. |
| Latin American Spanish (`es-419`) | No | Yes | Original `SpaText` target; regional label comes from Steam. |
| Brazilian Portuguese (`pt-BR`) | No | Yes | Original UTF-8 `PorText` target; regional label comes from Steam. |
| Russian (`ru`) | No | Yes | Original ISO-8859-5 `RusText` subtitles; not a complete Russian dub. |

The current [official Steam language matrix](https://store.steampowered.com/app/311340/METAL_GEAR_SOLID_V_GROUND_ZEROES/)
lists these eight text languages and two audio languages. Sources were checked
on the audit date. No additional complete regional PC dub was established.
Arabic placeholder resource paths in this installation do not establish an
official PC Arabic localization.

Select English or Japanese in Steam Properties → Language, finish the edition
download, then prepare again. The exact edition marker is the
`EngVoice/EngText` or `JpnVoice/JpnText` `e20010_subtitles.fpk` path hash.
Japanese text inside the English edition does not pass the Japanese voice check.
Missing Japanese audio remains an actionable missing-pack state with Japanese
still offered; conflicting edition markers fail closed.

The historic KONAMI PC page is no longer retrievable at its original address.
A [contemporaneous Steam discussion quoting that publisher page](https://steamcommunity.com/app/311340/discussions/0/619574421206844206/)
records separate English/Japanese downloads and English/Japanese subtitles for
the Japanese edition. This is historical secondary evidence, not a successfully
retrieved current publisher page. The adapter reads whichever official target
tables actually exist and reports absent targets; it never substitutes English
audio for Japanese. Native `PreinstallTape.lua` additionally declares five
`tp_arch_cd_01_*` archive tracks with positive Japanese duration and zero English
duration. Their exact path/subtitle binding schema is implemented and tested
synthetically without claiming playback from the absent Japanese edition.

## Native formats and exact bindings

- GZ's `data_01.g0s` and `data_02.g0s` use the GZS footer, 16-byte directory
  records, absolute-position XOR layer and optional encrypted payload wrapper.
  Archive identity uses GZ's extension codes and StrCode48 hash. This is not
  TPP's SQAR archive. `data_00.g0s` is an ASF movie and is excluded from archive
  parsing. FPK platform markers `ste` and `win` are supported; unknown platforms
  and out-of-bounds entries are rejected.
- Native legacy SUBP (`01 4c`) records retain their authored IDs and pages.
  Verified language paths select UTF-8, Latin-1 or ISO-8859-5. GZ LANG v2
  contains explicit key strings. Every distinct source variant is retained;
  conflicting subtitle IDs receive no guessed audio, and conflicting target
  translations are omitted.
- SBP enumeration covers BNK embedded media and STP v0/v1 streamed media.
  A Wwise RIFF `adtl/labl` string joins by StrCode48 to a SAB `SAL3` relation;
  its typed `.st` subtitle label joins by StrCode32 to SUBP. All three identities
  are revalidated on extraction. An audio label alone is insufficient. Prefetch
  fragments and non-RIFF entries are inventoried but never decoded as complete
  recordings. Standalone labeled media requires the same SAB relation.
- RDF v1 radio group conditions identify radio records through exact FNV1
  condition IDs. Radio classification does not manufacture missing audio.
- Cassette performances require the exact original archive path and subtitle
  ID. Known names come from the native preinstalled-track declarations. Music
  without a matching subtitle is not treated as dialogue. Thirty-nine standalone
  tracks bind in this English build; three additional subtitle performances use
  the regular SAB route.
- Cinematic bindings require `demoStreamPath` and `subtitleBinaryFile` from the
  same typed FOX2 entity. Local strings must reproduce their hashes. Structured
  localized SANI events supply `msgId` and authored frame order. FSM `SND`
  packets supply the original scene mix. Each authored subtitle ID remains a
  separate capture row with translations aligned by that ID, so matching an
  early caption does not reveal later captions. Playback uses the **complete
  original scene**, including music/effects; `playback_scope=full_track` and
  `cinematic_full_track` identify this explicitly. No per-line timing cuts are
  inferred from text length or frame order. Cassette tracks likewise expose
  `cassette_tape_full_track` when they represent a complete track.

Primary format references are
[GzsTool v0.2](https://github.com/Atvaark/GzsTool/tree/82f08c6f7ec5bc95046490797b53d837f6e05944),
[FoxEngine.TranslationTool](https://github.com/Atvaark/FoxEngine.TranslationTool/tree/7ba31f92c9d3f7d309c9caaa01d2ed6da386a57b),
[legacy CityHash](https://github.com/Atvaark/CityHash),
[StpTool](https://github.com/kapuragu/StpTool/tree/f7438b5d1153c1ae71f4a7a584b12d33f8aa2778),
[RdfTool](https://github.com/kapuragu/RdfTool/tree/aa8d89718143d212eda1fc58478eb82be1d7725c),
[FoxTool](https://github.com/Atvaark/FoxTool/tree/be69b04acfaa26725864de1908e2059e7b923676),
and [FsmTool](https://github.com/BobDoleOwndU/FsmTool/tree/a3e9ec0fd6c4c043a56a38e82d6da9754c0ed6b2).
GZ-specific differences were checked against installed files. No native game
assets or third-party tool binaries are redistributed.

## Dialogue presentations, unvoiced evidence and capture regions

KONAMI's [title-menu manual](https://www.konami.com/mg/mgs5/gz/webmanual/ps4/en/p0020.html)
explicitly describes BACKSTORY as reading and CASSETTE TAPES as information
retrieval. Its [radio manual](https://www.konami.com/mg/mgs5/gz/webmanual/ps4/en/p0100.html)
documents automatic incoming speech, player-initiated hints and binocular intel
calls. Its [basic-gameplay manual](https://www.konami.com/mg/mgs5/gz/webmanual/ps4/en/p0030.html)
describes cutscenes. These surviving official pages describe the PS4 presentation;
they do not validate Windows controls or pixel coordinates. Installed PC typed
resources independently establish the following routes.

| Presentation | Native evidence and implemented behavior | Screen-region evidence and remaining limits |
| --- | --- | --- |
| Mission dialogue, orders, ambient speech and barks | Common/mission SUBP plus exact SAB/WEM relations; every complete bank is enumerated. Shared-package records retain a broad category where their precise gameplay route is not established. | Caption presentation can overlap radio/field dialogue. Use full-frame matching or an independently calibrated subtitle region. No physical Windows layout acceptance is claimed. |
| Incoming/outgoing radio and binocular intel | RDF conditions identify 1,052 bound radio records. | The manual's top-left binocular icon is a call prompt, not proof of subtitle coordinates. Caption bounds need separate calibration. |
| Enemy conversations and carried-hostage speech | Native `cpradio_seq_v1.1` JSON sequences establish these modes; constituent SAB-bound recordings are supported. Event aliases do not directly equal subtitle IDs, so complete sequence-to-performance attribution remains unresolved. | Gameplay captions; moving context and overlapping UI require full-frame or calibrated regions. |
| Interrogations | Typed `interrogationResultTable` provides 211 uses of 58 caption IDs and separate generic voice-event names. All 58 captions remain unavailable because selecting the actual original performance requires runtime actor and switch state. | Narrative result captions are retained; they are neither confirmed silent nor assigned a guessed generic recording. |
| Cassette recordings, briefing/history tapes | Exact named track plus SUBP; complete track and all its authored pages retained. Five additional Japanese-only archive-CD definitions are supported by schema, with no absent-pack native claim. | Tape/menu presentation differs from ordinary HUD captions. Calibrate it independently or use full-frame matching. |
| Opening, mission and ending cinematics | Forty FSM streams bind through typed FOX2/SANI metadata, producing 266 separate caption rows with full-scene audio. | Current caption only is shown; playback is labeled full track. Unsupported scene variants and the separate ASF movie remain explicit gaps. |
| BACKSTORY prose | **11 confirmed unvoiced rows.** Typed `LangData.langFile` binds `gz_backstory.lng`; `TppUICommonBootData` binds the paused `title_prestory.uigb`. Its layout points to the paged `sys_prestory` reader. Only the authored `backstory_info_00_*` prose fields qualify. | A paged reading panel, not a bottom-only subtitle strip. The shared unvoiced capture toggle and full-frame/independent panel region apply. Headings remain unknown. |
| Deja Vu quiz answers | **100 confirmed unvoiced rows.** The typed `mgs_quiz` UI and 20 authored `SetupMgsQuizItemTable` declarations distinguish five selectable `choice_N_M` labels per item from separate question/correct radio events. | Quiz choice panel/list fields require their own region or full-frame matching. Question prompts and other quiz labels remain unknown. |
| Ending chronology, credits and other localization-only text | All distinct LANG variants retained. No proven sound-free route or exact original audio binding for these fields; **unknown**, not silently enabled. | Full-screen/end-roll and UI presentations differ from normal subtitles. Parsed resources do not establish native capture geometry. |

The confirmed unvoiced decisions rely on typed presentation routes, authored
field roles and the reading/choice semantics above, never merely on a failed
audio lookup. Other text remains unknown or unavailable as appropriate. No
additional comic/document presentation was established by this audit.

The interrogation limitation was investigated beyond filename matching. Native
Wwise v88 HIRC contains `DD_vox_ene` dialogue events (type 15). Their decision
trees select an actor and `ENQ_gonyo`/`ENQ_gonyo2`, then a type-6 switch container.
The inspected containers include an empty switch branch, a default original
sound and a different/cross-bank branch. Caption text does not encode that
runtime selection. The trace was independently inspected with
[wwiser's documented bank/tree parser](https://github.com/bnnm/wwiser/blob/master/doc/WWISER.md).
Neither one arbitrarily selected mumble nor a silent classification would
identify the actual performance.

Full-frame matching is available for stable exact captions and panel prose;
short/ambiguous text and mixed voiced/unvoiced identities remain subject to the
shared capture safeguards. Physical OCR, window bounds, DPI, zoom and panel
placement have **not** been validated by this file-format audit. A bottom-only
crop cannot establish complete presentation coverage.

## Installed inventory and verification

The read-only audit used the English Steam build **558266**. All eight official
text targets were read. A final index plus inventory probe took about **9 seconds**
with warm filesystem caches; this is not a setup-time guarantee.

| Installed inventory | Count |
| --- | ---: |
| Selected archive entries | 16,222 |
| SUBP / LANG packages inspected, including duplicate FPK residents | 216 / 256 |
| SBP / BNK / STP / SAB packages | 56 / 56 / 22 / 12 |
| Streamed / embedded / standalone media entries | 4,447 / 2,354 / 50 |
| SAB subtitle relations inspected | 3,936 |
| RDF files / radio groups | 26 / 2,014 |
| Unique source subtitle IDs | 3,463 |
| Total retained text/performance records | 8,728 |
| Voiced / unavailable / unknown / confirmed unvoiced records | 3,784 / 200 / 4,633 / 111 |
| Source IDs with conflicting text | 0 |
| Conflicting locale/ID pairs across target text, omitted as translations | 302 |
| Bound standalone cassette tracks | 39 |
| Typed cinematic relations / localized event containers inspected | 90 / 38 |
| Bound cinematic streams / caption rows | 40 / 266 |
| FSM streams with / without embedded original audio | 53 / 29 |

These are resource/performance counts, not a claim that every utterance has an
official caption. Duplicate bank residents and alternate performances can create
multiple voice rows for one text ID. Of the 53 audio-containing FSM streams,
13 lack a resolved exact subtitle route: `p11_010150_000`, `p11_010155_000`,
`p11_010170_000`, `p11_020001_000`, `p11_020002_000`, `p11_020003_000`,
`p12_040020_000`, `p12_040030_000`, `p12_050020_010`, `p12_050020_020`,
`p12_050020_040`, `p12_050020_055`, and `p12_050020_055_gns`. These may include
scene pieces or effects; they are not all asserted to contain subtitled speech.
The separate `data_00.g0s` ASF movie is unsupported. Also inventoried are 1,750
media entries without labels, 1,158 label occurrences without a unique SAB
relation, 457 relations without source subtitles, five prefetch fragments and
three non-RIFF media entries. Non-subtitled vocalizations and unresolved aliases
are not converted into invented dialogue records.

Four representative original performances passed exact archive extraction,
vgmstream decoding, nonzero PCM checks and the production MP3 conversion path:

| Mode | Native audio | Duration |
| --- | --- | ---: |
| Field/bark/scripted dialogue | Mono, 48 kHz | 2.143 s |
| Radio | Mono, 28 kHz | 1.877 s |
| Cassette | Mono, 48 kHz | 118.361 s |
| Cinematic | Six channels, 48 kHz | 297.667 s |

The private playback probe temporarily routed this adapter through the service
lookup while registry integration was in progress; extraction, decoding and MP3
conversion were real. It is not evidence of physical in-game capture or browser
playback. Generated recordings, decoded files and native dumps stay outside the
public repository. Compact local reports are ignored under
`output/checks/mgsvgz-native`.

The focused synthetic suite covers both voice editions, all eight text
encodings, cipher random access, archive bounds, exact SAB joins, standalone
media, Japanese-only tapes, typed cinematic aliases/events and separate current
captions, unvoiced evidence gates, unresolved interrogations, conflicting text,
changed-file rejection and extraction tampering. The final combined GZ/shared
TPP run passed **52 tests**. Fixtures contain invented text and audio headers,
not native assets. Japanese playback, unresolved runtime state routes and
physical Windows capture remain explicit validation limits.
