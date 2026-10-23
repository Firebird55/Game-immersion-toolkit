# Honkai: Star Rail language preparation

Choose **English, Simplified Chinese, Traditional Chinese, Japanese or Korean**
in **Setup → Languages**. Both Chinese scripts use original Mandarin audio.
Pair any study language with any of the game's **13 official text locales**
(65 study/translation combinations). The
[language matrix](languages/en.md#starrail) lists every supported combination.

## Setup

Select the installed client folder containing **StarRail.exe and StarRail_Data** in **Setup → Games**.
Epic/HoYoPlay launcher folders for Genshin and Star Rail are accepted when their
nested game client has been downloaded. Steam and conventional Epic/HoYoPlay
library locations are discovered automatically. Game folders are read-only.

Install the chosen original voice through the game's own language settings.
Prepare only the study language and translation you want. Missing official text
or audio stays unavailable; another language is never silently substituted.

## Dialogue and original voice

The reader follows **TalkSentenceConfig → VoiceID → VoiceConfig** from the
[game-data catalog](https://gitlab.com/Dimbreath/turnbasedgamedata). One immutable catalog revision supplies the selected
subtitle and translation tables. Only an exact authored source hash can bind an
installed original voice. Conflicting sources are skipped.

Split subtitle tables are merged with their Main tables at one immutable metadata revision. A whole movie audio track is never substituted for an individual caption.

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
