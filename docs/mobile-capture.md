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

## Receive a game screen for Mobile OCR

1. On the gaming device choose **Sender** and the game, then **Share screen &
   create offer**. Choose the game screen when the browser asks.
2. On the reading device choose **Receiver → Mobile OCR**, select the game and
   open its catalog and optional voice ZIPs in **Library**.
3. Pair in **Connection** using the same QR/answer flow above.
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

The native iPad capture helper is unfinished and not included. Safari may have no
screen-sharing API, or capture may stop when the game opens. Installing the page
on the Home Screen does not change this. Use a supported sender; do not interpret
successful pairing as proof of background game capture.

If scanning is difficult, use **Larger QR**. Multi-frame codes show progress and
can be paused/stepped. Pairing messages contain local connection details; share
them privately. Camera access ends after scanning or leaving the page. Switching
sources stops capture/OCR and cameras without deleting stored data.

For tests, enable **Settings → Developer mode** and follow the
[developer guide](online-companion-development.md). Ordinary use needs no
observation form or test report.
