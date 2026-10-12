# Automatic connection recovery

The public preview uses [the pairing service](https://game-immersion-pairing.boazbrak.workers.dev/health).

GitHub Pages serves the frontend. A separate small Cloudflare Worker with one
SQLite Durable Object per pairing room exchanges encrypted connection messages.
It uses the WebSocket Hibernation API, admission/message limits, bounded packets
and four-hour room expiration. The implementation fits Workers Free allowances;
free limits are shared with other Workers and traffic can exhaust them. Deployment
does not upgrade a plan or purchase a TURN relay. Review account usage before
serving a larger audience.

Game video remains peer-to-peer on the same network. OCR, libraries, transcripts
and original voice playback remain on the receiving device. The service cannot
make iPad Safari support screen capture, keep an operating-system capture running
against platform restrictions, or restore a page that was completely terminated.

## Security and lifecycle

- The sender generates a random 128-bit room identity and a 256-bit key. The key
  reaches the receiver in the privately transferred offer, including its QR.
  Anyone holding that offer can join; do not publish it or include it in reports.
- Each role authenticates with a distinct HMAC-derived proof. The server stores
  only hashes of those proofs plus expiry, never the key or SDP. Messages use
  AES-GCM with room/role authentication and fresh nonces. Replay duplicates are
  ignored by clients. The receiver accepts messages only for its existing game,
  session and newer attempt; stale offers and mismatched answers are rejected.
- Clients contact only the endpoint configured by this application's deployment.
  A pasted offer cannot redirect a phone to an arbitrary server. Sessions and
  keys are held in memory; reopening/reloading requires pairing again. Catalog
  and transcript storage remains independent of this session key.
- The worker checks an exact origin allowlist before admission, then limits
  requests through Cloudflare's rate limiter. That admission limit is per IP and
  Cloudflare location, not a global budget; shared networks may hit it. Each room
  bounds pending sockets, authenticated roles, packet size and message rate.
- One role can replace its own socket after reconnecting. Stop closes the client
  and cancels retries. Room hashes expire and are deleted automatically. Cloudflare
  manages storage backups and infrastructure metadata under its platform policy.
  Sampled logs contain generic errors; invocation request logging is disabled.
- This is a signaling service, not a proxy for arbitrary URLs or game media. The
  application performs neither library uploads nor account writes through it.

## Deploying and developing

The target is `game-immersion-pairing` in `services/pairing/wrangler.jsonc`, with
SQLite-backed Durable Objects. Use the pinned project Wrangler, and keep account
credentials in host protected storage. No workflow secrets are required.

1. Authenticate locally with `npx wrangler login`; review the account shown by
   `npx wrangler whoami`. No account identity or token belongs in source control.
2. Set `ALLOWED_ORIGINS` to exact frontend origins. Production allows the Pages
   origin. A fork should deploy its own service and allow its own Pages origin.
3. Run `npm run mobile:check`. Tests start an isolated local Worker with private
   state beneath ignored `output/`, synthetic video and ephemeral pairing keys.
   They do not use the deployed service or write to Cloudflare accounts.
4. Run `npm run pairing:deploy -- --dry-run`, then `npm run pairing:deploy`.
   This creates/updates the named service and its SQLite binding. Verify `/health`
   and a real frontend session; health alone does not prove video recovery.
5. Put its HTTPS origin in `public/mobile-capture/recovery-config.json`, with
   `origins` containing the frontend origin. Run mobile checks and public audit,
   commit, then publish the allowlisted Pages build through the release workflow.
   Local companion pages use direct pairing unless explicitly configured with a
   local recovery origin as well.

For local development, `npm run pairing:dev` runs only local bindings. Configure
its origin allowlist for the local frontend explicitly. Do not connect automated
tests to production account resources. Cloudflare worker releases are performed
from this PC using the pinned configuration; toolkit releases remain GitHub-hosted.

## Verification limits

Chromium/Firefox tests exercise real WebRTC after transport failure, visibility
return, denied/restarted screen capture, one-way offer transfer, preserved
observation and Stop. WebKit tests exercise real encrypted WebSockets and socket
reconnection. Automated tests do not verify iPhone Safari background capture.
Retest on both physical devices: pair once, switch apps, return, resume sharing
if it ended, and confirm moving video/OCR. Download reports on both devices.
