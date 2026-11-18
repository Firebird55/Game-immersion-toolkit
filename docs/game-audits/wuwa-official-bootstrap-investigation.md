# Wuthering official bootstrap investigation

## November 19, 2026 · Standalone release manifest continuation

All checked original mirrors still serve encrypted ENTRY metadata. The shared
Windows and Android provider now continues from its verified bootstrap with
the existing immutable Mornye Tools format pin. It reads exactly the two
parameter declarations as data, verifies the whole source file SHA-256 and
keeps those parameter bytes in memory. Plain publisher JSON bypasses the
compatibility source. The provider retains a digest for provenance.

The new stage verifies the launcher inventory MD5, both original PAK index
SHA-1s, the bootstrap config and the official resource and four dub
manifest SHA-1s. It also verifies both publisher KeyList/PakData routes
and rechecks the original entry, platform, key lists and launcher inventory.
Protected content indices still require authorization by their own hashes.

An empty shared Windows provider verified the 1,396,149,288-byte publisher
carrier. A transient Windows certificate-chain error was corrected through
the existing Kuro CA trust path. The retained stage then verified active
Global 3.8.12 and 598 package references using 1,591,828 bytes. Kuro serves
launcher metadata with gzip encoding even after an identity request. The
transport bounds and charges its wire bytes before the launcher parser
validates the decoded document and declared checksum.

The verified manifest is an intermediate receipt. Portable dialogue-table
selection and preparation, original voice acquisition and playback, and
Android update and recovery remain subsequent acceptance steps. Future
ENTRY rotations require a reviewed replacement pin or an official derivation.

## November 18–19, 2026 · Fresh Global Windows discovery and portable manifest reader

Ordinary Windows publisher discovery completed from an empty toolkit cache
with no installed game. The original 1,396,149,288-byte APK carrier passed
APK-v2 verification. Its authenticated module supplied the archive default.
The original Global bootstrap PAK passed both complete index hashes and
supplied the live entry URL. The official 3.8.12 resource and English 3.8.6,
Japanese 3.8.5, Korean 3.8.8 and Mandarin 3.8.5 dub inventories passed the
publisher-declared SHA-1 checks. Discovery verified 598 manifest entries and
rechecked three current pointers.

Normal Global library preparation with the packaged vgmstream decoder completed
for every study selection. English, Japanese, Korean, Simplified Chinese and
Traditional Chinese produced 144,130, 144,182, 144,028, 145,782 and 144,880
rows, respectively. One original recording per dub decoded to nonzero PCM.
Both Chinese scripts selected the same original Mandarin performance. The
English sample also matched its original hash from a fresh process with
publisher requests disabled.

Five reachable entry mirrors returned byte-identical encrypted entry metadata,
and four publisher content mirrors returned byte-identical encrypted platform
metadata. Normal discovery and language preparation now recheck the selected
entry response with the platform and key pointers. A redirected resource root
during preparation causes the candidate to be rejected before publication.

The existing immutable community pin supplied the ENTRY parameters. Its URL
and SHA-256 were verified. The reviewed v1.1.0 source declares the same
parameters. A separate authenticated symbol-table check found four-byte
Encrypt and Decrypt method entries and their reflection wrappers. Those
entries still leave the original ENTRY parameter producer unresolved. The
original publisher APK catalogue timed out earlier and later returned HTTP 200.

The ordinary Windows manifest reader and portable PAK reader now use the
toolkit publisher-crypto interface. The manifest reader validates PKCS#7
padding before parsing a JSON object. The portable PAK reader requires
explicit host cryptography and verifies both original index hashes before
exposing a newly derived default. Android still requires a verified ENTRY
input and the app-level manifest continuation before native acceptance.

