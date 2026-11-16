# Android and connected-reader development

The independent hosted gaming application is retired. The former GitHub Pages
workflow has no deployment trigger, Pages permission or publishing job. It can
be invoked explicitly to check the supported desktop-connected reader in
Chromium, Firefox and WebKit. It never makes the retired website available.

The Android replacement reuses the desktop core and maintained React reader.
Native capture/transport, protected storage, file selection and lifecycle belong
behind platform adapters. A WebView pointing to the old hosted application is
not the Android implementation. Dependencies and shared-core hosting must pass
an actual installable prototype before broader device-support claims.

Work on a `codex/` branch. Follow [development checks](development-checks.md),
run the affected desktop/mobile contracts and publication audit, and commit each
verified logical change. Shared component changes belong upstream, followed by
version publication and synchronization of both consumers. Public Lexirise
compatibility reviews remain optional; see [the runbook](../RELEASE.md).

The supported iPhone/iPad reader is served by the running desktop's local-network
gateway. `node scripts/desktop-lan-e2e.mjs` exercises the actual gateway and shared
reader against authored APIs and audio. Browser success remains separate from
physical iOS and Android evidence. The old browser-controller sources and tests
are retained as private development/migration fixtures while Android integration
is in progress; they are not a supported hosted or standalone-iOS product.

No personal data, game libraries, recordings or credentials may enter artifacts.
Do not add credentials or signing keys to workflow secrets. Retired Cloudflare
Workers are separate from the desktop's local gateway; removing them does not
remove the retained desktop reader. No cluster is required.

See [Android migration](android-migration.md), [desktop platforms](desktop-platforms.md)
and the historical [browser architecture](online-companion-development.md).
