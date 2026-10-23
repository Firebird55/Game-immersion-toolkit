# Native iOS screen source implementation plan

Status: implementation and local automated checks complete; physical two-device acceptance remains pending. The draft PR records final packaged-build and hosted check results. Public upstream baseline: `df2f38a80dcc0e8818f0cc9c59db51e5edf929b8` (2026-10-23), including merged PRs #26 and #27. No release or deployment is part of this change.

## Decision and boundaries

Device 1 runs the native VDO.Ninja app's SCREEN broadcast; device 2 runs the static toolkit receiver, local OCR, catalog and reader. No desktop service is required for this receiving route. Existing browser pairing, QR, paired-PC transport, Chinese transcripts, independent Migaku mode, calibration and voice ZIPs remain supported.

Use a bounded iframe frame bridge initially: the official viewer handles its native transport and the adapter requests programmable frames through `getVideoFrame` with `cib` correlation. Inspect the currently served implementation before fixing the response schema and supported URL forms. A visible iframe alone is not success. Cross-origin DOM reads are forbidden. Keep the complete accepted viewer URL, including password and supported server/route parameters; reject unsupported URLs explicitly rather than stripping routing information. Accept only reviewed official HTTPS viewer/service routes, never arbitrary external endpoints. No capture/camera/microphone permission is granted to the viewer.

The SDK direct `view()` and a WHEP receiver are different transports. Do not add an SDK dependency unless a published, pinned release demonstrably supports the selected native route. This design adds no SDK package; the official hosted viewer remains an external, unpinned service, and that compatibility limit must be documented and tested. App Store 5.0.108 is current at review; 5.0.102 notes Meshcast viewer delivery while the screen guide also describes direct/WHIP delivery. Native binary compatibility and background stability require physical-device acceptance.

## Shared contract (reviewed by both implementers)

`frame-source.mjs` defines one source with `connect(options)`, `disconnect()`, `dispose()`, `subscribe(listener)`, `getState()` and `readFrame({signal} = {})`. State has an opaque `sessionId`, `status` (`ready`, `connecting`, `live`, `stalled`, `reconnecting`, `ended`, `error`, `paused`), dimensions, last frame timestamp and a safe user message. A successful `readFrame` returns `{sessionId, sequence, timestamp, width, height, image, release()}`; `image` is drawable by canvas. No fresh frame returns `null`. Timestamp means receiver observation time, not capture latency. A frame is owned by its consumer until `release`, which is idempotent.

Only one request/decode may be active per source. Each connect has a new opaque identity. Disconnect/dispose invalidate every pending request and decoded frame, remove listeners/timers/iframe or owned tracks, and cannot publish an old result. A cancelled caller may not leave a second request queue. Status uses actual frame progress rather than connection events alone; unchanged screenshots cannot prove live capture. Hidden receivers pause requests/OCR and invalidate pending results. Resume requires a new frame before publication. Resolution changes preserve normalized crop coordinates.

The native sender can stop when the gaming phone locks. While receiving intent remains active, the adapter must automatically recover using the same private viewer link after the broadcast restarts. Bound retry delays, keep only one iframe/connection, renew session identity and discard old frames/OCR during recovery. Preserve OCR intent across temporary outages; explicit receiver Stop/dispose cancels every retry. The receiver cannot start an iOS system broadcast. Test both a real transport outage and an unchanged picture, without presenting the latter as proof of a network failure.

An existing-video adapter wraps the toolkit preview without creating another peer or decoder; capture.js retains its current transport ownership. A synthetic second source demonstrates replacement without exposing VDO objects to OCR. `createReceiverSource(factories)` in `receiver-source.mjs` owns source selection, private in-memory options, cancellation and pause/resume. Its `connect(kind, options)`, `disconnect()`, `pause()`, `resume()`, `dispose()`, `subscribe()`, `getState()` and `readFrame()` methods wrap the source contract above. `capture.js` exports the single receiver controller consumed by `mobile-ui.mjs`; OCR receives only generic frame envelopes. Both implementers cross-reviewed these boundaries and the lifecycle fixes.

