# Separate TTS-disabled ASR source experiment

This manual experiment is an unapproved alternative identity,
`sherpa-onnx-1.13.8-asr-reference.1`. It does not replace the stock sherpa
artifacts, application requirements, frozen runtime profiles or Migaku. No
installer, pretrained ASR-model download or production permission is added.

The existing Python binding contains an implemented eSpeak export; removing
unused C API DLLs cannot remove that binding's code. The upstream
[top-level build](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/CMakeLists.txt)
and [Python binding registration](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/python/csrc/sherpa-onnx.cc)
provide a TTS-OFF path. The recorded patch supplies its two missing `None`
placeholders, `GenerationConfig` and `OfflineTtsSupertonicModelConfig`, which
the unchanged Python initializer imports. Both upstream base and result are
hashed; the original Apache notice and patch remain with the private candidate.
[The public patch notice](../packaging/asr/SHERPA-PATCH-NOTICE.txt) retains Xiaomi's
copyright, the exact upstream source URL and a dated description of the two
additions. The complete original [Apache license](../packaging/asr/SHERPA-LICENSE.txt)
is retained byte for byte. Both are pinned in the manifest and copied into the
private source recipes and wheel notices. This preserves authoritative notices;
it does not grant new rights or alter the project's license.

## Exact inputs and dependency graph

[The experiment manifest](../packaging/asr/sherpa-reference.json) fixes upstream
commit `11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf`, all archive byte counts and
SHA-256 values, selected extraction scope, individual notice bytes, build flags
and the patch. The eleven source archives are sherpa-onnx, pybind11,
kaldi-native-fbank, kaldi-decoder, kaldifst, OpenFST, KISS FFT, Eigen, JSON,
simple-sentencepiece and hclust-cpp. Notices are retained individually; preserving
a license file does not classify every optional source as linked or approve
the combined output. The Eigen/JSON source archives also retain optional
material with other notices; output-specific review remains necessary.
The original simple-sentencepiece archive contains unused upstream tokenizer
test `.model` files. Its selected build prefixes omit those Python/test assets;
they are never loaded, placed in the candidate or presented as owned fixtures.
The retained original archive is private. The no-pretrained-weights boundary
concerns ASR weights; it does not pretend that every upstream source archive
contains only text or is free of upstream test fixtures.

