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

In **Capture setup**, select **Zero voice** for NTE movies with player variants.
There is no automatic/default gender choice. Fixed voices still capture without
this selection. For a centered 16:9 game picture inside a taller or wider window,
choose **Game picture area → Centered 16:9 picture inside black bars**. Leave
**Full game window** selected when the game fills the window. Preview uses the
same picture coordinates as capture. **Use tested dialogue crop** restores the
reviewed crop explicitly; updates preserve existing per-PC calibration.

## Verified coverage

NTE reads the installed English and zh-CN `game.locres` tables. It joins the
same localization namespace/key, verifies the exact `Play_Vo_<key>` bank and
event IDs, Chinese language ID, Wwise 154 fixed play tree, and numeric Chinese
media path. Only a single original source is accepted. Multiple sources,
unresolved dynamic choices, conflicting localization keys and mod archives are excluded.
The installation used for validation yielded **14,928** bilingual voice mappings;
coverage changes with the user's client and voice downloads.

That total includes **474 movie cue/voice mappings**. A reviewed seed
[movie binding catalog](https://github.com/Waifus-Grace/NTE_Assets/tree/cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7)
links the movie's subtitle file to its explicit CG voice event and localization
table. Caption keys, English/Chinese text, cue times and original Mandarin media
come from the user's installed archives. Playback cuts the original movie voice
at those authored times and checks decoded source bounds before saving a clip.
Repeated cue keys with ambiguous timings are excluded. The explicitly authored
`Sex_Switch` female/male branches are supported only when selected in setup;
random playback, other switches and continuous/faded branches remain excluded.
This covers the tested opening movie, radio captions, character introduction
card and later movie dialogue without scanning character labels across the screen.

Honkai starts with a reviewed public **4.7 bilingual catalog**, at revision
`01d7afbaf99ff7d3d027e27fe9a4b363a2db7cc1` from
[HonkaiImpactData](https://github.com/nairieberry/HonkaiImpactData).
The catalog supplies explicit TextMap hashes and authored dialogue-event names.
The reader verifies the installed PCK language table, Chinese(PRC) bank header,
Wwise 135 Event → Play action → Sound → media chain, package bounds, and RIFF
source. Other languages, silence generators, dynamic choices, ambiguous events
and missing media are excluded. Authored dialogue pages sharing one verified
performance are now joined into a complete bilingual utterance. An exact,
unambiguous page identifies that utterance and its complete original voice;
page-sized audio cuts are not inferred.

**Honkai coverage is limited to older catalog content.** The tested installation
yielded **222** bilingual performances, including **57 multi-page performances**,
with original Mandarin audio. This does not
claim full current story support, Part 2, or newer chapters. There is no raw OCR,
machine-translation, or recorded-audio fallback. Expanding coverage requires a
reviewed bilingual catalog with explicit event references and installed-source
validation. Setup and index status display the catalog limit.

The missing multi-page briefings in the reviewed older footage now capture.
Historical English rewrites that differ from every authored catalog page still
require a matching reviewed localization catalog; they are not guessed from
neighboring scene IDs. The published coverage count does not include those
rewrites or unsupported current chapters. See the
[footage and resolution checks](game-ocr-presentations.md#nte-and-honkai-footage)
for the precise tested presentations.

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
update. Compatible catalog updates are checked independently of toolkit releases;
see [game-data updates](game-data-updates.md). The available Honkai source still
covers older content: refreshing does not manufacture missing chapter text or
prove full current story coverage.

Regression tests use synthetic catalogs, banks, and packages. Contributors must
never commit real game text, audio, extraction metadata, or captured gameplay.
