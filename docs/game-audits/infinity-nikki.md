# Infinity Nikki: official-source discovery

Audited November 17, 2026. Implementation ticket:
[#145](https://github.com/Firebird55/Game-immersion-toolkit/issues/145).
This is an incomplete new integration. The discovery reader follows current
official regional launcher pointers and the Global anonymous SDK's base/hotfix
manifest pointers; it does not yet prepare game dialogue on PC or Android.
No game-data playback, installed-pack validation, full-story
denominator or autonomous game update has passed for this game.

## Official regions and language evidence

The publisher's [Global homepage](https://infinitynikki.infoldgames.com/en/home)
and [mainland China homepage](https://infinitynikki.nuanpaper.com/home) expose
their current Windows launcher links in the website's `__NEXT_DATA__`
`props.pageProps.pageData.page.windowsUrl` field. Global points directly to
the publisher's `x6oversea-game-package.infoldgames.com` CDN. Mainland links
through `ays.cn` to `x6cn-game-package.papegames.com`; the reader checks every
redirect before following it. The separate mainland Android download pointer
uses `x6cn-game-apk.papegames.com`.

The Global [publisher Steam language matrix](https://store.steampowered.com/app/3164330/Infinity_Nikki/)
lists English, French, Italian, German, Indonesian, Japanese, Thai, Simplified
Chinese, Traditional Chinese, Brazilian Portuguese, Latin American Spanish and
Korean for interface/subtitles. Full audio is listed for English, Japanese and
Simplified Chinese. The original Global hotfix descriptor independently lists
`VOICE_EN`, `VOICE_JA` and `VOICE_ZH` story/event resource groups. This establishes
the original pack-family names, not individual dialogue/audio bindings or
playback. Mainland voice/resource inventories still need independent
verification; the Global matrix cannot rule out additional regional content.

The publisher's [mainland launch FAQ](https://infinitynikki.nuanpaper.com/news/76)
confirms PC, Android, iOS and PS5 editions and separate PC/Android packages.
The [Version 2.8 update guide](https://infinitynikki.infoldgames.com/en/news/559)
distinguishes launcher pre-download and mobile partial-resource updates. These
platforms cannot be assumed to use interchangeable containers or manifests.

## What discovery currently proves

`backend/infinity_nikki_release.py` reads the exact bounded publisher website
field, rejects duplicate metadata, and follows changed launcher filenames without
a version allowlist. It rejects foreign, mixed-region and unsafe redirects.
It does not execute downloaded launcher or game code. The current observation
is launcher 1.3.1, which is a launcher version, not a game-resource generation.

Static inspection of bounded official installer ranges found a non-solid NSIS
archive with independent Deflate members. One complete 6,849,415-byte compressed
Global `xstarter.exe` member decoded to 10,816,688 bytes with exact Deflate EOF
and size bounds. Windows validated the complete extracted PE's Authenticode
signature from Suzhou Nikki Co., Ltd. The extracted file's SHA-256 is
`3a64a573b6d64abc625ba894fe68960a05e0dcbfe8e23f5c97a1ec53887cebff`.
This authenticates that component; it is not a whole-installer hash check.
No client code was executed.

The signed component contains updater paths including
`/v1/accessories/gameconfig/patchlist`, `checklauncherpkgupdate` and `parameter`,
and `/v1/user/resource_entry`. Its encoded `common.json` resource was decoded as
data after inspecting the complete 358,576-byte `libnetwork.dll` member, also
with a valid publisher Authenticode signature. The config cipher derives from
the launcher's own identity resource; the owned decoder requires no hardcoded
publisher key or protected key cache. This static discovery does not execute
client code.

The decoded Global production host is `https://passport.infoldgames.com`, with
independent test and preproduction hosts excluded from production discovery.
The normal patch-list request uses POST with `channel`, `region` and `env`;
launcher-package checks also include launcher identifiers and version. The SDK
transport adds application metadata, a form signature and encoded payload. The
owned reader reproduces the timestamp/identity-derived DES/AES, ECB/CBC and
HEX/Base64 transport choices. Its live anonymous request passed with `code: 0`
and a successfully decoded response. No account, installed game, community key,
protected key cache or real device diagnostics were used. Earlier partial
transport probes returning `args_error` are superseded by this successful test.

The response selected base manifest `PC_Smallest_Version_2828_O.json` and hotfix
`BuildVersion_2872.24.json` on separate original Global CDNs. The 629-byte base
manifest names a 1,093,871,896-byte original 7z bootstrap, with its 32-character
MD5 and an extraction-space field. The 9,806-byte hotfix descriptor confirms
IoStore and CMS, Windows, Region 1 / Channel 3 / Role 0, and base/default version
2872. These are source observations, not a whole-current-story count. No game
archive body was downloaded. The 7z's size and extraction hint are not a
selected-dialogue size plan.

The owned bootstrap planner now reads only PE/NSIS metadata first and reports
the exact selected launcher member's transfer bytes before downloading it.
All ranges bind to one strong publisher response validator. Its data-only
Unicode NSIS/Deflate and Qt resource readers reproduced the exact original
component and config from the privately retained official source ranges, without
7-Zip, capstone, pefile, client execution or fixed link addresses. Format details
were checked against the upstream [NSIS structures](https://github.com/NSIS-Dev/nsis/blob/master/Source/exehead/fileform.h).
The parser's structural checks do not independently verify Authenticode; the
separate native signature observation above remains distinct.

Cold HTTP orchestration and native Android acceptance still need end-to-end
verification on both runtimes, followed by original bootstrap/hotfix inventories,
actual text/voice package readers and required-file selection. The successful
metadata request does not prove full current-story, regional voice bindings or
availability of original recordings. No keys or client payloads belong in this
repository.

## Original game-bootstrap archive metadata

A bounded header-only probe of the publisher-selected 7z read 32 bytes of start
header, 39 bytes of next header and 7,045 bytes of encoded header. The source
CRCs and declared 70,370-byte decoded metadata length passed. The archive
structure follows the upstream [7z format](https://github.com/ip7z/7zip/blob/main/DOC/7zFormat.txt).
No game archive content stream was downloaded or executed.

The inventory has 466 entries, including 357 content files in two solid streams
of 616,011,349 and 477,853,431 compressed bytes. Its 13,536-byte
`HotUpdateBuildVersion.json` starts 58,797,864 decompressed bytes into the first
stream. It therefore cannot be treated as an independent 13,536-byte download.
The archive also contains localization, Lua, movie and IoStore containers, which
still require current inventory/format/binding work. The normal update source's
`Rel_2.8` bootstrap path is not proof of stale game coverage: the same current
descriptor explicitly contains a `Protect_2_11_2` resource group.

Preparation must offer **text only** and **text plus audio** on Android and PC.
Required-file selection, download size and local size must follow that choice;
text-only preparation must not silently obtain or retain voice packs. A solid
bootstrap archive is not sufficient evidence for a selective plan. The current
overall dialogue download/storage sizes remain unknown.

The upfront dialogue download/storage estimate remains **unknown**. Neither the
installer's size nor the publisher's whole-game free-space recommendation is a
valid substitute. A preparation plan must come from the current regional game
inventory, include required tables/bindings and selected original voice assets,
and account for cache, retained recordings and temporary extraction space.

## Presentation inventory and finite completion boundary

| Presentation | Primary evidence and remaining work |
| --- | --- |
| Story conversations and cinematic captions | The official update notices and sound-design report describe story dialogue and cutscenes. Original tables, authored display boundaries, speaker/voice ownership and capture regions remain unverified. |
| Graphic/text reading material inside dialogue and History | The [Version 2.3 notice](https://infinitynikki.infoldgames.com/en/news/447) describes independent layouts, a full-screen view and History review. A bottom-only subtitle crop cannot establish this coverage. Original text and voice state remain unverified. |
| In-world musical performances, boss performances and cinematic song/narration | The publisher's [Music Season sound-design report](https://infinitynikki.infoldgames.com/en/news/319) describes independently positioned NPC vocals and a final cinematic musical, including French pieces. Original performance language must be retained; a vocal's language is not necessarily the selected dialogue dub. Subtitle availability and source ownership remain unverified. |
| Choices, ambient captions, messages, documents and other active layouts | Inventory current official resources and representative online gameplay before marking these supported or absent. Do not infer silence from a missing pack or unresolved binding. |

Prioritize demonstrated current subtitle presentations. Unreferenced historical
or event resources are research inventory until current use is shown; they are
not automatically missing active dialogue, cut content or unvoiced lines.
Sounds with no on-screen subtitle do not block subtitle coverage.

## Remaining acceptance work

1. Complete fresh official Global/mainland bootstrap and current game
   inventories, original text/binding/voice containers, integrity fields and all
   voice locales. Global anonymous manifest-pointer discovery is implemented;
   independent mainland SDK acquisition and downstream resource inventories
   remain open.
2. Implement bounded manifest-based text-only versus text-plus-audio selection,
   size planning and download/deletion through the shared game-data manager on PC
   and fully independent Android. Preserve history, recordings and user settings
   when deleting prepared game data.
3. Validate Android-compatible owned readers and codec runtimes from actual
   format evidence; a Windows-only extractor or a community-prepared library
   does not meet the requirement.
4. Resolve authored text/translation/voice bindings for demonstrated current
   presentations and distinguish voiced, confirmed unvoiced, missing-pack and
   unknown entries. Verify all official dubs without inventing bindings.
5. Run changed-resource discovery and two consecutive official-generation
   preparation, interrupted-update retention, retry, offline restart and
   playback checks on PC and Android.
6. Register the completed game in the support matrix, generated language guides,
   installation/setup/capture/export surfaces and capability regressions. No
   supported-game registration or completed-game claim is made by this discovery
   stage. Keep #145 open until those acceptance conditions pass.
