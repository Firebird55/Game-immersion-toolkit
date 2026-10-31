# Lexirise public compatibility review — 2026-10-31

The public review found one functional preference gap in shared reader 1.0.12:
Lexirise now accepts `wordPopupOpenMode: shift-hover`, but the pinned reader
handled it as click mode. It also contained stale grammar-state explanatory
text. Both corrections are implemented in canonical shared version **1.0.13**;
consumer synchronization and package verification are recorded below. Existing
grammar buttons continue to save local choices.

## Scope and provenance

The watch report at `2026-10-31T16:27:43.243Z` flagged changed documentation and
website hashes, with no added or removed endpoint strings. A fresh public fetch
confirmed the same endpoint set. The reference advertises 47 method/endpoint
operations; the watch extracts 43 unique path strings, including example paths.
These counts describe different things and are not an API schema comparison.

The reviewed consumer pin is `@firebird55/lexirise-components` **1.0.12**, source
commit `2e84f74cf77ea4773463331c7ecde0b05faf31f8`. Review covered its account,
client, capability, word-popup and reader sources, plus the toolkit's settings
transport, reading service and frontend reading adapter. The initial review did not change vendor files, credentials, accounts, running
services or game data. The fix follows the canonical shared release/import
workflow; no consumer vendor source is edited manually. Public
responses and their receipt remain in ignored `output/lexirise-review-20261031`.

## Contract review

