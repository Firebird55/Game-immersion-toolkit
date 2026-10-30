# Arknights: Endfield language preparation

Choose **English, Simplified Chinese, Traditional Chinese, Japanese or Korean**
in **Setup → Languages**. Both Chinese scripts use original Mandarin audio.
Pair any study language with any of the game's **14 official text locales**
(70 study/translation combinations). The
[language matrix](languages/en.md#endfield) lists every supported combination.

## Voice language support and verification

The publisher's current [Steam language table](https://store.steampowered.com/app/4732690/Arknights_Endfield/)
lists **English, Mandarin Chinese, Japanese and Korean** full audio, alongside
14 subtitle languages. The [official Gryphline language announcement](https://endfield.gryphline.com/en-us/news/0767)
also identifies those four voice languages. Traditional Chinese is an additional
subtitle choice that uses Mandarin recordings; it is not a fifth voice pack.

All four voice formats are implemented and selectable regardless of which packs
are installed. The same exact source-path/hash binding and VFS reader handle
each namespace; initial and hotfix packages are included for every selection.

| Study selection | Voice package / VFS group | Implementation evidence | Playback verified on this host |
| --- | --- | --- | --- |
| English (`en`) | `english` / AudioEnglish | Authored schema, locale-specific hashes, extraction routing and missing-pack preparation regressions | No; English package absent in the audited install |
| Simplified Chinese (`zh-Hans`) | `chinese` / AudioChinese | Same contract plus installed package/index proof | Yes; production conversation and combat-bark clips decoded to non-silent audio |
| Traditional Chinese (`zh-Hant`) | `chinese` / AudioChinese | Installed Traditional Chinese text table and synthetic script/audio pairing regressions | Shared Mandarin decoder verified through Simplified Chinese; this text selection was not separately played in game |
| Japanese (`ja`) | `japanese` / AudioJapanese | Authored schema, locale-specific hashes, extraction routing and missing-pack preparation regressions | No; Japanese package absent in the audited install |
| Korean (`ko`) | `korean` / AudioKorean | Authored schema, locale-specific hashes, extraction routing and missing-pack preparation regressions | No; Korean package absent in the audited install |

For absent packs, compatibility is inferred from the installed common schema and
the reader's explicit per-language format, with synthetic per-locale validation.
It is not a claim that those unavailable packages were natively decoded. Missing
packs remain a preparation warning with an installation action, not an
unsupported-language error. See the [Endfield audit](game-audits/endfield.md)
for dated evidence and remaining presentation gaps.

## Setup

Select the installed client folder containing **Endfield.exe and Endfield_Data/StreamingAssets/VFS** in **Setup → Games**.
Epic/HoYoPlay launcher folders for Genshin and Star Rail are accepted when their
nested game client has been downloaded. Steam and conventional Epic/HoYoPlay
library locations are discovered automatically. Game folders are read-only.

Install the chosen original voice through the game's own language settings.
Prepare only the study language and translation you want. Missing official text
or audio stays unavailable; another language is never silently substituted.

Endfield needs the [Microsoft .NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0). **Install game tools** downloads pinned, checksum-checked [EndfieldStudio](https://github.com/EIHRTeam/EndfieldStudio) reader sources and retains their MIT notice in the private tool cache. The toolkit builds its small VFS bridge locally.

## Dialogue and original voice

The reader follows **DialogTextTable and RadioTable text ID → audioOverride → AudioDialog source path**, plus authored TextTable/TextVoIdTable narration, operator profile voices and exact AIBarkText voice-ID joins, from the
[third-party game-data mirror](https://github.com/rmxlinux/EndfieldData). One immutable catalog revision supplies the selected
subtitle and translation tables. Only an exact authored source hash can bind an
installed original voice. Conflicting sources are skipped.

Verified text-only choices, story panels, messages and readables can be prepared
without audio. Missing recordings and missing metadata are never relabeled
silent. Preparation reports unresolved metadata separately from known source
paths absent from the chosen locale; reinstalling a voice pack cannot repair a
missing metadata reference.

Endfield resolves the complete authored source path and its locale-specific Wwise external hash. StreamingAssets and Persistent layers are combined with patch precedence. Only the selected voice group, initial audio and hotfix group are read; unrelated music and effects are excluded.

Use **Capture setup → Endministrator voice** for ambiguous player performances.
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
