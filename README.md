# Proxy Transcript

A local, gameplay-first bilingual transcript companion for Zenless Zone Zero.

It captures English text from the running game, recognizes it with local Windows OneOCR, matches it against the parallel English and Simplified-Chinese TextMaps, and saves the official pair to a local SQLite transcript.

Three independent regions cover the normal dialogue box, upper-right spoken prompts, and voiced cutscene/comic panels. The last region only activates while speech is detected. The Knock Knock phone interface and Story Recap screen are explicitly excluded.

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

OCR, speech detection, matching, and audio clipping happen locally. The only network operation is downloading or updating the TextMap JSON files. Audio currently follows the default Windows playback device, so keep ZZZ routed to that device.

## Development

```powershell
# backend
.\.venv\Scripts\python.exe -m backend.main

# interface
npm run dev

# tests
.\.venv\Scripts\python.exe -m pytest -q
```
