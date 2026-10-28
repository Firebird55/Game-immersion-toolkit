# Dialogue coverage and game-update resilience

Each game below received a separate audit of installed files and public primary
sources in October 2026. Reports distinguish authored text, verified original
voices, confirmed unvoiced content, missing voices and unresolved formats.
Counts refer to the audited installation and locale, not every game chapter.

| Game | Implemented improvements | Evidence and limits |
| --- | --- | --- |
| Zenless Zone Zero | Unity-wrapped catalogs; typed stories, bubbles, cinematics, messages and gameplay tips | [ZZZ](zzz.md) |
| Wuthering Waves | Redirected localization shards; conversations, choices, messages, readables and movie captions | [Wuthering](wuwa.md) |
| Neverness to Everness | Typed subtitles; mail, summaries and messages; original voice provenance | [NTE](nte.md) |
| PRAGMATA | Bounded selective extraction; additional voice banks; narrative reading inventory | [PRAGMATA](pragmata.md) |
| Cyberpunk 2077 | Base game and Phantom Liberty; exact hashed voices; journal messages and readables | [Cyberpunk](cyberpunk.md) |
| The Witcher 3: Wild Hunt | Legacy/current bundles; authored choices, journals, profiles and readable body keys | [Witcher](witcher3.md) |
| Honkai: Star Rail | Messages, choices, narrated story and combat metadata; explicit voice states | [Star Rail](starrail.md) |
| Genshin Impact | Dialogue fallback, reminders, card dialogue and book paragraphs; version checks | [Genshin](genshin.md) |
| Arknights: Endfield | Conversations, choices, panels, messages, readables and operator archives | [Endfield](endfield.md) |
| Rise of the Tomb Raider | TIGER archives; authored subtitle and FMOD voice bindings; regional and DLC languages | [Rise](rise-tomb-raider.md) |
| Shadow of the Tomb Raider | TIGER archives; Wwise subtitle labels, cinematic timing and collectible narration | [Shadow](shadow-tomb-raider.md) |
| BEYOND: Two Souls | Explicit chapter choices; missing-performance inventory; faster repeated-performance validation | [BEYOND](beyond.md) |
| HEAVY RAIN | Explicit silent prompts; thought categorization; retained missing-voice records | [HEAVY RAIN](heavyrain.md) |
| Spyro Reignited Trilogy | All three games; localized dialogue tables, Wwise events, cinematic pages and explicit text-only dialogue | [Spyro](spyro.md) |
| Detroit: Become Human | Timed original performances, branching dialogue, choices, observations and magazine/news text | [Detroit](detroit.md) |

## Capture unvoiced dialogue

In **Capture setup**, enable **Include unvoiced dialogue**. It is off by default
and applies to every supported desktop game reader. Only authored silence or a
confirmed text-only presentation qualifies. Messages, choices and pages may be
outside the subtitle crop, so the enabled mode also scans the captured game
window for exact text-only matches. It requires stable observations and
deduplicates overlapping capture regions.

Missing packs, unresolved audio, unsupported formats and unknown voice status
do not count as silence. For example, PRAGMATA reading pages whose voice status
remains unknown are inventoried but not enabled by this toggle. See each report
before assuming a presentation is covered. OCR can still miss incomplete,
moving, obscured or unusually laid-out text; physical gameplay acceptance is
separate from file and synthetic tests.

Confirmed silent entries are labeled **Unvoiced dialogue**, can be favorited,
and can be saved as text-only Lexirise sentences. They never receive substitute
audio. Turning the option off preserves history. Paired phones can read the
desktop transcript; independent offline mobile OCR libraries retain their
existing voiced-catalog behavior in this release.

**Settings → Games & Languages → Dialogue coverage** separates presentations
and four voice states. Warnings identify unsupported or unresolved content.

## After a game update

Explicitly requested and prepared languages are checked in the background,
including games that are not running. First-time language choice remains
explicit; the toolkit does not guess account preferences or install every voice
pack. Requests survive failure and restart, duplicate work is coalesced,
progress names the current stage, and metadata outages back off before retry.

Fingerprints include relevant game/configuration manifests and voice data.
Reader revisions invalidate snapshots after adapter changes. Bounded, typed
readers reject recognized unsupported layouts with actionable errors and retain
the previous complete table. An arbitrary future binary format may still need
a toolkit update; unresolved records and warnings preserve that distinction.

Shared regression coverage exercises schema drift, malformed tables, missing
packs, cancelled workers, retained snapshots, retries, original voice ownership
and the unvoiced toggle. Tests remain in the repository because local checks and
GitHub Actions execute the same sources. Reports distinguish native probes from
remaining acceptance work without claiming full playthroughs.
