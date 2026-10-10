# Third-party notices

The Firebird55 license covers original shared code only. Dependencies retain their own terms: React/React DOM (Meta, MIT), Base UI (MUI, MIT), Lucide (ISC), TypeScript (Microsoft, Apache-2.0). Package metadata and dependency distributions contain their upstream notices. Builds and consumers must retain notices for dependencies they bundle.

The component uses documented Lexirise interfaces; this repository does not redistribute Lexirise's website bundles, account data or dictionaries. Public upstream bundles inspected by the compatibility watcher remain ignored local review material.

## Toolkit assets and tools

- FireRedVAD ONNX model and CMVN data: FireRedTeam, Apache-2.0. Full license, source revision and file hashes are in assets/fireredvad. These terms remain independent of the project license.
- Original PT launcher icon and favicon: generated from project-owned geometric shapes. Covered by LICENSE.
- shadcn-derived styling: retain styles/SHADCN-LICENSE.md (MIT).
- oneocr's Python wrapper is MIT. Windows Snipping Tool's proprietary OCR DLL/model files are read from the user's installed software during setup; they are not redistributed here.
- FFmpeg downloaded through imageio-ffmpeg, FModelCLI (GPL-3.0), WolvenKit and game-extraction dependencies remain separate installed/downloaded tools with their own license notices. They are not included in toolkit source or installer ZIPs; retain their notices when using or distributing them independently.
- scripts/extract_voice_links.mjs optionally loads a separately downloaded GalScript reader from simon300000/zenless-voice. That source is not vendored or relicensed here; obtain permission under its upstream terms before redistribution.
- Game scripts, subtitle catalogs, audio, recordings and extracted archives belong to their respective publishers and remain user-local. The project license grants no rights over game content.

JavaScript and Python dependencies retain their distribution licenses. The locked manifests identify exact dependencies; installed packages carry their upstream notices. Do not describe all repository or runtime content as covered by the Firebird55 license.
