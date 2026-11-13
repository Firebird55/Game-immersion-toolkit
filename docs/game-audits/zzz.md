# Zenless Zone Zero dialogue audit

## November 13, 2026 · Launcher dialogue in Windows Setup

Leaving the game folder empty prepares the selected study locale from the Global
launcher release. The worker reads the Perform table, follows the resource
catalogue and requests the scene byte ranges. The same release provides the
selected language and translation tables, the message and reply bindings,
ongoing performance variants, gameplay tips and original voice packages.
A fresh launcher check before publishing prevents mixing two releases.

In Global 3.3.0, 30,762 of 31,095 referenced dialogue paths matched the catalogue.
Both root-relative and fully qualified Perform paths are accepted. The latter
added 26 distinct Chat and Bubble assets and 292 typed scene records.
The selected scene bundles totalled 48,891,704 bytes before Sophon chunk
alignment. Setup retained conversations, narration, choices and ambient text.
The initial English study index with English and Simplified Chinese text produced
68,572 voiced, 132,908 authored unvoiced, 11,459 unavailable and 50,800 unknown
records including comics. Thirty-four English samples exported through the
desktop playback service and decoded to nonzero PCM, including phone, gameplay,
narration, early story and separate Belle and Wise performances. A caption shared between
a choice and spoken dialogue keeps its conflicting evidence.

The gameplay-tip table explicitly names GalGame recordings for five Virtual
Revenge tips and two Golden Week performances. The five Virtual Revenge tips
were previously unavailable. After accepting this source family, normal Setup
with an empty game-folder selection exported all seven English recordings.
The two Golden Week captions also appear in the scene catalogue. Each of the
seven named sources resolved uniquely and decoded to nonzero PCM in all four
publisher dubs. For example, Harumasa’s first cue (`Tips_72025056`) lasts
3.348 s in English, 5.216 s in Japanese, 2.567 s in Korean and 2.520 s in
Mandarin. This verification used the Global 3.3.0 launcher base.
[Publisher release manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)

The same Global release stores cinema dates under `VO_Cinema`, some MainCity
chat under `VO_Chat`, companion level voices under `VO_Accompany`, and
timeline dialogue under several recorded directory names. Setup now checks
these locations against each authored source and the selected dub's actual
Wwise file IDs. A second matching ID leaves the line unresolved. Actor
identifiers can start with a number, as in the Chapter 2 irate operator.
Repeated spellings of a name that differ only in case identify the same Wwise
path.

With the tip change above, the English index gained 1,821 voiced records in
the same selection: 1,441 ambient lines, 243 conversations, 129 gameplay tips
and eight narration lines. The resulting totals were 70,393 voiced, 132,908
authored unvoiced, 9,638 unavailable and 50,800 unknown. Nine newly mapped
sources were retrieved and decoded in all four publisher dubs. English Setup
also exported each of these nine, including Asha’s cinema date (5.551 s),
the irate operator (7.678 s), an Elpis fishing line (1.032 s) and Ju Fufu’s
companion line (3.325 s).
[Global 3.3.0 publisher manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)

Two Remielle gameplay tips name one take ending in `_F` and one ending in
`_M` under the same source name. The selected text names Belle or Wise.
These four additional English performances exported through Setup.
The two takes for `Tips_74580002` lasted 5.009 s and 5.274 s, and those for
`Tips_74580004` lasted 5.541 s and 5.552 s. These four bring the English
selection to 70,397 voiced and 9,634 unavailable records. Alternate takes
that only carry different numbers still need performer evidence.

The resource catalogue indexes the publisher's own
`assets/napresources/data/audio/voicedata.json`. The 388,096-byte bundle in
Global 3.3.0 contained 2,952 original voice directories and 85,839 numerical
source IDs in 1,302 directory groups. In each group the first number is the
32-bit FNV-1 of the lowercase directory, followed by the source-name IDs
and a zero terminator. Some groups name an actor directory directly; others
refer to a parent with several actor directories. Setup selects a recording
only when the complete path gives a unique 64-bit file ID in the requested
dub. The same reader found 2,889 directories, 84,259 source IDs and 1,283
groups in the 380,804-byte mainland 3.2.0 bundle. Neither location nor the
voice group memberships are pinned to these releases.

