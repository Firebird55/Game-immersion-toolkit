# R19 quarantined FFmpeg/Opus source replay

Status: **manual build-host experiment; native execution and rights gates remain open**.
This implements the first dependency replay proposed by the
[vgmstream r2168 source index](r19-vgmstream-source-index.md). The
[input policy](../packaging/codecs/ffmpeg-opus-replay.json) pins complete FFmpeg
9.0.2 and Opus 1.6.1 source archives, original upstream recipes/notices and
isolated MSYS2/make/NASM/pkgconf inputs.

The replay builds the four FFmpeg dependency DLLs used by the indexed Windows
recipe, with static Opus. It retains the original FFmpeg option file unchanged:
CLI programs and file/network protocols stay disabled. An authored, non-shipping
C harness supplies FLAC through memory-backed AVIO, compares independently
authored PCM, rejects truncation/CRC faults while preserving the prior complete
output, and tests static Opus encode → external libopus decode plus an actual
invalid-packet decoder error. Loaded FFmpeg DLL paths must resolve to the exact
quarantined candidate bytes.

This produces a distinct source-replay identity. It does not reproduce or
approve the existing upstream prebuilt DLLs, build the vgmstream CLI, provide
the general `ffmpeg_executable`, or integrate a decoder into the frozen runtime.
It establishes no broader game, language or full-export acceptance.

## Run the isolated experiment

The [manual workflow](../.github/workflows/r19-game-codec-replay.yml),
**R19 quarantined FFmpeg Opus source replay**, has no automatic push or PR
trigger. Once the workflow is available in the repository containing the
selected branch, choose Actions → that workflow → Run workflow and select the
reviewed branch. From that repository's checkout, the equivalent invocation is:

```sh
gh workflow run r19-game-codec-replay.yml --ref codex/r19-runtime-bundle
```

Record the actual run/head SHA before treating any result as evidence. The
workflow observes prerequisites and audits public source before acquiring
exact pinned inputs. It invokes
[build-game-codec-replay.ps1](../scripts/build-game-codec-replay.ps1), which
requires hosted image version 20261021.278.1, Visual Studio 18 2026, toolset
14.51.36231, compiler 19.51.36260.0, CMake 4.4.5 and SDK 10.0.26100.0. A changed
or unavailable host tuple fails; there is no substitute image or rolling
package installation. The declared NETFX 4.8 headers/libraries are bound when
present. Windows/.NET runtime implementation and independent compiler supplier
source/rights recovery remain explicitly unbound prerequisites.

The build uses a fresh isolated profile, disabled user/Directory.Build imports,
validated header/library search roots and before/after hashes of selected tools,
headers, libraries, targets and activation scripts. Original source bytes must
remain unchanged. The original VS2019 recipe and notices are retained alongside
the declared generator, prefix and build-isolation adaptations.

## Evidence and publication boundary

DLLs, the authored probe executable, static/import libraries, generated headers,
build configuration, authored audio and the private build log stay on the
ephemeral build host. The workflow uploads only:

- `REPLAY-RECEIPT.json`: sanitized source/tool/output hashes, actual configuration,
  native imports, candidate-relative DLL origins and bounded authored probes.
- `source-review.zip`: complete pinned source archives, unmodified original
  recipes/notices and project orchestration with its existing LICENSE and an
  explicit unapproved-source boundary. A passing receipt is written only after
  this archive has closed successfully.

The source review kit is not approved corresponding-source delivery or a durable
source service. Original upstream inputs retain their own terms. New project
orchestration remains under the existing project LICENSE; the scoped Xiph FLAC
grant does not apply and is unchanged. File-level notices, static Opus/CRT
incorporation, recipe-license compatibility, complete durable source delivery,
maintenance and actual required game-codec parity still require review.

A successful hosted run proves this dependency-subset experiment only. Runtime
collection, production execution, source-delivery approval and R19 completion
remain false. Windows 11 25H2 ordinary-user acceptance stays separate and
unavailable. PR #59 remains untouched; no installer or release is built.
