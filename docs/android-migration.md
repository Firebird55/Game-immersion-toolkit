# Android replacement and retired hosted application

The owner retired the independent hosted gaming application on November 16,
2026, allowing the old site to become unavailable while Android development
continues. No Android release is currently delivered. A WebView loading the old
hosted page does not satisfy the replacement.

The Android app must embed the shared toolkit core, use the maintained desktop
reader and components, import a private prepared library, recognize dialogue and
play available original audio locally. Development prototypes, browser fixtures
and emulator results are distinct from physical Android acceptance.

## Supported roles during the transition

| Role | Current contract |
| --- | --- |
| Desktop game and desktop reader | Existing desktop toolkit. |
| Desktop game and iPhone/iPad reader | Open the address and connection code shown by **Share** in the running desktop toolkit. The desktop owns processing, history and audio. |
| iPhone/iPad game and Android reader | Android receiver under implementation. The gaming device must explicitly start its screen sender. |
| Android local game capture | A separate MediaProjection adapter requires its own consent, foreground lifecycle and acceptance. It is not implied by receiving a remote stream. |
| Standalone iOS or two iOS toolkit devices | Retired. |

The desktop-connected reader uses the desktop's local-network gateway. It does
not depend on GitHub Pages or Cloudflare recovery/account proxies. An optional
external screen relay must be documented independently; an offline library is
not evidence that such a relay works offline.

## Preserve private data

1. Keep each original Mobile Library ZIP in your private files for recovery.
   Older browser archives lack the full native matcher contract. Create a new
   **Android Library ZIP** using the desktop manual export or automatic queue,
   then import that ZIP in Android. Check its game, study language, translation
   and player voice when importing. Existing automatic rules are retained; a
   format change queues a native export even if the game data are unchanged.
2. Keep old browser-origin storage until any wanted history and favorites are
   exported or a migration route is provided. Re-importing a library does not
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

Android delivery still requires an actual installable app, closed runtime and
dependency inventories, stable update identity, protected signing, restart/import
recovery, local voice playback and the iOS-sender route. The desktop-connected
iOS reader retains its browser and physical-device verification requirements.
See [issue #81](https://github.com/Firebird55/Game-immersion-toolkit/issues/81).

## Authored Android account acceptance

A DEBUG cold launch with `toolkitAuthoredAccounts=true` uses a separate
`authored-account-ui` app-private root and the authored AndroidKeystore alias.
The normal toolkit root and production account startup remain unchanged. The
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
actual Android target acceptance are separate integration work; normal
production account activation remains disabled until its UI fences are ready.

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
