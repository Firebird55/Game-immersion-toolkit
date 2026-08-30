# Proxy Transcript

A local, gameplay-first bilingual transcript companion for Zenless Zone Zero.

It captures the English subtitle region from the running game, recognizes it with local Windows OneOCR, matches it against the parallel English and Simplified-Chinese TextMaps, and saves the official pair to a local SQLite transcript.

The matcher also builds a blocklist from the official character-name and speaker-label records. Short standalone HUD actions are ignored, while short spoken replies are accepted when OCR sees them beneath a speaker label. This keeps the log focused on dialogue without maintaining a manual list of characters.

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
- TextMaps: `data/textmaps`

All OCR and matching happens locally. The only network operation is downloading or updating the TextMap JSON files.

## Development

```powershell
# backend
.\.venv\Scripts\python.exe -m backend.main

# interface
npm run dev

# tests
.\.venv\Scripts\python.exe -m pytest -q
```
