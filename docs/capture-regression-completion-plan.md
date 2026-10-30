# Capture and screenshot completion plan

Status: implementation in progress. This is companion work to the
[R19 completion plan](r19-completion-plan.md), tracked in
[delivery issue #61](https://github.com/Firebird55/Game-immersion-toolkit/issues/61).
Only verified results close a checkbox. Screenshot inputs are **game captures
only**; transcript UI images are not regression fixtures.

## Shared contract

All active games use the same confirmation, transcript identity, history,
language selection, update and package behavior. Keep adapters only for actual
layout, official catalog, player variant, file format and audio differences.
Preserve R19 B's distinct format evidence without separate product rollout rules.
Explicitly unvoiced official text is supported. Unknown or failed voice lookup
does not turn a voiced row into an unvoiced row or select another language.

## Remaining implementation

- [x] Persist ZZZ Automatic/Belle/Wise selection across all caption channels.
  Infer Automatic only from unique authored player/scene evidence; never from
  the mere appearance of Belle or Wise as the sibling NPC. A manual choice wins.
- [x] Reject the ZZZ account/events menu, including the false "…New?" result,
  while retaining legitimate short captions and comic menu controls.
- [x] Capture complete top-right bubbles promptly and retain multiple comics.
  Apply common scheduling and wrapped-line fixes to other adapters.
- [ ] Separate NTE custom-player speaker labels from caption matching; retain
  official identity/voice ambiguity when the observed text cannot settle it.
- [ ] Handle speaker titles, unknown speakers, narration, choices and partially
  revealed captions without inventing missing text or speaking order.
- [x] Follow the game window's physical bounds and monitor, including negative
  coordinates, per-monitor DPI, resize and display movement. Retain calibration.
- [ ] Add equivalent platform discovery/capture adapters as declared in the
  [host delivery plan](desktop-delivery-completion-plan.md).

## Supplied game corpus

| Game | Images | Presentations |
| --- | ---: | --- |
| Zenless Zone Zero | 4 | Top-right bubble, account-menu negative, one/two comic bubbles |
| Arknights: Endfield | 3 | Story/walking dialogue and wrapped lines |
| PRAGMATA | 3 | Named subtitles, wrapped lines and HUD exclusion |
| Neverness to Everness | 7 | Movies, narration, player name, walking and partial dialogue |
| Honkai: Star Rail | 6 | Movies, named/wrapped/partial dialogue, choices and walking |
| Genshin Impact | 4 | Movie, speaker titles and colored dialogue |
| Wuthering Waves | 9 | Named/unknown speakers, narration, choices and illustrated scenes |

- [x] Import all 36 game images with source dimensions and SHA-256. Redact
  nonessential account IDs before committing; preserve caption pixels and
  creator attribution. Record redactions and derived-image hashes.
- [x] Independently annotate required/forbidden text, regions, speaker and
  partial-text state. Voice is unknown unless verified outside the still image.
- [x] Exercise real OCR and production crop/matching. Bind catalog and voice IDs
  only where verified; label OCR-only cases separately from package acceptance.
- [x] Verify voiced and explicitly unvoiced paths with suitable catalog fixtures.
  Public decoder fixtures use authored audio, not original game recordings.
- [ ] Run the corpus in GitHub Actions; missing expected text fails, empty output
  is not success. Record engine/model, fixture and source identity per run.

## Missing game screenshots and tests

Every other supported game still needs representative screenshots and regression
tests: Cyberpunk 2077, The Witcher 3, BEYOND: Two Souls,
Heavy Rain, Detroit: Become Human, Rise of the Tomb Raider, Shadow of the Tomb
Raider, Spyro Reignited Trilogy, Metal Gear Solid V: The Phantom Pain,
Metal Gear Solid V: Ground Zeroes, Death Stranding, A Plague Tale: Innocence,
Portal, Portal 2, Half-Life 2, Half-Life, Persona 5 Royal, and
Deus Ex: Human Revolution Director's Cut. Reconcile this list against the active
registry when adding fixtures; historical or retired support is not a new claim.

Their status is **awaiting screenshots/tests**. Passing the seven supplied games
does not close any of these gaps. The separate [screenshot regression plan](screenshot-regression-plan.md)
continues to define package input, sampled locale and temporal-evidence rules.

## Acceptance and R19 dependencies

Source OCR/caption tests can proceed before R19's helper collection is complete.
Local replay on 2026-10-30 passed all 36 cases with Windows OCR and the bundled
RapidOCR 1.4.4 offline engine. The required integration job now runs the offline
replay with Python checks and uploads observations and source identity. Hosted
execution remains unchecked above until a run succeeds. Browser Tesseract is a
separate diagnostic comparison and does not yet pass this entire corpus.
Frozen OCR/voice/export acceptance names the eligible R19 artifact and actual
toolchain. Native monitor/DPI evidence contributes to R19 D; package readback
contributes to B3. A still frame proves neither temporal order nor actual audio.

Windows discovery now retains pointer-sized native handles and identifies the
monitor containing most of the game window using
[MonitorFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-monitorfromwindow).
Capture continues to use the complete physical client rectangle, including a
window spanning displays; it is never clipped to the primary monitor. Capture
setup reports the detected display. On 2026-10-30 the opt-in
`scripts/check-monitor-capture.py --background` probe moved an owned colour window
across three real displays (portrait, negative-origin and primary), verified its
pixels, then covered it and verified isolated background capture on each display.
No screen images were saved. Unit cases cover monitor changes, lost windows,
physical crop bounds and 64-bit handle declarations. This is source/host evidence;
the final frozen candidate still requires the same native acceptance.
