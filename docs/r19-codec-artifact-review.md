# R19 codec artifact: rights, source delivery and servicing review

Subsequent work on 2026-10-30 [selected and source-verified Xiph FLAC](r19-codec-replacement.md).
The negative disposition below applies to the old Gyan FFmpeg artifact and is
not reversed by the new candidate's source/decode evidence.

Reviewed **2026-10-29** against implementation commit
93cd61c3f3d206533312172113646e4ebc21b954 and its
[extracted Windows evidence](r19-codec-experiment.md#extracted-windows-observation-2026-10-29).
The [structured review](r19-codec-artifact-review.json) records exact identities,
all observed configuration flags, supplier dependency/version entries, PE imports,
primary sources and the disposition. It is review metadata, not runtime policy.

**Decision: do not promote this exact FFmpeg 7.1 artifact to production.**
Its origin and GPLv3 licensing basis are identified. Complete corresponding
source and notice delivery have not been established, and its unserviced
snapshot is rejected as a production input. Keep the existing bounded experiment
quarantined. A successful decode remains functional evidence; it closes none of
these distribution gates.

| Review | Evidence established | Disposition |
| --- | --- | --- |
| Rights | Exact executable, upstream/supplier GPLv3 notice, GPL/version3 configuration and wrapper/BSD separation | License identified; exact dependency notices and integration review incomplete; redistribution not approved |
| Source delivery | Supplier points to exact FFmpeg commit; original binary matches wheel | FFmpeg source pointer identified; complete dependency sources, patches, build scripts and delivered source bundle absent from inspected delivery |
| Servicing | Original September 2024 snapshot; later 7.1.1/7.1.2 security fixes; many dependencies without complete source mapping | Reject this artifact for production; select a maintained input with complete source/notice closure |
| Windows | Prior authored FLAC decode passed on Server 2025; static PE imports inspected here | Clean Windows 11 25H2, actual codec DLL loads and native acceptance remain unavailable |

No runtime pin, allowed operation, release asset, installer or production gate is
changed by this review. PR #59 remains at
8369c9534762cd2232fb44424772bd6b5a72b6d2; PR #60 remains draft.

## Artifact identity and supplier chain

The selected wheel remains imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl
(31,246,824 bytes), uploaded 2025-01-16 according to
[PyPI metadata](https://pypi.org/pypi/imageio-ffmpeg/0.6.0/json).
Its SHA-256 is 02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a.
The member executable is 87,638,016 bytes, SHA-256
2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3.

The imageio release's [packaging task](https://github.com/imageio/imageio-ffmpeg/blob/ae47d8028c237ca5507ceef1b843ee427b442887/tasks.py)
copies prebuilt executables from imageio-binaries. It is not an FFmpeg compiler
recipe. The [binary rename commit](https://github.com/imageio/imageio-binaries/commit/f8f64710ea88e7e4a352c0f7d8c0deac9f5fd685)
records Git blob 2f7e6546b8648db9a1e2a7270d02e4569e3fd546; computing the Git blob
hash over the wheel member reproduces it.

The executable identifies itself as **7.1-essentials_build-www.gyan.dev**, built
with gcc 14.2.0 (Rev1, Built by MSYS2 project). The original
[Gyan 7.1 release](https://github.com/GyanD/codexffmpeg/releases/tag/7.1),
published 2024-09-30, supplies ffmpeg-7.1-essentials_build.7z. The downloaded
archive is **28,223,874 bytes**, computed SHA-256
4d903da24c1c07ee72e08a38689327ab0593da9d8802beae2fc50868c0c04cfe.
Streaming its bin/ffmpeg.exe through SHA-256 reproduces the exact wheel member
hash above. No executable from this archive was run during this review.

The original archive's README.txt has SHA-256
cf9643d68f4149f534cf5e010760cb5125b109c1ec04cfdab4fd38e968212e69.
Its LICENSE matches the already pinned full GPLv3 text:
8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903.
The README and release both point to FFmpeg commit
b08d7969c550a804a59511c7b83f2dd8cc0499b8. Thus the previous unknown supplier
and top-level source pointer are resolved. The GitHub release asset has no
published digest field; the computed archive hash and byte agreement are
integrity/identity observations, not a signed build attestation or reproducible
build result.

## Rights and notice findings

The wrapper's BSD-2-Clause text covers imageio's wrapper. The wheel contains no
separate binary-source bundle or complete embedded-library notice collection.
The codec experiment already adds FFmpeg's GPLv3 text and upstream license
overview; these are necessary evidence, not complete distribution clearance.

The exact configuration enables GPL, version3 and static linking, and does not
enable nonfree. The executable's license text permits GPL version 3 or later.
The supplier README calls the build GPLv3. Use **GPL-3.0-or-later** as the
FFmpeg executable's identified basis, rather than the wheel's wrapper license.
FFmpeg's [version-specific license overview](https://github.com/FFmpeg/FFmpeg/blob/b08d7969c550a804a59511c7b83f2dd8cc0499b8/LICENSE.md)
also identifies GPL-sensitive external libraries, LGPLv3/Apache version
constraints and IJG attribution requirements. Absence of nonfree does not prove
that every notice, source obligation or patent question is resolved.

The supplier lists **40 external-library entries** and **13 hardware-acceleration
entries**. The latter include interfaces and header/SDK capabilities; they are
not proof of 13 redistributable drivers or independent bundled packages.
The structured review preserves every entry and supplied version verbatim.
Those versions are supplier assertions, not independently verified source pins.

| Observed group | Concrete examples from this binary | Required disposition |
| --- | --- | --- |
| GPL-sensitive integration | AviSynthPlus v3.7.3-75-gc6649361, rubberband v1.8.1, vidstab v1.1.1-13-g8dff7ad, x264 v0.164.3192, x265 4.0-6-ga009ec077, xvid v1.3.7 | Retain exact licenses/copyrights and corresponding source/patches for incorporated versions |
| Version3-sensitive libraries in FFmpeg's overview | GMP; OpenCORE AMR-NB/WB 0.1.6, VisualOn AMR-WB 0.1.3, VMAF v3.0.0-95-gd95b69e0 | Resolve actual version/license choices, Apache notices where applicable and source linkage |
| Remaining linked libraries and transitive code | GnuTLS, libssh 0.11.1, SDL prerelease-2.29.2-377-g1edaad172, zlib and the other entries in the ledger | Exact source/archive/patch/notice mapping; a configuration switch is insufficient |
| Compiler/runtime and hardware interfaces | MSYS2/GCC, pthread support, AMF, ffnvcodec, oneVPL, VAAPI and Windows APIs | Classify incorporated objects, exceptions, headers and external/system dependencies individually |

The README gives no version for **bzlib, GMP, GnuTLS, iconv, fontconfig,
OpenJPEG, libxml2, lzma or zlib**. Media Foundation is separately an OS-interface
entry. Full dependency and transitive source/notice mapping remains unresolved
even for entries that do have a version description.

The toolkit invokes a separate CLI executable through fixed arguments and
standard FLAC/PCM files; it does not link FFmpeg libraries into Python.
The engineering assessment is a candidate aggregate boundary, subject to the
independence conditions in GPLv3 section 5. A subprocess alone is not automatic
approval, and the toolkit's MIT license does not replace the codec's terms.
This review grants no patent clearance for the broad compiled build.

## Corresponding source and concrete delivery design

The controlling reference is the exact
[GPLv3 text, sections 1, 4–6](https://github.com/FFmpeg/FFmpeg/blob/b08d7969c550a804a59511c7b83f2dd8cc0499b8/COPYING.GPLv3).
For an eventual network binary download, use section **6(d)**: offer equivalent
access to the matching source beside the binary, without an additional charge.
Clear directions may identify another server, but the distributor remains
responsible for source availability. A wrapper sdist, a mutable upstream branch
or the FFmpeg top-level source link alone does not cover this static binary.
The physical-product written-offer route in 6(b), including its duration rule,
is not the proposed route for this download.

Before accepting any replacement, prepare these concrete, independently checked
outputs. They are a source-delivery design; none is published by this review:

| Output | Required content and verification |
| --- | --- |
| Codec source archive | Exact FFmpeg tree and every incorporated dependency's preferred source, patches and applicable notices; stable identifiers and SHA-256 per input |
| Build recipe | Actual configure flags, compiler/linker target, dependency options and scripts needed to generate/install the covered executable; classify System Library and general-purpose-tool exclusions |
| Source/binary manifest | Map binary and source archive hashes, source commits, patches, configuration, licenses and notice locations; no fabricated source pins for version strings |
| Recipient source instructions | Adjacent binary/source download directions, no special key/account required; verify downloads and source correspondence from a fresh checkout |
| Distribution notices | Full applicable licenses, copyright/NOTICE/attribution text, modification statements where relevant and matching source directions |

The inspected original Gyan archive contains executable documentation, presets,
its README and GPL license, but no complete dependency-source archive or
compiler recipe. The inspected imageio release script packages that executable;
it does not reconstruct the missing build. No claim is made that such sources
could never be obtained elsewhere. They have not been established and delivered
for this artifact.

GPL source correspondence does **not** itself require byte-identical rebuilding.
Project verification must nevertheless demonstrate that the supplied trees,
patches and scripts produce the described build/configuration. Reproducible
bytes would provide additional provenance; they have not been demonstrated.
Do not replace missing corresponding source with a claim that unused encoders
or a FLAC-only CLI policy eliminate obligations for code still in the executable.

## Servicing disposition and replacement requirements

This is the original 2024 FFmpeg 7.1 supplier snapshot repackaged by imageio in
January 2025. The [upstream security ledger](https://ffmpeg.org/security.html)
records later fixes, including:

| Later release | Fix | Relevant upstream change |
| --- | --- | --- |
| 7.1.1 | CVE-2025-0518 | [af_pan sscanf correction](https://github.com/FFmpeg/FFmpeg/commit/b827ac49b770635fc666f8543cb9585e1bc6308b) |
| 7.1.1 | CVE-2023-6602 / CVE-2023-6604 | [HLS extension validation](https://github.com/FFmpeg/FFmpeg/commit/b753bac08f6881b2d3dea8f1ab84c81550f35897) |
| 7.1.2 | CVE-2025-9951 | [JPEG2000 cdef validation change](https://github.com/FFmpeg/FFmpeg/commit/4c036ec307040469783bab0b7223006c0facec1d) |

These are evidence that the supplier-identified source is behind later security
servicing; no supplier patch/backport record was found in the inspected delivery.
They are **not** reproduced exploits or claims that these particular paths are
reachable through the fixed native-FLAC operation. The adapter fixes the
demuxer/protocol/output and has deadlines; the compiled binary still contains
broader code. The dependency advisory review is also incomplete. A clean hash,
old supplier version or successful fixture cannot establish security currency.

The runtime component maintainer and release maintainer should select a
**maintained, minimal Windows codec build with complete source/notice delivery**.
For the current FLAC slice, omit unrelated encoders, network libraries, hardware
interfaces and filters where possible. Decide the exact license/configuration
from the actual replacement, not an assumed LGPL label. No replacement version
or binary is selected or built in this review.

For each candidate, check upstream security changes and dependency advisories,
record applicable fixes/reachability limits, then update archive/executable/source
pins together. A replacement requires the actual frozen decode/failure/lifecycle
probes and source-download checks again. Do not fall back to this rejected
snapshot merely because it decodes the fixture. Recovery or rollback may use only
another accepted artifact; an obsolete version requires a fresh explicit review.

## Windows gates and evidence limits

Static inspection of this exact x64 PE found **19 normal DLL imports**, no
delay-import descriptors and no embedded Authenticode certificate table.
The ledger lists each DLL, including msvcrt.dll. This does not prove signature
trust, current system-library servicing, delay-free runtime loading or absence
of LoadLibrary/driver dependencies. Hash verification establishes selected bytes.

The codec subprocess's loaded-module inventory was not captured by the earlier
parent-process inventory. Keep that native dependency probe open. Clean Windows
11 25H2 without developer tools must still verify runtime/CRT resolution, actual
DLL origins and cleanup with the accepted replacement. Existing OCR, capture,
DPI, Framework/WOW64, installed-game and broader R19 gates remain separate.
Server 2025's bounded FLAC pass supplies none of that missing acceptance.

## Review checks

The original supplier archive and wheel were read without executing the codec.
The wheel executable SHA-256, Git blob SHA-1, original supplier executable
SHA-256 and supplier notice hashes agree. The ledger's 40/13 entries and 56
configuration flags were checked against the exact README and embedded
configuration; the SHA-256 of that ASCII string without its NUL is
5c7613daf44b35cec408d53ce3ccacc609f543cb89d3d6564d7625ca3325f92c.
That differs intentionally from the earlier full diagnostic-output hash.

No runtime code or build inputs change, so the existing Windows decode evidence
is retained at its actual tested commit rather than rerunning the broad suite
for review documentation. Generated documentation/link/publication checks apply
to this change. Raw supplier archives, private observations and logs remain under
ignored output/checks; the public files contain review metadata and source links.

The review's manual identity/ledger verification passed without codec execution,
as did documentation/generated-guide/link checks and the public source/history
audit. Changed-check record e4960ca6-4544-4608-ac59-34b9219e00af conservatively
selected the full gate for the new JSON review metadata. Its source fingerprint
was unchanged: typecheck and 271 Node tests passed (one skipped), then macOS Python
collection lacked pyaudiowpatch. Later aggregate checks did not run; that record
is failed/incomplete, not full-suite evidence. No browser/native suite is repeated
for this documentation-only review.

The required public compatibility watch returned 2 with no added/removed
endpoints. Public settings/effective-language/lookup-tab/AI references and the
landing page were inspected without account access; live UI compatibility
remains open. No shared code, account settings or watch baseline changed.
