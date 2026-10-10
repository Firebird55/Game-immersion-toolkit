# Game immersion toolkit

Local Windows OCR, verified bilingual transcripts and original game audio for Hito's World, Zenless Zone Zero, PRAGMATA, Cyberpunk 2077, Wuthering Waves and The Witcher 3. Shared Lexirise settings/readings/lookups support 31 study languages; Migaku remains a separate reading mode. Existing game transcripts remain Chinese.

Download a private release ZIP and double-click **Install.cmd**. The optional game-folder popup locates your own installed files, saves locations per PC and preserves automatic discovery. Game assets are never bundled or uploaded. See [installation guide](INSTALL.md), [mobile-friendly installer page](INSTALL.html), [contributing](CONTRIBUTING.md), [agent rules](AGENTS.md) and [release/rollback](RELEASE.md).

The UI adapts to narrow/short windows and high browser/Windows zoom. Hito automatically follows dialogue boxes; capture regions are normalized against physical game-window pixels and local calibration remains per PC.

OCR scales to game-window height across small windows, 4K and ultrawide layouts, and windowed captures exclude title bars/borders. See [OCR resolution support and offline screenshot checks](docs/ocr-resolutions.md).

See [Cyberpunk support and automatic subtitle languages](docs/cyberpunk-support.md) for bilingual-mod compatibility, V voice selection, and the Where Winds Meet limitation.
See [Wuthering Waves support](docs/wuthering-support.md) for the Chinese voice-pack requirement and Rover selection, and [Witcher 3 support](docs/witcher-support.md) for stock/dual subtitle compatibility. Both Witcher 3 and Cyberpunk work without a subtitle mod.

## Detailed behavior (Proxy Transcript companion)

A local, gameplay-first bilingual transcript companion for Zenless Zone Zero,
PRAGMATA, Cyberpunk 2077, Wuthering Waves and The Witcher 3, with game-text capture for Hito's World.

It captures English or Chinese subtitles from the running game, automatically recognizes the language with local Windows OneOCR, matches it against the parallel English and Simplified-Chinese TextMaps, and saves the official pair to a local SQLite transcript.

Three independent regions cover the lower subtitles, upper-right spoken prompts,
and voiced cutscene/comic panels. Within the lower region, wide dark interaction
boxes in normal 3D gameplay are excluded unless an exact original voice mapping confirms the line. White outlined subtitles
drawn directly over the scene are treated as voiced gameplay lines and matched
against the game's OngoingLevel records. The Knock Knock phone interface, Story
Recap, and HDD commission-selection screen are explicitly excluded.

Because these floating gameplay subtitles are brief, the newest confirmed one
remains in **Current line** after it disappears in-game. It stays there until any
new voiced line arrives, keeping the Hanzi available for Migaku without creating
a duplicate History row. Other dialogue presentations keep their live behavior.

Only visible subtitles with a verified original voice mapping are captured. Their official bilingual text appears immediately while the original clip is decoded from the installed game files. The app does not listen to game output, record the headset/speakers, or use live speech detection. Missing mappings are skipped; failed extraction keeps the confirmed text for retry.

Setup installs a local FFmpeg binary through `imageio-ffmpeg` for original game voice conversion.

The matcher also builds a blocklist from the official character-name and speaker-label records. Short standalone HUD actions are ignored, while short spoken replies are accepted when OCR sees them beneath a speaker label. This keeps the log focused on dialogue without maintaining a manual list of characters.

Repeated TextMap lines are suppressed for 60 seconds across all capture regions. If typewriter text first matches a partial sentence and the complete official line appears within five seconds, the existing transcript row and pending audio clip are upgraded in place.

History rows show the speaker in English and Simplified Chinese whenever the
exact game voice path or the on-screen nameplate identifies them. The bilingual
name itself comes from the official TextMaps. Comic bubbles without a nameplate
remain unlabelled rather than being assigned to a guessed speaker.

## First-time setup

Install Python 3.12, Node.js 22 or newer, and Windows Snipping Tool, then open PowerShell in this folder and run (the Codex desktop bundled Python 3.12 can also be used when present):

```powershell
.\scripts\setup.ps1
```

