# Proxy Transcript

A local, gameplay-first bilingual transcript companion for Zenless Zone Zero.

It captures English text from the running game, recognizes it with local Windows OneOCR, matches it against the parallel English and Simplified-Chinese TextMaps, and saves the official pair to a local SQLite transcript.

Three independent regions cover the normal dialogue box, upper-right spoken prompts, and voiced cutscene/comic panels. The last region only activates while speech is detected. The Knock Knock phone interface, Story Recap, and HDD commission-selection screen are explicitly excluded.

Windows loopback audio is kept only in a short in-memory rolling buffer. When a matched line contains speech, the companion uses GameSentenceMiner's local FireRedVAD model to trim away the music-only lead-in and tail, saves a compact MP3 clip, and adds playback controls to that row in the web interface. It does not make a continuous recording.

The matcher also builds a blocklist from the official character-name and speaker-label records. Short standalone HUD actions are ignored, while short spoken replies are accepted when OCR sees them beneath a speaker label. This keeps the log focused on dialogue without maintaining a manual list of characters.

Repeated TextMap lines are suppressed for 60 seconds across all capture regions. If typewriter text first matches a partial sentence and the complete official line appears within five seconds, the existing transcript row and pending audio clip are upgraded in place.

## First-time setup

Open PowerShell in this folder and run:

```powershell
.\scripts\setup.ps1
```

The TextMap download is approximately 100 MB and is stored locally under `data/textmaps`.

## Normal use

1. Start Zenless Zone Zero with English subtitles.
2. Double-click `Start Proxy Transcript.cmd`.
3. The companion opens on the portrait monitor to the right of the primary display.
4. Use **Capture setup** if the live crop contains HUD text or misses part of the subtitle.

Double-click `Stop Proxy Transcript.cmd` to stop the background services.

## Local data

- Settings: `data/settings.json`
- Transcript: `data/transcript.db`
- Voice clips: `data/audio`
- TextMaps: `data/textmaps`

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
