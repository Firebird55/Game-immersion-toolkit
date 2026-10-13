# Online companion development and verification

The production bookmark stays at
https://firebird55.github.io/Game-immersion-toolkit/ . Only checked `main` builds
deploy there. `codex/` branches run validation and retain static review artifacts.
The static publisher uses an explicit asset allowlist, including bundled React,
the pinned shared reader, OCR and QR runtimes. No game files or desktop data enter
that list. Shared source belongs in Lexirise-shared-components; release and import
both consumers with `shared:update -- --version <version> --all`.

## Local work

Run `npm ci`, `node scripts/prepare-mobile-assets.mjs`, then `npm run mobile:dev`.
For the browser API gateway, use `npx wrangler dev --config
services/lexirise-gateway/wrangler.local.jsonc --local`. The development origin
configuration is separate from production. Never add real keys to config or
workflow secrets. Account writes in tests use mocks.

Enable **Settings → Developer mode** for capture observations, device verification
forms, raw counters and report downloads. The explicit `?developer=1` URL opens
the expanded module-verification workspace used by the older capture/OCR tests.
Normal UI tests use the default URL and assert that these controls are hidden.

## Lifecycle and storage

The static React shell calls `captureLifecycle`, `pairingLifecycle` and
`libraryLifecycle`. Source/role transitions stop capture, camera use and OCR.
Library contents, calibration and favorites are not erased. IndexedDB version 2
adds source identity to legacy mobile history in the existing upgrade transaction;
catalog and preferences keys are retained. PC history is separate and bounded to
500 recent nonfavorites and 5,000 favorites. Keys include source, game and line ID.

The vault uses authenticated AES-256-GCM, a fresh 96-bit IV, random 128-bit salt,
and PBKDF2-HMAC-SHA-256 with 600,000 iterations. Its derivation settings are checked
before decrypting. A generation counter prevents late unlocks from defeating a
lock. Wrong passphrases/tampering preserve the encrypted record. Locking aborts
transport and disposes the shared client's pending work and memory caches.
Background expiry is rechecked on visibility return in case timers were suspended.

The service worker handles allowlisted static GETs only, rejects requests carrying
Authorization, and does not cache the gateway or vault. Update activation is
explicit and blocked during sharing/library work. Previous static assets are kept
for offline recovery; IndexedDB is never cleared by a deployment.

## Transcript protocol

`proxy-transcript-v1` is an ordered WebRTC data channel using same-network ICE
candidates only. Pairing carries an explicit transcript mode through direct files,
compact QR and encrypted signaling. Every message contains protocol version and
the current session/pairing identity. Allowed messages are capabilities, page
requests/pages, incremental updates, audio requests/chunks and bounded errors.

Pages contain at most eight sanitized rows; messages are limited to 60,000 UTF-8
bytes. Audio is limited to 8 MiB, sent as 12 KiB chunks with ordered indexes,
bounded assembly, timeouts and a 128 KiB bufferedAmount threshold. The sender
processes one request at a time. Audio requests must name a previously exposed
original-voice line. Paths, URLs, desktop favorites, credentials and arbitrary API
operations cannot be requested. Closing stops the peer, provider subscriptions
and pending reads immediately. Reconnect capabilities trigger a fresh snapshot.

## Gateway

Deploy `services/lexirise-gateway/wrangler.jsonc` before the dependent frontend.
It accepts HTTPS authorization and versioned operation envelopes, fixes the
upstream to `https://api.lexirise.app`, validates routes/fields/limits, rejects
redirects and strips upstream error bodies. Uploads are bounded original-audio
files. Account settings use the desktop's writable field list; provider enum
validation remains authoritative. There are no data-storage bindings. Rate-limit
bindings retain only admission counters keyed by IP or a one-way credential
fingerprint. Workers logs, invocation logs and traces are disabled; no code logs
request/response payloads. Response caching is disabled in both directions.
CORS permits the production Pages origin and is not authentication.

## Checks and evidence

Run `npm run lexirise:watch` and review settings, lookup UI, API/AI references and
language capabilities before recording a new shared baseline. Then run shared
consumer checks, `npm run mobile:check`, `npm run check` and `npm run audit:public`.
`scripts/companion-e2e.mjs` checks the ordinary UI, vault, transcript-only pairing,
pagination, updates/deduplication, reconnect, local favorites and stop in supported
Playwright engines. The retained capture/library/update suites exercise modules
in explicit developer mode. All scenes, voices and account writes are synthetic.

Physical phone/tablet capture, actual same-network device pairing, Windows physical
capture bounds and iPad background capture require separate hands-on checks.
Windows WebKit does not support the same WebRTC/video paths as Safari on a real
iPad. Automated viewport, DPI and browser tests are not evidence of native iPad
background capture. Record unavailable checks as unavailable.

Release desktop integration only from clean `main` with the normal release
command. Monitor GitHub-hosted Actions and verify downloaded SHA256SUMS and
PROVENANCE against the tag before reporting delivery. Preserve local data and
host-protected credentials. No Argo or cluster is involved.

## Compatibility review, 2026-10-13

The watcher reported website bundle changes, with the API reference hash and
endpoint inventory unchanged. Reviewed current public settings and lookup
bundles: the nine popup tabs, four definition sections, locked definition tab,
reading-aid capabilities, tone/proficiency palettes and null reset semantics
remain compatible. Website-only per-language translation overrides are not
uploaded by this adapter. The pinned shared 1.0.11 baseline is retained, so the
watcher continues to flag the website changes rather than silently editing vendor
files. Both consumers passed their shared checks; Emulingo also passed Chromium,
Firefox and isolated-world/Shadow DOM checks with mock account writes.

WebKit CI runs on macOS as well as Windows and Linux. A native data-channel echo
probe serializes SDP between separate browser pages before testing the application
protocol. A same-page echo alone does not verify network candidate exchange.
Chromium and Firefox require a successful echo. If WebKit cannot exchange the
native echo, its transport checks are reported as unavailable in the job log and
Actions summary; UI, vault, OCR, encrypted signaling and offline checks still run.
If the echo succeeds, all application transport assertions are required. This follows
[Playwright's platform-specific WebRTC guidance](https://github.com/microsoft/playwright/issues/31016).
The macOS check is required before Pages publication, but a passing job with an
unavailable transport does not verify Safari pairing. The October 13 macOS runner
reported zero native ICE candidates in both headed and headless WebKit. A physical
Safari session remains required for device acceptance. Service workers are isolated from mocked API routes in the UI
suite; the separate update suite exercises real service-worker cache behavior.
