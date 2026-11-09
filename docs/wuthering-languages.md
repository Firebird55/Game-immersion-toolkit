# Wuthering Waves language preparation

Prepare English, Japanese, Korean, Simplified Chinese or Traditional Chinese
explicitly in the game's Languages setup. The Chinese scripts share original
Mandarin audio. In Windows Setup, leave the game folder empty to retrieve the
requested translations and voice inventory from Kuro Games' Global release.
Playback fetches each original recording from its versioned package. Choosing an
installed game folder reads that edition's local tables and voice pack. The
Windows runtime uses its bundled Node and ooz-wasm decoder for compressed
entries. Source checkouts use Node and the project's locked npm dependencies.

PlotAudio's authored filename and language-specific gender flag select the
original performance. Rover variants remain explicit. Language-independent
resources, unresolved filename parameters and another dub's files cannot be
relabeled as a selected voice. Missing voice packs remain visible as missing;
mixed-language extraction batches are rejected before the extractor runs.

Floating 2D and 3D captions use authored text IDs. A voice is available when
the ID resolves to its localized PlotAudio performance. Update detection
checks the active Global story and dub releases independently. For installed
games it also includes optional SD, HD and UHD film packages. [Film and floating-caption coverage](game-audits/wuwa.md)

The translation target follows that learning language's effective Lexirise
settings. Official translations must align through the same dialogue ID.
Missing, empty and unsupported translation tables produce an unavailable
status. Preparation requires nonempty study text in the selected edition.

Publisher samples decoded in all four dubs. The desktop playback service and
the private library exporter produced identical MP3s for two English lines
with Simplified Chinese translations. The tested local installation contains
English and Mandarin voices. Its mapping
checks found 46,461 English, 46,293 Simplified Chinese and 46,280 Traditional
Chinese voice references. Original female and male Rover samples decoded in
all three text locales. Japanese and Korean text tables are present, but their
voice packs are absent on this PC. Language-specific authored binding fixtures cover all five locales.
Empty Russian, Vietnamese and Indonesian tables in this installation are
reported unavailable rather than treated as official aligned translations.

Synthetic production OCR checks cover all five text locales at 720p, 1080p
and 4K with source, translation, inline and wrapped layouts. Japanese and
Korean OCR cases use explicitly mocked audio bindings; they do not establish
installed voice-pack or native playback coverage. Browser checks exercise
Japanese study text, original audio controls, desktop/mobile widths and
Chromium/Firefox zoom/DPR emulation. No complete gameplay chapter coverage is
claimed from these asset and synthetic checks.
