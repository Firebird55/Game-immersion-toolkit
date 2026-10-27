# HEAVY RAIN narrative audit

Audited 2026-10-27 using the installed Windows game, its shipped metadata and
read-only publisher/developer references. No game files, account settings or
original companion data were changed. The installation has four archive indexes,
11,262 distinct scene containers, 2,350 embedded localization resources, 47,500
voice-bank entries and 31 Bink movies. Resource counts include repeated and
non-dialogue data; they are not independent subtitle totals.

## Presentations and limits

| Presentation | Installed evidence | Reader behavior and remaining gap |
| --- | --- | --- |
| Ordinary, branching and optional conversations | Typed scene dependency references, compact localization and locale-specific type-4091 performances | Exact authored identity, language, timing and original audio retained. Choices do not select a guessed spoken response. Branch reachability is not reconstructed. |
| Internal thoughts | Shipped presentation-name tables identify `THOUGHTS` localization resources | 1,063 original thought performances in each audited language, inventoried separately from conversation. Names are used only for categories, never for audio binding. |
| Thought and conversation prompts | Nonempty compact rows with text flag 2 and explicit null voice references | 1,474 English and 1,476 Dutch prompts are certified unvoiced. The opt-in capture path reads exact text without uploading or playing invented audio. Repeated short prompts may remain ambiguous. |
| Simultaneous speakers and moving/paginated captions | Authored paragraphs, page separators and separate original performances | Existing context/paragraph matching is preserved. A page identifies its whole authored performance, not an inferred audio cut. Complete native layout coverage is not established by this audit. |
| In-engine cinematics, television/radio and phone dialogue | Scene-localized dialogue and original performance references | Included when represented by the supported typed scene/localization format. Their individual scene roles are not all separately classified. |
| Prerendered cinematics | 31 installed Bink files, including chapter transitions, endings, credits, trailers and making-of videos | Inventoried separately. No verified locale-track/cue join was established; whole movies are never substituted for a line's original voice. |
| Letters, newspapers, notebooks and environmental text | Authored letter/readable voiceovers and corresponding thought resources are present | Voiced reading remains part of the normal bound performances. Independent prop/image text has no verified schema and is not automatically treated as silent dialogue. |
| Menus, chapter labels and regional/demo resources | Eleven standalone expanded-format localization identities, repeated across startup/story indexes | Audited separately from compact scene dialogue and excluded from capture. Their header integers are big-endian while the expanded strings are UTF-16LE; this is distinct from compact UTF-16BE pools. |
| Comics, image-only panels and nonverbal vocalizations | No independent comic-dialogue table was identified; nonverbal resources also exist | No blanket comic support claim. Sound without authored subtitle text cannot supply a transcript. |

The publisher describes branching decisions, four playable perspectives and
cinematic storytelling, and lists ten voice languages separately from subtitle
languages. Those descriptions guide the inventory; they do not prove that every
presentation has an extractable text/audio mapping.

## Update and voice safety

Reader revision 2 retains explicit `voice_status` and `dialogue_kind` metadata.
Compact flag-2 rows with null references are distinguishable from undeclared or
unresolved voice pointers. A generic null reference, a missing pack, or a failed
audio read never certifies silence. Missing authored performances remain visible
as unavailable records with a warning instead of being discarded.

Required archive/schema changes produce `unsupported_game_format` with an
update-and-verify action. A changing installation produces `game_files_changed`.
The fingerprint includes archive parts and optional presentation-name tables.
An unreadable optional name table degrades category detail with a warning while
verified subtitle/audio bindings remain usable. It cannot redirect a voice.
The name reader bounds file size, row count, name length, schema version and
trailing data. Existing bounded raw-deflate, pointer, timing, duplicate-bank and
locale checks remain in place.

## Verification

Fresh native preparation produced:

| Source | Total entries | Verified original voices | Verified unvoiced prompts | Thoughts within voiced total |
| --- | ---: | ---: | ---: | ---: |
| English | 5,029 | 3,555 | 1,474 | 1,063 |
| Dutch | 5,032 | 3,556 | 1,476 | 1,063 |

Both runs requested official Simplified Chinese translations. The two native
runs took 47.52 seconds in total. Four bounded production audio probes—one
conversation and one thought in each language—decoded to non-silent PCM WAV
with durations of 10, 6, 10 and 4 seconds. These checks validate installed
references and decoding, not replay of the whole game.

Thirty-eight focused synthetic regressions passed, including the existing ten
voice-locale cases and caption safeguards. New cases cover explicit null versus
unresolved pointers, silent prompts versus missing audio, optional name-table
degradation, fingerprint changes and actionable unknown-patch errors. See
[adapter tests](../../backend/tests/test_heavy_rain_assets.py) and
[audit regressions](../../backend/tests/test_heavyrain_audit.py).
Private aggregate evidence, timings and temporary decoded runs remain under
ignored `output/checks/heavyrain-audit/`.

The earlier [gameplay coverage record](../heavy-rain-support.md) remains the
source for its limited English prologue replay evidence. This audit did not add
native playthrough, other-language footage, physical mobile or full chapter,
ending, movie and alternate-branch acceptance. No proprietary text or media is
included in the public tests or report.

## Primary references

- [Quantic Dream's official PC game and language specification](https://www.quanticdream.com/en/heavy-rain).
- [Quantic Dream: 15 years of Heavy Rain](https://blog.quanticdream.com/15-years-of-heavy-rain/), describing branching narrative, performance capture and cinematic direction.
- [PlayStation's interview with writer/director David Cage](https://blog.playstation.com/2009/05/22/heavy-rain-your-questions-answered/), covering the developer's contextual gameplay presentation.
- Installed `DC_INFO`, `LOCALIZ_`, `PARTITIO`, `TBOFFSET` and optional presentation-name tables are the direct schema evidence. They are inspected locally and not redistributed.
