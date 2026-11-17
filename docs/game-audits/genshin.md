# Genshin Impact narrative audit

## November 17 update policy

The owner accepted official publisher content/audio with controlled community
binding, schema and key metadata under the [per-game update policy](../live-service-completion.md#per-game-update-policy--november-17-2026). A matching immutable
community revision may change without a toolkit release. Full reconstruction
of every native table is no longer a closure requirement. Normal preparation
still needs original publisher-text integration, verified generation
compatibility, provenance and failed-update/offline acceptance; original-reader utilities alone do not prove those
ordinary-provider requirements. Subtitle and original-audio gaps remain in #83.


## Original TextMap utility · November 16, 2026

The experimental [original TextMap reader](../../backend/genshin_original_textmap.py)
can decode original subtitle/localization tables independently of mirror rows.
Its bounded native-template parser derives count and string parameters from a
caller-provided, authenticated x64 reader method. It recognizes the inspected
arithmetic forms without a game-version, address or parameter allowlist. It has
no disassembler/runtime dependency and never executes publisher code. The caller
still owns package authentication, native metadata/bootstrap, method ownership,
shard discovery and regional identity. A hash identifies an input; it does not
authenticate the publisher.

All 15 official text locales were actually read from the original 7.2 design
packages using the frozen utility: 15,360 shards, 495 packages and 12,779,262
localization entries. Every package passed its publisher size and whole-file
MD5 check (1,113,675,679 bytes total; largest file 32,447,783 bytes). Independently
fetched Global and mainland China design indexes advertised the same identities
for all 495 selected packages; regional identity was checked, not inferred from
the version number. Every shard passed strict EOF, UTF-8, native bucket,
duplicate and alias-reference checks. The native manager selects the low ten
hash bits, iterates 1,024 shards per locale and chooses the Medium prefix through
bucket 511 and the ordinary prefix thereafter.

| Locale | Ordinary entries | Medium entries |
| --- | ---: | ---: |
| CHS | 640,563 | 245,654 |
| CHT | 619,307 | 235,596 |
| DE | 618,847 | 235,238 |
| EN | 619,152 | 235,449 |
| ES | 619,024 | 235,473 |
| FR | 619,168 | 235,469 |
| ID | 618,732 | 235,088 |
| JP | 618,974 | 235,507 |
| KR | 619,154 | 235,507 |
| PT | 618,863 | 235,387 |
| RU | 619,109 | 235,601 |
| TH | 619,094 | 235,486 |
| IT | 584,785 | 234,866 |
| TR | 584,780 | 234,859 |
| VI | 619,063 | 235,467 |

These localization totals are not a story-coverage denominator. Only after all
original parsing completed, comparison with the already frozen matching English
and Japanese extractions found every ID and value identical. No new control
tables were downloaded; the other 13 locales have original-format validation,
without a claim of separate mirror comparison.

Both original native reader methods independently yielded the same parameters.
The all-locale parsing process prohibited network access, the older fixed-
parameter parser, mirror rows and precomputed parameter values. It made no
prohibited access, retained identical software/helper hashes and reproduced the
earlier English output hashes. This is current-generation parsing evidence,
not the two-generation normal-update acceptance trial.

The utility merges complete shard sets, resolves bounded aliases, rejects
ambiguous/malformed input and atomically publishes a separate text cache only
after complete validation. Owned tests cover changed native parameters and IDs,
Unicode/markup preservation, aliases across shards, duplicate/cyclic/missing
references, truncation, input limits, interrupted publication and restart/retry.
No real texts, native bytes or game parameters are included in those fixtures.

Following the actual native Talk manager's stream call identified a different
root reader and its array, record and role readers. A private diagnostic then
completely parsed two original Quest assets (514 and 197 bytes, with 11 and four
records), with strict EOF/UTF-8 and root IDs equal to the official asset paths.
The root reads its array before its ID; the first DWORD is an array length,
which explains why treating that word as the Talk ID found no valid reader.
The record's key accessor formats field +0x80 as a decimal string. All 15 decoded
field values exist as keys in all 15 independently parsed original locale tables
(225 matches); the accessor itself does not perform localization lookup.
No mirror rows were used to derive or parse those records.

## Experimental native reader foundations · November 17, 2026

The [native metadata reader](../../backend/genshin_native_metadata.py),
[contract builder](../../backend/genshin_native_contracts.py) and
[Voice owner analysis](../../backend/genshin_native_voice.py) now derive inspected
read contracts from supplied original executable and metadata bytes. Original
client code remains inert data. Current method addresses, type/member indices,
arithmetic operands, registration arrays and field offsets are discovered from
those inputs. Retained layouts describe formats and bounded instruction forms;
the repository contains no original game bytes, texts or codec keys.

This experimental analysis requires a Windows amd64 host and the exact pinned
Capstone 5.0.7 software decoder. Its native DLL and complete BSD notice are
verified before loading. The [software receipt](../../packaging/native-codecs/genshin-capstone-5.0.7-windows-amd64.json)
records the original wheel and every member digest; runtime collection retains
the package, DLL and original license metadata. It excludes installer-generated
local-wheel URLs. Other hosts refuse this experimental analysis while retaining
the existing provider.

On the held Global 7.2 originals, complete metadata parsing recovered 89,748
types, 741,021 methods, 445,462 fields and 555,919 parameters. Subsequent
development probes derive all 314,558 usage lists, 788,698 references and 87,253
strict UTF-8 literals. Their generated TalkExcel contract reads all 45,699 rows
with exact EOF and agrees with independently held original controls, opened
after parsing. The original Talk100001, Talk100002 and GlobalDialog objects also
pass exact EOF through the actual allocated type's native virtual reader.
The original Lut contract reads all 154,113 rows. Whole-corpus development
replays now read all 7,449 original Items groups / 154,113 entries and 47,121
previously source-bound original Talk objects / 418,454 nodes, with complete
catalog identities, payload hashes and exact EOF. Independent original controls
are opened after all new parses; they show zero differences. These corpus
replays explicitly reuse a private native-metadata intermediate and the held
positive source cohort. They do not establish full current presentation routing.

The [canonical bootstrap](../../backend/genshin_native_dialogue.py) connects those
native roles to the existing explicit preparation profile and atomic snapshot
writer. It acquires each original object once: exact Lut/Items bytes establish
trigger correspondence and feed that same preparation. Changed generations,
wrong read contracts and absent groups preserve the prior snapshot. Source-group
routing contracts are still caller-supplied. A separate fresh
original-executable/metadata trial derives metadata, usages, literals and the
canonical inventory/Talk/Lut/Items readers without that intermediate. Exact
original UUID-plus-argument joins derive all eight trigger names from current
data: 154,111 bindings match, including 149,114 Dialog entries. The two missing
UUID bindings remain unknown; event-only matches cannot replace them.

The [source-index reader](../../backend/genshin_native_sources.py) derives the
actual UInt32/UInt64 dictionary decoder, all five current index paths, their
typed path/stream/out-pointer cache writes and matching native getters. Actual
root allocations and called readers are recovered for NpcFree, MainQuestBrief
and MainQuest. All 3,978 original NpcFree groups pass whole-object EOF with their
own derived descriptor contracts. Typed array tail calls, register-derived
presence tests and full-width UInt64 values have explicit bounded readers.

The [method-attribute reader](../../backend/genshin_native_attributes.py) follows
the native MethodInfo constructor's actual table, row-index and attribute stores.
All 741,021 original method attributes decode with independently agreeing
after-parse results. Current attributes establish static/instance argument
positions; unsupported value-type/floating ABI shapes are refused. Descriptor
roles then follow the actual typed array callback and forwarded object to a
UInt32-keyed native store and matching getter/cache. Its UInt64 field reaches
a typed original stream opener through the proved Descriptor argument. These
are source-format roles, rather than proof that every declaring overload is
currently called or that full current routing is complete.

The analysis follows authored root-array registration, separate raw/decoded
presence flags, native transformations after initial field stores, and typed
protected-value setters. Voice field roles follow actual input comparisons,
event-key construction, group-cache consumers and original source-name copies.
The UUID role follows the converter's original ASCII case-folding/FNV-1 code.
The configuration registry's byte type tag does not establish a Voice API call.
Likewise, formatting a localization key does not prove every subsequent UI
presentation or player-role decision.

These readers do not activate an automatic original provider in normal
preparation. Complete descriptor/MainQuest source routing, original package
acquisition and its runtime codec closure, regional validation, and old/current
update plus recovery acceptance remain open. The 219 source-unbound configured
rows and direct-Global/player-role questions remain explicit research inventory;
configuration references alone do not prove current use, removal or unvoiced
status. Ten existing unused Action variants remain future content-support
qualifications when new content uses them, rather than new package formats or
proven current presentation blockers. Normal Setup retains its existing source.

## Explicit original Talk preparation API · November 17, 2026

The [original dialogue reader](../../backend/genshin_original_dialogue.py)
accepts typed read contracts from caller-proved original native owners. It
supports bounded unsigned arithmetic, flag-selected fields, protected-value
semantic inputs, UTF-8 strings, arrays and dictionaries. Exact EOF, duplicate
keys, finite floats and cumulative input limits are checked. The contracts and
their source/method digests are explicit inputs; this API does not automatically
discover native methods or derive a complete contract. The repository contains
synthetic contracts, never original native bytes, text or game parameters.

The preparation API consumes the entire supplied authored Talk inventory and
loads every referenced original Talk object. A native routing contract can
construct a resource path from its proven prefix and exact typed inventory ID;
unknown route values refuse preparation. Shared references load an object once.
No dialogue-number prefix or guessed ordinal supplies a filename.
Routes also support an original descriptor or a group of descriptors. Each
descriptor retains its full UInt64 catalog identity, native payload kind and
Talk ID. The asset loader must return that exact identity from a verified
catalog of the same publisher generation. Shortened container names cannot
replace full catalog/bundle ownership. Group root IDs and inventory membership
are checked before activation; duplicate, unknown or absent members refuse the
update. Catalog digests participate in the snapshot revision.
Native-owned UInt32-to-UInt64 source dictionaries can also enumerate Talks,
descriptors or descriptor groups directly. Every indexed root must match its
index key, and every descriptor must still resolve to a known Talk inventory
member. NPC/cutscene index keys have a separate namespace: an equal number cannot
silently replace an inventory Talk. Compound group routes retain the two typed
inventory values in their authored order, including native zero/default values;
both group root IDs must agree. An omitted native dialogue array means there
are no captions in that object, without manufacturing an unvoiced line.
An explicit `IndexedGroupPrefix` source contract follows the separate native
index-owned loading path: it consumes every field through the authored Talk
array while retaining the whole asset digest, catalog digest, whole byte count
and consumed prefix byte count in the snapshot. Its identity belongs to the
original dictionary, independently of an internal ID serialized later. It is
available only for indexed groups; ordinary groups still require matching root
IDs. The whole-object decoder retains exact EOF. Native tagged factories also
require explicit, unique cases, including proved zero-byte readers; unknown
tags cannot select a different reader or skip a payload.
It reads the original voice Lut,
loads each referenced Items group and joins the exact original UUID hash,
argument and trigger. Duplicate event keys, UUID hash collisions and missing
original identities cannot select a different recording. Conditional source
alternatives use the existing Traveler handling. An absent publisher recording
is unavailable; a Talk node without an authored binding remains unknown. Neither
case becomes confirmed unvoiced. The resulting cache uses the ordinary
installation-free snapshot and voice-service format. Failed, truncated or
interrupted updates retain the preceding cache, as does a changed publisher
generation at activation.

Completed original Talk captions retain positive text-capture provenance through
rendering and index reload, including choices and rows with missing UUID/audio
bindings. The separate missing-audio capture option can match their complete,
exact, unambiguous caption while preserving its unknown/unavailable voice state.
It is off by default. Unresolved source templates remain excluded, and generic
TextMap/interface translations without authored Talk membership are not promoted.

The actual product decoder, with private original-owned read operands, parsed
all **7,449 current Lut-referenced Items groups**: 33,079,559 original bytes,
154,113 Items records and 178,559 source alternatives. The original 154,113-row
Lut, 10,627-row Inner object and both Talk samples also passed exact EOF/UTF-8.
The native activation hashes each UUID to the VoiceID and combines the argument
and trigger as `(argument << 32) | trigger`; the Dialog enum is 2. Exact UUID
and argument joins succeeded for 154,111 Lut rows. Two original Dialog Lut
entries point at groups without their expected UUID hash and remain unresolved.
The Items field at offset +0x74 is an unrelated integer; the trigger comes from
its original string field, not that integer. These are current-generation source
checks, not a complete story inventory or an autonomous update acceptance run.

For the two sampled Talks, 13 lines have exact original Lut/Items WEM paths.
Two player-choice nodes retain unknown voice status. All four publisher dubs
contain the 13 recordings and four additional entries from those same Items
groups: **68 recordings, of which 52 belong to the sampled Talk lines**. Each
passed ordinary voice-service decoding twice with networking prohibited and a
new output directory on reopen. Decoded PCM was identical. The extra download
used 55 size/MD5-verified Sophon chunks, 68,708,466 compressed bytes, with no game
installation or whole-PCK download.

The actual original TalkExcel loader and its 45,699-row inventory object have
been identified and acquired from a fully MD5-verified publisher package. Its
42 serialized fields were recovered from the owned native control/data flow;
the additional metadata field caches a derived list. All 13,973,525 bytes then
passed the product decoder's strict UTF-8/EOF checks, with 45,699 unique positive
IDs. That nested table contains 5,055,663 decoded values, exceeding the former
four-million bound. The reader now permits eight million values while retaining
its byte, collection, nesting and cumulative-input limits. A synthetic nested
inventory regression covers this valid large-table case.

The 48 serialized runtime descriptor fields were separately recovered from
their original native owner, including both nested condition/execution arrays.
All **338 Blossom descriptors** passed strict decoding, retained their exact
inventory IDs and resolved their full UInt64 references to original catalog
entries. All 338 referenced Talk payloads then passed exact EOF and matching
root IDs, yielding 912 authored dialogue nodes. The **23,801** current direct
Quest paths identified from exact inventory IDs likewise passed original Talk
decoding and root-ID checks, yielding **321,344** nodes.

The grouped route also resolved **2,109 Activity, 242 Storyboard, 38 Scenery and
two Furniture descriptors** to 2,391 exact original catalog assets. Every Talk
payload passed strict decoding and matched its descriptor ID, yielding 21,051
nodes. The group IDs match their original resource names. Additional candidate
FreeGroup and NpcOther resources and the shared GlobalDialog object are readable.

The original source dictionaries independently enumerate **3,978 NPC free-talk
groups, 1,604 NPC other-dialogue objects and 37 cutscene dialogue objects**.
Every resource was resolved by its full catalog identity and passed strict
decoding with matching root IDs. The free-talk groups contain 18,493 descriptors
referencing 17,443 unique Talk payloads; all referenced Talks passed matching-ID
and EOF checks, yielding 68,208 nodes before repeated group contexts. The other
NPC objects contain 1,859 nodes and the cutscene objects contain 708. The original
MainQuest and MainQuestBrief dictionaries each enumerate 4,543 resources; their
source identities remain distinct.

All **4,543 MainQuest resources** now pass the product grammar's bounded
native-owned prefix projection through their Talk array. This includes all 74
resources with interaction dictionaries and all 29 with guide dictionaries.
The actually encountered native factory cases, nested records, strings and
collection bounds are consumed; unused scalar bits are not treated as IDs.
The original loader takes a dictionary key, obtains its full UInt64 asset
reference, reads the typed MainQuest and consumes that Talk array. Its internal
MainQuest ID occurs after this prefix and is not fabricated from an earlier
field. Every projected descriptor resolved to a known inventory Talk with a
matching ID and complete EOF: **23,801 Talks and 321,344 nodes**, the same set
already counted under direct Quest paths. This does not assert complete
MainQuest/SubQuest decoding, gameplay reachability or autonomous preparation.

Gadget loading uses the first two authored extra-load IDs in order. They are
not a Scene ID inferred from a dialogue number. The 1,506 inventory rows with
such pairs identify 667 groups exactly. A separate scan of all 176,150 named
data objects in their current verified bundle found one further group with
native default IDs: `0_0`. Classification required the exact native-constructed
path's full UInt64 catalog identity, followed by complete group decoding. Of
174,884 bounded prefix reads, 174,216 failed that catalog identity check; 1,266
other objects failed the prefix bounds. The resulting **668 groups and 1,507
referenced Talks** all passed complete EOF and ID checks, yielding **4,372 nodes**.
Ten inventory rows without authored pairs remain without a group binding; this
scan does not establish that other current or future bundle partitions contain
no additional groups.

The combined parsed sources currently contain **414,070 unique dialogue IDs**
and **411,847 positive caption hashes**, with no conflicting hashes for an ID.
These are measured parsed sources, not a complete story denominator. Joining
all 15 fully parsed original text locales leaves five caption hashes absent in
Simplified Chinese, 3,437 in English, 3,465 in Japanese, 32,833 in Turkish and
32,836 in Italian; other locale gaps are also recorded. These source gaps do
not establish silence, unreachable content or missing parser fields. All counts
above describe original-format evidence, not full end-to-end preparation or
complete presentation coverage.

All referenced Talk resources still need to be replayed through preparation.
The original load-type enum distinguishes ordinary quests, Blossom, activity,
gadget, furniture, storyboard and scenery. Runtime descriptors can reference
the actual dialogue payload by an original UInt64 asset index; grouped resources
must retain that authored hop. No constructed sample inventory establishes that
the complete original inventory and those routes work. Complete automatic native
schema/bootstrap recovery, regional/full-presentation coverage and the
two-generation preparation/update/restart trial remain open.

[Owned preparation and retention tests](../../backend/tests/test_genshin_original_dialogue.py)
cover changed operands, a 137-object synthetic inventory, a shared descriptor
graph with colliding shortened identities, conditional takes, unknown choices,
missing packs, ambiguous identities, strict bounds and failed update/retry.
Changed catalog identities refresh provenance; wrong identities, stale assets,
unsupported payloads and incomplete groups preserve the preceding snapshot.
Resource-index tests additionally cover changed native operands, full indexed
enumeration without filename probes, group-key namespace collisions, wrong
indexed roots, absent assets, truncated dictionaries, unknown indexed inventory
kinds, compound-ID disagreement and authored empty Talk arrays.
Indexed-prefix tests cover nested tagged cases, zero-byte cases, exact prefix
consumption, whole-source identity changes from unused trailing gameplay data,
changed native operands, strict whole-object refusal and failed-update retention
for unknown tags, truncated prefixes and unknown Talk membership.
These tests do not establish real native inventory discovery.

Normal Setup still uses its matching text extraction. The explicit API does not
switch that provider or change capture eligibility. Full original inventory
linkage, automatic native bootstrap and method discovery, and normal-worker
update/recovery acceptance remain open.
The original `Config_TextMap` object itself was decoded completely, but its
cache/partition settings do not resolve those remaining binding questions.

[Original Global design index](https://autopatchhk.yuanshen.com/client_design_data/7.2_live/output_49419538_604495f667/client/General/AssetBundles/data_versions)
· [Independently checked mainland design index](https://autopatchcn.yuanshen.com/client_design_data/7.2_live/output_49419538_604495f667/client/General/AssetBundles/data_versions)
· [Frozen matching extraction used only after parsing](https://gitlab.com/Dimbreath/animegamedata2/-/tree/a311cd77d7dafbd2bedc7d3cac4e986c6125b586)
· [Owned format tests](../../backend/tests/test_genshin_original_textmap.py)

## Active regional hotfixes without an installation · November 16, 2026

Normal publisher preparation now checks the selected Global or mainland China
Windows dispatch response, the current resource/design/silence indexes, and the
separate `base_revision` before selecting the matching immutable text extraction.
The public [Global bootstrap metadata](https://raw.githubusercontent.com/CollapseLauncher/CollapseLauncher-ReleaseRepo/main/metadata/v3/stable/config_GIGlb.json)
and [mainland bootstrap metadata](https://raw.githubusercontent.com/CollapseLauncher/CollapseLauncher-ReleaseRepo/main/metadata/v3/stable/config_GICN.json)
supply changing dispatch format parameters. The toolkit reads these documents
as bounded data, with the already pinned Brotli and PyCryptodome libraries.
It never downloads executable bootstrap code or persists decoded keys in a
snapshot. No account, UID, login token or game installation is used. The two
editions have different bootstrap parameters; reusing the Global parameters
for mainland China caused the earlier integer error response.

The original released Global 7.2 executable and both metadata files were
independently checked against their publisher manifests. Static string and
method analysis confirmed `MoleMole.Miscs.GetGlobalDispatchUrl`, the actual
Unity HTTP client version, and the default field read by its dispatch seed
argument. Native code was never executed. The public launcher's currently
decoded seed agrees with that original field. This is source evidence for
the bootstrap format, not a new runtime dependency on version-specific native
offsets. [Static analysis source](https://github.com/portra400nc/genshin-il2cpp-re/tree/9ba116e5cfed3edca08a3de300480674d315e921)
· [Original launcher response handling](https://github.com/CollapseLauncher/Hi3Helper.EncTool/blob/fe5bcb93dfdae80de8db5e759fb7abc7ee0f859b/Parser/YSDispatchHelper/DispatchHelper.cs)

Independent Global and mainland requests returned the same current index
identities. Every downloaded body matched its advertised size and MD5:

| Index | Revision and suffix | Bytes | Rows | MD5 |
| --- | --- | ---: | ---: | --- |
| Windows resources | `49411577_7ffe3bd9a6` | 370,957 | 2,631 | `0914db549b6118cc849a3063b7599239` |
| Design data | `49419538_604495f667` | 71,416 | 533 | `09f2c36615dc806f67f55e3d2c8a0c8d` |
| Silence data | `49291486_c25ba650a6` | 523 | 4 | `2bcf33810856cb0820725300ff2d8666` |
| Base revision | resource index above | 19 | 1 | `403247d78dc495d3bf57c7133d01978a` |

[Global resources](https://autopatchhk.yuanshen.com/client_game_res/7.2_live/output_49411577_7ffe3bd9a6/client/StandaloneWindows64/res_versions_external)
· [Mainland resources](https://autopatchcn.yuanshen.com/client_game_res/7.2_live/output_49411577_7ffe3bd9a6/client/StandaloneWindows64/res_versions_external)
· [Global design data](https://autopatchhk.yuanshen.com/client_design_data/7.2_live/output_49419538_604495f667/client/General/AssetBundles/data_versions)
· [Separate base revision](https://autopatchhk.yuanshen.com/client_game_res/7.2_live/output_49411577_7ffe3bd9a6/client/StandaloneWindows64/base_revision)
· [Matching November 12 extraction](https://gitlab.com/Dimbreath/animegamedata2/-/tree/a311cd77d7dafbd2bedc7d3cac4e986c6125b586)

The base revision is `49008628_644b3d946e`. Unpatched original audio and movies
use that base; patched packages use the current resource revision. Unchanged
packages retain their verified Sophon source. Changed packages are streamed
once into a private cache and verified against their complete publisher MD5
before any recording is exposed. Genshin's current CDN ETag is an opaque
multipart identifier, so a partial response's ETag is not used as an MD5 proof.
Subsequent reads verify the selected cache blocks, including after a process
restart. Snapshot identities contain only compact revision/index identities;
old recordings and indexes retain their original generation offline.

The source changed within the same 7.2 launcher build: compared with the
November 5 Windows resource index, two BLKs changed and
`Japanese/VO_7.2_b_0.pck` was added. Its 829,686 bytes match MD5
`d110dfe69ac4be4dc648627aec2a8a99`. The normal publisher voice API retrieves
its two exact authored Vesna friendship recordings (`friendship_01` and
`friendship_04`); neither external ID is unresolved. The new data/design
generation is selected independently of this voice change.
[New original Japanese package](https://autopatchhk.yuanshen.com/client_game_res/7.2_live/output_49411577_7ffe3bd9a6/client/StandaloneWindows64/AudioAssets/Japanese/VO_7.2_b_0.pck)

The normal installation-free Windows Japanese language worker selected the
current extraction and completed in 114.87 seconds. It produced 480,619
records: 186,719 voiced, 20,419 unavailable, 267,340 unknown and 6,141 unvoiced.
These include UI and player variants, not unique recordings or complete story
acceptance. Compared with the original launcher extraction, the English
TextMap has 56 rewritten existing hashes and two additions; 102 prepared
records contain the changed English translation, including voiced dialogue.
Both new Japanese profile captions match their own exact prepared line.
Normal LocalVoice exports of Fetter `143033` and `143036` decode to 15.182875
and 38.850 seconds. A newly opened voice service, fresh output directories
and prohibited publisher networking reproduce identical decoded PCM for both.
The production source hashes stayed unchanged throughout this worker proof.

The dispatch response is read over publisher HTTPS and the declared resource
hashes are checked. Independent RSA signature authentication of that response
has not been established; public launcher wrapping keys do not provide it.
A missing matching text commit, regional mismatch, malformed format or failed
checksum refuses the replacement generation and retains the previous prepared
table. Synthetic checks cover same-version text/voice changes without toolkit
code changes, edition-specific bootstrap parameters, the separate audio base,
changed movies, corrupted cache reads and old-generation offline playback.
This replaces the unresolved active-route limitation in the dated November 15
and earlier launcher-only checks below. Remaining authored caption/trigger
bindings, removed content and full platform/story acceptance remain open.

## Shared recordings with Traveler text conditions · November 16, 2026

Ordinary dialogue and reminders now render their authored M/F text fragments
and localized Traveler/sibling pronouns independently of the voice condition.
A shared recording can accompany two different displayed captions or
translations. The reader retains that original shared binding and selects
the text for the configured Traveler. Conditional fragments without an
opposite tag retain the surrounding text for that opposite branch.

The recording conflict check compares the original authored templates before
rendering. The two renderings of one template do not falsely disable each
other, while different original sentences pointing at one concrete recording
remain unavailable. Unsupported or empty source branches stay in the
inventory as diagnostics without audio. Unsupported translations are omitted;
they are never copied from the other Traveler. Historical recovery also
requires the exact rendered text and player condition, and cannot restore a
recording to an unresolved source branch. Index schema 19 and archive reader
4 refresh the affected maps without modifying existing recordings.

Normal source-development Windows publisher preparation was rerun with no
game folder, on the same Global 7.2 launcher snapshot and matching immutable
`bd35e243fa436f141f015cf221a6e19d0c34b7ca` extraction. It retained 476,560
records: 186,679 voiced, 20,510 unavailable, 263,227 unknown and 6,144 unvoiced.
These totals include player text variants and UI; they are not unique
recordings or complete story acceptance. Six unresolved source variants
remain diagnostic records. No voiced source retains an unrendered M/F or
SEXPRO marker.

For Dialog `30220315`, the full prepared index matches each rendered English
caption only for its selected Traveler. Both variants export the same authored
original WEM through LocalVoiceAssetService. Each decoded MP3 contains 655,648
nonzero PCM bytes with SHA-256
`ffd1f8bc7658f2d6a0184e775954eaaa8410754fa329624a0d51378c8484f91b`.
Fresh conversions after reopening the service, with discovery and package
networking prohibited, reproduce that PCM. This verifies one shared English
performance and its caption selection, not both protagonists' full narrative
or all dubs/platforms. This earlier proof used the launcher snapshot; the later
active-hotfix check above extends publisher preparation.
[Original dialogue graph](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Talk/Quest/302203.json)
· [Matching original voice declarations](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice)

## Kachina's English profile recording · November 15, 2026

Fetter `100024` belongs to Kachina, avatar `10000100`, and is titled
*About Citlali*. It uses voice trigger `4005`, voice switch `switch_kachina`
and text hash `2954663063`. The 5.5 and 7.2 voice declarations both resolve
to `English(US)\VO_friendship\VO_kachina\vo_kachina_teammate_citlali_01.wem`,
whose external-media ID is `b43555dea8d39785`.
[7.2 profile table](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/FettersExcelConfigData.json) ·
[7.2 voice declarations](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice) ·
[5.5 voice declarations](https://github.com/DimbreathBot/AnimeGameData/tree/dcf2fa8cccfe7bdc70797d1cfce79f6907806835/BinOutput/Voice)

An installation-free read of every external-media table in the Global 5.5 base
checked 160 English packages and 116,425 serialized entries. The Global 7.2 base
checked 178 English packages and 174,297 entries. Neither inventory contains
that declared ID. The publisher manifests and their chunk digests were
verified by the normal reader. The counts refer to serialized table entries.
[5.5 English manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/wUcNY2SeSiQE/manifest_f67cb4385a052f1f_485143352632d8d353b19e7ab85a35f5) ·
[7.2 English manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/msj5r4DqSLOw/manifest_17a2098527183c10_860f28f0e5bfd9b243a35760a8243968)

This English row keeps the `unavailable` recording state. Later launcher
snapshots re-evaluate the authored source. The November 5 hotfix inspected
below also lacks the recording. The current November 16 inventory independently
checked all 179 English packages and 174,299 serialized entries under active
resource revision `49411577`; it still contains zero hits for the declared
recording. This remains an unavailable performance, not verified silence.

## Windows 7.2 hotfix source verification · November 15, 2026

A public Android dispatch snapshot supplied the route hint for resource
revision `49086080`, suffix `1c55d912bf`, and data/silence revision `49291486`,
suffix `c25ba650a6`. This hint was not treated as a Windows manifest or proof
of the currently activated Global revision. The corresponding Windows indexes
were fetched independently from both publisher regions. Every paired body
was byte-identical. The data indexes additionally matched the dispatch
snapshot's declared size and MD5.
[Pinned route hint](https://github.com/HertaA11/genshin-android-hotfix/blob/412e899357942771b2b7d701ba915eb213f47207/CNRELAndroid7.2.0.json)

| Index | Bytes | Rows | MD5 |
| --- | ---: | ---: | --- |
| Windows `res_versions_external` | 370,806 | 2,630 | `f4da719220541436f56fd80f4ea510bb` |
| Windows `res_versions_medium` | 207,245 | 1,312 | `0e329f1abd269a2ee22213ec379257f5` |
| General `client/…/data_versions` | 71,416 | 533 | `2d53a763cf78415d4a90c81be3419da5` |
| General `client/…/data_versions_medium` | 7,002 | 52 | `6bf505fc8e990e881ae5b436b6a4071c` |
| General `client_silence/…/data_versions` | 523 | 4 | `2bcf33810856cb0820725300ff2d8666` |

[Global Windows resources](https://autopatchhk.yuanshen.com/client_game_res/7.2_live/output_49086080_1c55d912bf/client/StandaloneWindows64/res_versions_external)
· [CN Windows resources](https://autopatchcn.yuanshen.com/client_game_res/7.2_live/output_49086080_1c55d912bf/client/StandaloneWindows64/res_versions_external)
· [Global design data](https://autopatchhk.yuanshen.com/client_design_data/7.2_live/output_49291486_c25ba650a6/client/General/AssetBundles/data_versions)
· [CN design data](https://autopatchcn.yuanshen.com/client_design_data/7.2_live/output_49291486_c25ba650a6/client/General/AssetBundles/data_versions)
· [Global silence data](https://autopatchhk.yuanshen.com/client_design_data/7.2_live/output_49291486_c25ba650a6/client_silence/General/AssetBundles/data_versions)
· [CN silence data](https://autopatchcn.yuanshen.com/client_design_data/7.2_live/output_49291486_c25ba650a6/client_silence/General/AssetBundles/data_versions)

The Windows index contains 179 English PCKs. All 178 base English packages
retain exactly their Sophon path, size and MD5. The sole additional package,
`English(US)/VO_7.2_a_0.pck`, is 230,283 bytes with MD5
`f820260ccca60e0e7f67519096707553`. Its complete body was fetched separately
from each publisher region and verified. Both contain the same two original
WEMs. They decode to nonzero 48 kHz mono audio without a game installation.
[Global audio package](https://autopatchhk.yuanshen.com/client_game_res/7.2_live/output_49086080_1c55d912bf/client/StandaloneWindows64/AudioAssets/English(US)/VO_7.2_a_0.pck)
· [CN audio package](https://autopatchcn.yuanshen.com/client_game_res/7.2_live/output_49086080_1c55d912bf/client/StandaloneWindows64/AudioAssets/English(US)/VO_7.2_a_0.pck)

| External media ID | Authored sentence trigger | Original WEM bytes | Decoded duration |
| --- | ---: | ---: | ---: |
| `189754f4bdbc1f5f` | `70291110`, Varka | 75,351 | 4.386 s |
| `fd8d9fa8dc7b56de` | `776810312`, Iliana | 154,820 | 8.280 s |

The existing 7.2 voice declarations bind these IDs through their original
`sourceFileName` values, respectively `vo_ZDAQ7029_8_varka_01.wem` and
`vo_NWWQ004_4_iliana_06.wem`. Neither ID is Kachina's missing profile ID.
The unchanged base package identities and both complete new entries extend
that absence check to this particular hotfix.
[Authored voice records](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice/Items)

The metadata archive has an exact Windows title for these R/S/D revisions,
dated November 5. It also has a newer November 12 Windows title with resource
revision `49411577`, silence `49291486` and data `49419538`. At the time of
this November 15 check, the newer resource suffix and active Global route
remained unverified. The November 16 check above subsequently verified both
regions and connected matched text and original audio overlays to normal
publisher preparation.
[Matching November 5 Windows snapshot](https://github.com/DimbreathBot/AnimeGameData/commit/d7f2135c7eb0052e842e0f187f4e5bb88c304737)
· [Newer November 12 Windows snapshot](https://github.com/DimbreathBot/AnimeGameData/commit/a311cd77d7dafbd2bedc7d3cac4e986c6125b586)

## Regional Windows Setup, November 13, 2026

Setup can acquire the active Global or mainland China launcher release. It follows
the selected regional HoYoPlay branch and downloads original voices from that
region. For the Global base it first requests the exact OSRELWin text extraction.
A CNRELWin extraction can supply the same text only when both independently
released game builds agree on the version, revision markers and complete
AssetBundles inventory by relative path, size and publisher checksum. Setup
also compares the resource, data and silence indexes, content table and service
catalog. A mismatch requires a matching Global extraction. Each voice binding
keeps its original region's immutable Sophon build and selected package.
[Global launcher](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8)
· [Mainland launcher](https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?launcher_id=jGHBHlcOq1)

Global 7.2.0 build `msj5r4DqSLOw` and mainland build `asDgc67wRUeO`
shared all 2,031 AssetBundles blocks, the three revision files, all three
streaming indexes, the content table and service catalog. On Windows the
language worker used the Global publisher channel with an empty game-folder
setting and the matching immutable text revision. It prepared 464,300 English
records with Simplified Chinese translations requested. Of these, 160,654
had verified original audio. LocalVoice exported one story line and one
profile line to MP3. From distinct Global publisher packs the story line
`80030105` decoded to 8.263 s in English, 6.093 s in Japanese, 5.048 s
in Korean and 6.267 s in Mandarin. This comparison covers launcher bases.
The November 16 follow-up above adds active regional hotfix discovery and
replacements to these previously verified launcher bases.
[Matching text extraction](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca)

When the primary catalog rate-limits requests, Setup can use the maintained
GitHub copy. It compares the release title to the publisher revisions and
fetches the exact immutable commit. Larger authoring directories use Git if
available. The existing regional comparison still applies before using
mainland translation data for a Global release. Both hosts supply text
and binding metadata. Original recordings come from the selected publisher.

On November 13, the primary commit endpoint returned HTTP 429. With an empty
active metadata cache and primary requests deliberately limited throughout a
Windows worker test, 25 requests fell back to the mirror. The worker downloaded
the actual English and Chinese data, verified the live Global launcher's
release and indexed 471,176 entries in 116 seconds. Previously cached publisher
packages and historical indexes were reused. Normal playback exported the
original English line `80030105` to an 8.304-second MP3.
[Maintainer's live metadata mirror](https://github.com/DimbreathBot/AnimeGameData/tree/main)
· [Matching immutable release](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca)

## Character triggers in gameplay, November 13, 2026

The reader follows each authored AnimatorEvent, WeatherMonologue, JoinTeam,
Costume and Gacha trigger's original WEM, actor switch and player condition.
A trigger can carry several eligible performances. When the same performance
has one unique subtitle hash in the character profile table, its existing
profile row also supports gameplay capture. The selected audio binding
records the originating trigger types and IDs. Different texts attached to the
same performance remain ambiguous. Sources without a mapped actor, a unique
profile subtitle or a matching dub recording do not acquire a spoken line.

| Trigger family | Matched English profile performances on 7.1 | Matched English profile performances on 7.2 |
| --- | ---: | ---: |
| AnimatorEvent | 1,701 | 1,733 |
| WeatherMonologue | 453 | 461 |
| JoinTeam | 365 | 371 |
| Gacha | 122 | 124 |
| Costume | 0 | 0 |

On 7.2 the normal Windows language worker verified the selected English
recording for every counted performance. One line per matched family was
exported through LocalVoice. The four samples also decoded in each of the four
original Global dubs. The 7.1 column counts actor, media and text joins.
Of 31 distinct 7.2 Costume actor/file combinations, eight also occur among
Fetter's source candidates. None supplies a unique profile sentence through
its actor and trigger. The outfit name or inventory description cannot identify
the words in its original performance.
[Publisher text and playback metadata extraction](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice)
· [Outfit configuration](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/AvatarCostumeExcelConfigData.json)

### Costume wear-voice sources

Checked November 16, 2026. The 31 actor/file combinations above contain **30
distinct original WEM paths**. The original `ConfigCostumeData` separately
declares costume-specific `audio.wearVoice` Fetter triggers, using IDs
`5000001` through `5000003`.
`AvatarCostumeExcelConfigData` joins the outfit's `jsonName`, `skinId` and
`characterId`; the voice declarations also reference these recordings through
Costume triggers. These are original wear-voice bindings. None of the 9,330
profile rows references those three Fetter trigger IDs as its `voiceFile`.
The outfit names and descriptions therefore do not establish their spoken
captions. Separately, 18 profile rows have explicit show/hide costume lists;
those rows are not subtitle references for the three wear-voice triggers.
[Original wear-voice configuration](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Fashion/AvatarCostume/ConfigCostumeData.json)
· [Original outfit identities](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/AvatarCostumeExcelConfigData.json)
· [Fetter wear-voice source declarations](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice/Items)

The current hotfix's `ConfigCostumeData` is byte-identical to the launcher
baseline. Its 22 wear-voice declarations still provide no join to the three
trigger IDs in the current 9,330 Fetter rows. A bounded static inspection of
the original native metadata distinguishes `VoiceTrigger.Costume` from
`VoiceTrigger.Fetter`, but does not establish the exact outfit UI callback or
an authored subtitle reference. An `OnAvatarChangeCostume` string occurrence
belongs to an enum parser and is not accepted as an audio caller.

All 30 recordings have exact external-media entries in **each of the four
Global 7.2 launcher dubs**, for 120 verified index hits. The selected publisher
snapshot is `sophon-949715f1227aa46c6238a9484a772ca543d19e6387c20b9807ea5d1fd68ae534`.
These are availability checks, not playback of all 120 recordings. The unchanged
publisher reader additionally retrieved Diluc's
`VO_Costume\VO_diluc\vo_diluc_suit_aristocrat_02.wem` into a separate research
cache in each dub, without a game installation. Every sample decoded to
nonzero 48 kHz mono PCM:

| Dub | External media ID | Original WEM bytes | Decoded duration |
| --- | --- | ---: | ---: |
| English | `a98f0f9936ea7fdb` | 95,371 | 4.514792 s |
| Japanese | `2b19f33173a04e9d` | 54,376 | 3.073250 s |
| Korean | `032cc39612ca3064` | 53,661 | 2.542500 s |
| Mandarin | `6fd71aa0e4fca483` | 37,745 | 2.302563 s |

The missing part is the wear voices' original **caption/text binding**, not
availability of these 30 original recordings in the checked launcher source.
No sentence, translated transcript, silence classification or capture alias
is inferred from an outfit description. Full wear-voice sentence capture,
full live-device hotfix activation and other native-host acceptance remain open.

## Character profile and combat performances, November 9, 2026

Normal preparation joins the profile's avatar ID, Fetter voice trigger and
subtitle hash to the actor's configured voice switch. The avatar's numeric
`combatConfigHash` also resolves newly numbered configuration files. Original
media comes from the selected publisher dub. Separate male and female takes
use each source's gender field. Across 11,869 Fetter GUID/file pairs shared by
7.1 and 7.2 the named and obfuscated actor fields agreed. The corresponding
gender fields agreed for all 32 pairs with an explicit gender.
[Character configuration](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Avatar)
· [Profile text and triggers](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/FettersExcelConfigData.json)

| Publisher release | Distinct Fetter rows | Rows with original audio |
| --- | ---: | --- |
| Mainland 7.1.0 | 9,183 | 9,182 English |
| Mainland 7.2.0 | 9,330 | 9,329 English, all 9,330 in Japanese, Korean and Mandarin |

The same reader resolved all 147 newly added character entries. A profile
performance and a combat performance for Valeriy decoded in each dub. The
English samples lasted 24.505 and 1.120 seconds. The selected English
packages lacked Kachina's source for Fetter 100024. Her three other dubs
contained the source. The normal English desktop worker exported Valeriy's
two samples and Venti's two protagonist takes, then reproduced the four MP3s
offline using a fresh output directory. Independent AnimatorEvent, WeatherMonologue, JoinTeam,
Costume and Gacha triggers still need their own text and media evidence.

## Installation-free launcher release, November 9, 2026

Without a game folder the Windows language worker follows the released mainland
HoYoPlay branch into its Sophon build. It reads the Windows resource, silence and
data revision markers from the game manifest and selects the immutable CNRELWin
extraction matching all three. For 7.2.0 the matching markers were 49008628,
48722240 and 49008628. Two later 7.2 text snapshots already described hotfixes.
The worker verifies the decompressed checksums of manifests and audio chunks,
uses each localized PCK's own bounds, and fetches the original WEM for the
selected authored path. Existing prepared recordings keep their immutable
build identity. The updater can adopt another launcher build when the same
formats and matching text snapshot are available.
[Mainland released branch](https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?launcher_id=jGHBHlcOq1)
· [Matching text revision](https://gitlab.com/Dimbreath/animegamedata2/-/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca)

The Global and mainland manifests had matching file checksums for all 178
localized PCKs in each of the four dubs. The text comes from the mainland
catalog. Independent Global hotfixes and historical performances still have the
separate coverage described below.


Audited 2026-10-27 against an installed Windows 7.1.0 client and its English
voice pack. No account, game files, settings or live companion data were changed.
The read-only inventory found 1,985 asset BLKs, 275 USM movies and 310 audio PCKs.
The existing external-table reader resolved 169,523 English entries in 176 PCKs.
These are resource counts, not a claim that every resource is dialogue.

The metadata reference was Dimbreath's community mirror at
`792978e5503ecfba73dcb3562ed44a0d35a2abe2`, titled
`CNRELWin7.1.0_R48379043_S48511369_D48533839`. This is a third-party snapshot
of game data, not an official publisher API. The installed BLKs were inventoried
but their encrypted narrative data was not independently decoded. Matching the
release number does not establish that every server hotfix or optional asset is
present. Playback additionally requires the exact source hash and bounds in an
installed locale package.

## Presentations and limits

| Presentation | Observed evidence | Adapter behavior and remaining gap |
| --- | --- | --- |
| Quest and ordinary conversations | 23,208 Quest Talk files; 203,908 global DialogExcel rows; several coexisting Talk schemas | Parses supported authored ID/hash pairs. Runtime Talk records take priority; the global table fills absent IDs. Conflicting identities are excluded. |
| Optional NPC, gadget, furniture and hangout interactions | 16,927 Npc, 1,473 NpcOther, 1,485 Gadget, 1,287 Coop and associated group configurations | Supported Talk content is included regardless of whether it has audio. Group/routing configuration alone is not dialogue. Missing voice metadata stays unknown. |
| Events | 2,107 Activity Talk files, 105 ActivityGroup files, many dedicated event Excel tables | Supported event Talk content is indexed. Event-specific UI formats and expired/removed assets do not acquire coverage merely because ordinary event Talk works. |
| Ambient dialogue and reminders | 18,541 ReminderExcel rows and 1,798 BubbleTalkData rows on 7.1 | Reminders use their own Medium-first hash space. An authored audio flag with missing audio is unavailable. Bubble texts and information boards use their original localized content hash. General ambient speech bubbles have unknown voice status. |
| Character/profile and combat voices | 9,183 FettersExcel rows on 7.1; voice triggers include Fetter, AnimatorEvent, WeatherMonologue, JoinTeam, Costume and Gacha | The November 9 profile audit above covers the Fetter trigger and actor join on two releases. Other trigger families and combat sounds without authored subtitles remain open. |
| Card-game dialogue and tutorials | 1,256 GCGTalkDetail rows with parallel content/voice arrays | Nonzero voice IDs are paired with the original array position, including gaps. Conflicting IDs are excluded. Zero-voice slots and emoji-only messages remain outside this import. |
| Choices and black-screen narration | 23,483 global forced-choice rows; explicit black-screen role types | Retained and tagged by authored modality. A player role, blank audio filename or missing voice does not establish silence. Exact voice bindings still take precedence. |
| Storyboards, comics and cinematic dialogue | 242 Storyboard Talk files, 159 StoryboardGroup files and 37 Cutscene Talk files | Supported Talk rows are retained; explicit storyboard/narration types receive cinematic channel coverage. No claim of complete comic layout or sequence recognition. |
| Prerendered cinematics | Version-matched SRT subtitles and regional Windows USM inventory | Exact movie names yield timed subtitles and predecessor context. Locale recordings and isolated spoken performances remain unresolved. |
| Books, notes and readables | 1,919 English Readable text files; localized file identities | Version-matched book assets are indexed by paragraph as text-only content. Translations require the same file identity and paragraph count. Other readable assets and exact overlaps with known authored voice text remain unknown. This is not blanket support for voiced Travel Log archives. |
| Mail, messages and glasses chat | Mailbox templates, system notifications, Eye of Graeae messages, replies, topics and attachments | Setup imports authored text, translations and identified senders from the matching public version. Mailbox templates and system UI support unvoiced capture. Chat performances have unknown voice status. |

The reference contains 55,891 Talk files and 9,677 Voice files in total; many
are routing, lookup or emotion records. Counts overlap the presentation rows and
must not be summed as independent dialogue totals. Unrecognized content schemas,
missing localized text and unresolved performances produce public coverage
warnings rather than silently implying completeness.

## Update and voice safety

`LANGUAGE_INDEX_VERSION` is 3. The adapter checks the metadata release title
against the installed launcher configuration. A known version mismatch or wholly
unrecognized voice schema produces `unsupported_game_format` with a refresh/update
instruction. Unknown version provenance blocks text-only readable imports.
The common fingerprint includes text/config manifests and authored design data
where present, so voice-package stability alone is insufficient to reuse an index.
The installed-file check hashes the three `AssetBundles/*_revision` markers,
the base text/resource manifests and the persistent `data_versions_persist`
and `res_versions_persist` indexes. A replacement with the same size and
timestamp now invalidates the prepared index. Remote-only changes still
require the regional online updater in #83.
[Global 7.2 base manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/msj5r4DqSLOw/manifest_92303edbe132c634_2b4ef596e7440779759717433d1c86d9)
· [Persistent index paths](https://github.com/CollapseLauncher/Collapse/blob/7d975a8ffec73c6790af5194655dbc3ce85fef67/CollapseLauncher/Classes/RepairManagement/Genshin/Fetch.Persistent.cs#L76-L109)

Voice paths must match an installed locale's hashed external entry. Missing
packages and ambiguous performances are retained as unavailable, not silently
unvoiced. Multiple performances are accepted only as one distinct male/female
pair; two same-gender candidates cannot produce duplicate IDs. Traversing or
absolute source paths are rejected. No audio is synthesized and no missing text
is translated or transcribed from sound.

The November 8, 2026 source check verified that Genshin's Mandarin packages
and Wwise paths use `Chinese` for both Simplified and Traditional Chinese.
Two Paimon lines matched the published 4.8 Mandarin index, one in `1001.pck`
and one in `External21.pck`. The alternative `Chinese(PRC)` hash matched
neither. The reader now probes and hashes the Genshin namespace and preserves
previously bound local recordings that use the older toolkit spelling. The
official server supplied the Mandarin evidence. The installed 7.1 client in
the original audit contained the English pack.
[Publisher 4.8 Mandarin file index](https://autopatchcn.yuanshen.com/client_app/download/pc_zip/20240705190726_7q0dq7IxqQEpugte/ScatteredFiles/Audio_Chinese_pkg_version)

In the 7.2 extraction, 4,545 reminder rows explicitly signal audio. Of those,
4,127 name a WEM through a recognized voice trigger. The other 418 remain
unavailable. One has a routing lookup without a source file, two share a
number with a different trigger type, and 415 have no matching trigger in the
reviewed metadata. The checked 7.1, 6.7 and 4.5 voice snapshots supplied no
additional exact paths for those IDs. Missing reminders still require a
different authored binding or historical source.
[Reminder flags](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/ExcelBinOutput/ReminderExcelConfigData.json)
· [Voice trigger lookup](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Voice/Lut/Lut.json)

Readable downloads are immutable-revision archives parsed in memory. The parser
rejects traversal, links, foreign directories, duplicate identities and excessive
file/expanded sizes. It never extracts upstream paths. Book capture remains the
global opt-in exact-match behavior; partial page text and unknown voice status
do not gain fuzzy unvoiced capture.

## Ambient bubbles and scene boards

The 7.2 Global worker added 1,297 English entries with Simplified Chinese
translations, bringing the prepared total to 471,176, including 180,974 original
voices. Of 50 explicitly authored scene text boards, 49 qualify for unvoiced
capture. One also occurs as authored voice text, so capture keeps it ambiguous.
The 1,247 other bubbles lack a sentence-specific voice link. The 7.1 named
sound-effect field and the corresponding 7.2 field assign precisely the same
cardboard pop-up effect to 83 different bubbles, of which 69 have English text.
The reader keeps their text and excludes the shared effect from voice playback.
The same public schema test yielded 1,289 English entries on 7.1, 741 on 5.5
and 612 on 4.8. Known developer placeholder identities are excluded.
[7.2 bubble authoring table](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/BubbleTalkDataExcelConfigData.json)
· [7.1 sound-effect field](https://gitlab.com/Dimbreath/animegamedata2/-/blob/9587d1afbd9ab0419cdd00dc05ecd114b9e3fe99/ExcelBinOutput/BubbleTalkDataExcelConfigData.json)

## Written mail and Eye of Graeae messages

On 7.2 the Global Windows preparation worker returned 469,879 English records.
Of the 1,044 authored mailbox and message records, 332 were mail bodies, 332
were mail subjects and nine were system notifications. The Eye of Graeae
interface provided 281 full messages, 51 choices, six attachment captions,
four location objectives and 29 thread titles. All 1,044 had Simplified
Chinese translations. The five supported study selections each exposed
these entries, with one additional mail subject and body in Simplified Chinese.
The same reader found 984 English records on 7.1.

The mailbox uses the Medium text namespace. System notifications and Eye of
Graeae use the ordinary namespace. The reader distinguishes the full message,
preview, attachment, option and identified sender fields. It recognizes
renamed fields by their uniquely preserved values across independent records.
In the 7.2 public client data, the chat body and option hashes have no exact
DialogExcel text-hash link. Sample sentences shared with other presentations
therefore retain unknown audio status. The Windows capture index recognized
mail 3, including its Chinese translation, with unvoiced capture enabled.
[7.2 mailbox](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/MailExcelConfigData.json)
· [7.2 Eye of Graeae messages](https://gitlab.com/Dimbreath/animegamedata2/-/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/TpsGlassesChatMessageExcelConfigData.json)
· [7.1 Eye of Graeae messages](https://gitlab.com/Dimbreath/animegamedata2/-/blob/9587d1afbd9ab0419cdd00dc05ecd114b9e3fe99/ExcelBinOutput/TpsGlassesChatMessageExcelConfigData.json)

## Conflicting source recordings

### Authored protagonist conditions

Ordinary voice events can select different original media for a female or
male Traveler even when the filename contains neither name. On 7.2, 3,253
distinct Dialog trigger IDs described exactly two different source conditions.
On 7.1, 3,196 did so. The reader follows the explicit condition and renders
the corresponding M/F subtitle branch, including single-condition takes.
Conflicting conditions or an unrecognized flag block playback. Historical
indexes are upgraded once to include the newly recognized takes.

On the Global 7.2 English worker, 5,738 additional entries had playable
original recordings after this change, bringing the total to 186,607 of
474,075 entries. Of these, 20,594 came from older publisher releases.
Conversation ID `401710225` was recognized independently for each Traveler
selection and exported to a 2.136-second male and 2.184-second female MP3.
[7.2 playback conditions](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice)
· [7.1 playback conditions](https://github.com/DimbreathBot/AnimeGameData/tree/9587d1afbd9ab0419cdd00dc05ecd114b9e3fe99/BinOutput/Voice)

Some translations reference the player’s or sibling’s pronouns and forms
of address through separate localization keys. The current worker now
renders the selected character’s official wording for 522 voiced English
records whose Chinese translations contained those tokens. The reader checks
the original ManualTextMap and locale hash tables. On both 7.1 and 7.2,
all 704 Simplified Chinese source strings containing these constructs had
complete renderings for both Travelers, including the two complete sentences
selected by the Twins2 keys. Unknown or ambiguous keys remain unavailable.
[Versioned word and sentence keys](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/ManualTextMapConfigData.json)

### Reused audio

The 7.2 Global metadata assigns one original file to both opening dialogue
`3500404` (the unknown god addresses the travelers) and `3500424` (the
Traveler calls for their sibling). Checking the full index identified 35
physical recordings assigned to 112 distinct entries with incompatible English
sentence text. These include archived event dialogue and reused character
reactions. Preparation compares the actual original release, package, media ID,
dub and displayed study text across presentations. Capitalization and punctuation
alone preserve a shared performance. Conflicted entries retain their text and
unavailable status unless the actual audio bytes independently identify the
correct sentence. The three decoded English, Mandarin and Korean recordings of
the unknown god are 2.939, 4.628 and 2.911 seconds respectively. On these
originals independent speech recognition reproduced the god’s line. The Korean
transcript varied slightly in the pronoun. The toolkit checks the exact
original WEM digest and official source text before restoring this single
sentence. The traveler’s sibling line remains unavailable. The Japanese
publisher package had no corresponding file. A changed recording or rewritten
caption needs a fresh check before this exception can apply.
[7.2 original voice triggers](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/BinOutput/Voice)
· [7.2 authored dialogue](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/ExcelBinOutput/DialogExcelConfigData.json)

## Short conversation cues

The 7.2 Global English Talk graph provides 122,504 definite predecessor links
between playable conversations. Of these, 5,836 successors have fewer than
eight normalized English characters. Only a unique incoming edge from one
unconditional outgoing edge is used; disagreements, branching choices and
missing recordings are excluded. Capture requires a stable exact predecessor
inside the same window, crop, language, player variant and capture session.
Global Dialog `401860220` could not be selected from its short caption alone.
Replaying its authored preceding caption twice in the normal language index
selected the correct original performance. The 7.1 runtime successor field
also agreed with 165,503 nonempty Excel transitions. Four conflicting pairs
were excluded. Previous context never adds audio to a line with no binding.

## Cinematic subtitle timing

The November 13 cinematic check matched 252 of the 319 English subtitle files
to one of 279 Global 7.2 launcher movies. Four matching files contained no
caption text. The remaining 248 movies contributed 4,535 English cues and
4,283 immediate predecessor links. Japanese had 4,563 cues, Korean 4,538,
simplified Chinese 4,586 and traditional Chinese 4,580. Mainland 7.1 had
4,330 English cues from 240 of its 275 movies. Cue identities retain exact
start and end milliseconds. Languages may time dialogue differently, so an
ordinal-only match is insufficient. Translation joins use matching ordinal
and timestamps, or complete matching ordinal sequences with exclusive
overlapping intervals in both directions. This yielded 2,417 simplified
Chinese translations for the Global 7.2 English cues. The subtitle timeline
establishes the text's display time. Other movies still require a clean source
or independently verified locale audio track for each sentence.
[7.2 movie subtitles](https://github.com/DimbreathBot/AnimeGameData/tree/bd35e243fa436f141f015cf221a6e19d0c34b7ca/Subtitle)

For the first opening movie, the six complete dialogue texts in order match
the entire published cue sequence independently in all five study selections.
The Korean timeline uses nine cues, the other four use ten. Where a sentence
spans successive subtitle cards, its clean original WEM is published under
a complete-sentence ID. Each card keeps its original display interval.
The 7.2 Global base yielded all six complete performances in English, Korean
and Mandarin as separate voice files, and the first three Paimon lines in
Japanese. The Japanese movie soundtrack supplies the three remaining lines.

The first Paimon performance decoded to 5.133 seconds in English, 4.645 in
Japanese and Mandarin, and 4.028 in Korean. Normal Windows playback exported
the English film performance to a 5.160-second MP3. Its full timeline spans
1.450–6.852 seconds across two caption cards. The worker counted 471,180
English records with 180,869 playable entries, including 20,294 recovered
from earlier releases. The six film entries reuse separately authored
dialogue performances.
[English opening captions](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/Subtitle/EN/MDAQ001_OPNew_Part1_EN.srt)
· [Korean opening captions](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/Subtitle/KR/MDAQ001_OPNew_Part1_KR.srt)

### Japanese opening soundtrack

Japanese Windows Setup obtains all six opening performances from HoYoPlay
without a game installation. For the final three, the exported clip includes
the original voice, music and effects from the movie. The uploader's gameplay
starts about 0.86 seconds later than the 7.2 movie clock. The publisher's
Japanese preview has a shorter lead-in.

| Speaker and published subtitle | Publisher movie interval | Independent Japanese gameplay | Publisher's Japanese preview |
| --- | --- | --- | --- |
| Unknown god · 余所者 お前たちの旅はここまでだ | 24.100–28.844 s | [0:25](https://www.youtube.com/watch?v=br9TzkXmRA0&t=25s) | [0:13](https://www.youtube.com/watch?v=hQrHQVi2p2c&t=13s) |
| Lumine · 誰っ！？ | 30.781–31.725 s | [0:32](https://www.youtube.com/watch?v=br9TzkXmRA0&t=31s) | [0:20](https://www.youtube.com/watch?v=hQrHQVi2p2c&t=19s) |
| Unknown god · この「天理」の調停者が / ここで「人の子」の驕りに終焉を | 32.025–36.986 s | [0:33](https://www.youtube.com/watch?v=br9TzkXmRA0&t=32s) | [0:21](https://www.youtube.com/watch?v=hQrHQVi2p2c&t=21s) |

In the Global 7.2 release the opening movie is 76,360,448 bytes. Its four
stereo streams decoded using the bundled voice decoder. The separate Japanese
Paimon recording matched only the third stream strongly (0.92 normalized
correlation), and all three movie intervals matched the gameplay soundtrack
(0.98, 0.97 and 0.98). Global 4.8 and 5.5 shipped an earlier 76,356,000-byte
movie; its Japanese track matched the same three gameplay intervals at 0.97,
0.95 and 0.97. None of those three releases supplied the final three Japanese
performances under their separate authored WEM paths. [Global 7.2 publisher manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/msj5r4DqSLOw/manifest_92303edbe132c634_2b4ef596e7440779759717433d1c86d9)
· [Japanese subtitle cards](https://github.com/DimbreathBot/AnimeGameData/blob/bd35e243fa436f141f015cf221a6e19d0c34b7ca/Subtitle/JP/MDAQ001_OPNew_Part1_JP.srt)

Setup checks the selected regional game's movie manifest. A normal game
update may retain the movie or repack its tracks in another order. The reader
accepts a repack only when exactly one audio stream has the SHA-256 of a
verified Japanese recording. Playback rechecks that content and the selected
sentence interval before exporting. A different dub, changed recording,
changed subtitle wording or shifted cue does not inherit the old binding.

## Historical quest and event audio

On November 8, 2026, the source audit compared the Global 7.2 Windows base
voice packs with 14 earlier mainland-China Windows releases. Each supplied
Mandarin, English, Japanese and Korean. The audit checked all four 7.2 Sophon
voice-manifest checksums and read the external Wwise directories from 178 PCKs
per dub. The historical checks used bounded requests to publisher packages
where individual files were available. For later releases, they followed the
archived branch and version through the publisher's Sophon build service to
the four locale manifests and their chunks.
[Global launcher branches](https://sg-hyp-api.hoyoverse.com/hyp/hyp-connect/api/getGameBranches?launcher_id=VYTpXlbWo8)
· [4.8 publisher package index](https://autopatchcn.yuanshen.com/client_app/download/pc_zip/20240705190726_7q0dq7IxqQEpugte/ScatteredFiles/Audio_Chinese_pkg_version)
· [3.8 distribution record](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/3.8.0.json)
· [2.8 distribution record](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/2.8.0.json)
· [Historical launcher records](https://github.com/kuaichu/game-cdn-archive/tree/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e)

The same 14 historical Windows builds are available on the Global CDN. For
each build and dub, the audit compared the Global and mainland inventories by
package path inside StreamingAssets, byte length and publisher MD5. All
**8,256 PCK entries across 56 release/language combinations** matched in both
directions. For Sophon releases the build, version tag and game manifest were
checked against the archived Global release and each voice manifest was
verified against the checksum from the publisher. This gives a Global source
for the 39,020 additional IDs recovered from historical editions below.
[Global release records](https://github.com/umaichanuwu/meta/blob/9019bb94f6dccb62bd11be734599644ed20e73b3/hoyodata.json)
· [Global 3.1 Mandarin package index](https://autopatchhk.yuanshen.com/client_app/download/pc_zip/20220917165430_NyMmj1Ta9KlZKgCZ/ScatteredFiles/Audio_Chinese_pkg_version)
· [Global 6.2 Japanese voice manifest](https://autopatchhk.yuanshen.com/client_app/sophon/manifests/cxhpq4g4rgg0/b1yX8g30suHF/manifest_e6602b44c4d9a827_01aedf0468eb7ff42026a26d195e6447)

The comparison starts with 188,882 distinct 7.2 Dialog IDs with an
unambiguous text hash, English and Simplified Chinese text, and at least one
recognized authored Dialog WEM path. Of these, 36,120 occur in timed-event
quests via the quest's explicit `type: EQ`, its talk ID and the Talk record's
dialogue IDs. Each hit requires **every authored path in all four dubs of the
same release**. The rows count IDs once across releases, in the order shown.
[7.2 Talk records](https://github.com/DimbreathBot/AnimeGameData/tree/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Talk)
· [Quest assignments](https://github.com/DimbreathBot/AnimeGameData/tree/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Quest)
· [Authored voice paths](https://github.com/DimbreathBot/AnimeGameData/tree/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Voice)

| Windows release | Additional IDs with all four dubs | Of those, timed-event IDs |
| --- | ---: | ---: |
| 7.2 Global base | 149,737 | 6,241 |
| 4.8 mainland China | 16,520 | 12,574 |
| 3.8 mainland China | 0 | 0 |
| 2.8 mainland China | 11,889 | 9,112 |
| 1.6 mainland China | 0 | 0 |
| 5.8 mainland China | 6,628 | 5,288 |
| 6.4, 6.7 and 7.1 mainland China | 0 | 0 |
| 3.1 mainland China | 1,432 | 717 |
| 6.2 mainland China | 2,551 | 2,175 |
| 6.1, 6.0, 5.5 and 2.4 mainland China | 0 | 0 |
| **Present in at least one of the 15 releases** | **188,757** | **36,107** |
| **Still missing or incomplete** | **125** | **13** |

Of the remaining 125 IDs, 56 lacked a complete set of their authored paths
in any single dub, and 69 had at least one dub. For a playback check, the
publisher's 3.1 files supplied all four complete WEMs for Dialog `400790201`
in the event quest *Bonds of Melody*. The Mandarin, English, Japanese and
Korean recordings decoded to non-silent PCM lasting 4.544, 5.759, 7.560 and
5.575 seconds respectively. A second download from the Global 3.1 server
decoded to the same durations and had identical SHA-256 digests for all four
original WEMs. [Authored quest](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Quest/40079.json)
· [Audited 3.1 distribution](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/3.1.0.json)

The 13 incomplete event IDs were also checked in the releases that carried
their events. One ID in quest 40010 (1.6) and five in quest 40040 (2.4) had
Mandarin, English and Korean media in those releases. The authored Japanese
paths were absent. For seven IDs in quests 40177–40179 (5.5), the 7.2 paths
were absent from all four original release indexes. An alternative authored
binding or in-version update is still needed to resolve those performances.
[Quest 40040](https://github.com/DimbreathBot/AnimeGameData/blob/d7f2135c7eb0052e842e0f187f4e5bb88c304737/BinOutput/Quest/40040.json)
· [Global 2.4 Japanese package index](https://autopatchhk.yuanshen.com/client_app/download/pc_zip/20211225051318_JHACtHpvJ2yRaZH0/ScatteredFiles/Audio_Japanese_pkg_version)
· [Global 5.5 Japanese package index](https://autopatchhk.yuanshen.com/client_app/download/pc_zip/20250314110016_HcIQuDGRmsbByeAE/ScatteredFiles/Audio_Japanese_pkg_version)

The 3.8 indexes independently confirm 8,782 IDs missing from 7.2, including
7,206 event IDs. All also occur in 4.8. These are package-index matches for
the 7.2 metadata corpus. Lines removed from that metadata, historical script
changes, unnamed WEMs, movie cues, and regional 7.2 hotfixes require separate
evidence. A package hit establishes a source candidate for each dub. Historical
download, revision selection and per-take playback are still outside the
installed-pack adapter.

The installation-free reader keeps a regional record of verified performances
from each prepared release. When a later package drops a recording, the reader
can use the earlier publisher package if the current line ID, original path,
player variant and displayed study-language text still agree. Ambiguous current
package IDs are excluded. November 13 checks replayed the mainland 7.1 and 7.2
English builds in succession. All previously matched surviving lines already
had current recordings. A separate Global test prepared the 4.8 binding for
event Dialog `400810204` and recovered it under 7.2, where the recording is
absent. Normal playback exported 5.664 seconds from the publisher’s older file.
Fresh installations also import verified Windows 4.8 and 5.5 releases for the
chosen edition and dub. Global and mainland share all 1,193 narrative file entries
in 4.8, all 1,498 in 5.5, and the three revision values in each release.
Setup checks each immutable regional release
descriptor and reads only the selected audio pack directories. The archive is
limited to original Talk and voice metadata for lines still identifiable in
the current edition. GitLab provides the historical metadata. When unavailable,
Setup can fetch the same Git objects from GitHub with an existing Git installation.
Current-release preparation remains available if both archival routes fail.
On the Global 7.2 English build, 4.8 recovered 16,303 recordings and 5.5
supplied another 4,017. This raised the playable total from 160,654 to 180,974
among 464,300 indexed records. Global 5.5 Dialog `401730201` exported to a
9.120-second English clip through normal playback. The 4.8-only comparison
also recovered 16,285 Japanese lines, 16,290 Korean lines, 16,292 Mandarin
lines with simplified subtitles and 16,289 with traditional subtitles. For the
same event line the four Global 4.8 sources decoded to 5.619 seconds in English,
5.289 in Mandarin, 6.497 in Japanese and 4.521 in Korean.
[4.8 dialogue](https://github.com/DimbreathBot/AnimeGameData/blob/411376ae92931a04d41ae5a9386d45c0d2deb8a8/BinOutput/Talk/Quest/4008102.json)
· [4.8 original voice binding](https://github.com/DimbreathBot/AnimeGameData/blob/411376ae92931a04d41ae5a9386d45c0d2deb8a8/BinOutput/Voice/Items/3238191112.json)

## Verification

### Original TextMap source checkpoint — November 17, 2026

The explicit `original_text=True` publisher/preparation API now connects official
hotfix package acquisition, a complete design catalog, named original data
objects and the existing original TextMap decoder. It authenticates complete
publisher package sizes/MD5 values and the launcher-owned executable as data.
Bounded unwind-range template discovery found two equivalent compiled readers
and one numeric contract in the current original executable. Every matching
method hash is retained; this is format discovery, not semantic method ownership.
No native game code executes.

The container helper compiles only an exact frozen MIT `BlbUtils` implementation
and an owned adapter. The original upstream `CryptoHelper` is excluded from Git
and the helper executable. An allowlisted immutable community description supplies
bounded numerical arrays as private input data. A failed original-container read
can request one controlled description refresh. Installed bundles resolve a closed
helper apphost and its included .NET runtime; only source checkouts use a build
SDK. The helper contract retains full upstream and runtime notices. UnityPy and
Unity texture/mesh loading are not dependencies of this route.
The original provider now derives BLB parameters directly from the authenticated
official executable. A bounded, seed-free native reference/consumer pass yields
complete candidates; strict original catalog parsing must select exactly one.
All matching method hashes remain in its private provenance. No community-key
refresh or fallback runs on this path. Dispatch bootstrap and dialogue bindings
remain separate community dependencies, with last-resort eligibility unproven.
Immutable provenance alone does not establish official autonomy.

The seed-free current replay recovered four candidate contracts and rejected
three against the original catalog. With community numeric-data reads and
network denied, the accepted contract redecoded all 495 packages, then parsed
all 15,360 original shards and 12,779,262 rows across fifteen locales. This is
current retained-input evidence, not an old-to-new executable trial. Ordinary
preparation validates all selected source/target locale shards; the all-locale
format proof does not authorize hidden downloads of unselected locales.

The actual current replay parsed all 15 official locale inventories: 15,360
shards, 495 whole-verified publisher packages and 12,779,262 rows. Network was
disabled and comparisons with retained original outputs happened after parsing.
A separate ordinary acquisition-API replay read all 1,024 English shards and
854,601 rows from the cached original generation, including automatic native
template recovery, with no new game bytes. Synthetic regressions cover changed
parameters/shard counts, full identity ownership, shortened-name ambiguity,
truncation, missing shards, wrong editions/titles/hotfixes, immutable helper
retries, complete receipts, failed-generation retention and offline reopen.

This remains an explicit source route: **the normal provider is unchanged**.
Whole ordinary dialogue/voice preparation, old-to-new original content/audio
acceptance and packaged-runtime collection/native acceptance are still required
before activation. The generation receipt expressly distinguishes original
TextMap content from the existing community Readable/Subtitle text routes; those
two routes must obtain original publisher bytes before all text can be called
publisher-sourced. Existing verified snapshots keep their original provenance.
An unknown compiled reader shape needs a controlled compatible parameter
description or supported decoder; a normal compiler/key change is not silently
treated as a new package format. Two missing original voice identities and
conditional/direct-Global dialogue qualifications remain explicit.

The pinned generic source and full MIT license are recorded in
[the input policy](../../packaging/genshin-reader/inputs.json). The public code
and synthetic fixtures contain no original codec arrays, game bytes or dialogue.
The [direct Android data runtime audit](genshin-android-data-runtime.md) records
the tested complete PC worker, reusable contracts, remaining platform work and
the explicit official-manifest preflight size bounds.

Synthetic regressions cover schema drift, global fallback precedence, conflicts,
parallel card arrays, reminder hash collisions, player variants, missing versus
explicitly silent voices, version mismatch, typed modalities, paragraph alignment
and hostile text archives. See
[the dedicated tests](../../backend/tests/test_genshin_audit.py).

The local pinned-metadata probe completed in 30.94 seconds and retained 441,130
records: 146,834 with installed English audio, 43,431 unavailable, 245,679 unknown
and 5,186 verified text-only book paragraphs. The 8,071 readable paragraphs
include conservative unknown rows. These totals are not counts of
capture-eligible lines. Three bounded sample reads returned valid RIFF payloads
without exporting media. Private aggregate evidence and timings are retained
under ignored `output/checks/audit-genshin/`. The final targeted run passed 36
tests with 10 unrelated Endfield cases deselected.

GitLab REST/raw requests returned HTTP 429 during this audit. The schema and
binding probe used a local Git snapshot at the same immutable revision. It did
not prove production HTTP download availability. There was no live quest replay,
OCR/DPI run, movie decryption, non-English installed pack or controller/mobile
capture acceptance test in this game-specific audit.

## Primary references

- [HoYoverse developer discussion: dialogue playback, choices and Travel Log](https://genshin.hoyoverse.com/en/news/detail/7170).
- [HoYoverse 1.1 details: Books and Archive presentation](https://genshin.hoyoverse.com/en/news/detail/103763).
- [HoYoverse 1.4 notice: Hangout Events and event quests](https://genshin.hoyoverse.com/en/news/detail/9254).
- [HoYoverse published cutscene animation](https://genshin.hoyoverse.com/en/news/detail/165844).
- [Upstream reader implementation](https://github.com/simon300000/genshin-voice/blob/master/update.ts), inspected for authored joins and Medium text-map behavior; reader code is evidence of that implementation, not publisher documentation.
- [Upstream Talk reader](https://github.com/mrzjy/GenshinDialog/blob/main/extract_talks.py), inspected for NPC/gadget/event/hangout Talk handling.
- [Versioned metadata reference](https://gitlab.com/Dimbreath/animegamedata2/-/tree/792978e5503ecfba73dcb3562ed44a0d35a2abe2).
