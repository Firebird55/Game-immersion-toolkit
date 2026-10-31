# Shared reader completion work

Updated 2026-10-31. This supplements [R19 A/B](r19-completion-plan.md) and
[desktop delivery](desktop-delivery-completion-plan.md). Game identity must not
permanently select a quarantine or a different installation experience. Format,
dependency, rights and native-platform evidence determine each operation's
availability. A synthetic fixture or an approval-like string is not evidence
that a real archive/audio chain works.

| Operation | Implemented now | Remaining work |
| --- | --- | --- |
| RE PAK selected extraction | Owned Python v2/v4 raw/DEFLATE/Zstandard, encrypted table and chunk readers replace compiler-dependent REE; eight installed MSG/SBNK/SPCK/TMLFSM2 byte comparisons pass | Frozen candidate validation, target-platform native Zstandard closure and shared voice-codec verification; see [reader evidence](re-pak-runtime.md) |
| Owned Node grammar operation | Fixed app-local Node command; hash-checked entry/parser/runtime; no system Node/npm fallback in bundles | Include exact resources in each candidate, run retained grammar protocol against an explicit installation and perform platform-native validation |
| Endfield selected VFS | Owned Python VFS 3/4/5 and streaming PCK/bank reader replaces the SDK bridge; private verified numerical metadata stays outside distributed code; installed Chinese text/voice join and exact original clips pass | Frozen candidate and native-platform/codec verification; see [reader evidence](endfield-runtime.md) |
| NTE selected archives | Self-contained bridge dispatches actual archive operations through a strict managed dependency inventory and private output contract; all 30 embedded assemblies have exact supplier/source/notice records | Clean final helper build and native frozen-image acceptance; Linux/macOS need corresponding native resources; see [runtime contract](nte-runtime.md) |
| Wuthering selected archives | Same managed bridge replaces FModelCLI/native codec acquisition; all five study-locale production indexes pass; authored English/Mandarin clips decode | Clean final helper build and native frozen-image acceptance; Japanese/Korean packs absent locally; Linux/macOS need native resources; see [runtime evidence](wuthering-runtime.md) |
| ZZZ scene/voice graph | Existing app-local Node probe and build preparation remain available | Collect actual reader/module/WASM closure with corresponding sources/notices and verified metadata acquisition; prove real scene/voice bindings |
| Shared voice decoding | Existing source decoding and bounded FLAC experiment remain distinct | Replace the rejected FFmpeg snapshot, record complete codec/native/source obligations, then enable each supported codec operation in the packaged resolver |

The Node collector is `scripts/build-node-toolchain.py`. It consumes exact
official Node 24.22.1 archives and integrity-checked Acorn 8.18.0 without invoking
npm or a compiler. Supported collection targets are Windows x64, Linux x64 and
arm64, and macOS x64 and arm64. Collection support is not native acceptance.
Node's complete upstream license and third-party notices, Acorn's MIT notice,
the toolkit license, source version/checksums and a bounded resource inventory
are retained. The resource manifest leaves rights review and native acceptance
pending for the final candidate's review.

The fixed operation uses `backend/hito-grammar.cjs`, Acorn's three runtime files
under `backend/node_modules/acorn/`, and `toolchains/node/` runtime metadata,
executable and notices. `backend/node_tools.py` verifies those resources through
the frozen outer inventory, matches the host platform and exact Node version,
and removes inherited Node loader/module settings. Source installs retain their
existing developer Node behavior. Hito is currently a retired adapter in the
active game registry; this change does not reactivate it or alter public
game/language choices. The retained reader has an executable packaging path.

Local evidence: 24 focused resolver/Hito/storage tests passed. The exact Windows
Node executable loaded the collected Acorn parser with an empty PATH, returned
Node v24.22.1/Acorn 8.18.0 and parsed an authored statement. No preserved explicit
Hito installation was available for a real grammar protocol probe. These checks
do not replace a frozen-image game test or macOS/Linux execution.

All remaining reader operations must use shared preparation progress, retries,
missing-pack/error states, local data roots and export contracts. Preserve all
official voiced languages and their authored bindings while replacing runtime
dependencies. Do not mark unavailable recordings as unvoiced or infer voices
from adjacent text. Missing cross-game screenshot tests remain tracked in the
[screenshot regression plan](screenshot-regression-plan.md).

The blanket bundled-game preparation refusal has been replaced with checks of
the actual audio and archive operations. See [shared preparation readiness](bundled-tool-readiness.md)
for verified behavior, exact missing extractor capabilities and focused checks.
