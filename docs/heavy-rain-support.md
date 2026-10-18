# HEAVY RAIN

Select the installed PC game in Setup, choose a learning language under
**Languages**, and explicitly prepare its lookup table. The reader supports
English, French, Italian, German, Spanish (Spain), Dutch, Japanese, Polish,
Portuguese (Portugal) and Russian with their installed original performances.
Select matching spoken audio in the game. Official text in other languages,
including Simplified and Traditional Chinese, can supply aligned sentence
translations. The translation target comes from that learning language's
Lexirise settings. Missing official translations remain unavailable.

The reader uses typed localization and language-specific FlowDialog references
from the startup and story archives, plus both official LanguageData banks.
It checks duplicate voice-bank identities, authored partition offsets and
subtitle times. Big-endian raw-deflate metadata is read in bounded ranges.
Facial data is excluded from audio; original silent blocks retain their timing.
Authored page separators provide OCR anchors for one complete paragraph and
performance. They do not imply matching page boundaries in another language.
Unknown patch archives require verification rather than guessed priority.

The game also paginates some paragraphs at runtime. Long exact caption pages
can resolve a unique complete paragraph; they retain its full original audio
and official translation. Short repeated captions require an independently
confirmed caption from the same authored localization group. This context
expires after twelve seconds and clears across account, language, index,
window, calibration, menu and capture-state changes. Ambiguity within that
group remains unresolved. Overlapping speakers confirm and store their own
performances independently. Document text above the subtitle lane is excluded.

The tested installation contains 3,556 mapped Dutch performances, with 3,555
aligned Simplified Chinese paragraphs. All 3,556 Dutch originals pass actual
audio decoding. Installed mapping checks also cover all ten supported voice
languages. These are asset checks, separate from gameplay capture acceptance.
One original performance in each other voice locale also passes decoding.
Synthetic OCR regressions cover all ten locales at 720p, 1080p and 4K, with
ordinary and wrapped layouts. Synthetic Chinese pages resolve Dutch study
text and original audio using the full Dutch/Chinese table with no English
table. These are synthetic tests, not native gameplay recordings.
Synthetic regression resources contain no game assets or account information.

The [footage manifest](../backend/tests/fixtures/heavy-rain-video-ocr.json)
lists all 73 installed chapter/epilogue labels and their coverage status.
The English PC recording from 00:00–04:00 and 15:00–17:00 covers the opening
menu and movement negatives, internal thought, a letter voiceover, ordinary
family dialogue, overlapping speakers, a brief reply, runtime paragraph pages
and QTE instructions/glyphs. Sixteen independently annotated original
performance identities pass production cropping, OneOCR, matching,
confirmation, deduplication and SQLite storage at a 250-ms frame cadence.
All tested negative text stays out of the transcript. Complete paragraphs and
repeated calls can share one captured original performance.

The recording is 1080p. Resized replay tests do not establish native 720p or
4K game coverage. The gaps between the tested prologue segments, every later
chapter, alternate branch, optional scene, ending, DLC and subtitle presentation
without explicit replay evidence remain untested. Dutch gameplay footage,
other language-specific footage, physical mobile capture and mobile gameplay
OCR acceptance remain pending. Desktop/mobile Chromium and Firefox checks use
synthetic libraries, mocked account operations and reading layouts; they do
not establish complete gameplay coverage. Full-game acceptance is incomplete.
Recordings, local indexes and account diagnostics are never distributed.
