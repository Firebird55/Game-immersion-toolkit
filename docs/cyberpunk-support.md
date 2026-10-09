# Cyberpunk 2077 and automatic subtitle languages

Cyberpunk, ZZZ, and PRAGMATA automatically match visible English or Simplified
Chinese subtitles to official bilingual game text. Study text stays Chinese and
voice playback stays Mandarin. Hito's World keeps its existing capture behavior.

Cyberpunk is detected by `Cyberpunk2077.exe`. Choose the installation root in
**Choose Game Folders.cmd**, or use automatic Steam-library discovery. The
Mandarin voice pack must be installed through Steam. Phantom Liberty language
archives are included when present; the toolkit does not acquire the expansion.

The first background check downloads WolvenKit Console 9.0.1 and verifies its
SHA-256 against the pinned digest. It extracts stock subtitle and Mandarin voice
maps into ignored local `data/cyberpunk` caches. Matching joins exact 64-bit
localization IDs and preserves male/female text and voice variants. Original
WEM clips are extracted and decoded on demand with vgmstream and FFmpeg; game
archives are read-only and are never redistributed. Changed or moved archives
trigger another background check. Refresh can also be requested from the UI.

In Cyberpunk's **Capture setup**, choose **V voice: Female** or **Male** to match
the current playthrough. This also selects NPC performances that address that
variant of V. Until selected, lines with different male/female voice assets are
skipped. Repeated text with multiple possible performances is skipped rather
than attached to an arbitrary clip.

The [Dual Language Subtitles (English Appended) mod](https://www.nexusmods.com/cyberpunk2077/mods/10260)
can display Chinese with English beneath it. The matcher handles separate or
flattened bilingual rows, wrapped dialogue, and bilingual speaker labels. Both
halves resolve to one subtitle record. Indexing uses stock archives rather than
the mod's combined strings, so menus and interface descriptions remain excluded.
Both the full-interface and subtitles-only editions use this capture behavior.

Per-PC capture settings and existing transcripts are preserved. ZZZ/PRAGMATA
Lexirise deck mappings stay unchanged. The configured Cyberpunk sentence deck
ID is stored locally in the Lexirise export database rather than in source.

## Where Winds Meet

Where Winds Meet is excluded from this pass. Its official text and raw Wwise
audio are accessible, but the dialogue metadata does not yet provide a verified
subtitle-to-original-clip mapping. No recording or inferred voice fallback is
enabled. Its requested Lexirise deck was created and remains available for a
future verified integration.

## Validation limits

Regression fixtures cover English/Chinese recognition, bilingual wrapping,
variant selection, exact voice paths, game isolation, optional expansion files,
and interrupted updates. A real installed Mandarin clip was decoded and checked.
Native Windows OCR and display geometry are checked separately. These checks
do not substitute for observing subtitles during actual gameplay with the mod.

On this PC, the stock installation yielded 85,391 bilingual records and 75,098
Mandarin voice references. A sampled original clip decoded to 1.56 seconds of
non-silent Mandarin audio. No game was launched for validation.

The offline screenshot check passed seven synthetic **3840 × 2160** fixtures
using official extracted text: ZZZ and PRAGMATA in English and Chinese, plus
Cyberpunk in English, Chinese, and the bilingual layout. Each fixture runs
through the production crop, native OneOCR, matching, stability, and original
voice-reference gate. Bilingual capture produces one transcript entry. These
plain-background fixtures are not screenshots taken during gameplay.

Run `python scripts/check-subtitle-screenshots.py --fixtures` with the configured
Windows virtual environment to recreate them. Images and results are stored
under ignored `output/playwright/subtitles-4k`. To inspect existing actual
screenshots without starting a game, use
`python scripts/check-subtitle-screenshots.py --game cyberpunk --image "C:\path\screenshot.png"`.
The latter reports recognized text and matched identities, and writes only to
its isolated test transcript. It does not add lines to the user's real history.

Final checks include TypeScript, 241 Python tests, 11 JavaScript tests, the
production build, and Chromium/Firefox layouts at desktop, mobile, and 4K
resolutions (100%, 150%, and 200% scaling for 4K). Browser fixtures verify game
isolation, V voice saving, per-game refresh, calibration preservation, and
reading controls. Asset refresh and background polling preserve unsaved capture
settings while the setup dialog is open.

The public Lexirise compatibility check reported unchanged API documentation
and endpoint lists, with changed website bundle hashes. Public settings, lookup
terms, and Chinese language options were reviewed against the pinned shared
capabilities. The shared package and its baseline remain unchanged; account
settings writes in browser checks use mocks.
