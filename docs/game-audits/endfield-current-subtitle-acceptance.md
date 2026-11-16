# Endfield current subtitle acceptance

Checked November 16, 2026 against Global Windows **1.6.4**, initial/main
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

## Text provenance and remaining acceptance

Reader revision 19 marks text from the original conversation, radio, narration
and supported narrative tables, plus verified cinematic tracks, with
`text_capture_verified`. Arbitrary localization values receive no such flag.
This records subtitle ownership separately from `voice_status`: unknown and
unavailable audio retain their original state and no reaction becomes sentence
audio. The shared capture policy must honor this provenance through its
separate missing-audio opt-in and exact, unambiguous matching safeguards.

The current English worker has 53,675 records: 26,044 voiced, 18,619 unvoiced,
8,827 unavailable and 185 unknown. Those totals describe prepared authored
tables, not proof that every record is currently reachable story content.
The unavailable/unknown records include 8,134 conversations, 605 radio records,
271 narration records and two voice-message cells. Their text must not disappear
merely because their audio is unresolved.

Current timed film/scene preparation supplies 467 English, 483 Japanese,
459 Korean and 483 Mandarin clips per script choice. Saved bindings retain
release, dub, protagonist, recording identity and clock. Exact individual-word
cuts are not a closing requirement; a correctly identified original context
clip containing the complete utterance is acceptable when clearly labeled.
Subtitle display clocks alone do not establish a complete spoken interval.

The version rehearsal verifies changed English text, two changed original
recordings, a new voiced line, offline restart and retention of older recordings.
An additional real-worker transfer trial removed only the isolated trial's
cached English table, then interrupted its official HTTPS response after
4,096 bytes. No partial table or candidate snapshot was published. The retained
1.5.3 snapshot remained byte-for-byte unchanged. A fresh process retried normal
preparation in 28.219 seconds and produced all 53,675 current records with the
same text, audio bindings and voice states as the earlier current preparation.
Running-device scheduled activation remains distinct from worker/cache evidence.
Current-content acceptance still needs the shared missing-audio capture/export
route, representative end-to-end captures for that route, regional differences
accounted for against the selected mainland release, and any current cinematic
caption excluded for an unresolved recording/clock to be explicitly inventoried.
This report does **not** claim #86 is closed.
