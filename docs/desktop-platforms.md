# Desktop capture on each platform

The desktop host, transcript browser and LAN reader share one implementation.
Native discovery supplies the game window and display coordinates; game readers
continue using the same capture, locale, text and original-voice services.

## Game integration scope

The maintained Windows game integrations are listed in the language matrix. Six
live-service games are also targets for independent online preparation and
original playback on Linux, macOS and Android. Every other game integration
is Windows only, including Cyberpunk 2077 and Death Stranding. The generated
matrix and desktop Setup read the same list and per-game Windows preparation
status. [Game capability data](../public/mobile-capture/games-data.json) · [Language matrix](languages/en.md) · [Current publisher sources](live-service-sources.md)

<!-- generated game host roles -->

| Toolkit host | Independent preparation | Original playback | Game and capture device | Transcript reader |
| --- | --- | --- | --- | --- |
| Windows | Installed readers and the per-game publisher Setup routes listed in the language matrix. | Matched voices from the selected PC edition or its verified publisher release. | Local PC game window or monitor. | Local reader or desktop-hosted browser reader on another device. |
| Linux and Steam Deck | Pending per-game native acceptance for the six targets. | Pending per-game native acceptance. | Visible-window X11 adapter. Wayland support is pending. Proton requires edition and capture checks. | A browser can connect to a desktop host. |
| macOS | Pending per-game native acceptance for the six targets. | Pending per-game native acceptance. | Visible-window CoreGraphics adapter with screen-recording permission. Native and compatibility-layer game editions require separate checks. | A browser can connect to a desktop host. |
| Android | Planned shared-core app. Installable app and device acceptance are pending. | Independent playback on the device awaits acceptance. | Planned receiver for an explicitly started iPhone/iPad screen share. Capturing an Android game needs separate acceptance. | A browser can read a desktop transcript. The independent Android transcript host is planned. |
| iOS and iPadOS | Standalone toolkit processing is unsupported. | The desktop-connected reader can play matched audio from the host. | Game device and explicit screen sender for the planned Android receiver. | Desktop-connected transcript panel. |

<!-- end generated game host roles -->

