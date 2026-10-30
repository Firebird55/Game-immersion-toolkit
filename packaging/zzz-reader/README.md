# Compiler-free Node boundary prototype

Only the original synthetic helper is executable through the frozen resolver.
`voice-links` and `cinematic-links` always fail before PATH discovery, compilation
or downloads in `_links`. Changing receipt fields to `approved` cannot enable a
game reader. The normal source adapter remains separate and retains its current
setup behavior. This is not completion of the actual ZZZ compiler-free helper.

The build script uses only Node built-ins and build-host `tar`. It accepts an
explicit archive; it does not download, run npm, inspect an installed game, or
collect the source checkout into a runtime. The exact supplier inputs are in
[inputs.json](inputs.json), independently of a caller's receipt. Official inputs
were observed on 2026-10-28 at the
[Node 24.22.1 release](https://nodejs.org/en/blog/release/v24.22.1) and its
[SHA256 list](https://nodejs.org/dist/v24.22.1/SHASUMS256.txt). Hash verification
does not establish publisher signatures or complete supplier acceptance.

On a Windows x64 build host, supply the exact archive named in inputs.json:

```powershell
node scripts/build-zzz-reader-helper.mjs --node-archive C:\build-inputs\node-v24.22.1-win-x64.zip --platform win-x64 --output-root output/zzz-helper-probe --probe
```

The builder checks the archive, exact executable member, AMD64 PE header and
complete archive LICENSE, then emits only `probe.mjs`, `probe-worker.mjs`,
`sum.wasm`, project LICENSE/NOTICE, app-local Node and its full LICENSE. Authored
text emission is explicitly LF on every build host; upstream archive bytes are
not normalized. The manifest maps every file to size/SHA256, rejects extra empty
directories/nonregular files, and has an ordinal canonical build identity. The
Python resolver additionally requires every byte to be pinned by the outer
runtime resource manifest at `helpers/zzz-reader-probe/`; this prototype does not
silently add a child kind to the frozen application profile.

`--probe` invokes the copied executable from an unrelated working directory,
with empty PATH and no HOME/account locations, NODE_OPTIONS, NODE_PATH,
NODE_COMPILE_CACHE or npm configuration. The helper checks `process.execPath`
against the app-local executable. A real module worker instantiates the authored
arithmetic WASM, adds 19+23 and roundtrips synthetic Chinese JSON. Input/output
are explicit files under an owned temporary work folder; the application tree
must remain byte-identical. The sanitized observation at
`output/checks/r19-node-helper.json` is written only after owned process exit and
temporary cleanup. It contains hashes/versions/booleans, never text or paths.
The macOS ARM64 pin permits local protocol evidence, not Windows acceptance.
Hosted Windows Server evidence is separate from Windows 11 25H2 acceptance.

## Actual ZZZ build-only quarantine recipe

The existing reader imports Node crypto/zlib, `ooz-wasm` and `xxhash-wasm`. The
exact pinned TypeScript source/license and npm archives can be supplied manually
from the URLs in inputs.json. No game or catalog files are inputs to this step.
Keep all supplied files and emitted bytes in private ignored build storage:

```powershell
node scripts/build-zzz-reader-helper.mjs --prepare-blocked-reader --reader-source C:\build-inputs\galgame-perform.ts --reader-license C:\build-inputs\reader-LICENSE --archives-root C:\build-inputs --output-root output/zzz-reader-blocked-quarantine
```

Archive names must be `typescript-5.9.3.tgz`, `ooz-wasm-2.0.0.tgz` and
`xxhash-wasm-1.1.0.tgz`. SHA512 integrity is the existing package-lock pin; SHA256
and runtime member hashes are recorded independently in inputs.json. The build
extracts only the verified TypeScript compiler and its notices to an owned
temporary directory, transpiles the upstream source with the original unpacker
export appended, target ES2022/module ESNext, then deletes the compiler tree.
No TypeScript/npm executable is emitted.

The quarantine includes immutable `reader.mjs` and deterministic adaptations of
both owned extractors. Adaptation requires the exact expected bootstrap shape,
replaces runtime TS transpilation/tool-directory JS writes with an adjacent
immutable reader import, and preserves explicit private cache/output paths.
The original six owned script hashes and all emitted bytes are in the blocked
manifest. Node `--check` parses the emitted entrypoints without importing or
executing upstream code. No game helper is run by this build step.

The selected runtime module closure is:

| Input | Selected runtime files | Native/WASM detail |
| --- | --- | --- |
| zenless-voice `bb2b9790d2d45a5c662c36cd9f046d05893d0ef4` | transpiled galgame-perform.ts, upstream LICENSE | Contains unreviewed game-format/decryption constants; no source body is checked in or published here. |
| ooz-wasm 2.0.0 | package.json, index.js, build/ooz.js, LICENSE | Embedded WASM in generated JS; GPL-3.0-or-later. No native proprietary Oodle DLL is included. |
| xxhash-wasm 1.1.0 | package.json, esm/xxhash-wasm.js, LICENSE.md | Fixed ESM import condition; embedded WASM. MIT. No CJS/UMD/workerd variants are selected. |
| Original toolkit adapters | extract_voice_links.mjs, extract_cinematic_links.mjs, scene-catalog.mjs, cinematic-links.mjs, comic-links.mjs, zzz-dialogue.mjs | Custom project attribution license, retained separately. |
| Node 24.22.1 | exact platform executable and full archive LICENSE | Node's built-in crypto/zlib; not a claim that the whole runtime is solely MIT. |
| TypeScript 5.9.3 | none at runtime | Verified build-only compiler, removed after transpilation. |

The source and npm module inventories have hashes, not an assertion of complete
rights. The pinned npm ooz distribution does **not** establish its complete GPL
corresponding C++/WASM source, exact compiler/Emscripten toolchain, build scripts
and notices. The upstream project is
[SnosMe/ooz-wasm](https://github.com/SnosMe/ooz-wasm); a matching source revision
and reproducible source offer remain absent from this candidate. Combined
GPL/custom-attribution terms and upstream game constants/catalog redistribution
also remain unreviewed. The quarantine is never collected by the runtime spec,
uploaded as an artifact, or accepted by the prebuilt resolver. It has a distinct
`proxy-zzz-quarantine-v1` blocked manifest, no authorized runtime entrypoints and
`game_execution_allowed: false`.

Before an actual production reader can be collected, close those source/rights
items, independently validate the emitted import/WASM closure under app-local
Windows Node with developer tools absent, validate owned cancellation and
bounded shutdown, and exercise the real formats against an authorized installed
game without publishing its data. Until then the frozen ZZZ preparation gate
stays closed; a successful authored probe cannot change it.