ONNX Runtime 1.28.2 MT Release is a **separate prebuilt native dependency** from
the [supplier release](https://github.com/csukuangfj/onnxruntime-libs/releases/tag/v1.28.2),
with the exact hash selected by the
[upstream Windows recipe](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/cmake/onnxruntime-win-x64.cmake).
Its DLL, headers, import library, LICENSE and ThirdPartyNotices are bound to the
archive. Rebuilding sherpa does not rebuild this DLL or establish its complete
source/compiler/CRT correspondence. That review stays pending.

The existing CPython 3.12.16 supplier archive supplies the separate build/probe
interpreter, headers and Python import library. Its existing supplier and notice
review limits apply. Every actual interpreter-root file must match the exact
supplier archive before sealing/building. The exact Windows NumPy 1.26.4 wheel is extracted into a
separate probe-dependency directory; no ambient installed sherpa or NumPy can
satisfy the native probe. NumPy is not silently bundled into the variant wheel.

Preparation downloads nothing. It validates every original archive hash before
writing, rejects selected traversal/links/Windows path aliases/nonregular or
oversized entries, checks each notice and applies only the fixed patch. Unused
platform links in the main archive cannot enter its explicit selected source
prefixes. Original archives and full inventories stay in private build output.
Subsequent source checks recheck source, original archives, notices and copied
recipes. The raw archive pin retains the omitted platform material's identity.

Every selected `FETCHCONTENT_SOURCE_DIR_*` is explicit, including the upstream
hyphenated `simple-sentencepiece` name. CMake's disconnected mode is mandatory;
the expanded configure trace must show exactly the declared/populated dependency
set and no `file(DOWNLOAD)` or downloader invocation. Module precedence selects
the root's Eigen 5.0.1/OpenFST recipe over nested alternative recipes. No
PortAudio/WebSocket/test/demo/CAPI/TTS fetch may enter the experiment. The trace
check is a source-graph observation, not an operating-system network sandbox.

## Build and probe boundary

Use the manual **R19 separate ASR-only source experiment** workflow on a clean
candidate commit. It observes the actual PR target's development prerequisites,
audits public source, downloads only pinned public inputs, and invokes
[the Windows wrapper](../scripts/build-reference-asr.ps1). There is no push trigger.
Before this new workflow is registered, dispatch the existing R19 entry workflow
with `source_replay=sherpa-asr` on the reviewed branch. It calls the reusable ASR
workflow at that same commit and skips the frozen/FLAC/observer jobs:

```sh
gh workflow run r19-runtime-experiment.yml --ref codex/r19-runtime-bundle -f source_replay=sherpa-asr
```

Select the review repository explicitly for a checkout with multiple remotes.
No default branch or repository setting is changed. The registered dedicated
workflow remains directly dispatchable; no successful source-only run can stand
in for a skipped frozen-runtime job.

The constraints select hosted VS18 2026, MSVC 19.51.36260.0/toolset
14.51.36231, isolated CMake 4.4.5 and Windows SDK 10.0.26100.0. Version strings are not
immutable supplier identities. Exact VC/MSBuild/selected SDK/CMake/Python file
inventories are hashed before configuration and compared after the build/probes;
only counts and digests leave the host. OS services and the supplier/toolchain
rights decision remain external to this byte-stability check. It does not
assert approval of a mutable hosted image.
The workflow uses the shared [pinned CMake helper](../scripts/pinned-build-cmake.py)
and [official ZIP policy](../packaging/build-tools/cmake-4.4.5-windows-x64.json).
After doctor/audit it acquires the exact original ZIP and publisher checksum list,
prepares a fresh private build-host container, and verifies the complete tool
tree. The wrapper requires that container explicitly through `CMakeRoot` and
passes its verified payload to Python. Before any CMake execution and after the
build/probes, Python uses the same shared verifier against the original retained
ZIP, complete file/directory inventory and notices. The observed version must
still equal 4.4.5, and the payload remains in the complete before/after tool seals.
Each declared tool root must resolve to one existing filesystem directory and
enter Python as a single string; arrays, missing roots and additional root
labels are rejected before sealing. The source manifest and `SOURCE_FILES` bind
the shared policy/helper. Source recipes retain those files; the CMake ZIP,
tool executables and complete tool tree remain runner-local and never enter
the ASR source recipes, private variant wheel, runtime or uploaded artifacts.
The successful ASR receipt retains the verified tool's safe summary only; this
grants no runtime collection or additional supplier/source approval.
Failed toolchain validation distinguishes fixed root-schema/filesystem,
interpreter-origin, supplier-byte and CMake-version subphases. A failed receipt
may include only bounded numeric expected/observed CMake versions and the
executable's byte count/SHA-256; raw version lines, paths, arguments and exception
text remain private. An observed mismatch does not relax the 4.4.5 constraint.
VC-target selection, parent-import review and configure-argument/source
validation have distinct fixed subphases. The hosted
[review run](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41160408338)
observed all three installed families, `v160`, `v170` and `v180`, before configuration.
The manifest selects only `v180` and pins its actual `Microsoft.Cpp.Default.props`
at 25,028 bytes / SHA-256
`a2676be54dd09fc6b05903be07e28a3ae83c182de3d9ae91214db1ce029dd4ef`.
CMake 4.4.5's
[generator factory](https://github.com/Kitware/CMake/blob/aa4fae824a02a175c4a11653d7a851a948f0c004/Source/cmGlobalVisualStudioVersionedGenerator.cxx)
binds the requested generator to VS18, its
[MSBuild invocation](https://github.com/Kitware/CMake/blob/aa4fae824a02a175c4a11653d7a851a948f0c004/Source/cmGlobalVisualStudio10Generator.cxx)
uses `VisualStudioVersion=18.0`, and Microsoft's
[build-tool example](https://github.com/microsoft/cpp-language-server/blob/933ac0f10446009d972421329918b1d73bc2e0ff/AUTHORING_EXTRACTOR_SKILL.md)
documents the VS18 `v180` target family. The props pin's provenance identifies
the exact observed run, job, source commit and checksum-verified failure artifact.
Only one canonically spelled selected props file with those exact bytes is
accepted. Missing, changed or aliased selected inputs are refused; a later or
older installed family cannot become a fallback. Every installed family remains
in the complete MSBuild before/after seal and bounded diagnostics.
Before refusal, diagnostics collect every candidate's bounded numeric `v...`
label and props byte count/SHA-256, selected-family count/pin-match state, and
fixed parent-import categories. Unrecognized labels and raw paths/props contents
cannot enter the receipt. Registry fallback and parent imports remain refused.
The review run did not reach configuration, compilation or inference; the new
selection still requires a fresh native build/probe result.
The complete VS/MSBuild and VC/Auxiliary trees and any present named NETFX4.8
headers/import libraries are included. The OS/.NET execution prerequisites
remain named, unbound native inputs. A fresh empty profile, explicit sealed VC
targets, disabled Directory.Build/user wildcard imports and disabled node reuse
prevent ambient MSBuild user configuration. Parent response/import files are
rejected; the source files are preserved. Each build/probe runs in the existing
join-before-spawn Win32 Job Object and drains only its owned descendants,
including after a timeout. Cleanup failure prevents a passing receipt.

The build uses explicit Release/x64/static-CRT flags consistent with the selected
ONNX MT input. No Microsoft redistributable is copied from a developer machine.
Package registries, installed ONNX detection, ambient Git metadata, compiler flags
and Python user sites cannot choose source inputs. Generated compilation units
must remain in the prepared/build root. Actual native project/source inputs,
the binding link map, named exports and normal/delay imports are checked for the
expected Python/ONNX/system scope and absence of eSpeak/Piper/phonemizer inputs.
One shared native-name predicate recognizes vendor/API boundaries in actual
`espeak_`/`espeak_ng_` functions, `espeak-ng`/`piper-phonemize` libraries/paths,
and native phonemizer identifiers, including MSVC-decorated forms. Retained
`OfflineSpeakerDiarization`/`PybindOfflineSpeakerDiarization` names contain an
incidental e+Speaker substring and must not count as eSpeak implementation.
This keeps diarization enabled; fixed TTS-OFF/configuration, exact source graph
and structural TTS compilation checks remain independent requirements.
Dynamic runtime loading in unexercised features is still an exact-output review
question; a marker search alone is not a broad native-closure approval.

The private wheel uses distribution name `proxy-r19-sherpa-asr-reference`, version
`1.13.8+proxy.r19.asr1`; the ordinary `sherpa_onnx` Python API is retained inside
that isolated candidate. No stock core wheel or package from site-packages is
used. Source Python files, the explicit version suffix, patched binding, exact
ONNX DLL and notices have recorded identities.
Upstream `version.cc` embeds an older Git identifier (`8c8e275d`); it is retained
as upstream metadata and explicitly cannot prove the selected source revision.
Archive/patch/source-inventory hashes provide that binding. The probe also checks
the actual ONNX API's reported version against 1.28.2.

[The owned fixture](../scripts/probe-reference-asr.py) writes a small original
ONNX protobuf graph, original six-token vocabulary and half a second of silence.
Its four inputs and metadata follow the fixed
[SenseVoice adapter](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/csrc/offline-sense-voice-model.cc)
and [decoder](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/csrc/offline-recognizer-sense-voice-impl.h).
The wire fields follow the public [ONNX schema](https://github.com/onnx/onnx/blob/v1.16.0/onnx/onnx.proto).
Its dynamic logits deliberately emit `AUTHORED` regardless of sound. Separate,
bounded native child processes must exercise `from_sense_voice`, `create_stream`,
`accept_waveform`, `decode_stream` and `result.text`, reject an invalid ONNX file,
and observe the native adapter's empty result after an incompatible input shape.
They verify the imported binding and loaded ONNX DLL's exact candidate origin.
These are native format/API checks, **not speech recognition or model accuracy**.

Success uploads only `PREPARED.json` and `ASR-RECEIPT.json`. Failure may separately
upload `ASR-FAILURE.json`, containing fixed phase/category and allowlisted tool
codes, with failed status and all acceptance gates still closed. Exception,
log, command, model and path text is excluded. No native
payload, wheel, input archive, model/audio fixture, raw log/trace/link map, private
file inventory or absolute build/tool path is uploaded. An incomplete native
build/probe produces no passing final receipt.

## Open decisions

All production execution and runtime collection permissions remain false;
redistribution and ONNX/toolchain/CRT source correspondence stay pending. Source
and notice retention do not approve native ownership, static-CRT redistribution,
the existing Python supplier's mappings or the complete combined artifact.
The project license is unchanged, and the separate Xiph build-recipe grant is
not extended to this experiment.

No pretrained ASR model weights or model terms are used or accepted. The official
[SenseVoice model card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)
declares separate model terms; a later exact weight/token selection and intended
use need their own review. An authored graph cannot close that gate.

Local preparation and regression tests do not establish a successful Windows
build. A successful hosted Server run would establish only its bounded source
build and native format/API observations. Clean ordinary-user Windows11 x64
25H2, capture/DPI, trained recognition quality, full R19 and merge readiness
remain separate gates. No such Windows11 environment is currently available.
