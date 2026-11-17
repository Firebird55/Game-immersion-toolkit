# ZZZ on-device preparation and download planning

Audit date: November 17, 2026. Desktop source base
`8a85e9f4ee18232b56d7cc0399839b8c8279dbfe`, with bootstrap checkpoint
`6485905b506f1e17dfb9c209c365ed8d9bd58bab`. The accepted Android core examined is
`5ea69c705845a2f8c28a7f3e74b4aafcf65e9e79`. Later provider/UI work is separate
until its own source, runtime and device checks pass.

**Independent official-source ZZZ preparation on Android is not implemented.**
The accepted Android `packaging/android/app/build.gradle` lists 45 portable
prepared-library/account modules. It includes matching, storage and prepared
MP3/WAV playback; it does not package the ZZZ publisher preparation/export path.
A desktop library import cannot satisfy the independent-download requirement.

## Existing stages and exact portability boundaries

| Stage | Existing source | Android requirement still open |
| --- | --- | --- |
| Official release, dispatch and inventories | `sophon_assets.release`, `zzz_hotfix.discover`, `hoyo_dispatch_metadata.load` | Package this provider closure and its TLS/decompression/crypto dependencies. Keep Global/CN source partitions, immutable initial provenance and final generation checks. |
| Original bootstrap TextAssets | `hoyo_bootstrap_assets.object_ranges` / `text_assets`, `hoyo_zzz_bootstrap.renew` | The metadata-only reader is standard Python. Its availability in a desktop checkout does not establish APK inclusion or an Android source run. |
| Unity/BLB dialogue, catalogs, comics and film tracks | `zzz_publisher._read_catalogue`, `prebuilt_node_reader.production_zzz_reader`, `ZzzReader.publisher_command` | Supply an explicit Android runtime for the frozen reader protocol, or a format-equivalent owned adapter. The current Node subprocess/`node:fs` protocol is not a WebView or Python module. |
| Block decompression and hashing | Frozen `galgame-perform` reader, source-built `ooz` WASM and `xxhash-wasm` | Bind the actual Android executor, WASM/native dependencies, notices, preferred source and build provenance. Desktop manifests do not authorize an Android build. |
| PCK/Wwise/event/bus/media ownership | `honkai_assets`, `zzz_publisher_cinematics`, `zzz_voice_layers`, `zzz_bus_routing` | Much is standard Python plus locked FlexBuffers. Package the import closure without accidentally invoking another game's installer. Preserve source kind, bank/language, full-media, player and bus guards. |
| Original WEM decoding and MP3 output | `VoiceAssets.extract` / `extract_batch`, `media_tools`, `native_codecs` | Replace the present vgmstream-to-WAV-to-FFmpeg subprocess adapter with the verified Android codec service. Verify original WEM/whole-context decoding and MP3 output on the actual ABI. Existing prepared playback is a separate capability. |
| Update/storage/history | Source descriptors, prepared library writer and retained original audio bindings | Wire app-private roots and the shared Android game-data service. Failed download, validation or publication must retain the accepted generation and saved recordings. |
| Gateway key and protocol inputs | Official TextAssets plus the new pure-Python native data locator and bounded official-server protocol negotiation | The current Global/CN production route works without initial/community/protected key inputs. Package this closure and verify it on Android; original historical key-rotation acceptance is still separate. |

The accepted Android dependency lock has the prepared/account stack, including
Pydantic, RapidFuzz, OpenCC and HTTPX. It does not contain the source provider's
`zstandard`, Brotli, PyCryptodome or FlexBuffers runtime. Their Android artifacts,
import closure and source notices require verification; adding package names is
not native ABI evidence. `node_tools.ARCHIVES` and the codec host resolvers have
desktop targets, with no accepted Android resource contract. A Linux ARM64
selection must not be reported as Android/Bionic support.

The official Windows data route can remain a data source on Android: its
`StandaloneWindows64` inventory and Wwise packages describe data, and no game
code needs to execute. Changing these paths to guessed Android equivalents
would introduce an unproved source. The app must execute only its own verified
reader/codec software.

