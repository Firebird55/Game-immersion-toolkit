# Cyberpunk language preparation

Cyberpunk preparation reads only the selected official text pack, its matching
voice archive and the requested official translation tables. The supported study
locales are English, French, Italian, German, Spanish (Spain), Japanese, Korean,
Polish, Portuguese (Brazil), Russian and Simplified Chinese. Traditional Chinese
and other installed subtitle locales can supply official sentence translations.
Generic Spanish resolves to Spain and Portuguese to Brazil when those tables are
available. An absent translation stays unavailable.

Base-game and Phantom Liberty string IDs remain scoped to their content group.
When both groups reuse an ID, both receive explicit scopes so an older unscoped
identity cannot recover the other performance. Existing historical records and
cached clips remain intact; ambiguous recovery is unavailable.
Female/male V variants remain explicit when the authored voice paths differ.
Missing source voices never borrow another language's performance. Modified
subtitle layouts can be read in stacked, wrapped and tilde-separated forms,
including pairs using the same writing system. Ambiguous performances are rejected.
Empty official target tables are reported unavailable, and extraction batches
cannot mix original dubs.

Language snapshots replace the previous complete table atomically. Preparation is
manual; automatic updates revisit only previously prepared languages. The
WolvenKit version and checksum remain pinned in the reader. Extracted text,
archives and decoded clips stay on the user's computer.

## Validation evidence

All eleven voice locales have mocked archive-selection and original-voice binding
regressions. Unicode and wrapped/same-script dual subtitles have matcher tests.
Native extraction reads official study text in all eleven locales. The tested
installation maps 85,448 English dialogue variants with 75,374 voice references,
and 86,612 Mandarin text variants with 75,215 voice references. English and
Mandarin female/male performance samples decode to non-silent audio. The other
nine voice packs are absent on this PC, so native playback for those dubs remains
untested. Phantom Liberty is not installed locally; DLC identity isolation has
fixtures, while native DLC playback remains untested.
The other dubs' OCR fixtures use official installed text with explicitly mocked
audio bindings. Synthetic checks cover source, translation, inline and wrapped
layouts at 720p, 1080p and 4K; they do not establish native gameplay, chapter or
branch coverage. Browser checks use French study text with Chinese reading
preferences across Chromium/Firefox desktop/mobile widths and zoom/DPR emulation.
