# BEYOND: Two Souls

Choose the installed Steam folder in Setup, select the original spoken
language you are learning, then explicitly prepare that learning language in
**Languages**. Steam downloads additional original voice packs when its game
language changes. Wait for that download to finish before preparation.
The game may display the prepared official translation language instead: for
example, Chinese subtitles can match the Chinese table while the companion
shows Dutch study text and plays its original Dutch performance.

The reader recognizes English, French, Italian, German, Spanish (Spain), Dutch,
Japanese, Polish, Portuguese (Portugal), Portuguese (Brazil), Russian and Spanish
(Latin America). Each requires its actual installed voice pack. Chinese is an
official sentence-translation target, not a spoken learning language for this
game. Other official text targets are available when their aligned text exists.
The account's effective target is resolved separately for its learning language.

Text comes from authored localization identities. Original speech requires a
typed FlowDialog reference, a matching language and a real installed partition.
Partition offsets bound extraction; facial-animation bytes are excluded. Silent
partitions retain their original time. Numbered or explicit time cues select
audio only when their authored timing table agrees. Some shipped paragraphs
have different numbers of text pages and audio time pairs; those retain the
complete original performance and individual official OCR anchors. They are
not assigned guessed per-page audio cuts. Ambiguous repeated performances
remain unmatched.

An ambiguous short caption can be collected with its following authored cue
when both belong to the same original performance and have verified timings.
The record contains both official texts and their original audio range. A
continuation that is itself ambiguous requires the preceding caption to have
been observed and confirmed; context expires and clears across account,
window, calibration and language changes. Other performances retain their
ambiguity rather than inheriting a misleading unique match. Context never
combines different speakers or invents a missing sentence translation.

The default crop includes wider captions near the screen edges. Existing
saved calibration remains in effect. A reliable match for a complete wrapped
caption takes precedence over an isolated phrase from that caption.
Overlapping speakers confirm independently, so a longer foreground caption
cannot hide a brief background reply. Each accepted performance queues its
own original asset. Wrapped fragments and ambiguous performances remain
excluded, and pending confirmations clear across account or capture changes.
The mobile catalog worker follows the same matching and confirmation behavior.

Dutch asset validation found 5,446 records with 2,777 distinct original
performances, including 5,437 aligned Simplified Chinese records. Missing target
text remains unavailable. These counts describe the tested installation, not
an exhaustive gameplay-coverage claim. Original game data and account
diagnostics remain private and are never distributed.

Installed English asset validation found 6,212 records covering the same count
of distinct original performances. Both installed voice sets pass decoding of
all 2,777 mapped performances. MPEG-1 Layer III streams retain their actual
32, 44.1 or 48 kHz frame rate during validation, then resample to the shared WAV
rate while preserving authored silent partitions. Other voice packs still need
installation-specific validation; synthetic locale fixtures are separate evidence.

The checked-in [replay manifest](../backend/tests/fixtures/beyond-video-ocr.json)
records the tested opening segments and the untested archive/chapter groups.
The English PC recording from 00:00 to 04:00 covers opening narration, the
police cutscene, a phone intercut, letterboxing, brief and wrapped subtitles,
an initial menu negative, and uniform labels that must not become dialogue.
All thirteen independently annotated authored cue identities pass
production cropping, OneOCR, matching, confirmation, deduplication and SQLite
storage at four frames per second. A context record can cover two annotated
cues. Replay reports preserve both the captured record IDs and authored cue
IDs, expected events, misses, incorrect captures, chapter, branch and source
timestamps. The original recording is 1080p; 720p and 4K
runs resize that recording and do not establish native-resolution coverage.
An additional 04:00–06:00 segment passes at the recording's 1080p size. Its
seven manually annotated caption appearances cover four authored performances,
including one complete performance with four subtitle pages. Chapter titles and
movement prompts do not become dialogue. Resized replay of this additional
segment remains untested.
The 06:00–08:00 laboratory corridor and start of the card experiment also pass
at the recording's 1080p size. Twenty-seven independently annotated caption
appearances map to eighteen authored cue identities and seventeen stored
performances, with no misses or incorrect captures. These include simultaneous
foreground/background speakers, brief greetings, wrapped instructions and
paragraph pages. Card symbols, device numerals, clothing/badge lettering and
unspoken LOOK/MOVE prompts stay out of the transcript. This segment exposed
three missed overlapping cues; independent confirmation fixes all three.
Resized 720p and 4K replay also pass for this segment. Those runs retain the
recording's layout and do not establish native-resolution game coverage.
Chinese caption sequences also pass synthetic native OCR checks with Dutch
study text, official Chinese translation and extracted original Dutch audio.
Those synthetic checks are separate from the English gameplay evidence.

All footage after 08:00, including the remainder of the card experiment and
childhood chapter, every later chapter, alternate branch,
optional scene, ending, DLC, and subtitle presentation absent from those
segments remain untested. Dutch gameplay footage
and language-specific footage outside English are not covered by that replay.
Synthetic format regressions cover all twelve voice locales; they are distinct
from installed Dutch asset checks and actual gameplay evidence. Mobile carries
explicit study/translation/audio languages, but mobile OCR footage acceptance
is still pending. Full-game capture acceptance is **incomplete**.

Reader format research: [Quantic BigFile format](https://github.com/Ekey/QD.BIG.Tool)
and [BEYOND subtitle/audio research](https://hugo.fyi/projects/reverse-engineering-b2s).
No extractor implementation, assets or recordings from those sources are bundled.

## Short OCR interruptions

BEYOND now retains a pending caption across one missed scan for up to 750 ms.
It still requires two agreeing observations; menu transitions and longer gaps
reset confirmation. An exact first observation also requests a prompt rescan.

The opening 120-second recorded fixture was replayed through native desktop OCR
at 1920 × 1080 and four frames per second: six expected authored lines, six
captured, no incorrect lines. Separate regression fixtures cover overlapping
speakers, wrapped captions, short dropouts and stale candidates. This does not
extend the documented chapter coverage or guarantee every live subtitle.
