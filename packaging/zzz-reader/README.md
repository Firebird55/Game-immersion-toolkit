# Compiler-free ZZZ reader

The desktop runtime uses a precompiled ZZZ scene reader, an app-local Node
runtime, and an embedded WASM decompressor built from retained preferred source.
Installation and game preparation do not invoke TypeScript, npm, a system Node
installation, or a compiler. Game files remain inputs on the user's computer.

The generic desktop build collects this reader through the same immutable
resource manifest used by other game helpers. Missing or damaged resources
produce an installation repair state. A synthetic probe receipt or an
`approved` string cannot substitute for the selected production files.

## Exact inputs and source

[production-inputs.json](production-inputs.json) pins the
[zenless-voice reader](https://github.com/simon300000/zenless-voice/tree/bb2b9790d2d45a5c662c36cd9f046d05893d0ef4),
TypeScript 5.9.3, ooz-wasm 2.0.0, xxhash-wasm 1.1.0, and their preferred source
archives. The collection helper verifies archive SHA256, npm SHA512, exact
selected members, and complete license files. It rejects archive links,
noncanonical paths, duplicate members and oversized expansion.

The original TypeScript and MIT license are retained. The build-only compiler
exposes the existing unpacker export and emits ES2022/ESNext; the two package
imports become fixed relative paths. The emitted code, fixed transformation
recipe, compiler archive identity and source hash are recorded. The compiler
and npm archives are build/review evidence and are not shipped as executable
runtime dependencies.

| Component | Runtime selection | Terms and preferred source |
| --- | --- | --- |
| zenless-voice | Original TypeScript and precompiled module | MIT; exact original source archive and full LICENSE retained |
| ooz-wasm | Unchanged wrapper and source-built embedded WASM | GPL-3.0-or-later; full C++/headers, upstream CMake recipe and full GPL terms retained |
| xxhash-wasm | Unchanged ESM module | MIT; exact source revision, preferred WAT/JS, build scripts and full LICENSE.md retained |
| Emscripten runtime | JS/WASM code emitted by the source build | Exact preferred source and full Emscripten, compiler-rt, musl, libc++ and libc++abi terms retained |
| Owned adapters | Fixed dialogue/comic/cinematic entrypoints | Toolkit attribution license retained with the exact owned recipe |
| Node | Separately collected platform executable | Full archive LICENSE, including bundled dependency terms |

[ooz-build.json](ooz-build.json) records the Emscripten 6.0.13 supplier archives,
source revision, compiler arguments and independently observed generated output.
The build runs the exact compiler with explicit configuration and a verified
Node executable. An authored compressed Kraken fill quantum must expand
correctly; malformed input must fail. No proprietary Oodle DLL is selected.
This is our source build, not a claim to reproduce the npm supplier's
undocumented generated WASM. The complete retained recipe allows rebuilding it.
The GPL component remains identified as GPL; it is not relabeled MIT or as
original toolkit code.

## Construction and acceptance

After collecting the pinned Node runtime, build the decompressor and reader:

```powershell
python scripts/build-ooz-runtime.py --output output/ooz-build --work output/ooz-work --cache output/ooz-source-cache --node output/node-resources/toolchains/node/node.exe
python scripts/build-zzz-toolchain.py --platform win-x64 --output output/zzz-resources --evidence-root output/zzz-evidence --input-cache output/zzz-inputs --node-executable output/node-resources/toolchains/node/node.exe --ooz-build-root output/ooz-build
python scripts/probe-native-zzz.py --zzz-resources output/zzz-resources --node-resources output/node-resources --output output/native-zzz-probe.json
```

Use fresh output/work/evidence directories; input caches may be reused only
when their bytes still match their exact pins. Linux and macOS use their native
Node executable and platform target. No installed game is needed for the
hosted authored-format probe.

The independent desktop input reviewer compares the candidate's exact source
commit, full source/notice bytes, npm archives, selected runtime inventory and
source-build receipt. It replays the pinned TypeScript transformation and
requires the same emitted bytes. Native execution is a separate check. The
hosted matrix runs construction and authored format execution on Windows x64,
Linux x64 and macOS arm64 before desktop acceptance. A local Windows result
does not establish Linux/macOS execution or every installed game presentation.

## Historical diagnostics

[inputs.json](inputs.json) and `scripts/build-zzz-reader-helper.mjs` describe the
older compiler-boundary experiment. Its synthetic probe and quarantined
supplier build remain diagnostic formats. They are not collected by the
production workflow and cannot authorize or replace this reader. Their old
blocked receipts describe those historical outputs, not a permanent game gate.