Memory acceptance also remains open. `zzz_hotfix.CheckedBase.read` currently
materializes and checks an entire base file; `_verified_base` can retain four
files, each bounded at 256 MiB. The Node reader reads complete staged buffers,
and the preparation path builds complete record lists/JSON. One retained real
Japanese prepared payload is approximately 254 MB of generated JSON. That is
neither a download estimate nor Android peak-memory evidence. A mobile adapter
needs bounded staging, record publication and measured memory acceptance.

## Manifest-driven preflight contract

Download and Delete belong to the shared game-data service. The ZZZ provider
must expose a source-bound plan before bulk transfer, using the same edition,
study/translation locales, original object selections and audio policy as
preparation. An unknown amount must remain unknown; it cannot appear as zero.

1. Resolve the official release and declared manifest sizes. Small discovery
   traffic and any required planning metadata must be accounted for separately.
   Pin the plan to the publisher fingerprint, manifest identities and selected
   locales. If detailed selection requires unacquired catalogs, return a
   declared complete-container upper bound or a metadata-only plan with its
   own bound. Do not silently download catalogs to obtain a purportedly free
   estimate.
2. Use the actual catalog/design plans to select bootstrap ranges, TextMaps,
   presentation roots/configuration, scenes, comics, film tracks and voice
   directory/registry dependencies. Full selected-voice offline preparation
   must also include original ordinary recordings and required film bank/media
   dependencies. A text/index-ready state with deferred audio is not a complete
   offline-audio state.
3. For a `sophon_assets.File`, map every selected range to its original complete
   transport chunks. Sum each unique chunk's declared **compressed** size for
   nominal network payload and **expanded** size for the retained cache. Reuse
   a chunk only after size/hash validation. Deduplicate across ranges, packages,
   selected locales and editions only where their own manifests name the same
   verified content.
4. For `zzz_hotfix.File`, any first range read downloads and checks the whole
   publisher file. Charge its whole `fileSize`, not its requested range or the
   synthetic 8 MiB access windows exposed by `.chunks`. For `CheckedBase`, unwrap
   `.asset` and include all original Sophon chunks needed for the whole-file
   check. Its access windows are also not transport chunks.
5. Preserve these distinctions in both estimates and progress. An observed
   139,083-byte recording required a 916,490-byte compressed Sophon chunk; an
   observed Korean patch container required 134,016,456 bytes even for metadata
   access. These are retained examples, not future constants or per-language
   totals. Shared SFX dependencies stay distinct from selected voice media.
6. Report nominal new network payload, new retained cache bytes, existing
   verified bytes, generated catalog/index bytes and peak additional staging
   space separately. Include pending transfers, prepared-generation publication
   and bounded decoder/WAV/MP3 scratch space. Codec size/duration uncertainty
   needs an explicit upper bound. Retries are visible actual traffic, rather
   than pretending they are newly required source objects.
7. Compute used bytes from owned on-device files with shared-object ownership
   accounted for. A per-game total must not double-count immutable shared
   runtime software or a content-addressed object shared with another retained
   generation. Delete removes only the selected game's owned data under the
   shared service's policy; it must preserve transcripts, saved recordings,
   account state and still-referenced shared objects.
8. Recheck the live publisher pointer before publication. If the generation or
   selection changes, invalidate/replan the candidate and preserve the previous
   accepted generation. The update must not require a new community extraction,
   desktop import or toolkit update for ordinary unchanged formats.

An exact plan requires resolved original selections and verified cache state.
An upper-bound plan must label that bound and enforce it. If required identities
or source sizes are missing, preparation is unavailable with a retryable source
state; no full-download button should advertise an invented amount.

## Required acceptance before reporting Android readiness

Run the real publisher provider on Android with an empty app cache, no desktop
import, no game installation and community requests blocked after immutable
initial input. Exercise both editions, all four spoken dubs and Chinese script
selection, ordinary and supported film recordings, and cold codec output. Then
prove an upstream-only generation change, interrupted transfer/publication,
retained old/new history after app restart, selected-game deletion and accurate
planned/actual byte accounting. Existing desktop source controls and prepared
Android matching/playback remain useful evidence for their own boundaries.
