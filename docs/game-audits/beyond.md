# BEYOND: Two Souls narrative audit

Audited 2026-10-27 against installed Windows PC archives with English and Dutch
voice data. This is a read-only asset and reader audit. It does not establish
full-game capture coverage, and it does not alter the game, accounts or settings.

## Installed evidence

The inventory found 50 BigFile index files, 1,421 containers containing authored
localization, nine standalone localization resources, and 66 Bink videos.
Container localization contains 17,942 English entry occurrences and 5,415
unique keys. Repeated copies across containers are not separate sentences.
The unique keys comprise 4,963 speech-reference entries and 452 text-only fields;
empty speech text can describe a vocalization without a usable subtitle.

The game has three distinct localization value families in the observed files:

- Type 1 carries authored FlowDialog references. A missing performance or
  unverified resource-language link is **unavailable**, never silent.
- Type 2 contains text labels. Only chapter-scoped labels with no speech pointer
  are classified as **unvoiced choices**. Global system and shared controller
  prompts are excluded. The English asset inventory contains 337 such chapter
  labels, including repeated wording.
- Type 4 points to localized textures. An image/resource alias is not transcript
  text and does not become an unvoiced sentence.

The parser preserves null, unresolved, internal and resolved pointers separately.
Their previous common `None` representation was insufficient evidence for silence.
Unknown flags or unclassified text remain unknown instead of being inferred from
an empty audio field. The same key and cue identity supply translations; text is
never translated or aligned by row position.

## Presentations and limits

| Presentation | Evidence and behavior |
| --- | --- |
| Conversations and branching replies | Authored subtitle paragraphs and exact FlowDialog identity, locale, partition offsets and cue times. Existing verified voice bindings are retained. |
| Simultaneous foreground/background voices | Independent authored cue identities remain available to the existing multi-speaker capture path. Matching two voices at once still requires visible, unique captions. |
| Inner monologue, narration, flashbacks and memories | Included when represented by the same verified subtitle/FlowDialog structures. The generic resource format does not prove a finer semantic category for every paragraph. |
| Short choice labels and action choices | Chapter-scoped type-2 fields are retained as text-only choices and require the unvoiced toggle. The spoken result of a choice has its own type-1 identity; its voice is never attached to the label. Repeated short choices can remain ambiguous to OCR. |
| Interactive cinematic scenes and phone intercuts | Supported through authored subtitles and original performances. Camera framing alone does not identify a different extraction format. |
| Prerendered video and bonus material | All 66 installed Bink files are inventoried, including story transitions, flashbacks, trailers, credits and making-of material. No verified per-caption audio join was established. Whole video audio is not substituted for a subtitle performance. |
| Written environmental material and localized textures | Nine standalone localization resources were parsed. Most reference texture resources rather than text sentences; image-only writing remains outside transcript coverage. No verified separate book, inventory-note or message schema was found. |
| Comics or storyboard panels | No distinct comic dialogue schema was established in this installation. This is an evidence limit, not a claim that every visual presentation has been ruled out. |
| DLC and alternate branches | The PC edition includes Advanced Experiments. All discovered BigFile archives are traversed, but archive enumeration is not gameplay acceptance for every DLC branch or ending. |
| Menus, system notices and controller prompts | Excluded from the narrative catalog even when their text is localized. |

## Update behavior

The reader revision is 3. Unknown archive/localization layouts produce
`unsupported_game_format` with instructions to finish game updates, verify files
and update the toolkit. Files changing during preparation produce
`game_files_changed`; the publication path keeps the previous complete table.
Every index/data part used by extraction contributes to the installed fingerprint.

Preparation can inventory text-only choices even if the selected voice pack is
absent. The resulting warning explicitly asks for that voice pack, and spoken
records stay unavailable. This makes a failed voice lookup distinguishable from
intentional silence.

Repeated containers can refer to the same performance. The reader validates its
partition once per preparation and caches only timings, offsets and block count.
It does not retain all audio in memory. A conflicting repeated offset table is
still rejected. Standalone localization keeps section lengths that embedded
components omit; the separate bounded reader validates all three section lengths
before parsing their contents.

## Verification

Synthetic checks cover pointer provenance, unknown pointer scopes, contradictory
null bindings, standalone section bounds, texture references, chapter choices,
system-label exclusion, missing dubs, unexpected archive updates and repeated
performance validation. Existing cue timing, translation, sample-rate, contextual
matching and multi-speaker capture regressions also run.

The 42 targeted tests passed. Fresh native preparations compared every existing
record's identity, original audio reference, source text and translations against
the previous reader, with no changes to those fields:

| Study language | Preserved voiced records | Confirmed text-only choices | Unavailable speech paragraphs | Total records |
| --- | ---: | ---: | ---: | ---: |
| English | 6,212 | 337 | 393 | 6,942 |
| Dutch | 5,446 | 337 | 393 | 6,176 |

The additional unavailable paragraphs have no verified original performance;
they remain excluded from capture even with the unvoiced toggle enabled. Some
unused paragraphs repeat cue numbers, so they retain their whole paragraph
identity without inventing timing anchors. Bound speech still requires valid
cue numbering and timing.

Each preparation validated 4,084 unique original performances and inspected
1,823 standalone localization entries. One original performance decoded
successfully for each study language. These were full performance-resource
decodes, not a claim that every line clip or physical-game scene was played.
Preparation took 210.61 seconds for English and 179.14 seconds for Dutch on this
machine, compared with 262.58 and 269.12 seconds for the previous reader in this
run. The comparison used warm local files and is not a general speed guarantee.
Private files, raw text, comparison assertions and timings remain under ignored
`output/checks/beyond-audit/`.

See [existing capture evidence](../beyond-support.md) for the earlier annotated
English opening replay and its explicit untested chapter/branch list. This audit
did not repeat physical gameplay, Windows DPI, mobile OCR or full-game playback.

## Primary references

- [Quantic Dream game page](https://www.quanticdream.com/en/beyond-two-souls): PC edition, local co-op, cinematic/chronological order and Advanced Experiments.
- [David Cage's gameplay explanation](https://blog.playstation.com/archive/2013/06/11/beyond-two-souls-gameplay-detailed-in-new-videos/): conversations, choices, environmental inspection and interactive cinematic presentation.
- [Quantic Dream PC launch announcement](https://www.quanticdream.com/img/uploads/corporate/page_70/ae00b2a9b2f54da09b1a075d74e59cb7.pdf): PC story and included DLC scope.
- [Publisher's Steam language matrix](https://store.steampowered.com/app/960990/Beyond_Two_Souls/): audio and subtitle availability are separate.
- [Ekey's original BigFile reader](https://github.com/Ekey/QD.BIG.Tool): archive versions and debug-resource structure; this is third-party format research, not publisher documentation.
