# Reader and LAN completion plan

Status: reader and LAN implementation complete; final installed artifact and physical-device acceptance remain. Companion to the
[R19 completion plan](r19-completion-plan.md), especially C/E's retained-origin,
browser and update continuity, and [issue #61](https://github.com/Firebird55/Game-immersion-toolkit/issues/61).
Use the existing desktop/static frontend and mobile reader; no second frontend
server or duplicated reading engine is required.

## Reading surface

- [x] Use equal current/history source and translation font sizes, with readable
  ruby/gloss scaling and selectable text in independent Browser Extension mode.
- [x] Join current and previous lines with minimal side padding and one usable
  scroll area; remove the restrictive nested history viewport. Show a subtle
  separation only when history scrolls away from the current line.
- [x] Remove the OCR/TextMaps/session tiles, Saved transcript label, separate
  History button and intervening layout elements.
- [x] Show Earlier lines centered only for empty history.
- [x] Put one Favorites/History toggle immediately to the left of Speed in the
  lower controls; the label names the destination view.
- [x] Present game updates and transient messages outside the reading layout.
  An update appearing or disappearing must not change the current line's position.
- [x] Use exactly: "Matched game dialogue appears here."
- [x] Keep settings, pause, calibration, original audio and per-line favorites
  accessible while reducing the space occupied by secondary controls.

## One desktop origin on the LAN

- [x] Remove client-side loopback constants in favor of one endpoint resolver.
  Preserve the existing local browser origin and storage keys for installed users.
- [x] Serve UI/API/WebSocket routes through the existing source router and R19
  static host. The frozen build must not reintroduce Node/Wrangler as a prerequisite.
- [x] Display a usable local-network URL/port and allow a phone/tablet to open it.
  Keep protected account/setup routes protected and validate origin/host handling.
- [x] Add Connect to desktop to the mobile player; accept an address and open
  the same desktop Web UI. Preserve the independent mobile/offline mode.
- [x] Handle disconnect/reconnect without losing transcript or favorite state.
  Show connection status compactly without moving the text.
- [x] Use safe-area insets, large default text, compact touch controls and minimal
  margins on iPhone, iPad and Android portrait/landscape screens.

## Checks and R19 compatibility

- [ ] Chromium/Firefox desktop at 100%, 150% and 200% zoom: equal computed text
  sizes, no horizontal overflow, usable history, toggle and pagination.
- [ ] WebKit/Chromium phone/tablet layouts: touch, safe areas, long captions and
  lookup overlays. Keep physical-device evidence distinct from browser emulation.
- [x] Assert zero current-line displacement as game-update state changes.
- [x] Exercise desktop plus second LAN client, reload/reconnect, playback and
  favorites; reject unintended cross-origin operations.
- [ ] Test the built static R19 frontend and the source frontend using the same
  assertions; retain browser storage/userscript identity through restart/update.
- [ ] Run real account verification read-only; account-write cases use mocks.
  Shared-component changes are published in the shared repository and synchronized
  to both consumers; never modify vendor source in this repository.

Browser tests are behavioral/layout assertions. The supplied game screenshots
belong only to [capture regressions](capture-regression-completion-plan.md).

Reader validation: production frontend in Chromium, Firefox and WebKit; 28
viewport/DPR cases including phone landscape and 150%/200% equivalent CSS
viewports. Assertions cover equal typography, document scrolling, favorites,
pagination, update displacement, empty history and oversized current captions.
Native browser validation on 2026-10-30 used installed Edge 156.0.4314.50,
Windows 150% DPI and actual browser zoom controls at 100% and 150%.
Both caption areas retained the same 27px computed font size, with no horizontal
overflow; history used document scrolling. Favorites switched to seven authored
saved rows and the button changed to History. A game update and its open status
popover caused exactly zero current-caption displacement. Screenshots and the
measurement receipt remain in ignored local output. Native Firefox/200% zoom and
physical phone/tablet acceptance remain separate from viewport emulation.

LAN validation: the actual Python gateway serves paired Chromium, Firefox and
WebKit clients over a private interface. The same assertions exercise the built
source frontend and verified R19 static frontend: shared favorites, original
audio byte ranges, live WebSockets, retained pairing and runtime activation.
Chromium/Firefox also decode the owned MP3 fixture. Windows WebKit rejects even
the local MP3 blob; its transport/layout checks pass while native playback remains
unavailable in that test engine. Physical Safari/iPhone/iPad testing remains open.
The mobile player's Connect to desktop form opens this same paired reader.
Host/Origin validation, restricted host account/runtime operations and short-lived
invitation codes preserve the loopback backend boundary. Phone sessions expire
after 24 hours and return to pairing when the next snapshot is unauthorized.

Source recovery validation also covers the real gateway: owned frontend/router/
backend crashes, concurrent launchers, failed publication cleanup and preservation
of the single capture owner. Update completion waits for the gateway to acknowledge
the candidate API and frontend ports; an old healthy response is insufficient.
Running/paused updates, capture resumed during preparation/quiesce and failed
candidates passed with authored services. The initial selected run caught stale
mobile navigation assertions; the corrected affected scenarios and remaining
Windows checks passed separately, rather than treating that failed aggregate as
a full passing run. Final branch/release gates still remain.
