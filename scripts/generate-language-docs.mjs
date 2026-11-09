import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {translate} from '../public/mobile-capture/interface-language.mjs';
const catalog=JSON.parse(readFileSync('public/mobile-capture/games-data.json','utf8'));
const repo='https://github.com/Firebird55/Game-immersion-toolkit',site='https://firebird55.github.io/Game-immersion-toolkit/';
const text={
 en:{title:'Read the dialogue. Stay in the story.',intro:'Follow official game dialogue, replay original voices, and learn with reading tools on Windows, phone or tablet.',download:'Download for Windows',online:'Open online companion',guide:'Installation & help',support:'Games & language support',game:'Game',learn:'Learning languages',targets:'Translation languages',details:'Language details',language:'Language',voice:'Original voice',study:'Learning',translation:'Translation',evidence:'Evidence',yes:'Yes',no:'—',expected:'Expected',implemented:'Reader implemented',playback:'Audio decoded locally',formatOnly:'Format tested; voice pack not verified locally',unavailable:'Unavailable',textOnly:'Text only',mandarin:'Shared Mandarin voice',legend:'✓ = implemented reader support; ◇ = expected from the shared locale format; — = unavailable. Language support does not mean every chapter has been played or every line is mapped.',assumptions:'You do not need to export every language pack. Readers reuse the game’s authored identifiers and locale format. Choose the original voice and an official translation in Setup. For games prepared from installed files, install the selected voice pack first. Missing assets or translations remain unavailable.',start:'Start in three steps',steps:['Download a release, extract it, and run **Install.cmd**.','Open **Settings → Games & Languages**. Choose your game, learning language and translation; prepare the selected table.','Start your game with subtitles. Check **Capture**, then read and replay dialogue.'],modes:'Choose how to play',desktop:'Windows capture',desktopText:'Capture game subtitles and read locally. Game files and account keys stay on your PC.',paired:'Desktop-connected reader',pairedText:'Read the desktop transcript and play matched voices on a phone or tablet, including iPhone and iPad. Keep the desktop running.',mobile:'Android app (planned)',mobileText:'Android will run OCR, match dialogue and play the original voice locally. The shared-core app and iPhone/iPad screen-sender route still need device verification.',help:'Help and development',helpText:'Lexirise is optional. Migaku remains an independent mode where the browser extension is supported. Existing Chinese transcripts keep their original language.',install:'Install and prepare',storage:'Understand storage',storageText:'The language manager shows actual table sizes. Shared audio/tools are counted once. Game archives and external exports are reported separately; unknown sizes are not shown as zero. Removing a table clears local language selections, but keeps history, favorites, game files and credentials. Prepare the table again to restore original-voice lookup.',trouble:'Troubleshooting',tips:['Missing voice pack: install the matching spoken language through the game launcher, then prepare again.','Skipped captions: check the subtitle crop, resolution and on-screen subtitle language. BEYOND tolerates one brief OCR dropout while still requiring confirmation.','Mobile offline: download the chosen OCR pack first. Keep on this device reopens libraries automatically; retain your ZIP as a recovery copy because the operating system can remove browser storage.','Account settings: reload to read existing preferences. Only explicit save controls change your account.'],source:'Official language listing',coverage:'Coverage notes',matrix:'Language support matrix'},
 nl:{title:'Lees de dialoog. Blijf in het verhaal.',intro:'Volg officiële gamedialogen, speel originele stemmen af en leer met leeshulpmiddelen op Windows, telefoon of tablet.',download:'Downloaden voor Windows',online:'Online companion openen',guide:'Installatie en hulp',support:'Games en taalondersteuning',game:'Game',learn:'Leertalen',targets:'Vertaaltalen',details:'Taaldetails',language:'Taal',voice:'Originele stem',study:'Leren',translation:'Vertaling',evidence:'Onderbouwing',yes:'Ja',no:'—',expected:'Verwacht',implemented:'Reader geïmplementeerd',playback:'Audio lokaal gedecodeerd',formatOnly:'Formaat getest; lokaal stempakket niet geverifieerd',unavailable:'Niet beschikbaar',textOnly:'Alleen tekst',mandarin:'Gedeelde Mandarijnse stem',legend:'✓ = readerondersteuning geïmplementeerd; ◇ = verwacht op basis van hetzelfde taalformaat; — = niet beschikbaar. Dit betekent niet dat elk hoofdstuk gespeeld of elke zin gekoppeld is.',assumptions:'Je hoeft niet elk taalpakket te exporteren. Readers hergebruiken de oorspronkelijke game-ID’s en het taalformaat. Kies in de instellingen de originele stem en een officiële vertaling. Gebruik je geïnstalleerde gamebestanden, installeer dan eerst het gekozen stempakket. Ontbrekende bestanden of vertalingen blijven niet beschikbaar.',start:'Begin in drie stappen',steps:['Download een release, pak deze uit en start **Install.cmd**.','Open **Instellingen → Games en talen**. Kies je game, leertaal en vertaling; bereid de geselecteerde tabel voor.','Start je game met ondertiteling. Controleer **Ondertitels vastleggen** en lees of beluister de dialoog.'],modes:'Kies hoe je speelt',desktop:'Windows-opname',desktopText:'Leg ondertitels vast en lees lokaal. Gamebestanden en accountsleutels blijven op je pc.',paired:'Reader gekoppeld aan de desktop',pairedText:'Lees het desktoptranscript en speel gekoppelde stemmen af op een telefoon of tablet, ook op iPhone of iPad. Houd de desktop aan.',mobile:'Android-app (gepland)',mobileText:'Android gaat lokaal OCR uitvoeren, dialogen herkennen en de originele stem afspelen. De app met de gedeelde toolkitcode en het delen van een iPhone- of iPad-scherm moeten nog op apparaten worden getest.',help:'Hulp en ontwikkeling',helpText:'Lexirise is optioneel. Migaku werkt zelfstandig waar de browserextensie wordt ondersteund. Bestaande Chinese transcripten behouden hun taal.',install:'Installeren en voorbereiden',storage:'Opslag begrijpen',storageText:'De taalmanager toont echte tabelgroottes. Gedeelde audio en hulpmiddelen worden eenmaal geteld. Gamearchieven en externe exports staan apart; onbekende groottes zijn geen nul. Een tabel verwijderen wist lokale taalkeuzes, maar bewaart geschiedenis, favorieten, gamebestanden en sleutels. Bereid de tabel opnieuw voor om stemmen terug te vinden.',trouble:'Problemen oplossen',tips:['Stempakket ontbreekt: installeer de juiste gesproken taal via de gamelauncher en bereid deze opnieuw voor.','Ondertitels gemist: controleer opnamegebied, resolutie en ondertiteltaal. BEYOND verdraagt één korte OCR-uitval, maar vereist nog steeds bevestiging.','Mobiel offline: download eerst het gekozen OCR-pakket. Bewaar catalogus- en stem-ZIP’s; het besturingssysteem kan browseropslag opruimen.','Accountinstellingen: laad opnieuw om voorkeuren te lezen. Alleen expliciete opslagacties wijzigen je account.'],source:'Officiële taallijst',coverage:'Dekkingsnotities',matrix:'Taalondersteuningsmatrix'},
 'zh-Hans':{title:'读懂对话，沉浸故事。',intro:'在 Windows、手机或平板上阅读官方游戏对话、重播原版配音，并使用阅读工具学习语言。',download:'下载 Windows 版',online:'打开在线伴侣',guide:'安装与帮助',support:'游戏与语言支持',game:'游戏',learn:'学习语言',targets:'翻译语言',details:'语言详情',language:'语言',voice:'原版配音',study:'学习',translation:'翻译',evidence:'依据',yes:'是',no:'—',expected:'预计支持',implemented:'已实现读取器',playback:'已在本机解码原始配音',formatOnly:'格式已测试；未在本机验证配音包',unavailable:'不可用',textOnly:'仅文本',mandarin:'共用普通话配音',legend:'✓ = 已实现读取支持；◇ = 根据相同语言格式预计可用；— = 不可用。语言支持不代表已玩遍所有章节或已映射每句对话。',assumptions:'无需逐一导出所有语言包。读取器复用游戏原有标识符和语言格式。在设置中选择原版配音和官方翻译。若从已安装的游戏文件准备数据，请先安装所选语音包。缺失的文件或翻译仍会显示为不可用。',start:'三步开始',steps:['下载发行版，解压后运行 **Install.cmd**。','打开 **设置 → 游戏与语言**。选择游戏、学习语言和翻译语言，然后准备所选数据表。','启动游戏并开启字幕。检查 **字幕捕获**，即可阅读和重播对话。'],modes:'选择使用方式',desktop:'Windows 捕获',desktopText:'捕获游戏字幕并在本地阅读。游戏文件和账户密钥保留在电脑上。',paired:'连接桌面端的阅读器',pairedText:'在手机或平板（包括 iPhone 和 iPad）上阅读桌面端生成的台词记录并播放匹配的配音。桌面端须保持运行。',mobile:'Android 应用（计划中）',mobileText:'Android 将在本机进行 OCR、匹配台词并播放原版配音。采用共享核心的应用以及从 iPhone 或 iPad 发送游戏画面的流程仍需真机验证。',help:'帮助与开发',helpText:'Lexirise 为可选服务。支持浏览器扩展的环境中，Migaku 可独立运行。现有中文文本保持原语言。',install:'安装与准备',storage:'了解存储空间',storageText:'语言管理器显示实际数据表大小。共享音频和工具仅计算一次。游戏存档和外部导出文件分别列出；未知大小不会显示为零。删除数据表会清除本地语言选择，但保留历史记录、收藏、游戏文件和凭据。重新准备数据表即可恢复原版配音查找。',trouble:'故障排除',tips:['缺少配音包：通过游戏启动器安装对应的口语语言，然后重新准备。','漏掉字幕：检查字幕裁剪区域、分辨率和屏幕字幕语言。BEYOND 可容忍一次短暂 OCR 丢失，但仍需要确认。','移动端离线：先下载所选 OCR 包。保留目录和配音 ZIP；操作系统可能清理浏览器存储。','账户设置：重新加载以读取现有偏好。只有明确的保存操作才会更改账户。'],source:'官方语言列表',coverage:'覆盖范围说明',matrix:'语言支持矩阵'},
 'zh-Hant':{title:'讀懂對話，沉浸故事。',intro:'在 Windows、手機或平板上閱讀官方遊戲對話、重播原版配音，並使用閱讀工具學習語言。',download:'下載 Windows 版',online:'開啟線上伴隨應用程式',guide:'安裝與說明',support:'遊戲與語言支援',game:'遊戲',learn:'學習語言',targets:'翻譯語言',details:'語言詳細資訊',language:'語言',voice:'原版配音',study:'學習',translation:'翻譯',evidence:'依據',yes:'是',no:'—',expected:'預期支援',implemented:'已實作讀取器',playback:'已在本機解碼原始配音',formatOnly:'格式已測試；未在本機驗證配音包',unavailable:'無法使用',textOnly:'僅文字',mandarin:'共用華語配音',legend:'✓ = 已實作讀取支援；◇ = 根據相同語言格式預期可用；— = 無法使用。語言支援不代表已玩遍所有章節或已對應每句對話。',assumptions:'無需逐一匯出所有語言包。讀取器重用遊戲原有識別碼和語言格式。在設定中選擇原版配音和官方譯文。若從已安裝的遊戲檔案準備資料，請先安裝所選語音包。缺少的檔案或翻譯仍會顯示為無法使用。',start:'三步開始',steps:['下載發行版，解壓縮後執行 **Install.cmd**。','開啟 **設定 → 遊戲與語言**。選擇遊戲、學習語言和翻譯語言，再準備所選資料表。','啟動遊戲並開啟字幕。檢查 **字幕擷取**，即可閱讀和重播對話。'],modes:'選擇使用方式',desktop:'Windows 擷取',desktopText:'擷取遊戲字幕並在本機閱讀。遊戲檔案和帳戶金鑰保留在電腦上。',paired:'連接桌面端的閱讀器',pairedText:'在手機或平板（包括 iPhone 和 iPad）上閱讀桌面端產生的台詞記錄並播放對應的配音。桌面端須保持執行。',mobile:'Android 應用程式（規劃中）',mobileText:'Android 將在本機執行 OCR、比對台詞並播放原版配音。採用共用核心的應用程式以及從 iPhone 或 iPad 傳送遊戲畫面的流程仍須實機驗證。',help:'說明與開發',helpText:'Lexirise 為選用服務。支援瀏覽器擴充功能的環境中，Migaku 可獨立執行。現有中文文字維持原語言。',install:'安裝與準備',storage:'了解儲存空間',storageText:'語言管理器顯示實際資料表大小。共用音訊和工具僅計算一次。遊戲封存檔與外部匯出檔案分別列出；未知大小不會顯示為零。刪除資料表會清除本機語言選擇，但保留歷史紀錄、收藏、遊戲檔案和憑證。重新準備資料表即可恢復原版配音查找。',trouble:'疑難排解',tips:['缺少配音包：透過遊戲啟動器安裝對應的口語語言，再重新準備。','漏掉字幕：檢查字幕裁切區域、解析度和螢幕字幕語言。BEYOND 可容忍一次短暫 OCR 遺漏，但仍需要確認。','行動版離線：先下載所選 OCR 包。保留目錄和配音 ZIP；作業系統可能清理瀏覽器儲存空間。','帳戶設定：重新載入以讀取現有偏好。只有明確的儲存操作才會變更帳戶。'],source:'官方語言清單',coverage:'涵蓋範圍說明',matrix:'語言支援矩陣'}
};
const storageNotes={
 en:'In Games & Languages (also in first-run setup), Keep mobile library updated maintains one ZIP per chosen voice language and translation while the companion runs. Choose an existing local folder, preferably synchronized with your mobile cloud-storage app. Keep on this device retains mobile libraries and voices for reopening. Separate Remember on this device options save the API key and complete VDO.Ninja link without an application passphrase; use only on trusted devices. Browser/OS deletion is still possible.',
 nl:'In Games en talen (ook bij de eerste installatie) houdt Keep mobile library updated één ZIP per gekozen stemtaal en vertaling bij zolang de companion draait. Kies een bestaande lokale map, bij voorkeur gesynchroniseerd met je mobiele cloudopslag. Keep on this device bewaart bibliotheken en stemmen voor opnieuw openen. Afzonderlijke Remember on this device-opties bewaren de API-sleutel en volledige VDO.Ninja-link zonder appwachtwoord; gebruik dit alleen op vertrouwde apparaten. De browser of het besturingssysteem kan opslag nog steeds wissen.',
 'zh-Hans':'在游戏与语言设置（也包括首次设置向导）中，Keep mobile library updated 会在桌面 companion 运行时为所选配音语言和译文维护各自的 ZIP。选择已有的本地文件夹，建议使用与手机云存储同步的文件夹。Keep on this device 会保存资料库和配音供下次自动打开。两个独立的 Remember on this device 选项可在没有应用口令的情况下保存 API 密钥和完整 VDO.Ninja 链接；仅在信任的设备上启用。浏览器或系统仍可能删除存储。',
 'zh-Hant':'在遊戲與語言設定（也包括首次設定精靈）中，Keep mobile library updated 會在桌面 companion 執行時為所選配音語言和譯文維護各自的 ZIP。選擇既有的本機資料夾，建議使用與手機雲端儲存同步的資料夾。Keep on this device 會保留資料庫和配音供下次自動開啟。兩個獨立的 Remember on this device 選項可在沒有應用程式口令的情況下保存 API 金鑰和完整 VDO.Ninja 連結；僅在信任的裝置上啟用。瀏覽器或系統仍可能刪除儲存。'
};
const publisherSetup = {
 en: 'Leave the game folder empty in Windows Setup to prepare mainland China Genshin Impact, regular Global Star Rail voices, Global Endfield narrative voices or Global Wuthering Waves dialogue. Choose the language you want to study. Endfield film clips require verified timelines. For Zenless Zone Zero, an empty folder prepares recorded phone messages from the Global launcher base. Other dialogue requires installed files.',
 nl: 'Laat de gamemap leeg in de Windows-instellingen voor de Chinese vastelandversie van Genshin Impact, de reguliere Global-stempakketten van Star Rail, de Global-verhaalstemmen van Endfield of de Global-dialogen van Wuthering Waves. Kies je leertaal. Endfield-filmfragmenten vereisen een gecontroleerde tijdlijn. Bij Zenless Zone Zero levert een lege gamemap de ingesproken telefoonberichten uit de Global-launcher op. Voor andere dialogen zijn geïnstalleerde gamebestanden nodig.',
 'zh-Hans': '在 Windows 设置中将游戏文件夹留空，选择学习语言，即可准备中国大陆版《原神》、全球版《崩坏：星穹铁道》的常规配音、全球版《明日方舟：终末地》的剧情配音或全球版《鸣潮》的台词与配音。《终末地》的过场片段需要经过核实的时间轴。《绝区零》可从全球版启动器基础包获取有声手机消息。其他对话需要已安装的游戏文件。',
 'zh-Hant': '在 Windows 設定中將遊戲資料夾留空，選擇學習語言，即可準備中國大陸版《原神》、全球版《崩壞：星穹鐵道》的常規配音、全球版《明日方舟：終末地》的劇情配音或全球版《鳴潮》的台詞與配音。《終末地》的過場片段需要經過核實的時間軸。《絕區零》可從全球版啟動器基礎包取得有聲手機訊息。其他對話需要已安裝的遊戲檔案。'
};
const sourceLabels = {
 en: ['Text, voices and upstream projects', 'Game', 'Original audio distribution', 'Text sources, reader credits and coverage by game'],
 nl: ['Tekst, stemmen en bronprojecten', 'Game', 'Distributie van originele stemmen', 'Tekstbronnen, gebruikte readers en dekking per game'],
 'zh-Hans': ['文本、配音与上游项目', '游戏', '原版配音发布渠道', '各游戏的文本来源、读取工具与覆盖情况'],
 'zh-Hant': ['文字、配音與上游專案', '遊戲', '原版配音發布管道', '各遊戲的文字來源、讀取工具與涵蓋範圍'],
};
const upstreamProjects = {
 genshin: ['HoYoverse / HoYoPlay', [
   ['Dimbreath/AnimeGameData', 'https://gitlab.com/Dimbreath/animegamedata2', 'dialogue'],
   ['kuaichu/game-cdn-archive', 'https://github.com/kuaichu/game-cdn-archive', 'historical']]],
 starrail: ['HoYoverse / HoYoPlay', [['Dimbreath/TurnBasedGameData', 'https://gitlab.com/Dimbreath/turnbasedgamedata', 'sentence']]],
 zzz: ['HoYoverse / HoYoPlay', [
   ['Dimbreath/ZenlessData', 'https://git.mero.moe/dimbreath/ZenlessData', 'sceneTables'],
   ['simon300000/zenless-voice', 'https://github.com/simon300000/zenless-voice', 'sceneReader'],
   ['Hiro420/ZZZ_TextMap', 'https://github.com/Hiro420/ZZZ_TextMap', 'schemaReference']]],
 endfield: ['GRYPHLINE', [
   ['rmxlinux/EndfieldData', 'https://github.com/rmxlinux/EndfieldData', 'storyTables'],
   ['EIHRTeam/EndfieldStudio', 'https://github.com/EIHRTeam/EndfieldStudio', 'voiceArchive']]],
 wuwa: ['Kuro Games', [
   ['SnosMe/ooz-wasm', 'https://github.com/SnosMe/ooz-wasm', 'compressedAudio'],
   ['Yumeo0/mornye-tools', 'https://github.com/Yumeo0/mornye-tools', 'launcherFormat'],
   ['yarik0chka/wuwa-keys', 'https://github.com/yarik0chka/wuwa-keys', 'archive'],
   ['Arikatsu/WutheringWaves_Data', 'https://github.com/Arikatsu/WutheringWaves_Data', 'comparison']]],
 nte: ['Perfect World Games', [
   ['Waifus-Grace/NTE_Assets', 'https://github.com/Waifus-Grace/NTE_Assets', 'movies'],
   ['555me/NTEData', 'https://github.com/555me/NTEData', 'mainlandText'],
   ['555me/NTE-usmap', 'https://github.com/555me/NTE-usmap', 'archiveSchema'],
   ['BlueHeisenberg/SCSKiller', 'https://github.com/BlueHeisenberg/SCSKiller', 'archiveMetadata'],
   ['Tobiichi-Origuchi/nte_patcher', 'https://github.com/Tobiichi-Origuchi/nte_patcher', 'globalUpdater'],
   ['kuaichu/game-cdn-archive', 'https://github.com/kuaichu/game-cdn-archive', 'mainlandUpdater']]],
};
const projectRoles = {
 en: {
   heading:'Upstream project and role',
   dialogue:'required translations and dialogue-to-voice IDs',
   sentence:'required translations, sentence IDs and voice tables',
   sceneTables:'required translations and scene tables for installed games',
   sceneReader:'required scene reader',
   storyTables:'required localization and story tables for installed games',
   voiceArchive:'required voice archive metadata',
   launcherFormat:'required publisher catalogue format',
   archive:'required game archive metadata',
   comparison:'optional table comparison',
   movies:'required movie tables, with a pinned fallback revision',
   archiveSchema:'required installed type schema',
   archiveMetadata:'required compatible installed archive metadata',
   globalUpdater:'required for Global updater checks',
   compressedAudio:'required for compressed publisher audio entries',
   mainlandText:'Chinese text for the mainland release, required by the regional export command',
   mainlandUpdater:'required for mainland updater checks',
   historical:'optional historical release index',
   schemaReference:'optional TextMap schema reference',
   readers:'Unreal archive readers',
   audio:'Audio decoding and conversion',
   notices:'Third-party notices',
   scope:'These six games are the targets for independent preparation and playback on Linux, macOS and Android. Per-game acceptance on those hosts is pending. Other game integrations support Windows only.',
 },
 nl: {
   heading:'Bronproject en rol',
   dialogue:'benodigde vertalingen en koppelingen tussen dialoog en stem',
   sentence:'benodigde vertalingen, regel-ID’s en stemtabellen',
   sceneTables:'benodigde vertalingen en scènetabellen voor een geïnstalleerde game',
   sceneReader:'benodigde scènelezer',
   storyTables:'benodigde vertalingen en verhaaltabellen voor een geïnstalleerde game',
   voiceArchive:'benodigde metadata voor stemarchieven',
   launcherFormat:'benodigde formaatinformatie voor de uitgeverscatalogus',
   archive:'benodigde metadata voor gamearchieven',
   comparison:'optioneel voor vergelijking van tabellen',
   movies:'benodigde filmtabellen, met een vastgelegde revisie als terugvaloptie',
   archiveSchema:'benodigd typeschema voor geïnstalleerde bestanden',
   archiveMetadata:'benodigde metadata voor compatibele lokale archieven',
   globalUpdater:'nodig voor controle van de Global-updater',
   compressedAudio:'nodig voor gecomprimeerde audio in de uitgeverspakketten',
   mainlandText:'Chinese tekst voor de vastelandversie, nodig voor de regionale tekstexport',
   mainlandUpdater:'nodig voor controle van de Chinese vastelandupdater',
   historical:'optionele index van oude releases',
   schemaReference:'optionele referentie voor het TextMap-schema',
   readers:'Readers voor Unreal-archieven',
   audio:'Audio decoderen en converteren',
   notices:'Licenties en vermeldingen',
   scope:'Voor deze zes games werken we aan zelfstandige voorbereiding en weergave op Linux, macOS en Android. Verificatie per game op die platforms staat nog open. De overige game-integraties ondersteunen alleen Windows.',
 },
 'zh-Hans': {
   heading:'上游项目及用途',
   dialogue:'提供必需的译文和台词与配音的对应关系',
   sentence:'提供必需的译文、台词编号和配音表',
   sceneTables:'本地游戏读取所需的译文和场景表',
   sceneReader:'必需的场景读取器',
   storyTables:'本地游戏读取所需的本地化和剧情表',
   voiceArchive:'读取配音包所需的格式信息',
   launcherFormat:'读取发行商目录所需的格式信息',
   archive:'读取游戏资源包所需的格式信息',
   comparison:'可选的数据表核对来源',
   movies:'必需的影片表，必要时使用固定版本',
   archiveSchema:'已安装资源所需的类型表',
   archiveMetadata:'读取本地资源包所需的兼容元数据',
   globalUpdater:'核对全球版更新器所需',
   compressedAudio:'读取发行商压缩配音条目所需',
   mainlandText:'中国大陆版文本导出命令所需的中文本地化数据',
   mainlandUpdater:'核对中国大陆版更新器所需',
   historical:'可选的历史版本索引',
   schemaReference:'可选的 TextMap 格式参考',
   readers:'Unreal 资源读取器',
   audio:'音频解码与转换',
   notices:'第三方许可与声明',
   scope:'这六款游戏计划支持在 Linux、macOS 和 Android 上独立准备数据及播放配音。各平台仍需逐款验证。其他游戏仅支持 Windows。',
 },
 'zh-Hant': {
   heading:'上游專案及用途',
   dialogue:'提供必要的譯文和台詞與配音的對應關係',
   sentence:'提供必要的譯文、台詞編號和配音表',
   sceneTables:'讀取已安裝遊戲所需的譯文和場景表',
   sceneReader:'必要的場景讀取器',
   storyTables:'讀取已安裝遊戲所需的在地化和劇情表',
   voiceArchive:'讀取配音封存檔所需的格式資訊',
   launcherFormat:'讀取發行商目錄所需的格式資訊',
   archive:'讀取遊戲封存檔所需的格式資訊',
   comparison:'可選用的資料表比對來源',
   movies:'必要的影片表，需要時使用固定版本',
   archiveSchema:'已安裝資源所需的型別表',
   archiveMetadata:'讀取本機資源包所需的相容中繼資料',
   globalUpdater:'核對全球版更新程式所需',
   compressedAudio:'讀取發行商壓縮配音項目所需',
   mainlandText:'中國大陸版文字匯出所需的中文在地化資料',
   mainlandUpdater:'核對中國大陸版更新程式所需',
   historical:'可選用的歷史版本索引',
   schemaReference:'可選用的 TextMap 格式參考',
   readers:'Unreal 資源讀取器',
   audio:'音訊解碼與轉換',
   notices:'第三方授權與聲明',
   scope:'這六款遊戲規劃支援在 Linux、macOS 和 Android 上獨立準備資料及播放配音。各平台仍須逐款驗證。其他遊戲僅支援 Windows。',
 },
};
const switches='[English](README.md) · [Nederlands](README.nl.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md)';
function output(path,content){
 if(process.argv.includes('--check')){if(!existsSync(path)||readFileSync(path,'utf8').replaceAll('\r\n','\n')!==content)throw Error(`Regenerate language documentation: ${path}`);}
 else writeFileSync(path,content);
}
const platformPath = 'docs/desktop-platforms.md';
const platformDoc = readFileSync(platformPath, 'utf8').replaceAll('\r\n', '\n');
const hostTable = ['| Toolkit host | Independent preparation | Original playback | Game and capture device | Transcript reader |',
 '| --- | --- | --- | --- | --- |',
 ...Object.entries(catalog.platformScope.hosts).map(([host, roles]) =>
   `| ${host} | ${roles.preparation} | ${roles.playback} | ${roles.gameCapture} | ${roles.reader} |`),
].join('\n');
const hostMarkers = /(<!-- generated game host roles -->\n)[\s\S]*?(\n<!-- end generated game host roles -->)/;
if (!hostMarkers.test(platformDoc)) throw Error('Missing platform table markers');
output(platformPath, platformDoc.replace(hostMarkers, (_match, start, end) => start + '\n' + hostTable + '\n' + end));
mkdirSync('docs/languages',{recursive:true});
for(const [locale,t] of Object.entries(text)){
 const display=new Intl.DisplayNames([locale],{type:'language'}),name=code=>display.of(code)??code;
 const matrixPath=`docs/languages/${locale}.md`,installPath=`docs/languages/install-${locale}.md`;
 const overview=`| ${t.game} | ${t.learn} | ${t.targets} |\n| :--- | :--- | :--- |\n`+catalog.games.map(g=>`| [${g.name}](${matrixPath}#${g.id}) | ${g.textOnly?`**${t.textOnly}:** `:''}${g.study.map(name).join(' · ')} | ${g.targets.length} |`).join('\n');
 const [sourceTitle,sourceGame,publisher,sourceLink] = sourceLabels[locale];
 const roles = projectRoles[locale];
 const {targets, windowsPreparation, windowsOnly} = catalog.platformScope;
 const platformGuide = translate('Toolkit hosts and game devices', locale);
 const preparation = id => translate(windowsPreparation[targets[id]]?.label ?? windowsOnly, locale);
 if (Object.keys(upstreamProjects).some(id => !Object.hasOwn(targets, id))) throw Error('An upstream credit is missing from platformScope');
 const sources = [
   '## ' + sourceTitle, '',
   `| ${sourceGame} | ${publisher} | ${roles.heading} | ${translate('Windows Setup', locale)} |`, '| :--- | :--- | :--- | :--- |',
   ...Object.keys(targets).map(id => {
     const game = catalog.games.find(game => game.id === id);
     const [channel, projects] = upstreamProjects[id];
     const credits = projects.map(([name, url, role]) => `[${name}](${url}) (${roles[role]})`);
     return `| ${game.name} | ${channel} | ${credits.join(' · ')} | ${preparation(id)} |`;
   }), '',
   `${roles.readers} ([UEExtractor](https://github.com/SolicenTEAM/UEExtractor), [CUE4Parse](https://github.com/FabianFG/CUE4Parse)). ${roles.audio} ([vgmstream](https://github.com/vgmstream/vgmstream), [FFmpeg](https://ffmpeg.org/)).`, '',
   publisherSetup[locale], '',
   roles.scope, '',
   `[${sourceLink}](docs/live-service-sources.md) · [${platformGuide}](docs/desktop-platforms.md) · [${roles.notices}](THIRD_PARTY_NOTICES.md)`,
 ].join('\n');
 const readme=`<!-- Generated by scripts/generate-language-docs.mjs -->\n# Game immersion toolkit\n\n${switches}\n\n## ${t.title}\n\n${t.intro}\n\n**[${t.download}](${repo}/releases/latest)** · **[${t.online}](${site})** · [${t.guide}](${installPath})\n\n![Game immersion toolkit](public/proxy-transcript.png)\n\n## ${t.start}\n\n${t.steps.map((s,i)=>`${i+1}. ${s}`).join('\n')}\n\n## ${t.support}\n\n${overview}\n\n[${t.details}](${matrixPath}) · [${t.online}](${site}games.html)\n\n${t.assumptions}\n\n${sources}\n\n## ${t.modes}\n\n| | |\n| :--- | :--- |\n| **${t.desktop}** | ${t.desktopText} |\n| **${t.paired}** | ${t.pairedText} |\n| **${t.mobile}** | ${t.mobileText} |\n\n${t.helpText}\n\n## ${t.help}\n\n[${t.guide}](${installPath}) · [${t.matrix}](${matrixPath}) · [${t.coverage}](docs/game-ocr-presentations.md)\n\n[Contributing](CONTRIBUTING.md) · [Release](RELEASE.md) · [Security](SECURITY.md) · [License](LICENSE)\n\nCreated by [Firebird55](${repo}).\n`;
 output(locale==='en'?'README.md':`README.${locale}.md`,readme);
 let matrix=`<!-- Generated by scripts/generate-language-docs.mjs -->\n# ${t.matrix}\n\n${switches.replaceAll('](README','](../../README')}\n\n${t.legend}\n\n${t.assumptions}\n`;
 for(const g of catalog.games){
  matrix+=`\n<a id="${g.id}"></a>\n\n## ${g.name}\n\n[${t.source}](${g.source}) · ${g.reviewedAt??catalog.checkedAt} · [${t.coverage}](../${g.guide})\n\n${preparation(g.id)}\n\n${g.notes}\n\n<details>\n<summary>${t.details}</summary>\n\n| ${t.language} | ${t.voice} | ${t.study} | ${t.translation} | ${t.evidence} |\n| :--- | :---: | :---: | :---: | :--- |\n`;
  for(const code of [...new Set([...g.officialText,...g.study,...g.audio,...g.targets])]){
   const shared=code==='zh-Hant'&&g.study.includes(code)&&!g.textOnly;
   matrix+=`| ${name(code)} | ${g.captureCapabilities?.voiced===false?'—':g.audio.includes(code)?'✓':shared?t.mandarin:'—'} | ${g.study.includes(code)?g.textOnly?t.textOnly:'✓':'—'} | ${g.expectedTargets?.includes(code)?'◇':g.targets.includes(code)?'✓':'—'} | ${g.unverified[code]?t.unavailable:g.expectedTargets?.includes(code)?t.expected:g.playbackVerified?.includes(code)?t.playback:g.formatOnly?.includes(code)?t.formatOnly:t.implemented} |\n`;
  }
  matrix+='\n</details>\n';
 }
 output(matrixPath,matrix);
 output(installPath,`<!-- Generated by scripts/generate-language-docs.mjs -->\n# ${t.install}\n\n${switches.replaceAll('](README','](../../README')}\n\n${t.steps.map((s,i)=>`${i+1}. ${s}`).join('\n')}\n\n[${t.download}](${repo}/releases/latest) · [${t.matrix}](${locale}.md)\n\n## ${t.modes}\n\n**${t.desktop}:** ${t.desktopText}\n\n**${t.paired}:** ${t.pairedText}\n\n**${t.mobile}:** ${t.mobileText}\n\n## ${t.storage}\n\n${t.storageText}\n\n${storageNotes[locale]}\n\n${publisherSetup[locale]}\n\n| ${sourceGame} | ${translate('Windows Setup', locale)} |\n| :--- | :--- |\n${Object.keys(targets).map(id => `| ${catalog.games.find(game => game.id === id).name} | ${preparation(id)} |`).join('\n')}\n\n${roles.scope} [${platformGuide}](../desktop-platforms.md)\n\n## ${t.trouble}\n\n${t.tips.map(s=>'- '+s).join('\n')}\n\n${t.helpText}\n`);
}
console.log(process.argv.includes('--check')?'Language documentation is current.':'Generated four README, installation and language-matrix versions.');
