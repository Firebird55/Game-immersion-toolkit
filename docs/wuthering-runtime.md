# Wuthering Waves compiler-free archive runtime

Updated 2026-10-31. Wuthering Waves and NTE use the same owned archive helper,
app-local .NET runtime and exact managed CUE4Parse dependency inventory. A
complete desktop bundle needs no SDK, system .NET or native Oodle/zlib download.
This replaces the Wuthering adapter's FModelCLI acquisition path without changing
its authored dialogue or original-voice binding rules.

## Shared runtime and bounded operations

The [NTE runtime contract](nte-runtime.md) also supplies Wuthering's immutable
`helpers/nte` apphost and `toolchains/nte` dependencies. The existing helper and
resource builders produce both games' required runtime. The name of that shared
resource directory does not select a different preparation or release policy.
The [managed component lock](../packaging/game-readers/managed-components.json)
binds the same 30 embedded assemblies, exact supplier identities and complete
license/notice collection for both adapters.

The helper's `wuwa-list` and `wuwa-extract` operations construct CUE4Parse with
its Wuthering game-format setting and managed codec defaults. They permit the
existing four narrative/audio configuration tables, each supported locale's
MultiText base/shard prefix, and flat original voice entries. Arbitrary asset
export is not exposed. Extraction limits file count, individual size and total
bytes; output stays in private storage outside the installation and runtime.

Existing public archive metadata is selected against installed archive headers
and passed on bounded stdin, never command arguments or logs. Both base and
nonzero patch archive identifiers receive the installed-version keys. The
provider's winning entry supplies both the size and extracted bytes, preserving
patch priority when its enumeration contains duplicate paths. The authored
`RedirectDbIndex` continues to select localization shards; missing shards fail
preparation instead of producing placeholder text.

Index preparation and the shared playback service resolve the same verified
executable. Playback no longer tries a historical mutable tool-cache filename
inside a bundled installation. Wuthering batch selection uses its private
installed-file inventory and only selects a prefix when it exactly covers the
requested original recordings.

## Installed-file evidence

A private Windows x64 apphost probe ran the production Wuthering indexer with
an empty executable search path, system .NET discovery disabled and only the
pinned UEExtractor DLL in its dependency directory. No game was launched.

| Study locale | Emitted records | Installed original voice bindings |
| --- | ---: | ---: |
| English | 132,394 | 46,461 |
| Simplified Chinese | 134,024 | 46,293 |
| Traditional Chinese | 133,157 | 46,280 |
| Japanese | 132,463 | 0; pack absent |
| Korean | 132,261 | 0; pack absent |

The managed provider listed 93,609 external-source paths. Its PlotAudio and
English base MultiText extraction matched the existing extractor cache byte for
byte. The complete production run included patch localization shards, flow
actions, movie captions and readable records. Existing language-specific gender
rules, exact voice identities and unvoiced/unavailable/unknown distinctions were
retained. See [language coverage](wuthering-languages.md) and the
[presentation audit](game-audits/wuwa.md) for remaining dialogue format gaps.

An authored English recording and an authored Mandarin recording were extracted
and decoded through the maintained shared decoder at 48 kHz: respectively
123,658 and 182,891 samples. Both Chinese scripts resolved the same Mandarin
recording. Japanese/Korean playback remains unverified because those packs are
absent. The newly shared helper also repeated NTE's established authored Chinese
recording with byte-identical output.

Focused tests cover all official voice identifiers, 245-entry private metadata
requests, all existing translation locale filters, localization shard selection,
unsafe/overbroad selection rejection, installed inventory use, missing resources
and production voice-service dispatch for both games. These fixtures do not
claim native execution for absent packs or untested platforms.

## Remaining delivery work

The helper build currently targets Windows x64. Linux and macOS need native
apphosts, maintained .NET runtime resources and their own execution acceptance;
managed parser code alone is not proof of platform support. Final resources
must be rebuilt from the committed clean source and tested inside the assembled
desktop candidate. The private development probe's modified helper and dirty
source receipt are not release artifacts. Supplier review and native acceptance
remain attached to the final candidate. No game data, archive metadata,
recordings or personal installation paths are distributed.
