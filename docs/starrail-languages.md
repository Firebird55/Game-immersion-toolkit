# Honkai: Star Rail language preparation

Choose **English, Simplified Chinese, Traditional Chinese, Japanese or Korean**
in **Setup → Languages**. Both Chinese scripts use original Mandarin audio.
Pair any study language with any of the game's **13 official text locales**
(65 study/translation combinations). The
[language matrix](languages/en.md#starrail) lists every supported combination.

## Setup

Leave the folder empty in **Setup → Games** to use the selected Global or
mainland China publisher edition. In **Languages**, prepare the study language and translation you want.
The Windows companion retrieves the original recording when you play or export
a matched line. Base and chapter packages follow the current regional publisher
manifests; missing original recordings stay unavailable.

To use an installed client, select its **StarRail.exe and StarRail_Data** folder.
Epic/HoYoPlay launcher folders for Genshin and Star Rail are accepted when their
nested game client has been downloaded. Steam and conventional Epic/HoYoPlay
library locations are discovered automatically. Game folders are read-only.

For installed preparation, download the chosen voice through the game's language settings.
Prepare only the study language and translation you want. Missing official text
or audio stays unavailable; another language is never silently substituted.

## Dialogue and original voice

The reader follows **TalkSentenceConfig → VoiceID → VoiceConfig** from the
[game-data catalog](https://gitlab.com/Dimbreath/turnbasedgamedata). One immutable catalog revision supplies the selected
subtitle and translation tables. Only an exact authored source hash can bind an
published or installed original voice. Conflicting sources are skipped.

Split subtitle tables are merged with their Main tables at one immutable metadata revision. A whole movie audio track is never substituted for an individual caption.

Film subtitles also follow their authored paths into the publisher's current
resource directory, including files missing from the community caption folder.
New filenames and repacked resources are discovered during preparation without
a toolkit update. Their movie and player associations stay separate from audio
verification: subtitle display times do not establish when the words are spoken.
The [caption audit](game-audits/starrail.md#declared-caption-resources-resolved--november-16-2026)
records the verified paths, language coverage and remaining gaps.

Battle College tutorial films use their separate authored caption and movie
paths. In the reviewed release, 38 of 45 declared captions have text in every
supported locale; seven strings remain missing. Their original movie stream
directories contain no embedded audio tracks. Tutorial audio therefore remains
unavailable while any separate sound-event route is unresolved; those entries
are not classified as silent dialogue. See the
[tutorial audit](game-audits/starrail.md#battle-college-tutorial-captions--november-16-2026).

Some written descriptions accompany a short character greeting or reaction.
That audio does not establish a recording of the written words. Unnamed
entries with candidate audio but no primary sentence voice remain unresolved; the toolkit
preserves them separately from confirmed spoken and unvoiced lines.

Publisher preparation can also read original audio from reviewed movie files,
without an installed game. Silent Galaxy currently has eight English and five
Japanese film clips with verified recording identities and separate spoken
windows. Boarding also has two reviewed English captions and two Japanese
captions in each Trailblazer movie variant. Select **Trailblazer voice** to
choose the authored movie; one variant never supplies a missing counterpart.
Other unresolved captions remain unavailable. First preparation fetches
Silent Galaxy (about 65 MB) and both Boarding variants (about 69 MB together)
to retain both player choices. Later exports reuse their verified audio.
The optional community format metadata is checked for updates automatically.
New or changed performances still need verified spoken boundaries. See the
[movie audit](game-audits/starrail.md#protagonist-movie-clips--november-16-2026)
for source provenance and remaining limits.

Use **Capture setup → Trailblazer voice** for ambiguous player performances.
The bottom dialogue crop has separate per-PC calibration for this game. Check
it against your subtitle size, resolution and display scaling. YouTube evidence
and reproducible replay instructions are in
[game OCR presentations](game-ocr-presentations.md#starrail-genshin-endfield).

## Updates, reading and mobile

After the official launcher finishes a patch or voice download, choose
**Refresh game data**. Automatic checks revisit prepared locales about every
two minutes. A failed build leaves the previous complete table available.

History, favorites, original playback, explicit game-deck export, Lexirise
reading and independent Migaku mode use the existing language-aware workflow.
Export a private mobile library for independent phone/tablet OCR, or pair the
phone with the running Windows companion. Catalogs and voices remain private.

Game files, recordings, extracted catalogs, compiled readers and audio caches
are never committed or included in the public mobile preview. No account writes
are needed to prepare a language or run the capture checks.
