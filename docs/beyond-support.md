# BEYOND: Two Souls

Choose the installed Steam folder in Setup, select the same spoken and subtitle
language in the game, then explicitly prepare that learning language in
**Languages**. Steam downloads additional original voice packs when its game
language changes. Wait for that download to finish before preparation.

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

Dutch asset validation found 5,446 records with 2,777 distinct original
performances, including 5,437 aligned Simplified Chinese records. Missing target
text remains unavailable. These counts describe the tested installation, not
an exhaustive gameplay-coverage claim. Original game data and account
diagnostics remain private and are never distributed.

The checked-in [replay manifest](../backend/tests/fixtures/beyond-video-ocr.json)
records the tested opening segment and the untested archive/chapter groups.
The English PC recording from 00:00 to 02:00 covers opening narration, the
police cutscene, letterboxing, brief and wrapped subtitles, and an initial menu
negative. All six independently annotated original-performance identities pass
production cropping, OneOCR, matching, confirmation, deduplication and SQLite
storage at four frames per second. The native recording is 1080p; 720p and 4K
runs resize that recording and do not establish native-resolution coverage.

Every later chapter, alternate branch, optional scene, ending, DLC, and subtitle
presentation absent from that segment remains untested. Dutch gameplay footage
and language-specific footage outside English are not covered by that replay.
Synthetic format regressions cover all twelve voice locales; they are distinct
from installed Dutch asset checks and actual gameplay evidence. Mobile carries
explicit study/translation/audio languages, but mobile OCR footage acceptance
is still pending. Full-game capture acceptance is **incomplete**.

Reader format research: [Quantic BigFile format](https://github.com/Ekey/QD.BIG.Tool)
and [BEYOND subtitle/audio research](https://hugo.fyi/projects/reverse-engineering-b2s).
No extractor implementation, assets or recordings from those sources are bundled.
