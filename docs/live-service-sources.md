# Live-service dialogue sources

Reviewed November 9, 2026. All six Windows readers support installed voice packages.
Without a game installation, desktop Setup supports Global and mainland China Genshin launcher releases, Global and mainland China Star Rail base and chapter voices, Global and mainland China Endfield narrative tables and voices, and Global and mainland China Wuthering Waves story tables and four dubs. For each game, the source audit also retrieved complete
sample recordings from a publisher update server. The two columns below let a
reader reproduce the online check and see which inputs setup currently needs.
Release region, resource revision and spoken locale matter when comparing audio.

The [publisher inventory command](../scripts/live_game_sources.py) records the
active Windows generation without installing a game. Save each region's receipt
privately, then pass it with `--previous` to see added, changed and removed
entries after an update. For example:

```text
python scripts/live_game_sources.py wuwa-global --cache private-cache --output wuwa-before.json
python scripts/live_game_sources.py wuwa-global --cache private-cache --previous wuwa-before.json --output wuwa-after.json
```

| Channel | Compared release inputs on November 9 |
| --- | --- |
| `genshin-global`, `genshin-cn` | Independent 7.2.0 launcher manifests, each with 712 dub PCKs and the main game-manifest identity. November 16: active regional 7.2 resource/design/silence indexes and the independent audio base are verified before normal preparation. |
| `starrail-global`, `starrail-cn` | The two 4.6.0 launchers each list 692 regular dub PCKs. All 692 match across regions by full path, size and MD5. Separate optional chapters require their own source checks. |
| `zzz-global`, `zzz-cn` | The two 3.3.0 launchers each list 313 dub PCKs with identical full paths, sizes and MD5s. The individual Global [dialogue command](../scripts/probe-zzz-publisher.py) can fetch an authored line and original dubs. |
| `endfield-global` | Both 1.6.4 resource indexes. [Radio and film commands](game-audits/endfield.md) resolve original performances from the current dub. |
| `wuwa-global` | The 3.7.1 base leads to the active 3.7.19 story data, four independently versioned dub manifests and 231 movies per quality tier. The command compares 1,549 released file entries and can download an exact external WEM. |
| `nte-global`, `nte-cn` | Regional branch chain and the publisher-verified decoded resource list, including file ranges inside packages. Global PC_140 1.4.11 lists 552 files and mainland PC_150 1.5.4 lists 366. The command downloads individual files by exact name and MD5. A second command matches the mainland publisher manifest to 121,753 Chinese strings in 195 namespaces. Later metadata and direct publisher probes are recorded below. |

