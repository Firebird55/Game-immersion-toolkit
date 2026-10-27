# PRAGMATA dialogue coverage audit

Audit date: 2026-10-27. Scope: read-only installed PC metadata and selected
Mandarin voice decoding, plus primary-source research. No game files,
transcripts, recordings, personal paths or account data belong in this report.

## What the game presents

The Shelter includes progress-dependent conversations, REM interactions,
hide-and-seek, drawings, Cabin services, readable Data Library files and a Bot
Database. Mini-Cabin collectibles also make audible calls. These are distinct
coverage cases, not just main-story subtitles. See the first-hand
[PlayStation Shelter guide](https://blog.playstation.com/2026/04/13/pragmata-all-the-ways-the-shelter-expands-gameplay-and-story/).

First-hand previews describe a conversation-triggered drawing cutscene and a
hacking prompt during a boss cutscene. Therefore, transitions between dialogue,
interactive gameplay and cinematics require separate capture checks. See
[Xbox Wire's hands-on report](https://news.xbox.com/en-us/2026/03/18/pragmata-hands-on-preview-boss-weapons/)
and [PlayStation's hands-on report](https://blog.playstation.com/2026/03/17/pragmata-hands-on-report-hack-and-blast-through-a-futuristic-city/).

These sources establish presentation types. They do not establish a particular
local asset's text-to-voice mapping, every subtitle's visibility, or silence.

## Installed inventory after the fixes

The private probe read 112 MSG v23 tables, 46 TMLFSM2 version 42091004 timelines
and 99 installed Wwise version 150 localized bank headers. This audit used
Simplified Chinese study text with English translations. Counts are records,
not distinct sentences, and can include dormant content in installed tables.
Category names below follow authored file families; they are not observations
of every line playing in the game.

| Category | Indexed records | Verified voice bindings | Known voice unavailable | Voice unknown |
| --- | ---: | ---: | ---: | ---: |
| Conversation: stages, Shelter, REMs and shop | 2,309 | 2,305 | 4 | 0 |
| Combat | 481 | 481 | 0 | 0 |
| Ambient and gimmick chatter | 301 | 301 | 0 | 0 |
| Spoken stage guidance | 297 | 292 | 5 | 0 |
| Cinematic subtitles | 511 | 448 | 48 | 15 |
| Narrative reading pages | 238 | 0 | 0 | 238 |
| **Total** | **4,137** | **3,827** | **57** | **253** |

The 3,827 bindings comprise 3,340 exact SoundID mappings, 39 authored fixed
layer mappings and 448 timeline-GUID intervals. Zero records are asserted to be
unvoiced: absence of a supported binding is insufficient evidence of silence.
Unknown reading pages are retained for inventory and must not be enabled by a
capture-unvoiced toggle as if their voice status were established.

The reading inventory contains 71 Data Library/shop bodies, 79 stage-file
bodies, 11 wall-file bodies, 31 Bot Database descriptions and 46 archived
conversation/hologram transcript pages. The latter are composed from authored
references to dialogue and character names. A transcript page is not assigned
a constituent line's audio or an invented concatenation.

## Defects corrected

- Preparation formerly selected only bank names ending in `dialogue`. Earth,
  later-chapter and common voice banks use other names. Selecting the chosen
  locale's bounded bank headers recovered **119 exact voice bindings**, from
  3,708 to 3,827. It does not eagerly extract all voice packages.
- Archive narrative bodies were excluded. Both index paths now retain the
  allowlisted bodies, resolve nested speaker references, and reject whole
  entries with missing, conflicting or cyclic references.
- The legacy index could borrow a performance from another ID with equal text
  and speaker. That fallback is removed, old alias audio is rejected while
  refresh is pending, and conflicting cinematic intervals remain unresolved.
- Each record carries a presentation category and an explicit voice status.
  A bare MSG SoundID is not proof of speech: UI and credits also have IDs.
  Known voice status requires a voice-graph trigger or matching cinematic
  subtitle GUID with a known dialogue bank.

## Remaining gaps and exclusions

Forty-seven cinematic rows have authored intervals but no requested Mandarin
bank header in this installation: `cs0260`, `cs0840`, `cs0920` and `cs0940`.
A targeted read across base, sub and patch archives recovered their timelines
but not those bank headers. The public graph naming a bank does not prove it is
installed. Ten other known voice references remain unresolved across stage
dialogue, guidance and one cinematic row; they are not silent dialogue.

Fifteen cinematic rows have no verified voice evidence, including entries in
`cs6010` and `cs6030`. Their presence in MSG tables does not prove that a player
can trigger them. Do not infer their voices from neighboring entries, similar
sentences or a public trailer.

Generic menus, inventory/weapon descriptions, tutorial panels, objective labels,
credits, rejected development strings and sound-effect/nonverbal captions are
excluded from dialogue. Spoken advice in `conv_stagetips` is covered separately
from tutorial UI. No dedicated branching-choice family or proof of intentionally
silent spoken dialogue was established. Mini-Cabin calls without authored
subtitle identity, movie-only text, and any new asset formats remain unverified.

## Verification and outstanding acceptance

Thirty-one focused synthetic tests passed, covering localized bank identity,
nonstandard bank selection, missing-bank status, exact-only voice association,
legacy alias rejection, nested/cyclic references, readable/UI separation,
nonverbal captions, timeline parsing, fixed layers and strict legacy loading.

Two newly recovered exact bindings, from `ch01000_earth` and `ch05000_chp7`,
decoded through the production lazy extraction service to non-silent audio
(approximately 2.58 and 1.64 seconds). This proves package lookup and decoding
for those samples; it is not a listening comparison, exhaustive playback test
or live subtitle/voice synchronization test. Raw evidence stays under ignored
`output/checks/game-readiness-probe/`.

Still required for a complete gameplay claim: independently annotated gameplay
and cinematic screenshot sequences; Shelter/REM/hide-and-seek transitions;
speaker/nameplate handling; guidance over combat; archive pagination and
scrolling; subtitle options; missing-pack behavior; other selected dubs; Windows
DPI/capture bounds; desktop/mobile Shadow DOM readers in Chromium and Firefox.
No physical gameplay capture or device session was performed by this audit.