Run setup from the project folder. The app, frontend build, transcript, and TextMap data stay in that folder. Game installations can be on a different drive; the updater discovers their game files separately. Each PC keeps its Python environment, launcher, capture settings, and encrypted Lexirise credential under Local AppData. Setup downloads the TextMaps only when the project does not already contain them.

When copying the folder to another PC, keep the whole `gamesentenceminer` directory (including `data` and `work`) and run `scripts\setup.ps1` there. The launcher and Start menu shortcut are recreated for the new path. The updater locates the running ZZZ executable or a local Steam installation, so game and app drive letters may differ. Headset selection and game volume do not affect subtitle matching or original voice extraction. The DPAPI-encrypted Lexirise key cannot be copied between Windows users. Set it on the other PC with the hidden prompt:

```powershell
& "$env:LOCALAPPDATA\Programs\Proxy Transcript\venv\Scripts\python.exe" -m scripts.set_lexirise_key
```

Start the app from the **Proxy Transcript** Start menu shortcut or `Start Proxy Transcript.cmd` in the project folder. The app and capture service listen only on this PC. `scripts\install-status.ps1` shows local indexing and service status, including percentages. Before first live gameplay, `scripts\check-capture-readiness.py` verifies local OCR and display capture; see `docs\capture-readiness.md` for the results and live game checklist. If this folder is copied to another Windows PC, run setup there again because the Python environment and encrypted API credential belong to this PC.

## Normal use

1. Start a supported game with English or Chinese subtitles and its installed Mandarin voice pack.
2. Double-click `Start Proxy Transcript.cmd`.
3. The companion opens on the portrait monitor to the right of the primary display, or on a connected secondary display such as Duet when no portrait monitor is present.
4. Use **Capture setup** if the live crop contains HUD text or misses part of the subtitle.

The **Game** switch above the transcript keeps each title's History and
Favorites separate. It follows the running game automatically; you can switch
it manually to review the other game's saved lines.

The compact **Reading** switch chooses Migaku (default) or Lexirise. In Lexirise mode, **Reading options** controls Pinyin, Zhuyin, separate tone marks, inline English meanings, and tone colors. Each can appear on unknown words, all words, or be turned off. Tone colors default to Migaku's red/yellow/green/blue/gray mapping and each color can be edited. Tap a word for a built-in definition, or scan its selectable text with Yomitan. These display choices are remembered in the browser and do not send a sentence to a Lexirise deck. The research and implementation details are in `docs/lexirise-reading-mode.md`.

## Hito's World

Hito reads verified Chinese/English text from the running game's `resources/app.asar`, including generated sentences and mixed English/Hanzi tutorial lines. Both the bottom dialogue panel and top message panel appear in Current line and History without requiring recorded audio.

Automatic capture follows the visible message-box borders, so screen resolution and game zoom can change without recropping. Capture setup shows the detected crop. Moving a region slider switches Hito to manual regions; re-enable the automatic checkbox and save to resume box detection. Manual settings belong to this PC and are not synchronized with the project folder.

The game-file catalog refreshes automatically when the running game's archive changes. **Capture setup → Refresh from game** forces a refresh. If an update changes the grammar format incompatibly, the previous catalog stays available and `data/hito/grammar.log` contains the error for a software update.

## PRAGMATA

PRAGMATA's radio dialogue, cinematics, and in-world conversations all use a
centered lower subtitle lane. The companion reads that lane and matches it
against the official English and Simplified-Chinese strings extracted from the
installed RE Engine message archives. Speaker references are resolved from the
same files (for example, `Ken` / `肯`).

Only message families used for spoken conversations and cutscenes are indexed.
A matching subtitle is published when an exact original voice mapping confirms it.
Playback comes directly from its Mandarin Wwise media: conversation `SoundID`
links select individual WEMs, while cinematic subtitle GUIDs and timeline frames
cut sentence-sized clips from the original scene track. Unmapped records are
skipped. The game is never modified.

Fixed Wwise voice layers are combined using their authored gains and delays;
shared radio effects cannot extend playback past the sentence. Identical
English/Chinese lines by the same speaker can reuse a verified official take,
marked internally as `bilingual_alias` (not a claim about which take played).
The September 2026 index has 3,882 audio-linked records out of 3,894 dialogue
records. Credits, sound-effect captions and rejected development strings are
excluded. The remaining records are skipped because their source is absent, has no timeline interval, or uses an unsupported event tree.
`data/pragmata/textmap.json` includes `excluded` and `audio_diagnostics` reports.

