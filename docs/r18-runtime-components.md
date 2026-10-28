# R18 runtime, tools and redistribution inventory

Status: **research and R19 input, not a bundle or installer**. Inspected on
2026-10-28 at upstream `4a4abfcee8d4fa87a8bfacdae12b6cef5284cad9`
(toolkit 0.21.3). The source baseline was freshly fetched before this study.
No dependencies, game tools or models were installed, no accounts or game files
were accessed, and no Windows executable was run for this inventory. Upstream
documentation and license files establish requirements and review gates; they do
not establish native compatibility or redistribution permission for every binary.

This report covers the existing Python runtime, frontend, every active game
toolchain, development/build tools, native dependencies and downloaded data.
The companion [storage and host contract](r18-storage-host-contract.md) owns paths,
origins, migration, readiness and lifecycle. Read this with the
[architecture study](rework-architecture.md), [roadmap](rework-roadmap.md),
[development checks](development-checks.md) and [release runbook](../RELEASE.md).

## Decisions and evidence rules

The proposed R19 starting point is **Windows x64, the existing Python runtime in
a PyInstaller directory (`onedir`) bundle**. Investigate a static frontend in a
separate equivalence spike. Retain the current router/origin behavior until the
spike proves the host contract. This decision does not select new recognition
algorithms or rewrite game readers.

Each component below has a disposition:

- **Bundle** means include in the candidate after the named license/native
  closure gates pass. It is a packaging decision, not a claim that the current
  release already contains it or that an unresolved license is permitted.
- **Separate user download** means acquire from the named upstream into local
  tool/data storage, with a verified receipt and the upstream notices. Unknown
  rights remain a gate. Separate download is not a cure for GPL integration,
  missing copyright permission, or rights over game-derived content.
- **System prerequisite** means an explicit OS/browser/runtime dependency, or a
  tool installed only on the build/development host. The end user must not need
  Python, Node/npm, a .NET SDK, Visual Studio or C/C++ Build Tools for the R19
  candidate. A still-required compiler or unclosed toolchain blocks the affected
  game's R19 acceptance; support must not silently disappear from the UI.

All external links in this report were consulted on **2026-10-28**. Versioned
source links identify the inspected version where possible. Moving documentation
describes upstream behavior on that date, not the contents of a checksum-pinned
release archive. An upstream project's top-level license does not establish the
license of its embedded dependencies, models, native libraries or game content.

## Current distribution and practical Windows boundary

[Packaging](../scripts/package-release.mjs) archives tracked source, adds the
prebuilt `dist` frontend and npm notices, and writes checksums/JSON provenance.
It does not freeze Python, embed Node, or collect ignored game-tool caches.
[Setup](../scripts/setup.ps1) still requires Node 24+, npm 10+, Python **3.12**,
and an installed `Microsoft.ScreenSketch` package; it creates a venv, runs pip
against the lock, copies local OCR assets, then runs `npm ci`. A matching release
frontend avoids a build, but not npm installation. The
[launcher](../scripts/companion-runtime.ps1) runs the Python backend, Node router
and Wrangler frontend. The [updater](../scripts/update-companion.ps1) also invokes
npm/pip and can build a frontend. A successful source ZIP install is therefore
different from a standalone R19 bundle.

Setup also calls [shortcut installation](../scripts/install-shortcuts.ps1),
which requires a Windows .NET Framework v4 `csc.exe` even when an existing
launcher needs no rebuild. It compiles the owned
[managed launcher](../launcher/ProxyTranscriptLauncher.cs) as a Windows executable,
then writes a project-path pointer and Start menu shortcut. This is separate
from the runtime launcher's `Add-Type` shim and from game-reader compilation.

