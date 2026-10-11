# Mobile library verification — 0.2.17

These results establish the exported-file workflow and its tested boundaries.
They do not establish physical iPhone reliability or complete game coverage.
Follow [the transfer and device-test instructions](mobile-library.md).

## Automated and local checks

- Exporter fixtures cover all eight adapters, catalog-only export, original
  bindings, player variants, installed DLC, cinematic timing, deduplication,
  cancellation, interrupted work, cache/pack corruption and source changes.
  Local API tests retain the localhost, origin and action-header protections.
- Private two-line exports from Wuthering Waves, PRAGMATA, Cyberpunk, Witcher,
  NTE and Honkai opened and played original MP3s in Chromium. Those files remain
  outside Git and releases. Hito is not currently installed on the verification
  PC; its text-only package path is covered by fixtures rather than a fresh
  installed-game export. ZZZ's package format and adapter are covered by tests;
  its original voice decoding also retains the existing desktop checks.
- Browser checks exercise real ZIP file selection, English and Simplified
  Chinese Tesseract OCR, manual MP3 playback, favorites, malformed packages,
  reload/reselection and private diagnostics. Chromium and Firefox pass locally.
  Windows Playwright WebKit passes file reading and canvas OCR; its runtime
  cannot decode the media fixture. Linux CI passes the full media checks in all
  three engines, including offline pack reselection, playback and warmed Chinese
  OCR. A small visible preview prevents the observed off-screen WebKit stall.
- Real Chromium/Firefox WebRTC recovery preserves the opened catalog,
  transcript and favorite. Software-update tests in all three engines retain
  the catalog, calibration and favorite, including an offline reload and a
  waiting update while session controls are locked.
- An owned 2.15 GiB fixture contains five voice ZIPs and a small catalog.
  Chromium opened it in approximately 0.52 seconds, played its local tone,
  restored its catalog on reload and played after pack reselection. IndexedDB
  use stayed below 64 MiB. This is a desktop browser measurement, not an iPhone
  timing or peak-memory measurement.
- The production OCR pipeline passes 64 authored layout cases: eight game
  dialogue templates, comic/card/overhead/legacy/light-panel presentations and
  menu/HUD negatives at 720p, 1080p, 4K and ultrawide sizes. Synthetic templates
  verify algorithms and crop scaling; they cannot verify unseen game scenes.
- Desktop Setup and reading UI checks cover Chromium/Firefox, phone/tablet
  widths, zoom and device-pixel ratios. Shared reading components are unchanged.

## Private recorded footage

The latest results combine the full replay with targeted reruns after correcting
response-menu word bounds and light Honkai panels. There are 27 annotated clips,
each resized/padded to 1280×720 and 1920×1080. **35 of 54 cases pass all their
annotations.** No annotated negative emits a voice in these final results.
Some positive cases contain legitimate matched lines while missing other
required lines; those cases remain failures.

| Game | Observed result and remaining boundary |
| --- | --- |
| Honkai Impact 3rd | All 12 sampled cases pass: modern white panels, legacy/right panels, multi-page dialogue and negatives. This does not verify newer chapters outside the installed adapter's catalog. |
| Wuthering Waves | Sampled ordinary dialogue and menu negatives pass; a centered card passes at 720p. Some movie/story captions and the same card at 1080p still miss. |
| NTE | Sampled radio captions and introduction cards pass. Wrapped/walking dialogue, speaker-strip cases and some opening-movie/player-variant captions still miss. |
| Cyberpunk | Some overhead lines match, but the annotated small overhead conversation is incomplete at both resolutions. |
| Witcher III | Sampled cutscene subtitles pass; top-edge NPC chatter still misses at both resolutions. |
| ZZZ / PRAGMATA | No existing private footage was available for the browser replay. Public layout fixtures pass; real browser footage verification remains pending. |

Local footage, row identities, OCR strings and detailed reports stay in ignored
directories. Public CI contains only authored synthetic scenes and tones.
Crop calibration, original-image contrast and larger game subtitles may improve
individual cases, but are not counted as verified fixes without another replay.
Rejected or missing lines remain unsupported rather than acquiring guessed
bilingual text or voice bindings.

## Physical acceptance remains pending

No physical iPhone has yet confirmed this build's 2 GiB selection, original
playback, reboot/reselection, application update and 15-minute OCR session. The
page provides a private device report to record those observations. The retained
Files copies remain the recovery source if Safari clears its catalog cache.

An iPad/iPhone gaming device must provide a working foreground-game capture
source. A native system-capture sender is outside this release. Test the phone
receiver with a PC sender until that source is available; GitHub Pages and a
Home Screen shortcut cannot add an absent capture API.
