# Two-device mobile capture test

The mobile companion retains this capture/reconnect test alongside its local-file
library, OCR, bilingual transcript and original-voice features. Follow
[mobile library setup](mobile-library.md) for those features. Mobile account
integration and a native iPad sender remain outside this build.

## Open on iPad and phone

The public bookmark is [the mobile preview](https://firebird55.github.io/Game-immersion-toolkit/).
Tap **Reload latest** before pairing and compare the displayed commit on both
devices. Selecting a game does not claim capture/OCR or complete catalog coverage:
open an exported library and verify actual moving gameplay and recognized scenes.

## Intended setup: iPad game → iPhone receiver

The iPad is the **sender**, running the game. The iPhone is the **receiver**,
showing the transcript panel and received video. The devices' roles do not reverse
when capture is unavailable.

1. Open the bookmark on iPad and iPhone on the same Wi-Fi; tap **Reload latest**.
2. On iPad choose **Share screen** and the game. Check **Screen capture API**.
3. If unavailable, this browser page cannot send the game. A native iPad capture
   helper is still required and is not included. Do not switch the iPad to receiving
   as a substitute for this setup. A Home Screen shortcut does not add capture.
4. If available, tap **Share screen & create offer**. On iPhone choose
   **Receive screen → Scan the other device’s QR** and point at the sender’s QR.
   Typical offers and replies now use one static, compact QR. Use **Larger QR**
   and keep the code centred in the camera; the message is accepted automatically.
   Reload both devices before testing the new QR format. The new scanner can
   still read older QR messages.
5. With **Automatically recover the connection when returning** enabled, the
   answer returns through the recovery service automatically. No second scan is
   needed. With direct pairing selected, scan the iPhone’s answer QR back on the
   sender. Both cameras stop after scanning.
   Exceptionally large messages fall back to balanced QR frames changing every
   three seconds. If the scanner reads only some frames, it lists the missing
   numbers: use **Pause QR rotation** and **Next QR** on the displaying device
   to hold each missing frame. Stopping and restarting the camera keeps partial
   progress on the current page. A page reload needs a fresh scan.
   Copy/paste and pairing files remain available if a device has no camera.
   Short codes require a hosted signaling service and are not part of this direct
   pairing flow. Switch the iPad into the game, keep the iPhone page open and start its **15-minute observation**.
   Verify actual moving gameplay after switching apps; download the report.

Capture availability alone does not prove background game capture. Browser OCR
uses an explicitly opened library and only verifies supported bilingual matches.

## Recover a frozen connection

Returning to the page resumes paused playback automatically. With recovery
enabled, both devices also reconnect to the Cloudflare service and exchange
fresh offers/answers after a failed connection, with bounded retries. Keep both
pages loaded: reloading loses the in-memory pairing key and needs a fresh scan.
The opened library, transcript, favorites and running observation survive
connection recovery. If screen sharing ended, tap **Resume screen sharing** on
the sender to grant capture again; the paired phone reconnects automatically.
The browser cannot grant screen-capture permission without that gesture, force
a suspended operating-system capture to run, or add capture support to iPad Safari.

If using direct pairing, or if the recovery service is unavailable, use this flow:

1. Return to Safari on iPad. Check **Capture**: if it is **live**, tap
   **Reconnect & create new offer**. This keeps the existing capture permission
   and track; it replaces the connection only. A muted track is kept open too,
   but reconnect cannot force the browser to resume a suspended capture.
2. Transfer the fresh iPad offer to iPhone and tap **Accept message**. Transfer
   the new iPhone answer back to iPad and accept it. Older offers and answers
   are rejected so they cannot replace the current connection accidentally.
3. Switch back into the game. Confirm moving gameplay resumes on iPhone.
   The running observation, counts, result and notes are retained, including
   the interruption. **Stop** ends capture and observation. A new capture after
   Stop is a new session; Stop the receiving test before accepting that offer.
4. Download a report on **both** devices after the failure and after recovery.
   Note whether only the connection failed, the capture was muted/ended, or the
   iPad page returned from the background. If capture ended, use **Resume screen
   sharing**, then exchange its fresh offer and answer for direct pairing.

Reload the latest build on both devices before the next test. Answers from older
preview builds do not carry the new pairing identity and cannot complete a new
sender's offer. Video remains on the direct local connection, without STUN or
TURN media relays. The optional Cloudflare service exchanges encrypted connection
details only; it does not receive game video, voices or libraries. Service
sessions expire after four hours and remain available while the PC is off.
See [operating the recovery service](mobile-recovery-service.md).

## Optional PC streaming check

Use **PC → iPhone** to check the receiving phone and pairing independently while
the native iPad sender is unfinished. This does not validate capturing an iPad game.

1. Open the bookmark in Chrome/Edge on the PC and Safari on the iPhone, on the same Wi-Fi.
2. On the PC select **Share screen** and the game, then **Share screen & create offer**.
   Choose the game window or monitor in the browser permission dialog.
3. On iPhone select **Receive screen**. Transfer the PC offer privately, paste/open
   it, and tap **Accept message**.
4. Transfer the generated answer back to the PC and accept it there.
5. Keep the iPhone page open. Start **15-minute observation** on iPhone and play on PC.
   Verify moving game content, dialogue and cutscenes; rotate the iPhone and return
   to Safari. Stop, select the observed result, and download the report.

For normal development, use the [GitHub preview cycle](mobile-development.md).
It provides a stable public HTTPS bookmark from this public repository. The PC
does not need to serve the page or install a certificate on your devices. The
local HTTPS setup below remains available for offline or unpublished testing.

The test is available at `/mobile-capture/index.html` from the frontend, or with
the standalone server below. Screen sharing requires a secure context. Plain
HTTP to a PC's LAN address is insufficient. Bypassing a certificate warning is
not a substitute for a trusted certificate.

Use a locally trusted certificate with the PC's LAN address in its subject
alternative names. For example, if mkcert is already installed:

```powershell
mkcert -install
mkcert -cert-file work/mobile-cert.pem -key-file work/mobile-key.pem localhost 127.0.0.1 <PC-LAN-IP>
node scripts/serve-mobile-capture.mjs --cert work/mobile-cert.pem --key work/mobile-key.pem
```

Create `work` first if it does not exist. Install **only the public root certificate**
from `mkcert -CAROOT` on your own iPad and iPhone and explicitly enable its trust
in Settings. Never transfer the CA private key or the server private key. Certificates
and keys stay outside Git. A trusted certificate for a domain you own is another
option. Certificate setup is manual; the server does not install a trust root.

Open the printed `https://<PC-LAN-IP>:8443/` address on both devices. Allow this
server through the Windows firewall on the private network if necessary. Keep the
devices on the same Wi-Fi without client isolation. The PC serves the static page
during setup; screen frames travel directly between the mobile devices. Keep the
server running until both pages have loaded and pairing is complete.

1. On iPad choose the game, then **Share screen & create offer**. If the API is
   unavailable, report that result; installing a home-screen shortcut does not add it.
2. Transfer the offer privately to the phone, using copy/paste or the pairing file.
3. On the phone select its receiving role, paste/open the offer and accept it.
4. Transfer the phone's answer back to the iPad and accept it there.
5. Switch the iPad into the game. Confirm the phone preview shows the actual game.
6. Start the 15-minute observation on the phone. Keep the phone page foregrounded.
   Exercise dialogue, cutscenes, rotation and a return to Safari. Repeat separately
   for ZZZ and Wuthering Waves; stop and pair again between tests.
7. Select the observed result and download a report on the phone. Download an
   iPad report too if helpful; its visibility events may explain interruptions.

## Interpret the result

Reports contain capability information, user-agent, connection events, delivered
frame counts, low-resolution image change counts, dark-image samples, and your
notes. They also include track live/muted/ended state, connection/ICE/signaling
events, and up to 120 numeric RTC samples taken every two seconds. Sender source
frame counters, when provided by the browser, help distinguish capture producing
frames from the connection sending them; receiver counters describe incoming and
decoded frames. Attempt numbers separate counters from replacement connections.
No screenshots, pairing descriptions/identities, track/device identifiers,
credentials or network addresses are exported. Notes are user-provided; avoid
entering sensitive details. Reports are downloaded locally and are not uploaded.

Page visibility, pagehide/pageshow, freeze/resume and online/offline events are
recorded when the browser exposes them. Abrupt suspension or termination may not
emit an event. Capture API availability is detected on each device; a browser
support table cannot establish whether a particular iPad can capture a game in
the background. Inspect actual gameplay and both reports before claiming support.
Reports remain in memory until you download them; closing or losing the page
can discard an undownloaded report. See the [WebRTC connection-state rules](https://www.w3.org/TR/webrtc/#dom-rtcicetransportstate)
and [capture mute/end behavior](https://www.w3.org/TR/screen-capture/#closed-and-minimized-display-surfaces)
for the distinction between a recoverable connection and an ended capture.

Frame delivery and image changes do not prove that the game was captured. A
stationary scene can have no image changes; a stream can deliver repeated or black
frames. Review the moving game preview and the observation report together.
The test never automatically claims background capture succeeded.

Proceed to browser OCR and catalog matching only after actual-device evidence
confirms 15 minutes of usable capture for the target game. If sharing is unavailable,
freezes, captures only Safari, or produces black game content, stop this approach
and report it. A native iPad capture helper with a browser phone panel is the next
architecture to evaluate; it is not implemented by this milestone.

## Checks

`node --test tests/mobile-capture.test.mjs` covers pairing identity validation,
privacy of RTC/track diagnostics, frame-stall and black-image detection.
`node scripts/mobile-capture-e2e.mjs` checks
the actual page in Chromium and Firefox, mobile layouts, permission failure,
malformed/stale pairing, reconnect without requesting capture again, retained
observation evidence, private diagnostics, stopping during an unfinished offer,
ended capture and a synthetic peer-to-peer video connection. Synthetic tests
cannot establish iPad background capture or game compatibility.
