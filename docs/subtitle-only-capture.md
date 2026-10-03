# Subtitle-only original voice capture

Starting October 3, 2026, Proxy Transcript captures only visible subtitles that match official bilingual text and have a verified mapping to an original game voice file. This applies to ZZZ dialogue, floating gameplay subtitles, top-right voiced subtitles, comics/cinematics, and PRAGMATA dialogue.

The running application no longer opens a loopback recording stream, performs live speech detection, recognizes agent selection audio, transcribes agent clips, or builds audio fingerprint indexes. The Agents view and its API routes are removed. Agent menus have no subtitles and are outside the supported capture workflow. Existing agent archives are preserved on disk.

A stable matched subtitle is published immediately while the mapped original voice is decoded asynchronously. Voice clips come from installed game files, so headset selection and game volume do not affect matching. Missing voice mappings are skipped; extraction failures retain the confirmed subtitle and can be repaired from the exact mapping. Automatic text and original voice mapping updates remain active.

Regression checks exercise mapped/unmapped ZZZ capture across all four channels, PRAGMATA capture without live speech, original extraction failure and retry, preserved confirmed subtitles/favorites, and removal of agent routes. No actual game is currently running for a live subtitle check.

The full regression suite passed (143 tests, one skipped) before the separate full Lexirise analysis change. Native OCR recognized “Enemies incoming!”, local FFmpeg was available, the 1920×1200 display could be captured, and all four subtitle crop geometries stayed within the display.
