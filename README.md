# Proxy Transcript

A local, gameplay-first bilingual transcript companion for Zenless Zone Zero
and PRAGMATA.

It captures English text from the running game, recognizes it with local Windows OneOCR, matches it against the parallel English and Simplified-Chinese TextMaps, and saves the official pair to a local SQLite transcript.

Three independent regions cover the lower subtitles, upper-right spoken prompts,
and voiced cutscene/comic panels. Within the lower region, wide dark interaction
boxes in normal 3D gameplay remain excluded as unvoiced. White outlined subtitles
drawn directly over the scene are treated as voiced gameplay lines and matched
against the game's OngoingLevel records. The Knock Knock phone interface, Story
Recap, and HDD commission-selection screen are explicitly excluded.

Because these floating gameplay subtitles are brief, the newest confirmed one
remains in **Current line** after it disappears in-game. It stays there until any
new voiced line arrives, keeping the Hanzi available for Migaku without creating
a duplicate History row. Other dialogue presentations keep their live behavior.

Windows loopback audio is kept only in a short in-memory rolling buffer. When a matched line contains speech, the companion uses its bundled FireRedVAD model to trim away the music-only lead-in and tail, saves an MP3 clip when FFmpeg is available or a WAV clip otherwise, and adds playback controls to that row in the web interface. It does not make a continuous recording.

Setup installs a local FFmpeg binary through `imageio-ffmpeg`, so exact original game voices and recorded clips can be converted without relying on a separate system-wide FFmpeg installation.

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

Run setup from `PROJECT_ROOT/GameSentenceMiner`. The app, frontend build, transcript, and TextMap data stay on D:. The Zenless Zone Zero installation can remain on the Intenso USB stick; the updater discovers its game files separately. This PC keeps its Python environment, launcher, and encrypted Lexirise credential under Local AppData. Setup downloads the TextMaps only when the project does not already contain them.

When copying the folder to another PC, keep the whole `gamesentenceminer` directory (including `data` and `work`) and run `scripts\setup.ps1` there. The launcher and Start menu shortcut are recreated for the new path. The updater locates the running ZZZ executable or a local Steam installation, so game and app drive letters may differ. Connect the desired headphones before launching; capture follows the current Windows WASAPI output and reconnects after an audio-device switch. The DPAPI-encrypted Lexirise key cannot be copied between Windows users. Set it on the other PC with the hidden prompt:

```powershell
& "$env:LOCALAPPDATA\Programs\Proxy Transcript\venv\Scripts\python.exe" -m scripts.set_lexirise_key
```

On this PC, the app is installed on D:. Start it from the **Proxy Transcript** Start menu shortcut or `PROJECT_ROOT/GameSentenceMiner\Start Proxy Transcript.cmd`. The app and capture service listen only on this PC. `scripts\install-status.ps1` shows local indexing and service status, including percentages. Before first live gameplay, `scripts\check-capture-readiness.py` verifies local OCR and display capture; see `docs\capture-readiness.md` for the results and live game checklist. If this folder is copied to another Windows PC, run setup there again because the Python environment and encrypted API credential belong to this PC.

## Normal use

1. Start Zenless Zone Zero or PRAGMATA with English subtitles and Mandarin audio.
2. Double-click `Start Proxy Transcript.cmd`.
3. The companion opens on the portrait monitor to the right of the primary display, or on a connected secondary display such as Duet when no portrait monitor is present.
4. Use **Capture setup** if the live crop contains HUD text or misses part of the subtitle.

The **Game** switch above the transcript keeps each title's History and
Favorites separate. It follows the running game automatically; you can switch
it manually to review the other game's saved lines. The Agents collection is
specific to Zenless Zone Zero.

The compact **Reading** switch chooses Migaku (default) or Lexirise. In Lexirise mode, saved Chinese lines show proficiency colors, pinyin, and inline English meanings for words below the known level. The **Pinyin** control chooses unknown words, all words, or off. Tap a word for a built-in definition, or scan its selectable text with Yomitan. These display choices are remembered in the browser and do not send a sentence to a Lexirise deck. The research and implementation details are in `docs/lexirise-reading-mode.md`.

## PRAGMATA

PRAGMATA's radio dialogue, cinematics, and in-world conversations all use a
centered lower subtitle lane. The companion reads that lane and matches it
against the official English and Simplified-Chinese strings extracted from the
installed RE Engine message archives. Speaker references are resolved from the
same files (for example, `Ken` / `肯`).

Only message families used for spoken conversations and cutscenes are indexed.
A matching subtitle is published only after local voice detection confirms
speech, so credits, HUD labels, menus, and unvoiced text are skipped. Whenever
the game exposes an exact link, playback comes directly from its Mandarin Wwise
media: conversation `SoundID` links select individual WEMs, while cinematic
subtitle GUIDs and timeline frames cut sentence-sized clips from the original
scene track. Windows loopback remains only as a fallback for unmapped lines;
the game is never modified.

