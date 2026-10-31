# Authored subtitle boundaries

Code and synthetic-fixture review: **2026-10-31**. Scope: all 25 games in the
[public capture catalog](../public/mobile-capture/games-data.json), plus the
retained Honkai Impact 3rd reader. This is an audit of supported resource formats,
not a claim that every scene or current game build has passed native gameplay.
No live installation, game file or saved transcript was changed for this review.

## Shared rule

A displayed subtitle page is its own transcript entry when the game supplies a
page boundary, cue identity or timestamp. Selecting a page must not emit later
pages in its paragraph. The original audio binding is a separate question: valid
authored recording intervals produce an excerpt; otherwise a verified complete
recording stays explicitly labeled as paragraph audio. Missing recordings remain
unavailable, and authored silence remains distinct from missing audio.

Translations require an evidenced relationship to that page. Equal page counts,
similar text, punctuation and reading duration do not establish one. Anonymous
pages therefore keep their source text without an invented translated page.
Source text and original audio never switch to another language to fill a gap.
Line wrapping inside the same displayed caption is not automatically a temporal
page boundary. Simultaneous captions can remain together in one authored frame.

The [page helper](../backend/subtitle_pages.py) separates a local page identity
from its optional cross-language alignment key. It retains repeated pages and
unmarked prefixes. Reader revisions invalidate older prepared snapshots when
their page representation changes; existing saved history is not rewritten.

## Reader inventory

| Game | Authored unit and reviewed behavior | Remaining boundary or audio limitation |
| --- | --- | --- |
| Zenless Zone Zero | Story, comic, ongoing and `CS_` cinematic TextMap IDs remain separate. Speaker/scene context combines only OCR rows in the same captured caption. | Pagination inside a single indivisible TextMap string has no independently verified schema. Timeline positions are not guessed recording cuts. |
| Wuthering Waves | Story `TidTalk`, choices and individual movie-caption text references remain separate localization identities. | Embedded movie audio and some event families remain unbound. No invented split inside an indivisible localized field. |
| Neverness to Everness | Dialogue namespace/key pairs remain separate; supported SRT movie cues use authored cue keys and times. | Dash and Japanese glyph aliases are OCR forms, not proof of successive pages. Unmapped movies/comics remain outside the known schema. |
| PRAGMATA | Each MSG entry remains independent; cinematic subtitle GUIDs bind to authored timeline segments. | Unknown timeline/MSG layouts and image-only reading have no fabricated page or voice mapping. |
| Cyberpunk 2077 | Each subtitle string ID and selected player variant remains separate; original hashed voice references do not merge neighboring entries. | Standalone video soundtracks and runtime pagination within an indivisible string have no established per-page mapping. |
| The Witcher 3 | Localization/string IDs retain base/DLC scope and exact speech identities. | Cinematic sidecar/video cues are not a completed original-audio mapping. No sentence-based splitting inside one field. |
| BEYOND: Two Souls | Authored cue IDs remain separate even when their recording timing cannot be resolved. | Unresolved cues use paragraph audio; duplicate/unknown cue layouts are not assigned guessed translations or cuts. |
| HEAVY RAIN | Revision 3 emits each `{B}` page, including repeated pages and unavailable recordings. | Anonymous page positions do not establish cross-language alignment or per-page audio timing. Multi-page translations are omitted; original audio has paragraph scope. |
| Honkai: Star Rail | Individual `TalkSentenceID`/TextMap references, choices and message bodies stay separate. | `Cutscene` voices without verified line bindings remain unavailable rather than borrowing the movie track. |
| Genshin Impact | Individual Talk/Dialog/reminder/card text references remain separate. Blank-line book paragraphs are distinct readable rows. | Movie subtitle/audio timing is incomplete. Readable translations currently use equal-count positional paragraph pairing without independent paragraph keys; that is limited alignment evidence, separate from voiced cue matching. |
| Arknights: Endfield | Authored dialogue nodes, panels and rich-content elements have separate identities and voice metadata. | An indivisible localized content field is not split by punctuation or text length; image/video-only cells are not fabricated captions. |
| Rise of the Tomb Raider | Revision 2 keeps each source MUL caption frame interval. A translation is attached only for the identical authored interval. | Staggered locale pages remain untranslated for that interval. Pages outside recording bounds retain paragraph audio. Bink movie locale/cue mapping remains unverified. |
| Shadow of the Tomb Raider | Separate localization identities and paired Wwise `subtitle-start`/`subtitle-end` labels provide caption intervals. | Missing/ambiguous labels do not justify inferred excerpts or new text boundaries. |
| Spyro Reignited Trilogy | Revision 2 preserves every `{N}` page for all three games, including repeats and missing voices. | Cross-language page mapping through `SplitIndex` is not established by this adapter. Anonymous multi-page translations are omitted; scene times are not audio-file offsets. |
| Detroit: Become Human | Revision 2 preserves unique, repeated and untimed cue pages independently. Valid individual cuts survive another cue's invalid timing. | Repeated markers and unmarked prefixes do not establish translation alignment. Untimed cues retain paragraph audio. |
| DEATH STRANDING | Sentence GUIDs and cinematic subtitle resources remain independent. Exact sequence bindings can attach a complete scene track to each resource. | Scene-track audio has paragraph scope. Raw newline aliases are visual-wrap candidates, not verified temporal pages. |
| Portal | Authored Source caption delay boundaries define distinct pages with the unchanged complete original recording. | Display delays are not recording-file offsets; delayed pages use paragraph audio. Differing localized delay layouts do not establish translation alignment. |
| Half-Life | Individual authored title/HUD message resources remain separate. | This reader has no supported spoken-subtitle transcript; ordinary newlines do not establish successive voiced pages. |
| A Plague Tale: Innocence | Each `VO__` localization/event identity remains independent; silent narrative entries retain separate identities. | No evidenced pagination schema inside a single localized field; complete original recording playback does not prove an inferred page cut. |
| METAL GEAR SOLID V: GROUND ZEROES | SUBP pages remain separate for field/radio, cassette and supported scene paths. | Translation joins require unique authored intervals; complete-track fallbacks do not merge source pages. |
| METAL GEAR SOLID V: THE PHANTOM PAIN | Each SUBP page retains its authored interval and exact original voice/scene identity. | Ambiguous/unavailable original bindings and unsupported scene formats are not replaced by neighboring pages or tracks. |
| Portal 2 | Source caption delay pages remain separate with paragraph audio; authored movie and credit cue records stay separate. | Localized delay layouts must agree. Existing validated movie cue intervals remain excerpts; caption delays alone are not recording offsets. |
| Half-Life 2 | The shared Source caption path preserves pages within each base/episode namespace. | Missing or incompatible caption timing is not evidence for a fabricated page translation. |
| Persona 5 Royal | BMD message pages are emitted separately with the relevant authored voice commands and flow/message identity. | Page number alone across unrelated messages or flows does not establish audio ownership. Unsupported message formats remain explicit. |
| Deus Ex: Human Revolution – Director's Cut | Each authored caption page remains separate for ordinary dialogue and supported CRI cinematic paths. | Cross-language pages require unique matching authored start/end intervals, not only equal counts. Invalid recording timing retains complete-track playback explicitly. |

