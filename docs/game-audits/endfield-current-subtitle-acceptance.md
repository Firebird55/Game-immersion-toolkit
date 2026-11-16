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

The full revision-20 prepared indexes were then checked through the separate
missing-audio policy and the production preceding-caption controller. Both
`radio_sm2l7m1_5_002` and `radio_gm01m16_3_002` resolve after two stable
observations of their actual authored predecessor in all five selections.
Their audio stays unavailable. Default-off behavior, complete-text guards and
the two unknown cinematic captions per selection were also checked.

| Study selection | Residual radio rows matched with the applicable opt-ins/authored predecessor | Still guarded |
| --- | ---: | ---: |
| English | 133 / 134 | 1 |
| Japanese | 133 / 134 | 1 |
| Korean | 132 / 134 | 2 |
| Simplified Chinese | 132 / 134 | 2 |
| Traditional Chinese | 132 / 134 | 2 |

These remaining rows are explicitly accounted for, not a full capture pass:

- `radio_gm01m12_1_001` remains ambiguous in every selection and has no authored
  predecessor. Its short reaction-like caption cannot identify one current row.
- `radio_m1m76_2_001` remains ambiguous in Korean and both Chinese scripts and
  likewise has no authored predecessor.

The confirmed unvoiced `radio_e10m1_11_002` now resolves after stable observations
of `radio_e10m1_11_001` in both Chinese scripts through the existing unvoiced
option. It works with missing-audio capture disabled, and remains excluded when
unvoiced capture is disabled. Neither its state nor the existing toggle changed.

The smallest remaining matching work is additional authored presentation/speaker
context for the two rows without predecessors. Broad fuzzy matching or a
generic voice must not be substituted. One captured identity per selection is
an alias with the same complete official text, translations and audio state.

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

With revision-20 code and format metadata held fixed, the retained official
1.5.3 discovery descriptor was replayed once more. Its normal English worker
completed in 31.172 seconds with 48,291 records: 22,920 voiced, 17,189 unvoiced,
7,995 unavailable and 187 unknown. Live 1.6.4 again retains every old ID and adds
5,418 records, including 3,156 voiced records; five existing English texts change.
The earlier changed-recording and restart proof remains independently recorded.

The version rehearsal verifies changed English text, two changed original
recordings, a new voiced line, offline restart and retention of older recordings.
An additional real-worker transfer trial removed only the isolated trial's
cached English table, then interrupted its official HTTPS response after
4,096 bytes. No partial table or candidate snapshot was published. The retained
1.5.3 snapshot remained byte-for-byte unchanged. A fresh process retried normal
preparation in 28.219 seconds and produced all 53,675 current records with the
same text, audio bindings and voice states as the earlier current preparation.
Running-device scheduled activation remains distinct from worker/cache evidence.
Current-content acceptance still needs the remaining short-caption matching
cases above and representative physical/end-to-end captures. The eight cinematic
audio exceptions above remain explicit. This census covers tracks accepted by
the strict original-config/director reader; it does not prove that every other
client scene format or physical capture layout has been exercised.
This report does **not** claim #86 is closed.