Release and device evidence for the six games stays with their tickets.
[Genshin Impact](https://github.com/Firebird55/Game-immersion-toolkit/issues/83) · [Honkai: Star Rail](https://github.com/Firebird55/Game-immersion-toolkit/issues/84) · [Zenless Zone Zero](https://github.com/Firebird55/Game-immersion-toolkit/issues/85) · [Arknights: Endfield](https://github.com/Firebird55/Game-immersion-toolkit/issues/86) · [Wuthering Waves](https://github.com/Firebird55/Game-immersion-toolkit/issues/87) · [Neverness to Everness](https://github.com/Firebird55/Game-immersion-toolkit/issues/88)

The Cyberpunk and Death Stranding tickets preserve historical reader-portability
work under the Windows-only game policy. The Steam Deck, edition compatibility,
representative capture and capability matrix tickets track separate acceptance
questions. Android development and the retained iOS roles belong to the
shared-core mobile work. [Cyberpunk #71](https://github.com/Firebird55/Game-immersion-toolkit/issues/71) · [Death Stranding #72](https://github.com/Firebird55/Game-immersion-toolkit/issues/72) · [Steam Deck #75](https://github.com/Firebird55/Game-immersion-toolkit/issues/75) · [Game editions #76](https://github.com/Firebird55/Game-immersion-toolkit/issues/76) · [Capture and language packs #77](https://github.com/Firebird55/Game-immersion-toolkit/issues/77) · [Capability matrix #78](https://github.com/Firebird55/Game-immersion-toolkit/issues/78) · [Android and iOS #81](https://github.com/Firebird55/Game-immersion-toolkit/issues/81)

## Desktop capture implementations

| Platform | Capture implementation | Current limits |
| --- | --- | --- |
| Windows | Physical client bounds, per-monitor DPI, foreground capture and isolated Windows Graphics Capture for covered windows | Final frozen candidate and Windows 11 hardware acceptance remain required |
| Linux X11 | Native X11 window/process discovery, client coordinates, monitor intersection and verified visible-window capture | Keep the game visible and uncovered; native Linux acceptance remains pending |
| macOS | CoreGraphics window/process discovery and nominal-resolution desktop capture | Screen recording permission and an uncovered game are required; native macOS acceptance remains pending |
| Linux Wayland | Explicit unsupported-capture state | A screen-sharing portal backend remains to be implemented; an X11 desktop session can use the implemented backend |

Discovery uses executable identity, never an unrelated browser title that names
a game. Wine processes can expose their actual Windows executable; an ambiguous
or unresolved executable path cannot choose a reader merely because it is the
preferred game. Native game editions whose assets or executable identities differ
still need their own evidenced format coverage. A platform package does not make
every game edition runnable or supported on that operating system.

The display with the largest intersection follows the game automatically,
including monitors left of or above the primary display. X11 uses pixel
coordinates. macOS uses CoreGraphics display points together with MSS nominal
resolution, preserving mixed-Retina monitor origins. Portable grabs verify the
window identity, bounds and occlusion before and after taking one frame. A moved,
minimized or covered game causes capture to wait with a visible explanation.

On macOS, allow the toolkit under System Settings → Privacy & Security → Screen
& System Audio Recording and reopen it. Missing permission is reported explicitly.
On Linux, launch within the desktop user's X11 session. Missing display access,
missing native components and Wayland are separate actionable states.

Original voice from installed game files does not require a playback/loopback
audio device. The legacy Windows WASAPI recorder is unavailable on other
platforms and reports that limitation without preventing the application from
importing or turning a missing recording into confirmed unvoiced dialogue.

## Local setup and accounts

On the desktop PC, **Account settings → Add account securely** accepts a key in
a masked field. The local backend verifies the identity with `GET /v1/me` and
saves the selected account in protected storage. The form clears the key on
submission and closes after saving. Setup also offers bundled native dialogs
for account entry, game-folder selection and capture checks.

Windows retains its existing DPAPI credential format. macOS uses Keychain and
Linux uses the desktop Secret Service through explicitly selected bundled
backends. Those stores hold the random master key; application files contain a
versioned authenticated AES-GCM envelope. The toolkit does not select alternate
keyring plugins or fall back to plaintext. Locked, denied or missing desktop
storage produces an actionable message while preserving saved ciphertext.
An unlocked OS credential service is required for saving accounts; capture and
independent reading modes do not require a Lexirise account.

Frozen account and game-folder settings use the selected user data directory.
Source Windows installations retain their legacy per-user credential location;
source Linux/macOS settings use XDG data storage or Application Support. The
optional command-line key prompt remains available to source developers, with
hidden input and the same protected storage.

The local capture check loads the real OCR engine and reads an authored English
sentence, checks desktop permission/display access, and verifies the bundled
audio converter is present. This is component readiness, not acceptance of a
particular game or every OCR language. The native-window probe below tests
actual capture geometry separately.

## Verification

Contract tests cover negative coordinates, monitor movement, occlusion,
minimized/replaced windows, macOS point geometry, Wine identity and missing
platform capabilities. `scripts/probe-native-desktop-capture.py` creates and
captures an independently painted native window, checking two expected colors
and capture bounds. Its safe JSON result distinguishes pass, failure and
unavailable permission/display access. It never reads game or account data.

The Windows source probe passed at 150% DPI, with a 480×320 logical window
captured at 720×480 physical pixels. This validates the existing Windows geometry
and the probe itself; it does not prove Linux/macOS behavior or final packaged
game capture. Hosted Linux/macOS runs and physical permission/display cases remain
part of the [desktop delivery plan](desktop-delivery-completion-plan.md).

Native Qt account-form tests use mock identity responses and mock protected
storage only. They cover cancellation, failed verification, hidden key entry,
encrypted persistence, locked/missing master keys and interrupted atomic writes.
Actual macOS Keychain/Linux Secret Service interaction and native setup on those
platforms remain required candidate acceptance; these mocks do not prove it.

The native API contracts are documented in the
[EWMH specification](https://specifications.freedesktop.org/wm/latest/ar01s05.html),
[Python Xlib window API](https://python-xlib.github.io/python-xlib_20.html), and
[CoreGraphics window API](https://developer.apple.com/documentation/coregraphics/cgwindowlistcopywindowinfo(_:_:)).
The pinned MSS macOS backend requests nominal-resolution images. These platform
differences are confined to discovery/capture, rather than game-specific behavior.
