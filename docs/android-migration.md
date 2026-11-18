# Android replacement and retired hosted application

The owner retired the independent hosted gaming application on November 16,
2026. The 0.24.0 Android prerelease is scoped to Global Zenless Zone Zero.
It embeds the shared toolkit core and prepares original publisher data in the
app. The owner is validating the physical gameplay flow after installation.

The Android app must embed the shared toolkit core and use the maintained
desktop reader components. Fresh setup uses per-game downloads to prepare and
update official text and original audio on the device. Existing history and
recordings have a separate recovery flow. Development and emulator checks
provide separate evidence from acceptance on a physical Android device.

## Supported roles during the transition

| Role | Current contract |
| --- | --- |
| Desktop game and desktop reader | Existing desktop toolkit. |
| Desktop game and iPhone/iPad reader | Open the address and connection code shown by **Share** in the running desktop toolkit. The desktop owns processing, history and audio. |
| iPhone/iPad game and Android reader | Global ZZZ in the first Android prerelease. Start screen sharing on the gaming device and paste the VDO.Ninja viewer link on Android. Physical gameplay validation is pending. |
| Android local game capture | A separate MediaProjection adapter requires its own consent, foreground lifecycle and acceptance. It is not implied by receiving a remote stream. |
| Standalone iOS or two iOS toolkit devices | Retired. |

The desktop-connected reader uses the desktop's local-network gateway. It does
not depend on GitHub Pages or Cloudflare recovery/account proxies. An optional
external screen relay must be documented independently; an offline library is
not evidence that such a relay works offline.

## Preserve private data

1. Keep any previously exported Mobile Library ZIP in your private files for
   recovery. For a manual recovery that uses a prepared Android Library ZIP,
   check its game, study language, translation and player voice before
   importing. Older browser archives can have different matching data.
2. Keep old browser-origin storage. Use the explicit
   [history and favorites migration](browser-history-migration.md) when available
   in the Android candidate. Re-importing a library does not
   itself copy history or favorites. A native app cannot read another browser's
   IndexedDB or OPFS implicitly.
3. Enter account credentials through the app's protected account flow when
   available. Do not put API keys, browser vaults, connection codes or private
   stream URLs in a library ZIP, diagnostic attachment or ordinary migration
   export. Existing browser storage is not silently deleted or copied.
4. Preserve reading-mode and per-language/account preferences explicitly. The
   desktop Chinese transcript stores and independent Migaku mode remain intact.
   A mobile WebView must not advertise desktop browser-extension compatibility.

The old service worker may retain an already installed browser copy while
offline. Removing a website cannot remotely erase that local cache. The source
transition does not clear private caches, library stores, credentials, history
or favorites. There is no new independent-browser support promise for that copy.

## Deployment and acceptance

The former Pages workflow is now an explicitly invoked, unpublished diagnostic
for the retained desktop reader. It has no automatic deployment trigger, Pages
write permission, upload or deployment job. Historical browser sources and
authored fixtures remain available during migration; their tests are not Android
app or physical iOS evidence.

The first APK uses a stable package identity and owner-protected signing.
The release receipt covers the physical ARM64 installation and records gameplay
validation separately. The seven other live-service publishers remain tracked
in their individual issues. The desktop-connected iOS reader continues to use
the desktop's Share address. [Android release scope](https://github.com/Firebird55/Game-immersion-toolkit/issues/81)

## Native reader insets

Native inset acceptance uses the production reader's actual Android window
geometry. A debug-only launch records the focused WebView bounds, current
rotation and visible system-bar/cutout insets. The hosted checks bind each
portrait/landscape/portrait sample to the installed APK and live app process.
The Android 14 runs through `fbac2920` reached their local reader service, but
the accessibility hierarchy showed a system error dialog before the initial
portrait measurement. Android 16 passed those authored runs. The geometry
probe records an accessibility snapshot on failure for separate diagnosis.

## Authored Android account acceptance

