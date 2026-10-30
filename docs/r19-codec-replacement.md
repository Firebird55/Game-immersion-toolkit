# R19 maintained codec selection and source verification

Selected on **2026-10-30**: **Xiph FLAC 1.5.0**, built from its official source
for Windows x64 with Ogg, external pthreads, C++ wrappers, examples, tests,
documentation generation and SIMD/assembly optimizations disabled. This is a
replacement candidate for the first bounded native-FLAC-to-PCM slice. It is not
a general FFmpeg/game decoder or a production-runtime activation.

The [rejected Gyan FFmpeg 7.1 review](r19-codec-artifact-review.md) remains binding.
That binary is not a fallback for this candidate. The existing frozen experiment
now uses the new CLI/DLL in the [frozen integration](r19-frozen-xiph.md); its old
FFmpeg receipt cannot be attributed to Xiph. The standalone source/rebuild
checkpoint below remains distinct from subsequent frozen evidence.
PR #59 remains unchanged; no installer is built.

## Selection and maintained scope

[Xiph's release](https://github.com/xiph/flac/releases/tag/1.5.0) identifies 1.5.0
as the current stable release and publishes a SHA-256 for its complete source.
Upstream development remains active; the inspected head on 2026-10-30 is
59fa3402cb19b6b7c85b916f138cfb03c7b27504 (2026-10-28). This is evidence of an
active maintained project, not a guarantee of defect-free software.

The [input policy](../packaging/codecs/flac-reference.json) pins source commit
1507800de4b70e21be71f38caa0d9079d0bc6e45 and flac-1.5.0.tar.xz, SHA-256
f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920.
The downloaded tarball matched the published hash. The official Windows ZIP was
inspected for supplier comparison and matched its published hash
53f1500f0d6e7c61379d7fee50d4a9f7f504c650009506d9ba015530d76c0dde;
its prebuilt executables are **not** the selected artifact.

The [upstream Windows release recipe](https://github.com/xiph/flac/blob/1507800de4b70e21be71f38caa0d9079d0bc6e45/doc/release_checklist.md)
uses MinGW and an unpinned latest libogg. Instead, the selected candidate uses
the supplied CMake build system with Ogg and multithreading explicitly off.
Only the source-built flac.exe and FLAC.dll are collected. There is no external
codec library, compiler runtime copied from the build host, libFLAC++, metaflac
or downloaded executable in this candidate.

The inspected 35 commits after the release include an
[RF64 overflow-check correction](https://github.com/xiph/flac/commit/d17f0d2f0dedc495acbed2f547b0cee32cda79a5)
and [ReplayGain bound check](https://github.com/xiph/flac/commit/380001b324db1581cc9a3e369c2c0cc972a0421c).
The candidate stays limited to native FLAC decode with raw PCM output, without
RF64 input/encoding, foreign-metadata preservation or ReplayGain application.
These changes are recorded, not silently claimed to be backported. Before
broadening the command surface, revisit current upstream fixes and either
rebase or supply exact reviewed patches. The upstream security page has no
published advisories/policy; that is not evidence of absence of vulnerabilities.

## Complete covered source, recipes and notices

The self-contained source kit contains the original unmodified source tarball,
the exact input policy, the two build/verification scripts and their license.
The historical kit carries the custom Firebird55 Attribution License; the
earlier MIT label was incorrect. The owner subsequently approved a limited
additional GPL-2.0-or-later route for those three inputs, without the extra
visible-credit/link condition. The [new source kit](../third_party/codecs/xiph-flac-1.5.0-gpl-recipes/README.md)
includes the scoped grant. Its Windows rebuild and frozen evidence remain pending;
the historical selection hashes below are preserved. The
[rights/source/maintenance review](r19-xiph-distribution-review.md) records both.
No source patch is applied. The tarball retains
all upstream build systems, C/C++ sources, headers, resource files, copyright
headers, licenses and authorship; it is not a wrapper sdist or a source link.

[Build recipe](../scripts/build-reference-codec.ps1):

    ./scripts/build-reference-codec.ps1 -SourceArchive inputs/flac-1.5.0.tar.xz -OutputRoot <fresh-build-root>

The build host needs Python 3.12+, CMake and supported MSVC/Windows SDK tools.
Those unmodified general-purpose tools are prerequisites, not user runtime
dependencies or undisclosed codec source. The recipe selects an installed
MSVC 17/18 generator explicitly, records its compiler/CMake versions and actual
generator, builds only the flacapp target, and verifies all policy options from
the resulting CMake cache. It rejects changes to the extracted upstream source.
Source hashes and compiler observations bind the output inventory to this build.
No future rebuild is assumed to reproduce the same bytes across toolchain/image
changes; the actual binary hashes must be reviewed for each new build.

[Source-kit verification](../scripts/reference-codec.py) checks archive, notice
and source/recipe hashes, rejects traversal, links/reparse points, hardlinks,
case aliases and special files before extraction, and preserves existing output.
The source ZIP has an exact file allowlist, fixed entry timestamps and no
binary, PDB, credential, log or host-path payload. Its receipt records every
delivered source file and the ZIP SHA-256.

Notice delivery retains the full GPL, LGPL, Xiph/BSD and FDL texts, AUTHORS,
the project README and file-level source copyright headers. flac.exe is
GPL-2.0-or-later, including its GPL/LGPL command support; the reference library
is BSD-3-Clause. The source package also preserves original file-level terms.
The BSD library label is not applied to the GPL CLI or LGPL support objects.
The supplied LGPL text is the applicable later-version choice for getopt's
Library-GPL-2-or-later notice and covers the 2.1-or-later ReplayGain code.

For a future network binary download, ship the matching complete source kit
with equivalent access beside it under the GPLv2 section 3 network-distribution
provision. Retain notices and source directions next to the candidate. This
step uploads the public source kit and sanitized verification metadata only;
no production binary, installer or corresponding-source release promise is
published. Seven-day CI artifact retention is review evidence, not a durable
production source-delivery service. The exact kit is now also retained in
[versioned Git source](../third_party/codecs/xiph-flac-1.5.0/README.md).
Canonical retention and cohosting beside a future binary remain separate gates.

## Verification protocol and explicit Windows gates

The existing R19 workflow has a separate manual codec-source mode with a
12-minute ceiling and no browser matrix. It builds the selected source, checks
normal/delay x64 PE imports, removes developer/loader/account variables for the
probe, marks candidate files read-only and decodes the independently authored
512-sample FLAC frame to all 1,024 expected PCM bytes.

The [actual probe](../scripts/probe-reference-codec.py) reuses PreparationJob's
Windows Job Object ownership for decode/deadline/cancellation and stages output
before atomic publication. Pre-cancelled, truncated-input and deadline cases
must retain prior output and clean up. Only this authored native FLAC case is
verified; predictive variants, Ogg, other codecs and installed games remain out
of scope.

The second build starts from a fresh extraction of the **delivered source ZIP**,
using that kit's recipe and input policy rather than the live repository's
builder. It must decode the same PCM and regenerate the identical source kit.
This checks that the delivery is complete and usable; it is not an assertion of
byte-identical binaries.

Dynamic MSVC/UCRT system DLLs remain named native prerequisites; no redistributable
CRT files are collected. Static import inspection cannot prove actual loaded
module origins, ordinary-user availability, CPU coverage or clean Windows 11
25H2 behavior. Hosted Server 2025 evidence does not close those gates.
Frozen adapter/DLL-origin work is tracked in the [integration evidence](r19-frozen-xiph.md).
Clean-PC CRT resolution and real game/export acceptance remain required.
The standalone source-candidate receipts keep runtime collection disabled;
the separate frozen collector permits only its bounded experimental operation.
All receipts keep production disabled, Windows 11 unavailable, installer not
built and R19 incomplete.

## Verified Windows candidate and downloaded source delivery

[Run 41072777245](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41072777245)
passed at clean source 9dc86be1886084afd9084fd291abc196f66f9beb on hosted Windows
Server 2025, image windows-2025-vs2026/20261021.278.1. It used MSVC
19.51.36260.0, CMake 4.4.4 and the Visual Studio 18 2026 generator. Both the
initial source build and independent delivered-kit rebuild passed the exact PCM,
pre-cancellation, deadline, truncation, previous-output and cleanup cases.

The selected files are:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| flac.exe | 187,392 | 959b7871c00598360734b3792e24b369de6a08f91c02d18abaa7678488b9a355 |
| FLAC.dll | 247,808 | 29c4c88bc8cb17e30aaef2d9af50455abeeccc59bda18d1189dfb7568d9e27d8 |
| codec-sources.zip | 1,086,902 | 7dc11c7fc0c87c6304b0d09af81d76a4d6229c15ce8590681a74e14ca85d2f6b |

The two builds also produced identical executable/DLL hashes on this same
toolchain image in different source/build directories. This is observed evidence
for these builds, not a promise across compiler/SDK/image updates.
The [selection ledger](r19-codec-replacement.json) persists the exact files,
notice hashes, source-kit inputs, toolchain, normal/delay imports and gates.

Downloaded source/metadata artifact **12986665350**, **1,093,294 bytes**, matched
GitHub's SHA-256
c0a23208750458fce5c5ba3ae7cc909c65e70a8967cfb4a3fc65fadf4666f01c.
The outer allowlist, inner ZIP hash, all five delivered entries, original tarball
and its 907 entries, notice hashes, source/build identities, both decode receipts
and disabled gates were independently checked. The Windows checkout uses CRLF
for recipe text: exact raw receipt hashes were checked first, then canonical
LF text was compared with Git sources. The original tarball bytes remain exact.
No runtime executable/DLL was uploaded or independently downloaded.

Source-kit preparation and self-contained rebuild were verified at this
checkpoint. Production source hosting/retention, license integration and the
explicit Windows gates still need their own acceptance.
Static PE imports name FLAC.dll, KERNEL32.dll, VCRUNTIME140.dll and UCRT API sets;
no delay imports were found. Actual DLL observation and frozen dispatch were
unprobed at this checkpoint; subsequent results are recorded in the
[frozen integration](r19-frozen-xiph.md).

## Local checks and first native attempt

Four source-trust tests pass locally, including malicious archive/destination
cases absent from the old runtime codec tests. The initial local fixture used
macOS's symlinked temporary prefix; canonicalizing the owned test root made the
fixture valid without relaxing source-path rejection.
The broad changed-check record 74588c6c-597d-4727-85a7-46b0257f44fb remains
failed/incomplete: typecheck and 271 Node tests passed (one skipped), then macOS
Python collection lacked pyaudiowpatch; later aggregate checks did not run.

[First native source run 41032262168](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41032262168)
passed the four trust tests but stopped before compilation: the recipe selected
Visual Studio 2022 while the actual image was Windows Server 2025/VS2026.
The recipe now selects the actual installed supported MSVC generator.
This failure is retained and is not a decode/source-rebuild pass.
