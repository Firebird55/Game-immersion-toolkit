# Two-device mobile capture test

The mobile companion retains this capture/reconnect test alongside its local-file
library, OCR, bilingual transcript and original-voice features. Follow
[mobile library setup](mobile-library.md) for those features. Developer mode is
needed only for the existing browser diagnostic forms. The native VDO.Ninja
receiver is implemented; physical two-iOS acceptance is still outstanding.

## Native VDO.Ninja two-iOS acceptance (60 minutes)

Use the actual gaming iPhone/iPad and a separate receiving iPhone/iPad. Allocate
60 minutes after installing the apps, preparing a catalog and selecting local
voice ZIPs. Keep power available, use a game scene with repeated dialogue and
Chinese text, and begin with VDO.Ninja **Balanced**. Do not change quality until
the baseline has been recorded. Repeat for every device/game combination claimed.

Keep a private local note with: date, toolkit build commit, both device models,
iOS versions, native VDO.Ninja app version, game/version, subtitle language and
size, preset, network type, receiver Safari or Home Screen, and each timed result.
The reviewed App Store baseline is **5.0.108**; **5.0.102** notes Meshcast delivery,
so record the *route type* used without recording its private link or token.
Never commit links, recordings, account diagnostics, game images or full reports.
An ignored `output/` report or a local Files note is suitable; manual notes are
necessary because the browser observation form measures the browser-pairing
transport, not native VDO delivery.

| Elapsed | Procedure | Record and pass condition |
| --- | --- | --- |
| 00–05 min | On device 1: VDO.Ninja **SCREEN → broadcast picker → VDO.Ninja Screen Recorder → Start Broadcast**, then open the game. On device 2 open the complete link in the **standard VDO.Ninja/Meshcast viewer first**. | Correct game, moving pixels, legible Chinese, no wrong screen/black output. If this fails, record the failure and stop: toolkit OCR cannot repair the native source. |
| 05–10 min | Keep playing a demanding scene in the standard viewer. Include a short dialogue and a cutscene. Estimate end-to-end delay by observing a deliberate menu highlight change on both screens three times. | Record approximate observed delays and interruptions; do not infer latency from receiver timestamps or frame counters. Note thermal warnings and visible quality loss. |
| 10–15 min | Close the standard viewer. On device 2 open toolkit **Receiver → Mobile OCR → Connection → VDO.Ninja native iPhone / iPad**, paste the complete link, connect. Verify dimensions/status before starting OCR. Open catalog/voices, preview crop, choose the subtitle language and **Start OCR**. | A changing preview, correct crop, unique known Chinese/catalog line in Reader; compare text and original voice to the selected local pack. An iframe alone is a failure of programmable-frame acceptance. |
| 15–30 min | Play 15 continuous minutes of demanding gameplay, dialogue and cutscenes. Include at least ten known catalog lines with Chinese characters; count correct, missing and incorrect matches separately. Keep the receiver foregrounded. | No incorrect line accepted; note unsupported/ambiguous scenes separately. Report text legibility, OCR delay and longest visible interruption. No automatic “pass” from delivery counters. |
| 30–35 min | On sender, switch game → native app → game. Rotate landscape/portrait and back where the game permits; change resolution if the app exposes it. Recheck crop. | Correct source returns; normalized crop stays in bounds and follows new dimensions. Recalibration is explicit if the game itself moves subtitles. No old scene appears as a new line after the switch. |
| 35–40 min | Background receiver for 30 seconds; reopen. Lock receiver for 30 seconds; unlock. Then lock sender briefly and unlock. | Receiver hidden state stops OCR; return waits for a new frame. Record whether sender lock terminates broadcast. If ended, restart SCREEN manually using the same link. The still-open toolkit receiver and OCR must resume automatically from fresh frames; iOS broadcast restart itself remains manual. |
| 40–45 min | Turn sender Wi-Fi off for 30 seconds and back on; repeat on receiver. Use a controlled network and note if cellular fallback occurs. | Observe stall/unconfirmed status, recovery time and any required manual reconnect. A static scene is not automatically a network fault. No stale OCR is published during recovery. |
| 45–50 min | Reload the toolkit receiver. Paste current link again and reconnect; reselect voice ZIPs and start OCR. Then tap **Stop native receiver** during dialogue and reconnect. | Link is not restored from storage. Catalog/history/calibration remain; voices require reselection. Stop removes iframe and pending output. New session uses fresh frames. |
| 50–55 min | Stop the actual iOS broadcast on sender. Confirm toolkit detects lack of progress. Restart **SCREEN → broadcast picker → VDO.Ninja Screen Recorder → Start Broadcast** with the same link, leaving toolkit and OCR running. | No false ongoing-live claim from an unchanged frame. Receiver and OCR recover automatically without Connect or Start OCR, with two fresh confirmed sightings. If the native app changes the link, record that separately and reconnect explicitly. After **Stop native receiver**, wait and verify no automatic restart. |
| 55–60 min | Resume demanding gameplay and Chinese dialogue; compare ten new known lines and original voice. Save the private notes. | Record total usable minutes, interruptions/restarts, correct/missing/incorrect matches and the outcome for this exact configuration. |

