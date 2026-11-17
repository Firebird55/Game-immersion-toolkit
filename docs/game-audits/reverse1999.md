# Reverse: 1999 source and coverage audit

Status checked **2026-11-17**. Tracked in
[#144](https://github.com/Firebird55/Game-immersion-toolkit/issues/144).
This is provider research and tested public launcher discovery, **not a playable
toolkit adapter**. The game must remain unavailable for preparation until its
original text/voice pipeline and standalone Android path work.

## Official releases and languages

The [Global publisher website](https://re1999.bluepoch.com/) advertises 3.9.
Its current [bootstrap script](https://re1999.bluepoch.com/assets/js/api.js)
supplies the page version and game ID for the publisher's read-only website
version query. That query returns the original installer URL. Discovery reads
the current script each time; it does not freeze a game version or installer.

The [publisher Steam listing](https://store.steampowered.com/app/3092660/1999/)
lists English, Japanese, Korean and Simplified Chinese voice support. Traditional
Chinese has interface/subtitles and shares Mandarin recordings; it is not a
fifth independently recorded dub. The publisher's original client archive also
contains `CH`, `EN`, `GT`, `JP` and `KO` bootstrap locale files. This confirms
containers, not complete translation/recording extraction. German, French and
Thai named resource containers also exist in the current archive; file names
alone do not establish complete officially supported translations.

The [mainland publisher site](https://re.bluepoch.com/) advertises a different
release, 4.1. Its own
[bootstrap script](https://re.bluepoch.com/assets/js/api.js) and version query
return official Android links on `d.bluepoch.com`. Regional identity must stay
separate: Global 3.9 assets cannot stand in for mainland 4.1. An initial HEAD
request for that official APK returned HTTP 567; no current mainland APK or
regional text/voice playback has been verified.

## Publisher discovery implemented

`backend/reverse1999_release.py` uses Python's standard library. The initial
public app/channel profile was identified in the
[launcher profile implementation](https://github.com/Peebify-Launcher/peebify-launcher-lite/blob/0fdb84bf39d27a5128178475ef728ffb6dd22656/src-tauri/src/backend/game_profiles.rs)
and then verified against the live publisher service. That reference is protocol
research, not a runtime community dependency or source of game assets.

Public read-only queries to the publisher's
[`/diff-update/version`](https://hotupdate-hw.sl916.com/diff-update/version) and
[`/diff-update/resource`](https://hotupdate-hw.sl916.com/diff-update/resource)
returned **Global Windows 3.9.0, resource 111.0.1065**, with 20 original archive
URLs on `download.bluepoch.com`. Each URL carries its original size, expanded
size, MD5 identity, app/resource revision and archive part identity. Discovery
validates totals, ownership, region/version agreement, duplicate parts and
allowed HTTPS hosts. It rejects redirects and oversized/truncated metadata.

The ordinary module, rather than only a research script, performed all four
public discovery requests successfully. The resulting source fingerprint was
`52b2507337ac94ef69ce248cfa9090f45f76968d945c11f9535802a775cb0400`.
This is **one actual generation**, not an actual A-to-B update acceptance test.

| Exact manifest value | Bytes | Scope |
| --- | ---: | --- |
| Download | 29,139,635,761 | Complete original Windows client archives |
| Expanded | 33,181,309,025 | Complete original Windows client |
| Dialogue preparation download | Unknown | Selection and hotfix inventory unresolved |
| Prepared dialogue disk use | Unknown | No prepared catalog or decoded audio yet |

The complete-client numbers must never be shown as a dialogue-only download
estimate. Return values explicitly mark this distinction and
`dialogue_preparation_implemented = false`. No installer, original game code or
client executable is executed. The module does not download any archives.

Bounded research range reads of all 20 original 7z headers were validated with
their start/header CRCs. They expose original bundle, language, Lua container,
`allmanifest.dat`, video and audio paths. Those receipts are private metadata;
no original assets are committed. The headers use LZMA1; payload folders use
LZMA2 and, for executable files, an x86 filter. Large solid folders make efficient
selective extraction an open engineering issue. Header inspection is not proof
that a selected asset's full publisher MD5 has been verified.

A separately authorized range, bytes 32 through 16,385,589 of original archive
part 0, supplies the complete first LZMA2 resource folder: 16,385,558 compressed
bytes and 61,658,292 expanded bytes. Its decoded files pass their header-sourced
CRCs. The selected original `resources.assets` is 613,192 bytes, with observed
SHA256 `ca87f392cca30daf2b8e43f7c69226778522d7d0c1b5d4c5f7e3e908b9d3827a`.
This is still a partial archive read, not verification against the publisher's
whole-archive MD5 or an independently located resource-catalog hash.

`backend/reverse1999_bootstrap.py` now parses the evidenced stripped-type-tree
Unity serialized-file version 22 using only the standard library. Structural
inspection of that original resource finds 1,445 objects, including build ID
**73**, optional-voice branch **109** and resource version **111.0.1065**. The
embedded appversion is `0.0.1`; it must not replace the public launcher 3.9.0
identity. Reading these fields dynamically avoids freezing a voice branch.
The production consumption API requires an independently verified resource
SHA256 and release revision. That independent hash locator remains open, so
current research inspection does not enable production preparation.
The serialization layout was cross-checked against the format reader author's
[serialized-file implementation](https://github.com/K0lb3/UnityPy/blob/master/UnityPy/files/SerializedFile.py)
and [object table implementation](https://github.com/K0lb3/UnityPy/blob/master/UnityPy/files/ObjectReader.py),
then confirmed with the original resource bytes; UnityPy is not a runtime
dependency of this reader.

The publisher GameConfig asset named `bluepoch` contains a 2,176-byte payload,
which the production bootstrap reader preserves as opaque data. Original
key/decoder derivation is still required. Packing or one failed
request is not evidence that official derivation is impossible. No community key
fallback or game-key literal has been added. The reader never evaluates game Lua
or executes game native/managed assemblies. It rejects altered serialization,
overlapping objects, duplicate/missing fields and mismatched source identities;
the returned bootstrap record omits its GameConfig payload from its diagnostic
representation.

The launcher archive inventory is **not the in-game hotfix catalog**. A partial
patch query returned `0.0.0`; it is not accepted as the live version. Its complete
public bootstrap, response ownership and ordinary update behavior still need
verification. Account login, a running game or captured user credentials must
not become prerequisites.

## Original optional voice inventories

Private research cross-checked the original GameConfig payload against a
[pinned legacy format reference](https://github.com/hax0r31337/re1999-tools/blob/b2f2d4f27c4effe6ebae8275da732f226a159e69/text-assets.py).
The decoded original configuration identifies a separate publisher voice service,
`optionalres-hw.sl916.com`, and its backup. This research is **not official key
derivation** and has not introduced a community key dependency/fallback into
production. The official key locator remains open; no game-key literal is
committed.

An initial request sent to the launcher host had returned an authorization error.
That is **not evidence of an account/header requirement**: the correct original
optional-voice host serves the metadata publicly, without credentials or the
game's `x-sl-info` header. `reverse1999_release.optional_voices` now successfully
queries it using the current bootstrap voice branch. It requests fresh original
inventories, validates returned branch identity, original CDN scope, ZIP MD5s,
sizes and update orders, and keeps the base voice separately unresolved.

| Optional dub | Current original version | ZIP archives | Exact compressed bytes |
| --- | --- | ---: | ---: |
| Japanese | 109.131 | 3 | 2,756,808,065 |
| Korean | 109.130 | 5 | 2,810,706,837 |
| Mandarin | 109.130 | 3 | 2,816,769,030 |
| English | Original base pack required | Unresolved | Unknown |

These packs contain localized audio **and videos**. The numbers describe their
complete archives, not a dialogue selection or final decoded-audio disk use.
English is the Global default/base voice and was absent from the optional
response; it must not be classified as unvoiced or substituted with another dub.
The returned completeness flag stays false when a requested base voice is still
unresolved. Korean includes ordered cumulative archive layers; preparation must
apply the publisher's update order and validate the resulting current files.
The ordinary discovery call returned source fingerprint
`29576336dc4c4ee3feeff003ee96780f1d4d32055cd07d346a225efe01ba4574`.

Bounded reads of one original Japanese ZIP found a standard central directory
(802 entries, 74,844 bytes), including 771 BNK files. This allows ordinary ZIP
seek/deflate readers instead of requiring a Unity runtime for these audio packs.
One 4,485-byte original story bank passes its ZIP-file CRC and has Wwise bank
version 150, DIDX/DATA/HIRC chunks and embedded RIFF/WEM Vorbis audio (mono,
24 kHz). No extra bank decryptor was needed for this example. Full ZIP MD5,
authored text/event ownership, every bank layout, audio decoding/playback and
native Android acceptance remain unverified. No recording is published.

A separate research query for the client-described `res-HD` group returned one
publisher ZIP, version 109.130, 599,736,462 bytes, original MD5
`91221a5ef9a48a3f5d20585b3e92fded`. One bounded 65,557-byte tail read contains its
complete 3,573-byte central directory: 47 MP4 files under `videos/HD/`, two
directories and `res-HD.json`. It contains no indexed English bank or text-config
path. No member payload was downloaded and member CRCs/whole-ZIP MD5 were not
verified. **This group does not establish an English base acquisition route**;
that hypothesis stops. The group name came from the pinned format description,
while host/branch and the actual response came from original publisher data.
It is not added as a new final runtime feed or an automatic text-only download.

## Bounded initialization research and stopping points

The already acquired official installer prefix contains a complete NSIS header.
Static LZMA decoding and its authored extraction entries identify exact original
launcher-module/config ranges. Five targeted ranges transferred 251,395 bytes,
expanding to 655,753 bytes. Their LZMA block sizes and end markers agree; there
are no individual NSIS-file CRCs, neither managed DLL has an Authenticode
signature, and the whole installer hash and complete Authenticode file
verification remain unchecked. The
launcher files confirm current publisher app/channel parameters but do not
contain the legacy content-decoder key/IV literals. No assemblies are executed.

The original 7z file properties explicitly mark
`il2cpp_data/Metadata/global-metadata.dat` as an **empty file**, separately from
its parent directory. A bounded native-file prefix identifies GameAssembly PE
sections and an unusual large `.rsrc2` section. This is evidence for examining a
specific native-initialization resource, not permission to assume its contents
are readable metadata or that an official key route is impossible.

One subsequent streaming read reused the existing compressed prefix, stopped at
decoded folder offset 94,730,672, discarded preceding output and retained only
the first 64 KiB of `.rsrc2`. It received 18,874,368 new compressed bytes, below
its explicit 63 MiB upper bound. The valid `IMAGE_RESOURCE_DIRECTORY` identifies
one custom `CFG/130/2052` resource: 25,449,372 bytes beginning at GameAssembly
file offset 94,245,476. Its inspected prefix does not establish a plain IL2CPP
metadata header or a verified reversible envelope. **This `.rsrc2` hypothesis
stops here**; no whole-resource literal/key scan follows. The whole GameAssembly
and archive hashes remain unverified. A complete preceding generic Unity
`baselib.dll` matches its 7z file CRC and has a valid Unity Authenticode signature;
it is not evidence for a game-specific decoder key.

Two bounded file-index URL hypotheses under the original `massHotUpdate` host
both returned HTTP 404: `/60001/Windows/configs/allmanifest.dat` and
`/60001/configs/allmanifest.dat`. No further path variants were tried. Provenance
is deliberately separate: the host comes from the original GameConfig, game ID
from original publisher configuration/API, the `/gameId` joining behavior from a
pinned community initialization description, and the relative manifest path from
the original 7z header. Neither guessed complete URL is an established official
download route. These failures do not demonstrate corruption, a package format
change, an authentication requirement or the absence of every official route.

The original `RuntimeInitializeOnLoads.json` and `ScriptingAssemblies.json` were
also read from the existing resource-folder bytes and checked against their 7z
file CRCs. Their Unity/Steam/render initialization and assembly inventories do
not supply a self-contained content-key derivation or base/hotfix schema. They
are static metadata; none of the listed initialization methods was executed.

The data-only `reverse1999_unity_owner.py` reader now cross-checks a
MonoBehaviour's serialized type/script-table entry against its actual `m_Script`
pointer, resolves the original external-file identity, and reads the referenced
MonoScript's namespace, class and assembly. Replaying the existing resource bytes
identifies the encrypted configuration carrier as
`SLFramework.GameConfigAsset`, assembly `Assembly-CSharp`, owned through
`globalgamemanagers.assets`. The scene's initial component is
`ZProj.ProjMain` in the same declared assembly. These are authored type-ownership
edges, **not a verified method call from startup to the configuration decoder**.
No fixed scene/object IDs or instance-name match is used by this reader; its
payload remains opaque. The original 20 archive indexes do not contain a
standalone `Assembly-CSharp.dll` path. Compiled or embedded code is not ruled out.

A separate typed read of GameAssembly's PE import descriptors, names and thunks
finds 13 nonzero descriptors for Windows system libraries and Unity `baselib`.
They establish no static import of another game-specific configuration decoder;
all referenced import metadata fits the retained 64 KiB window. That hypothesis
stops without searching unrelated modules. A final bounded entrypoint read
retains 4 KiB at the PE-authored entrypoint. After 14 statically decoded x64
instructions, execution would reach an indirect `call r9`; the preceding code
derives that target from the image base and an external DWORD. Analysis stops at
this unknown indirect edge, without emulation, further reads or packer
reconstruction. The new replay received 18,677,760 compressed bytes and retains
that private compressed range for exact reuse. These partial reads do not verify
the whole archive's MD5 or GameAssembly's full file CRC, and do not demonstrate
that official key derivation is impossible.

## Official Android-owner alternative

A separate metadata-only investigation follows publisher-authored Android links,
without revisiting the stopped Windows indirect-call route. It uses nine new
HTTP requests and 822,784 response bytes; no APK, native library or signing-block
bytes are acquired, and website JavaScript is read as data only.

The Global version-page response's Android link,
`https://reverse1999.onelink.me/Rh0f/ujn2ppo2`, returns HTTP 301 to Google Play's
`com.bluepoch.m.en.reverse1999` listing. A bounded 512 KiB listing prefix is
incomplete and does not establish an APK URL, package checksum or signer. Do not
infer that the entire store page lacks such metadata from this prefix.

The original mainland version response links to
`https://d.bluepoch.com/prepage/Reverse1999_Bluepoch_1006.apk` and to the original
`download.html` page with `Reverse1999_Bluepoch_1020.apk` in its `rbDL` parameter.
The complete 2,497-byte landing page statically confirms that Android follows
that parameter. Original site `api.js` also declares the advertising-channel
`prepage/bdsem/reverse1999_bluepoch_bdsem_200401.apk` link. All three exact APK
HEAD requests return HTTP 567 with an HTML error type. Their reported lengths
belong to error pages, **not APK sizes**, and no publisher package checksum or
signer is established. These failures neither establish permanent source
unavailability nor authorize an exceptional community key.

The same original mainland response explicitly links to the
[TapTap application page](https://www.taptap.cn/app/221062). Its complete
239,932-byte server-rendered page contains this current distributor descriptor:

| Field | Original descriptor value |
| --- | --- |
| Application identity | `com.shenlan.m.reverse1999` |
| Version / code | `4.1.0` / `180` |
| APK identifier | `1073124` |
| APK name | `com.shenlan.m.reverse1999-180.apk` |
| Compressed size | 1,990,140,900 bytes |
| Distributor MD5 | `b72b01d12251ef65e1a7a4b9d3a6118b` |
| Declared native ABIs | `arm64-v8a`, `armeabi-v7a` |

This is publisher-linked distribution metadata, not a verified whole-APK hash,
an independent publisher signing identity, or a manifest of native modules.
The page supplies no game APK URL. Its original download-button modules hand
off to the TapTap client; the structured-data `d.taptap.cn/latest` link denotes
that store client, not Reverse:1999. Existing exact shared API-definition bytes
were reused only after their full length/MD5 check; no game mappings or keys
were reused. Those definitions do not supply an Android package-transfer URL.
The site's original game-website link returns to the publisher landing page.
No guessed CDN URL, arbitrary API variant or account request follows.

The next bounded source step needs an actual authored APK transfer descriptor.
Only after that URL, total length and source identity are established can an
APK-tail/central-directory plan identify the real Unity resource, metadata and
native-owner entries. Any signing-block read must distinguish reading a
certificate from verifying package integrity and independently trusting its
publisher identity. Exact index/module ranges and new byte budgets must be
derived from the original owner structures before further acquisition. The
current evidence does not establish an Android `GameConfigAsset` initializer
or key; no Android source is accepted into the production provider yet.

The subsequent browser-route investigation reuses complete original source
modules after their length/MD5 checks and parses JavaScript syntax without
executing it. `AppButton.client`'s download case calls its authored `kt` handler,
then `Jn.androidDialogDownload`. The latter passes an app-module URI with
`app_id` to the store-client handoff. The independently fetched complete
`web-to-client.C-pNXRtT.js` (87,562 bytes, original Content-MD5 verified) builds
`taptap://taptap.com/app` and the public `dispatch.taptap.cn/taptap` address.
An anonymous request derived from that exact contract, using the known game ID
and no account/session cookie, returns a complete 5,070-byte "Download TapTap"
HTML page. Its original dispatch module (132,134 bytes, original Content-MD5
verified) derives `apkDownloadUrl` from the **store-client**
`d.taptap.cn/latest` base plus a store channel. The game ID is handoff/jump
context, not a proven game-package transfer descriptor. No analytics, account or
native bridge operation is invoked.

The original route table also identifies `/app/:id/signature`. Its complete
page and small original module read `app/v5/information.signature_data_list`,
separately from a catalog of applications with signature information. The
complete current Reverse:1999 response does not contain that list. It therefore
adds no signer proof or APK URL for this game; catalog entries for other games
are not substituted. The exact remaining step is resolving the game's known APK
identity into its actual transfer URL through an original public descriptor,
or another publisher-authored route. That native store-client step is not
established by these browser sources. It is not filled with an invented API.
That browser/maintenance phase uses eleven requests and 415,005 new metadata
bytes, including the fallback-source check below; no package/native bodies are
acquired in that phase.

### Bounded store-client component inventory

The original store-client fallback subsequently resolves by HEAD from
`d.taptap.cn/latest` to a 30,390,849-byte store APK on `rls.tapurl.com`. This is
distribution-tool research, **not an official Reverse:1999 package source or
game-key proof**. The hexadecimal filename token and multipart ETag are not
treated as whole-file checksums or publisher signing identities.

Separately approved, strict same-owner/ETag HTTP ranges acquire only a
65,557-byte EOCD tail and its exact 421,652-byte central directory. Their valid
single-disk ZIP structures index 6,208 entries, including seven DEX members.
One further bounded member read consists of the 49-byte original local header
and 44,912 compressed bytes of `AndroidManifest.xml`. Its DEFLATE stream expands
to exactly 480,736 bytes and passes its complete original member CRC. No other
member, native library or DEX body is read. The final continuation total,
including browser/maintenance metadata, HEAD requests and these approved reads,
is seventeen requests and 947,175 transferred bytes, within its 1 MiB limit.

Static Android binary-XML parsing establishes package `com.taptap`, application
`com.play.taptap.application.AppGlobal`, and these publisher-declared store
components:

| Kind | Declared owner |
| --- | --- |
| Service | `com.taptap.game.export.download.TapAppDownloadService` |
| Provider | `com.taptap.game.export.download.PreDownloadProvider` |

Those declarations identify download-related components; they do not prove a
network request producer, an accountless game APK API, or a mapping to one of the
seven DEX files. The whole store APK checksum/signature remains unverified. No
component or client is executed. The bounded store route stops here. A later
targeted hypothesis would need the exact declared class's DEX location and its
original request-production edge; downloading all seven DEX files blindly is
not accepted as the next step. The game's APK URL and original configuration
initializer remain unresolved.

### Community key candidate: research only

The original author repository
[hax0r31337/re1999-tools](https://github.com/hax0r31337/re1999-tools) is not
archived and reports a last push on September 9, 2026. Its decoder file was last
changed by [the June 23, 2024 decoder commit](https://github.com/hax0r31337/re1999-tools/commit/a43705eb2c7ce543ebe18bd5707363b22c9c34e6).
The current 498-byte `text-assets.py` contains the same two cryptographic
literals as the existing pinned research reference, compared through Python AST
data inspection only. No downloaded code is executed and no key material is
published or added to the provider.

This is a fixed-literal candidate, not an evidenced revision-aware key service.
Recent repository activity alone does not establish decoder/key maintenance.
The missing official derivation step is still not proven impossible or
unavailable, so the candidate remains unapproved research and does not activate
a production fallback. Even a later authorized exception would still require
original source/version/integrity validation and the unresolved content readers.

## Other regional publisher navigation

A separate investigation follows only actual publisher navigation and store
links. The Global landing page loads `bpFooter.en.js`, whose language choices
link to the Japanese site. The permanent Global homepage's original config
also names its Japanese and mainland homepages. The Japanese desktop/mobile
footers link back to English/Japanese; the inspected mainland footer and its
original website query establish no additional KR/TW publisher-navigation
edge. No regional hostname, path or game ID is guessed. This is the limit of
the inspected navigation chain, not proof that other official editions do not
exist.

The Japanese site's original `api.js` declares `gameId: 70001` and version page
`3.9`. Both its authored version-page request and permanent-home game query
confirm the following links:

| Field | Original Japanese publisher result |
| --- | --- |
| Android link | `https://reverse1999jp.onelink.me/XuII/ltt1kw5x` |
| Android redirect | Google Play, `com.bluepoch.m.jp.reverse1999.and` |
| PC installer | `https://download.bluepoch.com/jp/Reverse1999_v3.9.0.5_jp.exe` |
| Installer version / length | `3.9.0.5` / 357,407,088 bytes |

The Android redirect supplies no accountless game-APK transfer descriptor. The
installer responds publicly with HTTP 200 to HEAD and supports ranges. Its
multipart ETag is an owner-version token, not a verified file MD5. No ordinary
whole-file checksum is supplied by these website responses.

Separately approved reads acquire exactly 4,096 PE-header bytes and the
header-declared 12,016-byte `WIN_CERTIFICATE` table, under strict HTTP 206,
matching total length and the actual ETag. The security table begins at file
offset 357,395,072. Passive SignedCms verification validates its CMS signature;
the embedded X.509 code-signing certificate identifies
`BLUEPOCH GAMES CO., LIMITED`. The Windows code-signing chain validates offline
with certificate downloads disabled. **Revocation is not checked.** The signed
SPC indirect-data record declares this expected **Authenticode** SHA-256 digest:

`8060a1843df27f2dd6650c7816ce1cf734f603e63a455ee0541e659a1fc36517`

That value is publisher-signed expected file-digest metadata. The complete
installer has not been downloaded or hashed, and its complete Authenticode
file verification has not been performed. It is not a computed plain SHA-256
of the full file or proof of any unread payload's integrity. No installer code,
assembly or client is loaded or executed; this host-cryptography research is
not Android runtime acceptance.

An independent, zero-download replay of the already cached Global installer
certificate also validates its CMS signature/offline code-signing chain, with
the same revocation limitation. Its signed expected Authenticode SHA-256 is
`785cb5a9c4aa5b977ce2e8ddeb37b3daae99034df01a5e31b6ebf413be40d23c`.
That is separate Global ownership evidence, not an assertion that Global and
Japanese installer bytes or contents are identical.

The actual mainland permanent-home query additionally names
`/home/Reverse1999_Bluepoch_1000.apk` and a download-page parameter containing
`/home/Reverse1999_Bluepoch_1019.apk`, both on `d.bluepoch.com`. These are newly
observed authored links, not guessed variants. Both HEAD requests return HTTP
567 HTML errors and add no APK size/checksum evidence.

This regional phase uses twenty-two requests and 236,067 new response bytes,
including the specifically approved PE/security metadata. It downloads no APK,
DEX, complete executable or native library. The approved 4 KiB prefix spans its
1 KiB PE headers and 3 KiB of following stub-section bytes; those section bytes
are neither analysed nor executed. The new Japanese installer is a real
accountless publisher source with version, length and signed expected-digest
metadata. Its necessary GameConfig consumer/bootstrap module has not yet been
established or read, so the key/base/hotfix gap remains open. No community-key
fallback or production readiness is enabled by this checkpoint.

### Original Japanese/Korean launcher configuration

The next explicitly approved JP-installer read checks its 32-byte NSIS
firstheader at file offset 184,832. The declared compressed header is 56,511
bytes at 184,864 and expands to exactly 1,023,200 bytes with strict LZMA EOF and
no trailing compressed bytes. The original instruction/string tables identify
these configuration owners; branches are not executed:

| Authored owner path | Compressed block, including size prefix | Expanded bytes |
| --- | ---: | ---: |
| `runtimes/web/assets/ja/launchermanifest-jp.ini` | 1,066 | 2,143 |
| `runtimes/web/assets/ko/launchermanifest-kr.ini` | 920 | 1,874 |

Only those two separately approved config blocks are read and parsed as inert
data. Their declared lengths and strict LZMA framing/EOF agree; no per-file NSIS
CRC exists and the full installer hash remains unverified. The entries name no
standalone GameAssembly, global-metadata, Assembly-CSharp, GameConfig or
libil2cpp payload. This does not rule out embedded code or establish an active
game-config consumer.

The actual configuration supplies the following production identities without
guessing regional game/channel IDs:

| Profile | Game / channel / subchannel | Language | Original production website |
| --- | --- | --- | --- |
| Japanese | `70001 / 300 / 6002` | `ja` | `https://re1999.bluepoch.com/jp/home` |
| Korean | `90001 / 202 / 6004` | `kr` | `https://reverse1999.haoplay.com/` |

Both name `https://hotupdate-hw.sl916.com` as their production updater. Their
SDK hosts are respectively `https://gamesdk-jp.sl916.com` and
`https://gamesdk-kr.haoplay.com`; no account/SDK operation is called. Applying
the already evidenced ordinary updater metadata contract to those original
parameters gives independently owned client inventories:

| Profile | Reported base version / resource revision | Archives | Complete-client compressed / expanded bytes |
| --- | --- | ---: | --- |
| Japanese | `3.9.0 / 111.0.1067` | 20 | 29,112,314,082 / 33,175,073,230 |
| Korean | `3.6.5 / 111.0.907` | 10 | 25,200,090,518 / 28,785,835,609 |

The original URLs' game IDs, version/revision identities, part uniqueness and
archive size sums agree with their respective publisher responses. No archive
or game payload is downloaded and whole-archive MD5s are not verified. These
are complete-client inventories, not text/audio selection estimates.

The Korean website reached through its actual config is live and advertises
version 3.9, an original `dl.haoplay.com/kr/Reverse1999_v3.9.0.5.exe` installer
and Google Play package `kr.haoplay.game.and.reverse`. Its reported base 3.6.5
and website/launcher 3.9 are kept separate: their base/hotfix relationship and
current content revision remain unresolved, rather than being automatically
classified as stale or corrupt. No guessed target version is sent.

After this config and ordinary-metadata checkpoint, the conservative shared
regional/distributor ledger is 37 requests and 715,859 response bytes. The two
configs and installer index establish original regional bootstrap paths, not a
decryption key or game text/voice bindings. No fallback, prepared snapshot or
Ready state is enabled.

### Publisher-linked game APK descriptor and transfer stopping point

The existing mainland publisher response also explicitly links to
[the 3839 listing](https://www.3839.com/a/136385.htm). That complete listing
links its [mobile page](https://m.3839.com/a/136385.htm), whose original inline
JSON `downInfo` supplies an actual **game** APK descriptor, independently of the
previous store-client handoff:

| Field | Distributor-authored result |
| --- | --- |
| APK URL | `https://hot.71acg.com/release/hykb/202610/20261030reverse1999180_268.apk` |
| Package | `com.shenlan.m.reverse1999` |
| Distributor MD5 | `69718ac8e18427491e6cf33a0ed8146f` |
| Listing version | `4.1.0` |

The listing's rounded `1.85G` size is not an exact owner length, selected
text/audio estimate or proof of retained disk use. The distributor's MD5 is
neither a verified downloaded-file checksum nor publisher-authenticated signing
provenance. No equality with the separate TapTap APK is assumed.

HEAD, a separately approved exact `Range: bytes=0-0` GET, and an approved
ordinary GET inspecting headers only all return HTTP 405 with a 906-byte HTML
error response. No body is read for any of those APK requests. Its error-page
ETag is excluded from APK owner identity. Thus no exact APK length, real owner
ETag, readable archive index, signer or GameConfig module is established. The
ordinary GET result is not solely a Range-header rejection. This transfer route
stops without further header permutations or guessed URLs; the responses do not
prove permanent unavailability, an account requirement or impossible official
key derivation.

The complete regional/distributor investigation totals twenty-eight requests
and a conservative 593,452 transferred-byte budget, within 1 MiB. This includes
a 131,073-byte upper-bound charge for the first listing read whose size check
failed before its response was retained; the subsequent complete listing is
retained separately. Game-APK payload bytes remain zero. A reachable original
game-package owner, or an original prescribed delivery step for it, is still
needed before proposing exact ZIP-index and key-consumer member acquisitions.

## Text versus text and audio planning

`backend/reverse1999_game_data.py` exposes the shared host factory
`create_provider(platform=..., native=...)`; `reverse1999_provider.py` implements
its conservative publisher-discovery stage. The ordinary factory uses the shared
`PublisherTransport` with explicit original hosts, bounded GET/JSON POST metadata
and context byte accounting. Tests inject that transport's opener explicitly;
no global monkeypatch or unaccounted default network client is needed. Transport
network failures can use the existing original publisher backup; consent and
semantic failures cannot silently switch sources. Android, Windows, Linux and
macOS host factories share this data-only stage; this is not native game/audio
acceptance on each host.
Requests, private handles and revision identities distinguish `content_mode`
values `text` and `text-audio`. Old handles without the mode require repair;
this adapter does not modify saved history.

Text-only planning makes no optional-voice query, audio archive request or audio
resolve call. Its selected audio bytes are explicitly zero. Selected text/shared
bytes stay unknown; text-and-audio bytes also remain unknown while the original
text/base path is incomplete. Full-client inventory numbers are kept solely as
private source evidence and never become the selected download estimate.

The stage has `runtime_available = false` and cannot return a snapshot or mark
the game Ready. Mainland planning does not fetch Global data. Unknown estimates,
unsupported source preparation and failed freshness checks keep existing data.
Integration checks use the committed shared content-mode request and the real
`GameDataService`/`PublisherTransport`: both modes expose unknown selected sizes,
keep source-only handles private and refuse download/activation without creating
a dialogue snapshot. No fake prepared game or successful source proof is used.
This is an honest shared-protocol adapter for the proven discovery stage, not
independent content preparation. Root integration owns shared registry and
transport changes.

## Finite dialogue coverage boundary

Inventory current accessible dialogue and official regional languages. Do not
spend indefinitely on orphaned references, removed event content or audio without
captions. None of the following is implemented or classified as silent yet:

| Presentation to verify | Required authored evidence |
| --- | --- |
| Story conversations, narration and choices | Story group/step text IDs, translation IDs, authored voice event IDs and explicit silent choices |
| Character voice/archive and battle/ambient captions | Character/event/locale binding; confirm which sounds actually have visible captions |
| Event and other side-story presentations | Current entry points and the same original step/audio schemas, including moving text |
| Cinematics and text over videos/images | Original caption timing, locale tracks, audio ownership and independent screen regions |
| Readable pages/messages and special layouts | Current accessible text tables and explicit voice state |

Static schema research identifies story step/group JSON inside original Unity
bundles, and audio configuration fields for bank and event names with overseas
variants. These are leads for original-file validation, not implemented bindings
or permission to substitute community audio. Missing recordings stay unknown or
missing-pack; they must not become unvoiced by inference. Short repeated text
must use authored scene/step context where available.

## Remaining implementation and acceptance

- Complete original bootstrap/key/hash discovery and mandatory Global/mainland
  hotfix/base inventories. Global Japanese, Mandarin and Korean optional
  inventories are now publicly queryable without a local voice pack.
- Read the original selected metadata, translations, story layouts and audio
  event/bank/media relationships without evaluating game Lua or binaries.
- Implement portable archive/bundle/localization readers and original audio
  decoding, then exercise them inside the Android runtime. Standard-library
  discovery alone is not Android extraction or playback acceptance.
- Integrate the common Android/PC data manager: per-game download/delete,
  manifest-based transfer estimate, actual retained bytes, cancellation,
  interruption recovery and previous-complete-catalog retention.
- Prove two actual publisher generations without new external extraction or a
  toolkit update. Synthetic ordinary-version fixtures already cover discovery.
- Add support registry, detection/setup/capture/export regression coverage,
  public game metadata, README/install instructions and generated language
  guides when a functioning adapter is ready. Keep this issue open meanwhile.

The 85 owned synthetic fixtures currently exercise public metadata decoding,
ordinary-version and voice-branch refresh, announcement-insensitive launcher
fingerprints, original archive ownership and totals, bootstrap boundaries,
mandatory/optional voice distinctions, update order, malformed/oversized data,
network fallback, shared transport byte accounting, cancellation before a
connection, content-mode isolation, incomplete-stage nonactivation and
HTTP response integrity. No game text, recordings, keys or executable files are
test fixtures. No installed-game or physical-device playback is claimed.