The owner-selected [update policy](live-service-completion.md#per-game-update-policy--november-17-2026)
targets independent official updates for ZZZ, Endfield and Wuthering Waves.
Genshin, Star Rail and NTE may use controlled, generation-verified community
metadata fallbacks. All original audio remains publisher-supplied. Current
bootstrap/default-parameter and fallback-verification gaps stay explicit in
issues #83–#88; this policy is not a completion claim.

The three HoYoPlay readers retry the individual immutable manifest or chunk
after a network interruption and check its published digest before caching it.

For Endfield's historical Technical Alpha, the [archive acquisition command](game-audits/endfield-alpha-archive.md) retrieves eight verified original scene recordings from a public client archive: aircraft, bedside, briefing and motorcycle ambush in English and Mandarin. The explicit Mandarin list exports 47 verified caption cuts. Further caption coverage requires original text bindings and spoken boundaries; the historical source remains separate from current game-data refreshes.

NTE's [November 16 publisher pipeline](game-audits/nte.md#publisher-setup-and-immutable-voice-snapshots) connects normal installation-free Windows preparation and original playback to the selected regional manifest, current dialogue/movie tables and checked PAK/IoStore ranges. Its [original-native metadata path](game-audits/nte.md#original-native-publisher-preparation) uses authenticated client descriptors, a fixed retained seed and actual required-closure checks, without a current community mapping index. Global samples passed through the voice service in all four dubs, plus mainland Chinese study/playback, including offline restart. Counts include UI and unresolved entries. Complete story, live upstream-change and platform acceptance remain open. The five inspected Global HPW resources are short video-only MP4 containers, rather than a source of sentence audio or text overlays.

| Game | Inputs used by desktop preparation | Verified online distribution and remaining coverage |
| --- | --- | --- |
| Genshin Impact | Dimbreath's [AnimeGameData](https://gitlab.com/Dimbreath/animegamedata2) supplies translations and dialogue/voice identifiers. Without a game folder, Setup reads the selected regional PC release, verifies its resource identity against an immutable text commit and reads the selected publisher Wwise packages. | The released [HoYoPlay branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8) leads to the Sophon manifests. Public Collapse launcher metadata supplies changing bootstrap parameters; the selected publisher server supplies current hotfix indexes and original packages. Separate resource and audio-base revisions, immutable snapshots and matching text cover normal same-version updates. Historical releases recover removed event performances; some authored reminder, trigger and film bindings remain open. [Genshin evidence](game-audits/genshin.md) |
| Honkai: Star Rail | Dimbreath's [TurnBasedGameData](https://gitlab.com/Dimbreath/turnbasedgamedata) supplies TextMaps, sentence and voice tables. Original performances come from publisher Wwise packages and selected publisher USM movies. [Furina1027/hoyo-files](https://github.com/Furina1027/hoyo-files) supplies optional, data-only format parameters for reviewed movie audio; it does not supply the recordings. | The [HoYoPlay branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8) supplies all four regular Global voice packs. On 4.6 their 692 checksums match the independently updated audio manifest. All eight 4.6 chapter packages now resolve to their released checksums. Regional 4.7 hotfix discovery checks the publisher’s design, asset, Lua, audio and video indexes before retrieving changed files. Eight English and three Japanese Silent Galaxy clips use verified recording-specific spoken windows; other film boundaries and ambiguous takes remain unresolved. [Star Rail evidence](game-audits/starrail.md) |
| Zenless Zone Zero | Dimbreath's [ZenlessData](https://git.mero.moe/dimbreath/ZenlessData) supplies installed TextMaps and scene metadata. Publisher preparation reads the current original tables and overwrite maps. Installed/publisher scene bundles and banks use the pinned [zenless-voice](https://github.com/simon300000/zenless-voice) reader. | The [Global launcher branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=U5hbdsT9W7), public dispatcher/gateway and [Collapse bootstrap metadata](https://github.com/CollapseLauncher/CollapseLauncher-ReleaseRepo) select matching base and current text/resource/audio inventories without a game folder. Normal Japanese and English preparation, actual Persistent/base voices and fresh offline conversions passed. Complete raw patch hashes precede playback; unchanged base voices use verified selective chunks. Selected mainland preparation also passed for Traditional Chinese/Mandarin and Japanese using its own inventories, with eight original clips and seven retained Global clips reproduced after a fresh offline restart. The successful preparation reused only exact mainland-declared content hashes; a separate cold transfer encountered a connection timeout. The 333 scene references, additional films, cold-installation acceptance and auxiliary silence-payload interpretation remain open. [Zenless evidence](game-audits/zzz.md) |
| Arknights: Endfield | [EndfieldData](https://github.com/rmxlinux/EndfieldData) supplies localization, audio and story tables. Without a game folder the toolkit reads the original SparkBuffer localization and story tables, selected voice package headers and requested recordings from the selected Global or mainland China release. Installed VFS packages use format metadata from [EndfieldStudio](https://github.com/EIHRTeam/EndfieldStudio). | The [GRYPHLINE Global updater](https://launcher.gryphline.com/api/game/get_latest?appcode=YDUTE5gscDZ229CW&launcher_appcode=TiaytKBUIEdoEwRT&channel=6&sub_channel=6&launcher_sub_channel=6&disk_type=0&patch_encrypt=1) distributes the original 14 localization tables, story definitions and four language groups. Direct dialogue, Wwise events and cinematic timelines have different bindings. [Endfield evidence](game-audits/endfield.md) |
| Wuthering Waves | The toolkit reads the game's own ConfigDB, plot flows and Wwise banks. [wuwa-keys](https://github.com/yarik0chka/wuwa-keys) supplies archive-format metadata. | Kuro's [Global launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json) and [in-game patch manifest](https://cdn-aws-hw-mc.aki-game.net/prod/client/TkSftmDssRx6BIKZBudzeoOHTnxjoL43/Windows/config.json) distribute the text, flows and regional voice files. [Arikatsu's tables](https://github.com/Arikatsu/WutheringWaves_Data) provide an independent comparison. Movie captions can share a scene soundtrack and still lack an exact localized speech segment. [Wuthering Waves evidence](game-audits/wuwa.md) |
| Neverness to Everness | Publisher localization, original cooked dialogue/movie tables and selected Wwise banks supply text and voice without an installation. Original client descriptors generate current type metadata from a fixed [NTE-usmap](https://github.com/555me/NTE-usmap) seed, checked against the actual reader's required closure. Frozen [UnrealExporter](https://github.com/luk-gg/UnrealExporter) parameters are verified against original archive indices. Installed movie catalogs retain their separate [NTE_Assets](https://github.com/Waifus-Grace/NTE_Assets) source. | The [Global](https://ntecdn1.perfectworld.com/clientRes/publish_PC/Version/Windows/config.xml) and [mainland China](https://yhcdn1.wmupd.com/clientRes/publish_PC/Version/Windows/config.xml) channels advance independently. Same-locale Global old/current normal-worker trials preserve changed/new original playback and reject unsupported required metadata without replacing complete data. Text availability is edition-specific. Complete narrative, live upstream-change and platform acceptance remain open. [NTE evidence](game-audits/nte.md) |

The packaged Unreal readers for Wuthering Waves and Neverness to Everness use
[UEExtractor](https://github.com/SolicenTEAM/UEExtractor) and
[CUE4Parse](https://github.com/FabianFG/CUE4Parse). The audio pipeline uses
[vgmstream](https://github.com/vgmstream/vgmstream) and [FFmpeg](https://ffmpeg.org/).
Software provenance and notices are recorded in the
[runtime inventory](r18-runtime-components.md) and the
[managed-component manifest](../packaging/game-readers/managed-components.json).
The recordings and translations originate from each game's publisher.

Hugging Face was evaluated as a historical comparison for HoYoverse audio.
For example, the [zenless-voice dataset card](https://huggingface.co/datasets/simon3000/zenless-voice)
names the snapshot and its mapping limits. All six readers use the publisher's original game packages.

Genshin's November 16 Costume follow-up found all 30 authored wear recordings
in each of the four Global 7.2 launcher dubs and decoded one original sample
per dub without a game installation. The original subtitle/caption bindings
remain open; an outfit description does not supply the spoken sentence.
[Costume source identities and playback limits](game-audits/genshin.md#costume-wear-voice-sources)

## Conditional publisher checks · November 15, 2026

The HoYoPlay, Star Rail hotfix and Endfield publisher readers revalidate small
HTTP responses with the source's ETag or Last-Modified validator when supplied.
Each check still contacts the source. Only a matching HTTP 304 reuses a body;
a network error, an unsolicited 304, a mismatched 304 validator, a partial response
or an exceeded caller limit fails the check. Publishers without validators
continue to supply a complete response. Existing index and asset checksum
checks still run before snapshot activation.

The process-local metadata cache holds at most 64 entries and 8 MiB of bodies,
with a 2 MiB limit per entry. It respects `no-store` and does not persist
temporary launcher query parameters. This reduces repeated transfers where
the source supports validation; it does not supply missing active hotfix
routes or complete the remaining update and platform acceptance criteria.
[HTTP validation semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2)
