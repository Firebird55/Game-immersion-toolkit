# R19 local host and synthetic recovery experiment

Status on 2026-10-28: **static replacement disproved for the current emitted
frontend; production migration activation and guarded updates remain incomplete**.
The baseline is `8369c9534762cd2232fb44424772bd6b5a72b6d2`, with freshly fetched
upstream `ba0b7c34c358f1664220674e5ff8bb7f30502e5f`. Read the
[R18 contract](r18-storage-host-contract.md) and
[runtime candidate record](r19-runtime-bundle.md) for the wider acceptance gates.
This work creates no installer, installed shortcut, release, tag or Pages output.

## Static frontend decision

The canonical `npm run build` emitted `dist/server/wrangler.json` with
`main: index.js`, a server entry and a separate `ssr/index.js`. Its client tree
contains the separate mobile `index.html` and `games.html`, but **no desktop
`dist/client/index.html`**. A static file server pointed at those client assets
cannot reproduce the desktop `/` document. Generating a substitute HTML shell
or copying the mobile page would not establish equivalent hydration/navigation.

[The experiment](../scripts/r19-static-frontend-experiment.mjs) inspects the real
source/output, records SHA-256 hashes and reports `disproved-current-output`.
It never changes the host, copies assets into an asserted desktop export or
promotes an HTML file into browser-equivalence proof. Missing output reports
`unavailable`; a potential static document remains `incomplete` pending actual
browser equivalence. `--require-static-equivalence` exits 2 for this experiment.
The local report belongs in ignored `output/checks/r19-static-frontend.json`.

Keep Vinext/Wrangler and the existing source launcher/router. The canonical
browser origin remains `http://127.0.0.1:3000`, API remains
`http://127.0.0.1:8766`, and WebSocket remains
`ws://127.0.0.1:8766/api/ws`. Existing exact HTTP/preflight/WebSocket Host/Origin
checks in [local access](../backend/local_access.py) remain in place; this spike
adds no proxy, listener, CORS exception or origin. Source hosting still needs
Node/npm/Wrangler, so it does **not** satisfy R19's standalone frontend gate.
An alternative prerender/export or app-local server runtime needs a separate
implementation, artifact/license inventory and equivalent browser probes.

The ordinary browser, selected existing profile, independent `migaku` mode and
userscript keys are unchanged. The experiment does not open a fresh/private
profile or copy raw profile databases. That is continuity of configuration,
**not verified browser storage or real extension compatibility**. localStorage,
IndexedDB and OPFS each remain `unchanged-unverified`; an IndexedDB retained
library registry alone cannot establish usable OPFS bytes. Desktop hosting does
not acquire the mobile service worker, and the mobile Pages allowlist is unchanged.

## Synthetic guard and copy boundary

[bundle_host.py](../backend/bundle_host.py) accepts only newly created, marked
temporary fixture roots. It acquires the legacy
`data/companion-operation.lock` before the target migration/runtime lease and
holds both through fixture preparation, takeover, copy, failure and rollback.
Windows uses exclusive-share `CreateFileW`; macOS tests use an advisory `flock`
analogue and cannot establish Windows compatibility. Lock files are never
deleted or temporarily released to accommodate another operation.

`SyntheticHostCoordinator` serializes operations using an opaque in-process owner
object. Nested owner operations fail rather than reacquire the lock. Its typed
fixture adapters model readiness, capture, writer generations and shutdown.
Readiness cannot mint a copy barrier. `stopped_writers()` requires every fixture
writer/worker stopped, keeps serialization through copy, and binds the barrier
to both leased roots. Expired, changed or failed barriers keep source capture
stopped with a recovery checkpoint. An incomplete quiesce persists as a block on
new operations. Cleanup cannot release exclusion while any owned fixture
runtime's shutdown remains unconfirmed.

These callbacks are synchronous **without enforced deadlines**, and their process
ownership/writer proofs are injected. They do not establish bounded native
quiescence, stop real browser/API/account writers or supervise a Windows process
tree. The owned-process fixture uses deadlines for guard readiness/exit and proves
OS lease release after its process exits; it launches no worker descendants and
does not prove guard-crash containment. Those acceptance criteria remain open.

The source `update-companion.ps1` still acquires the legacy operation lock itself.
`require_guarded_source_update()` therefore fails explicitly. No bypass flag,
borrowed lockfile or temporary unlock is implemented. A synthetic owned update
can demonstrate ordering while exclusion stays held, but **real guarded update
integration and production migration activation remain disabled**. Existing
source updates continue through their existing unguarded source route.

