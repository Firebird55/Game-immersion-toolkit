# Third-party notices

## Live-service dialogue sources

Reviewed November 9, 2026. Each game's publisher supplies the original recordings
and translations. Game data and prepared language libraries stay private.
Source and tool licenses apply to the respective software. The per-game inventory
records the regional release, source checks and coverage limits. [Source inventory](docs/live-service-sources.md) · [Game credits and source roles](README.md#text-voices-and-upstream-projects)

| Upstream | Terms and use |
| --- | --- |
| Dimbreath's AnimeGameData, TurnBasedGameData and ZenlessData, rmxlinux/EndfieldData, Waifus-Grace/NTE_Assets, Arikatsu/WutheringWaves_Data | These mirrors expose game-derived tables. The toolkit reads selected records for local preparation or an independent comparison. A redistribution license for the publisher's text or recordings was not verified from these mirrors. |
| simon300000/zenless-voice, Hiro420/ZZZ_TextMap, EIHRTeam/EndfieldStudio, Tobiichi-Origuchi/nte_patcher | The scene reader and these format references declare MIT. Keep the applicable upstream notices with any distributed code. [Zenless scene reader](https://github.com/simon300000/zenless-voice/blob/bb2b9790d2d45a5c662c36cd9f046d05893d0ef4/LICENSE) · [Zenless TextMap](https://github.com/Hiro420/ZZZ_TextMap) · [EndfieldStudio](https://github.com/EIHRTeam/EndfieldStudio) · [NTE Patcher](https://github.com/Tobiichi-Origuchi/nte_patcher) |
| yarik0chka/wuwa-keys, Yumeo0/mornye-tools, 555me/NTE-usmap, kuaichu/game-cdn-archive | Private preparation and source checks use the relevant archive parameters, type schema, catalogue format or historical release references. GitHub did not identify a repository-wide SPDX license for these projects at review. [wuwa-keys](https://github.com/yarik0chka/wuwa-keys) · [mornye-tools](https://github.com/Yumeo0/mornye-tools) · [NTE-usmap](https://github.com/555me/NTE-usmap) · [game-cdn-archive](https://github.com/kuaichu/game-cdn-archive) |
| BlueHeisenberg/SCSKiller | The repository declares GPL-3.0. NTE preparation checks whether its public metadata source supplies a compatible entry for the selected archive. [SCSKiller](https://github.com/BlueHeisenberg/SCSKiller) |
| SolicenTEAM/UEExtractor, FabianFG/CUE4Parse | The installed Unreal readers use UEExtractor (MIT) and CUE4Parse (Apache-2.0). The component inventory records the pinned assemblies, transitive notices and checksums. [Managed component inventory](packaging/game-readers/managed-components.json) |
| vgmstream, FFmpeg | Original-audio decoding and conversion follow the included component notices. vgmstream lists its component terms in COPYING. FFmpeg's terms depend on the build configuration. [vgmstream COPYING](https://github.com/vgmstream/vgmstream/blob/master/COPYING) · [FFmpeg licensing](https://ffmpeg.org/legal.html) · [Desktop runtime inventory](docs/r18-runtime-components.md) |

The Hugging Face Zenless voice dataset was an optional historical comparison.
Desktop voice retrieval uses the publisher's original game packages. [Dataset card](https://huggingface.co/datasets/simon3000/zenless-voice)

## Portable desktop access

Native desktop construction uses pinned python-xlib 0.33 on Linux
([LGPL-2.1-or-later](https://github.com/python-xlib/python-xlib/blob/master/LICENSE)),
and PyObjC core/Cocoa/Quartz 13.0 on macOS
([MIT](https://github.com/ronaldoussoren/pyobjc/blob/main/pyobjc-core/LICENSE.txt)).
Credential storage selects the host's existing macOS Keychain or Linux Secret
Service through keyring 25.7.0 (MIT); Linux additionally uses SecretStorage 3.5.0
(BSD-3-Clause) and jeepney 0.9.0 (MIT). A missing or locked host credential service
is an explicit unavailable state; these dependencies do not introduce a plaintext
credential fallback. Windows continues to use the operating system's DPAPI.

The native builder retains the exact installed license/notice files for these
packages and their locked transitive dependencies, including cryptography's
Apache-2.0/BSD-3-Clause and its bundled OpenSSL notice. Candidate construction is
not an assertion that redistribution review of every collected native file is
complete. Source references: [keyring](https://pypi.org/project/keyring/25.7.0/),
[SecretStorage](https://pypi.org/project/SecretStorage/3.5.0/),
[jeepney](https://pypi.org/project/jeepney/0.9.0/),
[cryptography](https://pypi.org/project/cryptography/50.0.2/).

The Firebird55 license covers original project code only. Dependencies retain their own terms: React/React DOM (Meta, MIT), Base UI (MUI, MIT), Lucide (ISC), TypeScript (Microsoft, Apache-2.0). Package metadata and dependency distributions contain their upstream notices. Builds and consumers must retain notices for dependencies they bundle.

The component uses documented Lexirise interfaces; this repository does not redistribute Lexirise's website bundles, account data or dictionaries. Public upstream bundles inspected by the compatibility watcher remain ignored local review material.

## Toolkit assets and tools

- The Windows gateway socket cleanup in `backend/gateway_loop.py` adapts
  CPython 3.12's `Lib/asyncio/proactor_events.py` (Python Software Foundation,
  PSF-2.0). The change handles WSAECONNRESET from socket shutdown before normal
  close and server detachment. Full upstream terms are retained in
  [LICENSE.cpython.txt](packaging/runtime-bundle/python-notices/LICENSE.cpython.txt)
  and the native Python notices; this adapted code retains those terms.
- Desktop status/tray uses PySide6-Essentials and shiboken6 6.12.0 from Qt.
  Qt Core, GUI and Widgets are dynamically loaded; the toolkit does not claim
  ownership of Qt. The applicable Qt/PySide LGPLv3/GPL/commercial terms and
  selected native plugins must be reviewed against the exact frozen output.
  Candidate construction retains the wheel's actual notices and metadata;
  it does not establish an open-source redistribution grant for every collected
  file. Corresponding source/notice delivery is tracked in
  [native delivery acceptance](docs/desktop-native-acceptance-plan.md).
- Selective RE archive decompression uses zstandard 0.25.0 (Gregory Szorc,
  BSD-3-Clause); its bundled Zstandard implementation retains its own BSD
  notices. The complete installed distribution notices are retained in each
  constructed native candidate under THIRD_PARTY/zstandard.

- Local network interface discovery uses psutil 7.2.2 (BSD-3-Clause), copyright
  2009 Jay Loden, Dave Daeschler and Giampaolo Rodola. The full notice is retained
  in packaging/licenses/psutil-LICENSE.txt and in the collected Python distribution.

- FireRedVAD ONNX model and CMVN data: FireRedTeam, Apache-2.0. Full license, source revision and file hashes are in assets/fireredvad. These terms remain independent of the project license.
- Original PT launcher icon and favicon: generated from project-owned geometric shapes. Covered by LICENSE.
- shadcn-derived styling: retain styles/SHADCN-LICENSE.md (MIT).
- Geist and Geist Mono fonts: Copyright 2024 The Geist Project Authors, SIL Open Font License 1.1. Both families use the identical full notice in styles/GEIST-OFL.txt, also included in release THIRD_PARTY_LICENSES.txt. The notices were verified against google/fonts revision bd8f81ddb5c74d5c8897b36ad88b440266245103 (ofl/geist/OFL.txt and ofl/geistmono/OFL.txt). The font license remains independent of the project license.
- oneocr's Python wrapper is MIT. Windows Snipping Tool's proprietary OCR DLL/model files are read from the user's installed software during setup; they are not redistributed here.
- windows-capture (MIT) supplies Windows Graphics Capture for unfocused games. Its opencv-python dependency uses Apache-2.0 and includes upstream notices in its installed distribution. Both are installed from the locked Python manifest.
- FFmpeg downloaded through imageio-ffmpeg, FModelCLI (GPL-3.0), WolvenKit and game-extraction dependencies remain separate installed/downloaded tools with their own license notices. They are not included in toolkit source or installer ZIPs; retain their notices when using or distributing them independently.

The first private R19 extracted-runtime experiment collected one pinned
FFmpeg binary with notices; it is excluded from published source ZIPs and is not
approved for distribution. Its [exact-artifact review](docs/r19-codec-artifact-review.md)
identifies the GPLv3 build separately from the imageio wrapper's BSD license and
rejects the old snapshot for production pending a maintained replacement and
complete source/notice delivery. The native desktop packaging scripts now
construct explicitly marked private installer candidates; no production R19
installer is accepted by this construction step.

The subsequent [Xiph FLAC selection](docs/r19-codec-replacement.md) builds version
1.5.0 from its exact official source with Ogg and external pthreads disabled.
Its GPL-2.0-or-later CLI and BSD-3-Clause reference library retain GPL/LGPL/Xiph
texts, authorship and file notices, with a complete verified source/build kit.
The [frozen experiment](docs/r19-frozen-xiph.md) now collects that exact CLI/DLL,
notices and source kit. It is not published as a production binary;
Windows/CRT and production source-delivery gates stay open.
Both the [historical source kit](third_party/codecs/xiph-flac-1.5.0/README.md) and
the [new kit with scoped GPL build recipes](third_party/codecs/xiph-flac-1.5.0-gpl-recipes/README.md)
are retained in Git. On 2026-10-30 the owner approved an additional
GPL-2.0-or-later route for exactly the two codec build scripts and input policy,
without the extra visible-credit/link condition on that route. The general
project license and third-party terms remain unchanged; see the
[scoped grant](packaging/codecs/FLAC-BUILD-RECIPES-LICENSE.txt) and
[rights and maintenance review](docs/r19-xiph-distribution-review.md).
- The ZZZ scene adapters use the pinned GalScript reader from simon300000/zenless-voice (MIT, copyright 2024 simon3000). Source setup retains its full license in the local tool cache; desktop bundles retain the original source, precompiled reader, full license and exact source archive. ooz-wasm is GPL-3.0-or-later and is rebuilt from preferred source with the pinned Emscripten toolchain; xxhash-wasm is MIT. Their complete terms, preferred sources and rebuild recipe are retained in the immutable ZZZ resources. See [the exact reader inputs and source-build contract](packaging/zzz-reader/README.md). These components are not relabeled as original toolkit code, and no game catalog or recording is bundled.
- vgmstream is downloaded from its official r2117 Windows x64 release with full COPYING and dependency notices retained. The REE unpacker is downloaded separately from Ekey/REE.PAK.Tool; its upstream terms apply, and the project license grants no redistribution rights over that tool. Tool downloads are checksum verified and excluded from source/installer bundles.
- Game scripts, subtitle catalogs, audio, recordings and extracted archives belong to their respective publishers and remain user-local. The project license grants no rights over game content.
- Mobile OCR: pinned Tesseract.js/Tesseract.js-core 7.0.0 (Apache-2.0) and naptha/tessdata English, Simplified Chinese and Traditional Chinese models (Apache-2.0), obtained through pinned @tesseract.js-data packages. The generated Pages allowlist includes the runtime's distribution notices, Apache license, model provenance and checksums. Model weights retain the upstream license independently of the npm wrapper's MIT metadata. Authored browser test captions and generated tone/video fixtures contain no game content and are covered by LICENSE.
- Chinese capture matching: opencc-python-reimplemented 0.1.7 (Apache-2.0) and OpenCC-JS 1.4.2 (MIT implementation, Apache-2.0 dictionary derivatives). Conversion runs locally on lookup keys; official transcript text is preserved. The browser distribution includes OpenCC-JS and dictionary notices and licenses.
- Mobile QR pairing: qrcode-generator 2.0.4 (Kazuhiko Arase, MIT), jsQR 1.4.0 (Apache-2.0), and fflate 0.8.3 (MIT). Pinned runtime assets and complete notices are self-hosted in the Pages allowlist. Camera frames and pairing messages are processed on the devices.
- NTE uses a separately downloaded UEExtractor v1.0.8.7 (SolicenTEAM, MIT; copyright 2024 Denis Solicen/Ambi) with its full notice saved beside the verified tool. Its CUE4Parse and decompression dependencies retain their own upstream terms. The toolkit-owned C# bridge calls that tool; no upstream binaries or source are bundled as project-owned code. Honkai's reviewed public 4.7 catalog is downloaded only into a private runtime cache from nairieberry/HonkaiImpactData; it is game-derived content and is not included in source or installers.

JavaScript and Python dependencies retain their distribution licenses. The locked manifests identify exact dependencies; installed packages carry their upstream notices. Do not describe all repository or runtime content as covered by the Firebird55 license.

Toolkit release bundles include THIRD_PARTY_LICENSES.txt with the complete license/notice files from the locked JavaScript dependency installation used for the build. This includes libraries bundled into the prebuilt frontend.


Endfield game tools download pinned MIT-licensed reader sources from
[EIHRTeam/EndfieldStudio](https://github.com/EIHRTeam/EndfieldStudio). Their license
notice remains beside the locally built reader. Sources, native binaries,
archive metadata and game data stay in ignored local tool storage and are not
bundled in the repository, release ZIP or public mobile preview.

## Offline subtitle OCR

RapidOCR (`rapidocr-onnxruntime` 1.4.4) is Apache-2.0 licensed:
[source and license](https://github.com/RapidAI/RapidOCR),
[pinned distribution](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/).
Its bundled PP-OCRv4 detector/recognizer and PP-OCRv2 classifier originate from
[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), also Apache-2.0 licensed.
The pinned wheel includes these converted ONNX models; recognition makes no
network requests. Preserve both upstream licenses in packaged distribution
notices. Model hashes are recorded in `backend/ocr_engine.py` and must be included
in frozen runtime closure evidence. The supplied English screenshot corpus
validates this fallback; it does not establish coverage for every game locale.

RapidOCR depends on Pyclipper (MIT), Shapely (BSD-3-Clause, with GEOS LGPL-2.1
native libraries), ONNX Runtime (MIT), NumPy (BSD-3-Clause), Pillow (HPND),
PyYAML (MIT) and OpenCV (Apache-2.0, with bundled dependency notices). Their
distribution notices and native-library closure belong in packaged artifacts.

## Additional native game readers

The Fox readers retain the complete Atvaark, Google CityHash and kapuragu MIT
notices in `backend/fox_dialogue.py`. The Decima container reader uses format
research from Jayveer/Decima-Explorer and ShadelessFox/decima-workshop; its
MurmurHash3 arithmetic follows the public-domain algorithm. The Decima-Explorer
notice is retained below. Original game-owned decompression libraries are loaded
from the user's installation and are not redistributed.

Persona character mapping tables are downloaded separately from the pinned
Atlus Script Tools revision documented in the game audit. Their GPL-3.0 license
and source notice remain beside those tables in the private cache. Neither the
tables nor upstream executable code are bundled in the toolkit distribution.

The independently implemented Deus Ex readers reference the BIGFILE/CDRM/DRM
format research in Gibbed.CrystalDynamics and rrika/dxhr. They are not upstream
Gibbed tools. The Gibbed format-reference notice is retained below. Other game
container readers are described with their format references in the respective
source modules and game audits; these references confer no rights to game assets.

### Decima-Explorer — MIT License

Copyright (c) 2019 Jayveer Kathwadia

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Gibbed.CrystalDynamics — zlib License

Copyright (c) 2020 Rick (rick 'at' gibbed 'dot' us)

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would
   be appreciated but is not required.

2. Altered source versions must be plainly marked as such, and must not
   be misrepresented as being the original software.

3. This notice may not be removed or altered from any source
   distribution.