A DEBUG cold launch with `toolkitAuthoredAccounts=true` uses a separate
`authored-account-ui` app-private root and the authored AndroidKeystore alias.
This fixture leaves the normal toolkit root and its protected account store untouched. The
mode cannot be changed through HTTP or adopted by an already running host.
Non-debug builds reject the native authorization method.

Only the two synthetic keys defined in `backend/android_authored_accounts.py`
are accepted. An immutable HTTPX MockTransport handles the maintained account,
settings, reading, deck and sentence-export APIs; unknown keys, hosts and routes
fail closed. Mock remote settings and deck contents live only in the process.
Protected local profiles, imported libraries and transcript histories retain
their ordinary app-private storage. This mode exercises real UI ownership and
local lifecycle behavior, not real account writes or service availability.

An emulator test must explicitly identify this authored mode and still prove
account A-to-B-to-A isolation, original audio, stale request rejection and
restart behavior. Desktop fixture tests or a successful APK construction do not
establish that Android target result.

## Protected account recovery

When enabled, the native account host detects missing, corrupted, oversized or
unreadable protected credentials without deleting or replacing the saved blob.
It exposes a credential-free `credentials_unreadable` recovery state and an
empty stopped reader. It does not infer the previous account from profile
folders or display another owner's history. Imports, capture, media, settings
changes and ordinary account actions remain fenced while recovery is required.
Runtime detection also invalidates pending imports, source generations, receiver
ownership and previews. The neutral snapshot remains safe if temporary storage
is unavailable.

Unlock device protected storage and reopen the app to retry the original
credentials. Alternatively, an explicit generation-guarded
`POST /api/lexirise/accounts/recover` accepts the account key and optional name.
The maintained AccountStore verifies only `GET /v1/me`; it does not write remote
account data. Authenticated readback of a new protected store, preparation of
the verified owner's existing profile and an atomic bounded locator publication
must succeed before activation. Re-enter the same owner to reopen its original
libraries, transcript database, favorites, settings and voice files. Other saved
owners must be verified separately; their data stays in place.

Original and earlier protected stores remain unchanged, including after a
failed or superseded recovery. A candidate that may already be referenced by a
committed locator is retained after an uncertain I/O failure; reopening resolves
that state. Recovery attempts and retained store counts are bounded. No native
key deletion, plaintext fallback, arbitrary profile selection or automatic
remote writes form part of this recovery path. The visible recovery UI and
authored Android target acceptance passed at `cc0bf061`. Normal native startup
now enables the same protected provider and maintained account interface,
retaining existing local libraries/history without adopting environment or
desktop keys. Stored accounts may resume ordinary read-only settings/language
requests; an empty store never starts a connection. Local recovery and capture
do not depend on network availability. Normal activation still requires its
own matching native runtime evidence, separately from physical-device acceptance.

Native OCR completion may take longer than the confirmation gap on a slow
device. A bounded native admission ledger can retain an independently exact,
eligible caption candidate while authenticated images continue arriving within
three seconds of each other in the same receiver, document, generation and
session. Each completed image consumes one opaque receipt; recent admissions
and a maximum 35-second callback age are both required. The ledger retains at
most 128 IDs and never stores images or stream addresses. It does not extend
publisher predecessor contexts, fuzzy confirmation, menu observations or the
ordinary three-second behavior of callers without native receipts. Unit and
HTTP fixtures exercise serialized four-second OCR; this source checkpoint alone
does not establish Android target or physical-device acceptance.

Prepared Endfield libraries retain the original Baker mode, contact and ordered
cell metadata, bound to the same publisher revision. The shared Android session
uses the desktop's complete-cell matcher with genuine positioned OCR and the
unvoiced-capture opt-in, preserving the selected study language when the screen
uses another prepared display language. Unpositioned, incomplete, ambiguous or
menu observations cannot establish the written system-message context. Portable
export/import, history ordering and process restart pass authored shared-core
checks; actual Android OCR for these layouts remains a target acceptance check.
