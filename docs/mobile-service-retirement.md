# Hosted mobile service retirement

The owner retired the independent hosted mobile gaming flow on November 16,
2026, while the Android replacement is being built in [#81](https://github.com/Firebird55/Game-immersion-toolkit/issues/81).
The existing desktop React reader, including its iPhone/iPad LAN client, remains
supported. It uses the desktop's same-origin HTTP/WebSocket service and does not
require either Cloudflare Worker below.

## Service and data boundaries

| Production Worker | Former purpose | Stored data | Retirement source |
| --- | --- | --- | --- |
| `game-immersion-lexirise` | Fixed-upstream Lexirise transport for the hosted browser reader | Stateless; browser credentials remained in the browser, request tokens were forwarded only for requested operations | [Gateway config](../services/lexirise-gateway/wrangler.jsonc) selects the retired entrypoint |
| `game-immersion-pairing` | Encrypted connection-message recovery for the old browser PC transcript pairing | One SQLite Durable Object per room; authentication-proof hashes and four-hour expiry, no persisted SDP/key or game library/audio/history | [Pairing config](../services/pairing/wrangler.jsonc) selects the retired entrypoint while retaining the existing class/migration identity |

The pairing service was not the VDO.Ninja game-video relay. Removing these
Workers does not establish offline operation of an external video transport.
The desktop's local account client does not use the retired browser gateway.
Browser-origin libraries, history, preferences and remembered credentials are
not read or erased by service retirement. Migration must use an explicit local
export/re-import route; Android cannot implicitly read browser-origin storage.

Both production configs set `workers_dev: false` and `preview_urls: false`.
Their production entrypoints return HTTP **410 Gone** for health checks,
account operations, room registration, socket upgrades and all other requests.
The handler reads no body, credential or binding and makes no upstream request.
It does not announce an available Android release.

`PairingRoom` remains exported, with its original migration identity and expiry
alarm implementation. No `deleted` migration is introduced. Retiring HTTP
ingress must not silently delete the Durable Object namespace or bypass expiry
of existing rooms. The original protocol remains available only as a private
local test fixture through `services/pairing/wrangler.local.jsonc`; the gateway's
existing local test fixture is also separate from its retired production target.

## Deployment completion

A source commit and a dry run do not prove a remote shutdown. Complete the live
change from the authenticated operator host, using the repository's pinned
Wrangler or the Cloudflare API:

1. Select the actual account and compare the two exact Worker names above with
   their current scripts, settings, routes/custom domains, build triggers,
   service bindings and Durable Object namespace ownership. Do not delete
   similarly named Lexirise services, unrelated Workers or browser/user data.
2. Apply the retired production configs and verify that both `workers.dev` and
   version-preview ingress are disabled. Inspect custom domains and zone routes
   separately: disabling `workers.dev` alone does not remove them. Detach only
   routes proven to belong exclusively to these retired services. Any remaining
   controlled ingress must reach the 410-only entrypoint.
3. Confirm the deployed version and probe each former public ingress. Record
   the response and time privately. An arbitrary 403 or a failed network probe
   is not evidence of completed retirement.
4. Keep the pairing namespace and existing room expiry intact unless a separate
   account inventory proves it can be removed without another consumer. A
   `deleted` migration destroys namespace data irreversibly; no such migration
   belongs to this source change.

Authentication material stays in protected host storage, never source,
ordinary exports, command logs or workflow secrets. GitHub Pages retirement is
a separate repository/deployment operation; changing these Workers cannot
disable or erase a Pages deployment.

[Cloudflare routing controls](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)
explain why disabling a dashboard route must also be retained in Wrangler
configuration. The [Workers API](https://developers.cloudflare.com/api/resources/workers/)
documents script settings and destructive Durable Object migration semantics.
These documents were checked on November 16, 2026.

## Verification scope

`tests/mobile-service-retirement.test.mjs` bundles each actual production
entrypoint and exercises its local native Worker HTTP edge, including rejected
socket upgrades and HEAD/OPTIONS behavior. An independent handler test refuses
all access to request material and environment bindings. Existing gateway tests
continue to use authored account mocks. The retained local recovery scenario
uses only its explicit local fixture and does not deploy a production Worker.

These checks establish source/runtime behavior under the local test adapter;
they do not substitute for the authenticated remote account and ingress receipts
above or for physical Android/iOS acceptance.
