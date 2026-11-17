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
