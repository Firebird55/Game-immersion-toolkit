# Star Rail metadata helper

This separate GPL-3.0-or-later executable reads original client metadata and
bounded x64 instruction ranges as data. It never loads a game DLL or runs client
code. The ordinary dialogue provider still uses its existing preparation path;
this helper contract alone does not establish autonomous updates.

The frozen [HSRGlobalMetadata source](https://github.com/im-remi/HSRGlobalMetadata/tree/bb66f7c59d73cadcd026d817a011598ea23c5313)
is compiled through an owned metadata-only entrypoint. The 34 selected source
files exclude dummy assembly export, Mono.Cecil and the embedded dummy DLL.
[Iced 1.21.0](https://github.com/icedland/iced/tree/601c40570d6c986c8e1a6a2e483dd2fdf5ade552),
under MIT, provides managed instruction decoding. Exact source archives,
individual compiler inputs, NuGet package, managed assembly and licenses are
pinned in `inputs.json`. These are software dependencies; new third-party game
data is not required to regenerate metadata.

On a build host, first run `npm run dev:doctor`, then prepare the software with
`python scripts/prepare-starrail-reader.py --cache <private-cache> --output
<new-prepared-directory> --download`. Omit `--download` for an offline replay.
Build with `scripts/build-game-reader-helpers.ps1 -Kind starrail`, supplying
`-PreparedRoot`, the verified SDK and the usual evidence/output directories. The
shared builder enforces SDK 10.0.403, runtime 10.0.14, a matching native build
host, closed package inputs and an authored data probe. It emits a self-contained
apphost; installed users need neither an SDK nor a source compiler.

The helper payload includes full GPL/MIT notices, the exact selected GPL compiler
sources, the decoder source archive and an archive of its owned entrypoint,
project, build scripts and pin material. Uncompiled dummy export sources and
their embedded DLL are excluded. The complete upstream GPL archive stays in
private build evidence to authenticate source selection. Runtime validation
checks the shipped source members against the compiled source identity
and exact software hashes. The toolkit's project license does not replace the
helper's GPL terms. No original client files, extracted metadata, derived keys
or dialogue tables belong in the helper payload or public repository.

The `metadata` operation accepts an authenticated private input directory and a
new output directory. The caller must authenticate all three complete original
files against their official manifest before invoking it. The `disassemble`
operation accepts a data file, strict JSON range request and new output file.
Ranges carry file offset, virtual address and byte count; each is bounded to
64 KiB and 8,192 instructions, with aggregate limits of 16 MiB and 262,144
instructions per request. Decoding
rejects malformed/truncated instructions rather than dropping unread bytes.
All operations reject existing outputs and paths through links. The caller
stages results privately and publishes a generation only after its complete
semantic and integrity checks pass.

An optional `control_flow: true` range follows statically known direct branches
and a bounded compiler switch pattern: unsigned index guard, RIP-relative signed
32-bit table and register jump. It enumerates every table edge without evaluating
an input or executing instructions. Overlapping instructions, unterminated flow,
unknown indirect branches, external conditional branches and paths bypassing the
switch guard fail. This permits enum-label analysis without interpreting embedded
table bytes or unreachable tail data as instructions.

The separate `native-graph` operation accepts `{"entry_rva": <unsigned integer>}`
and follows direct branches between original x64 PE unwind regions. The initial
entry and each newly reached region require an original region-start boundary.
It reads at most 16 regions / 32 KiB of code and emits at most 8,192 instructions,
with source-region SHA-256 values, exact edges and returns. Calls are opaque
external edges; indirect branches, traps, overlap, graphs without a return and
unproved boundaries fail. Unreachable bytes are not decoded. The Python adapter
rechecks whole-native identity, PE mappings, original function-table entries,
region hashes and the complete reachable graph before returning it. This
provides data for description derivation; it does not enable metadata-key
fallback or change the ordinary provider default.

`starrail_native_preparation.prepare` joins complete original acquisition,
metadata regeneration, managed decoding, bootstrap/protocol descriptions and all
requested table descriptions. Cache identities cover the authenticated inputs,
helper artifact and owned derivation logic. Failed or incomplete generations
retain the previous descriptor receipt and complete outputs. Source checkouts
build only the fixed software in private directories with a closed package feed;
bundled installations resolve only the verified included apphost.

Functional research regenerated metadata from complete manifest-verified Global
4.6 and 4.7 inputs with the same frozen source and metadata-only entrypoint.
Managed decoding derived all nine bootstrap fields on both versions through the
unchanged owned description API, and reproduced the native string codec
description. The initial research build used SDK 10.0.302. A separate Windows
delivery trial then built the unchanged helper at source commit
`2efe139f44720d9402dbf2fa7f4922c6e9f9bf79` with the exact pinned SDK 10.0.403 and
runtime 10.0.14. The SDK archive and both runtime packages passed their SHA-512
pins before extraction; restores used only that closed local feed. The shipped
207-file resource set passed the ordinary prebuilt resolver, including exact
runtime members, corresponding sources and notices. Its build identity is
`481994032e491f59a6d491e408c440c2f58f1cd63c28278c7b4d0a84bc849b26`.

That self-contained apphost regenerated metadata from complete
manifest-MD5-verified Global 4.7 inputs with the SDK removed from `PATH` and
`DOTNET_ROOT` pointing to an empty directory. Its 189,595,914-byte dump and
12,498,550-byte literal map exactly matched the earlier control hashes. This
proves the Windows helper's compiler-free execution and pinned build path;
full desktop candidate acceptance, other platforms and the complete ordinary
worker/update/recovery acceptance remain separate requirements.

The subsequent graph bridge at source commit
`9a0c4dcc6c00b129c68639391f5e7f328f14cc79` also passed the exact SDK/runtime
build, authored malformed-input probes and production prebuilt resolver. Its
207-resource local payload has build identity
`c30cfd97613122bda90c8fd80b1c5a3c2a9fdacccd89ee0037075aef3e1a7f29`;
all nine owned source-input hashes match exactly. With no installed SDK/runtime
available, the apphost reproduces the original Global 4.7 type-initializer graph:
708 instructions, two PE-owned regions and 4,295 source bytes. Addresses,
instruction lengths, edges, returns and region hashes match an independent
static control. The complete original native file's manifest MD5 is rechecked;
no metadata dump or original instruction execution is used for this graph.
This proves the delivered Windows graph contract, while complete metadata-key
recovery and ordinary worker/platform acceptance remain separate.

## Android DATA-IR adapter

`backend/starrail_android_ir.py` implements the existing helper `disassemble`
and `native-graph` operations over the APK-verified `PackagedX64Decoder`. It
requires the real Android provider and binds the decoder proof and owned adapter
source into its identity. A missing runtime/source binding or unrepresented IR
semantics raises a typed unresolved-contract error. It does not diagnose a
publisher format change. Unsupported vector decorators remain unresolved.

The adapter formats structured operands rather than trusting `op_str`, including
unsigned/sign-extended immediates, RIP displacement, register and condition
aliases, `movabs`, implicit string operands and Iced pseudo-operations. Linear
decoding must consume the entire requested range. Control-flow decoding retains
the guarded switch-table checks, overlap and branch-bypass rejection; graphs
retain original PE/unwind ownership and the existing region, byte and instruction
limits. Calls are opaque. Invalid or incomplete requests create no result and
cannot replace an earlier output.

An authored-data trial compares the existing authenticated Windows CAPI reference
and frozen Iced helper: 87 linear ranges and nine control-flow ranges at three
exact 64-bit addresses match, together with the complete split-PE graph. These
are synthetic instruction bytes, not original client instructions or Android
execution. Host regressions cover malformed/partial decoding, missing IR,
prospective graph limits, wrong ownership and preservation of earlier metadata.

The adapter intentionally has no metadata operation, fallback build or factory
activation. Portable required-metadata parsing, signed-APK HSR acceptance and
ordinary preparation/update/recovery remain required. The saved required-method
projection component is a separate dependency; this adapter does not silently
import it or modify the C# helper, Android native/JNI code or locale guards.
