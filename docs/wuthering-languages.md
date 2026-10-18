# Wuthering Waves language preparation

Prepare English, Japanese, Korean, Simplified Chinese or Traditional Chinese
explicitly in the game's Languages setup. The Chinese scripts share original
Mandarin audio. Each preparation reads the requested official text tables and
the installed external voice inventory. It does not prepare other languages or
create dictionary entries.

PlotAudio's authored filename and language-specific gender flag select the
original performance. Rover variants remain explicit. Language-independent
resources, unresolved filename parameters and another dub's files cannot be
relabeled as a selected voice. Missing voice packs remain visible as missing;
mixed-language extraction batches are rejected before the extractor runs.

The translation target follows that learning language's effective Lexirise
settings. Official translations must align through the same dialogue ID.
Missing, empty and unsupported translation tables produce an unavailable
status, with no generated or English fallback. Source text packs must be
installed and nonempty before preparation succeeds.

The tested installation contains English and Mandarin voices. Native mapping
checks found 46,461 English, 46,293 Simplified Chinese and 46,280 Traditional
Chinese voice references. Original female and male Rover samples decoded in
all three text locales. Japanese and Korean text tables are present, but their
voice packs are absent on this PC; native playback for those dubs remains
untested. Language-specific authored binding fixtures cover all five locales.
Empty Russian, Vietnamese and Indonesian tables in this installation are
reported unavailable rather than treated as official aligned translations.

Synthetic production OCR checks cover all five text locales at 720p, 1080p
and 4K with source, translation, inline and wrapped layouts. Japanese and
Korean OCR cases use explicitly mocked audio bindings; they do not establish
installed voice-pack or native playback coverage. Browser checks exercise
Japanese study text, original audio controls, desktop/mobile widths and
Chromium/Firefox zoom/DPR emulation. No complete gameplay chapter coverage is
claimed from these asset and synthetic checks.
