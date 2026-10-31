# Live subtitle and reading follow-up

Reported during the 2026-10-31 BEYOND: Two Souls session. The running installation
is older than the candidate branch and remains available while fixes are tested.
The owner's room photographs and raw session diagnostics remain private; public
regressions use authored examples.

## Capture and matching

- [x] Correct mixed traditional/simplified Chinese normalization without changing
  genuine characters. Test short exact matches as well as normalization stability.
- [x] Preserve BEYOND subtitle-page identity when localized text and
  voice cue counts differ. Do not invent page-to-audio timestamps or label missing
  voice evidence as unvoiced. Check paragraph fallback and repeat suppression.
- [x] Audit equivalent paragraph/full-track handling in every supported reader
  at the source and synthetic-fixture level. The [reader boundary audit](subtitle-boundary-audit.md)
  records authored boundaries, implemented fixes and unresolved formats.
- [ ] Replay ordered observations to verify that a new page is captured once and
  an earlier page cannot displace it through stale or ambiguous matches.
- [ ] Compare the supplied missed-line examples with installed authored resources,
  then verify the corrected candidate with real capture separately from fixtures.

Source checks: commits `019705e` and `edd4ae2` passed 111 focused tests. A private,
read-only rebuild verified 2,655 separate fallback pages with unchanged full
recording bindings; the three reported text examples now match exactly. Ordered
synthetic page capture passes. This does not replace installed capture validation.
The actual built React reader also passed Chromium/Firefox at 1280px and 390px:
delayed visibility reports and audio-ready events for an older subtitle do not
rewind a newer confirmed line. Real OCR replay remains a separate acceptance step.

Boundary fixes in `4cbefbd` and `5ef141b` passed 152 focused tests for the page
helper, Heavy Rain, Detroit, Rise, Spyro and ZZZ. The retained Honkai reader's
explicit per-page TextMap hashes are preserved in `b9c7e36`. Source captions,
Ground Zeroes, Deus Ex and shared matching/storage checks passed 154 targeted
tests for `be96a96`. The all-reader audit
does not guarantee every translation boundary: anonymous multi-page translations
remain unavailable where alignment is unproven, and Genshin's readable-book
paragraph pairing still has only equal-count positional evidence. Representative
gameplay replay for each supported game remains unchecked.

## Reading layout

- [x] Align annotated Latin words and punctuation on a common baseline, with
  bounded gloss widths and natural word spacing. Preserve CJK annotations.
- [x] Keep apostrophes and punctuation attached using original-text boundaries,
  without inventing lexical tokens or replacing account definitions.
- [x] Publish the shared component fix and synchronize both consumers; verify
  Chromium/Firefox, document/Shadow DOM, narrow screens and zoom.
- [ ] Verify the candidate's connected current/history layout using these cases.
  The old installed layout is not evidence of the candidate's appearance.

Shared release 1.0.14 is integrated in `5df400b`. The
[typography evidence](shared-reader-typography-2026-10-31.md) records both consumer
checks and browser results. Paragraph-scoped recordings remain available through
an explicitly labeled playback button on desktop/mobile. Sentence export omits
those recordings when exact page timing is unavailable, retaining voiced status;
mobile packages and desktop sharing preserve that distinction.

## Delivery

- [ ] Incorporate verified fixes into the existing installer/release candidate.
- [ ] Complete hosted native input, executable, browser and installer acceptance,
  then follow the normal clean-main release and verified-download procedure.
- [ ] Hand off the running installation only after preparation succeeds, retaining
  the transcript origin and session data. Record any remaining native limitations.

See the [desktop delivery plan](desktop-delivery-completion-plan.md) and
[R19 completion plan](r19-completion-plan.md) for the broader release gates.
