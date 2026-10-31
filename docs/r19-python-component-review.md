# R19 A2 Python supplier and native component review

Review date: **2026-10-30**. This is an exact-input gap review for A2 in the
[completion plan](r19-completion-plan.md), not redistribution approval or Windows
acceptance. The current [supplier pin](../packaging/runtime-bundle/python-supplier.json),
[runtime recorder](../packaging/runtime-bundle/record_runtime.py),
[notice recorder](../packaging/runtime-bundle/record_diagnostic.py),
[closure validator](../packaging/runtime-bundle/closure.py) and
[freezer specification](../packaging/runtime-bundle/runtime.spec) were inspected.
Their observed-experiment/pending gates remain appropriate. No installer is built.

## Supplier identity verified; notice closure still pending

The selected CPython 3.12.16 artifact is Astral python-build-standalone release
20261026, source fa506e0858ac9f2cc5b289c137b888a2aa24d1ee, Windows MSVC x64
install_only. The [supplier release API](https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/20261026)
was read again: release 424411241 is immutable; asset 678575209 is 47,113,364
bytes. Independently downloaded bytes match the pin and API digest:
590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5.
Nothing was installed or executed. CPython's [3.12.16 release](https://www.python.org/downloads/release/python-31216/)
is source-only; the supplier is therefore material to the binary decision.
The [Python lifecycle](https://devguide.python.org/versions/) supports the
security-maintenance decision through October 2028; it does not approve this
particular collected binary tree.

The selected install_only tar contains python/LICENSE.txt, 25,066 bytes,
SHA-256 886a0ead2d89030ee62dbff52b04e47ab91998341295bb9c56fb952b4e081c7a.
The base diagnostic recorder retains that file for CPython. It includes the historical
Python licenses, Windows Microsoft Distributable Code conditions, bzip2 and
Tcl-related terms. It does **not** contain the OpenSSL, expat, libffi, liblzma,
SQLite, zlib or mpdecimal notices needed to establish complete native closure.
Pip's vendored notices are present in the supplier installation but pip is
excluded from the frozen runtime; they do not fill those omissions.

The supplier's matching pgo-full asset 678575271 was separately downloaded and
its API digest verified:
37b4eb2818fee605fefa75ed156c4f2e1aaeaebaf662f9b30177c842ee16c48f.
It includes PYTHON.json and twenty files under python/licenses/, including
LICENSE.openssl-3.txt, LICENSE.expat.txt, LICENSE.libffi.txt,
LICENSE.liblzma.txt, LICENSE.sqlite.txt, LICENSE.mpdecimal.txt,
LICENSE.zlib.txt and LICENSE.zlib-ng.txt. These primary texts are now retained
as [twenty raw notice files with provenance](../packaging/runtime-bundle/python-notices/PROVENANCE.json),
126,019 bytes in total, without binaries or PYTHON.json. No new toolkit-owner
rights grant was needed to retain these upstream notices.
The [supplier archive contract](https://github.com/astral-sh/python-build-standalone/blob/fa506e0858ac9f2cc5b289c137b888a2aa24d1ee/docs/distributions.rst#install-only-archive)
explains that install_only omits PYTHON.json and files outside install/.
Consequently, byte verification of install_only alone is not notice closure.

The runtime recorder validates the provenance against the exact supplier pin,
then verifies each original archive member name, byte length and SHA-256 before
copying all twenty texts plus provenance into its CPython license evidence.
Both runtime profiles reject missing, changed or source-invalid notice delivery;
diagnostic profiles keep their historical behavior. Finalization delivers the
same hashed bytes under THIRD_PARTY/cpython/licenses/cpython/supplier/. This
closes their durable notice-delivery gap for future candidates, subject to an
actual frozen build. All twenty supplier texts are retained conservatively;
their presence does not assert that every named library is shipped. Native
applicability/ownership, Microsoft conditions and redistribution review remain
unverified/pending. No user-runtime download is added.

Use the exact [supplier source and build inputs](https://github.com/astral-sh/python-build-standalone/tree/fa506e0858ac9f2cc5b289c137b888a2aa24d1ee),
including pythonbuild/downloads.json and the Windows recipes, to reconcile
compiled-in and dynamic libraries. Downloads.json identifies CPython 3.12.16,
OpenSSL 3.5.9, expat 2.9.0, libffi 3.8.0, xz 5.8.4, mpdecimal 4.0.0,
bzip2 1.0.8, SQLite 3530100, zlib 1.3.2 and zlib-ng 2.2.4 source inputs.
Those are recipe declarations, not measured versions of every collected file.
PYTHON.json still names libcrypto-1_1-x64/libssl-1_1-x64 in link entries while
the selected installation contains libcrypto-3-x64/libssl-3-x64. Resolve that
discrepancy against real PE imports and supplier build inputs before approval;
do not copy the metadata into an asserted native inventory.

A subsequent download-free static review of the same verified install_only
archive resolves that specific import-name discrepancy for four supplier input
members. `python/DLLs/_hashlib.pyd` (54,784 bytes, SHA-256
71c71022b34ccb680bb51e77de3ce9cf2999e11abca7d969f0f8f7955d53c486)
imports `libcrypto-3-x64.dll`; `_ssl.pyd` (165,888 bytes, SHA-256
5322a75da94cc3839355451b574cd5a0e0ab5b8e7da01c9fa6ad1e1aedf2e429)
imports both `libcrypto-3-x64.dll` and `libssl-3-x64.dll`. The exact supplied
crypto DLL is 7,856,640 bytes, SHA-256
b1b422db706bae5429819cfbf77bb860fbb15843e4f812afc444d7345ded7dbf;
the SSL DLL is 1,571,840 bytes, SHA-256
c1a0ea16b3fe79b3ef9c6861533ddd8c5661f1b3244f67fcf1b53b2576ab809a,
and imports that same crypto basename. All four are native AMD64/PE32+ with no
delay imports. Only archive members were read; no DLL was loaded or executed.
The obsolete `1_1` link names in PYTHON.json therefore cannot describe these
four files' static imports. This does not establish their exact OpenSSL source
version, complete dynamic/provider behavior, final collected identity/load
origin or Microsoft/redistribution acceptance. Those reviews remain open.

## Exact-output findings and component dispositions

The available frozen report at source
33daa6db4e3d66e08f7b6702b67f6ad49c711dd3 is **historical**, not evidence for
the next candidate. Its raw inventory digest is
7e5b9629e0e44a909b32f77fb5eac22127945e6aff7925f30f0b1549efffa6ec.
It records 57 components, 1,514 files and 562 EXE/DLL/PYD files. The downloaded
report contains file identities, not all original notice text or binary bytes.
These findings therefore identify concrete review inputs, not an audit of an
unavailable final candidate's actual code. All recorded component rights remain
pending-exact-output.

That output also lists ucrtbase.dll and api-ms-win-* DLLs in both main and ASR
trees, while those files are absent from the selected Python install_only tar.
Their supplying build-host/package path, allowed redistribution terms and exact
bytes need independent attribution; describing them as Windows prerequisites
does not explain copied files. Its _internal/FLAC.dll is byte-identical to
_internal/codecs/xiph-flac/FLAC.dll: 247,808 bytes, SHA-256
29c4c88bc8cb17e30aaef2d9af50455abeeccc59bda18d1189dfb7568d9e27d8.
The spec supplies codec PE files as Analysis data; PyInstaller 6.22.3
[reclassifies them as binaries](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/PyInstaller/building/build_main.py#L745),
then [collects dependencies outside package paths at the root](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/PyInstaller/depend/bindepend.py#L100).
The codec's PE report confirms flac.exe imports FLAC.dll. This explains the
duplicate without identifying a second codec family; the original build TOC
source paths were not retained, so that collection path remains an inference.
The freezer now keeps only the two verified standalone codec PE files outside
main Analysis dependency scanning and appends them afterward as explicit DATA.
Finalization revalidates the existing codec source/notice/PE inputs, then rejects
every extra flac.exe/FLAC.dll basename outside the exact isolated subtree,
including byte-identical copies. It also checks both canonical output hashes
and lengths before writing candidate metadata; no failed file is deleted.
The codec's runtime module-origin check is unchanged. Disk/configuration tests
cover this boundary; the new complete frozen output still needs hosted Windows
validation. An inventory generated after collection alone cannot establish scope.

The exact ONNX Runtime 1.24.4 cp312 Windows x64 wheel has SHA-256
535b29475ca42b593c45fbb2152fbf1cdf3f287315bf650e6a724a0a1d065cdb.
Its onnxruntime/ThirdPartyNotices.txt is 331,175 bytes, SHA-256
fb0af774b4d7cffc5b9d046f2aaeade2f37df2f80abf8033c95dfffcc77a8866.
Historical output already delivered those exact bytes under
_internal/onnxruntime/ThirdPartyNotices.txt as package data, but only LICENSE
was bound in the component notice records and central THIRD_PARTY directory.
The runtime recorder now binds that original wheel member to the matching
installed/version/file record and delivers its byte-exact central copy. The
upstream tag's text uses LF rather than the wheel's CRLF; substituting it would
change the selected payload hash. This closes central notice attribution and
delivery, subject to the next actual frozen output. It does not identify the
separate ONNX library embedded in sherpa-onnx-core or approve either native tree.

The exact [windows-capture 2.0.1 wheel](https://pypi.org/pypi/windows-capture/2.0.1/json)
has SHA-256 209c2318e2168802b9afd1005e99499639e8835e71a1e188a3ddc77c7ccc3f04.
It contains a full wrapper MIT notice at
windows_capture-2.0.1.dist-info/licenses/LICENCE: 1,091 bytes, SHA-256
e11eff681f6f0eb76dbea5787b100d646e4eb5d711e50cb5c9032595f6ca6a68.
The generic recorder now recognizes the British LICENCE spelling and delivers
the original installed/wheel-bound text centrally instead of falling back to
METADATA. Its delivery regression preserves original CRLF bytes and excludes a
raw SBOM fixture. The real supplier SBOM includes upstream absolute build paths
and all-target dependencies; it remains private review material. This notice
step does not approve Rust/native dependencies, compiler/SDK/runtime terms or
Windows capture, and its exact frozen delivery still requires a hosted build.

Flatbuffers 25.12.19's ten Python wheel members were byte-compared with fixed
upstream commit 7e163021e59cca4f8e1e35a7c828b5c6b7915953; all match. Its full
[Apache-2.0 LICENSE](https://github.com/google/flatbuffers/blob/7e163021e59cca4f8e1e35a7c828b5c6b7915953/LICENSE)
is now retained with [source/wheel provenance](../packaging/runtime-bundle/flatbuffers-notices/PROVENANCE.json):
11,358 bytes, SHA-256 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30.
The inspected upstream archive has no supplementary NOTICE file. The recorder
binds all ten source identities to the exact wheel and observed installed bytes,
then delivers LICENSE and provenance centrally. Runtime preflight rejects
omitted, stale or changed notice records. This source-notice step retains the
pending component/native gates. The exact frozen output at `12d0d0e` now
confirms the central LICENSE and Windows-checkout provenance bytes in the
[download review](r19-frozen-checkpoint-20261031.json); the
pure Python wheel does not identify FlatBuffers embedded in other native code.

The sherpa rights question also affects the Python binding actually imported by
the ASR worker. The exact cp312 wheel has SHA-256
566e49ad3fb2aa8ceb723a52f9809aa6c2ee0a5eb3b0946c3fd2374af807a5c6;
its _sherpa_onnx.cp312-win_amd64.pyd has SHA-256
c7cbe8071492dde37f7c9d640fd882ff52f62073c5214741c74178502aa6c593.
Static PE inspection finds espeak_Initialize implemented in .text at RVA
3743504, without export forwarding. The binding imports ONNX/Python, while
[matching pybind CMake](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/python/csrc/CMakeLists.txt)
links it directly to static core; removing unused C/C++ API DLLs cannot remove
that eSpeak implementation. TTS OFF preserves unconditional ASR/SenseVoice
sources, but the [disabled-feature placeholders](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/python/csrc/sherpa-onnx.cc)
omit GenerationConfig and OfflineTtsSupertonicModelConfig although the package
imports them. An ASR-only rebuild is plausible with a recorded compatibility
fix and new build/native/inference evidence. No such replacement was built or
executed here, and the incorporated eSpeak/source/rights gate remains open.

| Component/output | Observed evidence | Remaining disposition input |
| --- | --- | --- |
| CPython 3.12.16 and both interpreter trees | The acc68be/12d0d0e frozen inventories confirm twenty retained supplier texts plus provenance alongside LICENSE.txt. Main/ASR trees contain Python, OpenSSL, libffi and other extensions. | Map every shipped and compiled-in native dependency to source/version/build recipe/terms, including duplicate ASR files. Reconcile Microsoft runtime ownership and conditions. |
| sherpa-onnx and sherpa-onnx-core 1.13.8 | Wrapper has an upstream license; core notice is METADATA only. Exact core wheel SHA-256 5579e80196d516e6dae23c8f629292ce3142ab8869925d32b94612fd86f93733 was downloaded and checked: it contains onnxruntime.dll and two sherpa API DLLs, with no LICENSE/NOTICE file. | Add versioned sherpa/ONNX Runtime incorporated notices and establish the core wheel's actual native build inputs/options. The wrapper's Apache-2.0 label does not cover the DLL closure or optional ASR model. |
| ONNX Runtime 1.24.4 in main | Historical package data includes exact ThirdPartyNotices, while central notice evidence has LICENSE only; acc68be/12d0d0e confirm the original wheel's exact ThirdPartyNotices in central delivery. Main and ASR have distinct ONNX libraries. | Establish upstream source/build identity and inspect provider DLLs, compiler/CRT requirements and actual origins for each process. Do not substitute main's version for ASR's bundled runtime. |
| NumPy 1.26.4 and SciPy 1.14.1 | Four/five notice records; OpenBLAS DLLs are collected, including ASR's NumPy tree. | Inspect the actual notice text and map OpenBLAS/LAPACK/compiler runtime and incorporated routines to the exact collected files and corresponding sources. Notice count alone is not a completeness decision. |
| OpenCV Python 4.11.0.86 and Pillow 13.0.0 | OpenCV has LICENSE and LICENSE-3RD-PARTY copies; Pillow has one license record. | Review selected native image/video codec features and actual incorporated notices/source obligations, including FFmpeg if present. Excluding imageio-ffmpeg or Haar data does not establish OpenCV's native closure. |
| windows-capture 2.0.1 | Historical notice records fell back to METADATA because the collector missed LICENCE; acc68be/12d0d0e confirm the existing exact wheel's wrapper notice in central delivery. | Complete Rust/native/compiler/runtime attribution and capture acceptance separately. Raw supplier SBOM publication remains closed. |
| flatbuffers 25.12.19 | Historical notice evidence falls back to METADATA; new collection requires the exact retained source LICENSE/provenance and ten source-identical wheel/installed member records. | The 12d0d0e checkpoint confirms the central source LICENSE/provenance bytes; retain source attribution. Native libraries incorporating FlatBuffers need their own version/source/native review. |
| oneocr 1.0.12 | Historical notice records are METADATA fallbacks. | Retain authoritative versioned copyright/license evidence. Its wrapper license cannot grant rights to proprietary Snipping Tool DLLs/models; those remain user-local prerequisites. |
| kaldi-native-fbank, PyAudioWPatch, webrtcvad-wheels, PyCryptodome, RapidFuzz, pydantic_core, httptools, watchfiles, websockets, PyYAML, protobuf and other collected wheels | Exact distribution/version/wheel hashes and installed file checks exist; native imports remain observed/unverified. | Use the selected wheel's own complete notices and source/native-build records. Reconcile PortAudio/PyAudio, WebRTC and compiled Rust/C/C++ dependencies rather than inheriting one wrapper license. |
| certifi, OpenCC, pypinyin and FireRedVAD resources | Wheel notices and owned FireRedVAD provenance/resources are recorded. | Review the exact CA/dictionary/model data terms and final bytes independently of implementation licenses. Optional agent model/tokens require their own manifest; no private model may become seed data. |
| Freezer/build-only packages | Recorder includes the locked build environment as well as runtime packages; runtime.spec excludes pip/setuptools/pytest and selected other packages. | Distinguish actual emitted code from build-only packages, retain exact PyInstaller bootloader exception and embedded native notices, and verify exclusions in the final output. All 49 lock entries need a disposition, not necessarily inclusion. |

Primary starting points for the native wheel rows are the
[versioned sherpa license](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/LICENSE),
[exact core wheel metadata/files](https://pypi.org/pypi/sherpa-onnx-core/1.13.8/json),
[versioned ONNX Runtime notices](https://github.com/microsoft/onnxruntime/blob/v1.24.4/ThirdPartyNotices.txt)
and the selected wheel/source links in the
[R18 component review](r18-runtime-components.md#core-runtime-and-python-dependencies).
These sources establish review material, not that their complete contents were
collected into the candidate.

## Concrete A2 completion inputs

For one clean candidate, retain its actual input records and wheel filenames/
hashes, original notice paths/text/hashes, source revisions or source archives,
build recipes/options, and a file-to-component ownership map covering every
collected EXE/DLL/PYD plus compiled-in dependencies. The additive
native_input_ownership report now joins each native output hash to verified
component artifact/hash/relative-input records and resource path/version/public
source records. It preserves every exact match and distinguishes ambiguous,
unmatched and expected generated executable paths. It does not guess by file
name or assign transformed/unmatched binaries to a supplier. Original file
entries keep exactly path, SHA-256 and bytes; existing inventory readers retain
their schema. Raw host paths, object representations and unused diagnostic
fields are excluded; invalid private path spellings reject the report.

The separate [native collection observation](r19-native-collection-provenance.md)
now consumes actual Analysis TOCs and verifies source-to-final-output byte
bindings without changing this inventory or ownership report. Its authored
contracts are implemented; actual frozen Windows execution remains pending.
Unknown host sources and unexplained transformations block the new observation.
Its build-host JSON is not part of the runtime or artifact upload allowlist.

An exact byte match identifies a supplying input, not its incorporated code's
copyright owners, licenses or runtime load origin. Generated executable contents
and transformed binaries still need a sanitized build-input/TOC provenance
chain. Original notice names/text, complete dependency/source mapping and actual
native behavior remain necessary for exact-output review; METADATA fallback
explicitly remains incomplete evidence. The report grants no production or
rights approval and preserves the pending native/component gates.
Required corresponding-source delivery must follow each applicable license;
permissive packages need notice compliance and traceable sources, without an
invented universal requirement to redistribute all source code.

Reconcile the native/source/notice mapping, Microsoft redistribution conditions,
actual OpenCV/ASR codec closure and optional model status before recording an
explicit component-by-component decision. This public-source work can proceed
without a Windows 11 host or additional toolkit ownership permission. DLL load
origin/compatibility and clean ordinary-user execution still require Windows
evidence. The user has confirmed no Windows 11 25H2 x64 test environment is
available; the [native acceptance gate](r19-native-acceptance.md) stays unavailable.
Neither this research nor hosted Windows Server tests close that external gate.
