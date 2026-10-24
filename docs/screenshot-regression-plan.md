# Screenshot and mobile-package regression plan

Status: **proposed infrastructure; not implemented by this documentation PR**.
This is the acceptance contract for R01, R07a/R07b and R11 in the
[rework roadmap](rework-roadmap.md). It also informs the test review in R25.
Use screenshots, including small ordered screenshot sequences when necessary.
Downloading or playing YouTube videos is not a required CI dependency.

## Two complementary kinds of coverage

1. **Game-specific presentation regressions.** Find layouts that the ordinary
   subtitle lane does not cover, collect representative screenshots, annotate
   the expected behavior and preserve each confirmed fix with a regression.
2. **Sampled language combinations.** Exercise a few explicitly selected,
   supported combinations through the same mobile-package path. Do not build
   the Cartesian product of games, languages, browsers and resolutions.

A language sample does not establish presentation coverage for a game. A comic
test does not establish every language pair. Report both dimensions separately.
Every supported game belongs in the coverage inventory; no game gets priority
just because it already has more custom code or readily available fixtures.
Choose the next case by a reported failure, a distinct untested layout or script,
user impact and the cost of obtaining useful evidence.

## Inventory and screenshot collection

Start from the capability catalog, current adapters and
[known presentations](game-ocr-presentations.md). These are investigation leads,
not claims that every listed presentation is currently broken:

| Game or group | Presentations and boundaries to inspect |
| --- | --- |
| ZZZ | Light/dark comic bubbles, simultaneous bubbles, scrolling fragments, ordinary subtitles and player voice variants; preserve the existing multi-bubble implementation |
| Cyberpunk 2077 | Overhead NPC conversations versus main subtitles, overlapping speakers and response-menu negatives |
| The Witcher 3 | Top-edge NPC chatter, normal subtitles, supported dual-subtitle layouts and HUD/Gwent negatives |
| Wuthering Waves | Centered story cards, ordinary captions and the optional top-right channel; an experimental channel remains experimental |
| NTE | Wrapped/walking dialogue, radio/movie captions, introduction cards and player variants |
| Honkai Impact 3rd | Legacy/right and centered/light panels, multi-page dialogue, tutorial and combat negatives |
| Heavy Rain / Beyond | Context-dependent short lines, page fragments, simultaneous lines and branch/voice identity |
| PRAGMATA and every other active adapter | Inspect actual presentation types and current capability limits; record missing screenshots explicitly rather than assuming the generic subtitle case is sufficient |

R01 enumerates the actual active game IDs from the current capability catalog;
the final row is not permission to leave those games out of the inventory.
Retired or unsupported adapters retain their preservation tests without acquiring
new support claims. Track each distinct presentation as `uninspected`,
`awaiting-input`, `annotated`, `failing`, `passing` or `unsupported`, with an owner,
evidence reference and the applicable desktop/mobile route. A passing fixture
does not erase other open presentations for that game.

For a suspected gap:

1. Obtain the original screenshot at its known resolution and subtitle settings.
   Record the game/patch, source and usage permission. A YouTube page may help
   locate a scene; take permitted fixed screenshots with source timestamps instead
   of making live playback part of the test. Do not scrape arbitrary media in CI.
2. Include a positive case and the nearest useful negative, such as a response
   menu, HUD label, unrelated short word, ambiguous voice or missing catalog entry.
3. Annotate regions, visible text, expected catalog identity and allowed outputs
   independently of the current recognizer. Cross-check source/translation/voice
   identities against the package. Never generate expected results by accepting
   the application's current output.
4. Reproduce the failure through the affected production route. Keep the case
   when fixing it; a generic synthetic layout alone cannot close a real-scene gap.
5. Record both the real-scene result and any authored public reproduction. The
   reproduction protects the algorithm but is not additional real-game evidence.

Preserve source dimensions and distinguish native screenshots from resized
variants. Test only resolutions/crops relevant to the bug. Upscaling one image
does not establish a new native-resolution layout.

## Fixture contract