[Global launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json)
· [Kuro Global 3.8 platform config](https://cdn-akamai-hw-mc.aki-game.net/prod/client/zXGBurT1FHY5eBpEhgbCw7n85imvi3XR/Windows/config.json)
· [Reviewed compatibility revision](https://github.com/Yumeo0/mornye-tools/blob/36761bfe2618c7f28488abe457e162a711170290/src-tauri/crates/game-client/src/discovery.rs).

## November 17, 2026 checkpoint

The original Android bootstrap/default producer is now implemented as a
bounded, address-independent static reader and connected to ordinary publisher
preparation. The fully authenticated current original module opens both complete
original Global bootstrap indices without legacy/community inputs. This is
**not complete cold preparation**: encrypted release JSON still depends on
separately frozen/protected `ENTRY_KEY`/`ENTRY_IV` format inputs. Actual default
key rotation and independent Android runtime acceptance remain unverified.
Failure must retain the previous library, with a typed source/key error rather
than an invented format change.

This checkpoint supersedes the early negative Windows probe and pending update
trial in [the historical recovery note](wuwa-publisher-recovery.md). The retained
3.7.19 → ordinary-live 3.8.11 changed-text, translation, original-audio,
interruption and offline-restart trial subsequently passed. It does not prove
unknown-key derivation or cold Android preparation.

## Original source evidence

The current Global launcher bootstrap PAK has a **v12 encrypted main index and
zero FGuid**. Its original footer agrees with both retained complete main and
directory SHA-1s. Those retained indices are authenticated original data; their
availability does not demonstrate keyless cold opening. The currently verified
default value is absent from the original resource KeyList's 14 records and
video KeyList's 248 records. Neither list contains a zero UUID. UUID-owned keys
must therefore not be tried as unrelated defaults.

The original Global Shipping executable is now fully authenticated: its
104,857,600-byte first chunk and 61,402,632-byte second chunk pass their publisher
MD5s, as does the complete 166,260,232-byte file. The earlier separate header and
consumer samples agree with it. Passive inspection of the concrete `Decrypt`
and `LoadKeys` owner windows did not establish a readable initialization rule.
No client code was loaded or executed. This bounded negative result is not
proof that official derivation is impossible; repeating opaque samples is not
an implemented resolver.

Sources: [Global launcher manifest](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json),
[publisher download page](https://web-static.kurogames.com/mcDownloadPage/index.html)
and [publisher main website](https://wutheringwaves.kurogames.com/en/main).

## Independent distribution investigation

The publisher website's original mobile page links to
[TapTap app 234280](https://www.taptap.cn/app/234280) and
[Haoyou app 143964](https://www.3839.com/a/143964.htm). These establish an actual
publisher-to-distributor link, not the authenticity of any native module.

* The original publisher transfer script provides a concrete credentialless
  download-JSON contract. The exact mainland route timed out during the bounded
  probe. A format-derived Global counterpart returned 404; it was not an
  independently authored current Global APK link. These are availability
  observations, not proof that no official route exists.
* Haoyou's mobile page names an Android game APK, package identifier and MD5.
  The first one-byte range request returned 405 before any APK body was read.
  The distributor's checksum and official-server label do not establish a
  publisher signing certificate. No ZIP directory, signed manifest or native
  module was accepted.
* TapTap's public structured data exposes a store-client installer link; it
  must not be mistaken for the game's APK. Complete checksum-verified API and
  app-detail modules identify an app-information GET with the actual app ID.
  The APK-list route is used by an update-log drawer and is not proven to be a
  download resolver. The app delegates transport to `window.$tapApi`; the
  bounded retained shared-client prefix does not establish its base URL or
  header serializer. No guessed API request, account operation or native body
  download was made.

The initial TapTap API family consumed 473,268 of its 524,288-byte ceiling,
including five additional requests; it made zero public JSON or APK/native-body
reads. Its shared-client prefix is partial source evidence, without a complete
script-integrity claim. The unresolved source owner is the authored
`app-shared.Lloon1lG.js` module, declared as 1,882,970 bytes by that CDN. Further
acquisition needs its own finite plan; this audit does not expand to unrelated
assets or distribution services.

### Bounded shared-client follow-up

A separate authorized two-MiB family subsequently completed that exact
[shared module](https://assets.tapimg.com/apps/web-app-next/_nuxt/app-shared.Lloon1lG.js):
1,856,145 new bytes, reusing the 26,825-byte prefix under the same ETag, with
the complete CDN Content-MD5 verified. Static inspection now establishes
`window.$tapApi` → `sC` → `W0`, same-origin GET transport and the actual app-ID
query serialization. It also establishes the ordinary `X-UA` query construction.
The complete source depended on another authored serializer and current page
configuration. That family stopped without inventing those inputs; its later
HEAD request read zero body bytes.

### Owned anonymous API result

A final, separately bounded family authenticated the complete 262,431-byte
`cupid-utils.GZo16did.js` serializer and 12,480-byte
`app-utils.BfjbmzQn.js` runtime helper against their CDN Content-MD5s. A
64-KiB compressed read of the original app page contains the complete standalone
Nuxt configuration and environment statements. The HTML/gzip stream itself is
incomplete; no whole-page integrity or complete hydration claim follows.

Complete received hydration entries nevertheless bind app 234280 to the mainland
game's ARM64 Android APK: version **3.8.0**, code **183728903**, exact size
**1,396,149,288 bytes**, and a distributor-declared MD5. This is game metadata,
separate from TapTap's own installer. It supplies neither a payload URL nor a
publisher signing certificate and cannot authenticate a native module.

Static source inspection now establishes the normal anonymous `X-UA`
serialization, runtime header and app-ID parameters. Two ordinary read-only
requests succeeded without account cookies or executing downloaded JavaScript:
`/webapiv2/app/v5/information` returns descriptive/developer information;
`/webapiv2/apk/v1/list-by-app` returns ten update-log entries containing only
version label/code, update date and release notes. That history contains no
URLs or downloadable APK descriptors. The evidenced mobile download UI hands
the action to the TapTap app; no direct game-payload delivery route was proved.

The final family used **396,761 of 524,288 bytes**, including **56,314 JSON
bytes**, and stopped at its **six-request** limit. No APK/native body was read.
This closes the bounded website/API hypothesis with an explicit delivery gap;
it does not prove that every official Android source is unavailable, establish
a signer, derive a bootstrap key or demonstrate key rotation.

### Original publisher Android route recovered

One subsequent bounded retry of the **exact original transfer-script route**
succeeded. The current mainland `official/cn/zh-Hans/android_app.json` response
is 430 bytes, passes its original Content-MD5 and supplies primary/secondary
HTTPS APK URLs on the publisher's `aki-game.com` mirrors. Both HEAD responses
declare **1,396,149,288 bytes**, byte-range support and the same multipart ETag.
Neither supplies a full-file Content-MD5; the hash-like filename component must
not be accepted as one. The previous timeout was temporary availability, not an
absent distribution source.

The original APK's complete central directory and signing-block metadata were
read with pinned ETag, exact total size and bounded 206 ranges. Its 2,613 entries
include 57 ARM64 native libraries. No v1 signature entries or v3 block were
found; a v2 block is present. The RSA signature over the received signing
metadata verified at this initial structure checkpoint, before the subsequent
whole-content verification below. Metadata alone did not authenticate a native
module or recovered key.

A complete CRC-checked binary Android manifest identifies
`com.epicgames.ue4.KrApplicationEx`, the launch activity and the GameActivity
metadata `android.app.lib_name=UE4`. The exact local header binds that intended
library to `lib/arm64-v8a/libUE4.so`, a **95,859,345-byte Deflate member** with
**329,258,456 decoded bytes**. This metadata/manifest family used 257,581 bytes.
A separate authorized 65,536-byte compressed prefix yields readable AArch64 ELF
headers. It is partial, unauthenticated native data: neither complete member
CRC nor APK content verification follows from the prefix. Relocated dynamic
framing and extra load segments alone establish neither readable key consumers
nor an unusable/protected module.

At that checkpoint the next gate was authenticated full-owner content
verification and complete member framing/size/CRC. The later successful proof
below supersedes that pending gate. Original client code is never executed.

Sources: [publisher download page](https://web-static.kurogames.com/mcDownloadPage/index.html),
[original transfer script](https://download.kurogames.com/assets/index-e5f35666.js)
and [source-derived mainland download metadata](https://download.kurogames.com/mc_WnGtDn85y8lJB4mTmYHYuNjIl9n6YGVm/official/cn/zh-Hans/android_app.json).

### November 18 current catalogue availability

The live Android plan-only attempt could not reach the original
`download.kurogames.com` catalogue; an independent desktop request timed out
also. This is a source-availability failure, not demonstrated TLS, signature,
ENTRY or package-format failure. The successful authored Android runtime
fixture does not establish that this live publisher source is reachable.

A separate bounded investigation read **six publisher responses totaling
2,503,606 bytes**, with no APK, client, audio or runtime acquisition. The
current Global and mainland main pages succeeded and exactly matched the
retained complete page bodies. The mainland page's published main script
imports separate mobile and desktop components; both were read as static data.
The mobile component's current
[download landing page](https://web-static.kurogames.com/mcDownloadPage/index.html)
and the desktop component's Android button still point to the same
`download.kurogames.com/transfer/.../official/cn/zh-Hans/android_app` route.
No independent current Android descriptor was established in this source chain.

Complete HTML, mobile and desktop script Content-MD5 checks passed. The main
script supplies no Content-MD5; its complete body MD5 matches its ETag. The
landing page's multipart ETag is retained as an identity, not treated as a
whole-body digest. Complete local SHA-256s and original URL ownership are
recorded separately. These website checks establish neither a newly observed
APK version/size/ETag nor module integrity.

The desktop script also publishes a `download.kurogames.net` Global
`pc_app` route, including an Android-labelled UI button. That label does not
establish an Android payload: no host/path substitution or request to a guessed
`android_app` counterpart was made. The failing catalogue was not retried
unchanged, and no old APK or retained native output was promoted into a current
cold-download fallback. The provider remains honestly gated on live source
availability. This bounded result does not prove every official alternative
is unavailable.

### Authenticated native default producer

One complete 1,396,149,288-byte original APK stream passed the canonical APK-v2
RSA/content-digest, signing-block, directory, EOCD and EOF checks. Only the
selected compressed library and its 329,258,456-byte decoded module were
retained. Deflate EOF, declared size and ZIP CRC agree. The source opts into an
explicit, RSA-covered four-zero signing-data tail; this is not a general
trailing-data exception, independent certificate pin or Android installation
acceptance claim.

The source-owned chain is the actual initialization-array constructor, callback
registration, shared Core default-delegate storage and the registered
`FEncryptionKeyRegistration::Callback`. The bounded ELF/AArch64 reader derives
all 32 output bytes from the readonly producer. It rejects unknown instructions,
incomplete writes, writable data, ambiguous registration and unrelated runtime
paths. It has no version, address or recovered-value allowlist and executes no
original code.

A fresh Global bootstrap index cache then decrypted and checked both complete
original main/directory SHA-1s with only that native candidate: 440,816 bytes of
exact original footer/sample/index responses, no member bodies. This proves
compatibility for that actual Global owner, not every region or a future key
rotation. Ordinary discovery now retains immutable native-source identity
separately from UUID-owned KeyLists and independently proven historical legacy
inputs. A candidate is not trusted as a default until both complete original
indices pass. Corrupt present provenance, revoked UUIDs and unrelated GUIDs
retain their rejection boundaries.

### Current-content update and recording reuse

During ordinary-worker verification the real resource revision changed from
3.8.11 to 3.8.12. The first guarded attempt stopped before an uncached large
index; the older discovery result was not substituted for the current one.
Of 29 changed resource owners, 28 already had complete cached indices. The one
missing main index required 2,832,133 original bytes and passed its complete
SHA-1. Its 5,274,534-byte directory already existed under the exact native SHA-1
and size and needed no new transfer.

The current five-language selection has sixteen original tables. Two were
already cached; fourteen required exactly 321,815,270 header/body bytes. The
evidence levels are distinct: both original indices have complete SHA-1 checks;
these raw encrypted members have the native 2,048-byte encrypted-prefix SHA-1;
the remainder has original HTTPS owner/range/length/ETag binding; retained
complete plaintext tables have local SHA-256 checks. This does **not** assert a
whole publisher member hash or complete PAK-owner hash from selective reads.

Complete recordings now have an additional cache bound to the exact original
manifest URL, owner size/hash, encoded entry position and full authored WEM
path, plus a complete local recording SHA-256. Ordinary validated extraction is
its producer. A changed text catalogue may reuse that exact recording; a new
owner/member, another dub/Rover path, a tombstone or corrupt cache may not.
Existing snapshot caches cannot silently acquire this ownership. For private
research reuse, all 714 previously extracted originals were separately resolved
against both old and current complete indices and had identical full references
and valid old cache receipts. The old files were kept unchanged. No recording
body was downloaded in this table/update cohort.

All five ordinary workers then passed against live 3.8.12 with one unchanged
backend source hash. They used the authenticated retained native module and
ordinary official KeyLists; initial/community key entry points were forbidden.
The separately frozen/protected manifest-format input remained in use.

| Study selection | Current rows | Changed records from 3.8.11 | Changed source texts |
| --- | ---: | ---: | ---: |
| English | 144,130 | 5 | 4 |
| Japanese | 144,182 | 6 | 2 |
| Korean | 144,028 | 10 | 5 |
| Simplified Chinese | 145,782 | 5 | 1 |
| Traditional Chinese | 144,880 | 34 | 29 |

There were no added/removed records or changed audio bindings in this actual
update. Each selection retained 1,359 film-context variants across 87 scenes.
The ordinary pipeline made 586 exact-owned recording-cache hits, without new
WEM, MP4, table or APK bodies during the workers. A metadata-cap stop retained
the three completed selections; the final two continued under an explicit
additional metadata allowance, with the same source hash and cumulative ledger.
Total small metadata was 3,090,919 bytes, separate from the exact main-index and
fourteen-table acquisition families above. This is warm source/cache acceptance,
not a second cold APK acquisition or a real key-rotation trial.

A new offline process replayed the same retained whole film context in all four
dubs and both Chinese scripts. Old/current original hashes and complete decoded
frame counts agree; playback made no network or protected-key reads. An actual
original-source acquisition outage reports `publisher_bootstrap_unavailable`.
An interrupted ordinary publication of the complete current payload retains the
old payload. All five original 3.8.11 payload files remain unchanged. Synthetic
source, rotation, provenance, cache and parallel-publication controls passed
alongside 642 affected tests and sixteen subtests.

### Distinct manifest consumer and bounded initializer follow-up

The remaining `ENTRY_KEY`/`ENTRY_IV` inputs unwrap Base64/AES-CBC **outer release
JSON**. They are not SQLite ConfigDB entry parameters or the PAK archive-default
key. The original entry/config, resource/dub/video manifest and encrypted
KeyList paths use this boundary. Existing original launcher scripts pass the
HTTP response to `UKuroLauncherLibrary::Decrypt` before JSON parsing.

The authenticated Android module's complete reflected `execDecrypt` wrapper
calls that exact native method. Its four-byte declared entry is neither a
supported direct branch nor a normal return; the bounded static pass did not
recover the key/IV producer. The registered archive-default output is also not
equal to the already frozen manifest AES key. No key transforms, generic
literal search or original-code execution were used.

A further original-APK primary-DEX probe checked the exact binary-manifest
application class as a possible initialization owner. After an explicitly
recorded local ZIP-flag assertion failure, the separately authorized exact retry
passed strict ETag/range, Deflate size/CRC and DEX SHA-1/Adler checks. The exact
application class was absent from its 3,913 class definitions. The probe stopped
without downloading the other fifteen DEX files or executing protection code.
This closes that particular primary-DEX hypothesis; it does not establish
official derivation impossible. Later range bytes retain original HTTPS/ETag
ownership to the previously fully verified APK, without claiming a fresh
independent APK-v2 digest for that member.

The canonical desktop/Android Settings provider now exposes the verified
bootstrap stage and then the explicit manifest-format gate. It does not turn
this remaining dependency into a ready language library; see
[the staged portability report](wuwa-android-portability.md#settings-bootstrap-provider).

### Standalone Windows launcher follow-up

A separate bounded pass investigated the standalone launcher, rather than
repeating the opaque game-native Windows/Android functions. Two already cached
3.1.0.1 modules, `launcher_main.dll` and `launcher_updater.dll`, have valid CLR
metadata. Their ZIP member CRCs and local hashes were checked. The cached
archive's current publisher checksum authority was **not** re-established; this
is explicitly qualified cached-source evidence, not a trusted new key source.

An owned passive PE/metadata/IL reader inspected 4,734 main-module and 1,132
updater methods. It never loaded or executed the original assemblies. The
concrete game-configuration path is `KRCheckUpdateFlow.InitGameServerConfig`
through the HTTP helper and response data to `KRGameServerConfigAdapter`, then
the ordinary System.Text.Json deserializer. There is no Base64/AES step in this
response-to-JSON path. Its models describe launcher resource packs, bundles and
index-file MD5s. Cryptographic calls found there concern MD5 file checks and
certificate checks; logging encryption and password-protected WebView ZIPs are
separate consumers. No caller connects `kurodata.dll` to this configuration
path, so that module was not pursued.

The original startup method separately decodes its local `KRApp.conf` using
Base64 and a source-defined byte XOR before JSON parsing. That local-profile
rule is not the encrypted game-entry AES-CBC rule. The profile supplies the
[official launcher application index](https://prod-alicdn-gamestarter.kurogame.com/launcher/app/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/index.json)
and [official game package index](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json).
Two current read-only responses, 1,711 and 5,026 compressed bytes, parsed as JSON
after ordinary gzip decompression without ENTRY or protected-format inputs.
The game response advertises the 3.8.0 common package inventory. This explains
how the evidenced standalone route operates without decrypting the separately
discovered in-game hotfix JSON; it does not supply a hotfix decryption key.

The current application response names a different default archive: parent
version 3.0.1.0, 465,195,358 bytes, with an explicit publisher MD5. Its original
HEAD agrees on length and ETag. One authorized 65,557-byte EOF range passed
strict 206, total-size and ETag checks. The entire 64,366-byte directory with
743 entries was already in that tail, so no additional directory transfer was
needed. It names the same launcher component family, but directory names do
not prove the new modules' behavior. No selected module was extracted and the
complete archive MD5 was not represented as verified from selective metadata.

This family used **72,294 of 1,048,576 authorized metadata bytes** and stopped.
No module bodies, complete installer, additional DEX files or old opaque
function windows were acquired or revisited. There is no concrete new ENTRY
consumer to justify such an acquisition. The exact missing evidence remains a
readable original game-configuration decrypt producer, or an independently
demonstrated alternative. This particular standalone route does not prove that
official derivation is impossible and does not close the manifest-key/IV gap.

### Exact Android application owner and initialization follow-up

A later, separately authorized pass resolves the previously uninspected DEX
ownership question; it does not repeat the closed standalone launcher or opaque
native-function probes. The authenticated original directory contains sixteen
DEX members in total, including the already checked primary file: **fifteen
secondary members**, not sixteen secondary members. Those fifteen are physically
contiguous. One exact original range contained **12,163,199 bytes**: 12,162,562
compressed DEX bytes and 637 local-header/name bytes, without unrelated members.
The original owner length and ETag matched before reading the strict 206 body.

Every selected local header matched the complete retained directory's name,
flags, compression, size and CRC; no extra fields or range expansion were
accepted. Complete Deflate EOF, plaintext size/CRC, DEX header SHA-1, Adler-32 and
section/map bounds passed. These later selective bytes have the original
HTTPS/ETag/owner binding and member checks, separately from the retained earlier
whole-APK-v2 receipt. This is not a fresh whole-carrier verification, independent
publisher-certificate pin or Android-install acceptance claim.

The exact manifest class `com.epicgames.ue4.KrApplicationEx` is uniquely defined
in `classes4.dex`, not the primary DEX. Its exact superclass
`com.kr.android.core.api.KrApplication` was located from the retained compressed
originals in `classes10.dex`, without another request. That superclass extends
`com.ace.gshell.AceApplication`. The manifest application binding therefore was
not invalidated by the earlier primary-only absence.

A separate cache-only pass first inventoried the two owners' 21 and four
declared methods. It then inspected only their seven declared `<clinit>`,
`<init>`, `attachBaseContext` and `onCreate` code items: **476 bytes and 87 decoded
instructions**, within the explicit 32-KiB/4,096-instruction ceiling. Complete
DEX hashes were revalidated before each input; instruction, register, reference
and branch bounds were checked. No additional callee bodies, original code
execution, generic string/key scan or network requests were used.

The observed startup sets up MultiDex, Tinker patch handling and lifecycle
callbacks. `KrApplicationEx.onCreate` explicitly calls
`PatchProtocol.SetContext` and `PatchProtocol.CheckSoPatch`. The exact superclass
invokes `AceApplication` construction and lifecycle methods, followed by
`KrImp.onApplicationCreate` and foreground/background detection. These are
concrete, **unexpanded** runtime/patch delegation edges. A package name or SDK
initialization call alone does not establish ownership of the encrypted game
release-entry JSON.

No ENTRY-key/IV producer or owned response-to-decrypt path was established in
those seven methods. The pass stops at the uninspected runtime/patch callees;
it does not infer that they are opaque, that the whole application is packed,
or that official derivation is unavailable. The encrypted manifest boundary
remains open. No preparation behavior or supported-coverage claim changed.

### Exact PatchProtocol startup edge

A subsequent cache-only pass follows only the already observed
`PatchProtocol.SetContext` and `PatchProtocol.CheckSoPatch` calls. The exact class
is uniquely defined in retained `classes2.dex`; its nineteen method declarations
were inventoried before those two bodies were selected. Complete input hashes
and DEX checks were revalidated. The two code items total **160 bytes and 31
decoded instructions**, below their separate 8-KiB/1,024-instruction limit.
No additional original bytes were acquired and the Ace/Shield branch remained
closed.

`SetContext` obtains and stores the application context. `CheckSoPatch` delegates
cleanup/loading decisions to `IsCleanPatch` and `CheckIsLoadBuiltinSo`, calls
`KuroTinkerManager.cleanPatch`, and serializes time/mobile-filter information
into the static `CacheCleanPatchInfo` status field. It also reads
`IsLoadBuiltinSo`. No HTTP-response, Base64/AES or entry-decrypt path appears in
these two complete methods. The exact same-owner checks and `cleanPatch` are
unexpanded next edges, not demonstrated release-metadata owners. No callee
bodies, generic key/URL search or original execution were added. This narrow
negative result leaves the ENTRY-key/IV gap open and does not establish that an
official route is unavailable.

### Named update-field ownership and failure boundaries

Only the existing authenticated config declarations were followed for the
retained `PackageUpdateDescUrl`, `ParallelPackageDescUrl` and `PackageUpdateUrl`
field names. `Launcher/BaseConfig/BaseConfigModel.js` defines them in
`EntryJson.constructor(i,s)`: it initializes them as undefined, then copies the
supplied object values with override selection. Those assignments establish a
config-field initializer, not an embedded URL, ENTRY parameter producer or
independent current resource/four-dub descriptor. No new request, original
module body or cleanup/lifecycle branch was added. The exact missing evidence
remains an independently obtainable ENTRY key/IV owner or independently owned
active resource/dub manifest chain.

The ordinary compatibility reader now reports separate failures for an absent
ENTRY input, an unverifiable protected cache, a different cache generation,
failed pinned-source checksum authentication, invalid key/IV declarations and
failed safe retention. A present invalid or other-generation cache is not
silently treated as a cold miss. Malformed response framing is distinct from a
verified pinned input that cannot decrypt the current manifest. The latter
reports the unresolved current ENTRY-verification step; it does not assert that
the game package format changed. Public messages contain no raw input values,
private paths or underlying cryptographic diagnostics.

This changes failure admission and labels, not source acquisition policy. The
existing pinned compatibility input remains separately qualified and is never
introduced as a fallback into the canonical Settings provider. A metadata-only
bootstrap quote also cannot restore as though its module had been verified;
it reports an incomplete bootstrap stage. Existing retained verified modules
still reach the explicit ENTRY gate locally.

Service/worker regressions exercise failure during discovery and inside the
ordinary language worker, keeping a valid prepared table, selected language,
source descriptor and original recording unchanged. Fresh index readers still
match the old text and restore the old cached original offline without ENTRY
or current-key access. Quote and retained-stage checks remain distinct from
Ready. A read-only positive compatibility check also decodes the three retained
Global/mainland/config responses with the existing verified input, without
network or cache changes; it is not independently derived ENTRY acceptance.

## Acceptance still required

The archive-default producer now has an authenticated current rule and ordinary
integration. Its normal refresh, failure and retained-source boundaries must
continue to preserve native UUID revocation, independent default provenance,
immutable retained descriptors and final-pointer checks. The distinct encrypted
JSON manifest `ENTRY_KEY`/`ENTRY_IV` consumer still needs an original-source
resolver; solving the PAK callback does not solve that dependency.

No current evidence proves official derivation unavailable. A maintained
community fallback has therefore not been selected as the resolution of this
gap. Real cold preparation without community/protected-cache inputs, all five
study selections and official dub bindings, failed-download retention, offline
restart and authentic key-rotation acceptance remain separate from the already
completed changed-content trial. Android native codecs, protected storage and
on-device acquisition are also separate outstanding acceptance requirements;
see [the portability audit](wuwa-android-portability.md).
