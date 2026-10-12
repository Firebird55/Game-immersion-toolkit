# Third-party notices

The Firebird55 license covers original project code only. Dependencies retain their own terms: React/React DOM (Meta, MIT), Base UI (MUI, MIT), Lucide (ISC), TypeScript (Microsoft, Apache-2.0). Package metadata and dependency distributions contain their upstream notices. Builds and consumers must retain notices for dependencies they bundle.

The component uses documented Lexirise interfaces; this repository does not redistribute Lexirise's website bundles, account data or dictionaries. Public upstream bundles inspected by the compatibility watcher remain ignored local review material.

## Toolkit assets and tools

- FireRedVAD ONNX model and CMVN data: FireRedTeam, Apache-2.0. Full license, source revision and file hashes are in assets/fireredvad. These terms remain independent of the project license.
- Original PT launcher icon and favicon: generated from project-owned geometric shapes. Covered by LICENSE.
- shadcn-derived styling: retain styles/SHADCN-LICENSE.md (MIT).
- Geist and Geist Mono fonts: Copyright 2024 The Geist Project Authors, SIL Open Font License 1.1. Both families use the identical full notice in styles/GEIST-OFL.txt, also included in release THIRD_PARTY_LICENSES.txt. The notices were verified against google/fonts revision bd8f81ddb5c74d5c8897b36ad88b440266245103 (ofl/geist/OFL.txt and ofl/geistmono/OFL.txt). The font license remains independent of the project license.
- oneocr's Python wrapper is MIT. Windows Snipping Tool's proprietary OCR DLL/model files are read from the user's installed software during setup; they are not redistributed here.
- FFmpeg downloaded through imageio-ffmpeg, FModelCLI (GPL-3.0), WolvenKit and game-extraction dependencies remain separate installed/downloaded tools with their own license notices. They are not included in toolkit source or installer ZIPs; retain their notices when using or distributing them independently.
- scripts/extract_voice_links.mjs loads a separately downloaded GalScript reader from simon300000/zenless-voice (MIT, copyright 2024 simon3000). Setup retains its full license beside the pinned reader in the ignored local tool cache. Its ooz-wasm (GPL-3.0-or-later) and xxhash-wasm (MIT) dependencies retain their own notices. Neither game metadata nor the reader is bundled as original project code.
- vgmstream is downloaded from its official r2117 Windows x64 release with full COPYING and dependency notices retained. The REE unpacker is downloaded separately from Ekey/REE.PAK.Tool; its upstream terms apply, and the project license grants no redistribution rights over that tool. Tool downloads are checksum verified and excluded from source/installer bundles.
- Game scripts, subtitle catalogs, audio, recordings and extracted archives belong to their respective publishers and remain user-local. The project license grants no rights over game content.
- Mobile OCR: pinned Tesseract.js/Tesseract.js-core 7.0.0 (Apache-2.0) and naptha/tessdata English/Simplified Chinese models (Apache-2.0), obtained through pinned @tesseract.js-data packages. The generated Pages allowlist includes the runtime's distribution notices, Apache license, model provenance and checksums. Model weights retain the upstream license independently of the npm wrapper's MIT metadata. Authored browser test captions and generated tone/video fixtures contain no game content and are covered by LICENSE.
- Mobile QR pairing: qrcode-generator 2.0.4 (Kazuhiko Arase, MIT), jsQR 1.4.0 (Apache-2.0), and fflate 0.8.3 (MIT). Pinned runtime assets and complete notices are self-hosted in the Pages allowlist. Camera frames and pairing messages are processed on the devices.
- NTE uses a separately downloaded UEExtractor v1.0.8.7 (SolicenTEAM, MIT; copyright 2024 Denis Solicen/Ambi) with its full notice saved beside the verified tool. Its CUE4Parse and decompression dependencies retain their own upstream terms. The toolkit-owned C# bridge calls that tool; no upstream binaries or source are bundled as project-owned code. Honkai's reviewed public 4.7 catalog is downloaded only into a private runtime cache from nairieberry/HonkaiImpactData; it is game-derived content and is not included in source or installers.

JavaScript and Python dependencies retain their distribution licenses. The locked manifests identify exact dependencies; installed packages carry their upstream notices. Do not describe all repository or runtime content as covered by the Firebird55 license.

Toolkit release bundles include THIRD_PARTY_LICENSES.txt with the complete license/notice files from the locked JavaScript dependency installation used for the build. This includes libraries bundled into the prebuilt frontend.
