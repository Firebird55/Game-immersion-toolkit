# NTE compiler-free archive runtime

Updated 2026-10-31. The desktop adapter can execute the owned self-contained
NTE bridge with its actual verified dependency directory. It no longer rejects
NTE solely because it is running from a bundle. This closes a runtime dispatch
gap; it does not approve an incomplete candidate for distribution.

## Runtime contract

`backend/nte_toolchain.py` requires the complete `helpers/nte` application-local
.NET 10.0.14 inventory and a separate `toolchains/nte` inventory. The dependency
contract pins the actual UEExtractor 1.0.8.7 managed assembly bytes, checks
every file against the outer application inventory, rejects extra libraries,
links and incompatible platforms, and retains supplier evidence as inert notices.
An approval-like manifest field cannot replace the required binary identities.

Only `inventory`, `index`, `voice` and `voices` are available. Inputs must be an
explicit installed-game folder; output must be inside private data/work/cache
storage and outside the game, application and dependency folders. Archive
metadata travels on stdin. The child receives a restricted loader environment
without system .NET discovery, profiling hooks, compiler paths or account values.
No executable download, SDK discovery or compilation occurs in the bundled path.

Existing selected text locales, all four official voice-language identifiers,
authored event/media bindings, movie timing and explicit Zero variants remain
unchanged. Missing recordings still produce missing-pack/unavailable states;
an absent voice is never inferred to be unvoiced. See [language evidence](nte-languages.md)
and the [presentation audit](game-audits/nte.md).

## Build inputs and remaining delivery work

`scripts/build-nte-toolchain.py --output <fresh-private-output>` collects exact
supplier bytes on the build host without executing them. It produces the common
`toolkit-native-resources-v1` inventory for the desktop builder's resource input.
The existing owned bridge builder separately supplies `helpers/nte`. Source
development retains its .NET SDK adapter; end users of a complete desktop bundle
do not need an SDK.

The collector preserves the [UEExtractor source revision](https://github.com/SolicenTEAM/UEExtractor/tree/1dff3554320d530efff26a827819f0e011f1b892),
its MIT notice, and its exact [CUE4Parse submodule](https://github.com/FabianFG/CUE4Parse/tree/6409f38e09e2a21aa839cd77b4515bca6c66f280).
The owned bridge constructs CUE4Parse directly. It does not invoke the supplier
wrapper constructor or native codec downloaders. CUE4Parse's managed OodleSharp
and Zlib defaults decode the installed archives. External OodleUE and zlib-ng
DLLs are neither collected nor permitted in the runtime inventory.

The checked-in [managed component lock](../packaging/game-readers/managed-components.json)
records all 30 Costura-embedded assemblies. Inspection of the exact supplier DLL
matched 29 assembly hashes to exact NuGet package members. The remaining custom
CUE4Parse build identifies its revision in both its informational version and
supplier submodule. Every package archive and selected member is verified again
when collecting resources. No NuGet restore, package installation or package code
execution is involved in that collection.

The collector retains 45 complete managed license/notice texts, including
CUE4Parse's incorporated-code NOTICE, Fmod5Sharp's vgmstream attribution, and
FixedMathSharp's LICENSE, NOTICE and COPYRIGHT. MANAGED-COMPONENTS.json maps each
text to its immutable source URL or exact package member/hash. Original supplier
copyrights, package versions, source references and license metadata are retained.
For packages without a source commit in their metadata, the pinned notice
reference is labeled separately; it is not a claim of reproducible binary source.
The unmodified permissively licensed package binaries are identified by their
exact supplier package and embedded assembly hashes.

The resource receipt binds this lock and collector source to its output. Rights
review and native acceptance remain pending for the final assembled application;
those fields alone never authorize execution or replace the exact inventories.
The helper/apphost contract currently targets Windows x64. The parser and codecs
are managed, but Linux/macOS still require native apphosts, .NET runtime resources
and platform acceptance. The Windows apphost must not be relabeled as portable.

## Validation

Focused tests cover complete notice collection, immutable package/member identity,
missing or altered notices, duplicate components and unsupported custom assemblies.
Existing adapter tests exercise every official voice identifier without SDK
acquisition, and reject missing/tampered/extra runtime dependencies and unsafe
output paths. They are not evidence of installed-game playback.

The managed-only bridge completed these read-only installed-file probes with
system .NET discovery removed and only UEExtractor.dll in its dependency folder:

- Inventory: 804,382 virtual paths, successful exit in 3.36 seconds.
- Index: 113,044 localization rows in each of English, Simplified Chinese,
  Traditional Chinese, Japanese and Korean, successful exit in 16.77 seconds.
- Chinese authored voice: the existing production binding extracted a valid
  46,379-byte RIFF recording in 0.78 seconds, byte-identical to the earlier native
  decoder result. No binding was generated or guessed for this probe.

Earlier native-decoder probes also extracted one archive entry each from English,
Japanese and Korean. Those checked archive decoding, not subtitle-to-voice
alignment or playback for those three languages; the current managed-only probe
has not repeated them. All four language formats retain authored fixtures and
missing-pack states.

These were private apphost/adapter probes while source changes were in progress.
Their dirty-source receipts cannot satisfy final frozen application acceptance
or release provenance. No game data, archive metadata, recordings or private
machine paths are part of the collected resource output.
