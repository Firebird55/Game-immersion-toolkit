# Portal language and dialogue audit

Reviewed 2026-10-28. Game ID `portal`; Steam application `400`; Windows process
`hl2.exe`, disambiguated by the installed `portal/gameinfo.txt` and Portal VPK.
This is partial native dialogue coverage, with unresolved and absent recordings
reported separately from confirmed text-only material.

## Official languages and installation

[Valve's Steam language matrix](https://store.steampowered.com/app/400/Portal/),
checked on the review date, lists six full-audio languages and 27 interface and
subtitle languages. Traditional Chinese is explicitly a full-audio locale;
Simplified Chinese is text-only in that matrix. The reader preserves both
regional text identities. Locale filenames agree with the installed resources
and [Steam's language identifiers](https://partner.steamgames.com/doc/store/localization/languages).

| Study/audio locale | Source identifier | Official interface/subtitles/audio | Native verification |
| --- | --- | --- | --- |
| English `en` | `english` | Yes / yes / yes | Text, bindings and representative original audio decoded |
| French `fr` | `french` | Yes / yes / yes | Text read; absent voice-pack schema tested synthetically |
| German `de` | `german` | Yes / yes / yes | Text read; absent voice-pack schema tested synthetically |
| Russian `ru` | `russian` | Yes / yes / yes | Text read; absent voice-pack schema tested synthetically |
| Spanish (Spain) `es-ES` | `spanish` | Yes / yes / yes | Text read; absent voice-pack schema tested synthetically |
| Traditional Chinese `zh-Hant` | `tchinese` | Yes / yes / yes | Text read; absent voice-pack schema tested synthetically |

The other official interface/subtitle locales are Danish `da`, Dutch `nl`,
Finnish `fi`, Italian `it`, Japanese `ja`, Norwegian `no`, Polish `pl`, Portuguese
(Portugal) `pt-PT`, Simplified Chinese `zh-Hans`, Swedish `sv`, Korean `ko`,
Bulgarian `bg`, Czech `cs`, Greek `el`, Hungarian `hu`, Portuguese (Brazil)
`pt-BR`, Romanian `ro`, Spanish (Latin America) `es-419`, Thai `th`, Turkish `tr`
and Ukrainian `uk`. All are implemented as target translations. The native
Korean filename is `koreana`, while its resource header says `korean`; this is an
evidenced same-language alias. English reference rows embedded in translated
text files are never substituted for missing translations. Thai's installed
caption table has 449 tokens; the English baseline has 506, so table availability
does not imply every line has a translation.

All six audio locales remain choices regardless of installed packs. Select the
language in Steam Properties → Language, wait for its download to finish, then
Prepare again. Verify files to repair incomplete downloads. The installed
`gameinfo.txt` explicitly mounts `portal_sound_vo_english.vpk` and documents
replacement of `_english` with the selected language before the English mount.
This establishes `portal_sound_vo_<language>_dir.vpk` and its numbered chunks as
the supported absent-pack schema; it is not inferred from a matching filename
stem in another language.

The shared `portal_pak` contains English recordings. They are accepted only for
English with a completed, matching Steam `MountedConfig` language; requested
`UserConfig` changes alone do not establish a completed pack. A non-English
request uses only its explicitly named voice archive. It cannot fall back to
shared English files, commentary, song or another locale. A moved installation
without a verified language manifest needs Steam file verification for shared
English voices. The reader does not change Steam settings or install packs.

## Authored formats and original voice bindings

The reader parses VPK directories and numbered chunks in place, validates
member boundaries and CRC32, and restricts mounts to official game resources.
No external extractor is downloaded. Sound-event manifests and ordered
KeyValues retain repeated `wave` options; direct events resolve to one authored
WAV/MP3 path. Randomized events with distinct recordings remain unavailable
because their generic caption does not identify the actual selected recording.

Named caption tokens come from `closecaption_<language>.txt`; the displayed
text comes from matching VCCD entries in the compiled `.dat` resource. This
follows [Steam's compiled-caption instructions](https://help.steampowered.com/en/faqs/view/73F2-8EEA-1113-69B2)
and the lowercase-token CRC32/block layout in
[Valve's caption compiler header](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/captioncompiler.h).
Thus a stale text-file translation does not override the compiled game text.

VSIF v2 scene images, raw and Valve-LZMA-compressed binary VCD v4, are parsed
using the layouts documented in
[SceneImageFile.h](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/scenefilecache/SceneImageFile.h),
[choreoscene.cpp](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/choreoscene.cpp),
[choreoevent.cpp](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/choreoevent.cpp)
and [choreochannel.cpp](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/choreochannel.cpp).
The independently written reader retains active channel grouping, caption
overrides, ordered sound events and relative start offsets. Disabled,
relative-tag and conflicting performances are never guessed. Synthetic tests
verify that composite recordings retain authored silence between parts.
Direct sound events take precedence over incidental repeated scene playback;
no native Portal caption required the synthetic composite path in this audit.

Commentary tokens contain exact dry-mix audio filenames, including `.wav`.
[Valve's commentary implementation](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/client/c_point_commentary_node.cpp)
passes the same filename to sound playback and direct caption display. The
reader strips only documented sound-control prefixes and validates the path;
it never searches for similarly named recordings. Extraction re-reads the
authored binding, verifies its locale, archive and ordered parts, then checks
the VPK member CRC. PCM WAVs remain original PCM; the existing installed media
decoder handles original MP3 and timed compositions.

## Native inventory and presentation coverage

The installed Portal archive has 3,524 members, including 344 GLaDOS-directory
WAVs, 64 turret-directory WAVs and 69 commentary WAVs. The scene image contains
1,970 scenes, including inherited Source content; counts are resource inventory,
not a count of unique story scenes. All 1,734 manifest sound events were read
with no missing manifest files. The English index contains:

| Presentation | Indexed records | Verified original-audio binding | Unavailable | Confirmed unvoiced |
| --- | ---: | ---: | ---: | ---: |
| GLaDOS, cores, PA/story/escape caption family | 335 | 309 | 26 | 0 |
| Turret ambient caption family | 11 | 1 | 10 | 0 |
| Developer commentary | 69 | 69 | 0 | 0 |
| End-credit song, separate localized lyric pages | 88 | 88 | 0 | 0 |
| English terminal/report headings in credits | 10 | 0 | 0 | 10 |
| Total | 513 | 467 | 36 | 10 |

The 36 unavailable entries comprise 20 unresolved bindings (including ten
randomized turret captions) and 16 authored bonus recordings not present in the
installed archive. None is labeled unvoiced. Ninety SFX/nonverbal captions,
including explicit `<sfx>` records and bracketed/growling vocalizations, are
excluded from language dialogue. The inventory also counts 115 voice-directory
paths outside resolved language-caption bindings; this includes excluded
nonverbal assets and does not claim 115 additional subtitled conversations.

`scripts/credits.txt` separates literal report/letter headings from localized
lyric token references. The ten literal English headings are text-only readable
content, available with the unvoiced capture toggle. They are not relabeled as
other languages when the interface changes. The song resolves through the
authored `Portal.song_credits` event. Its 88 localized displayed fragments are
separate captions with their own translations, so the current lyric does not
reveal the rest of the song. Playback is labelled as the complete original
English recording; its encoding is reused across captions. Typewriter and
credit display timings do not establish exact sung-line cut points. Other
study locales retain translated lyric text with unavailable audio rather than
mislabeling the English song as a local dub.

| Other presentation | Evidence and boundary |
| --- | --- |
| Ordinary conversations and choices | Portal's native story captions and sound events are covered; no branching conversation-choice table was found. Generic menu, achievement and tutorial UI is not imported as dialogue. |
| Cinematics | In-engine scene speech uses the same sound events and captions. Native scene parsing covers those bindings, but does not prove visibility or reachability of every retained resource. |
| Radio and environmental broadcasts | Authored verbal captions can resolve through exact events. Instrumental radio loops, signals and speech without authored visible text are not invented as dialogue. |
| Wall writing, graffiti, chamber signs and readables | Relevant materials/models are present; writing baked into textures has no localized text-token binding here. It remains unsupported, not confirmed unvoiced OCR text. |
| Terminal and ending report | The credit report's literal headings and translated lyric pages are handled as above. No separate interactive text-terminal database was established. |
| Movies, comics and logs | The installed shared media folder contains the Valve startup BIK; this movie format is outside the native caption/event reader. No separate comic or collectible audio-log text schema was established; embedded movie speech is not claimed. |

## Capture and verification

Enable captions/subtitles in Portal's Audio options. Gameplay captions occupy
the lower HUD; commentary uses a distinct larger caption panel; the ending uses
terminal-like text across the screen. Use full-frame capture, or independent
calibrated regions for all three. A bottom-only crop cannot cover the report
headings and credit lyric pages. Repeated short phrases, partial commentary
paragraphs and individual short lyric fragments can remain OCR-ambiguous.

Read-only native checks loaded all 27 text locales, indexed English in about
two seconds with all translations, and decoded representative original English
story WAV, commentary WAV and credit MP3. The five other voice packs were not
installed; their playback has not been natively verified. Their directory
schema, missing-pack behavior and language isolation are tested with synthetic
VPKs. A French native index correctly retained text with zero audio bindings.

Focused synthetic tests cover all six audio identifiers, compiled captions,
Korean aliases, scene/LZMA bounds, channel grouping, missing and ambiguous
voices, unavailable dubbed credits, extraction-reference tampering, original
PCM decoding and composite timeline offsets. Native output, transcripts,
decoded audio and paths stay in ignored `output/checks/portal-native`; tracked
fixtures contain only authored synthetic data.

This archive audit does not validate live OCR, physical mobile capture,
Firefox/Chromium rendering, ultrawide, Windows zoom/DPI or actual capture bounds.
Those remain separate capture acceptance checks. Custom/mod mounts, loose audio
overrides, future formats, regional non-Steam packages and texture/movie-only
text need their own compatibility evidence.
