# Game capture readiness on this PC

Checked 27–28 September 2026. Run `scripts\check-capture-readiness.py` with the Proxy Transcript virtual environment after any display, Windows Snipping Tool, or Python environment change.

## Result

The native OCR, screenshot/crop, FireRedVAD, audio conversion, and official voice extraction paths pass local checks. The local backend and website responded successfully, and the ZZZ TextMap reports **427,596 indexed bilingual entries**. ZZZ was briefly visible at `1920×1200`; the backend detected its executable and OCR read the resource-update text, but no voiced dialogue was displayed before the game closed. An actual subtitle-to-transcript capture remains to be checked during gameplay.

The game moved from `F:` to the USB drive `E:`. The automatic voice refresh rebuilt a current manifest from 84 USB source files with **56,650 exact Mandarin line mappings**. A saved ZZZ line was decoded to a 116,108-byte MP3, and FireRedVAD identified its speech intervals. The initial installation lacked FFmpeg, which prevented original voice playback; setup now installs `imageio-ffmpeg` for both this and future PCs. Windows loopback produced nonzero audio samples on the currently selected BOOM 3 output. AirPods were selected and the loopback stream opened successfully earlier, but they are disconnected now, so a post-reconnect sample check remains.

The audit uncovered a missing native OneOCR installation that would have broken OCR as soon as a game window appeared. The three native files from this PC's installed Windows Snipping Tool were copied into the current user's `.config\oneocr` folder. `scripts\setup.ps1` now installs and initializes them automatically on future setup runs. A synthetic English subtitle was recognized exactly as **“Enemies incoming!”**.

The audit also found that the FireRedVAD voice model was absent. This would have made the app discard OCR matches because it requires speech confirmation. The [official FireRedVAD model and normalization data](https://github.com/FireRedTeam/FireRedVAD/tree/main/pretrained_models/onnx_models) are now in `assets\fireredvad` on the USB stick. The backend loads them from the project, with the old GameSentenceMiner location only as a fallback. Setup downloads the pinned files if needed and checks their SHA-256 hashes. Model initialization and a silent-audio inference call passed; Windows reported `Speakers (Realtek(R) Audio) [Loopback]`.

## Display and crop checks

The Python capture process uses physical pixels for both Win32 game-window bounds and `mss` screenshots. A visible Chrome window on Duet reported `(1920, 0, 1488, 2206)`, matching Duet's physical monitor area `(1920, 0, 1488, 2266)` apart from the taskbar. Thus the Windows 125% scaling did not introduce a coordinate mismatch in the observed window and screenshot APIs.

The primary game display is `1920×1200` at `(0, 0)`; Duet is `1488×2266` at `(1920, 0)`. Both monitors returned 100×100 screenshot probes. The default normalized crops mapped to the primary as follows:

| Channel | Physical crop |
| --- | --- |
| ZZZ dialogue | `(154, 804)` at `1613×300` |
| ZZZ top-right tip | `(1190, 18)` at `710×228` |
| ZZZ cinematic | `(77, 72)` at `1766×1056` |
| PRAGMATA subtitle | `(365, 912)` at `1190×264` |

Each crop is within the primary display. The backend selects a visible, nonminimized game window by executable name and computes these regions from that window's own bounds, so moving the game to another monitor or using a different resolution recalculates the crop. The frontend on Duet is not selected as a game window.

## First live game check

1. Launch Proxy Transcript from Start and open the game in a visible window. If the captured image is black, use the game's borderless/windowed display mode and retry.
2. Confirm the footer changes from “Waiting for …” to a scanning or matched state. Open **Capture setup** to inspect the live preview for dialogue, tip, and cinematic regions. Move the normalized region controls only if the subtitle is outside the preview.
3. Display an English voiced subtitle twice long enough for the two-frame stability check. Confirm its English and official Chinese TextMap line appear in Current line or History. The app purposely waits for a voiced match; an unvoiced/menu line may be ignored.
4. If capture stays empty, run `%USERPROFILE%\AppData\Local\Programs\Proxy Transcript\venv\Scripts\python.exe scripts\check-capture-readiness.py` from `E:\gamesentenceminer` and inspect `/api/status` for `capture.phase` and `capture.last_error`.

The preflight verifies native OCR, FireRedVAD inference, loopback device discovery, screen capture, display geometry, and local service readiness. It cannot prove that this game's rendering mode exposes frames to `mss`, that its subtitles fall in the configured regions, or that its actual audio reaches the selected Windows playback device until the game runs.
