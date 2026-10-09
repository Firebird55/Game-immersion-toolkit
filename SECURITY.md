# Security and release boundaries

This is a local Windows companion, not an Internet-facing server. Bind only to loopback.
Keys remain in DPAPI; do not commit settings, caches, game assets, recordings or diagnostics.
Account settings writes require the explicit UI save action and localhost custom-header guard.

The October 2026 dependency refresh removes critical advisories and updates React/RSC, Vinext, Vite, Wrangler and formatting tools. An upstream braces 3.0.3 stack-exhaustion advisory remains in build-tool glob handling; current upstream Vinext depends on it. Only build trusted checkout/configuration inputs; do not use attacker-supplied glob patterns or expose development/build tooling. Track upstream fixes with npm audit. Never use npm audit fix --force to silently downgrade the framework.

Private releases use GitHub-hosted Actions and authenticated downloads, with provenance and SHA-256 checksums. Real Lexirise account verification is read-only; account-write tests use mocked transports.