| Boundary | Requirement, decision and limits |
| --- | --- |
| Product OS | Windows desktop. R19's proposed native baseline is **Windows 11 25H2 x64**, with an additional latest-serviced-image probe where available. No native validation is claimed here. [Microsoft's Home/Pro lifecycle](https://learn.microsoft.com/en-us/lifecycle/products/windows-11-home-and-pro) lists 25H2 servicing through 2027-10-13; 24H2 Home/Pro has already left ordinary support and is not the new default. Windows 10 x64 is a separately reported compatibility target, conditional on actual OS edition/build, working OCR assets, capture APIs and every selected tool. No Windows 7/8.1, Windows Server, macOS desktop or Linux product support follows from an individual dependency's platform list. |
| Windows lifecycle | Windows 10 Home/Pro ordinary support ended 2025-10-14. [Microsoft lifecycle](https://learn.microsoft.com/en-us/lifecycle/products/windows-10-home-and-pro) and [ESU information](https://www.microsoft.com/en-us/windows/extended-security-updates) distinguish ordinary support, edition-specific servicing and security-only ESU. The consulted consumer page reports coverage through 2027-10-12 and regional variation; recheck before a release. ESU enrollment is not a toolkit action and does not prove OCR or .NET support. |
| CPython support | [Python 3.12 Windows documentation](https://docs.python.org/3.12/using/windows.html) describes an upstream Windows 8.1+ floor and embedding options. That is not this app's supported OS matrix. [Python lifecycle](https://devguide.python.org/versions/) places 3.12 in security maintenance until 2028-10. The [3.12.16 release](https://www.python.org/downloads/release/python-31216/) is source-only; 3.12.10 was the last release with official binary installers. Pin an exact maintained Windows build and its supplier/source provenance before R19; selecting an arbitrary installed 3.12 or the last installer does not close this decision. |
| Architecture | The selected decoder, FModelCLI and Unreal decompression DLLs are x64. PRAGMATA's REE path is x86 and needs WOW64 plus matching x86 native libraries. ARM64 Windows/x64 emulation is **unverified**, including oneocr architecture matching, Python wheels, capture/audio, .NET location detection and x86 tool execution. No ARM64 or 32-bit product candidate is selected. |
| Capture and display | [Windows Graphics Capture](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture) depends on device/API support; HDR needs additional handling. [BackgroundCapture](../backend/window_capture.py) copies a GPU frame and checks DWM/client bounds, requiring a restored window for its error recovery guidance. Windowed/borderless, foreground/background, resize, minimization, multiple monitors, 100/125/150/175/200% DPI and capture bounds require native acceptance. A mocked browser build proves none of those. |
| Browser | **System prerequisite:** an ordinary desktop browser with the existing user profile and Browser Extension mode. The current [automatic launcher](../scripts/start-companion.ps1) searches only three fixed Google Chrome locations and fails to open a browser otherwise; `-NoBrowser` plus manually opening the canonical URL is a separate route. Chromium/Firefox are R19 functional test targets, not proof that today's launcher can select Firefox or that a real extension works there. Preserve browser/profile choice and do not silently create an isolated profile. Playwright engines are development artifacts; mobile Safari/WebKit evidence is separate. No WebView2 prerequisite is introduced. |
| Windows components | **System prerequisite:** Win32/DWM, DPAPI, Windows Job Objects, WASAPI and installed PowerShell used by current launch/update/setup scripts. They come from Windows, not copied OS DLLs. The launcher currently uses `Add-Type` to compile a C# Win32 shim through PowerShell/.NET facilities; distinguish that declared OS behavior from developer SDK/Build Tools and game-reader compilation. Record the supported PowerShell version/edition and prove any retained shim on the clean host, or precompile it. Do not assume a shell rewrite has already removed this dependency. |
| Managed launcher and native setup UI | **Bundle** a prebuilt owned launcher if retained for R19/R20; compile it on the Windows build host rather than during user installation. The current wrapper targets Windows PowerShell's `System32/WindowsPowerShell/v1.0/powershell.exe` and the pointer's source script/CWD; declare and probe its actual CLR/PE architecture and Framework/PowerShell requirements, or adapt it for the bundle. Current screen/folder dialogs also load `System.Windows.Forms`/`System.Drawing`; keep them as explicit Windows Framework conditions if retained. The `v1.0` path alone is not a PowerShell version probe. Source setup still needs Framework `csc.exe`; precompilation is proposed, not implemented. |

## Core runtime and Python dependencies

The authoritative current manifests are [requirements.txt](../requirements.txt)
and [requirements.lock.txt](../requirements.lock.txt). The latter is a resolved
Python 3.12/Windows set dated 2026-10-09, with **49 distributions** and exact
versions but **no wheel filenames, hashes or index provenance**. The input
requirements still contain ranges for ONNX Runtime and kaldi-native-fbank;
production setup uses the lock. The project declarations below were inspected
through their primary license files on 2026-10-28. Moving upstream license files
are a researched starting point; P1 still verifies the exact selected wheel's
terms and incorporated third-party files. `pytest` and its dependencies currently install
alongside application libraries. No Python package is made project-owned by
freezing it.

| Component/version at baseline | Current use and proposed disposition | License/native evidence and R19 gate |
| --- | --- | --- |
| CPython 3.12 (patch unpinned) and standard library | **Bundle** a Windows x64 interpreter/stdlib with the existing backend. Build host alone needs Python/pip/venv. | [PSF license and incorporated software notices](https://docs.python.org/3.12/license.html). Preserve the selected distribution's full notices and inventory `python312.dll`, `.pyd` modules and bundled OpenSSL, SQLite, expat, zlib, bzip2, lzma/libffi as actually present. Some libraries are compiled into extensions. Close the maintained binary supplier decision above and P1 below. |
| FastAPI 0.161.1; Starlette 1.9.0; Uvicorn 0.54.0; h11 0.16.0; anyio 4.15.1; click 8.5.0 | **Bundle** the HTTP/WebSocket service and its selected dependencies. | Primary declarations: [FastAPI MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE), [Starlette BSD-3-Clause](https://github.com/Kludex/starlette/blob/main/LICENSE.md), [Uvicorn BSD-3-Clause](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md), [h11 MIT](https://github.com/python-hyper/h11/blob/master/LICENSE.txt), [AnyIO MIT](https://github.com/agronholm/anyio/blob/master/LICENSE), [Click BSD-3-Clause](https://github.com/pallets/click/blob/main/LICENSE.txt). P1 closes exact wheel terms. `uvicorn[standard]` explains the native/optional dependencies below; no separate web server installation is required. |
| httpx 0.28.1; httpcore 1.0.9; idna 3.20; certifi 2026.10.23 | **Bundle** networking and CA data used for read-only/public downloads and explicitly requested account operations. | Primary declarations: [HTTPX BSD-3-Clause](https://github.com/encode/httpx/blob/master/LICENSE.md), [HTTPCore BSD-3-Clause](https://github.com/encode/httpcore/blob/master/LICENSE.md), [idna BSD-3-Clause](https://github.com/kjd/idna/blob/master/LICENSE.md), [certifi MPL-2.0 certificate data](https://github.com/certifi/python-certifi/blob/master/LICENSE). P1 must include CA-bundle notices and TLS/OpenSSL closure. Network availability and upstream limits remain runtime conditions. |
| Pydantic 2.14.1; pydantic_core 2.50.1; annotated-types 0.8.0; annotated-doc 0.0.5; typing-inspection 0.4.4; typing_extensions 4.16.0 | **Bundle** validation and typing support. | Primary declarations: [Pydantic MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE), [pydantic-core MIT](https://github.com/pydantic/pydantic-core/blob/main/LICENSE), [annotated-types MIT](https://github.com/annotated-types/annotated-types/blob/main/LICENSE), [annotated-doc MIT](https://github.com/fastapi/annotated-doc/blob/main/LICENSE), [typing-inspection MIT](https://github.com/pydantic/typing-inspection/blob/main/LICENSE), [typing_extensions PSF/Python license history](https://github.com/python/typing_extensions/blob/main/LICENSE). P1: native core wheel and full license chain; do not substitute another ABI/version based on a similarly named import. |
| oneocr 1.0.12 Python wrapper | **Bundle** wrapper only. [Capture](../backend/capture.py) imports `OcrEngine` directly. | [Exact PyPI release](https://pypi.org/project/oneocr/1.0.12/) declares MIT and supplies a small Python wheel; its examples require three external Microsoft files. Its Windows 10 classifier is not proof that current Snipping Tool OCR works on all Windows 10 builds. Include the wrapper's actual license through P1. |
| `oneocr.dll`, `oneocr.onemodel`, Snipping Tool's `onnxruntime.dll` | **System prerequisite**, locally obtained from the user's installed Snipping Tool. **Do not bundle.** Setup currently copies them to the oneocr user directory and initializes the engine. | [Microsoft Snipping Tool help](https://support.microsoft.com/en-us/windows/apps/use-snipping-tool-to-capture-screenshots) documents the app, not a redistributable OCR SDK. No Microsoft redistribution grant for these files was established. Wrapper MIT terms and ONNX Runtime's open-source terms do not relicense the Microsoft model or this particular binary set. R19 needs absence/version/architecture/readability/init probes with Store repair guidance; never take these files from a build host into the artifact. |
| mss 10.2.0; windows-capture 2.0.1; opencv-python 4.11.0.86 | **Bundle** capture libraries and applicable Windows wheel files. WGC is used for unfocused windows; MSS handles the ordinary screenshot route. | [MSS MIT](https://github.com/BoboTiG/python-mss/blob/main/LICENSE.txt); [windows-capture release](https://pypi.org/project/windows-capture/2.0.1/) declares MIT and describes Rust/Python capture. [OpenCV distribution licensing](https://pypi.org/project/opencv-python/4.11.0.86/#licensing): wrapper MIT, OpenCV Apache-2.0, bundled FFmpeg LGPL-2.1 and additional binaries/notices. P1 must inspect the wheel's Rust extension, `cv2.pyd`, FFmpeg/media DLLs and OS imports. Do not call the entire wheel Apache-only. |
| Pillow 13.0.0 | **Bundle** image decoding/conversion. | [Upstream license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) identifies **MIT-CMU**, including the retained PIL notices. P1 also covers the selected wheel's image codec/compression libraries, e.g. JPEG/PNG/TIFF/WebP/OpenJPEG/lcms/freetype where actually included. An upstream feature list is not an exact wheel inventory. |
| NumPy 1.26.4; SciPy 1.14.1 | **Bundle** numerical/fingerprint/VAD support. | Versioned [NumPy license](https://github.com/numpy/numpy/blob/v1.26.4/LICENSE.txt) and [SciPy license](https://github.com/scipy/scipy/blob/v1.14.1/LICENSE.txt) are BSD-style; their Windows wheel BLAS/LAPACK/OpenBLAS, Fortran and runtime libraries retain separate terms. P1 must enumerate `.libs`, `.pyd` and linked DLLs and CPU requirements. |
| onnxruntime 1.24.4 | **Bundle** CPU inference for FireRedVAD. No GPU/CUDA package is selected. | [Versioned MIT license](https://github.com/microsoft/onnxruntime/blob/v1.24.4/LICENSE), [installation requirements](https://onnxruntime.ai/docs/install/): Windows builds need the Visual C++ 2019 runtime or newer compatible runtime. Collect the wheel's actual provider/native DLLs and notices via P1. It is distinct from the Snipping Tool DLL and from sherpa's runtime. |
| kaldi-native-fbank 1.22.4; sherpa_onnx 1.13.8; sherpa-onnx-core 1.13.8 | **Bundle** only as required by the existing audio/agent path; preserve the isolated worker. | [kaldi release](https://pypi.org/project/kaldi-native-fbank/1.22.4/), [kaldi Apache-2.0 license](https://github.com/csukuangfj/kaldi-native-fbank/blob/master/LICENSE), [sherpa release](https://pypi.org/project/sherpa-onnx/1.13.8/) and [sherpa Apache-2.0 license](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE) establish project declarations. P1 must close exact wheel/native library terms and CPU ABI. [Agent recognition](../backend/agent_recognition.py) documents incompatible ONNX Runtime DLL versions and invokes [ASR](../backend/agent_transcribe.py) as a separate process. Freezing must preserve this process/DLL isolation, not import sherpa into the capture process. |
| PyAudioWPatch 0.2.12.9; webrtcvad-wheels 2.0.14.post1 | **Bundle** WASAPI loopback and voice detection. [Audio](../backend/audio.py) uses both with FireRedVAD. | [PyAudioWPatch release](https://pypi.org/project/PyAudioWPatch/0.2.12.9/) has a CPython 3.12 x64 wheel; package metadata says Apache-2.0 while inherited PyAudio prose says MIT. Retain and reconcile exact wheel notices, including PortAudio, through P1. [WebRTC wrapper license](https://github.com/daanzu/py-webrtcvad-wheels/blob/release/LICENSE) is MIT with additional WebRTC notices to retain. Test actual loopback endpoints; no microphone/account write is part of this research. |
| RapidFuzz 3.14.6; pycryptodome 3.24.1 | **Bundle** matching and archive/protected-data cryptographic support. | [RapidFuzz MIT](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE); [PyCryptodome public-domain and BSD-2-Clause portions](https://github.com/Legrandin/pycryptodome/blob/master/LICENSE.rst). P1 covers native matching/crypto extensions, CPU variants and complete incorporated notices. Crypto libraries do not authorize redistribution of keys or game resources. Windows DPAPI remains an OS service. |
| httptools 0.9.0; watchfiles 1.3.0; websockets 17.3; PyYAML 6.0.3; python-dotenv 1.2.4; colorama 0.4.6 | **Bundle** dependencies currently selected by Uvicorn's standard extra unless a separately checked runtime manifest proves an item unnecessary. | Primary declarations: [httptools MIT](https://github.com/MagicStack/httptools/blob/master/LICENSE), [watchfiles MIT](https://github.com/samuelcolvin/watchfiles/blob/main/LICENSE), [websockets BSD-3-Clause](https://github.com/python-websockets/websockets/blob/main/LICENSE), [PyYAML MIT](https://github.com/yaml/pyyaml/blob/main/LICENSE), [python-dotenv BSD-3-Clause](https://github.com/theskumar/python-dotenv/blob/main/LICENSE), [colorama BSD-3-Clause](https://github.com/tartley/colorama/blob/master/LICENSE.txt). P1 includes native extensions and their independent dependencies. No `uvloop` is in this Windows lock. |
| opencc-python-reimplemented 0.1.7; pypinyin 0.55.0 | **Bundle** local Chinese normalization/pinyin data, preserving original transcript text. | [OpenCC Python Apache-2.0](https://github.com/yichen0831/opencc-python/blob/master/LICENSE.txt), [pypinyin MIT](https://github.com/mozillazg/python-pinyin/blob/master/LICENSE.txt). P1 includes dictionary data and exact package notices; dictionaries are not covered merely by a module license label. |
| flatbuffers 25.12.19; protobuf 7.36.2; sympy 1.14.0; mpmath 1.3.0; packaging 26.3 | **Bundle** locked transitive runtime support where imported by the selected packages. | Primary declarations: [flatbuffers Apache-2.0](https://github.com/google/flatbuffers/blob/master/LICENSE), [protobuf BSD-3-Clause](https://github.com/protocolbuffers/protobuf/blob/main/LICENSE), [SymPy BSD-3-Clause](https://github.com/sympy/sympy/blob/master/LICENSE), [mpmath BSD-3-Clause](https://github.com/mpmath/mpmath/blob/master/LICENSE), [packaging Apache-2.0 OR BSD-2-Clause](https://github.com/pypa/packaging/blob/main/LICENSE). P1 distinguishes Python/native protobuf and retains file-level notices. These are resolved dependencies, not evidence arbitrary newer versions work. |
| imageio-ffmpeg 0.6.0 | **Bundle** wrapper; **separate user download** of FFmpeg until F1 closes an exact distributable binary. | [Wrapper license](https://github.com/imageio/imageio-ffmpeg/blob/main/LICENSE) is BSD-2-Clause. Its [upstream packaging](https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0) includes platform-specific FFmpeg executables in wheels. Avoid accidentally carrying that executable into the freeze while calling FFmpeg a separate download. See F1; either collect it deliberately with full evidence or exclude and verify the separate tool. |
| pytest 9.1.1; iniconfig 2.3.1; pluggy 1.7.0; Pygments 2.21.0 | **System prerequisite, development/build host only**. Exclude from the proposed user bundle after checking the runtime import graph. | [pytest MIT](https://github.com/pytest-dev/pytest/blob/main/LICENSE), [iniconfig MIT](https://github.com/pytest-dev/iniconfig/blob/main/LICENSE), [pluggy MIT](https://github.com/pytest-dev/pluggy/blob/main/LICENSE), [Pygments BSD-2-Clause](https://github.com/pygments/pygments/blob/master/LICENSE). They are in the current production install lock; do not edit it in R18. An R19 packaging manifest must prove runtime exclusion is safe. |

**P1 — exact Python/native closure gate.** For the chosen CPython patch, resolve
all 49 locked distributions for CPython 3.12/Windows x64 with binary-only
selection on the build host, without falling back to sdists or user compilers.
Record each wheel's filename, SHA-256, URL/index, architecture/ABI, dependency
metadata, license expression, full license/NOTICE paths and included data. Check
that the closure contains every package above and no unreviewed dependency.
Inspect every `.pyd`/`.dll`/`.exe`, including `.libs` and package data, using PE
imports and delay imports; record the recursively loaded non-OS modules in native
probes. Classify each DLL as app-local redistributable with evidence, separately
downloaded, or a named OS/VC runtime prerequisite. Resolve missing licenses rather
than interpreting missing metadata as permission. Compare PyInstaller's collected
files against this manifest and reject unlisted binaries. `pip freeze` and
successful imports alone are insufficient. This artifact-level closure remains
**open** because this study did not acquire Windows wheels or produce a bundle.

**VC runtime decision:** **System prerequisite**, with an explicit compatible
Microsoft x64 redistributable and x86 redistributable where an x86 tool requires
one. [Microsoft's rules](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
require matching architecture and a runtime at least as recent as the build tools;
redistribution has its own license conditions. R19 must name the observed minimum
version and offer an official repair/download route. Do not copy arbitrary DLLs
from System32, or assume a developer PC's preinstalled runtime is part of Windows.

## JavaScript, frontend and build closure

[package.json](../package.json) and [package-lock.json](../package-lock.json)
pin the current graph (lockfile version 2; **462 package entries**, excluding the
root). The engine field allows Node >=22.13.0, while setup/release/CI require
Node 24; R19 uses the latter build baseline and must pin a patch. Wrangler is a
`devDependency` yet an active installed-runtime dependency. Likewise TypeScript
is a `devDependency` but the ZZZ scene extractor imports it at runtime. npm's
development flag is not a safe end-user exclusion rule.

| Component(s), exact direct versions | Proposed disposition and purpose |
| --- | --- |
| Node 24 + npm 10+ (exact patches not pinned) | **System prerequisite on build/development hosts only**; **bundle** an app-local Node executable for a retained ZZZ helper after G1/J1 and functional proof. No end-user Node/npm installation. The current unbundled router/Wrangler host remains diagnostic; shipping an embedded frontend host needs a recorded reason and decision amendment in the [integrated plan](r18-runtime-inventory.md), plus exact closure and clean-host proof. Use the selected Node release's complete [license and incorporated dependency notices](https://github.com/nodejs/node/blob/v24.x/LICENSE), not an MIT label alone. npm need not run in the installed candidate. |
| vinext 1.3.0; react, react-dom and react-server-dom-webpack 19.3.1 | **Bundle** emitted frontend and any actually retained server runtime. Lock metadata identifies MIT. Static hosting is an R19 spike; the current [Vite configuration](../vite.config.ts) uses RSC/SSR/Cloudflare. A successful mobile static build does not prove equivalent desktop pages, API/WS or browser storage. |
| @cloudflare/vite-plugin 1.65.0; wrangler 4.152.0; @cloudflare/workers-types 5.20261023.1; @vitejs/plugin-rsc 0.5.38 | **System prerequisite on build host**; an installed-runtime **bundle** subset is conditional on a recorded embedded-host decision amendment and clean-host/license proof. The retained unbundled frontend adapter is diagnostic. Wrangler's locked transitive runtime includes Miniflare 5.20261019.2-beta, workerd 1.20261019.1, esbuild 0.28.2 and unenv 2.0.0-rc.24. Static equivalence is the preferred way to remove those installed-runtime requirements. |
| @openai/sites-vite-plugin 0.2.0; vite 8.3.5; @vitejs/plugin-react 6.1.2; typescript 5.9.3; @types/node 22.19.19; @types/react 19.3.0; @types/react-dom 19.3.0 | **System prerequisite on build host**. **Bundle** TypeScript with a retained ZZZ Node helper until it is precompiled with equivalent behavior. Versioned npm package notices/integrities require J1; the lock has no license field for the Sites plugin, which is a closure gate, not permission. No Sites/Cloudflare login is needed to run the local companion. |
| @tailwindcss/postcss 4.3.3; tailwindcss 4.3.3; tw-animate-css 1.4.0 | **System prerequisite on build host**; **bundle** generated CSS. Review native CSS compiler/license closure below. |
| @firebird55/lexirise-components 1.0.12 | **Bundle** emitted shared UI. [Provenance](../vendor/lexirise-components/PROVENANCE.json) pins source `2e84f74cf77ea4773463331c7ecde0b05faf31f8`; [custom attribution license](../vendor/lexirise-components/LICENSE). Change it only through the shared repository workflow. |
| @base-ui/react 1.7.0; @shadcn/react 0.3.1; class-variance-authority 0.7.1; clsx 2.1.1; cmdk 1.1.1; date-fns 4.4.0; embla-carousel-react 8.6.0; input-otp 1.5.0 | **Bundle** code actually emitted into the UI. J1 closes each package's actual notices and dependencies; do not distribute all node_modules merely because packages are listed here. |
| lucide-react 1.31.0; react-day-picker 10.0.2; react-resizable-panels 4.14.8; recharts 3.10.1; tailwind-merge 3.7.0 | **Bundle** emitted UI code under each upstream license; retain Lucide icon notices, rather than assuming all React packages share React's MIT terms. J1 applies to the entire emitted graph. |
| tesseract.js 7.0.0; @tesseract.js-data/eng, chi_sim and chi_tra 1.0.0; opencc-js 1.4.2 | **Bundle** browser OCR/WASM/models/dictionaries and notices. The locked transitive tesseract.js-core is 7.0.0. See M1 and the model table below; npm packaging metadata alone is not the model license. |
| jsqr 1.4.0; qrcode-generator 2.0.4; fflate 0.8.3 (development entry and override) | **Bundle** self-hosted QR/ZIP browser assets. jsQR Apache-2.0, QR generator MIT, fflate MIT are recorded with full notices by [mobile assets](../scripts/mobile-assets.mjs). Preserve those generated notices. |
| ooz-wasm 2.0.0; xxhash-wasm 1.1.0 | **Bundle** only within the selected ZZZ helper after G1 closes. The lock identifies **GPL-3.0-or-later** and MIT respectively. The actual GalScript reader imports these modules; a different process/download location does not by itself settle the combined-work question. |
| oxlint 1.89.0; oxfmt 0.74.0; oxlint-tsgolint 7.0.2005; playwright 1.64.1 | **System prerequisite on development/CI hosts only**. Do not ship linter/compiler or Playwright browser installations to users. Browser engine licenses and platform restrictions remain build/test concerns. |

**J1 — JavaScript/native closure gate.** The lock records tarball integrities but
omits the `license` field for **283 of 462** entries. That does not mean those
packages are unlicensed; it means the lock is not a complete license inventory.
[dependency-notices.mjs](../scripts/dependency-notices.mjs) collects top-level
license/NOTICE/COPYING files from installed packages and skips absent packages;
it does not recursively prove licenses of embedded binaries, nested notice
directories, downloaded fonts or non-npm tools. Current release notices are useful
input, not a future bundle SBOM.

On the Windows build host, inventory the **actual installed and emitted** graph
with exact versions/integrities and retain complete notices. Inspect the native
families below; separate packages used only during building from runtime files
actually emitted/loaded. Verify peer/optional selection rather than shipping
foreign-platform binaries from the cross-platform lock:

| Locked transitive family | Exact version and gate |
| --- | --- |
| Cloudflare workerd Windows binary | `@cloudflare/workerd-windows-64` 1.20261019.1, Windows x64 only; Apache-2.0 metadata. Inspect its embedded/native notices and PE closure if retained. No Windows ARM64 workerd entry is present in this lock. |
| esbuild Windows packages | 0.28.2 (`win32-x64`, `win32-arm64`, `win32-ia32` optional entries); license metadata absent in these lock entries. Verify the exact package license rather than inheriting another tool's license. |
| Rolldown/Oxc families | rolldown/@rolldown bindings 1.2.15; @oxc-project/types 0.155.0; @oxlint bindings 1.89.0; @oxfmt bindings 0.74.0; @oxlint-tsgolint 7.0.2005; MIT metadata where supplied. Their `.node`/executables and Rust/Go/native dependencies require actual package notices and build-host platform selection. |
| CSS native families | @tailwindcss/oxide 4.3.3; lightningcss 1.32.0 plus Vite's nested 1.33.0 and platform bindings. The 1.32.0 lock entries say MPL-2.0; several nested 1.33.0 entries have no license metadata. Preserve applicable source/license obligations for distributed files; do not flatten this into MIT. |
| Sharp/libvips | sharp and @img/sharp Windows bindings 0.35.5, optional/dev-optional; other-platform libvips entries 1.3.4. Lock license metadata is absent. If any part reaches the installed artifact, inspect the selected package's native image codecs, libvips/LGPL and other third-party notices and PE closure. Otherwise record build-only exclusion with emitted-artifact evidence. |
| WASM/data | tesseract.js-core 7.0.0, ooz-wasm 2.0.0, xxhash-wasm 1.1.0, blake3-wasm 2.1.5, QR/ZIP/OpenCC assets and font downloads require their real byte hashes and notices. A `.wasm` extension does not remove license obligations. |

The current lock's lifecycle scripts include esbuild, tesseract.js, workerd and
optional macOS fsevents. R19 must account for artifacts created/downloaded by
build scripts; npm integrity alone covers the package tarball, not arbitrary
post-install output. [Geist font notices](../styles/GEIST-OFL.txt),
[shadcn notices](../styles/SHADCN-LICENSE.md) and existing
[third-party notices](../THIRD_PARTY_NOTICES.md) remain part of the emitted product.

## Models, dictionaries and downloaded data

| Resource and provenance | Disposition and limits |
| --- | --- |
| FireRedVAD ONNX and CMVN | **Bundle** with Apache-2.0 license/notice. [Local provenance](../assets/fireredvad/PROVENANCE.json) records FireRedTeam commit `c30ec49e8cc69642b0ee65362eba11b9d11c6e54`, source URLs and both hashes; [upstream license](https://github.com/FireRedTeam/FireRedVAD/blob/c30ec49e8cc69642b0ee65362eba11b9d11c6e54/LICENSE) was checked. [Runtime](../backend/firered_vad.py) uses CPU ONNX Runtime and a legacy fallback asset location. Validate byte hashes and resource lookup in the extracted bundle. |
| Tesseract browser OCR | **Bundle** Tesseract.js/core 7.0.0 (Apache-2.0), `eng`, `chi_sim`, `chi_tra` `4.0.0_best_int` traineddata from the pinned 1.0.0 npm packages. The model's [upstream license](https://github.com/naptha/tessdata/blob/gh-pages/LICENSE) is Apache-2.0 independently of the npm wrapper's MIT metadata. [Mobile asset copying](../scripts/mobile-assets.mjs) retains notices and checksums; [integrity manifest](../scripts/mobile-ocr-integrity.json) pins core loader bytes. M1 must verify the full emitted asset/checksum set, workers and model selection, not just the six pinned core loaders. |
| OpenCC dictionaries and pinyin | **Bundle** exact selected package data. Browser OpenCC-JS has MIT implementation and Apache-2.0 dictionary derivatives; Python OpenCC is separately distributed. Keep full upstream data notices from the selected packages and preserve original transcript text. |
| Geist/Geist Mono | **Bundle** generated font assets with SIL OFL 1.1. [Existing notice](../styles/GEIST-OFL.txt) and [provenance notes](../THIRD_PARTY_NOTICES.md) identify google/fonts revision `bd8f81ddb5c74d5c8897b36ad88b440266245103`. Capture the actual downloaded font bytes/build source; fonts are outside npm's dependency tree. |
| Optional ZZZ agent ASR model/tokens | **Separate user download**, pending a verified source/license/version/hash manifest. [Agent worker](../backend/agent_transcribe.py) loads a SenseVoice-format `model.int8.onnx` plus `tokens.txt` from the local agent model folder; no automatic model acquisition or model provenance manifest was found in the inspected setup path. Do not infer rights from sherpa's license or bundle an existing local model. Missing files need an explicit unavailable state and preparation guidance. |
| ZZZ textmaps/metadata | **Separate user download**, private runtime data. [game_tools](../backend/game_tools.py) currently uses moving `dimbreath/ZenlessData` master for four metadata files; [language indexing](../backend/zzz_assets.py) resolves an immutable commit, while the legacy [TextMapIndex](../backend/textmaps.py) retains moving URLs. JSON validation/content hashes do not establish publisher permission or authenticity. Pin/reconcile provenance per prepared snapshot; never ship the caches as seed data. |
| Genshin/Star Rail/Endfield dialogue catalogs | **Separate user download**, private runtime data. [DialogueCatalog](../backend/dialogue_catalog.py) resolves commits from GitLab `Dimbreath/animegamedata2`, `Dimbreath/turnbasedgamedata`, and GitHub `rmxlinux/EndfieldData`, then records content hashes. These are third-party game-derived catalogs, not publisher redistribution grants. Preserve availability/unsupported-format errors and last complete indexes. |
| NTE movie metadata | **Separate user download**, private runtime data. [Catalog source](../backend/game_catalogs.py) is `Waifus-Grace/NTE_Assets`, seed `cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7`, subsequently refreshed by commit. No content redistribution is approved here. |
| PRAGMATA asset list/sound graph | **Separate user download**, private runtime data. [Indexer](../scripts/index_pragmata_assets.py) fetches Ekey's moving `P_STM_Release.list` and REasy's moving `resources/data/sound/pragmata.json.gz`, with cached fallback. They are not the pinned REE executable/source archive. R19 must record snapshot origin/hash and keep this game-derived material out of the installer. |
| Wuthering/NTE archive metadata | **Separate user download**, only during needed preparation. [Wuthering](../backend/wuthering_assets.py) reads public version metadata from `yarik0chka.github.io/wuwa-keys/keys.json`; [NTE](../backend/nte_assets.py) reads a public SCSKiller issue and may protect a local cache with DPAPI. No metadata values belong in the SBOM, logs or published provenance. A public endpoint does not grant rights to the game. Record source identity without copying sensitive values. |
| Game installations, optional voice packs, extracted text/audio/images, recordings, exported libraries and indexes | **System prerequisite/user-local content, never redistributed by the toolkit**. Read only the user's installed files; install language/voice packs through the publisher's launcher. Native validation of an absent pack remains unavailable. A game-derived cache, even with hashes or a third-party repository license, must not enter a public bundle/Pages artifact. |

**M1 — resource gate.** The extracted candidate needs an allowlisted resource
manifest with source/version/SHA-256/license per shipped model, dictionary, font,
WASM module and worker. Verify offline loading from the candidate, not a warm
developer cache or remote CDN. Preserve the mobile static publishing allowlist;
its assets do not authorize publishing desktop services or game data.

## Game tools and redistribution decisions

The active list is [game_paths.GAMES](../backend/game_paths.py): **13 games**.
[missing_tools/prepare_tools](../backend/game_tools.py) is the current acquisition
entry point. It downloads vgmstream for all active games except BEYOND/HEAVY RAIN,
then game-specific tools. Several important dependencies are detected only later
when indexing or playback begins; a file-existence check is not functional proof.

| Tool/version and source pin | Current behavior | R19 disposition and closure |
| --- | --- | --- |
| vgmstream r2117 `vgmstream-win64.zip` | [URL/hash](../backend/game_tools.py): SHA-256 `6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c`. Archive extraction retains all files, including `COPYING`, with a per-file receipt. | **Separate user download** from the [upstream release](https://github.com/vgmstream/vgmstream/releases/tag/r2117). [Core COPYING](https://github.com/vgmstream/vgmstream/blob/r2117/COPYING) permits redistribution with notices, but does not cover all dependencies. See V1 for its native/license closure. Do not include only the CLI executable or claim the whole archive is permissive. |
| FFmpeg (selected by PATH, else imageio-ffmpeg 0.6.0) | [media_tools](../backend/media_tools.py) prefers an arbitrary system `ffmpeg`, then `imageio_ffmpeg.get_ffmpeg_exe()`; playback/export invokes it as a subprocess. No exact FFmpeg binary/version/hash is fixed by the Python version pin. | **Separate user download** until F1 identifies a particular distributable build; then bundling can be a separately reviewed packaging decision. [FFmpeg's own license](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md) varies with configuration: LGPL base, GPL with selected parts, and further incompatible/nonfree combinations. The wrapper's BSD license is not the executable's license. |
| ZZZ GalScript reader | `galgame-perform.ts` from simon300000/zenless-voice commit `bb2b9790d2d45a5c662c36cd9f046d05893d0ef4`; source SHA-256 `176491a567b6152f5031b71ea7d742dba3228462d404a6abf03c2242c6ca2731`. MIT notice downloaded beside it. [Owned extractor](../scripts/extract_voice_links.mjs) transpiles it using TypeScript, imports it and uses ooz/xxhash WASM. | **Bundle** a prepared helper and required Node/runtime modules only after G1 and J1. The [reader's MIT license](https://github.com/simon300000/zenless-voice/blob/bb2b9790d2d45a5c662c36cd9f046d05893d0ef4/LICENSE) does not relicense GPL ooz. Leave game tables outside it. No runtime npm/TypeScript installation may be required from the user. |
| PRAGMATA REE x86 + selective adapter | REE `Latest/REE.Unpacker-x86.zip`, SHA-256 `caa20e3ad94a4e9f09d2a53b7aceaa4ca0dc6bdba403904da6b43ceffb510884`. [Selective builder](../backend/ree_extractor.py) also fetches source commit `d22c15314e84eecd31480acfe692092c48043ac0`, archive SHA-256 `eb868e19fe42ccc2f374a4c33963d9f2c5bbf996ca27f212b4de226c7d0f1776`; patches 17 C# files and compiles x86 with Windows .NET Framework `csc.exe`. Required files include `Zstandard.Net.dll`, `System.Buffers.dll`, `libzstd.dll` and project lists. | **Separate user download** of upstream tool/source only; **system prerequisite** .NET Framework currently supplies compilation/execution. **Blocked for compiler-free R19 delivery** until the right to distribute the modified selective binary/source and all dependencies is established and a prebuilt helper passes native checks. The [pinned source tree](https://github.com/Ekey/REE.PAK.Tool/tree/d22c15314e84eecd31480acfe692092c48043ac0) has no LICENSE/COPYING/NOTICE file in its complete tree; public source is not a license grant. Do not bundle this derived executable based on the toolkit's license. Do not substitute the stock all-files unpacker for bounded selective extraction. |
| WolvenKit Console 9.0.1 | [Downloader](../backend/cyberpunk_assets.py) uses SHA-256 `364427384c0f4ebb6b157fa9abd01595258af1b7993c7b3a7edd2920f2016e92` for the official ZIP; runs `WolvenKit.CLI.exe`. Existing verified-version receipt does not rehash every cached file. | **Separate user download**. [9.0.1 release](https://github.com/WolvenKit/WolvenKit/releases/tag/9.0.1) explicitly requires **.NET 10 runtime**, not SDK; [license](https://github.com/WolvenKit/WolvenKit/blob/9.0.1/LICENSE) is GPLv3. R19 must probe CLI/native RED4/Oodle/etc dependencies from this exact archive and pin runtime architecture. Prefer a verified self-contained upstream CLI if available; otherwise explicitly declare the .NET 10 x64 runtime prerequisite with repair guidance. Shipping another build requires its own hash/source/license closure and Cyberpunk format proof. G1 applies. |
| FModelCLI v1.0.2 | [Downloader](../backend/wuthering_assets.py) pins executable SHA-256 `86426493c63f0af2ccf6d1d8b498a737723069f6c25a573a46e94d1a3f26e835`, supplies `.data` decompression DLLs and copies vgmstream. | **Separate user download**. [Exact project](https://github.com/Herselfta/FModelCLI/blob/v1.0.2/FModelCLI/FModelCLI.csproj) targets .NET 8, `win-x64`, self-contained single-file; that differs from a .NET SDK requirement. [NOTICE](https://github.com/Herselfta/FModelCLI/blob/v1.0.2/NOTICE) identifies FModel/GPL, CUE4Parse and many managed/native libraries. Metadata differs between GPL-3.0-only project field and later-version wording in NOTICE; reconcile exact terms in G1. A self-contained label does not cover external Oodle/zlib, codec DLLs or all notices. |
| Shared Unreal decompression files | Both Wuthering and NTE call [ensure_unreal_decompression](../backend/wuthering_assets.py): `oodle-data-shared.dll` from WorkingRobot/OodleUE `2026-01-25-1223/clang-cl-x64-release.zip`, file SHA-256 `8f6c0d487573b5a7ea8548407cbf96f5cd833fe7138769914961b6697d74b3b3`; `zlib-ng2.dll.gz` from NotOfficer/Zlib-ng.NET 1.0.0, decompressed file SHA-256 `454be2f3d10f804ace577198401431db5e95d0286b59589bc28a40085388e7c2`. | **Separate user download**, subject to explicit rights review. [OodleUE](https://github.com/WorkingRobot/OodleUE#eula-notice) states Epic/RAD ownership and Unreal EULA applicability; no general toolkit redistribution grant was established. The [Zlib-ng.NET wrapper](https://github.com/NotOfficer/Zlib-ng.NET) says MIT, but the downloaded native library also needs its own [zlib-ng license](https://github.com/zlib-ng/zlib-ng/blob/develop/LICENSE.md), build provenance and imports. Unknown rights block bundling; a checksum is identity evidence only. |
| NTE owned bridge + UEExtractor v1.0.8.7 | [NTE preparation](../backend/nte_assets.py) checks for **.NET 10 SDK** before building and again before running the cached DLL. UEExtractor ZIP SHA-256 `e89ffece53cc11970d08f6d0a683b67ca58882e8c51fb99de07923175eb96660`; upstream license revision `1dff3554320d530efff26a827819f0e011f1b892`. [Bridge project](../scripts/game-readers/NteReader.csproj) is net10.0; bridge calls `Assembly.LoadFrom` on a physical `UEExtractor.dll`. | **Bundle** the owned bridge as a `win-x64` self-contained directory publication; **separate user download** of UEExtractor and decompression tools initially. [UEExtractor license](https://github.com/SolicenTEAM/UEExtractor/blob/1dff3554320d530efff26a827819f0e011f1b892/LICENSE) is MIT. [Its project](https://github.com/SolicenTEAM/UEExtractor/blob/1dff3554320d530efff26a827819f0e011f1b892/UEExtractor/UEExtractor.csproj) also uses CUE4Parse, Newtonsoft.Json 13.0.4 and Costura/PortableCostura build tooling. Review its pinned CUE4Parse submodule `6409f38e09e2a21aa839cd77b4515bca6c66f280` and actual archive/deps/native files before any binary inclusion. R19 must remove the runtime SDK check through a source/bundle adapter and prove dynamic loading. A cached DLL alone still requires an SDK under today's code. |
| Endfield owned bridge + selected EndfieldStudio source | [Source manifest](../scripts/endfield-reader-sources.json) pins **14 source files**, individual hashes and revision `48c40a5e6a931b08223384077b74b41b484a540f`. [Builder](../backend/endfield_assets.py) fetches sources/license, uses .NET 10 SDK and restores System.IO.Hashing 9.0.0 from NuGet; [project](../scripts/game-readers/EndfieldReader.csproj) targets net10.0. Runtime checks the SDK before executing. | **Bundle** a prebuilt self-contained `win-x64` reader after closure, with the selected source's [MIT notice](https://github.com/EIHRTeam/EndfieldStudio/blob/48c40a5e6a931b08223384077b74b41b484a540f/LICENSE). Close NuGet/runtime/native notices and provenance for the **selected subset**; do not import the entire EndfieldStudio GUI/FBX/Oodle pipeline. The manifest includes `Keys.cs`: classify game-derived constants/archive metadata separately before binary inclusion; implementation MIT terms alone do not establish publisher rights to embedded data. Never print values in public provenance. The upstream project also records ports from other projects; retain file-level notices and verify provenance. R19 must remove end-user compilation/SDK checks and prove VFS/text/audio/USM paths. No NuGet lock or exact SDK patch is currently tracked. |

**V1 — vgmstream closure.** The r2117 source tree contains an x64 library set:
`avcodec-vgmstream-59.dll`, `avformat-vgmstream-59.dll`,
`avutil-vgmstream-57.dll`, `swresample-vgmstream-4.dll`, `libatrac9.dll`,
`libcelt-0061.dll`, `libcelt-0110.dll`, `libg719_decode.dll`, `libmpg123-0.dll`,
`libspeex-1.dll` and `libvorbis.dll`. Its
[dependency license directory](https://github.com/vgmstream/vgmstream/tree/r2117/ext_libs/licenses)
contains separate FFmpeg LGPL-2.1/LGPL-3, mpg123, CELT, Vorbis/Ogg, Speex, Opus and
LibAtrac9 notices. This is a source-tree inventory, **not proof that the selected
ZIP contains exactly those files**. Before bundling, inspect the pinned ZIP's full
file list, versions, license/source obligations and PE closure; resolve G.719 and
any binary without adequate notices. Current separate-download preparation must
retain the whole archive's notices and verified receipt. Native decode probes
must demonstrate needed game codecs, not merely `vgmstream-cli --help`.

**F1 — FFmpeg distribution gate.** Record the selected executable's file hash,
origin, FFmpeg version, `-buildconf`, `-L`, enabled encoders/decoders and every
shared native library. Inspect applicable GPL/LGPL/version3/nonfree configuration
and corresponding-source/relinking/notice requirements. A PATH binary is unknown
until inspected; the imageio wheel's bundled executable is a different
distribution from vgmstream's FFmpeg DLLs and OpenCV's FFmpeg. Preserve those
three closures independently. R19 must use a deterministic app/tool path and
probe the needed codecs/output formats; current PATH-first behavior is a
documented compatibility input, not permission to copy whatever the build host
finds.

**G1 — copyleft and unknown-rights gate.** Establish the exact license and source
closure for distributed GPL components, including ooz WASM, FModelCLI and
WolvenKit. Record the helper/process interfaces and which code is combined,
linked, modified or merely aggregated; determine the applicable obligations for
that concrete arrangement with the project's custom attribution license. Include
corresponding source, build scripts, modifications and notices as required. Do
not assume a subprocess automatically establishes independence, or that
user-downloaded code makes a distributed integration compliant. For REE/Oodle or
any file without an established grant, keep redistribution blocked until the
rightsholder terms/permission cover the intended artifact. This report does not
give legal approval for those unresolved cases.

## All active games and distinct functional probes

Every game below also depends on core capture/OCR, the browser/UI and local
storage. Original audio export commonly uses FFmpeg; vgmstream is not needed for
Quantic MP3 block decoding. Rows identify additional toolchains, not a complete
claim about supported scenes, languages or installed packs. The
[game audit index](game-audits/README.md) owns those coverage limitations.

| Active game | Reader/tool path and minimum R19 functional probe |
| --- | --- |
| Zenless Zone Zero (`zzz`) | [ZZZ adapter](../backend/zzz_assets.py), Python PCK/voice reader, Node/TypeScript GalScript + ooz/xxhash WASM, vgmstream/FFmpeg; separate game metadata. Probe authored dialogue, comic and cinematic helper paths, archive refresh and one exact voice decode/export. A static frontend does not remove this Node dependency. Optional agent fingerprint/ASR is a separate declared probe with verified model provenance and isolated worker. |
| PRAGMATA (`pragmata`) | [Adapter](../backend/pragmata_assets.py), [MSG/audio indexer](../scripts/index_pragmata_assets.py), selective x86 REE/.NET Framework + Zstandard.Net/System.Buffers/libzstd, vgmstream/FFmpeg. Probe bounded selected-resource extraction and voiced/cinematic output with the actual prebuilt candidate; no stock whole-archive substitute. Gate remains blocked while derived-tool rights/compiler-free delivery are unresolved. |
| Cyberpunk 2077 (`cyberpunk`) | [WolvenKit adapter](../backend/cyberpunk_assets.py), .NET 10 CLI, vgmstream/FFmpeg. Probe base-game archive-to-JSON/readable text and original voice; expansion absence must be valid, with a separate installed Phantom Liberty probe when available. Record actual CLI runtime/native requirements. |
| Wuthering Waves (`wuwa`) | [FModelCLI adapter](../backend/wuthering_assets.py), self-contained .NET 8 x64 CLI plus external Oodle/zlib/vgmstream/FFmpeg. Probe list/extract, text/voice bindings and optional movie archives, missing public version metadata, correct `.data` lookup and codec output without preinstalled .NET SDK. |
| The Witcher 3 (`witcher3`) | [Python reader](../backend/witcher_assets.py) and [narrative parser](../backend/witcher_narrative.py), vgmstream/FFmpeg. No WolvenKit requirement is present for this adapter. Probe `.w3strings`/speech and compressed narrative bundles plus selected original voice. |
| Neverness to Everness (`nte`) | [Owned net10 bridge](../scripts/game-readers/NteReader.cs), UEExtractor/CUE4Parse, Oodle/zlib, vgmstream/FFmpeg, separate movie metadata. Probe real dynamic assembly loading, archive/localization and Wwise event/media paths, movie binding and protected local metadata cache. Must run without an SDK or user compilation. |
| BEYOND: Two Souls (`beyond`) | [Python Quantic reader](../backend/beyond_assets.py), shared [archive](../backend/quantic_assets.py)/[MP3 block decoder](../backend/quantic_audio.py), FFmpeg; no vgmstream/external extractor. Probe indexed text plus reservoir-preserving MP3 runs/authored silence and exact duration output. |
| HEAVY RAIN (`heavyrain`) | [Python Quantic/legacy reader](../backend/heavy_rain_assets.py), FFmpeg; no vgmstream/external extractor. Probe its distinct Resources/GameData archive layers and multilingual text/MP3 partitions; BEYOND alone does not prove this layout. |
| Honkai: Star Rail (`starrail`) | [Python HoYo PCK reader](../backend/starrail_assets.py) with [shared dialogue reader](../backend/hoyo_dialogue.py), separate immutable catalog, vgmstream/FFmpeg. Probe catalog acquisition/reuse, local pack detection and text-to-original-voice extraction, including a missing-pack result. |
| Genshin Impact (`genshin`) | [Python HoYo reader](../backend/genshin_assets.py), separate catalog, vgmstream/FFmpeg. Probe installed global/regional data-root variants as declared, PCK voice, narrative/cinematic catalog path and missing pack without fallback to another voice. Star Rail's format proof does not establish Genshin's. |
| Arknights: Endfield (`endfield`) | [Owned net10 reader](../scripts/game-readers/EndfieldReader.cs), selected EndfieldStudio sources/System.IO.Hashing, separate catalog, vgmstream/FFmpeg. Probe StreamingAssets/Persistent VFS precedence, missing layer, AKPK/audio, text and selected USM/cinematic path without SDK/NuGet on the user's PC. |
| Rise of the Tomb Raider (`riseofthetombraider`) | [Python TIGER reader](../backend/rise_tomb_assets.py), [shared archive parser](../backend/tiger_archive.py), vgmstream/FFmpeg for MUL/movie audio. Probe compressed/uncompressed archive entries, actual selected locale, authored stream/cue boundaries and movie path; regional/DLC packs remain explicit. |
| Shadow of the Tomb Raider (`shadowofthetombraider`) | [Python TIGER/locale/Wwise reader](../backend/shadow_tomb_assets.py), vgmstream/FFmpeg. Probe its localization/WEM bindings and archive segments; Rise's MUL success does not prove Shadow's audio format. |

The distinct required toolchain classes are: Python-only readers; Quantic MP3
decoding; vgmstream codecs; FFmpeg output; ZZZ Node/WASM helper; selective x86
REE; WolvenKit/.NET 10; FModelCLI/self-contained .NET 8 plus decompression;
NTE/.NET 10 dynamic loader; Endfield/.NET 10 selected-source reader. Use one
small functional fixture per distinct class in candidate CI, then native checks
with the actual installed games/packs available to the tester. Report missing
games/packs as **unavailable**, not synthetic/native passes. A game may share an
extractor yet need its own format probe, as the table specifies.

**Archived support:** `hito` and `honkai3` are absent from the active `GAMES`
tuple; [path persistence](../backend/game_paths.py) deliberately preserves their
old entries. Hito's Electron `app.asar` and Honkai Impact 3rd's legacy Python
Wwise/catalog reader remain source/history compatibility paths, not new active
installer tool requirements. Honkai's old catalog source is still named in
[game_catalogs](../backend/game_catalogs.py). Preserve existing settings/history;
do not advertise these as two additional active games or redistribute old data.

## .NET publication and build-only tools

Modern .NET and Windows .NET Framework are separate products. The current NTE
and Endfield paths use `dotnet build` and later `dotnet <reader.dll>` but check
for an SDK both times. A runtime alone is therefore insufficient **under the
current implementation**, although ordinary execution of a suitable published
assembly needs no SDK. [Microsoft installation guidance](https://learn.microsoft.com/en-us/dotnet/core/install/windows)
distinguishes SDK, .NET Runtime, Desktop Runtime and ASP.NET Runtime. Record the
runtime actually needed by each CLI; do not tell every user to install all three.
Its Windows support table is narrower than an executable merely starting on an
older OS, and must be rechecked for the exact chosen release/Windows edition.

[Microsoft single-file guidance](https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview)
makes single-file and self-contained separate settings. R19 should first publish
owned net10 readers as `win-x64` self-contained directories with exact runtime
pack versions and notices. A single-file optimization remains optional:
native DLLs may remain external or extract to `%TEMP%/.net`, and path-based
assembly loading can break. NTE deliberately loads a physical UEExtractor DLL;
neither trimming nor packing it blindly into one file is justified. Capture
the selected [.NET runtime license and third-party notices](https://github.com/dotnet/runtime/tree/main)
and NuGet package hashes/licenses, then test clean execution and cancellation.

| Build/development component | Disposition and unresolved selection |
| --- | --- |
| PyInstaller (not currently in project manifests) | **System prerequisite on Windows x64 build host**; selected direction is `onedir`. Pin a version, bootloader/hooks provenance and package hashes before R19 implementation. [Official licensing](https://pyinstaller.org/en/stable/license.html) describes GPL with the bootloader exception and limited Apache files; [operating model](https://pyinstaller.org/en/stable/operating-mode.html) includes the active Python interpreter and requires explicit hidden imports/resources when analysis cannot find them. The exception does not waive dependency licenses. No PyInstaller output was produced here. |
| Inno Setup (not currently selected/pinned in build scripts) | **System prerequisite on Windows build host** for R20, with installer runtime code in the generated setup artifact. Preserve selected-version [Inno license](https://github.com/jrsoftware/issrc/blob/main/license.txt) notices/conditions. [Upstream](https://jrsoftware.org/isinfo.php) supports per-user installs and x64/ARM64 targeting, but that does not establish toolkit ARM64 support. R18 selects no installer version or signing key. |
| .NET 10 SDK; .NET Framework compiler; optional .NET 8 SDK for rebuilding FModelCLI | **System prerequisite on build hosts only** for game-reader builds in the proposed delivery. Pin SDK/compiler versions and NuGet/source closure; game builds are not end-user setup work. A published self-contained reader includes runtime files but no SDK. Existing PRAGMATA/NTE/Endfield runtime compiler/SDK requirements must be removed with functional proof or retained as an explicit blocked game gate. Separately, prefer precompiling the owned launcher interop shim, or declare/probe its exact Windows PowerShell/.NET Framework `Add-Type` behavior; that current path is not compiler-free. |
| Git, npm/pip, archive tooling, Windows PowerShell, hosted CI actions | **System prerequisite on development/build hosts**. Current packaging invokes git archive, tar and PowerShell Compress-Archive; release machinery uses GitHub-hosted Actions, Node 24/Python 3.12 and .NET 10.x. Pinning SDK major/minor is not exact build provenance. Installer operation must not require Git, tar, pip, npm or CI tooling on the user's PC. |
| C/C++/Rust/Fortran/Go toolchains | **System prerequisite only when a reviewed build-host source build requires them**. They are implied by native package implementations, not current end-user prerequisites when valid wheels/tools are available. Binary-only closure must fail if a needed wheel is unavailable; do not silently install Build Tools. Exact compiler/CRT provenance is part of any rebuilt native binary. |
| Playwright engines, synthetic fixtures, lint/typecheck/test tooling | **System prerequisite on development/CI hosts only**. Current [CI](../.github/workflows/ci-release.yml) compiles the owned NTE bridge and uses synthetic services for package checks; it does not prove clean-PC OCR or every extractor. Preserve supported-host native acceptance outside that synthetic gate. |

## R19 acceptance inputs and remaining uncertainty

R18 supplies explicit decisions and closure gates, not a claim that packaging is
already possible for every tool under resolved terms. The installer must expose
actionable missing-system/tool/pack states without removing declared supported
languages or changing accounts/game installations.

Before calling an R19 candidate complete:

1. Resolve P1/J1/M1/V1/F1/G1 for the **actual distributed files**. Produce an
   artifact manifest with version, upstream/source revision, archive and file
   hashes, architecture, license/NOTICE/source-delivery mapping, permitted
   acquisition mode and deterministic executable/resource path. Keep game data,
   local metadata values and protected storage out of it.
2. Use the selected Windows x64 PyInstaller directory build and prebuilt game
   helpers. Prove no end-user Python, Node/npm installation, .NET SDK, NuGet
   restore, development compiler or Build Tools dependency. The current launcher
   uses PowerShell `Add-Type`; either precompile its owned shim or explicitly
   declare and prove that Windows-provided behavior on the selected image.
   No game-reader compilation is allowed on the user's PC. App-local Node can be bundled
   where still needed. A declared .NET runtime/system prerequisite must have
   an exact functional probe and official recovery instructions. Unresolved REE
   distribution rights cannot be hidden by a successful core startup.
3. Run each distinct toolchain probe above from an extracted artifact on clean
   Windows, with recorded OS edition/build, CPU architecture, runtime/CRT,
   Snipping Tool version/file hashes, game patch/pack availability and evidence
   classification. Test missing/corrupt/wrong-architecture native dependencies,
   blocked downloads, offline reuse, paths with spaces/Unicode, cancellation,
   resource loading, helper isolation and one exact original-voice output per
   distinct codec path. Hosted synthetic format tests and absent-pack schema
   tests remain separate from native playback.
4. Verify static frontend equivalence separately: ordinary-browser/extension
   behavior, current origin/storage, routes/API/WebSockets, OCR workers/WASM,
   service-worker/cache updates and lifecycle must match the host contract.
   Keeping the current frontend is a valid adapter until that evidence exists.
5. Follow clean-main release/audit/hosted candidate procedures; downloaded
   checksums and JSON provenance are different from Authenticode signatures or
   cryptographic build attestations. No installer build, signing or release is
   authorized by this research result.

The largest open issues are the maintained CPython 3.12 Windows binary supplier,
exact Windows wheel/native license closure, Snipping Tool prerequisite coverage,
GPL helper integration/source obligations, REE modified-binary rights, Oodle
redistribution terms, distribution-specific FFmpeg obligations and removing
NTE/Endfield/PRAGMATA user compilation. Native Windows validation, tool archives,
real voice packs and a completed static-host spike remain **unavailable in this
study**. None is converted into a pass by documentation review.
