> **Honkai Impact 3rd is archived and unsupported.** Honkai instructions and results below are historical research only. The game is absent from setup, automatic capture and the web UI. NTE remains supported.

# Neverness to Everness and Honkai Impact 3rd

Both games have separate transcript histories, favorites, capture calibration,
original Mandarin playback, and optional Chinese Lexirise deck destinations.
Honkai means **Honkai Impact 3rd**, not Honkai: Star Rail.

## Setup

For NTE, open **Setup → Games** and choose a publisher edition. Leave the game
folder empty for online preparation, or select an installed client. Steam
libraries on any registered drive are discovered automatically. Honkai setup
directions below are retained historical documentation.

- **NTE publisher:** choose the edition and an available study language in
  **Languages**. Official text, translations and selected original voices are
  retrieved without a game installation. Missing regional text or unresolved
  audio is reported separately. See the [current source audit](game-audits/nte.md#publisher-setup-and-immutable-voice-snapshots).
- **NTE installed fallback:** choose the Neverness to Everness folder containing
  `Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe`. The nested Client,
  WindowsNoEditor, or HT folder is also accepted. A launcher without the client
  download is insufficient. Install the Chinese voice pack through NTE.
- **Honkai Impact 3rd:** choose the folder containing `BH3.exe` and `BH3_Data`,
  or select BH3_Data itself. Download Chinese story audio inside the game.

Source installations of NTE need the [Microsoft .NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0).
For source development, install the SDK, then click **Install game tools**. Setup downloads a pinned,
checksum-verified UEExtractor and decompression libraries, retains its MIT
notice, and compiles this project's small reader bridge locally. These binaries
are separate local tools and are excluded from the toolkit repository and ZIP.
The desktop [compiler-free runtime contract](nte-runtime.md) instead uses its
bundled self-contained bridge and verified dependency inventory. It never asks
the user to install a compiler or downloads executables at runtime. Candidate
distribution/native acceptance is tracked separately in that document.
Honkai's package reader is built in; only the separately downloaded original
voice decoder is required.

Click **Refresh game data**, then use **Capture setup → Dialogue** to check the
subtitle crop with your game running. English or Simplified Chinese subtitles
are supported. Default crops are starting points; calibrate for the actual
dialogue layout. Neither game has an extra chatter/cinematic OCR channel yet.
The matcher requires an exact supported subtitle and a verified voice mapping;
unmapped text, response choices, and newer unsupported chapters are skipped.

In **Capture setup**, select **Zero voice** for NTE dialogue and movies with
protagonist variants. Fixed female/male branches use their authored bank media;
the corresponding text and translations follow the same choice. An unconfigured
choice does not select a default. Missing media in the other
branch does not block the configured branch. A caption also used by an unresolved
conversation or choice remains ambiguous until its context is verified.
There is no automatic/default gender choice. Fixed voices still capture without
this selection. For a centered 16:9 game picture inside a taller or wider window,
choose **Game picture area → Centered 16:9 picture inside black bars**. Leave
**Full game window** selected when the game fills the window. Preview uses the
same picture coordinates as capture. **Use tested dialogue crop** restores the
reviewed crop explicitly; updates preserve existing per-PC calibration.

## Verified coverage

The NTE publisher route reads the selected release's original localization,
dialogue and movie tables, sequence clocks and voice banks. Compatible needed
type-data updates are derived from the selected original client. Movie text aliases follow the
original registry and each actual StringTable namespace, including newly added
aliases in compatible game updates. Exact historical snapshots retain
their metadata and original recordings. Original CG references also support
voice-event object names that omit the redundant `CG` name segment, while
music events and unrelated source roots remain excluded. Wwise 154 separately
loaded media is parsed with its full codec header, but storage-0/1 cinematic
caption timing remains unavailable without a verified original clock contract.
Supported original authoring tables are discovered by native RowStructure and
exact export ownership, including Ride-Along voices; new compatible tables do
not require an updated filename list. Conflicting sequence/caption owners and
muted, looping or changed-clock sources remain unresolved.
The [original-native publisher route](game-audits/nte.md#original-native-publisher-preparation)
generates needed format metadata from authenticated publisher client files and
a fixed retained seed. It refreshes resolvable changed definitions and original
enum literals, then validates the actual reader's required closure before the
worker returns an index. The fixed original baseline is retrievable without a
game installation. No current community mapping index is required; existing
archive/localization parameters remain explicitly frozen. Unsupported required
layouts fail without replacing the prior complete index or historical audio.
The [November 17 current-use audit](game-audits/nte.md#current-use-acceptance-boundary)
separates demonstrated current presentations from configuration-only research
references. After the documented corrections, no active presentation with
incorrect audio or missing available original audio remains demonstrated in that
finite evidence; full-story coverage is not claimed. Unsupported cinematic clocks
and unresolved source references stay unavailable. Cross-platform acceptance is separate. The installed
results below describe an earlier reviewed client.

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

A later launcher update on 2026-10-10 exposed **2,772** verified performances
across **108** installed audio packages. The refreshed index fingerprint matched
that updated installation. A sampled original performance decoded successfully
and was non-silent. This is increased availability of catalog 4.7 performances,
not evidence of newer-chapter or Part 2 catalog coverage. Counts depend on which
story voices the user has downloaded.

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
