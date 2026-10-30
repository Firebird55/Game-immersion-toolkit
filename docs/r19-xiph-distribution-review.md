# R19 Xiph FLAC rights, source delivery and maintenance

Reviewed **2026-10-30** for the exact source-built Xiph FLAC 1.5.0 Windows x64
candidate in the [selection ledger](r19-codec-replacement.json) and
[frozen integration evidence](r19-frozen-xiph.md).
The [structured review](r19-xiph-distribution-review.json) binds this decision,
the retained source snapshot, all 35 inspected post-release commits and gates.

**Disposition: the owner approved the scoped build-recipe license resolution.**
On 2026-10-30 the copyright holder explicitly authorized an additional
GPL-2.0-or-later route for exactly the two codec build scripts and input policy,
without the extra visible-credit/link condition. The
[scoped grant](../packaging/codecs/FLAC-BUILD-RECIPES-LICENSE.txt) is delivered in
a new source kit. The general project license remains unchanged. The earlier
MIT description was wrong. The historical kit keeps its original terms;
new-kit build/rebuild and frozen evidence are still pending at preparation.
Canonical source retention, future binary cohosting, other component rights and
ordinary-user Windows acceptance remain separate open gates.

## Exact rights and collected scope

The selected flac.exe is 187,392 bytes, SHA-256
959b7871c00598360734b3792e24b369de6a08f91c02d18abaa7678488b9a355;
FLAC.dll is 247,808 bytes, SHA-256
29c4c88bc8cb17e30aaef2d9af50455abeeccc59bda18d1189dfb7568d9e27d8.
These are our unmodified-source MSVC builds, not Xiph's prebuilt Windows ZIP.
The [official licensing page](https://xiph.org/flac/license.html) distinguishes
the BSD reference libraries from GPL utilities. The actual file headers and
CMake targets in the retained source provide the more precise inventory below.

| Component | Actual terms and evidence | Distribution requirement |
| --- | --- | --- |
| flac CLI, UTF-8 support | GPL-2.0-or-later; src/flac and src/share/utf8 headers | Complete matching source/build inputs, copyright/license/warranty notices and recipient freedoms |
| Static getopt support | Library-GPL-2.0-or-later; src/share/getopt | Retain original notices; the later-version choice permits the supplied LGPL 2.1 text; provide source/relink materials |
| Static ReplayGain analysis/synthesis | LGPL-2.1-or-later; src/share/replaygain_analysis and replaygain_synthesis | Preserve contributors' headers and source/relink materials even though fixed dispatch does not enable gain application |
| FLAC.dll, grabbag/Windows UTF-8 and other BSD support | BSD notices in the original files, including Xiph contributors | Retain each copyright/conditions/disclaimer, including binary notice delivery and non-endorsement |
| Original documentation | Original file notices and COPYING.FDL 1.3 | Retain the entire unmodified source archive; no edited manual is substituted |
| Toolkit build scripts and policy | Additional GPL-2.0-or-later route for exactly the three named inputs; original Firebird55 Attribution License 1.0 remains an alternative | Deliver the scoped grant and full GPL text; no extra visible-credit/link term on the GPL route; general project license unchanged |

The CMake flacapp target links FLAC, getopt, replaygain_synthesis and utf8;
utf8 links grabbag, which links replaygain_analysis. No assumption that unused
features erase linked-code obligations is made. Full GPL/LGPL/Xiph/FDL texts,
AUTHORS, README and file-level contributor headers accompany the candidate.
All original source/build systems remain in the complete tarball, with no patch.

No libogg, external pthreads, libFLAC++, metaflac, compiler or CRT redistributable
is collected in this codec subtree. Its VCRUNTIME/UCRT are named Windows
prerequisites. Other frozen Python/ASR libraries retain their own separate gates;
the codec observation does not license the entire runtime. The source/build
compiler exception is not permission to copy arbitrary Microsoft DLLs.

The toolkit invokes the CLI as a separate process with ordinary files and fixed
arguments; it does not copy GPL implementation code into the Python adapter or
link Python to libFLAC. Treating these as separate works is an engineering
assessment of this integration, not a blanket ruling for future bindings or
protocols. [GPLv2 sections 2, 3 and 6](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)
remain the basis for aggregation, full source and no further restrictions.
Game audio and publisher data are outside this code review. Xiph's upstream
patent statement is not a project-specific patent clearance or warranty.

## Build-recipe license finding and approved resolution

The retained kit's LICENSE is the custom attribution license, not MIT. Its
public-adaptation condition requires visible Firebird55 credit and a specified
link. GPLv2 section 3 includes compilation/installation scripts in the required
source; section 6 bars additional restrictions on recipients. Calling the ZIP
an aggregate, or the library BSD, does not resolve terms on those required
scripts. Compatibility of this custom condition has not been established.
Source-only retention under the files' existing separate terms is not approval
to use this kit as the compliant source offering for a future GPL binary.

A narrow owner decision resolved the additional-terms finding for the new kit
without changing the toolkit-wide license. Approved scope is exactly:

- packaging/codecs/flac-reference.json;
- scripts/build-reference-codec.ps1;
- scripts/reference-codec.py.

The owner explicitly approved the additional **GPL-2.0-or-later** grant on
2026-10-30, without that extra condition on the GPL route. The scoped grant is
1,161 bytes, SHA-256
2725323b963852b42cbfd73f99ccd1068e42f2031742e055e50b4cb1fef5d070.
It preserves copyright/license/warranty notices and the original license as an
alternative. It grants no rights over other toolkit files or third-party code.

The regenerated six-input kit and fixed resolver pins below now include the
grant. Independent delivered-kit build/relink, decode and frozen checks must
still bind these new bytes before acceptance. Even unchanged executable bytes
need newly matched source-delivery evidence. The old snapshot remains historical
source; no runtime binary hash or acceptance flag is changed by this grant.

[LGPL 2.1 section 6(a)/(d)](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html)
supports complete source/relink materials with equivalent network access.
Provide the full CLI/support source and working recipes rather than relying
on replacing BSD FLAC.dll to satisfy the statically linked LGPL components.
Recipients may modify/relink and run their standalone codec; the toolkit's
integrity pins do not promise to run arbitrary replacement binaries. Never add
a blanket reverse-engineering or modification prohibition to codec terms.

## Durable source delivery

The exact 1,086,902-byte [codec-sources.zip](../third_party/codecs/xiph-flac-1.5.0/codec-sources.zip)
is retained in Git, SHA-256
7dc11c7fc0c87c6304b0d09af81d76a4d6229c15ce8590681a74e14ca85d2f6b.
[Source commit 0b2ae0e](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/blob/0b2ae0e4d4890225b2551c98d52ee9d4fea1412e/third_party/codecs/xiph-flac-1.5.0/codec-sources.zip)
provides a content-pinned review location. The archive's five inputs match the
previously rebuilt Windows delivery byte for byte. The original source tarball
retains all 907 entries. Recipes use CRLF: verify raw hashes before comparing
canonical LF text. [Source directions](../third_party/codecs/xiph-flac-1.5.0/README.md)
include the self-contained rebuild command and all license distinctions.
The commit-pinned raw download was retrieved without authentication on
2026-10-30 and matched all 1,086,902 bytes and the SHA-256 above. This verifies
the public review copy, not future canonical release hosting.

The new [GPL-recipe source kit](../third_party/codecs/xiph-flac-1.5.0-gpl-recipes/README.md)
contains six inputs, **1,087,821 bytes**, SHA-256
7dd55f62a9c558bf1065ec89b873f9f17dc6c542e806bf44e157475c870ab7b9.
It retains the same unmodified upstream tarball and original LICENSE, plus the
exact scoped grant and current recipes/policy. Windows CRLF recipe bytes and
byte-exact LF grant text are recorded separately. New Windows build/rebuild and
frozen receipts are pending; historical successful receipts above do not cover it.

This removes dependence on seven-day Actions retention for the review copies.
The publication scanner admits only these two exact path/size/hash tuples; changed,
appended, truncated or unrelated ZIPs remain rejected and content scanning stays
active. A PR branch still does not prove protected canonical upstream retention.
No repository protection setting, tag or release was created or changed.

For each future binary publication:

1. Retain the matching source kit on the canonical main/release lineage. Keep
   every old source snapshot indefinitely, including withdrawn binary versions.
2. Embed that kit and full notices beside codecs/xiph-flac, and attach a named
   xiph-flac-<version>-<source-kit-digest>-sources.zip asset beside the binary on
   the same download page. Offer equivalent access without an account or extra
   charge. A supplier URL, a moving branch, generated GitHub source archive or
   Actions artifact is insufficient as the sole source delivery.
3. Bind binary, source-kit and notice hashes, upstream commit, patches and build
   recipe/toolchain identity in the release provenance and SHA256SUMS. Publish
   source directions that map each binary to its exact complete kit and terms.
4. Before exposing the binary, download both staged assets independently,
   verify hashes/provenance and rebuild the delivered source kit. Verify notices
   and source directions from the extracted binary. If any step fails, block
   publication; do not substitute a newer unreviewed source archive.
5. Use the existing clean-main release process. Where adopted, GitHub's
   [immutable release workflow](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
   stages all assets in a draft before publication. Protected retention and
   publication settings must be observed, not assumed from this document.

The release maintainer owns availability checks every 30 days and before each
publication. If a source URL fails or hosting moves, restore the same bytes and
directions before offering further covered binary downloads. Preserve source
when withdrawing a binary. No written-offer route under GPLv2 section 3(b) is
chosen: retention policy is not a newly issued three-year source offer.
Canonical cohosting, download-page integration and operational retention remain
release gates; this PR publishes source only and builds no installer.

## Maintenance baseline and review of all later changes

The official release API still identifies 1.5.0 (2025-02-11) as stable on
2026-10-30. The inspected upstream head is
59fa3402cb19b6b7c85b916f138cfb03c7b27504, with **35 later commits**.
All 35 commits' changed files were inspected, with patch-level review of the
decoder/native changes used in this scope assessment. The structured review
records each exact URL, scope and disposition. No fix is claimed backported.
Upstream's [security page](https://github.com/xiph/flac/security) has no published
advisory or SECURITY.md visible; that is not absence-of-vulnerabilities evidence.

| Change group | Fixed-dispatch assessment |
| --- | --- |
| Cuepoint ordering/signed bounds, 530d765 / 9dbb051 | Changed callback is opt-in via --cue; current CLI has no --cue/--skip and bounds --until to 1..16000 |
| Ogg finish-link aborts, 1a0dd03 / e26a435 | Changed loop is compiled out with FLAC__HAS_OGG=0; revisit before Ogg/chained support |
| Rewinds, b2c46b5 | Change is in the fuzzing-build branch; ordinary CRC handling is unchanged |
| Unknown-length streams, 9547dbc | New capability is not adopted: the adapter rejects sample count 0 and requires exact output bytes |
| RF64/foreign metadata and ReplayGain, d17f0d2 / 9d23884 / 380001b | No encoding, preserved foreign metadata or ReplayGain application in fixed dispatch |
| Encoder/cuesheet/bitwriter fixes | Fixed invocation always decodes; retain the full source and re-review any encoder/writer adoption |
| Metadata/encoder null assertions, fab9967 | Changed APIs are outside the identified fixed calls; this is not a general null-safety proof |
| Bitreader/linkage and const cleanup, bba8f29 / b430c3a | Compiler/qualifier refactors without algorithm-body changes; preserve exact MSVC evidence and revisit toolchain changes |
| Metaflac, tests/fuzzers, docs, other build/platform/thread/SIMD changes | Not collected, test-only, documentation-only, different build path or disabled feature; exact per-commit reasoning is in the ledger |

This is source/control-flow triage for the bounded experiment, supported by its
existing fixtures. It is not exhaustive fuzzing, exploit reproduction, general
malformed-stream safety, predictive-frame acceptance or clean-PC evidence.
Input/time/output bounds reduce exposure but do not prove a decoder safe.

## Maintainer policy and stop conditions

The repository maintainer responsible for R19 codec adoption owns this review.
Refresh upstream releases, commits, bug/advisory reports and license changes at
least every **30 days** (next baseline review **2026-11-29**) and before every
binary publication. A new format/CLI/metadata limit, architecture, dependency,
CRT, compiler/SDK/image or license also triggers review. If ownership or a fresh
review is unavailable, new binary publication stays blocked. This document does
not create an automation or claim an unattended monitoring service.

For a credible in-scope security/integrity report, target initial triage within
24 hours and stop new affected publication immediately while impact is unclear.
Target a reviewed patch/replacement within seven calendar days; if unresolved,
keep publication blocked or withdraw affected binary downloads while retaining
their source. Review ordinary bug reports within 30 days. These are maintainer
response targets, not claims that upstream provides a support SLA.

Prefer a reviewed stable release. If a necessary fix exists only as a commit,
apply a minimal exact patch with dated modification notices, complete patch
source, new kit/pins and recorded applicability; otherwise keep the feature
blocked. Never discover latest binaries, borrow PATH/SDK tools or silently
replace a pinned artifact. Rebuild and relink from the delivered kit, rerun
positive/negative decode, cancellation/deadline/cleanup and actual DLL-origin
probes, and reassess changed licenses/notices/CRT/native prerequisites.
Rollback means a separately reviewed known-safe candidate, not returning to
the rejected Gyan snapshot. An unresolved security issue is not fixed by a
version label or a passing happy-path fixture.

## Gates preserved

The Windows Server 2025 observations prove the named authored operations only.
Clean Windows 11 25H2, ordinary-user VCRUNTIME/UCRT availability, CPU/DPI/capture,
OCR, Framework/WOW64, actual installed-game formats, broader codecs and full
export remain unavailable/unrun. Overall runtime component/source/native review
also remains separate. The production runtime is hard-disabled, every existing
receipt keeps production execution false and R19 incomplete, and PR #60 stays
draft. PR #59 is unchanged. No installer, release/tag, Pages publication, account
write or live migration occurs in this review.

## Checks for this review

Seven targeted publication/mobile-boundary cases passed. The new builtin-only
publication test runs the actual scanner against an owned Git repository: exact
snapshot acceptance; changed, appended and truncated copies; unrelated ZIP/TGZ
and uppercase ZIP names; and a changed historical snapshot hidden by restoring
the current bytes. The uppercase case reproduced a case-sensitive extension
bypass before the fix. Historical and current archive checks now use the same
case-insensitive ban; the one accepted source path/hash remains exact.

The source-only Windows job now runs that publication test and rebuilds from
the retained Git kit, after requiring its bytes to match the freshly generated
delivery. Source/native receipts still require independent download verification;
a queued or running job is not a pass. Runtime codec code, recipes, pinned
binary/source bytes and hard-disabled production gates are unchanged.

Stable branch-check record 87e03528-5703-4f78-8926-a35d47393343 resolved actual
upstream/main ba0b7c34c358f1664220674e5ff8bb7f30502e5f. Typecheck and the initial
source-guard snapshot's 272 Node tests passed (one skipped), then macOS Python
collection lacked pyaudiowpatch; later checks did not run. After the history
refinement, record d296a3b2-1f30-46bc-9229-1394d24b3259 remained source-stable
but stalled in the unchanged companion-router tests. Only the owned router
worker, identified through the unique check log and parent tree, was stopped;
the runner finalized failed/incomplete. Neither aggregate is a full pass, and
the later case-extension correction is covered by the targeted cases above.
Generated-guide/link checks and public audit are run separately.

[Windows retained-source run 41128774508](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41128774508)
passed at clean source 0c7941585066d1815cdc57eb71152c8565055f5c: the real
publication-CLI regression, four source-trust tests, actual selected-codec
build/decode/fault/cleanup/DLL-origin probe, then a fresh build and the same
probe from the retained Git kit using its own delivered recipes. The generated
kit was required to match that retained copy before expansion. All selected
binary/notice/source-kit hashes were unchanged. This is hosted Server 2025
source/rebuild evidence; the full frozen job was skipped in this bounded mode.

Downloaded artifact 13012097837 (1,094,227 bytes) matched SHA-256
17a0af9b36663a06d39c0bb2ab948aa5cb63870eb067d62f5a6dc2b2fade0200.
Its five outer entries, source/recipe hashes and original custom LICENSE,
anonymous/Git/CI source-kit byte equality, both build/probe identities, exact
binary/notice hashes, PCM/failure/cleanup/native-origin records and disabled
gates were independently checked. No binary or raw process/compiler log was
uploaded. This historical run preceded the scoped grant; it does not verify the
new six-input kit or prove production source-hosting/Windows acceptance.

Compatibility watch returned 2 after an initial sandbox DNS failure. Public
settings/lookup/language/AI/API reference review found no added/removed endpoints;
live account/UI equivalence remains outside this source-policy change. Its
baseline is unchanged, no account was accessed, and no shared code was edited.
