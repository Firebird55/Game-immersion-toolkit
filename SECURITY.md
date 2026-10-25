# Security

The maintained version is the latest release. Report vulnerabilities using **Security → Report a vulnerability** on GitHub. Do not post credentials, personal transcripts, local paths or private capture material in issues. If private reporting is temporarily unavailable, open an issue requesting a private reporting channel without disclosing the vulnerability.

The Windows companion binds to loopback. Do not expose its API, development server or desktop filesystem to the Internet. Lexirise keys stay in Windows DPAPI or the userscript manager; never place real keys in Git, Actions secrets, fixtures or artifacts. Account writes require explicit user actions and write tests use mock transports.

The public mobile preview is an allowlisted static browser experiment. It has no desktop API, catalog upload or hosted signaling service. Direct WebRTC pairing is intended for two devices on the same network. Pairing descriptions can contain local network addresses: do not post them publicly. Reports exclude pairing descriptions, frames and keys.

Game files, extracted voices, transcripts, calibration, local configuration and Windows native OCR binaries are excluded from distributions. The mobile application includes separately allowlisted, licensed Tesseract JavaScript/WASM and English/Chinese language models. Users select their own catalog and voice files locally; those files are never uploaded to Pages. Lexirise exports use explicitly selected destinations verified against the current account. Switching keys requires destination configuration for that credential and does not reuse another credential's export markers.

Pull-request workflows have read-only permissions and no live credentials. Release/deployment writes run only for trusted canonical-repository events. Dependency alerts and periodic Dependabot updates are enabled; contributors should run `npm audit` and report actionable vulnerabilities. Never use a forced automatic downgrade to conceal an advisory.

Checksums and provenance help detect corrupt downloads, but do not constitute a security guarantee. Publication checks scan history and decompressed archives; manual review remains necessary for assets, screenshots and third-party rights.

## Known dependency limitation

The current npm audit reports one upstream [braces stack-exhaustion advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), inherited through six packages in Vinext's build dependency chain. The latest published braces version remains 3.0.3. This affects deeply nested glob input; the app does not accept glob patterns from transcript users. Build only trusted configuration and keep build servers on loopback. A patched upstream version is still required; do not run npm audit fix --force, which currently proposes an unrelated framework downgrade.

## Explicit trusted-device mobile storage

Mobile Lexirise defaults to an encrypted passphrase vault. The separate, initially
unchecked **Remember on this device** option instead saves a plaintext API key in
this site's IndexedDB, readable by this site's scripts on that device. It is not
password-protected. Enabling it for an existing encrypted vault requires a
successful unlock; opt-out removes the automatic copy, and Forget clears saved
credentials and the active session. Desktop DPAPI storage is unchanged.

VDO.Ninja has an independent opt-in that remembers the full validated private
viewer link, including password and options. Restoration does not connect until
Start playing. Forget removes the copy and disconnects. Neither secret is included
in package exports, diagnostics, application URLs, logs or service-worker caches.
The viewer necessarily receives its connection options when the user connects.

Retained libraries use browser-owned OPFS with a separate IndexedDB registry.
Static application updates never clear these stores. Browser and OS deletion is
still possible; private ZIPs remain the recovery source. Automatic desktop exports
are per-machine local rules without account credentials. Only completed libraries
and instructions are published to the chosen private folder; cloud clients manage
synchronization independently. Do not share exported game libraries publicly.
