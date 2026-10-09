# Delivery verification — 2026-10-09

All three GitHub repositories are private, preserve their original history and use main. Initial releases were published in dependency order; tested fixes follow as immutable patch releases.

Shared package 1.0.2 and Emulingo 1.1.1 have successful hosted workflows. Their downloaded release assets passed SHA-256/provenance checks; the hosted userscript passed the Chromium/Firefox test matrix. Toolkit 0.2.1 also passed its Windows hosted workflow and downloaded ZIP clean-install/browser tests. The subsequent toolkit patch fixes the live Hito repeated-word capture regression described below.

## Coverage

- Shared contracts cover all 31 study languages, minimal explicit settings writes, preservation of other profiles/read-only fields, migration, account/language cache isolation, UTF-16 offsets, failures and non-English lookup results.
- Browser tests cover Chromium and Firefox, seven viewport/DPR combinations from phone dimensions through 4K with 100–200% zoom-equivalent layouts. Emulingo additionally checks Shadow DOM isolation and Firefox delegated settings controls.
- Toolkit has 215 Python tests and nine JavaScript tests. Capture regression tests include normalized physical-pixel regions across resolutions/DPI, automatic Hito boxes and existing ZZZ/PRAGMATA behavior. These simulations do not claim live testing on every physical monitor.
- Real Lexirise verification used read-only requests with the existing protected key. Writes were mocked; no real account preferences were changed.
- Setup completed on this PC with locked dependencies and Windows native OCR. Existing local data, capture preferences and DPAPI credentials remain outside release artifacts.

## Live Hito verification

At 3840×2160, the existing game displayed `看到.. 看到.. 看到!!`. OCR read it correctly, but the highlight merge previously assigned all same-baseline highlights to the first split OCR row, duplicating later words. Restricting replacements by both vertical and horizontal overlap fixes this without weakening verified-text matching. A synthetic regression reproduces the split rows. The live backend then reported `phase: matched`, score 100, no error and stored the exact bilingual counterpart from the game catalog.

## Watcher review

`npm run lexirise:watch` is available in both consumers. During final verification it detected a real public website redeployment. API docs/endpoints were unchanged; the current published lists still have the same 31 study languages, 26 translation/interface languages and reading-system options. The UI alert remains visible because bundle hashes alone cannot prove complete settings/lookup compatibility. No baseline was silently accepted. Agents should inspect `.watch/report.md` and follow RELEASE.md before recording a reviewed baseline.

## Remaining boundary

SECURITY.md documents an upstream build-tool-only braces advisory. Browser matrices do not replace manual testing of every live game state or every userscript manager. Private userscript assets are downloaded with authenticated GitHub access and installed locally; no GitHub token or automatic public update URL is embedded.
