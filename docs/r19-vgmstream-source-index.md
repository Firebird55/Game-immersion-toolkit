# R19 vgmstream r2168 source-input index

Status: **deterministic review index; source/build/rights/native closure remains open**.
Observed 2026-10-31: [official numbered release r2168](https://github.com/vgmstream/vgmstream/releases/tag/r2168),
commit d9875b1fff307e4759dfb85e49e3d5e6fb196f7c. This follows the
[R18 V1 requirements](r18-runtime-components.md#game-tools-and-redistribution-decisions)
and the [negative FFmpeg artifact review](r19-codec-artifact-review.md).
It selects no runtime artifact and changes no source adapter, game/language,
installer, PR #59 or acceptance flag.

## Exact review inputs

The [structured index](r19-vgmstream-source-index.json) binds eight complete
original dependency archives, 49 original vgmstream build/support files,
40 original dependency build files, 24 named dependency notice/author texts
and the upstream core/dependency notices. All nine notice copies under
vgmstream's ext_libs/licenses match the corresponding original archive bytes.
This verifies those selected texts, not every incorporated copyright or license.

| Original archive | Bytes | SHA-256 |
| --- | ---: | --- |
| [celt-0.6.1.tar.gz](https://downloads.xiph.org/releases/celt/celt-0.6.1.tar.gz) | 422769 | a991dff4a9e0772ede0881d81cdc7ac559148c2194885cbdd534fe4af43779da |
| [celt-0.11.0.tar.gz](https://downloads.xiph.org/releases/celt/celt-0.11.0.tar.gz) | 464316 | c94d4d34f5a2caa1574b1a94869202cacd959b55f643a8bafe0660008acad9c3 |
| [ffmpeg-9.0.2.tar.xz](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz) | 12040788 | 8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e |
| [libogg-1.3.5.zip](https://downloads.xiph.org/releases/ogg/libogg-1.3.5.zip) | 665108 | fd4e5ba7e93b84b3ec41cdf01494cc586ef6e912b313dbab25512dd02665dfaf |
| [libvorbis-1.3.7.zip](https://downloads.xiph.org/releases/vorbis/libvorbis-1.3.7.zip) | 1924556 | 57c8bc92d2741934b8dc939af49c2639edc44b8879cba2ec14ad3189e2814582 |
| [mpg123-1.33.7.tar.bz2](https://www.mpg123.de/download/mpg123-1.33.7.tar.bz2) | 1126376 | 31d0e35a4ca567ec9b5ebda6c3062bb4435d6d3eacd6ef0d95cadd7854dc03ee |
| [opus-1.6.1.tar.gz](https://downloads.xiph.org/releases/opus/opus-1.6.1.tar.gz) | 10472813 | 6ffcb593207be92584df15b32466ed64bbec99109f007c82205f0194572411a1 |
| [speex-1.2.1.tar.gz](https://downloads.xiph.org/releases/speex/speex-1.2.1.tar.gz) | 1043278 | 4b44d4f2b38a370a2d98a78329fefc56a0cf93d1c1be70029217baae6628feea |

Hashes identify the downloaded HTTPS bytes; no signature-verification or
source-to-binary correspondence is inferred. SourceForge did not serve the
mpg123 review request; the same named version was obtained from the author's
mpg123.de download site and its COPYING matches vgmstream's retained notice.
The FFmpeg and Opus sources already retained in the earlier ignored review were
rehash-checked without another download.

The original commit-pinned vgmstream repository ZIP is 9,584,384 bytes, SHA-256
4c7579a58084556e60a120de29b8d765c6ad10d94e7e38bb5511f03bab5155e1.
It contains 18 prebuilt dependency DLLs and must not be described as source-only.
This step reused that existing review archive, extracted 1,163 unmodified
source/support files while excluding those 18 compiled inputs, and retained the
original dependency sources, recipes and notices under ignored review storage.
No native binary was newly acquired, compiled or executed. No source ZIP or
source-delivery service is published by this index.

## What the recipes establish

The exact [Windows dependency guide](https://github.com/vgmstream/vgmstream/blob/d9875b1fff307e4759dfb85e49e3d5e6fb196f7c/doc/BUILD-LIB.md),
FFmpeg option file, import definitions, project properties and original scripts
are indexed by raw byte length/hash; CRLF and BOM bytes are preserved.
The guide describes CELT symbol/configuration/libtool changes, Speex exports,
the combined Ogg/Vorbis/Vorbisfile DLL and static Opus inside the FFmpeg subtree.
Those are instructions, not receipts from rebuilding the supplied DLLs.

The general BUILD.md still names FFmpeg n5.1.2. The dependency guide, CMake tag
and retained notices identify 9.0.2; the contradiction is recorded explicitly.
Non-Windows CMake also selects a GPL/static FFmpeg configuration, while the
Windows path consumes shared dependency DLLs. Neither path establishes the
other's configuration or rights. The default full-solution initialization
acquires unrelated plugin SDKs; a CLI replay must select its actual closure.

The core COPYING is ISC. Actual CELT COPYING texts have three BSD-style
conditions despite the general guide's MIT shorthand. The original archive
notices and per-file terms remain authoritative. The toolkit's license and
the Xiph FLAC grant are unchanged; that grant still covers only its three
approved build inputs and is not reused for vgmstream.

## Smallest executable continuation and open gates

Prepare one isolated build-host replay of the FFmpeg 9.0.2 + Opus 1.6.1 dependency
subtree using the indexed original Windows instructions and fixed compiler,
SDK, MSYS2/NASM/make inputs. Retain actual flags, patches, original notices,
imports and output hashes; do not substitute the existing prebuilt DLLs.
Then reconcile the other dependency transformations and rebuild the existing
CLI with matching headers/import definitions. Any needed build adapter needs
its own applicable original terms; this index applies no new license grant.

Before collection, the following remain required:

- Independent supplying-source/build correspondence for every actual output,
  including CPU/CRT settings, user-property isolation and a closed input graph.
- File-level vendored decoder, static Opus and compiler-runtime notice/source
  mapping; the core license and nine notice matches are insufficient.
- Dependency servicing review, complete source delivery and durable canonical
  access beside any eventual binary, preserving required game codec coverage.
- Real authored-format decode, corrupt/missing/cancel/cleanup and DLL-origin
  probes, followed separately by Windows 11 25H2 ordinary-user acceptance.

The structured index contains explicit unresolved records for these gates.
Its canonical identity is
2d25a1919a5f6758fc541944b79b475c6ba4f6aef2e1e0c8d45244a18b69fe27.
This is an identity of input records, not an approval receipt. Full B2/B3 game
or voiced-export acceptance, production execution and r19_complete stay false.
PR #59 remains untouched and no installer or release is built.
