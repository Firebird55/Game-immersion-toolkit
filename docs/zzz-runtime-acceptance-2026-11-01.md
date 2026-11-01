# ZZZ packaged reader verification — 2026-11-01

The production desktop reader now uses verified app-local Node, a precompiled
scene reader and a decompressor built from retained preferred source. Runtime
preparation does not need npm, TypeScript, a compiler or a system Node installation.
Missing or changed resources produce the common installation-repair state.
Historical authored-probe receipts do not authorize production extraction.

The [construction contract](../packaging/zzz-reader/README.md) records the exact
inputs, complete notices, source build and independent review. This changes
packaging and execution, while retaining the existing
[dialogue and language coverage](game-audits/zzz.md).

## Observed Windows evidence

The resource inputs were collected from clean source commit
`b0de3607a2bef88c35797156179e8d3fd390dbbc`. The reader build identity is
`47a7fc94d78f045aaa0214ce500f14c1e12edf81328a93d839024db36ea2e838`.
The source-built decoder SHA256 is
`b49c334cb0ecfeb632ae3696744eef794200b953218e69066f11b216e9c9bf83`.

- The independent input review accepted the exact selected source/notice
  inventory, archive members, source-build receipt and generated decoder. It
  replayed the pinned TypeScript transformation and obtained identical bytes.
- The native probe passed nine checks using the actual app-local executable:
  compiled module import, a known xxHash64 vector, invalid archive refusal,
  compressed Kraken expansion, malformed Kraken refusal, an authored resource
  catalog, both compiler-free entrypoints and immutable input preservation.
- The rebuilt decoder expanded a six-byte compressed Kraken fill quantum to
  4,096 verified bytes. This exercises decompression, beyond loading a module or
  copying uncompressed input.
- A private installed-file probe used the production resolver with an empty
  `PATH`, separate private metadata/output and the same verified resources.
  Dialogue, comic and cinematic extraction completed in 8.67, 9.06 and 231.38
  seconds respectively. All 223,634 scene records and 922 cinematic records
  exactly matched the previous catalog: zero added or removed records.
  The existing catalog and immutable resources remained byte-for-byte unchanged.

Raw installed-game inputs, extracted records, paths and logs remain private.
Only aggregate results and public source/build identities are recorded here.
The comparison proves retained bindings for that installed snapshot; it does not
invent missing bindings, add a voiced language, prove every presentation or
replace the separately required original-audio playback checks.

## Platform and installer acceptance

The collectors support Windows x64, Linux x64 and macOS arm64. Each target must
run its own hosted source build and native probe. The first Windows hosted probe
reached the actual modules but rejected a noncanonical runner temporary path.
Commit `db7f3c5` canonicalizes only the directory the probe creates; production
path/link validation remains intact. Its focused regression and local native
probe pass. That repair still requires a successful hosted rerun.

Linux/macOS native execution, the complete frozen desktop payload and final
installer acceptance remain separate target gates. The local evidence above is
not a claim that those gates passed. Follow the
[desktop delivery plan](desktop-delivery-completion-plan.md) for final artifacts,
hosted results and installation handoff.
