# Supplied game screenshot regressions

The 36 game screenshots supplied on 2026-10-30 are lossless WebP files at their
original dimensions. Account identifiers are blacked out; captions, HUD and
creator watermarks remain. The manifest records source and derived hashes,
redaction rectangles, independent caption expectations and partial-text cases.
Attachments 1, 5 and 6 were transcript UI references and are not included.

Run `python scripts/check-game-screenshots.py` with the locked dependencies. It
uses bundled offline OCR, production capture regions and text grouping, and
resolves the observed OCR against authored test catalogs. The required GitHub
check runs it whenever Python checks are selected, including full release checks.
Use `--native` for locally available Windows OCR; `--tesseract` is a diagnostic
comparison for the browser engine and is not the passing desktop baseline.

Each still image has unknown voice status. Separate authored catalogs exercise
voiced and explicitly unvoiced behavior; they do not claim to verify original
game audio, package bindings, speaker identity or temporal ordering. Partial
captions are evaluated only for the visible portion. Full temporal acceptance
requires additional sequences. Other games still need screenshots and tests as
listed in the [completion plan](../../../docs/capture-regression-completion-plan.md).
