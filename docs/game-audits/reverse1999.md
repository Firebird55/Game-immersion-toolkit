# Reverse: 1999 source and coverage audit

Status checked **2026-11-18**. Tracked in
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

### Store-client signing identity: separate from package integrity

A subsequent, separately bounded metadata stage follows the exact public
`https://pub.taptapdada.com/api/changelog` GET authored in the retained original
dispatch JavaScript. Its complete 1,297-byte JSON response supplies Android
version code `296161002`, matching the original store manifest. It contains no
package URL, length, checksum or signing identity. Display-version punctuation
differs between the JSON and manifest and is not treated as byte equality.

The original manifest also declares an HTTPS `autoVerify` intent filter for
`dispatch.taptap.cn`. Its protocol-derived
[Digital Asset Links document](https://dispatch.taptap.cn/.well-known/assetlinks.json)
returns 330 bytes of strict JSON naming exact package `com.taptap` and this
SHA-256 signing-certificate fingerprint:

`4fd67062300d3d9d6c384f7e4e512df4a9a32d165fcb3526428c8e9e3d4e44b7`

One further approved same-owner HTTP range reads only the 694-byte local ZIP
block for `META-INF/GAMECENT.RSA`. Exact local-header fields, raw DEFLATE EOF,
915-byte expanded length and member CRC 3529842923 pass. Passive CMS decoding
finds one certificate and one signer; both match that original domain-declared
fingerprint. Certificate identity alone does not authenticate a DEX member.

Three separately approved exact ranges then acquire only the `.SF` local block
and the original `MANIFEST.MF` local header/body: 477,504 additional bytes.
Their local fields, DEFLATE EOF, expanded lengths (527,105 and 526,981 bytes)
and complete original member CRCs pass. Detached CMS verification over the
**exact `.SF` bytes** succeeds with the domain-pinned signer. The signed
`SHA-256-Digest-Manifest` matches the complete original manifest, whose 6,205
named entries include `classes.dex`. The retained original Android manifest's
SHA-256 also matches its authenticated member entry. The authenticated expected
`classes.dex` SHA-256 is:

`9e64a00c5855302d1d795562355cb1238925742b440a899e3562d2d1f6fd873b`

This proves a signed expected digest, **not verification of the still-unread
DEX, a computed whole-APK checksum or Android's complete installation-signature
acceptance**. Trust is explicitly the original HTTPS Digital Asset Links
declaration; no certificate-chain revocation check is claimed. The store signer
does not authenticate the game's different APK descriptor or establish a game
key.

This stage transfers 479,825 bytes in six requests. No DEX/native body is read
and no client code is executed. A later separately bounded downloader-consumer
investigation must first verify its acquired member against that signed digest.
The manifest does not locate the declared components in a particular DEX;
primary-DEX placement remains a hypothesis, not permission to read all seven.

### Complete bounded locator for the declared store components

A separately approved primary-DEX hypothesis first reads its 41-byte local
header and 3,345,229-byte compressed payload. The 8,692,172-byte original member
passes its ZIP CRC, authenticated manifest SHA-256, raw DEFLATE EOF and DEX
SHA-1/Adler32. Header, identifier-table and map bounds also pass. None of the
three exact manifest classes is defined in its 10,019 formal class definitions;
that primary-only hypothesis stops without method-body inspection.

A new **complete class-owner locator** is then explicitly bounded to the other
six indexed DEX members. Their exact adjacent local blocks form one range of
16,151,569 bytes, comprising 16,151,317 compressed bytes and six 42-byte headers.
No unrelated archive entry is included. Every original local header, length,
CRC, signed manifest SHA-256, raw EOF, DEX SHA-1/Adler32 and header/map bounds
passes before exact formal class matching. The 47,933,912 expanded bytes are
processed one member at a time, with at most 9,237,536 expanded bytes present;
negative temporary members are removed. Only the bounded compressed input is
retained for subsequent source-owned reads.

| Exact manifest component | Authenticated defining member | Declaration evidence |
| --- | --- | --- |
| `com.play.taptap.application.AppGlobal` | `classes2.dex` | Class definition 5,707, superclass `BaseAppContext` |
| `com.taptap.game.export.download.PreDownloadProvider` | `classes4.dex` | Class definition 10,033, superclass Android `ContentProvider` |
| `com.taptap.game.export.download.TapAppDownloadService` | `classes4.dex` | Class definition 10,034, superclass Android `Service` |

Only formal declarations and method metadata are inspected. The service declares
non-native `onStartCommand` and `onBind`; the provider declares `query` and a
private method returning `com.taptap.game.export.f`. These are concrete consumer
owners, **not established call edges or a game-APK resolver**. No method body,
generic URL/string/key scan or client execution is performed. The locator closes
the standard seven-DEX ZIP inventory, without claiming closure for dynamically
loaded, encrypted, generated or native code.

The separate store-integrity/locator phase now totals nine requests and
19,976,664 transferred bytes. This is authenticated store-tool research;
Reverse:1999's game-package URL, original configuration initializer and production
preparation remain unresolved. The full store-APK hash and Android installation
signature acceptance remain unverified. The next bounded hypothesis is the
declared service callbacks' own typed delegation, using existing bytes only.

### Cache-only service delegation boundary

Separately approved static reads revalidate the complete signed `classes4.dex`
hash and inspect only four declared service methods: `onStartCommand`, `onBind`,
the constructor and `onCreate`. Their exact instruction arrays total 68 DEX code
units / 136 bytes; code-item headers, register/invoke references, instruction
boundaries and branch destinations pass. There are no exception-handler tables
in these methods. No original code is executed and no new network bytes are
needed.

The callbacks null-guard the service's field `a`, typed as
`com.taptap.game.export.e`, then invoke that interface's matching callback. The
constructor establishes the actual assignment: `ARouter.navigation` receives
the exact class operand `ITapAppDownloadServiceProvider`; after a cast/null guard,
its `createTapAppDownloadServiceProxy()` result is stored in field `a`.
`onCreate` only delegates initialization to the same instance.

**This pass stops at that returned interface factory.** Its concrete registration,
implementation and game-download request contract have not been read or proved;
no automatic callee expansion follows. The chain is source-owned delegation,
not an anonymous APK API, account requirement, native barrier or proof of
impossible official key derivation. The authenticated compressed input plus one
retained original `classes4.dex` occupies 24,995,265 bytes for this phase, within
the approved 26 MiB retention limit. Reverse:1999 preparation remains unavailable
in both content modes.

A later separately approved **metadata-only** locator follows the exact
`ITapAppDownloadServiceProvider` interface operand through all seven authenticated
DEX members. Two passes reach a fixed point over direct interfaces and
superclass inheritance. There is exactly one concrete candidate:
`com.taptap.game.downloader.impl.download.notification.TapAppDownloadServiceProvider`,
class definition 9,266 in `classes4.dex`. The interface itself extends ARouter's
`IProvider`. Original interface lists are bounded but sometimes unsorted; lookup
preserves their original membership without claiming canonical ordering.

No candidate method metadata or body is read in that phase, and no network or
additional retained file is needed. Formal metadata alone does not establish
the ARouter registration map. The next source-owned method candidate is this
implementation's `createTapAppDownloadServiceProxy()`; its declared code location
and actual return producer are checked in the separately bounded pass below.
A unique interface implementer is not treated as an anonymous game-download
request.

### Bounded concrete factory and conditional metadata-request chain

The exact candidate factory is subsequently read from the same signed cache:
method 52,177, code item 4,984,264. Its six code units / twelve bytes allocate
`com.taptap.game.downloader.impl.download.notification.j`, call that object's
constructor, and return the same object. The constructor body is not read.
Formal metadata confirms that `j` implements the service proxy interface and
`PreDownloadService$b`.

A separately bounded follow-up inspects eight source-owned methods, totaling
1,766 instruction bytes within an eight-method / 4,096-byte ceiling. The exact
`j.onStartCommand` body alone is 928 bytes, with its separately approved 16-byte
try table and eleven-byte handler list. The batch checks each full signed DEX
hash and register/invoke, instruction, branch and exception-handler bounds;
its total exception metadata is 32 try-table and 35 handler bytes. No constructor
body, original execution, generic URL/key scan or new request is involved.

The source-owned chain reaches `notification.a.a(AppInfo, Function0)`, concrete
coroutine bridges and finally `com.taptap.game.common.net.f.e`. Its caller passes
the exact path operand `/app/v1/mini-multi-get`, a map key `ids`, and response
class `com.taptap.common.ext.support.bean.app.f`. **The pass stops at that network
owner and the eight-method limit.** Its request builder is not read; no base
host, HTTP method, headers, accountless availability or actual response is proved.

This is a conditional **level-info-update** branch, gated by the original
`AppInfo.isLevel` and related-game state. Reverse:1999's actual branch value is
unresolved, so the path is not claimed as its ordinary APK delivery route.
The proxy also receives existing `download_id` and `app_info` values from an
Android intent. Its separately instantiated callback `j$b` is examined in the
finite follow-up below. The exact `ids` value comes through another source-owned
`AppInfo` helper whose body remains unread. These concrete boundaries do not
establish a game-package URL, official GameConfig initializer or usable catalog;
both content modes remain unavailable for preparation.

The level-info branch stops without reading its HTTP builder or making a
request. A separately approved normal-callback batch instead checks four exact
methods, totaling 182 instruction bytes within its four-method / 2,048-byte cap:
`j$b.invoke():Object`, `j$b.invoke():void`, `notification.b.l(downloadId, info)`
and `notification.b.c(downloadId, AppInfo)`. Every step revalidates the signed
member hash and register/invoke/instruction/branch bounds; no constructor or
network operation is performed.

The observed chain performs auxiliary notification bookkeeping with an already
supplied ID: notification records, timestamps, `AppInfo` maps and a widget
callback. It then calls `notification.b.p(downloadId)`, which remains unread.
No APK/source request, URL construction or creation of a new download ID is
observed in these four methods. This finite branch stops without a claim about
the unread callee or the whole application.

The notification callback does not construct its incoming task ID. The separate
source-owned locator below establishes the service Intent's writer, while the
actual task/descriptor origin remains unresolved. Neither auxiliary branch
establishes impossible official derivation or activates a community-key fallback.

### Exact service-Intent producer and download-center caller

A metadata-only inventory of the exact `TapAppDownloadService` type finds only
two carriers among all seven authenticated DEX members: `classes4.dex` and
`classes6.dex`. One formal `const-class` operand lookup is restricted to those
carriers. Their 111,648 code items and original method declarations pass numeric
instruction, payload, branch and handler bounds; 5,999,758 instruction bytes are
width-walked in 3.907 seconds. This is an exact type-operand index, without generic
strings, endpoints, keys or semantic constructor/callee inspection. Gross existing
source I/O is 83,551,012 bytes, including a recorded stopped reader preflight and
repeated source-hash validation, within the separately approved 128 MiB ceiling.
No server bytes are transferred.

The lookup identifies three `notification.i` methods in `classes4.dex` and one
separate store self-upgrade method in `classes6.dex`. Only the exact normal
candidate `notification.i.d(Context, String, AppInfo)` is then inspected:
280 instruction bytes, 24 try-table bytes and nine handler bytes. Its signed
source and typed bounds pass. The other three candidate bodies remain unread.

| Original service Intent field | Authored source |
| --- | --- |
| Target component | `TapAppDownloadService` |
| `app_info` | The incoming `AppInfo` object as a Parcelable |
| `download_id` | The incoming String argument, unchanged when nonempty |
| `app_id` / `app_title` | Optional `AppInfo.mAppId` / `mTitle` compatibility fields |
| `fg_service` | SDK/lifecycle-dependent service-start state |

The method invokes the source-owned `notification.g.a(Context, Intent)` helper
or Android `Context.startService`, including a direct start-service fallback.
It creates the service Intent, **not a download URL or a new task ID**; no helper
body is inspected.

A second exact owner/signature inventory and formal invoke-operand lookup finds
the service writer's single direct caller in the indexed DEX space:
`com.taptap.game.downloader.impl.download.DownloadCenterImpl.x(String, AppInfo)`,
method 52,041 in `classes4.dex`. Its header declares eight code units / sixteen
instruction bytes; its semantic body remains unread at this checkpoint. This
bounded pass revalidates 65,469,780 existing bytes, width-walks 3,114,348 instruction
bytes and completes in 2.047 seconds, without network requests or other semantic
body inspection.

The genuine remaining upstream target is now that download-center caller's
source for the supplied `AppInfo` and download ID. Starting the service with
forwarded values does not prove their APK metadata origin. No official game APK,
GameConfig initializer, English base/hotfix catalog or content preparation is
accepted from these partial source proofs.

### Download-center task/configuration boundary

A separately bounded upstream phase checks eight exact bodies / 1,112 instruction
bytes, below its eight-method / 8,192-byte ceiling. Their total exception metadata
is eight try-table and six handler bytes. Signed source hashes and typed register,
invoke, instruction, branch and handler bounds pass for every step. No constructor,
notification-service branch, network request or original execution is involved.

The sixteen-byte `DownloadCenterImpl.x` forwards its two incoming values. Its
only own-class caller is an eight-byte synthetic accessor `g`. Formal
`EnclosingMethod` / `EnclosingClass` annotations establish the exact compiler
members of this class without relying on a namespace guess. Restricted accessor
lookups across those proven members identify `DownloadCenterImpl$b$a.run` as
the caller. The two formal passes cover 80 code items / 6,966 instruction bytes
in 0.171 seconds, within the 1,024-item / 1 MiB / two-minute limit.

That runnable and its exact task-builder accessor establish these source paths:

| Value or operation | Authored source / remaining boundary |
| --- | --- |
| Download ID passed to service startup | `extensions.c.f(AppDownloadService$a)` uses a non-null supplied option ID; otherwise it calls still-unread `c` / `a` fallback helpers |
| `AppInfo` passed to service startup | The runnable reads `DownloadCenterImpl$b.a`; that field's initialization remains unread |
| Existing task configuration | `b.h` calls `GameDownloaderService.getApkInfo(id)` and reuses the returned task |
| New task configuration | `b.h` calls `GameDownloaderService.createApkInfo(AppInfo, type)` |

The exact service facade and companion resolve
`ARouter.navigation(GameDownloaderService.class)`. Formal interface/inheritance
metadata over the seven signed DEX members finds two concrete candidates in
`classes4.dex`: `GameDownloaderServiceImpl` and `GameDownloaderServiceLoaderProxy`.
The registration binding is not yet proved, so neither candidate's method body
is chosen or read. The phase stops at its eight-method limit.

This is genuine task/configuration ownership, rather than another notification
consumer. The next original source boundary is the router's concrete provider
binding for `createApkInfo`, followed by that evidenced descriptor producer.
The option-ID fallbacks and captured `AppInfo` initialization remain separate,
explicit provenance gaps. No actual APK URL, request contract, game key or
preparable catalog follows from the unresolved interface; both content modes
remain unavailable.

### Original routed delegate and title/icon refresh

The bounded annotation pass reads only the two exact candidates' original
class annotations: 603 metadata bytes, apart from necessary signed-source hash
validation. `LoaderProxy` alone has the original runtime-visible
`@Route(path="/game_downloader/service")`; `Impl` has only
`SourceDebugExtension`. The authored proxy reads its typed
`$$delegate_0: GameDownloaderServiceImpl` and directly calls that final
implementation. Generated provider-index activation and runtime router
execution remain unverified.

The implementation's task factory calls `requestApkInfo`, which launches the
owned coroutine. Its relative path is `/app/v1/mini-multi-get`, with `ids` and
response model `com.taptap.common.ext.support.bean.app.f`. A later complete
response-consumer pass **corrects the earlier interpretation of this helper**:
it copies only the returned app's title and icon into the task. It does not
supply an APK transfer URL or replace the task's file descriptor. This branch
is stopped; its name is not APK-delivery evidence.

The exact ID helper selects the literal `default` button flag and reads
`appLaunch.appId`, returning null when absent. There is no fallback to
`AppInfo.mAppId`. The retained Reverse:1999 SSR has no such launch value; no
website ID is substituted. That absence does not imply the page lacks a file
descriptor.

For completeness, this stopped branch's static request-contract pass proves a
POST request-model enum and conditional plugin identity in the input map. It
does not establish absolute host, transmitted headers, authentication,
accountless availability or a working game request. Its eight selected bodies
total 580 instruction bytes. No endpoint is called or client code executed.

### Native APK descriptor and actual file-source boundary

The exact original `AppInfo$URL` class is uniquely defined in the signed
`classes3.dex`. Its field annotations bind `mId` to JSON **`md5`** and `mSize`
to **`size`**. `mId` must therefore not be interpreted as a literal URL or the
page's numeric APK identifier. The already retained publisher-linked
[TapTap page](https://www.taptap.cn/app/221062) contains those exact descriptor
fields for its primary, default mainland APK, with the previously inventoried
MD5 and **1,990,140,900-byte** size. Its separate nonprimary cloud-game variant
is excluded. This is a native-schema match for existing distribution metadata,
not a computed game-APK checksum or a transfer URL.

The selected task factory copies this size and passes the MD5 to its original
source object's setter. That setter only stores the value. The original enum
switch, numeric selector getter and initializer establish the concrete regular
`LOCAL_TOTAL` route: type 1 selects `bd/e`; the different `SANDBOX` type 3
selects `bd/g`. This follows the authored branch rather than choosing an
implementation by name. The ordinary source `bd/e` inherits `getUrl`, which
only returns a stored field. Its own `y()` returns local storage search paths,
not network descriptors; that local-search branch is stopped. No source URL is
constructed by the inspected methods.

This real-source phase stops at its eight-body limit: 736 instruction bytes,
32 try-table bytes and 19 handler bytes. Each selected body is checked against
its complete signed DEX hash and typed instruction, register, branch and
handler bounds. All DEX input is existing signed cache, and the SSR is the
existing publisher-linked response; new origin bytes and client execution
remain zero. The remaining concrete boundary is the source's
`FileDownloaderType` and the consumer that populates or resolves its
stored URL from the MD5/size descriptor. No anonymous delivery route, original
game module, key, text/audio catalog or Ready state is established.

A research-reader correction is retained explicitly. An earlier locator
incorrectly assumed DEX `class_defs` were ordered by type index and reported
the shared base source absent. A dependent metadata fallback then exceeded the
64 KiB metadata allocation before finding that exact class; this is not a
successful within-budget phase or a game-format failure. No unrelated method
body or network data was read. The reader now requires a verified numeric
class-definition index and stops on locator failure. A separately approved
262,020-byte index pass covers all 65,491 original class definitions in the
seven signed DEX members without reading names or bodies. Rechecking the five
relevant earlier locator results changes only that base-class false negative;
the other definitions remain unchanged. The overrun and failed preflight
checks remain recorded. The independently verified signed model annotations
and retained SSR descriptor are not reclassified as a transfer proof.

### Concrete download-engine and descriptor-fetch consumer

The next exact source getter returns `FileDownloaderType.APK`. A formal
operand-only inventory for the three approved `tc.d` method signatures finds
only `classes4.dex` as a carrier and six call sites for its type getter.
`getUrl` and its setter are not declared under that interface owner; the actual
engine uses the inherited `tc.b.getUrl` operand. This is an owner distinction,
not a failed source format. The complete signed source and formal instruction,
payload, branch and handler checks pass for the positive carrier. The bounded
locator consumes a conservative 78,617,063 existing bytes in 2.078 seconds;
there is no generic string, URL or key search.

One concrete consumer, `downloadv3.e.r`, directly calls `downloadv3.f.m`.
That engine reads the stored URL, creates `tapfiledownload.core.b` and calls
`start()`. Its preparatory `f.d` only handles local reset state and is stopped.
Before engine construction, `e.r` also delegates through `impl.a.h` and `g`
to `downinfo.a.c`, which calls the actual file-info fetcher `downinfo.fetch.c.i`.
These are original typed edges, not a claim that every runtime setting selects
this engine.

The actual fetcher builds a file-info parameter map plus a separately
delegated context map, allocates the exact `fetch.c$a` coroutine and uses
`runBlocking`. This is a different producer from the stopped title/icon helper.
The next bounded pass below establishes its native ID input, relative request
paths and concrete source-URL assignment. It does not establish current live
parameter values, absolute host, transmitted identity or accountless behavior.

This consumer phase stops at eight bodies / 3,174 instruction bytes, 72
try-table bytes and 26 handler bytes, with the original signed-source and typed
bounds checks. New origin bytes and code execution remain zero. The next source
step is the exact allocated fetch coroutine and its concrete request/response
owners, not another broad store-client or Windows packed-code search.

### Original APK-detail paths and response-to-source assignment

The exact allocated fetch coroutine dispatches between `/apk/v1/detail` and
`/apk/v1/detail-with-user` after examining account login state. The ordinary
path calls the same source-owned `common.net.f.e` and POST-model transport
already examined independently. The context-map helper has also been read;
no concrete device/account values are collected or copied. These static edges
do not prove that a live accountless request succeeds, or that account
credentials are needed for the ordinary path.

Only necessary original initialization is read. The task factory takes
`Download.getMApkId()` when present, otherwise `AppInfo.apkId`; its value flows
through the task field, the exact downinfo constructor and the exact fetch
constructor into the request's `id`. The earlier URL-model `md5` is a different
value and is not substituted. The exact `AppInfo.apkId` annotation is only
`Deprecated`, with no demonstrated JSON-name annotation. That fallback does
not establish the page-to-native ID binding. The next original-model pass below
instead closes the primary download getter's own schema; absence of a fallback
annotation is not evidence of an impossible official route.

The complete response collector stores the typed file-info response. Its
consumer `downinfo.a.m` delegates the ordinary source assignment to
`downinfo.c.e`, which passes `fetch.b.a()` directly to `tc.b.setUrl`. The
separate patch path has its own typed getter. This establishes an actual
response-to-source assignment, rather than a title/icon update. The next
original-model pass below identifies the exact nested JSON URL member before
any live response is consumed.

That eight-body phase reaches the exact `compat.net.c.v` default wrapper and
its `c.u(FlowCollector, e7.d, int, Continuation)` delegate. The next bounded pass
below covers that implementation and its external configuration boundary. No
detail endpoint is called and no header, ID or hash URL is guessed.

This phase stops at eight bodies / 2,302 instruction bytes, eight try-table
bytes and six handler bytes. Explicit fail-fast metadata accounting records
40,792 bytes including exact owner locators, declarations, necessary
initializers, typed references and the negative annotation result, below the
64 KiB allocation. Each original DEX hash and method bounds is verified. The
earlier reader overrun remains recorded separately; this later metered pass
does not erase it. New origin bytes and original-code execution remain zero.
Preparation, all regional text/audio coverage and normal-update acceptance
remain open, with no Ready state or community fallback.

### Native primary ID, nested URL schema and injected transport

The original primary `Download.getMApkId()` getter returns its own field with
`@SerializedName("apk_id")`. That exact key is already present in the retained
primary default `download` record: **1073124**, tied to the same package, MD5
and size. This now establishes the native request-ID binding for that cached
record through the previously proven constructors and input map. It does not
use the deprecated fallback, website app ID, MD5 or absent native launch flag.
This remains one retained generation, not a fresh live-detail response.

The exact URL getter returns its original `@SerializedName("download")` field.
The response-envelope getter returns the `@SerializedName("apk")` member, whose
original subtype formally inherits that URL model. The ordinary assignment is
therefore **`apk.download` within the typed file-info payload to the source's
URL setter**, closed through original getters, annotations and inheritance.
The outer wire-response conversion, whole game-APK verification and live
consistency with the declared MD5/size remain pending.

The exact `compat.net.c.u` implementation creates a Retrofit service from its
stored Retrofit instance and calls its typed request interface. Registered
interceptors receive the request maps before dispatch. This method does not
construct the base host or establish the actual transmitted headers. A separate
operand-only check of the exact owner's 30 methods finds the three writers of
the two relevant private configuration fields: one constructor and two public
configuration methods. Only those positive writers are then inspected. The
constructor creates an empty interceptor list; `c.n(Retrofit, Retrofit)` and
`c.A(Retrofit)` only store externally supplied instances. They do not supply a
base URL. The next original-source pass below traces their concrete callers
and first actual builder. No anonymous request succeeds merely because a
non-user relative path exists.

The separately approved writer locator validates exactly 4,942 instruction
bytes and 344 try-table bytes in those 30 owned methods, with full formal
instruction/payload/handler checks: 11,096,520 existing bytes including
compressed input and full signed-source verification, 0.062 seconds. It reads
no unrelated class bodies, generic strings, URLs or keys. The direct semantic
phase stops at this configuration boundary after seven bodies / 2,288
instruction bytes, 192 try-table bytes, 40 handler bytes and 37,087 metered
metadata bytes. Previous failed or superseded interpretations remain recorded;
no earlier overrun is recast as a pass. No origin request, game/client execution,
Ready state or fallback activation occurs.

### Original initialization callers and first Retrofit builder

The exact configuration-method caller pass finds `common.net.g.c`, which
forwards the two supplied Retrofit instances and registers a concretely named
`common.net.b` interceptor. Its only ordinary caller is the original `g.b`
wrapper. The latter has three original call owners: `other.basic.impl.c$a.a`,
`InitHelper.doLiteTask` and `TapOtherExportBisServiceImpl.initTapApi`. These
remain separate initialization paths; no lite or exported-service path is
promoted to the active normal path on the strength of its name.

All three exact caller bodies obtain **both** Retrofit arguments from the same
`other.basic.impl.application.c.e()` method. That actual maker constructs a
`Retrofit.Builder`, supplies `baseUrl` from the original common-library domain
provider, adds a Gson converter, supplies an OkHttp client from its own `c()`
helper and calls `build`. This closes the chain from the detail request to a
real original builder, rather than stopping at parameter-forwarding wrappers.
The OkHttp/helper and interceptor header production remain separately unread.

The exact base-URL getter reads its own static string. Its necessary original
static initializer fills that string through
`BaseAppContext -> IAppConfiguration.getUriConfig() ->
IUriConfig.getDomain("DOMAIN_MAIN")`. It supplies no demonstrated literal
hostname or verified default. The next original-metadata pass below closes
the domain-service implementation and generated registration, then reaches the
separate environment configuration. A broad URL or selector-string search is
not substituted for that ownership chain. No accountless request is attempted.

The cumulative semantic phase closes at eight bodies / 1,392 instruction
bytes, 56 try-table bytes, eleven handler bytes and 27,452 metered metadata
bytes. Its two verification allocations remain separate and explicit: the
first finishes at 128,450,214 bytes within 128 MiB; the later approved
second-carrier pass reads 12,061,025 bytes within 16 MiB, reusing the already
verified immutable `classes3.dex` in memory. The latter formal pass closes both
positive carriers in 4.063 seconds. All later method reads reuse verified RAM
and numeric owner/invoke indices; the counters are not reset to conceal prior
reads. No new origin bytes, game/client execution, fallback or Ready state.

### Concrete domain-service binding and environment source

An exact formal interface/superclass graph over all 65,491 standard DEX class
definitions finds two concrete `IUriConfig` implementations: `startup.dependency.e`
and its subclass `k`. Both use the same original 38-byte `getDomain` method;
the subclass does not override it. That method reads no instance configuration
field. It obtains `TapOtherExportBisService` through its companion, delegates
the selector unchanged, and returns an empty string if the service/result is
absent. This is not a hostname or proof that two runtime environments have the
same values.

The companion's lazy supplier calls `ARouter.navigation` with that exact
service interface. The candidate implementation's original annotation declares
`/other_export_bis/service`, and it directly implements the export interfaces.
Annotation/name agreement is not used alone as provider selection. A single
compiler-owner hypothesis was absent from the retained two DEX members; this
was not classified as whole-package absence. Formal `IProviderGroup` metadata
then locates all 37 actual generated registries in the primary DEX, with their
real interface-method declarations and bounded headers.

A const-class operand pass over only those 37 methods, 5,392 instruction bytes,
finds one reference owner for the exact implementation class. Only that positive
344-byte registry body is read. Its original `Map.put` entries explicitly bind
`com.taptap.other.export.TapOtherExportBisService` and the second export
interface to `RouteType.PROVIDER`, `TapOtherExportBisServiceImpl.class` and the
matching authored route. This proves the generated interface-to-provider
binding; runtime activation is still not executed or inferred.

Only after that binding, the implementation's ten-byte `getDomain` is read.
It delegates to `other.basic.impl.net.r.b`. That method maps the already proved
`DOMAIN_MAIN` selector to its own stored domain string. The original `r.d`
initializer, called before the builder in the three retained initialization
paths, populates that value directly from `IEnvConfig.getApiDomain()`, with
exception handling. The precise remaining host producer is now that environment
provider and its concrete selection. No fallback/static-initializer value or
runtime hostname is assumed. OkHttp/header production and outer wire-response
conversion remain separate open points.

The URI-config metadata pass uses 53,039,663 combined verification/metadata
bytes within 80 MiB; the registry pass uses 53,049,618 within 64 MiB. Both read
metadata only and keep their allocations distinct. The shared 38-byte method
and its owner quote use 3,123 metadata bytes within a separate 4 KiB bound. The
registration/producer phase closes at eight bodies / 904 instruction bytes,
40 try-table bytes, fourteen handler bytes and 20,232 metered metadata bytes.
Its later method reads reuse verified immutable RAM and numeric indices. No
new origin requests, game/client execution, whole-game-APK verification,
community fallback or Ready state is claimed.

The next environment-selection phase follows the exact `cl.a.b` getter. It
reads a public static `IEnvConfig` field and throws if that field is unset;
no default domain is established. A formal field-write pass over only the
owner's thirteen methods (382 instruction bytes) finds its six-byte setter.
The setter receives one of two explicit `IEnvConfig` parameters from the
118-byte `init` method, selected by `isRND()`. This establishes the parameter
selection, not the concrete objects supplied by initialization callers.

The retained primary DEX has no reference to that exact `cl.a.init` signature.
The already validated invoke indices for the third and sixth DEX members
contain no caller. A separate, metadata-only check of the remaining four
signed members also finds no reference to that concrete owner/signature,
using 37,923,650 existing-file verification bytes and 2,290 metadata bytes.
This closes only direct invokes of that concrete method in the seven standard
DEX members. The original class metadata declares `IEnvConfigService`. An
exact query for the same signature under that interface, using only retained
metadata and the existing invoke indices, finds one concrete startup caller
in the sixth DEX. That separate query uses 2,891 metadata bytes without a new
source scan or cold read. Interface dispatch explains the earlier concrete-
owner negative result; it is not evidence of missing initialization.

The separate body phase closes at three bodies / 148 instruction bytes and
9,909 metered metadata bytes, entirely from authenticated immutable RAM.
The later four-member metadata pass reads no bodies and retains no additional
source member because there is no positive carrier. Neither phase uses new
origin bytes.

The next bounded phase reads the positive 150-byte startup caller. It obtains
the already bound export provider's environment service and passes the
original `n3/a` and `n3/b` configuration fields, together with three explicit
false Boolean arguments. The provider's six-byte `getEnvConfig` returns the
same `cl.a` service. Its 46-byte `isRND` takes the false branch for these
arguments without invoking the conditional runtime helper. Combined with the
previously inspected `init` selection, this proves which supplied
configuration this authored call selects; it does not assume a runtime
default or assign the alternative configuration the same host.

Only that selected configuration's 26-byte `getApiDomain` is then read. It
uses `Context.getString` on the original `R$string.api_domin` field. Exact
encoded-field metadata supplies its Android resource identifier. No hostname
is inferred from the resource name, and the unselected configuration remains
unread. This phase closes at four bodies / 228 instruction bytes, ten
bytes of explicit already-approved constant-operand rereads and 6,700 metered
metadata bytes. A failed private input-owner check and its bounded metadata
reconstruction remain included in that count; the original source is intact.
All reads in this phase reuse authenticated immutable RAM, with no new cold
source or origin bytes.

A separate resource-source phase rechecks the original 526,981-byte manifest
against its already CMS-bound SHA-256 and obtains the exact signed
`resources.arsc` member digest. Three strict same-owner/ETag range requests
read 44 local-header/name bytes, two declared zero alignment bytes and the
2,065,876-byte stored resource member: 2,065,922 transfer bytes in total.
The complete member matches both that signed SHA-256 and its original ZIP
CRC before resource interpretation. The two alignment bytes are qualified as
padding, not incorrectly claimed to form a complete extra-field TLV.

Formal lookup follows only resource identifier `0x7f100021`, already read
from the signed DEX. It has one string entry with the default configuration
and value `https://api.taptapdada.com`; no alternate configuration or alias is
present for this identifier. The runtime table key is `_`, rather than the
DEX field name `api_domin`. The binding is numeric, so equality of these
symbolic names is not required. An initial private post-parse equality check
was too strict; that reader limitation and both 2,713-byte interpretation
passes remain recorded without classifying the original bytes as corrupt.
No unrelated strings are decoded and no locale is guessed.

This establishes the host supplied by this authored initialization and
resource configuration. It does not prove runtime activation, request-header
construction or the outer response envelope. The source remains the signed
distribution tool, not a verified Reverse:1999 game APK. No whole-APK checksum,
installation acceptance, game/client execution or live detail request is
claimed; both preparation modes remain discovery-only.

The following header-contract phase follows the exact OkHttp factory used by
the proven Retrofit builder. Its original client getter delegates to its own
builder, which registers concrete interceptors. One inspected interceptor
passes the ordinary initial request unchanged to `proceed`; its exceptional
recovery helper is not followed. Formal retained type metadata places two
other concrete interceptors in the fifth DEX, which is not currently retained
in RAM. No cold read or speculative method choice is made for those owners.

The already inspected native request transport also invokes the exact
`Le7/a.c` request callback. Its original registration constructs
`common.net.b`; the constructor's actual field assignment binds the supplied
`v3.e` provider. The three previously examined initialization paths all pass
the same concrete `application.features.a` field as that provider. Its
inspected `h` method has request-flag-dependent account handling, a nullable
login/token path and further header delegates. The pass stops at these
concrete configuration/account boundaries: login getters, account state,
device values, delegated header generation and unretained interceptor code
are not followed or reused. Conditional account code does not establish that
the anonymous detail route requires an account; its actual request flags
and remaining header contract still need proof.

This separate phase closes at six bodies / 1,380 instruction bytes, forty
try-table bytes, twelve handler bytes and 12,443 metered metadata bytes. All
source reads reuse authenticated immutable RAM, with zero new cold or origin
bytes. A failed cache precondition and a dependent missing-spec attempt read
no source bytes and remain recorded as analysis-tool boundaries. No request
header values are published, and no endpoint request, device/account data use
or TLS/hostname/pinning change is introduced.

A separate flag pass follows the actual detail route through the POST wrapper,
its default-argument method, request-model construction and both original
constructors. All four Boolean inputs are false at creation. The exact
request getters used by the header callback read their corresponding stored
fields and return false. This is proved parameter/field dataflow, not a
Boolean default guessed from the anonymous endpoint name. The pass uses eight
bodies / 302 instruction bytes and 11,403 metered metadata bytes, entirely
from retained authenticated RAM. It does not alone establish the final
anonymous request contract.

The next phase closes the inspected default callback's optional-mutator
assignment: the original registration wrapper passes exactly null. One
two-byte operand in the previously checked callback also proves that its
last Boolean argument to the header feature is false. That selects the
ordinary SDK base-map branch. The SDK method constructs `time` and `nonce`
entries using separate generators; their values and generator bodies are
not read. The prefix-list-dependent parameter transformations in the
feature's `w` method remain unresolved.

The concrete header-finalization method `j` has a further source-owned
boundary. For a nonempty header map it calls a map-to-byte helper and then
`common.net.utils.NativeHttp.getSign(Context, byte[])`, storing the result in
the `sign` header. Null results and failures retry up to three times before
an exception; no unsigned fallback is inferred. Exact declaration metadata
confirms that `getSign` is native with no DEX code body. The native library
is not read or executed in this phase. This is a demonstrated native
producer boundary, not proof that official derivation is impossible.

The source-bound anonymous endpoint candidate is
`https://api.taptapdada.com/apk/v1/detail`, with the already proved native APK
identifier binding and a POST request model. Exact wire encoding,
map-to-byte canonicalization, remaining header/transport producers,
absent-login handling and the outer response envelope remain open before any
live request. The later phase closes at four whole bodies plus the single
two-byte operand: 372 instruction bytes, eight try-table bytes, three handler
bytes and 5,939 metered metadata bytes. It uses zero cold source reads or
origin bytes, follows no account/token/device contents, and introduces no
endpoint request or preparation-ready claim.

The next narrowly scoped pass reads only the native wrapper's 150-byte
managed initializer. It supplies the exact `tap-net` library name to SoLoader
and, on that loader's failure, to `System.loadLibrary`. Its environment
selector is explicit and is not substituted with a guessed runtime value.
The pass uses sixteen try-table bytes, five handler bytes and 1,441 metered
metadata bytes from retained authenticated RAM, with no new cold or origin
bytes and no native execution.

The existing original APK directory has matching `libtap-net.so` members for
both ARM64 and ARMv7. Rehashing the existing 526,981-byte manifest against its
CMS-bound digest authenticates the two exact member-digest sections, 200
bytes in total. The ABI members have distinct sizes/digests; equality between
them is not assumed. At that metadata-quote checkpoint neither native payload
had been acquired; neither a complete APK hash nor installation acceptance
is asserted.

The subsequent ARM64-only acquisition uses two strict same-owner/ETag range
requests: 57 local-header/name bytes and 6,939 compressed bytes, with no
extra field. Raw Deflate expands to exactly 17,768 bytes with strict EOF,
and the whole member matches its original ZIP CRC and CMS-bound SHA-256.
The ARMv7 payload is not acquired. Formal ELF metadata establishes an
AArch64 ELF64 little-endian shared object with 24 sections, nine program
headers and ten dynamic symbols. The 3,137-byte interpretation finds no
exact short/long JNI `getSign` export, but does find an owned 248-byte
`JNI_OnLoad` function; no native code is interpreted in this inventory pass.

Only that 248-byte registration function is then statically decoded. Its
PC-relative class/table references and 479 original relocation/class/method
metadata bytes prove a four-row `RegisterNatives` table. The exact
`NativeHttp.getSign(Context, byte[]) -> String` row identifies its original
implementation address. JNI slots and structure layout are checked against
the existing primary NDK headers. No generic string/key search or native
execution is used. A separate 222-byte unwind-header pass proves the
implementation's own 284-byte extent; a neighbouring exported function is
not used to guess its end.

The exact 284-byte implementation is then decoded as data only. It passes
the supplied Java `Context` to two helpers and checks cached results before
the direct byte-array helper. The returned buffer goes through the typed
JNI `NewStringUTF` slot. No context/account/device values, comparison
literals, helper bodies or signature algorithm are read in this pass.
Three actually called PLT stubs, 48 code bytes and 283 formal
relocation/symbol/name bytes, identify only `malloc`, `strcmp` and `free`;
no C-library implementation is followed. Another 290-byte unwind-header pass
quotes the three positive helper extents as 616, 216 and 388 bytes. All three
bodies remain unread at this checkpoint.

This closes the original signing-function owner chain, not the signer or
the anonymous wire contract. Java-context dependence in this source does not
establish a requirement for a real device, account or game installation.
Portable derivation, the context-helper semantics, request/header
canonicalization, other transport interceptors, absent-login handling and
the response envelope still require proof. No live endpoint is requested,
no unsigned fallback is enabled and no preparation-ready state is introduced.

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

### One original Korean base-client archive inventory

The next approved metadata-only probe targets only Korean base 3.6.5 archive
part 0: 4,773,351,938 compressed bytes, publisher MD5
`db28988fa73b1732b23fcc9ef2af1159`. HEAD agrees on length and returns that value
as its strong ETag; the complete file is not downloaded or MD5-verified.
Strict same-owner ranges read a 32-byte 7z start header, 40-byte NextHeader and
55,877-byte encoded header. Start/NextHeader CRCs and the 931,754-byte decoded
header CRC agree. This known-size raw-LZMA1 header has no EOS marker: exact
declared output size/CRC and no unused data establish its format boundary;
Python's decoder `eof` is explicitly false, not misreported as true.

The index identifies a distinct regional native-file inventory:

| Owner | Korean base metadata | Existing Global metadata |
| --- | --- | --- |
| `GameAssembly.dll` | 126,610,944 bytes; CRC 868644893 | 126,319,616 bytes; CRC 84286124 |
| `global-metadata.dat` | Explicit empty **file**, not a directory | Explicit empty file |

The Korean resource/globalgamemanagers metadata also differs. No standalone
Assembly-CSharp/libil2cpp file is declared. These are original file-index
comparisons, not verified whole-module hashes or a readable key-consumer proof.
The archive's first solid folder contains 5,147 subfiles (4,667,235,457
compressed / 4,787,591,367 expanded bytes, LZMA2). Its separate native folder
starts at compressed offset 4,667,235,489, contains 29 subfiles and uses
LZMA2 with a 32 MiB dictionary plus x86 BCJ (106,060,532 compressed /
345,341,131 expanded bytes). GameAssembly begins at native-folder decoded offset
419,760 after baselib. No folder/member body or other nine archives is read.

This inventory transfers 55,949 metadata bytes in three body requests. The
conservative combined regional ledger becomes 41 requests / 771,808 bytes.
It remains evidence for the reported base 3.6.5, not proof of the website's
current 3.9/hotfix content. Any native-header read needs a separately bounded
plan; no opaque Global code scan, key fallback or Ready state follows.

A subsequent separately approved **single** native-folder prefix request is
capped at 262,144 compressed bytes and stops after exactly 423,856 decoded
bytes. It actually receives 180,224 bytes, checks the complete preceding baselib
CRC 2294769330, and retains only the bounded input plus a 4,096-byte GameAssembly
prefix. Only PE directory/section metadata is inspected. Its headers occupy
1,024 bytes; the following 3,072 section bytes are not analysed or executed.
The AMD64 module again has zero CLI/security directories and the opaque
`.Sgxm0` / `.Sgxm1` / `.tvm0` / `.rsrc2` section pattern alongside its empty
metadata file. This bounded probe establishes no readable alternative consumer.

**The regional native line stops at that boundary.** No literals, keys,
disassembly, resources, entrypoint or further module bytes are inspected. The
complete archive MD5 and GameAssembly CRC remain unverified; the generic Unity
baselib CRC is not game-key proof. The conservative regional ledger finishes
this branch at 42 requests / 952,032 bytes, below 1 MiB. The result does not
prove that every official key derivation route is impossible and does not
authorize a community-key fallback or prepared game.

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