[bundle_migration.py](../backend/bundle_migration.py) requires the live synthetic
barrier. It copies the complete fixture data/settings trees and reviewed
`work/voice-assets`, preserving every filename, unknown data file and audio alias.
Aliases are copied independently so destinations need no hardlink support; space
is budgeted per name with additional verification room. The held coordination
lock is excluded rather than imported as ownership. Unknown old-root content,
host credential locators and selected external export/work roots remain in place.
External inventories include completed and previous libraries, resume records and
legacy workspace names. Nothing is classified as disposable merely by its name.

Per-file hashes, exact target inventory and expected SQLite versions/integrity
are verified. Closed-writer database/WAL/SHM file sets stay byte-for-byte intact;
SQLite verification uses a separate disposable copy so opening a database cannot
alter the retained snapshot. The fixtures preserve Chinese transcripts,
favorites, reading `grammar_choices`, account/language export completion ledgers,
language/voice metadata, cancelled requests and local-versus-legacy settings.
An interrupted file copy can resume under the same still-valid stopped-writer
barrier. Changed source, plan, external state, schema or unexpected staged files
fail closed and preserve source/staging. There is no live SQLite-copy strategy.

The manifest keeps `dpapi-current-user` locators unchanged and copies encrypted
legacy data-key fallback bytes only as fixture files. It performs no decryption.
An unreadable named account store records a preserving repair/reconnection
requirement; a successful file copy does not recover those accounts. No real
account, protected store, browser database, game or recording is migrated.

Journal and route checkpoints are separately flushed/replaced files. Recovery
reads require matching fixture schemas/identity and reject links. Stored runtime
IDs never grant live process ownership. Rollback stops the candidate before
restoring the old pointer/capture; post-activation writes require reconciliation.
Native crash/power-loss durability remains unverified. Launcher/shortcut status
stays `unchanged-unverified-R20`; these checkpoints do not implement R20 install
or installed Start-entry rollback. No production activation consumes them.

## Explicit static desktop adapter

The earlier `dist/client` copy failure remains valid: those bytes have no desktop
entry document and require the source SSR server. A new opt-in adapter instead
builds `desktop/index.html` and `desktop/main.tsx` with Vite, reusing `app/page.tsx`,
the product components and shared styles. Both source and static adapters use the
same locally pinned Geist fonts, with original OFL bytes and source/blob/SHA-256
provenance under `desktop/fonts`. No Next font fetch is required at runtime.

`npm run desktop:build` emits only reviewed static assets to ignored
`output/desktop-frontend`. Its closed manifest binds exact files, MIME types,
hashes, sizes, version, source/lock fingerprints, emitted dependency versions and
notices. Before copying the source client's `_next/static` compatibility files,
the builder verifies a canonical source build against unchanged inputs and actual
cached output hashes. It never copies the SSR/server tree, maps or developer paths.

The stdlib `backend.desktop_frontend` host accepts that manifest and serves only
its public files on loopback. Use `python -B -m backend.desktop_frontend --root
<absolute-built-tree> --port 3000` for a source experiment. The public origin stays
`http://127.0.0.1:3000`; API/WS remain directly on `127.0.0.1:8766`. The host reuses
the exact raw Host/Origin policy, verifies bytes before serving them, applies CSP
and MIME/nosniff headers, rejects unknown/API/private routes, and exposes the
existing `/mobile-capture/` entry. Old hashed chunks can be retained by an explicit
source experiment; mutable old mobile URLs cannot override the current build.
Frozen retained-build selection remains disabled pending update supervision.

This is not a default-host switch or a supervised production host. It does not
open a new browser profile, move browser data, proxy the API or activate migration.
The comparison harness uses an authored temporary persistent profile, swaps source
and static hosts at the same origin in the same open browser, restarts the browser
and checks localStorage, IndexedDB and OPFS. All API/account writes are mocked. It
also checks both reading modes, lookup portal, settings/setup, WebSocket reconnect,
failure preservation, local fonts, retained chunks, and actual built worker/WASM
OCR assets. Chromium/Firefox, 1280px/100% and 800px/125% cases use independent layout
bounds and fixed pixel limits (channel delta >16: at most 1.8% changed pixels;
mean channel delta at most 1.5). A source footer overflow found at 125% was corrected
by wrapping its controls; the comparison limits were not relaxed.

