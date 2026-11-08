# Live-service dialogue sources

Reviewed November 8, 2026. All six Windows readers support installed voice packages.
Endfield also supports Global 1.6.4 publisher playback without an installation. For each game, the source audit also retrieved complete
sample recordings from a publisher update server. The two columns below let a
reader reproduce the online check and see which inputs setup currently needs.
Release region, resource revision and spoken locale matter when comparing audio.

| Game | Inputs used by desktop preparation | Verified online distribution and remaining coverage |
| --- | --- | --- |
| Genshin Impact | Dimbreath's [AnimeGameData](https://gitlab.com/Dimbreath/animegamedata2) supplies translations and dialogue/voice identifiers. The reader joins the selected language's Wwise packages. | The released [HoYoPlay branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8) leads to the Sophon manifests. Historical release packages recover removed event performances. The current Global 7.2 in-version audio manifest and some reminder and film bindings remain open. [Genshin evidence](game-audits/genshin.md) |
| Honkai: Star Rail | Dimbreath's [TurnBasedGameData](https://gitlab.com/Dimbreath/turnbasedgamedata) supplies TextMaps, sentence and voice tables. Wwise packages supply the original performances. | The [HoYoPlay branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8) supplies all four Global voice packs. Some sentences name multiple takes and the reviewed scripts leave the selection unresolved. [Star Rail evidence](game-audits/starrail.md) |
| Zenless Zone Zero | Dimbreath's [ZenlessData](https://git.mero.moe/dimbreath/ZenlessData) supplies TextMaps and scene metadata. Installed scene bundles and Wwise banks are read with the toolkit and the pinned [zenless-voice](https://github.com/simon300000/zenless-voice) reader. | The [Global launcher branch](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8&game_ids%5B%5D=U5hbdsT9W7) delivered all 13 base text locales and four voice packs. Later installed overrides restore additional dialogue. Automatic discovery of the current Global 3.3 design hotfix remains open. [Zenless evidence](game-audits/zzz.md) |
| Arknights: Endfield | [EndfieldData](https://github.com/rmxlinux/EndfieldData) supplies localization, audio and story tables. Without a game folder the toolkit pins the verified Global text snapshot, reads publisher package headers and downloads each original voice on demand. Installed VFS packages use format metadata from [EndfieldStudio](https://github.com/EIHRTeam/EndfieldStudio). | The [GRYPHLINE Global updater](https://launcher.gryphline.com/api/game/get_latest?appcode=YDUTE5gscDZ229CW&launcher_appcode=TiaytKBUIEdoEwRT&channel=6&sub_channel=6&launcher_sub_channel=6&disk_type=0&patch_encrypt=1) distributes the original 14 localization tables, story definitions and four language groups. Direct dialogue, Wwise events and cinematic timelines have different bindings. [Endfield evidence](game-audits/endfield.md) |
| Wuthering Waves | The toolkit reads the game's own ConfigDB, plot flows and Wwise banks. [wuwa-keys](https://github.com/yarik0chka/wuwa-keys) supplies archive-format metadata. | Kuro's [Global launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json) and [in-game patch manifest](https://cdn-aws-hw-mc.aki-game.net/prod/client/TkSftmDssRx6BIKZBudzeoOHTnxjoL43/Windows/config.json) distribute the text, flows and regional voice files. [Arikatsu's tables](https://github.com/Arikatsu/WutheringWaves_Data) provide an independent comparison. Movie captions can share a scene soundtrack and still lack an exact localized speech segment. [Wuthering Waves evidence](game-audits/wuwa.md) |
| Neverness to Everness | Installed localization, cooked dialogue tables and Wwise banks supply text and voice. [NTE_Assets](https://github.com/Waifus-Grace/NTE_Assets) supplies movie-table metadata. | The [Global](https://ntecdn1.perfectworld.com/clientRes/publish_PC/Version/Windows/config.xml) and [mainland China](https://yhcdn1.wmupd.com/clientRes/publish_PC/Version/Windows/config.xml) channels advance independently. The audited Global Blackbird dialogue yielded complete recordings in four dubs. Preparing a fresh installation still requires compatible archive metadata. [NTE evidence](game-audits/nte.md) |

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
