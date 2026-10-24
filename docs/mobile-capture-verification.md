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
| 10–15 min | Close the standard viewer. On device 2 open toolkit **Play**, paste the complete link, connect. Verify dimensions/status before starting OCR. Open the library, preview the crop in Settings if needed, and tap **Start playing**. | A changing preview, correct crop, unique known Chinese/catalog line in Reader; compare text and original voice to the selected local pack. An iframe alone is a failure of programmable-frame acceptance. |
| 15–30 min | Play 15 continuous minutes of demanding gameplay, dialogue and cutscenes. Include at least ten known catalog lines with Chinese characters; count correct, missing and incorrect matches separately. Keep the receiver foregrounded. | No incorrect line accepted; note unsupported/ambiguous scenes separately. Report text legibility, OCR delay and longest visible interruption. No automatic “pass” from delivery counters. |
| 30–35 min | On sender, switch game → native app → game. Rotate landscape/portrait and back where the game permits; change resolution if the app exposes it. Recheck crop. | Correct source returns; normalized crop stays in bounds and follows new dimensions. Recalibration is explicit if the game itself moves subtitles. No old scene appears as a new line after the switch. |
| 35–40 min | Background receiver for 30 seconds; reopen. Lock receiver for 30 seconds; unlock. Then lock sender briefly and unlock. | Receiver hidden state stops OCR; return waits for a new frame. Record whether sender lock terminates broadcast. If ended, restart SCREEN manually using the same link. The still-open toolkit receiver and OCR must resume automatically from fresh frames; iOS broadcast restart itself remains manual. |
| 40–45 min | Turn sender Wi-Fi off for 30 seconds and back on; repeat on receiver. Use a controlled network and note if cellular fallback occurs. | Observe stall/unconfirmed status, recovery time and any required manual reconnect. A static scene is not automatically a network fault. No stale OCR is published during recovery. |
| 45–50 min | Reload the toolkit receiver. Paste current link again and reconnect; reopen the library and tap Start playing. Then tap **Disconnect screen** during dialogue and reconnect. | Link is not restored from storage. Catalog/history/calibration remain; voices require reselection. Stop removes iframe and pending output. New session uses fresh frames. |
| 50–55 min | Stop the actual iOS broadcast on sender. Confirm toolkit detects lack of progress. Restart **SCREEN → broadcast picker → VDO.Ninja Screen Recorder → Start Broadcast** with the same link, leaving toolkit and OCR running. | No false ongoing-live claim from an unchanged frame. Receiver and OCR recover automatically without Start playing, with two fresh confirmed sightings. If the native app changes the link, record that separately and reconnect explicitly. After **Disconnect screen**, wait and verify no automatic restart. |
| 55–60 min | Resume demanding gameplay and Chinese dialogue; compare ten new known lines and original voice. Save the private notes. | Record total usable minutes, interruptions/restarts, correct/missing/incorrect matches and the outcome for this exact configuration. |

Acceptance requires both standard viewer delivery and toolkit programmable frames,
crop, OCR/catalog matching and reader to work. State interrupted/failed checks
explicitly, including workarounds and recovery times; do not label the whole
hour uninterrupted if manual restarts were required. Desktop WebKit, synthetic
pixels and an API response are not physical iOS/ReplayKit/background proof. The
native viewer is an external unpinned dependency and delivery may use relays;
these checks do not establish local-only/P2P routing.

## Library and retained PC acceptance

On a physical iPhone, select a complete library larger than 2 GiB from On My
 iPhone and from the intended cloud/USB provider. Confirm the selected name and
Voices ready status remain after the native picker resets. Read English subtitles,
match their catalog lines and hear Mandarin audio only after tapping Play voice.
Reload, reopen the same file and repeat playback. Confirm history, favorites and
calibration survive. Cancel a replacement and try a damaged file; the working
library must remain usable. A legacy voice-only selection without its catalog
must explain which catalog is missing.

In Settings, choose Paired PC and pair with the desktop transcript sender. Verify
history, pagination, tap-to-play and reconnect after a dropped peer. Stop must
cancel automatic recovery. The mobile Play page must never ask for browser
screen capture or load PC pairing until it is selected.

Automated fixtures cover source validation, frame bounds, stale OCR invalidation,
ZIP64 range reads, one-file import, original voice playback, reloads, zoom,
retained PC transport and encrypted relay recovery. Physical Files access and
native ReplayKit endurance are still unverified until this protocol is performed.