Fixed Wwise voice layers are combined using their authored gains and delays;
shared radio effects cannot extend playback past the sentence. Identical
English/Chinese lines by the same speaker can reuse a verified official take,
marked internally as `bilingual_alias` (not a claim about which take played).
The September 2026 index has 3,882 audio-linked records out of 3,894 dialogue
records. Credits, sound-effect captions and rejected development strings are
excluded. Twelve remaining records retain capture fallback because their
source is absent, has no timeline interval, or uses an unsupported event tree.
`data/pragmata/textmap.json` includes `excluded` and `audio_diagnostics` reports.

On startup, the companion fingerprints PRAGMATA's `re_chunk_*.pak` files. A
changed game build or newer index format is re-extracted and re-indexed in the background while the
web interface continues using the last complete index. The generated files are
kept under `data/pragmata` and atomically replaced after a successful update.
Audio packages are unpacked lazily on first use and cached per game-build
fingerprint, so indexing does not duplicate the full game installation.

The **Speed** control in the footer plays story and agent clips at 1×, 0.85×,
0.75×, or 0.6× while preserving pitch. The choice is remembered by Chrome.

## Send to Lexirise

Use **Lexirise** beside a current sentence, the send icon in History/Favorites,
or the button beside an agent voice. Nothing is sent automatically. The backend
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

- Settings: `data/settings.json`
- Transcript: `data/transcript.db`
- Voice clips: `data/audio`
- TextMaps: `data/textmaps`
- PRAGMATA official index and extractor: `data/pragmata`

OCR, speech detection, matching, transcription, and audio clipping happen locally. Network access is used for initial data/model/tool downloads and updates, not for sending audio. Audio follows the default Windows playback device, so keep ZZZ routed to that device.

## Agent voices

The **Agents** tab sits between History and Favorites. While the game's agent
selection screen is visible (keyboard or controller layout), its UI labels are
excluded from story capture. The companion compares loopback audio with a local
fingerprint index of the installed Mandarin soundbanks and verifies candidates
against their original waveforms. Uncertain matches are skipped.

Newly recognized agent-screen voices automatically select **Agents**. Newly
captured voiced dialogue outside that screen selects **History**. Opening a
menu, toggling a favorite, replaying audio in the web UI, and polling old entries
do not change tabs. Missed voice events are recovered when the page reconnects.

Selection voices start immediately, so recognition includes a two-second
pre-roll on entering the agent screen and checks the small nameplate every
capture pass. On a character/screen change, its buffered audio is queued for
recognition with the character identity observed at capture time. Late results
can populate that character's collection without switching away from current
story dialogue. The queue is bounded to protect memory during very rapid changes.

Each heard agent/clip has one persistent entry. Hearing it again increases its
play count and moves that entry to the top. Agent entries are not subject to the
50-line History limit; older entries can be loaded with **Load more**.

Playback uses the complete original game clip, not a cropped music-containing
recording. Hanzi is transcribed locally from that clean clip with SenseVoice and
labelled **Automatic transcription**; it is not guaranteed official dialogue.
The app does not modify the game or read its process memory.

Local agent data is in `data/agent-voices`: `entries.db` (saved entries),
`library.json` (package offsets), `fingerprints.db` and `pcm` (rebuildable index),
`audio` (heard originals), and `model` (local SenseVoice model). Keep `entries.db`
and `audio` together when backing up your collection.

The library is maintained automatically while the companion runs. At startup
and every minute it checks the installed Mandarin soundbanks and streamed audio.
Changed/new clips are indexed in the background; agent recognition pauses during
that work, while story capture continues. Interrupted work resumes, failures
retry, and the last library is replaced only after indexing succeeds. Existing
saved agent entries and their original audio are retained.

New names can be learned from the selected agent's nameplate after two consistent
reads on a confirmed agent screen. This does not require an updated wiki or a
hand-maintained character list. New clips receive local automatic Hanzi
transcription the first time they are recognized. Repacked unchanged audio keeps
its identity; a reused game ID containing different audio gets a new identity.

This supports updates using the current package formats and nameplate layouts;
an incompatible future game format/UI may still require a software update. The
Agents tab displays automatic update/retry status rather than silently claiming
that unavailable audio was recognized.

The following commands remain available for development/recovery, but are not
required after normal game updates:

```powershell
.\.venv\Scripts\python.exe -m scripts.index_agent_voices --game-data "F:\SteamLibrary\steamapps\common\Zenless Zone Zero\games\ZenlessZoneZero Game\ZenlessZoneZero_Data" --avatars "work\voice-assets\AvatarBaseTemplateTb.json"
.\.venv\Scripts\python.exe -m scripts.build_agent_fingerprints
```

Initial indexing is resumable and runs separately from capture. The ASR model is the official
[SenseVoice int8 model](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html),
extracted under `data/agent-voices/model` with its tokens and license.

## Development

```powershell
# backend
.\.venv\Scripts\python.exe -m backend.main

# interface
npm run dev

# tests
.\.venv\Scripts\python.exe -m pytest -q
```