Use one small versioned manifest schema for all games and package adapters.
The schema and runner names below describe required behavior, not existing CLI
options. Keep schema/loader validation focused on failures that could invalidate
the result; do not create a new fixture framework for each game.

| Field group | Required information |
| --- | --- |
| Identity and provenance | Fixture ID/version, game/patch, presentation, source reference, rights/distribution classification and image SHA-256 |
| Image input | Dimensions, crop/calibration, subtitle settings, source frame ID and ordered observation IDs/times when used as a sequence |
| Languages | On-screen subtitle/OCR locale, study/source locale, translation target, audio locale and player variant if applicable; these are independent fields |
| Package binding | Package manifest/schema version and digest, catalog digest, selected locales, expected catalog IDs and voice identities or explicit no-voice state |
| Expectations | Required matches, permitted missing translations/audio, forbidden matches, ambiguity/no-match expectations and permitted normalization |
| Temporal expectations | Expected occurrences, confirmation, duplicate suppression and order or explicit unknown order; only present when the input supplies that evidence |
| Execution | Production route, engine/model and hash, chosen browser/host, fixture tier, reason for selection and runtime budget |

Never put personal paths, access tokens, account diagnostics or private download
URLs in the tracked manifest. Private bindings and annotations stay in an ignored
local sidecar; public fixture IDs use authored data. A package is test input, not
executable code: validate ZIP paths, sizes, schema and hashes before reading it.

## Sample a few language combinations

Start with **three to five deterministic combinations across the pilot corpus**,
then rotate or replace the supplemental sample when it adds useful coverage.
Known bug regressions remain pinned. This is a starting scope, not a promise
that every game supports these example pairs:

| Example source/study → translation | Reason to consider it |
| --- | --- |
| Simplified Chinese → English | Han text and a Latin-script translation |
| Japanese → English | Kana/kanji and different tokenization |
| Dutch → Simplified Chinese | Latin source and Han translation, where supported |
| Traditional Chinese → a verified target | Script distinction, when the game/package provides that locale |

Select actual pairs from verified reader and package capabilities. Do not create
a fictional pair to fill a matrix slot. Record unavailable pairs explicitly;
neither a storefront language checkmark nor a browser `locale` setting proves
that an official catalog, translation or voice binding exists.

At least one sample should distinguish subtitle locale from study/voice locale
where the product supports it. Also cover a missing target and a mismatched or
unprepared package without falling back to another language. A small mocked
account case checks per-language effective translation targets, including a
different global target; real account writes are never part of the matrix.

Select one main browser for real OCR samples; use a small representative smoke
case on the other relevant engines. Expand only for a browser-specific defect
or a changed integration boundary. Do not multiply every screenshot by every
engine, resolution and language. Record the exact chosen cases and the selection
reason so the same commit and fixture version reproduce the same run.

## Exercise the package and production path

Build the mobile artifact once for the exact tested commit. Load it from an
isolated test server and use the normal file-import path to open a small mobile
ZIP containing a catalog and, where needed, owned test audio. Do not replace
the package reader with a hand-built in-memory catalog in the end-to-end lane.

The primary path is:

```text
versioned screenshot + actual-format mobile ZIP
  -> normal package import and locale selection
  -> production frame/crop processing and real browser OCR
  -> production game-specific matching and confirmation
  -> transcript identity, translation and voice binding
  -> normal reader, storage and manual playback
```

R07a initially drives the existing production page with controlled frame input.
R13c extracts the same mobile controller only after this characterization.
R07b then injects screenshots, clock and I/O into that controller; it must not
maintain a second matching, confirmation or publication loop. Assert route
selection for each applicable game-specific path, including ZZZ's special path.

Check the expected line and translation, the voice identity/locale (or explicit
unavailable state), and the absence of forbidden outputs. A minimal audio smoke
case checks decoding and user-initiated playback; a synthetic tone does not
prove an original game performance. Reopening the package, offline reuse and
restored history/voice references each need one representative scenario unless
the change affects more cases. Test malformed, mismatched and incomplete inputs
at the lowest useful layer, preserving an already working library on failure.

Keep two evidence lanes distinct:

- **Real image OCR:** actual pixels and pinned OCR models through the shipped
  pipeline. Assert required/forbidden results and matching identity; report
  missing lines as failures, not merely a low score or an empty successful run.
- **Controlled temporal behavior:** ordered screenshots/observations and a fake
  clock exercise late results, scrolling, confirmation, repetition and source
  switches cheaply. Injected OCR is allowed here but must be labelled; it does
  not establish OCR accuracy. Reusing one screenshot to simulate persistence
  does not establish real-world chronology. Duplicate delivery of the same
  observation is not a new sighting; separate observations may have identical pixels.

A single screenshot can establish simultaneous visible content, not speaking
order or end-to-end latency. Use independent sequence annotations for temporal
claims; if the order is unknown, preserve it as unknown in display, storage and
paired-PC transfer. Performance runs are targeted measurements in R02a, not a
mandatory benchmark attached to every screenshot test.

## GitHub execution and private inputs

GitHub-hosted Actions can execute this browser pipeline and publish sanitized
results for an exact commit. The required public lane uses authored screenshots,
minimal synthetic packages and owned tones. These can run on pull requests with
read-only repository permissions and no account credentials. Test Windows for
the supported desktop environment and macOS/WebKit only for relevant mobile
browser behavior. **Do not add Linux product/browser test jobs.**

The real ZZZ package referenced in the owner's PR review is an initial input
candidate, not a verified fixture or a reason to prioritize ZZZ. R01 must inspect
its accessibility, format, locales, size and bindings before selecting usable
screenshots. It has not been downloaded or validated by this documentation
change. Later real packages use the same interface for every supported game;
another available package may be used first if it better covers a known gap.

Existing repository rules keep extracted libraries, original audio, private
screenshots and recordings out of Git, Pages, release assets and public test
artifacts. A shared Drive/YouTube link does not by itself grant redistribution.
Use the same runner locally for private package/screenshot validation by default.
That is genuine package coverage, but report it separately from hosted CI.

A real-input hosted run is optional and conditional: the input must be approved
for that processing, retrievable without adding personal credentials to workflow
secrets, and executed against trusted reviewed code. Use an explicitly selected,
digest-pinned input source, temporary runner storage and a bounded download.
Do not let fork code choose private inputs or use `pull_request_target` to run
untrusted code with privileged access. Never upload/cache the package, images,
OCR text, traces or raw failure screenshots from this lane; allowlist only
sanitized aggregate results and clean temporary inputs on completion. Without
these conditions, run it locally and report hosted real-input validation as
unavailable. Do not silently substitute synthetic results for the real package.

For public synthetic cases, retain bounded failure screenshots and diagnostics
as Actions artifacts, separate from the Pages publication allowlist. Reports
identify commit, artifact/package/corpus digests, exact sample, model versions,
route/browser/host, elapsed time and `pass`, `fail`, `not run` or `unavailable`.
Do not embed private resource links in logs or job summaries.

## Acceptance and cost

- R01 delivers the inventory, a few annotated samples, a package-input contract
  and independent expected results; it does not need the recognizer to pass yet.
- R07a/R07b prove that the harness calls production routes and detects a wrong
  identity, omitted required line, duplicate/stale event and incorrect locale.
  Use targeted fault examples, not an unrestricted mutation-testing campaign.
- R11 executes the selected game-presentation regressions plus the small language
  sample through the packaged app. Preserve failures and missing input as open
  coverage; close only cases with evidence. Full coverage of every game/language
  combination is not an acceptance condition.
- R25 reviews the cost and unique failure caught by each existing/new test.
  Share corpus loading, build and model setup; select affected cases in PRs and
  a bounded rotating sample in manual/candidate runs. Avoid repeating the same
  expensive suite in unit, browser, Pages and release jobs for one commit.
- Record baseline and changed wall-clock timings in ignored `output/checks/`.
  Set a measured job budget before expanding the corpus; no unsupported speed
  claim or arbitrary test-count target. Native Windows capture/OCR installation
  and physical iPhone/iPad behavior remain separate acceptance checks.
