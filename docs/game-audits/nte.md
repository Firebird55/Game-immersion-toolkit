# Neverness to Everness audit

## Released file acquisition across regions · November 9, 2026

The source command now follows each regional branch, decodes the updater resource list and checks its plaintext MD5 against the active launcher. It records independent files and the exact byte ranges of files stored inside aggregate packages. Global PC_140 1.4.11 listed 552 files and mainland PC_150 1.5.4 listed 366. Both included 77 PAK files. The updater format references are pinned by commit and SHA-256. The Global and mainland distributions use different public updater parameters. [Global launcher](https://ntecdn1.perfectworld.com/clientRes/publish_PC/Version/Windows/config.xml) · [Mainland launcher](https://yhcdn1.wmupd.com/clientRes/publish_PC/Version/Windows/config.xml) · [Global patcher integration](https://github.com/Tobiichi-Origuchi/nte_patcher/blob/1135247b3a21ac72304b8bd9f5aa548994f7a8ef/tests/test_integration.rs) · [Mainland downloader reference](https://github.com/kuaichu/game-cdn-archive/blob/58fb1715ce2f891e9873741c66700817d9552cda/scripts/nte_downloader.py)

Two empty-cache checks retrieved the same game path from different regional package objects. The Global member was 22,423 bytes, the mainland member 23,485 bytes. Each matched its own publisher checksum. The regional source command can save a selected file without installing or downloading a full game. The archive contents still require compatible game archive metadata and verified localization and Wwise bindings before normal Setup can play a sentence. [Source command](../../scripts/live_game_sources.py)

```text
python scripts/live_game_sources.py nte-global --cache private-cache --output nte.json --resource Client/WindowsNoEditor/HT/Content/PatchPaks/pakchunk2-Windows_0_P.pak --save selected.pak
```

## November 8, 2026 · Localized performances and sequence timing

The cooked Global dialogue and bubble sound tables contain explicit aliases
for text keys whose recording has a different name. The installed census
found 21,248 dialogue/bubble keys. Of these, 2,028 had eligible unambiguous
aliases. A native English probe found the indicated localized Wwise media
for 1,458 rows. The reader now looks up these declarations before using
the conventional event name. Conflicting declarations or ambiguous
localization namespaces keep the original voice unresolved.
[Pinned Unreal type schema](https://github.com/555me/NTE-usmap/blob/1b92d5267092dac6bcfec605bcaf6ae05b664746/mapping/HT-1.4-1413.usmap)

The reviewed movie catalog contains 218 definitions. Its explicit voice,
subtitle and StringTable fields yield 42 distinct movie paths across four
tables. In addition to 23 Sequence definitions, the reader recognizes 10
Wuchao, seven Blackbird and two Legend definitions. The installed subtitle
key, localized event bank and media must still resolve for an individual
caption to acquire audio. [Movie tables](https://github.com/Waifus-Grace/NTE_Assets/tree/cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7/DataTable/Skill)

Story sequences use a separate chain from the sequence's caption group to
the Unreal StringTable, dedicated voice event and locale-specific start and
end times. The pinned schema decoded all 177 nested sequence entries in the
inspected main scene table. The reader checks the playback rate, start offset,
unique event, localized media and overlap with surrounding cues. Synthetic
fixtures cover dub-specific clocks, repeated captions and ambiguous audio.
The final end-to-end count of playable sequences on Global remains unverified.
On a fresh workstation, the pinned type schema downloaded successfully, but
the existing archive metadata provider no longer supplied a usable entry.
The type schema and the archive metadata are separate prerequisites. [Global release resources](https://ntecdn1.perfectworld.com/clientRes/PC_140/Version/Windows/version/1.4.11/ResList.bin.zip)

Reviewed on 2026-10-27 against the locally installed client, using discovery from
`backend.game_paths`. This is an asset/adapter audit, not a complete playthrough
or evidence that every visible layout works in OCR. Game files, extracted text,
audio, credentials and machine paths remain in private ignored storage.

2026-10-30 runtime update: [compiler-free desktop dispatch](../nte-runtime.md)
now resolves the self-contained bridge and exact separately inventoried native
dependencies. This changes installation/runtime mechanics, not language or
presentation coverage. Supplier redistribution and full frozen-image acceptance
remain explicit remaining work.

## Installed evidence

The installation contains 20 PAK files, 22 UTOC/UCAS pairs and 178 HPW hotpatch
files. Fresh native extraction enumerated 805,652 unique virtual paths, including
113,044 localization rows in each of English and Simplified Chinese. Both
localization resources have locres version 3. The initial key-selected extraction
read 18,828 Mandarin event banks, all with Wwise version 154. There are 26,905
Mandarin event banks overall; event availability is not proof of a matching
visible subtitle. Four voice-language media inventories are present.

The updated adapter, with the locally reviewed movie catalog revision
`1816e237ffe9edf687dd6942d028e89cce121381`, produced 113,218 Mandarin-source records:
16,416 with verified voice bindings, 1,861 verified written records, 4,126 authored
voice references whose playback is unavailable, and 90,815 unknown records.
The total includes localization/UI strings and authored player-voice variants;
it is not a dialogue count or a completion percentage. The catalog supplied
23 movie bindings; the installation contains 41 story SRT files.

## Presentation inventory

| Presentation | Installed evidence | Adapter behavior and remaining gaps |
| --- | --- | --- |
| Main, side, legend and bond conversations | Main/side/legend dialogue string tables; dialogue sound tables; localized Play_Vo events | Exact namespace/key text plus a uniquely resolved event/media pair supplies original audio. New or ambiguous mappings remain unknown/unavailable. Some new quest table families remain uncategorized. |
| Ambient NPC, street and world bubbles | `ST_AmbianceDialogue`, `ST_Bubble_*`, `ST_StoryBubble`, bubble voice tables | Classified as ambient dialogue. A visible bubble does not establish silence; only resolved events supply audio. Timing and overlapping bubbles need gameplay captures. |
| Combat barks and shouts | Character, shouts, skill and attack event families; 2,772 Mandarin bank names contain `Vo_Char` | Audio-only events do not establish a subtitle identity. General combat bark/subtitle coverage is incomplete; no guessed text or voice link is created. |
| Realtime cutscenes | `ST_Sequence`, `ST_Sequence_Legend`, story/world sequence tables | Directly keyed voice events work. Dynamic sequence tracks without a reviewed binding remain unknown/unavailable. |
| Prerendered movies | Story SRT keys, FFMpeg movie catalog, CG events, loose movies and packaged media | Reviewed namespace, cue interval and deterministic voice variant are required. All 41 SRT files are inventoried; 23 catalog bindings are not complete movie coverage. Packaged USM or embedded captions have no general new mapping in this audit. |
| Comics and illustrated scenes | 106 unique comic-named assets, including textures and quest blueprints | Existence is verified; panel text ownership and per-panel original voices are not. No generic comic capture claim. |
| Bagel posts and replies | `ST_Bagel_TitleContent`, `ST_Bagel_Reply`, Bagel post/chat/comment tables | 1,536 nonempty written records are unvoiced and eligible only for opt-in exact capture. Server/user-generated posts are outside the installed authored corpus. An authored voice event always overrides the text-only inference. |
| Phone/bond chats | `ST_Likeability`, chat-group/chat-item tables and phone interactions | 7,877 bond-table records remain unknown in this installation. The mixed table needs row-level ownership before distinguishing text messages, voiced calls and choices. |
| Mail | Scheduled/model/birthday mail tables and `ST_PlayerBirthdayMail` | 45 nonempty birthday-mail body records are proven written content. Titles, other mailbox templates and server-delivered mail are not automatically admitted. |
| Response options | 104 ambient rows with authored `option_Player` keys, plus other dialogue branches | Classified response options retain unknown voice status when no event is established. A choice can be spoken after selection; absence of a bank alone never proves silence. |
| Narrative reading and recaps | `ST_DialogueSumUP`, character files, notebook article tables and world descriptions | 280 scene-summary records are written narrative. Character files mix profiles and voice lines, so missing-audio entries remain unknown. Notebook/other reading ownership and layout coverage remain incomplete. |

## Changes and update behavior

The native reader now records authored event presence across available dubs and
event assets. A missing selected voice pack therefore yields `unavailable` when
the authored event exists, not `unvoiced`. It also exposes a complete virtual-file
inventory for private audits and localization header versions. Verified written
content is retained in both legacy bilingual and language-specific preparation.

A fresh installed run found a movie with a two-digit millisecond field. The old
parser silently discarded all 16 cues. The bounded parser now accepts one to three
digits as integer milliseconds, matching
[FFmpeg's SRT demuxer](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/srtdec.c).
All 16 installed cues now have verified voice bindings. Milliseconds are not
rescaled as decimal fractions.

Newer recognized locres headers, unsupported Wwise bank versions and unsupported
reviewed SRT layouts raise `PreparationFailure('unsupported_game_format', ...)`
with recovery guidance. Files changing during preparation raise
`game_files_changed`. Completed caches are published by atomic rename; failed
preparation does not replace the last good index. Unresolved supported-version
event trees remain unavailable and contribute a coverage warning.

The fingerprint now includes every file in installed Content and Config, the
game executable, native reader sources, reader package pin, index version and
movie baseline. It catches added/removed loose localization, configuration,
movies and hotpatches without requiring an audio-bank change. Installed files
use path/size/mtime metadata: an external rewrite that preserves both size and
timestamp is not detected by this fingerprint. No archives were found outside
Content in this installation. Unknown future archive locations or encryption
changes still require a reader update. Language index version is 4.

## Primary-source cross-check

The [publisher's Steam listing](https://store.steampowered.com/app/4508340/NTE_Neverness_to_Everness/)
describes story encounters, side stories, Bagel connections and the independently
listed subtitle/full-audio languages. Its language list is storefront evidence,
not proof that this adapter supports every study locale.

The [developer's version 1.1 notes](https://nte.perfectworld.com/de/article/news/gamebroad/20260602/262480.html)
explicitly add Bagel social features, character messages, story-skip summaries,
dialogue interaction changes and a story voice-mute option. These support the
presentation inventory and the need to separate authored voice status from a
user's current mute setting.

[UEExtractor's upstream documentation](https://github.com/SolicenTEAM/UEExtractor)
identifies NTE's custom archive offsets and encrypted localization.
[CUE4Parse's localization reader](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Localization/FTextLocalizationResource.cs)
contains the NTE-specific string-table path and rejects unsupported newer
localization versions. This audit keeps the pinned reader rather than silently
upgrading native dependencies or importing a remote text corpus.

## Verification and remaining acceptance

Focused synthetic regressions cover voice-state precedence, opt-in exact-only
written capture, missing-dub provenance, ambiguous voice keys, typed format
failures, last-good-index preservation, loose-content invalidation and short
millisecond timing. Existing five-locale and cinematic branch regressions remain
enabled. The modified .NET reader built and freshly extracted the installed
English/Chinese resources; the final binding pass completed in 11.2 seconds.
Private summaries and raw evidence are under ignored `output/checks/nte-audit/`.

No live gameplay, account writes, new audio decoding, desktop/mobile screenshot
matrix, zoom/DPI or full chapter traversal was performed for this audit. Those
remain separate acceptance checks. Full preparation and native OCR should be
rechecked after an actual game update, especially new phone, comic, reading and
sequence presentations.