Comparing the updated English index with the first selection above, 6,341
previously unavailable performances now have audio: 5,593 ambient lines, 531
conversations, 198 gameplay tips and 19 narration lines. Fourteen cinema
entries named a breath or reaction under an on-screen description. Setup
keeps their sentence voice status unknown. This brought the totals to 74,913
voiced, 132,908 authored unvoiced, 5,104 unavailable and 50,814 unknown.
Seven newly resolved performances spanning the Forbidden Area, Severian,
Silver Soldier Anby, Cissia, Fairy and a timeline voice were retrieved and
decoded in all four dubs. The Forbidden Area line lasted 6.576 s in English,
7.467 s in Japanese, 5.550 s in Korean and 5.812 s in Mandarin. The
compiler-free Windows reader reproduced these English counts, exported the
seven English clips, and exposed no sentence audio for the cinema reaction.
[Global 3.3.0 publisher manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)

In 17 prologue captions the released scene spells one take twice, once as a
bare name and once with its actor directory. Both spellings independently
resolved to the same unique file within each of the four dubs. The normal
English Setup with no game folder gained all 17 performances, bringing its
totals to **74,930 voiced, 132,908 authored unvoiced, 5,087 unavailable and
50,814 unknown**. Setup leaves a caption unresolved when either spelling
is missing or the selected files disagree.