The Windows `frontend-experiment` profile collects only that frontend child and
the manifest-bound tree. Its hosted probe removes developer PATH, relocates the
executable, checks actual served hashes/MIME and confirms no application/data writes.
It retains observed, unaccepted Python supplier and exact-output rights gates.
No API/capture/update child, installer, release or Pages artifact is enabled.

The actual macOS comparison passed with Chromium **156.0.8078.4** and Firefox
**157.0**, Node **22.22.2**, Playwright **1.64.1**, build
`3332793ef3e6f75b0ff0039d4d9df8c3082f9a4cd086d2cc10d861ed259ad551`.
Both viewport/zoom screenshots and lookup comparisons had **zero changed pixels**
and zero mean channel difference. The same-context host swap, browser restart,
actual localStorage/IndexedDB/OPFS bytes, mobile production link, module worker,
English OCR using the shipped worker/model/WASM, nine old source chunks and a
separate authored retained chunk passed. Owned cleanup passed. Ignored metadata:
`output/checks/r19-frontend-equivalence.json`; authored screenshots stay private.
The audio-503 probe preserves confirmed text but observes the source adapter's
existing unhandled native play rejection; it does not claim an audio-error UI fix.
This precommit source observation does not replace exact-commit hosted acceptance.

The same comparison and actual relocated frozen frontend subsequently passed on
hosted Windows Server 2025 at commit `96ed0df` in
[run 40762619844](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40762619844).
Both browser engines again reported zero pixel difference, real built worker/WASM
OCR and storage/restart continuity. The fixed frontend executable ran with developer
PATH removed; served hashes, MIME, Host/Origin isolation and owned cleanup passed.
The [candidate record](r19-runtime-bundle.md#frontend-phase-continued-on-2026-10-28)
contains the downloaded metadata ZIP digest and explicit acceptance limits.

## Executed evidence and limits

On macOS, Python 3.12.13 in the task-local environment and Node 22.22.2 (the
package engine accepts Node 22; CI recommends Node 24):

- `npm run dev:doctor -- --base upstream/main`: pass for the initial docs scope,
  with optional Node-major difference. It did not prove later runtime prerequisites.
- Canonical dependency preparation/build completed under the integrator; the
  experiment inspected that emitted build without rebuilding it.
- `node scripts/r19-static-frontend-experiment.mjs`: executed; current static
  output equivalence disproved, source host retained.
- `node --test tests/r19-static-frontend.test.mjs`: two passes, about 0.07 seconds.
- `python3 -m unittest backend.tests.test_bundle_host backend.tests.test_bundle_migration`:
  eighteen passes on the host Python 3.9.6, about 0.50 seconds. Repeated with
  Python 3.12, eighteen passes in about 0.43 seconds. These are dependency-light
  synthetic probes, not the required Windows candidate gate.
- `.venv/bin/python -m pytest -q backend/tests/test_runtime_bundle.py backend/tests/test_runtime_composition.py backend/tests/test_bundle_host.py backend/tests/test_bundle_migration.py`:
  fifty-seven passes in about 0.61 seconds after the final peer-review fixes.
  The integrated final source run is recorded by the integrator.

The added tests prevent new false acceptance claims and ordering/data-loss cases
that ordinary source handoff tests do not exercise. The two implementers review
each other's actual source and check outputs; integrated checks and the final
source identity are recorded by the integrator. Review corrected unsafe resume
after a failed barrier, missing recovery-path link checks, unexpected resumed
snapshot files, persistent quiesce-failure blocking and raw fixture-parent links.
The reciprocal runtime review also found and corrected settings inside a
disposable root and a build-doctor dependency on the caller's working directory.

Still unavailable after the new synthetic-browser comparison: an ordinary
real-user selected-profile reopen, real extension behavior,
same-user Windows protected test credentials, verified global writer shutdown,
bounded process-tree supervision and guarded source updates. Clean Windows
artifact, native OCR/capture/DPI, game/toolchain and R02b measurements remain in
the wider candidate record. A passing synthetic probe does not close those gates.

A separate Windows-only source probe now uses the production DPAPI helper with
new protected TEST blobs under marked temporary roots. It checks copied legacy
fallback decryption under the same user, unchanged host-locator bytes, no plaintext
in the manifest/snapshot and an actually unreadable named-store fixture that
still requires preserving repair. It accesses no real account, host credential
locator or network client. The focused hosted job records actual OS/Python/import
versions and rejects a skipped test. Its server/source result is separate from
an extracted full candidate, Windows 11 acceptance and live account recovery;
the migration manifest continues to report incomplete with activation disabled.
