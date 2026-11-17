# Endfield current subtitle acceptance

Checked November 17, 2026 against Global Windows **1.6.4**, initial/main
resource **11775769-12**. This is the current-content closing basis for #86.
Historical Technical Test reconstruction is a separate archive feature.
The [publisher-version rehearsal](endfield.md#publisher-version-rehearsal-with-changed-text-and-voices--november-16-2026)
keeps the older release, reader and format metadata fixed.

## Original 89-group radio inventory

The current original `RadioTable`, actor/emotion tables, complete voice metadata
and selected-dub package inventories account for all **134 rows in 89 groups**.
Each row has English, Japanese, Korean and both Chinese-script text. Every
selected dub produces the same classification below; Traditional Chinese uses
the original Mandarin performance.

| Current route | Rows | Sentence audio | Text outcome |
| --- | ---: | --- | --- |
| Named generic reaction candidates | 121 | No bound sentence; reactions stay separate | Verified authored radio text, with unavailable sentence audio |
| No configured interjection | 4 | Released caller evidence establishes no speech route | Confirmed unvoiced capture |
| Explicitly empty authored performer | 5 | Released resolver rejects the reaction | Confirmed unvoiced capture |
| Literal performer `None` | 4 | No matching voice metadata; silence is not established | Verified authored radio text, with unavailable sentence audio |

The [per-row inventory](endfield-mission-radio-1.6.4.csv) records these routes.
The [original caller evidence and gameplay controls](endfield-radio-observations.md)
distinguish generic reactions from sentences. Fiona's tutorial reaction has its
own current dialogue-row binding; it does not require a preceding spoken line.
Neither an "ah" nor a sigh is offered as a recording of the displayed sentence.
No further per-row search for full sentence recordings is required by this
reaction mechanism unless new evidence identifies an actually missing spoken
subtitle.

The full revision-21 prepared indexes were checked through the separate
missing-audio policy and the production preceding-caption controller. Both
`radio_sm2l7m1_5_002` and `radio_gm01m16_3_002` resolve after two stable
observations of their actual authored predecessor in all five selections.
Their audio stays unavailable. Default-off behavior, complete-text guards and
the two unknown cinematic captions per selection were also checked.

| Study selection | Residual radio rows matched with the applicable opt-ins/authored predecessor or visible speaker | Still guarded |
| --- | ---: | ---: |
| English | 133 / 134 | 1 |
| Japanese | 133 / 134 | 1 |
| Korean | 133 / 134 | 1 |
| Simplified Chinese | 133 / 134 | 1 |
| Traditional Chinese | 133 / 134 | 1 |

These remaining rows are explicitly accounted for, not a full capture pass:

- `radio_gm01m12_1_001` remains ambiguous in every selection and has no authored
  predecessor. Its short reaction-like caption and punctuation-only anonymous
  speaker label cannot identify one current row.
- `radio_m1m76_2_001` now resolves in all five selections when its official
  Endministrator label is visible with the complete caption. Korean and both
  Chinese scripts remain ambiguous when only the sentence is visible; another
  authored radio line has the same sentence with Chen Qianyu as its speaker.
  No preceding line is required by the speaker/caption pair.

The confirmed unvoiced `radio_e10m1_11_002` now resolves after stable observations
of `radio_e10m1_11_001` in both Chinese scripts through the existing unvoiced
option. It works with missing-audio capture disabled, and remains excluded when
unvoiced capture is disabled. Neither its state nor the existing toggle changed.

The smallest remaining matching work is additional authored presentation
context for the anonymous row without a predecessor. Broad fuzzy matching or a
generic voice must not be substituted. One captured identity per selection is
an alias with the same complete official text, translations and audio state.

### Original speaker/caption context

The selected release's original `UI/Panels/Radio/RadioCtrl.lua` was fetched from
its own Lua VFS manifest and completely MD5-checked (`6677e5dc35b46c7d800bdc301006edd0`,
6,328 encoded bytes). It was decoded as data, never executed. Its display method
resolves `actorName` and `radioText` separately, then puts the name immediately
above the caption; an empty name uses the separate centered-text layout.

Revision 21 retains a complete official name-plus-caption OCR anchor. Competing
conversation/radio rows retain their own authored name/caption pairs, so equal
captions or equal speakers do not select a performance by table order. Only
literal names with identifying text are eligible: anonymous punctuation and
unresolved dynamic-name placeholders supply no anchor. Exact complete-text,
player and unavailable/unvoiced guards remain in effect. A choice, film or other
caption without an authored identifying speaker vetoes the same named-caption
anchor; a nearby name must not remove that ambiguity. This derives from the
current tables rather than a list of radio IDs; subsequent compatible content
can supply its own names and captions.

All five **ordinary installation-free publisher workers** completed against the
same current original release: 53,709 English, 54,968 Simplified Chinese, 53,690
Traditional Chinese, 53,800 Japanese and 53,688 Korean records. Every prior row
retains all fields other than the additional OCR anchors, including its complete
texts, translations, recording, audio state, branch and predecessor. A fresh
network-forbidden replay of all 134 residual rows per selection matches 133,
including the named short caption above. Existing predecessor controls,
unvoiced-only capture and the two unknown cinematic captions per selection pass
the same replay. The source-only replay separately reuses the retained verified
voice index; it does not claim a fresh offline publisher-index acquisition.

The remaining anonymous row is still guarded, and no generic reaction becomes
sentence audio. These are source/worker/matcher checks; physical capture of
every display layout and #86 closure are not claimed.

This 134-row subset is not the entire radio inventory. The current table has
**3,403 groups and 5,714 raw rows**. Protagonist expansion and localization yield:

| Study selection | Prepared radio records | Original sentence voices | Confirmed unvoiced | Unavailable sentence audio |
| --- | ---: | ---: | ---: | ---: |
| English | 5,913 | 5,109 | 199 | 605 |
| Simplified Chinese | 5,993 | 5,109 | 279 | 605 |
| Traditional Chinese | 5,913 | 5,109 | 199 | 605 |
| Japanese | 5,913 | 5,109 | 199 | 605 |
| Korean | 5,912 | 5,109 | 199 | 604 |

English's 605 unavailable radio records comprise 572 with available generic
reaction candidates, 25 without a mapped performer and eight without matching
reaction metadata. Its 199 unvoiced records comprise 112 without a configured
interjection and 87 with an explicit empty performer. The 87 are a complete
radio-record classification, separate from the five in the original subset.
Extra Simplified Chinese entries and the missing Korean text are localization
differences; no translation or speech is invented for them.

## Original 28-film inventory

The [28 configuration records](endfield-film-configs-1.6.4.csv) are not 28
missing current subtitle performances. Twenty-five have no authored caption
in their own tracks, including one null playable. The other three contain the
46 historical Chinese clocks. Their keys are absent from all 14 current
localization tables, and their movie names are absent from the current released
video inventory.

A fresh current-release source check read all **5,561 level scripts** and
**28 runtime string-pool shards**, verifying each original file against its
manifest hash. The pool has 277,950 strings and 39 movie-like names. The known
movie-call argument shape yields 44 references to 35 distinct movie names,
including the current quest movies in the original inventory, and **no `fmv_`
historical movie-call argument**. In particular, `fmv_e0m1_1` survives as a pool
string but has no matching movie-call action. A retained string alone is not
evidence that the current game plays that historical scene. This check covers
the identified serialized movie-call mechanism; it is not a claim to have
executed every possible caller in the client.

Current subtitle ownership must follow the enclosing scene rather than a
similar film name. The Valley Fort screen has four captions in
`cutscene_e1m3_2`, already prepared from its own original recording. The two
current captions bearing `cs_video_e0m0_3` IDs belong to `cutscene_e0m0_5`;
all four dubs and both protagonist variants have separate verified intervals.
The [film/gameplay inventory](endfield-film-gameplay.md#which-of-the-28-film-configurations-occur-in-the-game)
accounts for adjacent conversations, films without readable captions, retained
beta configurations and the historical test films separately.

The seven unfinished historical Mandarin archive cuts therefore do not by
themselves block current subtitle acceptance. A newly found current caller or
current subtitled performance would reopen the relevant item. Historical
English text and archive cuts remain explicitly incomplete in the
[archive guide](endfield-alpha-archive.md).

## Written instructions and tutorials

The original current `InstructionBookCtrl`, `WikiGuideCtrl`,
`WikiGuideTipsCtrl`, `WikiGuideMediaCell` and `DungeonCharTutorialStepHudCtrl`
were retrieved from the same release's Lua manifest, completely MD5-checked and
decoded as data, never executed. The first three views render the authored
written body independently of titles and illustrative media. The training HUD
selects its `stepDesc` through the current dungeon-stage `stepIds`; its icon and
short `iconDesc` labels are separate fields.

Revision 22 adds these finite current-format inventories:

| Written presentation | Current authored bodies | Selection and treatment |
| --- | ---: | --- |
| Instruction books | 131 | Original `content`, separately from the heading |
| Guide explanations | 631 | Original page `content`; all pages have current tutorial references; input-specific pages retain their own identity |
| Operator-training steps | 498 | All current step definitions are referenced by the 29 dungeon tutorial entries; original `stepDesc`, separately from the skill label |

These **1,260 bodies per study selection** are written, unvoiced presentations,
using the existing opt-in full-frame text reader on the tip channel. They do not
borrow a video, background track or combat bark as sentence audio. Their exact
official translations come from the same localization tables; an absent
translation is not synthesized. New compatible page IDs, body fields and stage
references are discovered through the current original tables, not an ID list.
Missing stage references produce an explicit warning; retained unreferenced step
definitions are not treated as displayed training instructions. A changed
required structure rejects preparation while retaining the previous snapshot.

The ordinary installation-free Global 1.6.4 workers prepare **54,969 English,
56,228 Simplified Chinese, 54,950 Traditional Chinese, 55,060 Japanese and 54,948
Korean records**. Every previous record retains its complete texts, translations,
audio reference, voice state and player/predecessor binding. A single old
conversation's speaker OCR anchor is conservatively removed in each selection:
a newly represented unnamed instruction has the same rendered caption. A name
elsewhere in the frame must not turn that written explanation into speech.
Saved recordings retain their original identity and source.

A fresh, network-forbidden complete-index replay tests every new full body.
Aliases count only when **all official texts and the unvoiced state agree**:

| Study selection | Instruction bodies matched | Guide bodies matched | Training-step bodies matched | Standalone bodies still guarded |
| --- | ---: | ---: | ---: | ---: |
| English | 125 / 131 | 630 / 631 | 462 / 498 | 43 |
| Simplified Chinese | 131 / 131 | 626 / 631 | 469 / 498 | 34 |
| Traditional Chinese | 131 / 131 | 626 / 631 | 469 / 498 | 34 |
| Japanese | 131 / 131 | 626 / 631 | 492 / 498 | 11 |
| Korean | 131 / 131 | 626 / 631 | 498 / 498 | 5 |

The [remaining standalone-body cases](endfield-tutorial-capture-guards-1.6.4.csv)
need reliable presentation context or rendering support; a populated prepared
row is not a complete capture pass. This replay does not change the existing
radio result: 133 of 134 residual rows still match per selection under their
applicable opt-ins/authored context, and each selection's two unknown cinematic
captions retain their original state and complete-text guard.

With revision-22 reader and unchanged format metadata frozen, an explicitly
**replayed** original 1.5.3 descriptor prepares 49,438 English records, compared
with live 1.6.4's 54,969. Every old ID remains, 5,531 records are added including
3,156 voiced and **113 new written bodies**; six existing written explanations
change alongside the five previously documented English changes. All previously
prepared baseline texts/audio/states also remain equal to the retained
revision-21 baseline apart from recognition anchors. This extends the existing
changed-recording/restart proof; it does not claim a new physical-device test.

The [publisher's update notes](https://endfield.gryphline.com/en-us/news/0751)
independently identify current Basic Training and Operator Guide content. Those
notes establish presentation availability, not exact runtime OCR or media
coverage. These inventories are authored-body denominators, not a claim that
every tutorial was unlocked or played on a physical device. Exact matching and
ambiguity guards still apply to repeated or short explanations. Video sound,
image-only text, input-glyph rendering and every physical layout remain separate
acceptance work. No tutorial audio or story-wide completeness is inferred from
the count of written bodies.

## Written Baker system messages

Revision 23 follows the native `SNSDialogContentType.System` presentation,
separately from ordinary text, voice, image and video cells. The selected
original Windows client's metadata defines **System = 7**; the same field/default
inventory independently reproduces the existing Text = 1 and Voice = 5 controls.
The current MD5-checked `SNSContentSystemMsg` Lua widget renders the cell's
`content` as written text. This source was decoded as data, never executed.
An original text reference in an image cell is not enough to call it a displayed
caption; those other media widgets retain their own rendering rules.

All **117 current authored system-message bodies** are now prepared in every
study selection under the existing unvoiced capture option. They retain their
official localized text, have no sentence-audio reference and do not borrow the
cell's parameter or a background voice. The normal publisher workers prepare
55,086 English, 56,345 Simplified Chinese, 55,067 Traditional Chinese, 55,177
Japanese and 55,065 Korean records. Every prior revision-22 record remains
unchanged, including its recognition anchors and original audio state.

Fresh network-forbidden complete-index matching resolves 102 of the 117 English
bodies, 104 in each Chinese script, 110 Japanese and 104 Korean. These counts
include aliases only when all official texts and the unvoiced state agree. The
[remaining standalone system-message cases](endfield-system-message-capture-guards-1.6.4.csv)
remain guarded; indexing the native text is not a full capture pass. The shared
minimum-text and ambiguity rules were not weakened for short system labels.

The same frozen revision-23 reader prepares 49,550 English records from the
explicitly replayed original 1.5.3 descriptor and 55,086 from live 1.6.4. All old
IDs remain. The 5,536 additions include 3,156 voiced rows and 118 written bodies
(113 tutorials/instructions and five system messages). The six written-text
changes above are retained. Previously verified recordings keep their exact
source references; this text-only extension does not claim a new audio/device
acceptance run. Runtime-generated notices, actor-name substitution, unsupported
media contents and the remaining presentation/capture guards stay explicit.

## Original top captions and training-step order

Revision 24 reads each current dialogue graph's original `_showAtTop`
declaration. The current `DialogTimelineCtrl` renders those captions through
its separate `topTrunkText`/`topTrunkNode` view; its original encoded Lua is
MD5-checked (`0d86f5c6732969ce9dc5388b3413c1c0`) and decoded only as data.
The controller and source graphs are not executed. Ordinary voiced top captions
therefore enter full-frame capture without enabling unvoiced-text capture.
The normal bottom dialogue region remains independently available.

An offline census read all **3,093 original current dialogue graphs**, with
18,835 distinct trunk references. Fifteen nodes explicitly use the top layout.
The strict selector accepts 12 IDs, producing **13 prepared records** because
one has both protagonist performances. Three other top nodes enable an emotion
voice route and retain the existing conservative layout restriction pending
separate route acceptance. Custom text, disabled speech, actor-action groups,
radio and alternate-voice cases do not acquire this new top-caption route.
This finite graph inventory is not proof that every other client presentation
or indirect world trigger has been inventoried.

Only original, unique and unbranched same-layout edges supply a preceding top
caption. Referenced operator-training stages independently supply their exact
`stepIds` order. A step used with different predecessors gets no guessed order.
Written steps can share predecessor aliases only when all their official texts
and unvoiced state agree. A confirmed later occurrence replaces a canonical
first-row alias only when every other complete source field also agrees,
including translations, audio, branch, category and capture channels.
Menus, changed capture scope and stale observations clear these contexts.
Short text and ambiguity safeguards remain unchanged.

All five ordinary publisher workers complete with the revision-23 record totals
above. Every previous text, translation, recording reference, voice status and
OCR anchor remains exactly equal. Only 13 capture-channel declarations,
359 predecessor fields and 312 English/326 other-selection step-alias fields
change. A fresh network-forbidden complete-index replay checks each current
training stage in authored order, with two stable exact observations per step:

| Study selection | Training bodies matched with stage context | Remaining guarded bodies |
| --- | ---: | ---: |
| English | 472 / 498 | 26 |
| Simplified Chinese | 478 / 498 | 20 |
| Traditional Chinese | 478 / 498 | 20 |
| Japanese | 496 / 498 | 2 |
| Korean | 498 / 498 | 0 |

These counts include aliases only when all official texts and the unvoiced state
agree. The [remaining ordered-stage cases](endfield-training-context-guards-1.6.4.csv)
stay guarded. The instruction-book and guide-body standalone limits above remain
separate. All 12 selected top captions match independently for each protagonist
in every study selection. Synthetic production-capture tests additionally check
the top screen position, written-step progression, repeated occurrence and menu
reset. This is not physical OCR, device or playback acceptance.

With the same revision-24 source and format metadata frozen, the explicitly
replayed original 1.5.3 descriptor prepares 49,550 English records; live 1.6.4
prepares 55,086. Every old ID survives, with 5,536 added records including
3,156 voiced records and the same 11 changed English texts. Both generations
discover the same 13 selected top-caption records. The existing changed-voice,
offline restart and retained-recording proof remains separate; this metadata
change does not claim a new physical scheduled-activation trial.

## Explicitly disabled original dialogue speech

Revision 25 honors a unique original dialogue caller's literal
`disablePlayVoice = true`. The original Windows metadata identifies this field
in `DialogPlayTrunkActionData`. Static reading of `DialogManager._PlayVoice`
shows its branch skipping both actual `VoiceManager.SpeakNarrative` calls.
The same metadata lookup independently reproduces the top-layout getter field.
All four current, MD5-checked original IFix files were parsed as data; their
replacement signatures do not patch this controller or its action-data type.
No native client, Lua or patch code was executed, and no negative speech
detector result supplies this classification.

The full 3,093-graph census contains exactly two unique simple callers with
that declaration: `dlg_c37m3_40_010` and `dlg_sm2l2m4_3_012`. Both display only
punctuation. The first retains an original WEM in the released tables/packages;
the second has no usable recording. Their actual caller disables speech in
both cases, so both now use **unvoiced** state. Scripted actor actions/groups,
alternate routes, custom text and repeated references stay outside this strict
rule. The source selector follows current graph paths and content hashes;
new compatible IDs do not require an ID override or newer community snapshot.

All five ordinary current publisher workers retain their previous record
totals, texts, translations, capture layouts, predecessors and recognition
anchors. Exactly these two voice states change per selection: one voiced and
one unavailable record become unvoiced, and the disabled retained WEM is no
longer offered as the caption's sentence recording. All other audio bindings
and states remain exactly equal. Existing saved recordings and older snapshots
are retained. Punctuation-only text remains guarded by the existing minimum;
unvoiced capture remains opt-in.

The same frozen revision-25 reader replays original 1.5.3 discovery and prepares
49,550 English records, against live 1.6.4's 55,086. Every old ID remains, with
5,536 new records and the same 11 changed English texts. The updated new-voice
count is **3,155**: the later retained-but-disabled recording is correctly
excluded. The old generation contains only the second disabled caller, whose
prior unavailable state becomes unvoiced. No other prior audio or capture
metadata changes. This corrects source ownership; physical gameplay and the
remaining presentation/device acceptance gates remain separate.

## Original operator recordings and source callers

Revision 26 resolves a specific recording-identity collision. Current spaceship
dialogue and the operator's voice archive can display the same official caption
while referring to separate WEM paths. The original graph declares its
`spaceshipCharId` and NPC actor index. Its blank trunk owns the outgoing
`ExTrunkReplace` extension; the native `GetExNodeData` and
`FindTrunkIdForReplacement` readers establish that ownership. All 33 current
friendship extensions contain six conditional utterances each. Their **198
original sentence voices are already prepared in every study selection**.
The complete source selector also accounts for direct spaceship utterances:
394 speaker bindings across 34 operator identities. Character profiles retain
their own original `CharacterTable` speaker identity.

Before this correction, different file IDs made 197 English, 198 Simplified
Chinese, 196 Traditional Chinese, 197 Japanese and 198 Korean friendship captions
ambiguous. Missing sentence files were not the cause. A bounded original-media
census checks matching full text, speaker/player branch and line scope, then
compares complete original WEM bytes. Every same-length candidate group proved
byte-identical: 230 English, 230 Simplified Chinese, 229 Traditional Chinese,
142 Japanese and 230 Korean groups. Different-length groups remain separate.
Japanese has fewer eligible groups because the complete requested official
translations do not always agree between presentations.

All verified groups have default dialogue `audioEffect = 0`. Their original
metadata agrees except for path, speaker channel and voice type. Those **in-game
bus differences remain explicit**; no equal gameplay mix is claimed. A fresh
network-forbidden process exported one conversation/archive pair per dub
through `LocalVoiceAssetService`. Each pair produced identical MP3 bytes and
identical non-silent PCM. Thus the toolkit's original line export, playback and
gain agree even though the game can route those sources differently.

The reader adds optional `original_recording_sha256` and `original_speaker_id`
metadata while retaining every authored audio reference and member identity.
It only compares the complete verified raw recording under default line-export
options. Full official texts, translations, actual speaker, player, locale,
scope, predecessor requirements, member IDs, channels and OCR evidence must
still agree. An archive entry cannot bypass a guarded short conversation.
Portable clips additionally retain their actual encoded content identity;
different encodings or export options remain separate. No recording-ID alias
list, fuzzy exception or generic reaction substitution is used.

Hash receipts bind to the current official package digest, entry ID/offset/size
and dub. Changed packages require new byte verification; unchanged packages can
reuse verified cache receipts across resource revisions. Source graph bindings
independently follow their current path/content digest. New compatible game IDs
therefore need no toolkit update or newer community-data snapshot.

All five ordinary publisher workers retain the revision-25 record totals and
every prior text, original audio reference, state, recognition anchor, channel,
predecessor and member field. A fresh complete-index replay, with networking
forbidden and ordinary voiced capture, now gives:

| Study selection | Friendship captions captured | Still guarded | All verified recording groups captured |
| --- | ---: | ---: | ---: |
| English | 173 / 198 | 25 | 230 / 230 |
| Simplified Chinese | 172 / 198 | 26 | 230 / 230 |
| Traditional Chinese | 173 / 198 | 25 | 229 / 229 |
| Japanese | 113 / 198 | 85 | 142 / 142 |
| Korean | 172 / 198 | 26 | 230 / 230 |

The last column covers all annotated conversation/archive groups, including
friendship groups, rather than an additional disjoint inventory. The
[caption-only friendship guards](endfield-operator-capture-guards-1.6.4.csv)
retain actual recording or official-translation differences. Revision 29 adds
the separately verified world-dialogue presentation below; it does not merge
these recordings or change bare-caption matching.

With the same revision-26 code and format metadata frozen, explicitly replayed
original 1.5.3 discovery prepares 49,550 English records; live 1.6.4 prepares
55,086. Every old ID and prior binding survives, including 460 original-recording
digest rows in each generation. The update adds 5,536 records, including 3,155
voiced records, with the same 11 existing English text changes. Actual selected
old media is verified separately; the package-bound digest cache does not assume
that equal file IDs imply equal content across releases. The earlier
changed-recording, interruption and retained-export proofs remain separate.

For caller inventory, an owned data reader consumes all 405,739 bytes of the
current original `DialogIdTable`: 3,106 dialogue IDs and 5,440 option IDs, with
both inverse maps consistent. All 3,093 current dialogue graphs have registry
entries. Thirteen registry entries lack a current graph; none has a checked
constant-dialogue-parameter reference in the 5,561 current level scripts.
They are not counted as missing current subtitles without a current caller.
Static original union metadata identifies all 1,364 action tags. The strict
reader accepts all 15 serialized fields of **1,029 `StartDialogAction` records**:
1,021 literal calls refer to 974 dialogue IDs; eight parameterized calls in four
scripts still need producer/context tracing. NPC overrides, preloads and other
caller families are separate. This is source-call evidence, not execution of
the game's root triggers or physical gameplay acceptance.

## Compact current capture and audio endpoint

### Original world-dialogue presentation

Revision 29 distinguishes a spoken bottom world caption from an operator's
voice-archive copy using the released game's own UI and controller data.
Preparation reads three original UI prefabs and three original Lua controllers
as data. It verifies the separate speaker/body view, upper-right Auto/Skip
controls and the profile's mutually exclusive role-information/voice-information
views. It derives localized control labels and original visible actor names
from the current publisher tables. No original game or Lua code is executed.

The stateless full-frame route requires Auto and Skip in their expected relative
positions, one separately visible original actor, the complete centered bottom
caption, valid physical OCR boxes and confidence of at least 0.8 for every used
line. Missing controls, unreliable body lines, profile overlays, response-only
text and changed geometry fail closed. NPC choices may remain visible beside
the spoken caption. Their menu detection still resets dialogue context; this
route neither consumes nor establishes a predecessor. All short-caption,
predecessor, missing-audio, unknown-audio and competing-presentation vetoes remain.
Only a voiced operator-archive peer with the same original actor is excluded
after world ownership is proved. Different conversation takes stay ambiguous.

All five ordinary current publisher workers retain every revision-27 record
field, original recording and translation. Their new UI descriptors contain
only their actually prepared text locales and 33 original actors per locale.
With every current record and archive peer retained, a network-forbidden replay
of the actual production capture service captures **198 / 198 friendship
captions in every study selection**, after two stable observations, with NPC
choices present and the menu flag set. The finite proof uses exact synthetic
OCR spans; each row also rejects missing Skip, unreliable body confidence,
profile overlays and response-only bottom text. Bare-caption counts in the
table above remain unchanged.

Separately, the pinned bundled OCR was run offline on public gameplay images
from the [GameWith trust guide](https://gamewith.net/akendfield/72609). At the
production OCR size, the complete world image supplies genuine Auto-Play, Skip,
actor and wrapped-caption boxes/confidences. The complete production index and
capture service choose the exact original Ardelia conversation and schedule its
recording while NPC choices are visible. The smaller image misses Skip and is
rejected; the actual profile image is rejected. These older public images are
layout/OCR evidence, not current physical gameplay or native-device acceptance.

The same frozen revision-29 reader also derives the original UI descriptor from
explicitly replayed publisher 1.5.3: its six source digests differ from current
1.6.4 and its prepared locales contain 31 actors. All 49,550 old records retain
every revision-27 field; live 1.6.4 keeps 55,086, including the same 5,536 added
records, 3,155 added voiced rows and 11 changed English texts. No additional
original recordings are downloaded for this rehearsal. UI labels, actor names,
bindings and recordings are re-derived after normal updates. Unsupported UI or
controller changes omit this extra route and retain the existing guarded index.
The bounded descriptor and pure presentation classifier are shared contracts
for portable preparation; native confidence and device acceptance remain
separate requirements.

### Source-declared top captions

Revision 27 completes the source-declared top-caption family: all **15 current
IDs / 16 protagonist-expanded records** enter the voiced full-frame route.
The three previously excluded `enableEmotionVoice` declarations have their own
original sentence recordings. Static original `DialogManager._PlayVoice` data
shows that the primary `DialogTextData.audioOverride` lookup runs first;
`VoiceUtils.TryGetVoiceDuration` must find voice metadata and a duration greater
than zero. A successful lookup skips the complete emotion fallback branch.
The original duration getter reads the selected Mandarin, English, Japanese or
Korean field. The current original patch inventory changes neither controller
nor voice utility. No client or patch code is executed for this proof.

Preparation now requires the exact authored primary filename, its matching
`AudioDialog` ID, a finite positive duration in the selected dub and that dub's
original recording before admitting any top caption to full-frame voiced
capture. Missing metadata, invalid/zero duration, placeholders and missing
media do not gain this route. The bottom mission selector keeps its existing
emotion-route restrictions. No caption-ID allowlist or borrowed generic sound
is used. Normal updates re-evaluate the current graph, metadata and packages.

All five ordinary current publisher workers keep their complete record totals,
texts, recordings, voice states, OCR anchors, recording digests and member
identities. Exactly three capture-channel fields and two authored predecessor
fields change. A network-forbidden replay uses each complete current language
index and the actual `CaptureService` with synthetic top-position OCR boxes:
**15 / 15 captions per protagonist in every study selection**, each after two
stable observations, with unvoiced and missing-audio capture disabled. This is
production capture-policy evidence, not native OCR or physical playback.

The same frozen revision-27 reader prepares 49,550 English records from the
explicitly replayed original 1.5.3 descriptor and 55,086 from live 1.6.4. Both
generations admit 16 expanded top records using their own primary metadata.
Every old ID, recording reference, voice state, OCR anchor, digest and member
identity survives. The current generation adds 5,536 records including 3,155
voiced rows and keeps the same 11 existing English-text changes. Original
package directories are revalidated through the normal publisher reader;
this remains a frozen two-generation rehearsal rather than future-update or
physical scheduled-activation acceptance.

These finite checked families are not a claim that every indirect trigger,
readable layout, operator menu or other narrative presentation has passed.
Counts use prepared captions/performance pairs rather than unlocked player
content. Chinese script choices share the original Mandarin sources.

| Checked family | English | Simplified Chinese | Traditional Chinese | Japanese | Korean | Remaining condition |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Current cinematic original audio bound | 499 / 501 | 501 / 503 | 501 / 503 | 495 / 497 | 497 / 499 | Two boss-caption performances per selection retain unknown speech ownership |
| Original residual radio subset captured | 133 / 134 | 133 / 134 | 133 / 134 | 133 / 134 | 133 / 134 | One anonymous short caption; generic reactions stay separate |
| Source-declared top captions admitted automatically, per protagonist | 15 / 15 | 15 / 15 | 15 / 15 | 15 / 15 | 15 / 15 | Exact primary binding and positive selected-dub duration required; physical acceptance separate |
| Instruction bodies captured | 125 / 131 | 131 / 131 | 131 / 131 | 131 / 131 | 131 / 131 | Six English bodies remain guarded |
| Guide bodies captured | 630 / 631 | 626 / 631 | 626 / 631 | 626 / 631 | 626 / 631 | Exact/rendering ambiguity remains |
| Training bodies captured with authored order | 472 / 498 | 478 / 498 | 478 / 498 | 496 / 498 | 498 / 498 | Short/repeated cases retain context guards |
| Baker system bodies captured | 102 / 117 | 104 / 117 | 104 / 117 | 110 / 117 | 104 / 117 | Short/repeated system text retains guards |
| Friendship NPC captions, caption alone | 173 / 198 | 172 / 198 | 173 / 198 | 113 / 198 | 172 / 198 | Recording/translation differences retain guards |
| Friendship NPC captions, verified world UI | 198 / 198 | 198 / 198 | 198 / 198 | 198 / 198 | 198 / 198 | Complete localized controls, actor, caption, geometry and reliable confidence; current physical acceptance separate |

All friendship recordings are prepared; the last two rows measure capture
disambiguation. The cinematic row measures original audio ownership, not a
physical capture pass. Other prepared conversation, radio, choice, story-panel,
message, readable, operator archive and bark inventories retain their existing
limits. Finite active-caller closure and representative physical/end-to-end
capture, scheduled activation and regional acceptance remain open. #86 stays
open; historical films without a current caller are not substituted for those
current acceptance requirements.

## Text provenance and remaining acceptance

Reader revisions 19–20 mark text from the original conversation, radio, narration
and supported narrative tables, plus verified cinematic tracks, with
`text_capture_verified`. Arbitrary localization values receive no such flag.
This records subtitle ownership separately from `voice_status`: unknown and
unavailable audio retain their original state and no reaction becomes sentence
audio. The shared capture policy must honor this provenance through its
separate missing-audio opt-in and exact, unambiguous matching safeguards.

The revision-20 English worker has 53,709 records: 26,076 voiced, 18,619 unvoiced,
8,827 unavailable and 187 unknown. Those totals describe prepared authored
tables, not proof that every record is currently reachable story content.
The unavailable/unknown records include 8,134 conversations, 605 radio records,
271 narration records, two voice-message cells and two cinematic captions. Their text must not disappear
merely because their audio is unresolved.

Current film/scene preparation retains 467 English, 483 Japanese,
459 Korean and 483 Mandarin line clips per script choice. Saved bindings retain
release, dub, protagonist, recording identity and clock. Exact individual-word
cuts are not a closing requirement; a correctly identified original context
clip containing the complete utterance is acceptable when clearly labeled.
Subtitle display clocks alone do not establish a complete spoken interval.

### Complete original context recordings

A fresh census of the readable localized movie and scene tracks found 108
additional current performance/caption pairs beyond those line clips. Their
recording/caller, dub, protagonist and original bytes were checked separately.
Revision 20 adds **100 context bindings**, retaining the other eight captions
with unknown audio rather than assigning the wrong recording.

| Study selection | Existing line clips | New original context recordings | Authored captions with unknown audio | Accounted current performance/caption pairs |
| --- | ---: | ---: | ---: | ---: |
| English | 467 | 32 | 2 | 501 |
| Japanese | 483 | 12 | 2 | 497 |
| Korean | 459 | 38 | 2 | 499 |
| Mandarin, each Chinese script | 483 | 18 | 2 | 503 |

Context exports contain the **complete original scene recording**, observed at
14.5–224.5 seconds. They are labeled `context`, never a precise or short sentence
cut. Overlapping captions and repeated text can share this complete source only
when every occurrence has the same unambiguous original recording. A caption
that remains on screen after the speech track ends does not truncate that
recording. Player-marked text selects the matching protagonist. A missing game
translation does not remove available study text or fabricate a replacement.

All five ordinary publisher language workers completed. The 53,675 previously
prepared English records retain exactly the same texts, audio bindings, voice
states, protagonist selections and predecessors. Eight representative context
exports cover overlap, repetition, lingering text, both protagonists and all
five study selections. Their MP3s decode to nonzero PCM of the expected full
source length. A fresh process blocked networking, discovery and context
rebuilding, exported into new folders, and reproduced all eight PCM hashes.
The new immutable context cache is separate from the existing line-clip cache;
existing saved line exports do not require a new context census.

The eight unresolved pairs are the two protagonist performances of
`cutscene_e0m0_5_03` in all four dubs. The selected original voice recording
contains digital silence during its English and Mandarin caption windows, and
only sparse ±1 least-significant-bit decoder noise in Japanese and Korean.
It contains different, later sentences and cannot be offered as this line's
voice. The current scene's separate effects event has six original media
sources; the bounded source check did not establish a spoken binding for this
caption. Missing speech detection is not proof of silence. These entries remain
**unknown**, with their original text and verified subtitle provenance. No
per-caption silence override or reaction substitution was added.

The same ordinary worker also prepared current **Mainland China 1.6.4** English
and Mandarin. It selected that edition's own release descriptor and original
sources, producing the same 501 English and 503 Mandarin accounted cinematic
pairs, including the same two unresolved captions per selection. English has
53,709 total records and Mandarin 54,968. This verifies current regional source
preparation; it does not claim every regional device/playback flow was exercised.
An independent original-file comparison also matched all 770 table hashes,
all 22 initial/dub/hotfix package hashes across the four dubs, and all 5,826
cinematic asset paths and bundle hashes between the selected Global and
Mainland releases. The editions retain their own release descriptors and URLs.

A bounded check of the current male prologue playback locates the unresolved
boss caption at [4:54](https://www.youtube.com/watch?v=59n93iqzIIM&t=294s).
Two separate later original-voice controls identify the scene at upload offset
290.045375 seconds, with waveform correlations 0.750 and 0.642. The checked
4:54.3 frame displays this exact caption over the boss's runes/effects. A
24-second transcript recovers the later ordinary English voices but does not
establish the boss caption's spoken wording. The speech-detector configuration
also misses those known controls, so its negative result is not evidence of
silence. This is an actual current caption with **unknown original speech
ownership**, not a completed spoken binding or certified unvoiced line.

With revision-21 code and the same frozen format metadata, the retained official
1.5.3 discovery descriptor was replayed once more. Its normal English worker
completed in 23.172 seconds with 48,291 records: 22,920 voiced, 17,189 unvoiced,
7,995 unavailable and 187 unknown. Live 1.6.4 again retains every old ID and adds
5,418 records, including 3,156 voiced records; five existing English texts change.
The earlier changed-recording and restart proof remains independently recorded.
Every old baseline row, and every live revision-21 worker row above, matches
the retained revision-20 evidence in all fields apart from the additional OCR
anchors. The new anchors do not replace historical texts or recording references.

The version rehearsal verifies changed English text, two changed original
recordings, a new voiced line, offline restart and retention of older recordings.
An additional real-worker transfer trial removed only the isolated trial's
cached English table, then interrupted its official HTTPS response after
4,096 bytes. No partial table or candidate snapshot was published. The retained
1.5.3 snapshot remained byte-for-byte unchanged. A fresh process retried normal
preparation in 28.219 seconds and produced all 53,675 current records with the
same text, audio bindings and voice states as the earlier current preparation.
Running-device scheduled activation remains distinct from worker/cache evidence.
Current-content acceptance still needs the remaining anonymous short-caption
case above and representative physical/end-to-end captures. The eight cinematic
audio exceptions above remain explicit. This census covers tracks accepted by
the strict original-config/director reader; it does not prove that every other
client scene format or physical capture layout has been exercised.
This report does **not** claim #86 is closed.
