# Live-service dialogue sources

Reviewed November 9, 2026. All six Windows readers support installed voice packages.
Without a game installation, desktop Setup supports Global and mainland China Genshin launcher releases, regular Global Star Rail launcher voices, Global and mainland China Endfield narrative tables and voices, and Global Wuthering Waves story tables and four dubs. For each game, the source audit also retrieved complete
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
| `genshin-global`, `genshin-cn` | Independent 7.2.0 launcher manifests, each with 712 dub PCKs and the main game-manifest identity. Global in-game hotfix overlays still require a matching resource manifest. |
| `starrail-global`, `starrail-cn` | The two 4.6.0 launchers each list 692 regular dub PCKs. All 692 match across regions by full path, size and MD5. Separate optional chapters require their own source checks. |
| `zzz-global`, `zzz-cn` | The two 3.3.0 launchers each list 313 dub PCKs with identical full paths, sizes and MD5s. The individual Global [dialogue command](../scripts/probe-zzz-publisher.py) can fetch an authored line and original dubs. |
| `endfield-global` | Both 1.6.4 resource indexes. [Radio and film commands](game-audits/endfield.md) resolve original performances from the current dub. |
| `wuwa-global` | The 3.7.1 base leads to the active 3.7.19 story data, four independently versioned dub manifests and 231 movies per quality tier. The command compares 1,549 released file entries and can download an exact external WEM. |
| `nte-global`, `nte-cn` | Regional branch chain and the publisher-verified decoded resource list, including file ranges inside packages. Global PC_140 1.4.11 lists 552 files and mainland PC_150 1.5.4 lists 366. The command downloads individual files by exact name and MD5. A second command matches the mainland publisher manifest to 121,753 Chinese strings in 195 namespaces. Fresh per-line audio still needs game archive metadata. |

The three HoYoPlay readers retry the individual immutable manifest or chunk
after a network interruption and check its published digest before caching it.

| Game | Inputs used by desktop preparation | Verified online distribution and remaining coverage |
| --- | --- | --- |
| Genshin Impact | Dimbreath's [AnimeGameData](https://gitlab.com/Dimbreath/animegamedata2) supplies translations and dialogue/voice identifiers. Without a game folder, setup reads the released mainland PC branch, matches all three resource revisions to an immutable text commit and reads the selected publisher Wwise packages. | The released [HoYoPlay branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8) leads to the Sophon manifests. Historical release packages recover removed event performances. The current Global 7.2 in-version audio manifest and some reminder and film bindings remain open. [Genshin evidence](game-audits/genshin.md) |
| Honkai: Star Rail | Dimbreath's [TurnBasedGameData](https://gitlab.com/Dimbreath/turnbasedgamedata) supplies TextMaps, sentence and voice tables. Wwise packages supply the original performances. | The [HoYoPlay branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8) supplies all four regular Global voice packs. On 4.6 their 692 checksums match the independently updated audio manifest. Five of eight additional chapter packages match files in the public Global preload. The other three and automatic hotfix acquisition remain open. Some sentences name multiple takes and the reviewed scripts leave the selection unresolved. [Star Rail evidence](game-audits/starrail.md) |
| Zenless Zone Zero | Dimbreath's [ZenlessData](https://git.mero.moe/dimbreath/ZenlessData) supplies TextMaps and scene metadata. Installed scene bundles and Wwise banks are read with the toolkit and the pinned [zenless-voice](https://github.com/simon300000/zenless-voice) reader. | The [Global launcher branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=U5hbdsT9W7) delivered the same-build Perform table, scene bundles, all 13 base text locales and four voice packs. With no game folder, Windows Setup prepares recorded phone messages from that Global launcher base in the selected dub. The source-checkout publisher command also fetches selected scene and ongoing lines by subtitle ID. Later installed overrides restore additional dialogue. Automatic discovery of the current Global 3.3 design hotfix remains open. [Zenless evidence](game-audits/zzz.md) |
| Arknights: Endfield | [EndfieldData](https://github.com/rmxlinux/EndfieldData) supplies localization, audio and story tables. Without a game folder the toolkit reads the original SparkBuffer localization and story tables, selected voice package headers and requested recordings from the selected Global or mainland China release. Installed VFS packages use format metadata from [EndfieldStudio](https://github.com/EIHRTeam/EndfieldStudio). | The [GRYPHLINE Global updater](https://launcher.gryphline.com/api/game/get_latest?appcode=YDUTE5gscDZ229CW&launcher_appcode=TiaytKBUIEdoEwRT&channel=6&sub_channel=6&launcher_sub_channel=6&disk_type=0&patch_encrypt=1) distributes the original 14 localization tables, story definitions and four language groups. Direct dialogue, Wwise events and cinematic timelines have different bindings. [Endfield evidence](game-audits/endfield.md) |
| Wuthering Waves | The toolkit reads the game's own ConfigDB, plot flows and Wwise banks. [wuwa-keys](https://github.com/yarik0chka/wuwa-keys) supplies archive-format metadata. | Kuro's [Global launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json) and [in-game patch manifest](https://cdn-aws-hw-mc.aki-game.net/prod/client/TkSftmDssRx6BIKZBudzeoOHTnxjoL43/Windows/config.json) distribute the text, flows and regional voice files. [Arikatsu's tables](https://github.com/Arikatsu/WutheringWaves_Data) provide an independent comparison. Movie captions can share a scene soundtrack and still lack an exact localized speech segment. [Wuthering Waves evidence](game-audits/wuwa.md) |
| Neverness to Everness | Installed localization, cooked dialogue tables and Wwise banks supply text and voice. [NTE_Assets](https://github.com/Waifus-Grace/NTE_Assets) supplies movie-table metadata. | The [Global](https://ntecdn1.perfectworld.com/clientRes/publish_PC/Version/Windows/config.xml) and [mainland China](https://yhcdn1.wmupd.com/clientRes/publish_PC/Version/Windows/config.xml) channels advance independently. The regional text command checks the mainland manifest against the immutable [NTEData export](https://github.com/555me/NTEData). The audited Global Blackbird dialogue yielded complete recordings in four dubs. Preparing a fresh installation still requires compatible archive metadata. [NTE evidence](game-audits/nte.md) |

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
