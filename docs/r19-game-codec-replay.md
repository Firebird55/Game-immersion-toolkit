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
trigger. Before a new manual workflow has been registered, use the existing
R19 runtime workflow's explicit source-only selector. It calls this reusable
workflow at the same reviewed commit and skips all frozen/FLAC/observer jobs:

```sh
gh workflow run r19-runtime-experiment.yml --ref codex/r19-runtime-bundle -f source_replay=ffmpeg-opus
```

Select the review repository explicitly when the checkout has multiple remotes.
GitHub's [manual dispatch registration rules](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
apply; no default-branch or repository setting is changed for this experiment.
Once registered, the dedicated workflow can also be dispatched directly.
Record the actual run/head SHA before treating any result as evidence. The
workflow observes prerequisites and audits public source before acquiring
exact pinned inputs. It invokes
[build-game-codec-replay.ps1](../scripts/build-game-codec-replay.ps1), which
requires one of the two explicitly reviewed hosted image versions
20261021.278.1 or 20261030.294.1, Visual Studio 18 2026, toolset
14.51.36231, compiler 19.51.36260.0, CMake 4.4.5 and SDK 10.0.26100.0. A changed
or unavailable host tuple fails; there is no wildcard, automatic new-image
acceptance or rolling package installation. These two versions were observed
in simultaneous jobs during GitHub's rollout: FFmpeg run 41163848164 received
the new image and ASR run 41163849991 still received the old one. The
[new image's pinned software catalog](https://github.com/actions/runner-images/blob/0dfe95c53f998c186f26977422790b191450df29/images/windows/Windows2025-VS2026-Readme.md)
and release manifest are identified in the input policy. They admit the host
to preflight; they do not prove compiler bytes. All concrete compiler, toolset,
SDK and CMake checks and complete per-run tool seals remain unchanged. Each
result retains its actual image version. CMake comes only from the
[shared pinned ZIP helper](pinned-build-cmake.md), prepared at the caller's
fixed isolated tool root and verified before native execution and after the
build. The workflow passes the absolute python.exe selected by setup-python
3.12.10. Installed ProgramFiles/Strawberry/PATH matches are not candidates.
Optional Git discovery is disabled:
the original Opus cmake/OpusPackageVersion.cmake selects its unchanged
package_version file when Git is unavailable. The declared NETFX 4.8.1
headers/libraries are bound when
present. Windows/.NET runtime implementation and independent compiler supplier
source/rights recovery remain explicitly unbound prerequisites.

The exact NETFX selection follows the verified
[native preflight at `a57cc6c`](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41167086271):
three early Windows contracts passed without skips, then the original 4.8 policy
refused the actual 4.8.1 `Include/um` and `Lib/um/x64` entries. Failure artifact
13029314482 matched 833 bytes / SHA-256
7253217c0f12a619ecca190196a264246fb28cc08fc294984f92cb9cc74e7731,
the exact source/manifest and the fixed numeric/suffix projection. The other
twelve entries, including the observed VC Auxiliary header, were accepted.
The policy now selects only that evidenced 4.8.1 input and retains before/after
tree sealing; it does not admit an arbitrary sibling SDK or establish native
codec build/decode, runtime requirements or redistribution rights.

The build uses a fresh isolated profile, disabled user/Directory.Build imports,
validated header/library search roots and before/after hashes of selected tools,
headers, libraries, targets and activation scripts. Original source bytes must
remain unchanged. The original VS2019 recipe and notices are retained alongside
the declared generator, prefix and build-isolation adaptations.

Compiler activation uses one generated `activation.cmd` under the fresh private
profile. It calls the exact selected vcvars batch with numeric SDK/toolset
arguments and exits on any nonzero result before reading the environment.
Only the existing compiler/SDK variable allowlist is imported. Generated batch,
activation logs and raw environment output remain private and outside the
source-review ZIP; authored Windows contracts cover paths with spaces and
failed activation without partial or foreign variable export.
The authored batch checks both the exact raw `%*` invocation and the separate
`%3`/`%4` parameters produced by the unquoted `=` in the
[documented vcvars switch](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line).
The previous fixture incorrectly expected the whole switch in `%3`;
[Microsoft's archived batch-parameter example](https://jeffpar.github.io/kbarchive/kb/071/Q71247/)
describes this delimiter behavior. The corrected contract still requires the
exact SDK/toolset arguments and a failed activation without partial export.
Contract failures expose only fixed phase labels and an optional numeric exit.

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

The helper and shared CMake policy are included as project recipe inputs; the
complete original CMake ZIP and its native tree stay in the separate isolated
build-tool container. The replay receipt binds the verified CMake supplier
summary, and source-review.zip contains no CMake executable or tool archive.

On a failed build command, `FAILED-STAGE.json` is a separate failed receipt.
It preserves the fixed command phase and numeric exit code, with only selected
compiler/linker/MSBuild/command-line error codes and fixed categories from that
command's private log tail, bounded to 2 MiB. The MSVC allowlist includes the
[documented D command-line errors](https://learn.microsoft.com/en-us/cpp/error-messages/tool-errors/command-line-errors-d8000-through-d9999)
and [C1001](https://learn.microsoft.com/en-us/cpp/error-messages/compiler-errors-1/fatal-error-c1001).
An observed C/LNK/MSB/D error code outside that allowlist produces only a fixed
unclassified family category; its numeric token is never published.
When the byte bound truncates the command log, classification discards the first
fragment through its next LF before decoding or matching. With no LF the retained
classification input is empty. This conservative rule prevents an original line
or word prefix from disappearing at the cut and creating a false diagnostic;
it reads no bytes before the command offset and keeps `log_truncated` true.

Other fixed categories recognize fatal GNU make recipe/no-rule diagnostics,
shell command-not-found/cannot-execute/permission diagnostics, the
[NASM 3.02 GNU and Visual C diagnostic formats](https://www.nasm.us/doc/nasm02.html#section-2.1.15),
and three original FFmpeg 9.0.2 `compat/windows/makedef` failure messages.
Make warnings and ignored recipe failures are excluded from its fatal categories;
NASM warnings are excluded from its error categories. The makedef categories
apply only to the FFmpeg build/install phases. These are observations of known
formats in an untrusted private log, not proof of diagnostic authorship or root
cause. In particular, [GNU make exit code 2](https://www.gnu.org/software/make/manual/html_node/Running.html)
identifies an error without identifying the failed child tool. The
[shell's 126/127 conventions](https://www.gnu.org/s/bash/manual/html_node/Exit-Status.html)
are not inferred from that enclosing make exit code. Earlier commands, error
text, matched targets, paths, arguments, source/model strings and raw logs are
not published. Unknown diagnostics remain a fixed unclassified category. This
receipt cannot establish a passing replay or change any gate.

A version-gate mismatch uses a separate preflight-failure schema at the same
failed-receipt filename. It binds the source commit and input-manifest hash to
strictly numeric expected CMake/compiler versions, observed CMake version,
CL FileVersion/ProductVersion resource numbers and each executable's byte count
and SHA-256. Resource versions are observations, not inferred compiler identity.
The current gate still compares CMake and the CL file-resource version with the
unchanged pins. Native version output is bounded and omitted. Only a mismatch
creates its fresh failure directory; matching preflight leaves the source
preparation's fresh-output requirement intact.

After successful compiler activation, a rejected `INCLUDE` or `LIB` search path
uses a separate toolchain-preflight failure schema at `FAILED-STAGE.json`.
It binds the source commit and manifest bytes/SHA-256 to at most 64 entries per
search variable: fixed component roles, directory-existence flags and fixed
rejection reasons. Missing values, oversized values, too many entries and
inspection errors fail closed. Broader NETFX/SDK/MSVC component roles classify a
rejected path; they do not admit a new compiler input root. Schema v2 also records
a NETFX SDK version only for a strictly numeric direct child of the declared
NETFXSDK parent with an exact `Include/um` or `Lib/um/x64` suffix. The public
fields contain that numeric version and a fixed include/lib role; other paths
retain null fields and remain rejected. No NETFX version is inferred or newly
admitted. Numeric versions, relative suffixes and source commits use
[absolute .NET regex anchors](https://learn.microsoft.com/en-us/dotnet/standard/base-types/anchors-in-regular-expressions)
so a trailing newline cannot pass the fixed projection. Paths, path hashes,
environment contents, arbitrary object fields and
exception text are omitted.
Passing search checks leave source preparation's destination absent; only a
failure creates the fresh receipt directory. All build/runtime/rights gates stay
false in this diagnostic receipt.

[Run 41161558418](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41161558418)
executed both early authored Windows contracts successfully with zero skips.
Its verified failure receipt identifies the exact `VC/Auxiliary/VS/include`
header root and two other NETFX SDK search entries. The auxiliary header root is
now explicitly declared and was already inside the complete `VC/Auxiliary` tree
sealed before configure/compilation and again after probe compilation. An
authored header regression verifies that both seals include its bytes and detect
a change. The NETFX entries remain blocked pending their exact numeric/suffix
observation; this run built or executed no codec. Existing compiler/CMake/SDK
pins and runtime, rights, source-delivery and Windows 11 gates are unchanged.

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
