# Xiph FLAC 1.5.0 source kit with scoped GPL build recipes

The copyright holder approved the additional GPL-2.0-or-later grant on
2026-10-30 for the exact two build scripts and codec input policy named in
[FLAC-BUILD-RECIPES-LICENSE.txt](../../../packaging/codecs/FLAC-BUILD-RECIPES-LICENSE.txt).
The general project license and upstream code licenses remain unchanged.

[codec-sources.zip](codec-sources.zip): **1,087,821 bytes**, SHA-256
7dd55f62a9c558bf1065ec89b873f9f17dc6c542e806bf44e157475c870ab7b9.
The six files are the original upstream flac-1.5.0.tar.xz, input policy, two
self-contained build/verification scripts, original project LICENSE and scoped
additional grant. The complete original tarball retains all 907 entries and
GPL/LGPL/BSD/documentation notices. No upstream C source patch, executable,
DLL, compiler, recording or private data is included.

The ZIP preserves Windows CRLF build-input bytes and byte-exact LF grant text.
Verify raw hashes before canonical text comparison. Extract it to a fresh
build-host directory and invoke its own scripts/build-reference-codec.ps1 with
inputs/flac-1.5.0.tar.xz and a new output root, as documented for the
[historical source kit](../xiph-flac-1.5.0/README.md). Build-host MSVC/CMake and
Python are separate prerequisites; no developer tools are needed on the user PC.

The historical 7dc11c7f kit remains retained at its original path and is not
retroactively relicensed. New kit hashes, independent build/relink and native
results are recorded separately. This new source copy is byte-verified against
Git, an anonymous commit-pinned download and the downloaded CI artifact.
[Run 41137727454](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41137727454)
at `8f38e6debddecacba9197946a2ff70ee3fc24e59` passed both the selected Windows
build and an independent rebuild using this kit's own inputs/scripts, with
unchanged executable/DLL hashes, actual decode, fault, cleanup and DLL-origin
checks. The [distribution review](../../../docs/r19-xiph-distribution-review.md#durable-source-delivery)
records the downloaded artifact identity and limits. The later bounded
[frozen checkpoint at acc68be](../../../docs/r19-frozen-checkpoint-20261031.json)
also passed, with its source and sanitized metadata downloaded and verified.
Native binaries remain runner-local; this is not final-candidate acceptance.
No production or Windows 11 gate is granted by this file.

Canonical retention and cohosting beside any future binary remain required.
Retain each reviewed historical path/hash tuple; add a separate pinned source
identity for future changes rather than overwriting an old accepted snapshot.