## File ownership

- Agent 1: new `public/mobile-capture/frame-source.mjs`, `public/mobile-capture/vdo-source.mjs`, adapter-focused `tests/mobile-frame-source.test.mjs`, `tests/mobile-vdo-source.test.mjs`, and `scripts/mobile-vdo-source-e2e.mjs` if needed. Own URL research, wire protocol, lifecycle and bounded frame delivery. Do not edit existing UI/capture files.
- Agent 2: `public/mobile-capture/mobile-ui.mjs`, `capture.js`, `ocr-pipeline.mjs`, `index.html` body, `style.css`, `interface-copy.mjs`, new `receiver-source.mjs` if needed, UI/OCR tests and `scripts/mobile-source-e2e.mjs`, user docs `docs/mobile-capture.md`, `docs/mobile-capture-verification.md`, `docs/mobile-library.md`. Own source selection, onboarding, stale OCR protection, calibrated frame consumption and browser pipeline tests. Do not edit CSP meta or build scripts.
- Coordinator: this plan and technical decision/evidence document, CSP meta (after HTML handoff), static allowlists/build ordering, check selector and selector tests, Git/commits, dependencies, public audit, compatibility watch, integrated checks and draft PR. No vendor edits.

Both agents review the contract before implementation and then review each other's changes after their owned work. Only the coordinator commits, sequentially after relevant checks, with GitHub noreply identity.

## Steps and acceptance

1. Commit this plan, verify public native viewer/protocol behavior and agree the shared contract. Record supported and unsupported route forms, external dependency limits and hardware assumptions.
2. Implement sources and unit tests for URL rejection, origin/source/schema/session validation, delayed responses, cancellation, timeouts, start/stop, stall/recovery and cleanup.
3. Integrate receiver UI and OCR: native startup instructions, full viewer-link input, meaningful status, crop preview and reader. Abort/invalidate old frame and OCR/match responses on every source/session change and page lifecycle transition. Keep one worker/job and bounded frame retention.
4. Prove moving synthetic frames reach real crop/OCR/catalog matching and the reader. Test interchangeability, stop/restart, late replies, visibility, rotation/resolution and no stale publication. Exercise actual browser postMessage boundaries and malformed messages. Preserve QR/datachannel regression checks.
5. Add only reviewed static modules to build and publication allowlists; verify hashed imports and restrictive iframe CSP. Extend affected-check scenarios to execute new tests, including Chromium, Firefox and WebKit, mobile layouts, Shadow DOM and zoom where affected. Desktop WebKit does not prove iOS broadcast behavior.
6. Run `check:changed` against the recorded upstream baseline, production and mobile builds, `audit:public`, and `lexirise:watch`. Inspect exit 2 compatibility changes without account writes or an unreviewed baseline update. Record timings in ignored `output/checks`. Review each other's work, resolve findings and commit logical changes. Push only after checks; create and attach a draft PR to canonical main, then inspect hosted CI. No merge/release/deployment.
7. Deliver an executable two-device protocol: native sender to standard viewer first, then toolkit receiver plus OCR, about 60 minutes heavy gaming, Balanced first, Chinese legibility, frame interruptions, observed latency, app switching, rotation, locking, Wi-Fi loss, reload and manual broadcast restart. Record device/game/OS/app/preset locally without public captures or private links. If devices are unavailable, clearly leave these physical checks outstanding.

## Sources checked on 2026-10-23

- [App Store native app and release history](https://apps.apple.com/us/app/vdo-ninja/id1607609685)
- [Native screen-share workflow](https://docs.vdo.ninja/guides/screen-share-your-iphone-ipad)
- [Native capabilities and public-source limits](https://docs.vdo.ninja/steves-helper-apps/native-mobile-app-versions)
- [Quality presets and viewer parameters](https://docs.vdo.ninja/guides/improving-quality-of-the-native-app)
- [Iframe frame API](https://docs.vdo.ninja/guides/iframe-api-documentation/iframe-api-basics)
- [SDK versus WHIP/WHEP](https://sdk.vdo.ninja/docs/streaming.html)