The retained Honkai Impact 3rd reader is reviewed separately from the current
25-game catalog: explicit per-page TextMap hashes remain separate, with row-level
original audio. Retired-reader availability is not a new public game-support
announcement. HiTo is also outside the 25-game catalog and has no resource-based
subtitle-page join: its OCR frame text and bilingual lexicon alternatives do not
establish new authored page boundaries.

## Verification and remaining acceptance

Public synthetic regressions cover anonymous/repeated pages, unique and repeated
cue IDs, missing voices, invalid timing bounds, mismatched locale boundaries,
consecutive ZZZ cinematic IDs, and extraction-time interval validation. Relevant
tests include [page alignment](../backend/tests/test_subtitle_pages.py),
[Heavy Rain](../backend/tests/test_heavy_rain_assets.py),
[Detroit](../backend/tests/test_detroit_assets.py),
[Rise](../backend/tests/test_rise_tomb_assets.py),
[Spyro](../backend/tests/test_spyro_assets.py), and
[ZZZ](../backend/tests/test_zzz_languages.py). The parallel shared-reader checks
cover [Source captions](../backend/tests/test_source_caption_pages.py),
[Portal](../backend/tests/test_portal_assets.py),
[Portal 2](../backend/tests/test_portal2_assets.py),
[Ground Zeroes](../backend/tests/test_mgsv_gz_assets.py) and
[Deus Ex](../backend/tests/test_deusex_hr_assets.py). These are collected by the normal
Python test suite in GitHub Actions; no game files are included in these fixtures.

Native gameplay acceptance still needs representative multi-page sequences for
each supported game, including source/translation languages whose pagination
differs, voiced and confirmed-unvoiced paths, missing packs, and mobile display.
The supplied screenshot fixtures are useful capture regressions but a single
still cannot prove page order, audio start/end or translation alignment across
successive frames. The [screenshot regression plan](screenshot-regression-plan.md)
tracks missing game fixtures. Future game updates can introduce new boundary
formats; this audit does not assert support for an unobserved schema.
