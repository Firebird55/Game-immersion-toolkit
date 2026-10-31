# Native dependency sources and notices

Reviewed 2026-10-31. The desktop build collects the following additional inputs
because Python wheel metadata alone did not contain all the native libraries'
licenses. The exact public URLs, revisions and SHA-256 digests are in
[`native-notices.json`](../packaging/desktop/native-notices.json) and
[`qt-sources.json`](../packaging/desktop/qt-sources.json).

Run these commands with the prepared desktop build interpreter, after the
normal dependency preparation and verification:

```text
python -I scripts/build-native-notices.py --output output/native-notices --cache output/desktop-source-cache
python -I scripts/build-qt-resources.py --output output/qt-resources --cache output/desktop-source-cache
```

Pass both output directories as separate `--resources-root` arguments to
`scripts/build-desktop-runtime.py`. Use fresh output directories. These commands
run on the build host; the installed application does not download source
archives or need build tools. The collectors retain unmodified source archives,
expose full license and attribution files with their original paths in an index,
and record every output file's digest and size. Archives are read without
extracting or executing their source files. Changed inputs, unsafe paths,
missing required notices and mismatched OCR model bytes fail before resource
output is created. Qt network failures get at most three attempts; incomplete
downloads never replace a verified cache file.

## Collected evidence

| Component | Retained material and scope |
| --- | --- |
| RapidOCR 1.4.4 | Complete supplier source and Apache-2.0 license, which the inspected wheel omitted. The collector checks the installed package version and all three OCR model hashes. |
| PaddleOCR models | Full upstream Apache-2.0 license and attribution. All three converted model files were compared with the exact model bundle used by RapidOCR's pinned wheel workflow. The supplier does not establish an exact upstream training revision; the manifest records that limit. |
| sherpa-onnx/core 1.13.8 | Complete supplier source, build workflows and pinned native dependency sources, including nested decoder dependencies. Optional/build dependencies are retained conservatively; their presence does not assert that every one is linked into each target. |
| eSpeak NG for Piper | Full source and GPLv3 `COPYING`, plus its Apache, BSD and Unicode notices. The upstream sherpa wheel builds enable TTS, so the wrapper's Apache metadata does **not** establish Apache-only licensing for the combined ASR native library. |
| ASR ONNX Runtime 1.28.2 | Its own full license and third-party notices pinned to the release revision. The main OCR runtime's ONNX Runtime 1.24.4 wheel notices are retained independently. These are distinct native copies. |
| GEOS 3.13.1 | Complete LGPL-2.1 source, build instructions, and Ryu notices. The collector checks Shapely's reported GEOS version before accepting this source. |
| Qt/PySide 6.12.0 | Complete PySide, QtBase, SVG and image-format sources; QtTranslations and QtWayland source inputs; and QtDoc's full Mesa/LLVM/Khronos/Boost attributions. Required license files are specific to each module. Translations and documentation do not automatically inherit QtBase's LGPL license option. |
| Qt software OpenGL | Upstream Mesa 11.2.2 and LLVM 3.6.2 sources and full notices, matching the embedded version strings of the selected Windows `opengl32sw.dll`. The DLL remains included. Supplier-specific build patches are not inferred from version strings. |

Qt/PySide and GEOS libraries remain dynamically loaded. Compatible modified
LGPL libraries can be substituted, and the toolkit does not prohibit reverse
engineering needed to debug those modifications. The source archives retain
their build instructions; replacement binaries must remain ABI-compatible.

## What this collection proves

The resource manifest proves the identities of the collected source and notice
files and records the checked package/model versions. It leaves
`rights_review` as `pending-exact-output`: release review must compare these
inputs with the actual target's native binary inventory. This is separate from
whether the desktop application passes its runtime acceptance tests.

The remaining target review must account for the combined ASR library's GPL
terms, any supplier-specific ONNX Runtime or Mesa additions, and platform
libraries selected by the Linux/macOS wheels. Keeping a dependency's source in
the bundle does not establish its presence in a particular binary or turn the
whole dependency set into permissive code. QtWayland sources document bundled
plugins; they do not claim that Wayland game capture has been validated.

## Validation

The focused tests cover archive traversal, links, duplicate paths, changed
checksums, missing full notices, runtime/model mismatches, downstream resource
collection, and bounded atomic Qt downloads. The complete local resource runs
retained 119 native-source/notice files (93,880,998 bytes) and 277 Qt-source/notice
files (128,745,193 bytes). These counts describe the pinned collection, not a
newly validated frozen application or an approved installer.
