# NTE compiler-free archive runtime

Updated 2026-10-30. The desktop adapter can execute the owned self-contained
NTE bridge with its actual verified dependency directory. It no longer rejects
NTE solely because it is running from a bundle. This closes a runtime dispatch
gap; it does not approve an incomplete candidate for distribution.

## Runtime contract

`backend/nte_toolchain.py` requires the complete `helpers/nte` application-local
.NET 10.0.14 inventory and a separate `toolchains/nte` inventory. The dependency
contract pins the actual UEExtractor 1.0.8.7, Oodle and zlib-ng DLL bytes, checks
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
its MIT notice, and its exact [CUE4Parse submodule](https://github.com/FabianFG/CUE4Parse/tree/6409f38e09e2a21aa839cd77b4515bca6c66f280)
with the Apache notice. The embedded assembly's full transitive version/source/
notice inventory still needs to be completed before distribution.

The exact Oodle build comes from [WorkingRobot/OodleUE](https://github.com/WorkingRobot/OodleUE/tree/9bd4cc1e644f2890785b970cc09b96ea488be4e6).
Its supplier README references the Unreal Engine EULA; the archive contains no
license notice. A public binary download is not evidence of a redistribution
grant. Establish the applicable grant for those bytes or replace the decoder.
The [Zlib-ng.NET wrapper](https://github.com/NotOfficer/Zlib-ng.NET/tree/52175d749e2a00ddf9b10610197c27b2c1d65658)
has an MIT notice, but the exact native zlib-ng build/source and notices also
remain to be closed. These are specific supplier obligations, shared by any game
using the same dependencies. They are not permanent per-game policy exceptions.

The receipt consequently keeps rights review and native acceptance pending.
Current collection and apphost contracts target Windows x64. Linux/macOS require
corresponding native libraries and bridge/runtime resources; the Windows DLLs
must not be relabeled as portable. Final frozen-image acceptance and distribution
checks are still required.

## Validation

106 focused adapter, dependency-closure, path/environment and NTE audit tests pass;
one directory-link test needs Windows symlink privileges and is skipped on this
host. Authored fixtures exercise every official voice identifier through the
real Python dispatch without an SDK, executable download or compiler. They verify
missing/tampered/extra dependencies, wrong platforms, unrelated output paths and
approval-string rejection. They are not evidence of installed-game playback.

The build-host collector downloaded and verified all three selected DLLs and
four available supplier notices. No game data, archive metadata, recordings or
private machine paths are part of its resource output.

An actual self-contained owned bridge built with the pinned SDK/runtime completed
these read-only installed-file probes with system .NET discovery removed:

- Inventory: 804,382 virtual paths, successful exit in 3.69 seconds.
- Index: 113,044 localization rows in each of English, Simplified Chinese,
  Traditional Chinese, Japanese and Korean, plus 18,828 selected Chinese banks;
  successful exit in 17.83 seconds.
- Chinese authored voice: the existing production binding extracted a valid
  46,379-byte RIFF recording. No binding was generated or guessed for this probe.
- English, Japanese and Korean archives contained respectively 33,016, 33,120
  and 33,058 media entries. One real entry from each extracted as RIFF. These
  checks demonstrate archive decoding only, not subtitle-to-voice alignment or
  playback verification for those three languages.

This was a private apphost/adapter probe while other source changes were in
progress. Its dirty-source build receipt cannot satisfy final frozen application
acceptance or release provenance. The runtime dispatch, supplier-rights review
and complete desktop acceptance remain separate checks.
