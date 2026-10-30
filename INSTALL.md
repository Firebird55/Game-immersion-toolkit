# Install Game immersion toolkit

Windows companion for official multilingual game transcripts, local subtitle OCR and Lexirise/Migaku reading. See the [current game and language matrix](docs/languages/en.md) and [per-game dialogue inventories](docs/game-audits/README.md) for supported voices, text-only dialogue and remaining gaps.

## Install on a new PC

1. Download the latest release ZIP and SHA256SUMS from [GitHub releases](https://github.com/Firebird55/Game-immersion-toolkit/releases/latest). Check the ZIP's SHA-256 before extracting it to a writable folder outside your game installation.
2. Install Python 3.12 with its Windows launcher or install manager, [Node.js 24 with npm](https://nodejs.org/en/download), and Windows Snipping Tool through Microsoft Store. [Python for Windows](https://www.python.org/downloads/windows/) includes the installation instructions. No administrator access is required for the toolkit itself.
3. Double-click **Install.cmd**. It checks prerequisites, installs locked dependencies, initializes OCR, and creates a Start menu shortcut. Release ZIPs use their included prebuilt frontend; source checkouts build it locally.
4. The optional Windows folder picker lets you select only the games you own and want to configure. Choose an installation folder rather than an executable or archive. Blank fields and Cancel preserve existing selections. Tools for selected games are downloaded separately into ignored local caches, with verified checksums and upstream notices.
5. The companion opens after installation. Its first-run **Setup** screen guides you through **Games**, **Capture**, and **Reading**. You can finish without installing every game or adding a reading account. Reopen Setup from the footer whenever needed.

## Games and voices

| Game | Folder to choose | Voice requirement |
| --- | --- | --- |
| Zenless Zone Zero | Contains ZenlessZoneZero_Data, or the Data folder itself | Mandarin voice pack installed through the game launcher |
| PRAGMATA | Contains PRAGMATA.exe and re_chunk_*.pak | Mandarin voices are verified during indexing |
| Cyberpunk 2077 | Contains bin/x64 and archive/pc/content | Official Simplified Chinese voice pack |
| Wuthering Waves | Contains Client, or Client itself | Download the Chinese voice pack inside the game |
| The Witcher 3 | Contains bin and content | Official Chinese speech pack |
| Neverness to Everness (NTE) | Contains Client/WindowsNoEditor/HT, or the nested client folder | Chinese voices; .NET 10 SDK for the local reader |
| Honkai: Star Rail | Contains StarRail.exe and StarRail_Data | Selected English, Mandarin, Japanese or Korean voice pack |
| Genshin Impact | Contains GenshinImpact.exe and GenshinImpact_Data (YuanShen clients accepted) | Selected English, Mandarin, Japanese or Korean voice pack |
| Arknights: Endfield | Contains Endfield.exe and Endfield_Data/StreamingAssets/VFS | Selected voice pack and .NET 10 SDK |
| Spyro Reignited Trilogy | Contains Spyro.exe and Falcon/Content/Paks | All 14 official voice languages; installed original banks are read directly |
| Detroit: Become Human | Contains DetroitBecomeHuman.exe and BigFile_PC.idx | All 12 official voice languages and 24 text locales; original voices read directly |
| Persona 5 Royal | Contains P5R.exe and CPK/BASE.CPK | Selected study text CPK and matching English or Japanese original voice pack; verified character metadata is cached on first preparation |
| METAL GEAR SOLID V: THE PHANTOM PAIN | Contains mgsvtpp.exe, master/data1.dat and master/chunk0.dat | Selected English or Japanese original PC voice edition; Metal Gear Online is excluded |
| DEATH STRANDING | Contains ds.exe and data | Original PC edition with the selected voice pack and its owned oo2core_7_win64.dll; Director’s Cut requires a separate reader |
| Portal | Contains hl2.exe and portal/gameinfo.txt | Selected official Steam language; shared English voices require its completed Steam language manifest |
| Half-Life | Contains hl.exe and valve/liblist.gam | Original GoldSrc edition; authored text messages only, with Include unvoiced dialogue enabled |
| A Plague Tale: Innocence | Contains APlagueTaleInnocence_x64.exe, LangDef.tsc, TRTEXT and SOUNDBANKS | Selected English, French or German voice pack and official text files |
| METAL GEAR SOLID V: GROUND ZEROES | Contains MgsGroundZeroes.exe and data_02.g0s | Selected English or Japanese original Steam voice edition; original Ground Zeroes GZS archives |
| Portal 2 | Contains portal2.exe and portal2/gameinfo.txt | Selected official Steam voice language; update and DLC resources are mounted in authored priority |
| Half-Life 2 | Contains hl2.exe and hl2/gameinfo.txt | Anniversary base game plus installed episodic/ep2 campaigns; each requested voice pack must exist in its own campaign |
| Deus Ex: Human Revolution - Director's Cut | Contains DXHRDC.exe and BIGFILE.000 | Director’s Cut PC edition with complete BIGFILE segments and the selected original language |

Setup shows saved/automatically detected folders, missing voice packs and tools, index readiness, progress and the last check. **Browse game folders** opens the Windows picker; pasted paths are validated before saving. **Use automatic detection** removes only that game's override. **Install game tools** prepares missing dependencies; **Repair game tools** retries their verified downloads. Preparation runs in the background and failures can be retried.

See [NTE support](docs/nte-honkai-support.md) before configuring NTE. Honkai Impact 3rd is archived and unsupported; it is not available in setup or capture. NTE's reader requires the [Microsoft .NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0).

Cyberpunk users can include **Phantom Liberty**: install the DLC and its Simplified Chinese voice pack through the game launcher, select the main Cyberpunk folder, then refresh. Setup checks its optional English/Chinese text and Mandarin voice archives; index status reports mapped DLC performances. V voice selection applies to DLC variants too. The base game works without the DLC. Witcher III refresh includes installed DLC localization and Mandarin speech automatically.

No game archives, audio packages, extracted voices, catalog data or captured clips are included in this repository or installer. The game installation is read-only. Locations are stored per PC in LOCALAPPDATA/Proxy Transcript/game-paths.json, separately from capture calibration and credentials. Tool/game-derived caches stay under data and work and must never be published.

## After a game update or move

Let the game's own launcher finish the patch and voice downloads. Open **Setup → Games**, choose the title and click **Refresh game data**. Checks also run automatically: ZZZ about every 15 minutes, prepared language tables about every two minutes. A moved game can be selected and refreshed without restarting the companion.

The toolkit rebuilds subtitle and original-voice indexes; it does not patch the game. Compatible content and catalog updates need no new toolkit release. NTE movie bindings check their fixed upstream sources daily, on detected game changes, and immediately on explicit refresh. Complete catalog snapshots use one immutable source revision. Previous complete catalogs and indexes remain available if a download or rebuild fails. ZZZ language maps publish as one validated snapshot, so an interrupted update cannot mix old English with new Chinese. Incompatible game formats require a normal toolkit update. See [game-data updates](docs/game-data-updates.md).

## Capture and optional reading accounts

For mobile use, **Setup → Games & Languages → Keep mobile library updated**
maintains one private ZIP per selected voice language and translation while the
companion runs. Choose an existing local folder, preferably synchronized with
your phone through a cloud-storage application. The first-run wizard uses the
same controls. Manual exports remain available. Open the ZIP with **Keep on this
device** enabled in the [public mobile companion](https://firebird55.github.io/Game-immersion-toolkit/).
See [mobile library setup, recovery and physical device checks](docs/mobile-library.md).
The PC can be off during play; the game device must supply a working screen stream.

In **Setup → Capture**, check OCR/audio prerequisites and run the read-only OCR/display test. Its local console remains open until Enter is pressed. Start your game with the prepared study or translation subtitles, then open Capture setup to check the live crop, display scaling, and V/Rover/Zero voice selection. Automatic capture on startup is optional. A microphone is not needed.

For NTE movie variants, select **Zero voice**. For NTE displayed as a centered 16:9 picture inside black bars, select that **Game picture area** option before adjusting the crop. Use **Full game window** when the game fills the window. **Use tested dialogue crop** explicitly applies the reviewed default; upgrading preserves existing calibration.

In **Setup → Reading**, choose Migaku or Lexirise. Migaku uses your installed browser extension. Lexirise reading preferences are local; account features are optional. **Set up local API key** opens a hidden-input prompt on this PC and stores the key encrypted for the Windows user. It is not sent through the browser. Choose an explicitly verified game-deck destination before exporting; account saves and uploads remain explicit actions.

**Download setup report** creates a report with versions and readiness flags. It excludes game-folder paths, account details, credentials, raw errors and transcript contents. The latest-release link provides toolkit updates; it does not rewrite a working Git checkout.

## Repair and toolkit upgrades

Re-run Install.cmd to repair dependencies or OCR after a Snipping Tool update. If the existing Python environment uses a different version, stop the companion, rename only LOCALAPPDATA/Programs/Proxy Transcript/venv to a backup name, and rerun Install.cmd with Python 3.12 installed. Keep key.dpapi and the other files beside the environment.

For a toolkit upgrade, stop the old companion, extract the new verified ZIP, and retain your private data/work folders if you want to keep transcripts, favorites and cached indexes. Capture preferences, game locations and the encrypted key are stored per PC and reused. A key encrypted for one Windows user cannot be copied to another. Run Install.cmd in the new folder. Use scripts/install.ps1 -NoLaunch -NoGamePicker for an unattended dependency repair with existing selections.

## Contributors and agents

Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [RELEASE.md](RELEASE.md). Preserve unrelated work and local data, commit logical changes, and run checks before pushing. Edit shared UI in its source repository, then publish and synchronize consumers. Never publish game assets, captures, keys or private backups. Installation does not itself authorize publication or account changes.

App updates prepare a separate replacement while the current companion keeps translating. Use the new release's `scripts/update-companion.ps1 -SourceRoot <new-release> -Root <current-companion>` for a running installation. OCR and the selected game index warm before capture transfers; open readers reconnect automatically. Game-data rebuilds run at lower priority in separate processes, and matching keeps the previous complete index until the replacement is ready. Failed preparations keep the working version and local data.

For BEYOND: Two Souls, choose the folder containing BeyondTwoSouls_Steam.exe and BigFile_PC.idx.
Install the selected original voice pack with Steam, enable matching subtitles in the game,
then prepare that language in Setup → Languages. See [BEYOND coverage](docs/beyond-support.md).

For HEAVY RAIN, choose the folder containing HeavyRain.exe and Resources.
Select matching spoken audio in the game, then explicitly prepare the learning
language in Setup → Languages. See [HEAVY RAIN coverage](docs/heavy-rain-support.md).


Honkai: Star Rail, Genshin Impact and Arknights: Endfield support English, both
Chinese scripts, Japanese and Korean as study languages, paired with every
listed official translation. See [Star Rail](docs/starrail-languages.md),
[Genshin](docs/genshin-languages.md) and [Endfield](docs/endfield-languages.md).

For Rise of the Tomb Raider, choose the folder containing ROTTR.exe and bigfile.000.tiger.
For Shadow of the Tomb Raider, choose the folder containing SOTTR.exe and bigfile.000.tiger.
Use Steam Properties to install the spoken language, wait for downloads to finish,
then prepare it in Settings → Games & Languages. All official voice formats are
supported even when a pack is absent locally; missing packs remain unavailable
until installed. Regional and DLC availability differs, and the two Chinese
packs keep separate identities. See the [Rise language matrix](docs/rise-tomb-raider-languages.md)
and [Shadow language matrix](docs/shadow-tomb-raider-languages.md).

Hito’s World is [disabled](docs/archived-hito.md); existing records and calibration are retained.