| Area | Public evidence and consumer result |
| --- | --- |
| Settings | The [API reference](https://lexirise.app/api-reference#get-settings) still returns global and per-language preferences. The consumer preserves returned fields, sends only explicit writable differences, and excludes native/effective read-only values. Null resets and partial updates retain their documented meanings. |
| Translation | The toolkit uses the per-language effective translation target before global fallbacks, keeping account and language cache scopes separate. The public language module retains Chinese script-specific translation codes. |
| Accepted values | Reading aids, five tone-palette identities, nine popup tab IDs, four definition-section IDs and first/last opening preference match. The new **shift-hover** mode requires the shared 1.0.13 adaptation; unchanged endpoint strings did not reveal this accepted-value change. |
| Lookup | Public popup normalization still keeps Definition enabled, appends omitted defaults and preserves a readable definition fallback. Public floating UI retains portal rendering and viewport/scroll handling. The consumer uses its own supported portal container, fixed positioning, collision handling and composed-path dismissal; it does not depend on upstream CSS selectors or DOM structure. This source review is not a new browser or Shadow DOM test. |
| Analysis and dictionary | The [analysis](https://lexirise.app/api-reference#analysis) and dictionary contracts retain token offsets, pending analysis, contextual questions and translation readiness. Existing requests and response handling remain compatible. Empty or pending translations are not treated as a completed lookup. |
| Languages | Fresh public arrays exactly match the pinned **31 study languages** and **26 translation/interface languages**. Reading-aid availability, grammar support for Mandarin/Japanese/Korean, tone coloring for Mandarin/Cantonese and unavailable TTS for Latin/Ancient Greek/Classical Chinese match the capability manifest. These reading capabilities do not imply original game voice availability. |
| Transport and AI references | The [API reference](https://lexirise.app/api-reference#authentication) continues to document authenticated REST JSON and multipart audio upload. The toolkit uses that contract. The public [AI-readable index](https://lexirise.app/llms.txt) was also reviewed; it links product and learning pages and does not specify a replacement MCP or streaming transport. No authenticated API or MCP call was made. |
| Grammar state | The [documented PUT operation](https://lexirise.app/api-reference#set-grammar-state) accepts known/unknown state. Shared reader 1.0.12's claim that this API is read-only is therefore outdated. Its local-only behavior still works; changing that behavior would require a separate explicit account action. |

## Public source identities

These hashes identify inspected bytes, not an upstream release or permanence
guarantee. Website chunks can disappear after a deployment.

| Public source | SHA-256 |
| --- | --- |
| [API reference HTML](https://lexirise.app/api-reference) | `3f45247485b7d49338cd60f4f6fcd65e9854563a5ee326758202cbb9084f8354` |
| [Language/capability module](https://lexirise.app/_next/static/chunks/2-_nw52iokrxo.js) | `5e2c6ff57ba2f5f78e77ea86ce4c6df3bbc079d234364596a4a1a0fffebba344` |
| [Reading/popup settings module](https://lexirise.app/_next/static/chunks/3s-cfl8tdgtmm.js) | `b7e358bea253a3a1b82aa4394dd7eefc55be6f6bf77df0a7e9b270c1dd7b9be5` |
| [Lookup/floating UI module](https://lexirise.app/_next/static/chunks/2nzxjj_v_r-x8.js) | `6c60472c93c3cfc51e47393d7710298374c817a843e3571aad8b26f698587547` |
| [Global settings module](https://lexirise.app/_next/static/chunks/1i0u8jpv5kylz.js) | `d8256ad47239eac2d1aef9f52e4f3db430d4b0429cd275ab9f4fe9360301aa9c` |
| [AI-readable index](https://lexirise.app/llms.txt) | `3aa46da6ceaebac8bbf441f3dd7c4b47bb7079663c8ddca17b2b49c25629057c` |

## Adaptation and verification

Canonical shared 1.0.13 adds Shift-only pointer entry, Shift toggling over a word,
100 ms dismissal after leaving a pointer-opened popup, and the preference option.
Modified shortcuts, key repeats, typing fields, dragging and disabled popups do
not trigger it. Click/tap and Enter/Space remain available. The grammar copy now
accurately describes local status storage without changing account-write behavior.

Shared contract checks passed **26/26**. The isolated consumer fixture passed all
**eight** Chromium/Firefox × document/Shadow DOM × mouse/touch cases against the
canonical sources before release. It checks portal movement, typing, modifier
handling, keyboard access, click mode, disabled popups and absence of account
writes. These are browser tests, not new physical-device or live-account evidence.

The public watch baseline was recorded only in the canonical shared repository
after the review. The [1.0.13 hosted release](https://github.com/Firebird55/Lexirise-shared-components/actions/runs/41228771735)
passed at `da10892b3f2bc6f0b518b79c353edbf2fcb9af00`. All **12** downloaded release
asset hashes matched `SHA256SUMS`; provenance matched the annotated tag's commit.
The package SHA-256 is `cd25f71a092eb3d5ce8f1d28cb08c5253a7b5b9c0a4036afb898d3b1390cb291`.

The required `shared:update -- --version 1.0.13 --all` ran in isolated linked
worktrees. Both consumers passed their type, contract and build checks; the
toolkit also passed its complete Python suite. It produced toolkit pin commit
`d4f22be` and Emulingo pin `605c4be`, following its browser-regression commit
`6dbfb26`. The new eight-case gesture matrix passed again against the imported
package, along with all four existing popup cases and the Firefox isolated-world
settings checks. The active game companion, accounts and storage were untouched.
Remaining acceptance evidence stays in the
[reader completion plan](reader-lan-completion-plan.md#remaining-acceptance-evidence).

## Deployment refresh at 22:09 UTC

The watch at `2026-10-31T21:40:12.157Z` reported unchanged documentation and
changed UI hashes. A fresh unauthenticated fetch at 22:09 UTC compared all 42
current homepage JavaScript chunks with the earlier source receipt. Forty are
byte-identical after replacing only their two PostHog build-ID annotations.
This includes the settings, reading/popup, lookup and language/capability modules
reviewed above. Their accepted settings, lookup behavior and language arrays
therefore remain covered by the previous contract review.

The other two chunks correspond to earlier files under new names. After the
same instrumentation normalization, their complete sources differ only in one
opaque `dismissPromo` server-action identifier and the public website's
`X-Lexirise-Version` value changing from `0.15.24` to `0.15.25`. Neither is a
consumer API contract change: the toolkit does not invoke the website's promo
server action or impersonate its client version. The normalized API-reference
hash remains `4c6d3e5f84efaf1f0c953151bf564fadc5b552e14ec28dcaf5cbc6a3289a0b77`;
the AI-readable index is byte-identical to the prior receipt.

The current raw contract-module SHA-256 identities are:

| Source | SHA-256 |
| --- | --- |
| [Language/capability module](https://lexirise.app/_next/static/chunks/2-_nw52iokrxo.js) | `489818903844eec7224a5c9cdffdfcc85595e3b4e5b777da146942434483bd71` |
| [Reading/popup settings module](https://lexirise.app/_next/static/chunks/3s-cfl8tdgtmm.js) | `2d41ed938af103e5aa1e58beb83963e885737abf969c86bcd3c8948a9659bf8e` |
| [Lookup/floating UI module](https://lexirise.app/_next/static/chunks/2nzxjj_v_r-x8.js) | `814728eb7b9fd8c288375caa59d091049268d497fd45d2fb8d168df88f0aa8b9` |
| [Global settings module](https://lexirise.app/_next/static/chunks/1i0u8jpv5kylz.js) | `fdb542bd9ec4e6818fdde3cde18ab8b8a19ec6316aa078279fa17d62e5b5a91d` |

The full fetch and exact replacement comparisons remain in ignored
`output/lexirise-review-20261031-refresh`. This refresh required no functional
adaptation to shared **1.0.14** and no account operation. The shared baseline was
left unchanged; a repeated hash alert for this reviewed deployment does not
imply an unreviewed behavior change. Later public deployments still require a
new comparison. The [shared typography report](shared-reader-typography-2026-10-31.md)
records 1.0.14's separate release and consumer validation.
