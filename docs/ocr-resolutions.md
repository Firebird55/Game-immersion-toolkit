# OCR at different resolutions

Capture regions follow the game's physical client area. Windowed mode excludes
the title bar and borders; fullscreen and borderless modes use the same relative
regions. Moving the window to another monitor, including a monitor at a negative
desktop coordinate, preserves the crop. Windows DPI and browser zoom are not
applied a second time. Existing per-PC calibration is preserved.

ZZZ, PRAGMATA, Cyberpunk, Wuthering Waves and Witcher OCR scales using client
height to a 1440-pixel reference, with at most 2× enlargement. Wide crops retain
their width rather than shrinking subtitle glyphs to meet a fixed width cap.
This improves small-window text and 21:9/32:9 subtitles while reducing unnecessary
4K pixel processing. Previews keep the original crop. Hito retains its dedicated
pixel-text enlargement and automatic dialogue-box detection.

Chinese comic-fragment lookup reuses the prepared localization index, keeping
an expensive per-frame rebuild out of the subtitle stability window. Exact
original voice ownership, ambiguity checks, and the two-frame dialogue gate
are unchanged.

Punctuation-only OCR rows, such as an isolated ellipsis, no longer divide two
wrapped Chinese rows into separate language blocks. This preserves the full
original subtitle when OCR segmentation changes with resolution or font size.

## Offline verification

The synthetic screenshot matrix uses actual installed English/Chinese text at
800×600, 1280×720, 1366×768, 1280×800, 1920×1080, 1920×1200, 2560×1440,
3440×1440, 3840×2160, and 5120×1440, with normal and 75% subtitle font sizes.
It covers single-language capture in all five games, Cyberpunk bilingual
subtitles, and Witcher inline/wrapped Dual Subtitles. Tests use native Windows
OCR and production cropping/matching, including an offset second-monitor
origin, and isolate their databases from the user's history.

All 260 matrix cases passed, producing exactly one verified transcript row
per case. The final checks also passed 282 Python tests, 11 JavaScript tests,
type checking, the production build, and native Windows capture/OCR preflight.
Wuthering Waves used its downloaded Mandarin pack, with 46,280 original voice
mappings available during the checks.

Run with the configured Windows virtual environment:

```powershell
python scripts/check-subtitle-screenshots.py --fixtures --resolution-matrix --font-scale 1 --font-scale 0.75 --output output/playwright/subtitles-resolutions
```

Choose a specific game and custom resolution:

```powershell
python scripts/check-subtitle-screenshots.py --fixtures --game wuwa --resolution 1920x1080
python scripts/check-subtitle-screenshots.py --game witcher3 --image 'C:\screenshots\dialogue.png'
```

Synthetic checks do not validate a game's actual subtitle placement, alternate
HUD safe zones, letterboxing, or unusual font settings. Use Capture setup's
preview to adjust a game's region when its real layout differs. No game is
launched by these checks.

## Recorded gameplay

[Game-specific OCR presentations](game-ocr-presentations.md) documents the
additional Cyberpunk/Witcher NPC regions and Wuthering centered story cards,
with real sequential footage checks at 720p, 1080p and a 4K resize. The earlier
synthetic matrix complements these placement and negative-screen checks.
