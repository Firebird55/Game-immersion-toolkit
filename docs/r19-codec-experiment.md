# R19 first codec step: verified FFmpeg and a bounded real FLAC decode

Status: **implemented experiment; actual extracted Windows decode passed**.
This implements the first bounded slice from the [completion plan](r19-completion-plan.md#immediate-next-implementation-slice).
It does not enable the production runtime, general game FFmpeg paths, vgmstream,
an installer or redistribution of the candidate. PR #59 stays unchanged.

The subsequent [artifact review](r19-codec-artifact-review.md) identifies the
original supplier and FFmpeg source pointer but **rejects this exact artifact for
production**: full source/notice delivery remains incomplete and later security
servicing is absent. Historical experimental receipts retain their pending/open
fields; they are not approvals. Select a maintained replacement before promotion.
The [replacement selection](r19-codec-replacement.md) now verifies a source-built
Xiph FLAC candidate and its independently rebuilt source kit. Frozen adapter
integration is still separate; the historical FFmpeg receipt below is unchanged.

## Exact artifact and remaining rights

The existing lock selects imageio-ffmpeg **0.6.0**. Its
[Windows x64 wheel metadata](https://pypi.org/pypi/imageio-ffmpeg/0.6.0/json)
identifies imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl, SHA-256
02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a.
The exact wheel contains ffmpeg-win-x86_64-v7.1.exe, **87,638,016 bytes**,
SHA-256 2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3.
Both were independently downloaded/hashed before pinning; no PATH binary was
selected. The build host supplies the exact wheel; runtime never installs the
Python wrapper, downloads a codec or chooses another version.

The archive's BSD notice belongs to the imageio wrapper. It is not treated as
the FFmpeg executable's license. Preparation retains that exact notice plus
the full GPLv3 text and FFmpeg license overview from upstream n7.1 commit
b08d7969c550a804a59511c7b83f2dd8cc0499b8, with independent file hashes in
packaging/codecs/ffmpeg-flac.json. Actual -version, -buildconf and -L
observations must agree with the selected GPL/version3 build; sanitized receipts
contain hashes and configuration flags, not raw compiler/process output.

[FFmpeg's upstream licensing reference](https://ffmpeg.org/legal.html) distinguishes
build configurations and matching source obligations. Matching binary build
recipes, incorporated-library/source-delivery closure and exact-output review
remain **open**. The old existing-lock binary is observed, not approved as a
maintained production supplier: servicing review is also **open**. None of these
gates is closed by successful decoding or by moving a binary into a subprocess.

Only the quarantined runtime-experiment may collect this subtree. Preparation
and collection bind the exact current policy/builder/resolver source hashes,
clean source commit, archive/executable/notice hashes and nested/outer inventories.
Output is a new directory; links/reparse points and unlisted files/directories
fail closed. The manifest retains production_execution_allowed=false, pending
redistribution, open source-delivery/servicing review, unavailable Windows 11
acceptance and r19_complete=false. Approval-like strings cannot promote it.

## Fixed runtime operation

media_tools.experimental_flac_decoder() resolves only
codecs/ffmpeg-flac/ffmpeg.exe through the frozen resource inventory. It accepts
only the experimental profile and revalidates exact bytes before execution.
The ordinary ffmpeg_executable() remains unavailable in bundle mode, retaining
the existing general game/audio gate. Source PATH/imageio behavior is unchanged.

The new operation is native FLAC to signed 16-bit little-endian mono PCM at
16,000 Hz, at most one second. Input is a regular file in an explicit private
work subdirectory, at most 1 MiB, with bounded STREAMINFO; output stays in the
same work directory. No caller-supplied FFmpeg switches, network protocol, shell,
report path or inherited IMAGEIO/FFREPORT/loader/account variables are accepted.
Fixed file protocol, format/map/output arguments, output-size cap and deadline
bound this initial operation. It proves no other FFmpeg input/codec/filter.

The adapter reuses PreparationJob and its Windows Job Object bootstrap so the
parent retains ownership until process-tree cleanup completes. The bootstrap
receives only OS essentials plus explicit frozen roots; developer/loader/account
environment is removed. A cancellation checkpoint guards final publication.
Decode output is staged privately and replaces the destination only after
successful exit, exact sample-byte count and cleanup. Failed, cancelled or timed
attempts retain the previous complete output and remove their attempt directory.

## Actual decode case and failure evidence

backend.codec_fixture authors a native FLAC STREAMINFO and one verbatim frame,
with standard CRC8/CRC16 and a patterned, non-silent **512-sample** mono signal.
No FFmpeg encoder, game, recording or fetched fixture creates the input. Expected
PCM bytes are independently constructed, **1,024 bytes**, SHA-256
e153774c8d06b094341ec9eb1e1f53571d3398a01cfd6526df97bc073f7ef379.
FLAC SHA-256 is
4e4d0d3eec7654126c8dfb64b54bddc3de62ae4181bcce206726df3e321792df.
This is an actual FLAC format case with a verbatim subframe, not evidence for
predictive FLAC variants, MP3/AAC/Bink/Wwise, game voices or full export.

The existing integrated Windows workflow prepares the codec from its locked
wheelhouse, freezes it and runs the real executable via the actual frozen
adapter after Unicode/spaces relocation, with an unrelated CWD and read-only app.
The native probe compares every PCM byte, tests pre-cancellation, an owned
deadline and a truncated frame, and requires previous-output retention and owned
cleanup. The outer full file/directory inventory must remain unchanged, including
Hidden/System entries. Actual child cleanup uses the existing process ownership
code; source mocks do not establish the native decode pass.

Cheap contracts separately cover missing/corrupt/unbound artifacts, missing
notices, extra files/directories, wrong PE/profile/source/policy, forged review
states, canonical private paths, output publication, cancellation after decode
and collector source/destination binding. These tests use authored PE bytes or
mocked process results and are never labelled actual codec execution.

No new browser matrix or codec workflow is added. The existing integrated-runtime
45-minute ceiling is unchanged; this slice adds a short fixed decode/failure set.
Only sanitized metadata and the hash inventory may be uploaded. Executables,
wheel caches, raw logs and authored PCM/FLAC contents stay on the build host.
Windows Server results remain distinct from clean Windows 11 25H2/native/CRT
acceptance, installed-game playback and the unresolved component rights.

## Local checks and retained limitations

The affected codec/runtime/helper contracts passed locally: **147 tests** across
the selected files, combining the 139 initial passes with the eight listener
cases that first failed under sandbox loopback restrictions and then passed in
the unchanged 13-case frontend group outside the sandbox. The first failure is
retained in ignored logs. These are source contracts, not a Windows decode pass.
Documentation/generated-guide/link checks, workflow YAML parsing and the public
source/history audit passed before the implementation push.

Changed-check record 236f67df-d48d-429f-884b-dfdd9776401f resolved actual
upstream/main at ba0b7c34c358f1664220674e5ff8bb7f30502e5f with an unchanged source
fingerprint. Typecheck and 271 Node tests passed (one skipped); Python collection
then failed because macOS lacks pyaudiowpatch. Later aggregate checks did not
run. This is an incomplete failed aggregate, not full-suite evidence.

The public compatibility watch returned 2 on 2026-10-29, with no added/removed
endpoints. The public settings, lookup-tab, effective-language and AI/API
reference was reinspected without accounts; the landing-page fetch timed out.
Live UI compatibility remains open and the watch baseline is unchanged.

## Extracted Windows observation (2026-10-29)

[Integrated run 40941114224](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40941114224)
passed on hosted Windows Server 2025 at clean source commit
93cd61c3f3d206533312172113646e4ebc21b954, build
runtime-experiment-40941114224-1. The 141 affected frozen contracts passed in
14.97 seconds. The workflow completed within its existing 45-minute ceiling.

The actual frozen adapter decoded the authored FLAC to every expected PCM byte:
512 samples, 1,024 bytes, SHA-256
e153774c8d06b094341ec9eb1e1f53571d3398a01cfd6526df97bc073f7ef379.
The selected executable hash matched the pin above. Actual diagnostic output
reported GPL and version3 enabled, nonfree disabled. Pre-cancellation, the owned
deadline and truncated input retained prior output; temporary/owned process
cleanup passed. Application inventories stayed unchanged after relocation and
read-only marking with developer discovery removed, including the Hidden/System
inventory regression.

Downloaded metadata artifact **12926768443** (101,956 bytes) matched GitHub's ZIP
SHA-256 d825605460906fec6ec005c5a1fbc3224471ab34e11159bdfdb55ebdd388bf2e.
Its exact source/build, native/ASR/frontend probe statuses, five codec subtree
entries, pinned artifact/executable/notices, PCM/input hashes, failure states and
pending gates were independently checked. The inventory contains **1,507 files,
636 directories, 710,010,894 bytes**; its raw JSON SHA-256 is
87ac48f962e5ba41f8e6cee19e6e438b04c94b28716d735831214fa397159d27.
No runtime executable was uploaded or independently downloaded in that artifact.

The existing [authored helper run 40941114153](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40941114153)
and all three [frontend/diagnostic/protected-TEST jobs 40941119384](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/40941119384)
also passed at the same source commit. These retain their existing authored-case
scope; no new actual game chain is accepted.

The [upstream required workflow 40941123800](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/40941123800)
still requires maintainer approval. Fork experiment success does not replace it.
Production execution, exact-output redistribution, matching source delivery,
servicing and clean Windows 11 25H2 acceptance remain open. General FFmpeg/game
dispatch remains blocked; R19 stays incomplete and PR #60 stays draft. PR #59
remains at 8369c9534762cd2232fb44424772bd6b5a72b6d2. No installer was built.
