# Pair devices and read a transcript

Open the [online companion](https://firebird55.github.io/Game-immersion-toolkit/)
on the receiving phone, tablet or computer. Choose **Receiver**. Reading is the
default view; setup stays in **Connection**, **Library** and **Settings**.

## Share a PC transcript

1. In the Windows desktop companion, select a game and click **Share transcript
   to another device**. The local sharing page opens separately.
2. Click **Share transcript & create offer**. This does not request screen capture.
3. On the receiver choose **Paired PC**, then **Connection → Scan the other
   device's QR**. Allow the camera and local network access when requested.
4. With automatic recovery enabled, the answer returns automatically. Otherwise
   scan the receiver's answer QR back on the sender or transfer its pairing file.
5. Open **Reader**. The latest lines arrive first. **Load older PC history** pages
   backward; new dialogue arrives live. Play **Original voice** on demand.

Keep both devices on the same network and keep the desktop companion and local
sharing page running. No relay for remote-network video/audio is provided. The
signaling service exchanges encrypted connection details only. Receiver favorites
remain local; clearing receiver history never deletes PC data. Unlock the
receiver's own Lexirise key for account actions; the desktop key is never shared.

**Stop** closes access immediately. To resume, create a new offer and pair again.
For interruptions, use **Reconnect** or automatic recovery; the refreshed snapshot
is deduplicated against receiver history. If the companion restarts, reconnect to
refresh the snapshot. Saved local text remains readable while disconnected.

## Two iOS devices with native VDO.Ninja

The gaming iPhone or iPad runs the native VDO.Ninja app. The other iPhone or iPad
runs this static companion, its local OCR, prepared catalog and reader. No PC
service is required during play; exporting an existing catalog is a separate
preparation step. This is an implemented receiver route awaiting physical-device
acceptance, not a verified promise of background capture for every iOS game.

1. On the gaming device install/open native VDO.Ninja. Select **SCREEN**, choose
   **Balanced** initially, and open the iOS broadcast picker. Select
   **VDO.Ninja Screen Recorder → Start Broadcast**, then open the game.
2. Open the app's complete viewer link in the standard viewer on the second
   device first. Verify moving gameplay, readable Chinese subtitles and the
   correct orientation. An iframe loading successfully is not capture evidence.
3. Open this companion on the receiving device. Choose **Receiver → Mobile OCR**,
   then **Connection → Game screen source → VDO.Ninja native iPhone / iPad**.
   Paste the complete HTTPS viewer link, including password and route parameters,
   and tap **Connect native screen**. Unsupported routes are rejected explicitly.
4. Open your game's catalog and optional voice ZIPs in **Library**. Choose the
   actual subtitle language and player voice. Preview/calibrate the crop, then
   tap **Start OCR** and return to **Reader**. Catalog matching and OCR run on
   this receiving device; two confirmed sightings are required for a line.
5. Keep this page visible and the gaming device's broadcast active. **Stop native
   receiver** closes this receiving connection. Stop the iOS broadcast separately
   on the gaming device. If iOS ends it, repeat **SCREEN → broadcast picker →
   VDO.Ninja Screen Recorder → Start Broadcast**. Leave the toolkit receiver
   running: it retries a lost viewer with bounded backoff, and OCR resumes from
   fresh confirmed frames when the same link returns. If the app gives a new
   link, stop the receiver and connect that complete link.

Viewer links can grant access to the stream. They are kept only in this page's
memory, never in settings, history, diagnostic reports or application logs. The
input clears after connection; paste it again after stopping or reloading. Share
the link privately. The hosted viewer and native delivery use external VDO.Ninja
services and may use relay delivery; this route has no local-only or peer-to-peer
guarantee. Existing direct browser pairing remains a separate transport.

The receiver shows actual frame dimensions and safe source status. A first frame
is insufficient to establish motion. An unchanged picture can mean a stationary
scene or interrupted capture; **stalled** does not establish a network failure.
On backgrounding, frame requests/OCR pause and old results are discarded.
Returning creates a new receiving session and waits for a fresh frame. It cannot
restart an iOS broadcast that has ended. Sender lock can stop native broadcasting;
restart it on that device. The still-open receiver retains OCR intent and recovers
automatically when the same stream returns. An explicit receiver Stop cancels
that intent and all recovery. A URL reload or source switch likewise
invalidates old OCR/catalog results without deleting the library or transcript.

The review baseline is App Store **5.0.108**. The **5.0.102** release notes describe
Meshcast viewer delivery, while the screen-share guide also describes direct/WHIP
delivery. The hosted viewer is an external, unpinned dependency; exact native
binary/route compatibility and sustained background behavior must be tested on
the two devices. Follow the complete [60-minute acceptance protocol](mobile-capture-verification.md#native-vdoninja-two-ios-acceptance-60-minutes).

Official references: [native screen-share guide](https://docs.vdo.ninja/guides/screen-share-your-iphone-ipad),
[quality presets](https://docs.vdo.ninja/guides/improving-quality-of-the-native-app),
[App Store version history](https://apps.apple.com/us/app/vdo-ninja/id1607609685).

## Receive a browser-shared game screen for Mobile OCR

1. On the gaming device choose **Sender** and the game, then **Share screen &
   create offer**. Choose the game screen when the browser asks.
2. On the reading device choose **Receiver → Mobile OCR**, select the game and
   open its catalog and optional voice ZIPs in **Library**.
3. Choose **Browser screen pairing** in **Connection** and use the same QR/answer flow above.
4. In **Library**, choose the subtitle language and player voice where applicable,
   then **Start OCR**. Return to **Reader**. A small video remains visible so frame
   processing is not disrupted by scrolling through the transcript.
5. Use calibration only if the subtitle region needs adjusting. Text is matched
   against verified catalog entries on this device; ambiguous scenes are skipped.

The PC can be off after exporting the library. Voice packs must be reselected
after reopening. Keep the receiving page open and a selected USB drive connected.
Browser backgrounding suspends OCR; returning resumes it when the stream survives.
Use **Resume screen sharing** on the sender if the browser ended its capture.

## Browser limitations and recovery

Safari may have no screen-sharing API, or browser capture may stop when the game
opens. Installing the page on the Home Screen does not change this. Use the
native VDO.Ninja route above for system-wide iOS screen broadcast, or a browser
sender that supports capture. Successful pairing does not prove game capture.

If scanning is difficult, use **Larger QR**. Multi-frame codes show progress and
can be paused/stepped. Pairing messages contain local connection details; share
them privately. Camera access ends after scanning or leaving the page. Switching
sources stops capture/OCR and cameras without deleting stored data.

For tests, enable **Settings → Developer mode** and follow the
[developer guide](online-companion-development.md). Ordinary use needs no
observation form or test report.
