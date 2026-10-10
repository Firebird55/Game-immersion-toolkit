# Two-device mobile capture test

This is the first, gated milestone of mobile support. It has no OCR, catalog import,
audio, account connection, or transcript writes. The desktop capture pipeline is unchanged.

## Open on iPad and phone

For normal development, use the [GitHub preview cycle](mobile-development.md).
It provides a stable public HTTPS bookmark from this private repository. The PC
does not need to serve the page or install a certificate on your devices. The
local HTTPS setup below remains available for offline or unpublished testing.

The test is available at `/mobile-capture/index.html` from the frontend, or with
the standalone server below. Screen sharing requires a secure context. Plain
HTTP to a PC's LAN address is insufficient. Bypassing a certificate warning is
not a substitute for a trusted certificate.

Use a locally trusted certificate with the PC's LAN address in its subject
alternative names. For example, if mkcert is already installed:

```powershell
mkcert -install
mkcert -cert-file work/mobile-cert.pem -key-file work/mobile-key.pem localhost 127.0.0.1 <PC-LAN-IP>
node scripts/serve-mobile-capture.mjs --cert work/mobile-cert.pem --key work/mobile-key.pem
```

Create `work` first if it does not exist. Install **only the public root certificate**
from `mkcert -CAROOT` on your own iPad and iPhone and explicitly enable its trust
in Settings. Never transfer the CA private key or the server private key. Certificates
and keys stay outside Git. A trusted certificate for a domain you own is another
option. Certificate setup is manual; the server does not install a trust root.

Open the printed `https://<PC-LAN-IP>:8443/` address on both devices. Allow this
server through the Windows firewall on the private network if necessary. Keep the
devices on the same Wi-Fi without client isolation. The PC serves the static page
during setup; screen frames travel directly between the mobile devices. Keep the
server running until both pages have loaded and pairing is complete.

1. On iPad choose the game, then **Share screen & create offer**. If the API is
   unavailable, report that result; installing a home-screen shortcut does not add it.
2. Transfer the offer privately to the phone, using copy/paste or the pairing file.
3. On the phone select its receiving role, paste/open the offer and accept it.
4. Transfer the phone's answer back to the iPad and accept it there.
5. Switch the iPad into the game. Confirm the phone preview shows the actual game.
6. Start the 15-minute observation on the phone. Keep the phone page foregrounded.
   Exercise dialogue, cutscenes, rotation and a return to Safari. Repeat separately
   for ZZZ and Wuthering Waves; stop and pair again between tests.
7. Select the observed result and download a report on the phone. Download an
   iPad report too if helpful; its visibility events may explain interruptions.

## Interpret the result

Reports contain capability information, user-agent, connection events, delivered
frame counts, low-resolution image change counts, dark-image samples, and your
notes. No screenshots, pairing descriptions, credentials or network addresses
are exported. Notes are user-provided; avoid entering sensitive details.

Frame delivery and image changes do not prove that the game was captured. A
stationary scene can have no image changes; a stream can deliver repeated or black
frames. Review the moving game preview and the observation report together.
The test never automatically claims background capture succeeded.

Proceed to browser OCR and catalog matching only after actual-device evidence
confirms 15 minutes of usable capture for the target game. If sharing is unavailable,
freezes, captures only Safari, or produces black game content, stop this approach
and report it. A native iPad capture helper with a browser phone panel is the next
architecture to evaluate; it is not implemented by this milestone.

## Checks

`node --test tests/mobile-capture.test.mjs` covers pairing validation, frame-stall
detection and black-image detection. `node scripts/mobile-capture-e2e.mjs` checks
the actual page in Chromium and Firefox, mobile layouts, permission failure,
malformed pairing and a synthetic peer-to-peer video connection. Synthetic tests
cannot establish iPad background capture or game compatibility.