Acceptance requires both standard viewer delivery and toolkit programmable frames,
crop, OCR/catalog matching and reader to work. State interrupted/failed checks
explicitly, including workarounds and recovery times; do not label the whole
hour uninterrupted if manual restarts were required. Desktop WebKit, synthetic
pixels and an API response are not physical iOS/ReplayKit/background proof. The
native viewer is an external unpinned dependency and delivery may use relays;
these checks do not establish local-only/P2P routing.

## Browser pairing regression protocol

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
3. If unavailable, this browser page cannot send the game. Use the native
   VDO.Ninja protocol above. Do not switch the iPad to receiving
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

Use **PC → iPhone** to check the receiving phone and browser pairing independently
of native VDO.Ninja. This does not validate capturing an iPad game.

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
and report it. Evaluate the native VDO.Ninja route with the separate protocol
above; browser-pairing results cannot establish native-broadcast behavior.

## Checks

`node --test tests/mobile-capture.test.mjs` covers pairing identity validation,
privacy of RTC/track diagnostics, frame-stall and black-image detection.
`node scripts/mobile-capture-e2e.mjs` checks
the actual page in Chromium and Firefox, mobile layouts, permission failure,
malformed/stale pairing, reconnect without requesting capture again, retained
observation evidence, private diagnostics, stopping during an unfinished offer,
ended capture and a synthetic peer-to-peer video connection. Synthetic tests
cannot establish iPad background capture or game compatibility.


## Physical iPhone acceptance test

Automated Chromium, Firefox and WebKit results do not establish physical iPhone
reliability. Perform these checks on the actual phone:

1. Record the displayed build and actual persistence status. Open a catalog plus
   multiple voice packs totaling **at least 2 GiB**. Record opening time/failures.
2. Play a known original clip and favorite its line. Verify audio is local and
   correct, and note playback timing in **Download library test report**.
3. Reload: remembered text/history should return, while playback requests pack
   reselection. Reselect, verify the accessible count, and play again.
4. Reboot the phone, reopen and repeat selection/playback. Retain the Files
   originals throughout. Check recovery if browser caching was unavailable.
5. Once a newer application build is published, stop capture, update, and check
   the same favorite, history and calibration before reselecting voices.
6. Complete **15 minutes** of actual gameplay, with dialogue, a supported special
   presentation, rotation/resolution changes, a pause and manual reconnect.
   Confirm moving game frames, correct bilingual lines and original playback.
7. Fill **Physical device verification** with only observed checks. Download the
   library report and both devices' capture reports. Library reports contain
   timings/counts/storage state and observations, without file names, original
   text, game frames, pairing messages, account details or installation paths.

To test large file providers without game content, contributors can generate
an owned synthetic 2.15 GiB library:

```powershell
python scripts/generate-mobile-storage-test.py
```

Transfer the six generated ZIPs from ignored `output/mobile-storage-test`, open
them and use **Find line → Storage test line 0** to play the small generated tone.
This tests storage access, not real game voices or gameplay OCR.

## Package and contributor checks

Format `proxy-mobile-library-v1` uses STORE-only ZIPs capped at 512 MiB. Catalog
NDJSON entries are approximately 4 MiB, with a 128 MiB/250,000-row total limit.
Manifest and voice-entry limits are 8 MiB and 64 MiB. Stable dialogue/variant,
revision, content and pack identities are retained; clips are deduplicated by
content hash. Readers reject compression, unsafe names, overlapping/truncated
entries, duplicate identities, mismatched packs and failed checksums. Imported
strings are rendered as text.

Run `npm run mobile:check`, repository checks and the public audit. Public CI
uses only authored synthetic text, video and tone fixtures. For private footage:

```powershell
python scripts/prepare-mobile-replay.py
node scripts/replay-mobile-ocr.mjs
```

The existing annotation manifest supplies positive/negative expectations.
Local media, prepared catalogs, images and detailed results stay in ignored
`output/`; the replay server binds only to loopback. Resized/padded footage
checks crop/OCR behavior, not native game UI reflow. Record failures honestly and
never mark a missing scene or chapter verified because packaging succeeded.

See the [0.2.17 verification record](mobile-library-verification.md) for measured
browser results, observed footage misses and the pending physical-device checks.


