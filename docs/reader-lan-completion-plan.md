# Reader and LAN completion plan

Status: remaining implementation. Companion to the
[R19 completion plan](r19-completion-plan.md), especially C/E's retained-origin,
browser and update continuity, and [issue #61](https://github.com/Firebird55/Game-immersion-toolkit/issues/61).
Use the existing desktop/static frontend and mobile reader; no second frontend
server or duplicated reading engine is required.

## Reading surface

- [ ] Use equal current/history source and translation font sizes, with readable
  ruby/gloss scaling and selectable text in independent Browser Extension mode.
- [ ] Join current and previous lines with minimal side padding and one usable
  scroll area; remove the restrictive nested history viewport. Show a subtle
  separation only when history scrolls away from the current line.
- [ ] Remove the OCR/TextMaps/session tiles, Saved transcript label, separate
  History button and intervening layout elements.
- [ ] Show Earlier lines centered only for empty history.
- [ ] Put one Favorites/History toggle immediately to the left of Speed in the
  lower controls; the label names the destination view.
- [ ] Present game updates and transient messages outside the reading layout.
  An update appearing or disappearing must not change the current line's position.
- [ ] Use exactly: "Matched game dialogue appears here."
- [ ] Keep settings, pause, calibration, original audio and per-line favorites
  accessible while reducing the space occupied by secondary controls.

## One desktop origin on the LAN

- [ ] Remove client-side loopback constants in favor of one endpoint resolver.
  Preserve the existing local browser origin and storage keys for installed users.
- [ ] Serve UI/API/WebSocket routes through the existing source router and R19
  static host. The frozen build must not reintroduce Node/Wrangler as a prerequisite.
- [ ] Display a usable local-network URL/port and allow a phone/tablet to open it.
  Keep protected account/setup routes protected and validate origin/host handling.
- [ ] Add Connect to desktop to the mobile player; accept an address and open
  the same desktop Web UI. Preserve the independent mobile/offline mode.
- [ ] Handle disconnect/reconnect without losing transcript or favorite state.
  Show connection status compactly without moving the text.
- [ ] Use safe-area insets, large default text, compact touch controls and minimal
  margins on iPhone, iPad and Android portrait/landscape screens.

## Checks and R19 compatibility

- [ ] Chromium/Firefox desktop at 100%, 150% and 200% zoom: equal computed text
  sizes, no horizontal overflow, usable history, toggle and pagination.
- [ ] WebKit/Chromium phone/tablet layouts: touch, safe areas, long captions and
  lookup overlays. Keep physical-device evidence distinct from browser emulation.
- [ ] Assert zero current-line displacement as game-update state changes.
- [ ] Exercise desktop plus second LAN client, reload/reconnect, playback and
  favorites; reject unintended cross-origin operations.
- [ ] Test the built static R19 frontend and the source frontend using the same
  assertions; retain browser storage/userscript identity through restart/update.
- [ ] Run real account verification read-only; account-write cases use mocks.
  Shared-component changes are published in the shared repository and synchronized
  to both consumers; never modify vendor source in this repository.

Browser tests are behavioral/layout assertions. The supplied game screenshots
belong only to [capture regressions](capture-regression-completion-plan.md).
