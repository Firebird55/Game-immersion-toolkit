# Desktop capture on each platform

The desktop host, transcript browser and LAN reader share one implementation.
Native discovery supplies the game window and display coordinates; game readers
continue using the same capture, locale, text and original-voice services.

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

Game-folder selection, account entry and capture checks use bundled Qt dialogs
on each platform. Account keys are entered in a native password field. Verification
only reads the account identity (`GET /v1/me`); saving a local account does not
change remote settings, decks or vocabulary. Keys are never put in the browser,
command arguments or process environment by these dialogs. Canceling a folder
selection leaves the saved game locations unchanged.

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
