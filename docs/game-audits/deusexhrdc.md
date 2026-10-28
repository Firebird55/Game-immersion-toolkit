# Deus Ex: Human Revolution — Director's Cut

Reviewed 2026-10-28. This report covers the Windows Director's Cut, Steam
application **238010**, identified by `DXHRDC.exe` and `BIGFILE.000`.
The original Human Revolution and The Missing Link standalone editions are
different products and are not claimed as supported by this adapter.

## Official languages and primary evidence

The [publisher's Steam listing](https://store.steampowered.com/app/238010/Deus_Ex_Human_Revolution__Directors_Cut/)
lists interface, full audio and subtitles for **English, French, Italian,
German and Spanish (Spain)**. The adapter supports all five: `en`, `fr`, `it`,
`de`, `es-ES`. All five packs are present in the audited installation. There
is no fallback from a missing selected voice to English. The listing explicitly
identifies developer commentary as English only and includes the original
making-of video as an extra.

The [official PC manual](https://store.steampowered.com/manual/238010) documents
Infolink briefings, social conversations, the mission log, media log, computers,
exploration and the extras menu. These establish the presentation inventory
alongside the installed authored resources. Its PDF pages 3–5, 8–9 cover the
relevant HUD, menu and social systems. The Steam listing also confirms that
The Missing Link and Tong's Mission are integrated into this edition.

| Locale | Shipped text-table code | BIGFILE language bit | Original speech |
| --- | --- | --- | --- |
| `en` | 0 | 1 | Installed and decoded |
| `fr` | 1 | 2 | Installed and decoded |
| `it` | 2 | 8 | Installed and decoded |
| `de` | 3 | 4 | Installed and decoded |
| `es-ES` | 4 | 16 | Installed and decoded |

Other legacy locale bits, text tables and cinematic source names occur in the
archives. Their presence does not establish a complete officially supported
Director's Cut localization. Russian, Polish and Japanese are not advertised
as supported study/audio choices for this edition.

## Authored bindings and presentation coverage

| Presentation | Binding and behavior |
| --- | --- |
| Ordinary conversations and selected player responses | DRM type 7/subtype 13 sound graph → stream path and authored 16-bit text ID → matching `locals.bin` entry → exact BIGFILE path hash and selected language bit. Original MUL streams demux to their FSB4 recording; stereo streams preserve both original channels. |
| Ambient, overheard and occupation dialogue | The same sound graph schema covers these families. Only recordings carrying an authored subtitle ID are OCR candidates. |
| Infolink radio and public-address announcements | Their authored sound paths retain these categories; filtering is already part of the original recording. No synthesized filter or substitute voice is applied. |
| In-engine cinematics | Speech uses the same authored sound graph and caption IDs. Its categorical label may remain ordinary dialogue when the resource itself does not distinguish a cinematic performance. |
| Pre-rendered cinematics, tutorial movies and endings | DRM movie definitions → exact `.usm` identity → named CRI voice track; explicit `(start_ms, end_ms, text_id)` movie timeline. Human/machine/ambivalent ending variants remain separate. The sound-effects/music track is not mistaken for a voice locale. |
| Making-of video | The original English extra has its own authored timeline and one multiplexed original audio track. Its 356 caption cues are supported for English; other selected languages do not receive English audio as their requested original voice. |
| Conversation wheel | Typed `Conversation_Choice` nodes → authored choice transitions → label and preview text IDs. These 907 text fields are confirmed unvoiced prompts. The response spoken after selection has its own separate sound binding. |
| Email and pocket-terminal correspondence | The email database explicitly identifies sender, recipient, subject and body text fields. Captured through the unvoiced toggle. |
| Ebooks, newspapers and other iReader prose | The iReader database explicitly identifies title/body text. Captured through the unvoiced toggle. |
| Mission log | Authored title/description fields are confirmed text-only. Captured through the unvoiced toggle. |
| Developer commentary and other speech without authored captions | Inventoried, but no OCR-to-recording binding is invented. English-only commentary has 280 stream definitions with no subtitle ID. |
| Unclassified interface, credits and other localization | Kept as `unknown`; absence of a discovered recording is not evidence of silence. |

Each authored `//(seconds)` subtitle page becomes a separate current-line
record. Valid page times trim the original performance. Empty timed pages
preserve authored gaps without becoming transcript lines. Movie page offsets
are relative to their explicit parent cue. A cue extending beyond an audio
stream ends at that stream's actual EOF. When page timing cannot establish a
valid cut, the exact original track remains playable and is explicitly marked
`playback_scope=full_track`, with a `_full_track` category suffix. Future
caption pages are never appended to the current displayed text.

Cross-language pages are aligned only when their authored page counts agree;
an unmatched translation paragraph is not substituted for a current page.
An individual movie subtitle ID can occur in multiple scene/ending variants,
which retain independent identities. The shared matcher must disambiguate
repeated text before selecting a recording.

Where a movie defines exactly one original voice per locale, its explicit
movie identity and locale establish the correspondence even when translated
source filenames differ. Multiple performances within one locale remain
separate variants rather than being assigned by track order.

Some movie definitions swap the numeric German/Italian labels. The reader
uses the exact authored locale-bearing WAV filename and exact CRI directory
filename, rather than assuming numeric track order. The PC menu tutorial's
documented filename alias removes its stale `_pc` suffix. The epilogue's two
identically named English streams are checked for byte-identical ADX data
before either can identify playback. These are inspected shipped cases,
not a generic filename or language fallback.

## Installed-file evidence

The installation contains 103,372 BIGFILE directory entries and 15,552 DRM
resources. Bounded section reads inspect relevant sound, movie and conversation
sections without unpacking unrelated textures to disk. The shared inventory
finds 19,137 sound definitions, 17,265 original voice stream bindings, 803
conversation graphs and 63 movie definitions.

The English snapshot contains **24,739** individual caption/text records:

- **12,240 voiced** records, including 703 timed cinematic captions,
  two cinematic pages with explicit full-track playback and 356 making-of
  captions.
- **4,074 confirmed unvoiced** records: 907 choice fields, 2,359 email fields,
  314 iReader fields and 494 mission-log fields.
- **12 unavailable** records: 11 authored caption IDs bind to multiple
  different recordings; one has two subtitle pages. These are not assigned an
  arbitrary performance.
- **8,413 unknown** records, excluded from voiced and unvoiced OCR matching.

The final native snapshots for all five languages have these counts. Counts
vary because each localization has its own authored caption pages.

| Locale | Total records | Voiced | Confirmed unvoiced | Unavailable | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| `en` | 24,739 | 12,240 | 4,074 | 12 | 8,413 |
| `fr` | 24,678 | 11,817 | 4,074 | 369 | 8,418 |
| `it` | 24,497 | 11,638 | 4,074 | 369 | 8,416 |
| `de` | 24,727 | 11,864 | 4,074 | 369 | 8,420 |
| `es-ES` | 24,559 | 11,698 | 4,074 | 369 | 8,418 |

The 369 unavailable records in each non-English snapshot comprise the same
12 ambiguous dialogue pages, 356 captions for the original English making-of
and one caption whose movie supplies only an English voice. These remain
unavailable for the selected language, not confirmed unvoiced.

There are 2,502 records with authored playback cuts. The movie definitions
provide 871 parent cues, including the making-of; two reference empty/missing
selected-language text. No movie cue is left without a traced resource
definition. Of 17,265 voice stream bindings, 7,029 carry no nonzero authored
subtitle ID. This includes commentary, non-subtitled performances and other
unclassified VO resources; it is not a claim that all are linguistic dialogue.

The final five-language indexing pass took about 41 seconds on the development
PC, reusing the common resource inventory across the five snapshots.
Timing is observational, not a performance guarantee. Private native indexes,
decoded samples and compact check evidence remain outside published artifacts.

## Screens, missing packs and verification limits

Use full-frame matching or independent calibrated regions for main subtitles,
HUD/Infolink dialogue, conversation wheels, terminal panels and iReader/media
screens. A single lower subtitle crop does not cover the game. The shared
unvoiced toggle governs confirmed choice/readable/log text; it does not enable
unknown or unavailable records. Live game capture, Windows DPI, zoom and
physical mobile OCR were not exercised by the archive/decoder probe and remain
separate UI acceptance checks.

All official locale schemas have synthetic fixtures, including missing text
and missing voice packs. Missing selected text raises an actionable preparation
error. Missing selected speech remains unavailable and directs the user to
Steam Properties → Language, completion of the download and file verification.
Files changing during preparation retain the prior snapshot. Extraction
revalidates the exact owner, sound/movie identity, caption, locale and media
binding against the installed resources.

The 20 focused tests cover BIGFILE/CDRM/DRM bounds, original-language selection,
MUL demux, CRI typed metadata, separate cinematic pages and timings, locale
tracks with deliberately shuffled numeric IDs, duplicate streams, choice
fields, unvoiced matching, missing packs, modified bindings and the local
decoder hook. Representative installed dialogue and cinematic recordings are
decoded and matched for each of the five supported locales. This is format and
native playback evidence; it does not claim exhaustive listening to every
recording or a live playthrough.

Additional native French dialogue and Spanish public-address stereo samples
decoded at 44.1 kHz with both channels and nonzero PCM. Their decoded lengths
were 192,384 and 4,777,344 frames respectively. The decoder hook validates each
channel's sample rate and length before interleaving the original left and
right channels; it does not synthesize or mix a substitute recording.

## Format research

The implementation is independently written from installed-file evidence and
these upstream format references; no external executable or unreviewed script
is needed at preparation time:

- [Gibbed BIGFILE v2](https://github.com/gibbed/Gibbed.CrystalDynamics/blob/master/projects/Gibbed.CrystalDynamics.FileFormats/BigArchiveFileV2.cs),
  [locale bits](https://github.com/gibbed/Gibbed.CrystalDynamics/blob/master/projects/Gibbed.CrystalDynamics.FileFormats/ArchiveLocale.cs),
  [CDRM blocks](https://github.com/gibbed/Gibbed.CrystalDynamics/blob/master/projects/Gibbed.CrystalDynamics.FileFormats/CompressedDrmFile.cs).
- [Gibbed DRM sections](https://github.com/gibbed/Gibbed.CrystalDynamics/blob/master/projects/Gibbed.DeusEx3.FileFormats/DRMFile.cs)
  and [MUL demux format](https://github.com/gibbed/Gibbed.CrystalDynamics/blob/master/projects/Gibbed.DeusEx3.Demux/Program.cs).
- [rrika DRM relocation research](https://github.com/rrika/dxhr/blob/main/tools/drm.py)
  and [typed section descriptions](https://github.com/rrika/dxhr/blob/main/tools/drmexplore.py).
- The existing toolkit CRI UTF reader supplies typed stream-directory decoding;
  the verified local vgmstream decoder handles original FSB4/ADX recordings.

No game transcripts, recordings, archive extracts, personal paths or account
data are included in public fixtures or documentation.
