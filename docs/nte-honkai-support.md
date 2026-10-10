# Neverness to Everness and Honkai Impact 3rd

Both games have separate transcript histories, favorites, capture calibration,
original Mandarin playback, and optional Chinese Lexirise deck destinations.
Honkai means **Honkai Impact 3rd**, not Honkai: Star Rail.

## Setup

Open **Setup → Games**, choose the game, and select its installation folder.
Steam libraries on any registered drive are discovered automatically.

- **NTE:** choose the Neverness to Everness folder containing
  `Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe`. The nested Client,
  WindowsNoEditor, or HT folder is also accepted. A launcher without the client
  download is insufficient. Install the Chinese voice pack through NTE.
- **Honkai Impact 3rd:** choose the folder containing `BH3.exe` and `BH3_Data`,
  or select BH3_Data itself. Download Chinese story audio inside the game.

NTE needs the [Microsoft .NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0).
Install the SDK, then click **Install game tools**. Setup downloads a pinned,
checksum-verified UEExtractor and decompression libraries, retains its MIT
notice, and compiles this project's small reader bridge locally. These binaries
are separate local tools and are excluded from the toolkit repository and ZIP.
Honkai's package reader is built in; only the separately downloaded original
voice decoder is required.

Click **Refresh game data**, then use **Capture setup → Dialogue** to check the
subtitle crop with your game running. English or Simplified Chinese subtitles
are supported. Default crops are starting points; calibrate for the actual
dialogue layout. Neither game has an extra chatter/cinematic OCR channel yet.
The matcher requires an exact supported subtitle and a verified voice mapping;
unmapped text, response choices, and newer unsupported chapters are skipped.

## Verified coverage

NTE reads the installed English and zh-CN `game.locres` tables. It joins the
same localization namespace/key, verifies the exact `Play_Vo_<key>` bank and
event IDs, Chinese language ID, Wwise 154 fixed play tree, and numeric Chinese
media path. Only a single original source is accepted. Dynamic voice choices,
multiple sources, conflicting localization keys, and mod archives are excluded.
The installation used for validation yielded **14,364** bilingual voice mappings;
coverage changes with the user's client and voice downloads.

Honkai uses a reviewed public **4.7 bilingual catalog**, pinned to revision
`01d7afbaf99ff7d3d027e27fe9a4b363a2db7cc1` from
[HonkaiImpactData](https://github.com/nairieberry/HonkaiImpactData).
The catalog supplies explicit TextMap hashes and authored dialogue-event names.
The reader verifies the installed PCK language table, Chinese(PRC) bank header,
Wwise 135 Event → Play action → Sound → media chain, package bounds, and RIFF
source. Other languages, silence generators, dynamic choices, ambiguous events,
multi-page dialogue sharing a voice, and missing media are excluded.

**Honkai coverage is limited to older catalog content.** The tested installation
yielded **165** bilingual lines with original Mandarin audio. This does not
claim full current story support, Part 2, or newer chapters. There is no raw OCR,
machine-translation, or recorded-audio fallback. Expanding coverage requires a
reviewed bilingual catalog with explicit event references and installed-source
validation. Setup and index status display the catalog limit.

## Updates and privacy

Game locations and credentials remain per PC. Game archives are opened read-only.
Indexes, downloaded catalogs, extracted clips, and compiled readers remain in
ignored local caches; they are never included in Git or release artifacts.
NTE public archive metadata is passed to its reader through stdin, never command
arguments or logs, and cached with Windows DPAPI for the local Windows user so
subsequent playback can work offline. Initial preparation/indexing needs internet
access. No game files, voice packs, or decrypted catalogs are redistributed.

After the official launcher finishes updates or downloads more Chinese voices,
click **Refresh game data**. Checks run automatically about every two minutes.
Archive/package changes invalidate cached mappings. Failed or interrupted
refreshes preserve the previous complete index, while changed files block stale
audio extraction. New archive formats or unsupported banks need a toolkit
update; new Honkai chapters also need a reviewed catalog update.

Regression tests use synthetic catalogs, banks, and packages. Contributors must
never commit real game text, audio, extraction metadata, or captured gameplay.