On startup, the companion fingerprints PRAGMATA's `re_chunk_*.pak` files. A
changed game build or newer index format is re-extracted and re-indexed in the background while the
web interface continues using the last complete index. The generated files are
kept under `data/pragmata` and atomically replaced after a successful update.
Audio packages are unpacked lazily on first use and cached per game-build
fingerprint, so indexing does not duplicate the full game installation.

The **Speed** control in the footer plays saved voice clips at 1×, 0.85×,
0.75×, or 0.6× while preserving pitch. The choice is remembered by Chrome.

## Send to Lexirise

Use **Lexirise** beside a current sentence or the send icon in History/Favorites.
Nothing is sent automatically. The backend
uploads the available voice clip and creates a Chinese sentence with its English
translation, then adds it to the correct existing deck:

- PRAGMATA → deck 1951.
- Zenless Zone Zero, including agent voices → deck 1950.

The deck is chosen from the saved line's game, not the tab currently open.
Agent Hanzi remains automatic transcription; no English translation is invented.
Original game audio is used when the saved clip has it; otherwise the available
recording is sent and labeled as such. Missing clips must be ready before sending.
Lexirise hosts uploaded audio at an HTTPS URL; the API accepts clips up to 90 seconds.

Sent markers and partial transfer progress survive restarts. Repeated sends of
the same Mandarin sentence to the same deck reuse the export. A lost response
is reconciled against Lexirise before adding another deck entry. Existing study
notes and proficiency are preserved. Previously sent lines remain in Lexirise
when local history is pruned.

The key is stored encrypted for the current Windows user. On this PC, the key
file lives in `%LOCALAPPDATA%\Programs\Proxy Transcript\key.dpapi` so a synced
project can keep different DPAPI keys on different PCs. Existing installations
can still read `data/lexirise/key.dpapi`. The export ledger in `data/lexirise`
is excluded from Git and is not served to Chrome. Other hosts can supply
`LEXIRISE_API_KEY` to the backend environment. To replace a Windows key, call
`save_api_key` from `backend.lexirise` with the local AppData directory; there
is intentionally no browser endpoint exposing or replacing credentials. API
contract: https://lexirise.app/api-reference.

## Automatic updates

The companion opens immediately using its last complete local indexes. A
progress bar in the web interface then checks the upstream ZenlessData metadata,
the bilingual TextMaps, and the installed Mandarin game packages in the
background. New chapter, event, sidequest, floating gameplay, comic, and agent assets are indexed
without blocking the webpage or changing game files. The check repeats every
15 minutes while the companion is running; failures keep the previous complete
indexes active and retry automatically.

The floating-gameplay index reads the installed Ongoing Tips metadata for every
referenced speaker; it is not limited to Wise or Belle. Gender-specific TextMap
variants retain separate original WEMs. New package timestamps and metadata are
noticed at startup and by the recurring background check, then atomically
hot-reloaded without blocking the page.

This updates data and game-derived indexes, not the customized application code
or a dirty Git working tree. A future incompatible game format still requires a
normal software update.

Double-click `Stop Proxy Transcript.cmd` to stop the background services.

## Local data

- PC settings: `%LOCALAPPDATA%/Proxy Transcript/settings.json` (existing `data/settings.json` is imported once)
- Transcript: `data/transcript.db`
- Voice clips: `data/audio`
- TextMaps: `data/textmaps`
- PRAGMATA official index and extractor: `data/pragmata`
- Hito game-text catalog and extraction log: `data/hito`

OCR, subtitle matching, and original voice extraction happen locally. Network access supports data/tool updates and explicit Lexirise actions. Capture is independent of the Windows playback device.

## Subtitle-only capture

Agent-screen handling and the Agents view have been removed because that screen has no subtitles. Legacy agent archives are kept on disk, but the application no longer reads nameplates, recognizes audio, transcribes clips, or rebuilds fingerprint indexes. See `docs/subtitle-only-capture.md` for the current workflow and verification.

## Development

```powershell
# backend
.\.venv\Scripts\python.exe -m backend.main

# interface
npm run dev

# tests
.\.venv\Scripts\python.exe -m pytest -q
```