Four English publisher clips also matched the mixed audio in CGInferno's 1.0
prologue playthrough. The matches begin at about 34:12 (Billy, 3.488 s),
34:21 (Billy, 4.379 s), 34:26 (Billy, 7.797 s) and 35:02 (Anby, 5.649 s).
The four clips each exported through the normal English service. Gameplay
corroborates the English recordings; the other dubs were verified against the
publisher files. [Billy at 34:12](https://www.youtube.com/watch?v=k8HMd3Bea-o&t=2052s)
· [Billy at 34:21](https://www.youtube.com/watch?v=k8HMd3Bea-o&t=2061s)
· [Billy at 34:26](https://www.youtube.com/watch?v=k8HMd3Bea-o&t=2066s)
· [Anby at 35:02](https://www.youtube.com/watch?v=k8HMd3Bea-o&t=2102s)

The publisher gameplay-tip reader also checks the reaction, sound-event vector
and indirect reference fields before certifying silence. Across 17,528 release
rows, the reaction column had 268 populated entries and 16 rows referred to an
additional sound event. With English and Simplified Chinese text, 6,862 tips
had proven silent instructions and 780 retained unknown voice status.

The subtitle configuration supplied 248 Clue intervals in each of the four
dubs. Its source, dub, text key and millisecond start and end refer to the same
released recording. The normal voice decoder trims the selected interval and
checks that it fits the actual file. The first Limbo recording's opening
caption exported as 2.066 s in English and 3.429 s in Japanese.

All 101 motion-comic paths in the released Perform table matched. The catalog
identified 114,239 bytes of root manifests. Their 1,100 directly named bundles
added 1,833,974 bytes before launcher chunk alignment. A separate scan of all
1,153,992,096 bytes of transitive dependencies recovered the same bindings.
The voice dictionaries linked 1,929 distinct panel IDs to
recordings, including separate Belle and Wise performances where authored.
For the English study selection above, 2,025 panel performances had an original
recording in the English voice pack, two had an unavailable recording and 656
had unknown voice status. A single panel exported as 4.992 s, and another
panel's separate Wise and Belle recordings exported as 2.027 and 2.310 s.
Unknown panels remain eligible for text lookup.

Additional filmed scenes and the 333 unresolved Perform paths remain under
investigation. The launcher base omits some later Japanese text and
same-version Global changes still need independent discovery.

The November 6 mainland production snapshot (D20245314) retains all 333
references in 313 distinct Perform entries. Twenty-eight of these entries
also name a different performer path that the Global launcher catalogue does
resolve. Only that named path supplies records. Both official mainland 3.2
catalogues (524,742 asset IDs each) and the 3.3 mainland base catalogue
(565,107 asset IDs) lack the 333 exact IDs. The cause of their absence and
their use in actual gameplay remain unconfirmed. The public revision timeline
identifies D20245314 but does not give a Global PC download manifest.
[November 6 mainland Perform snapshot](https://git.mero.moe/dimbreath/ZenlessData/src/commit/ab85fff9659168f981904259ebb9ec2c51fb5fe4/FileCfg/PerformTemplateTb.json)
· [Public revision history](https://zzz.gachabase.net/timeline/release)

The same source reader also processed the archived mainland 3.2.0 launcher
build (RXWlt1ru1jf6). It resolved 30,176 of 30,503 referenced dialogue paths
and all 99 motion-comic paths. The publisher ranges produced 228,625 scene
records, 1,929 distinct comic bindings, nine recorded messages, 14,783
ongoing records, 16,847 tip records and 248 English clue intervals. The 3.2
comic manifests and their directly named dependencies occupied 1,895,469
bytes before launcher chunk alignment. An original English panel (4.992 s),
phone message (6.483 s) and complete first Limbo recording (90.647 s) were
retrieved from the older English Wwise pack and decoded to nonzero PCM.
This checks format continuity across two releases and regions. The Windows Setup region remains Global.
[Archived mainland launcher listing](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/nap/3.2.0.json)

## November 9, 2026 · Dialogue from one Global launcher release

The publisher's 3.3.0 base (revision 19316624) contains the Perform scene
references, their resource catalog, subtitle tables and original Wwise packages.
The Perform table named 31,069 dialogue scene paths. The resource catalog
resolved 30,736 paths across 18 blocks. The 48,849,768 bytes of selected
scene bundles contained 221,699 dialogue records, including 59,316 with an
authored voice reference. Of the 221,561 distinct subtitle IDs, 217,629 had
both English and Simplified Chinese, and 213,899 had text in all 13 locales.
These figures cover conversations, choices, ambient lines and narration
in the resolved dialogue scenes. The count of voice references precedes audio
package matching. [Publisher release manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)

The released scenes contained 1,619 chapter 240 records. In package 10126,
49 subtitle IDs resolved to an exact original file in every dub. None of those
49 had text in all 13 base locales. Three of the 49 were downloaded and decoded
in all four languages. Their Japanese recordings were already in the release,
while their Japanese subtitles first appeared in the inspected later override.
Fetching that Global hotfix on a fresh device remains open.
[Publisher chapter announcement](https://zenless.hoyoverse.com/m/en-us/news/166963)

From a source checkout, the following command follows the released Global
launcher branch, reads the checked scene and translation tables, and searches
every released package for the requested dub. With the checkout's Node
dependencies installed, it fetches the pinned upstream scene reader, checks
its SHA-256 and compiles it in the private working directory. An existing
compiled toolkit reader can also be selected with `--reader`.
The result contains the available original translations, a WEM for each requested
dub and a receipt with build, package, file ID and SHA-256. Repeating `--dub`
selects multiple recordings. Omitting it requests all four. Both Chinese scripts
use the Mandarin recording.

```text
python scripts/probe-zzz-publisher.py Galgame_Chapter0_11_01_01 --cache private-cache --output new-private-folder
```

This query returned Nicole's authored source, all 13 translations, and four
complete recordings that decoded to nonzero PCM. Their durations were 4.700 s
in English, 6.556 s in Japanese, 4.700 s in Korean and 5.195 s in Mandarin.
The same command for `Main_GalGame_Chapter240_124000005_001` returned four
original recordings and 12 translated strings from the same build.

The publisher command also reads the original Message and OngoingTips
FlatBuffers directly. For these two presentations it downloads the design
tables and selected voice package ranges. Scene blocks are unnecessary.
Use `--kind message` for a phone recording. Use `--kind ongoing` and
`--protagonist belle` or `--protagonist wise` for a conditional performance.
The optional `--channel zzz-cn` selects the independent mainland launcher;
the default remains Global.

```text
python scripts/probe-zzz-publisher.py Message_100403 --kind message --cache private-cache --output message
python scripts/probe-zzz-publisher.py Main_OngoingLevel_Chapter180_111801006_01 --kind ongoing --protagonist wise --cache private-cache --output wise
```

The 3.3.0 message table named nine recorded message bodies. All nine resolved
in each dub, and all 36 original WEMs decoded with nonzero PCM. The example
message yielded 13 translations. Its English Global and mainland recordings were byte
identical. The ongoing sample yielded separate original recordings for Belle
and Wise in all four dubs. Their English recordings decoded to 5.345 and
5.731 seconds. The same command followed an archived mainland 3.2.0 launcher
announcement to the publisher and retrieved the English message and Wise
performances. That release stores the design index in the older supported
gzip resource catalog. Publisher scene receipts also classify unmatched reference
paths. On Global 3.3 the 333 absent paths comprised 144 Bubble, 21 BubbleStory,
142 Chat, three ChatPlus and 23 GalGame paths. Whether these scenes run in a
different content layer remains open.

The command requires a unique authored scene source and a unique matching file
in the selected dub. It supports direct source paths and the evidenced GalGame
and ongoing speaker directories. Additional conditional scene voices, comic panels and cinematic events
require their own bindings. The November 9 implementation of Windows Setup
read the Global launcher's message configuration and the selected base and
overwrite TextMaps. That implementation prepared only phone message bodies with a unique authored source and an exact
original recording in the selected language. Replies, other presentations, later
in-version Global overrides and independent phone preparation remain outside this route.

The Windows language worker prepared the Global 3.3.0 base from an empty
game-data cache without a game folder or any reads from an installation. The smoke test used the rebuilt
production reader, its hash-verified app-local Node executable and source-built
ooz decoder. The helper ran with an empty executable search path. All five
study selections yielded nine unique recorded bodies and 15 display rows because
some translations distinguish the two protagonists. Every display row had all
13 text locales, an unambiguous source and a recording in the selected dub.

The desktop playback service produced 75 MP3s, one for each display row in
each selection. All decoded to nonzero PCM. The 36 distinct source recordings
span four dubs. The two Chinese script selections share Mandarin. Measured
durations were 3.805–15.536 seconds in English, 3.922–22.840 in Japanese,
3.398–16.050 in Korean and 3.164–15.957 in Mandarin. A separate two-release
fixture changed the package contents under the same filename and verified
both the refreshed recording and playback from the earlier snapshot.

## November 8, 2026 · Publisher sources and subtitle variants

The released Global Windows 3.3.0 branch serves the game TextMaps directly.
Follow the HoYoPlay branch into its Sophon game manifest and read
`StreamingAssets/data_version`. For this release, the 25 listed
`Blocks/Data` files contained the 13 base locale tables. The check downloaded
those files from the publisher and verified the manifest, chunks and assembled
files against their MD5s. In each Unity bundle, the TextAsset name equals the
decimal xxHash64 of the lowercase table name. The FlatBuffer stores the authored
key and text. This also located the source objects for Perform, OngoingTips,
Tips, Message and Subtitle configuration. Their object names alone do not
decode the bindings. [HoYoPlay release branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=U5hbdsT9W7)
· [Audited publisher manifest](https://autopatchos.zenlesszonezero.com/pclauncher/manifests/cxi9qfgtcu0w/20260928/3.3.0/KjHGqRMV1ck0/manifest_023518ab349f7365_9e52d5132ba03a37ec0161c5cedbaafc)
· [TextMap schema reference](https://github.com/Hiro420/ZZZ_TextMap/tree/499541c07d73216b4a3cd3ae1720a81597c17e6d/ZZZ_TextMap/Defs)

The base contained 439,660 English keys and 450,561 Simplified Chinese keys.
Of 224,387 distinct subtitle IDs from the audited scene, comic and cinematic
readers, 220,442 had both languages and 216,719 had text in all 13 locales.
The denominator includes choices and silent lines. It excludes presentations
outside those readers. The three checked chapter 240 lines were absent from
the older English 3.2 chapter inventory. For each, the game-authored scene
binding identified a complete WEM fetched from the publisher in Mandarin,
English, Japanese and Korean. All three had translations in 12 base locales.
The Japanese text for all three was in the installed 3.3 override table.
Across this chapter's GalGame IDs, the bilingual count rose from 1,744 in
the launcher base to 1,846 after applying the installed design update.
[Publisher chapter announcement](https://zenless.hoyoverse.com/m/en-us/news/166963)
· [3.2 text comparison](https://github.com/malu-no996/ZenlessData/tree/1277ebca4b8a7a6c3bcbaac6d5708dc9f4a55f23/TextMap)

For 1,509 distinct voiced GalGame references in the chapter 240 scene extraction,
the check computed exact external-media identities for the tested source paths.
Across all 313 publisher base voice indexes, 1,476 matched in Mandarin, 765 in
English, 195 in Japanese and 1,474 in Korean. Only 49 matched in all four base
indexes. Three of those were downloaded in full in every dub. The later
installed indexes matched 1,477 per installed language (Mandarin, English and
Japanese). These are directory joins. An unmatched path can reflect another
binding or a subsequent update. The audit did not have the later Korean pack.

The inspected launcher base had data revision `19316624`. The installed
Global revision `19916124` contained 13 base and 13 overwrite tables. An
older Global 3.2 hotfix manifest and its block were independently retrieved
from the publisher. Current Global 3.3 hotfix discovery from an empty device
remains open. The installed reader supplies additional cinematic voice mappings. [Historical publisher design manifest](https://autopatchos.zenlesszonezero.com/design_data/3.2_live/output_19159270_4529024a46/client/StandaloneWindows64/oversea/data_version)
· [Public release revision history](https://zzz.gachabase.net/changelog/release)

On 2026-11-13 the public Global HoYoPlay branch returned 3.3.0. The separate
package-list response still listed 3.2.0 as its main package and 3.3.0 as
its pre-download. Neither response supplied the Global player’s in-version
design or voice manifest. The Steam public build (25596035) had an October
20 depot update. The November Steam app metadata change did not change that
build. These distributor results cannot establish the current in-version
revision or its download directory. [Publisher branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=U5hbdsT9W7)
· [Publisher package list](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGamePackages?launcher_id=VYTpXlbWo8&language=en-us)
· [Public Steam app metadata mirror](https://api.steamcmd.net/v1/info/4162040)
· [Publisher Steam announcements](https://steamcommunity.com/app/4162040/announcements/)

The 3.3 English base contains 2,355 gender-tagged entries with text outside
the tags and 200 entries with repeated male tags. The corresponding Simplified
Chinese counts are 2,627 and 198. The prepared and legacy readers now preserve
the surrounding words, resolve every inline group and align translations by
the authored M/F labels. Missing voice packs retain the two distinct performance
identities. Local design and silence manifest changes invalidate language
preparation even when audio stays identical. The legacy update status reports
an unavailable upstream and retains the last verified revision for retry.

Audit date: 2026-10-27. This is a format and coverage audit, not a claim that every
scene, language, or capture layout has passed native gameplay testing. Game
resources were read from the owner's installation. Extracted assets, dialogue,
audio, account details and installation paths stay in ignored local evidence.

Subtitle boundary review, 2026-10-31: story, comic, ongoing and cinematic readers
retain individual authored TextMap identities. The cinematic adapter joins each
`CS_` identity to its exact authored Wwise event; it does not concatenate a movie
or infer page timings from timeline position. Speaker/scene context joins OCR
rows visible in the same captured caption, not successive subtitle records.
A synthetic index-to-match regression verifies consecutive cinematic IDs preserve
their own source and translated text even when they reference the same recording.
This does not prove pagination inside an indivisible TextMap string: if a game
version dynamically subdivides such a string without an evidenced page schema,
that boundary remains unresolved. No sentence-length or punctuation split is
presented as game-authored pagination.

## Evidence and scope

The publisher explicitly describes cutscenes and motion comics as separate
production formats in its [cinematics-team ZTALK](https://www.youtube.com/watch?v=RC4XoA7dhf0).
The [3.1 update announcement](https://zenless.hoyoverse.com/en-us/news/165414)
separately lists story content, Trust Events and Quality Time Events, and reports
fixes to missing voice lines during accelerated story playback. The current
[3.3 announcement](https://zenless.hoyoverse.com/m/en-us/news/166963) reports
continued changes to localized text and older English, Japanese and Korean story
and combat voice-overs. These are reasons to invalidate prepared data after
updates; patch notes do not document the binary asset schema.

Schema evidence comes from installed resource catalogs, exact referenced bundle
ranges and serialized story objects. TextMap and configuration metadata are
game-authored data obtained through a community-maintained mirror, not a
publisher-operated API. The audited fresh metadata revision was
`c7551c3040a69ffc28c6b13cb75ee1f95dc2f9d2`. Additional table discovery used a
separate cached 3.2 metadata snapshot, `b084f66` dated 2026-09-09; those obfuscated
field names must be revalidated against the current version before use.

The original prepared snapshot contained 71,449 Chinese entries and 69,861
verified original voices. A successful typed extraction found 221,705 references
across 29,365 story assets. Its 31,072 requested paths had 333 unresolved entries
in the installed catalog. These are extraction counts, before TextMap joining,
gender expansion, language selection and voice resolution; they are not counts
of playable, unique or currently accessible dialogue.

The final Chinese preparation with English translations completed successfully:
237,096 records, 71,628 original voices and 118,187 certified unvoiced records.
All 69,861 previously verified voiced rows remained present with the same file
identity and package binding; 1,767 additional original voices were resolved.
The worker validated every prepared row against the shared dialogue contract.

A subsequent bounded message/tip pass used the same current metadata revision
and the existing scene cache. Its complete preparation produced 265,241 records,
77,148 original voices and 135,479 certified unvoiced records. It added 28,145
entries, 5,520 verified voices and 17,292 silent records while retaining every
previous voice binding and silent classification unchanged. No cinematic rescan
was needed. The nine `VO_Message` entries all matched the installed Chinese pack.

## Inventory and implemented coverage

| Dialogue presentation | Authored evidence | Coverage and limits |
| --- | --- | --- |
| Normal and visual-novel conversations | `GalPlayStoryNode`, `GalPlaySubStoryNode`, `MainCityChatPlayStoryNode`; `dialogueKey`, `externalVoiceKey`/`voiceKey` | Typed reader supports voiced and explicitly silent records. `GalGame`, `Chat` and `ChatAudio` asset families are selected. |
| ChatPlus conversations | `PlayChatPlusStoryNode`; capitalized `DialogueKey` and `ExternalVoiceKey` | Supported independently of the older lowercase schema. Installed samples verified the difference. |
| Illustrated, no-avatar and group dialogue | `GalPlayPictureStoryNode`, `GalPlayNoAvatarStoryNode`, `GalPlayStoryMultiSpeakerNode` | Supported through the owning typed object's text and voice fields; the initial voice-regression comparison exposed these additional forms. |
| Narration and scene-transition text | `GalSubNarratorNode`, `GalSwitchSceneNode`, `GalWhiteSwitchSceneNode`, `SwitchSceneConfig` | Preserved as `narration`; empty authored voice fields establish silence, while missing fields remain unknown. |
| Conversations during gameplay | `MainCityChatInLevelPlayStoryNode` | Supported with the gameplay channel as well as dialogue capture. |
| Dialogue response choices | `TransitionDisplayItem`, `MainCityChatTransitionDisplayItem`; `textKey` | Preserved as `choice`. Voice status stays `unknown`: the absence of a voice property alone does not certify silence. |
| City, NPC, Trust and Quality Time bubbles | `GalBubbleStoryNode`; `Text`, `Voice`; `Bubble`, `BubbleStory`, `BubbleNpc` families | Empty/null authored voice is `unvoiced`. Nonempty values may be short reaction pools; those remain `unknown`, with no fabricated sentence audio. |
| Motion comics | Exact GUID-to-voice dictionaries; `Comic_` TextMap identities | Original voice mappings remain supported. Empty entries are certified silent only inside a complete, otherwise verified voice dictionary. All-empty generic dictionaries or unmatched TextMap IDs remain `unknown`. No such silent comic entry was observed in this installed dictionary extraction. |
| Cinematic timelines and cutscenes | Typed `WwiseAudioClip`, owning track and authored `CS_` subtitle/event relationship | Supported for the known clip layout, including the auxiliary empty string variant. Existing locale/event resolution remains required. Cinematic text with unresolved authored audio is `unavailable`, not silent. |
| Gameplay and ongoing tips | `OngoingTipsConfigTemplateTb` text IDs and explicit male/female source fields | Preserves existing original voices and now retains records with both authored voice fields empty. The current metadata contained 1,466 such rows before TextMap filtering. Other tips tables are not implied by this support. |
| NPC greetings and ambient combat reactions | Some are present in supported ongoing/bubble records; other source-only tables exist | Only authored text/source relationships are eligible. Audio-only barks cannot be reconstructed as official dialogue from filenames. |
| Knock Knock messages and reply choices | Separate `MessageConfigTemplateTb`; text, options, emoji and occasional `VO_Message` sources | Current schema imported through exact TextMap joins. Empty authored message source columns establish silence. A message recording never becomes its reply-choice audio; reply-only evidence remains unknown. Image paths and literal content are excluded. |
| Clue recordings with timed subtitles | `SubtitleConfigTemplateTb`, `Clue_` IDs, locale, source and start/end timestamps | Inventoried; the Global launcher adapter now validates per-dub intervals and extracts the corresponding sentence. |
| Other tips, TV/Hollow and event interfaces | `TipsConfigTemplateTb`, `HollowBottomMessageTemplateTb`, event-specific tables | Current `TipsConfigTemplateTb` is imported as `gameplay_tip`, including authored spoken guidance and silent instructions. Reaction pools never substitute for the main recording. Independent Hollow/event tables remain incomplete. |
| Journey UI, reading screens, messages, mail, summaries and tutorials | Separate UI/configuration references; `ChatJourney` sample invokes journey UI rather than containing dialogue text | No blanket TextMap import. UI labels, item descriptions and notification text must not become dialogue merely because OCR sees them. |
| Pre-rendered movies, baked text, songs and subtitles without a verified timeline event | Not established by the supported dictionary/timeline relationships | No completeness claim. Require a format-specific subtitle binding and timing/locale validation. |

The fresh typed extraction classified 98,759 conversation, 17,496 ambient and
2,356 narration references as explicitly silent. It retained 41,529 choice
references as unknown, 59,313 conversation/narration references with authored
voice sources, and 2,252 other references with unknown voice status. Reused lines
can have conflicting evidence; the prepared table does not promote such a
conflict to certified silence. Successful audio resolution always means `voiced`.

## Format handling and update behavior

The resource reader supports legacy gzip catalogs and the observed Unity v21
serialized `Res` catalog object with its asset, bundle, block and flat dependency
arrays. It follows authored dependencies and validates byte ranges. The new
story reader parses bounded Odin objects and their types and properties, including
empty strings and nulls. It does not pair adjacent strings or infer a voice from
matching filenames. The binary token definitions are documented by the
[Odin serializer project](https://github.com/TeamSirenix/odin-serializer/blob/master/OdinSerializer/Core/DataReaderWriters/Binary/BinaryEntryType.cs).

Installed blocks are opened read-only and only selected bundle ranges are read.
Preparation remains outside capture. Cache signatures include the installed
fingerprint, metadata and reader code; index reader revision 5 forces older
language snapshots to refresh. A malformed recognized Odin stream fails the
preparation instead of publishing its partial records. Every ongoing row is
checked against a supported schema, rather than trusting only the first row.
Known extraction failures retain the prior prepared index and return the
actionable ZZZ format/update error provided by the preparation layer.

Missing scene paths are reported as coverage notes, separately from preparation
failures. A follow-up compared all 31,072 authored dialogue paths with both
installed resource asset tables: the hotfix catalog has 570,614 asset identities
and the base catalog 565,107. None of the 333 hotfix-unmatched paths occurs in the
base table either. They cover 144 Bubble, 21 BubbleStory, 142 Chat, three ChatPlus
and 23 GalGame paths, referenced by 313 metadata rows. Case/prefix/extension
variants tested during diagnosis supplied no additional exact matches. No
filename similarity was promoted into a subtitle or voice binding. The reason
for each missing reference remains unestablished; it is not evidence that the
whole index failed or that the user's voice pack is absent.

That comparison exposed a separate catalog compatibility defect. Unity aligns
arrays after the packed nine-byte block records. The installed base catalog's
10,470 blocks require two padding bytes before its dependency array; the hotfix
catalog's 10,532 blocks happen to need none. The reader now validates and consumes
zero alignment padding before each array. Both complete native catalogs parse,
including all 778,848 base and 784,390 hotfix bundle dependency/reference slices
and their exact object boundaries. Existing synthetic catalog coverage now
exercises all four alignment cases and rejects corrupt padding. This fixes
catalog-format handling without inventing any of the 333 absent path mappings.

Unknown objects containing dialogue fields are counted and produce an explicit
format-update warning. No such unsupported node remained in this extraction.
Optional cutscene resources remain a limitation.

One performance follow-up remains: cinematic extraction hashes the entire
scene-catalog module, so a path-selection-only edit can unnecessarily invalidate
the expensive cinematic scan. Split decoding into a dedicated module before
narrowing that cache dependency; do not replace it with an unchecked version
number or fragile source slicing.

## Supplemental message and tip tables

The follow-up fetched the current tables at the same pinned revision as the
TextMaps. Their obfuscated field names differ from the older discovery snapshot.
The adapter checks the complete observed field set and the used value types for
every row; drift raises an actionable format-update error before replacing the
previous index. Supplemental downloads do not invalidate the scene cache.

- `MessageConfigTemplateTb`: 12,205 rows and 14,305 selected-Chinese text
  references, before deduplication and gender expansion. `LDHNMACDKLH` is the
  message identity; `BKAEOOPMGNC`/`GJNMPOBFICI` are the source columns. All nine
  observed nonempty pairs agree. Differing future pairs remain unresolved rather
  than guessing a gender or selecting whichever recording is installed.
  `FNOKFPDDECI`, `NAPGHEGEOOC`, `GGHOAADLHCF` and `EEJNOOGPFND` contain reply
  references; only exact textual IDs present in the selected TextMap are used.
- `TipsConfigTemplateTb`: 17,661 rows and 16,677 selected-Chinese references.
  `BHLFCEAPFIG` is the text identity, `NMMACKNBLKO` the main authored source,
  `FNHBBPCONOL` a separate reaction source/pool, `NPDBBLABDAK` an alternate
  source and `FFNNCACHDLN` additional sound events. Only the main supported
  sentence source is resolved. Silence requires empty main, alternate, reaction
  and event fields. Eighteen unequal alternate pairs and seven additional source
  names remain unresolved by this supplemental adapter; missing audio never
  changes those records to silent. The resulting new `gameplay_tip` records
  include 5,511 verified voices and 7,914 certified silent instructions.

The shared full-window exact-match capture can consume certified message/tip
records. These table checks did not constitute native UI or OCR-layout testing.

## Remaining table work

These field names are evidence from the separate cached 3.2 snapshot, not a
future-proof schema contract:

- `SubtitleConfigTemplateTb`: 992 rows, comprising 248 `Clue_` subtitles in each
  of four audio languages. `PMIKEPAJFKN` is the voice source, `APDFDBPICNM` the
  audio locale, `AFDMDFIHPMH` the text identity and `INPHPLFPOKF`/`GMHGKDKPKJB`
  the start/end timestamps. The Global launcher adapter now validates these
  intervals per dub and extracts the selected segment.
- `HollowBottomMessageTemplateTb` contains nine related text references. These
  may overlap imported tips, but no comprehensive independent adapter is claimed.
- `MainCityStoreVoiceConfigTemplateTb`: 262 source-only entries were observed.
  A text binding still needs to be established; the source name is not a subtitle.

## Verification

Focused regression checks cover typed silent objects, choices, ChatPlus,
cross-object voice isolation, reaction pools, malformed/truncated streams, both
Odin string encodings, path safety, comic ambiguity, supported ongoing schemas,
locale isolation and unknown/unavailable distinctions. The audit ran 17 JavaScript
tests and 25 Python tests successfully. The supplemental pass subsequently ran
31 Python tests successfully, including pinned downloads, schema drift, exact
message/choice separation, reactions and missing/ambiguous voices. Native Windows capture bounds, DPI,
desktop/mobile layout, Firefox/Chromium and all four installed audio languages
were not exercised by these parser checks; they remain separate acceptance work.

The [2026-11-01 packaged-reader verification](../zzz-runtime-acceptance-2026-11-01.md)
records the compiler-free production resource contract, Windows native checks
and a private installed-file comparison preserving all observed scene/cinematic
bindings. Other platform and final installer gates remain separate.
