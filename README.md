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

After a game update changes the Mandarin packages, rebuild the library and
fingerprints using a matching AvatarBaseTemplateTb data dump:

```powershell
.\.venv\Scripts\python.exe -m scripts.index_agent_voices --game-data "F:\SteamLibrary\steamapps\common\Zenless Zone Zero\games\ZenlessZoneZero Game\ZenlessZoneZero_Data" --avatars "work\voice-assets\AvatarBaseTemplateTb.json"
.\.venv\Scripts\python.exe -m scripts.build_agent_fingerprints
```

Restart the companion after rebuilding. Initial indexing is resumable and runs
separately from capture. The ASR model is the official
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
