# Cyberpunk language preparation

Cyberpunk preparation reads only the selected official text pack, its matching
voice archive and the requested official translation tables. The supported study
locales are English, French, Italian, German, Spanish (Spain), Japanese, Korean,
Polish, Portuguese (Brazil), Russian and Simplified Chinese. Traditional Chinese
and other installed subtitle locales can supply official sentence translations.
Generic Spanish resolves to Spain and Portuguese to Brazil when those tables are
available. An absent translation stays unavailable.

Base-game and Phantom Liberty string IDs remain scoped to their content group.
Female/male V variants remain explicit when the authored voice paths differ.
Missing source voices never borrow another language's performance. Modified
subtitle layouts can be read in stacked, wrapped and tilde-separated forms,
including pairs using the same writing system. Ambiguous performances are rejected.

Language snapshots replace the previous complete table atomically. Preparation is
manual; automatic updates revisit only previously prepared languages. The
WolvenKit version and checksum remain pinned in the reader. Extracted text,
archives and decoded clips stay on the user's computer.

## Validation evidence

All eleven voice locales have mocked archive-selection and original-voice binding
regressions. Unicode and wrapped/same-script dual subtitles have matcher tests.
An installed English/French build mapped 85,448 dialogue variants and 75,374
original voice references. An installed English voice was decoded and checked for
non-silent output. This installation currently has English and Mandarin voice
packs; the other nine languages' actual audio was not decoded here. Synthetic OCR
checks are recorded separately from real gameplay footage and do not establish
chapter or branch coverage.
