# Cyberpunk 2077 installed-data audit

Reviewed on 2026-10-27 with the pinned WolvenKit Console 9.0.1 reader. This audit
read the installed base game and Phantom Liberty without launching the game or
writing to game files, user history or accounts. Extracted resources and audio
remain under ignored `output/checks/cyberpunk-audit/`.

## Installed inventory and coverage

Both content groups contain 19 official text archives and English/Mandarin voice
archives. The inspected English text archives contain 3,087 base and 717 expansion
JSON resources. The selected game-data archives contain 7,067 base and 513
expansion scene resources, one base journal, and two expansion-archive journals
(one is a base-journal overlay). The base video archive contains 497 Bink videos;
the expansion game-data archive contains another 83. These are resource counts,
not counts of completed quests or verified gameplay presentations.

| Content | Authored installed evidence | Reader behavior and remaining limit |
| --- | --- | --- |
| Main, side and minor quests; NPC conversations | Subtitle resources under `quest`, expansion `overlays_quest`, and `q`, `sq`, `mq` resource groups | Exact localization IDs join subtitle and voice maps; main/side/NPC execution and branch completeness are not inferred from filenames. |
| Ambient conversations, vendors and combat barks | `open_world` scenes, vendors, voicesets, street stories, fixers and activity groups; expansion overlay groups | Included as ambient dialogue. A voiceset directory does not establish which lines actually fire during combat. |
| Cutscenes, intro, broadcasts, loading screens and final boards | Subtitle `media` groups and Bink resources | Media subtitles with exact voice maps work. No standalone Bink audio segmentation or guessed cutscene timing is added. |
| Spoken phone/holocall dialogue | Quest/open-world subtitle tables and ordinary, holocall and helmet VO maps | Existing exact ordinary voice binding is preserved; processed variants do not replace the clean performance. |
| Text messages and phone replies | `gameJournalPhoneMessage.text` and `gameJournalPhoneChoiceEntry.text` | Newly indexed as verified text-only messages and response labels. |
| Conversation response options | Scene `screenplayStore.options`, `locstringId.ruid` and embedded `locStore` descriptors/payloads | Still unsupported. An inspected expansion scene has eight options and 26 localized descriptors across three locale identifiers, with valid payload indexes. Phone replies use the separate supported journal format. |
| Shards and other readable bodies | `gameJournalOnscreen.description`, `gameJournalFile.content` | Newly indexed as readable text, without assuming every onscreen journal entry is a shard. Video-bearing file entries are excluded. |
| Computer/email bodies | `gameJournalEmail.content` | Newly indexed as text-only email bodies; video-bearing entries are excluded. |
| Comic/image text | No distinct comic dialogue class was established by the inspected localization/journal/scene samples | Image-only text and any comic panels remain an explicit coverage gap. |
| Quest objectives, journal summaries, web pages, menus | Separate journal/UI classes and general onscreen localization | Deliberately excluded from reading capture; arbitrary interface strings are not promoted to dialogue. |
| Phantom Liberty | Separate language archives, journal and scene resources, including base-content overlays | Native extraction verified. Localization/voice ownership stays scoped; resources are never borrowed across groups. |

Journal `LocalizationString.value` entries in this installation mostly use
`LocKey#<decimal>`, which resolves exactly to an onscreen `primaryKey`. Explicit
textual references use `secondaryKey`. The reader selects the authored journal
class and body field before joining; it does not classify arbitrary translations
by keywords. A base journal stored inside the expansion archive still uses the
base localization namespace. Full reading bodies are preserved; this audit does
not establish OCR matching for cropped or scrolled excerpts.

## Reader changes and voice evidence

Language reader revision 3 includes journal metadata in its fingerprint and uses
a separate extraction cache from legacy subtitle-only preparation. Unsupported
localization/journal shapes return the actionable `unsupported_game_format`
failure. Coverage warnings expose omitted categories and unresolved references.
The older bilingual index still reads subtitles only and says so in its warnings.

Bound voice resources are `voiced`; an authored nonzero resource reference that
cannot be interpreted as an original WEM is `unavailable`. Absent or zero voice
references remain `unknown`. Only the explicitly selected text-only journal
modalities become `unvoiced`. Capture of these entries uses the common opt-in,
exact-match behavior. No silence is inferred from a missing voice pack.

The installed English voice maps reference 126 resources missing from the pinned
tool's path-name dictionary. All 126 exist under the exact REDengine FNV-1a
resource key. Single extraction now retries that key; batch extraction includes
its exact numeric filename. Numeric `.bin` output must contain a RIFF/RIFX WAVE
header before it reaches the normal voice decoder. Archive/locale/path checks
still apply. This recovers the authored resource without substituting audio.

## Verification

Native English preparation with requested Simplified Chinese translation produced:

| Result | Records |
| --- | ---: |
| Total | 122,966 |
| Verified original voice bindings | 98,698 |
| Verified text-only journal entries | 6,917 |
| Subtitle variants with unknown voice status | 17,351 |
| Expansion-scoped records | 31,947 |
| Records with the requested Chinese translation | 122,895 |

The text-only subset contains 2,961 phone messages, 1,150 phone replies, 729 email
bodies and 2,077 readable bodies. There are 999 distinct authored journal
references without matching installed English text; the public preparation
warning reports this count. Missing translations remain absent. Counts include
authored variants and do not assert unique conversations or currently reachable
content. Every indexed English voice reference was checked against its selected
installed archive by exact path or exact resource hash; none was unresolved.

Fresh native extraction took 136.80 seconds; a rebuild using the extraction cache
took 13.33 seconds. Production single and batch voice-service checks each decoded
a dictionary-missing resource through extraction, vgmstream and FFmpeg to a
45,044-byte MP3. This proves decoding, not live playback during gameplay.

The 50 targeted Cyberpunk/capture/patch-refresh tests passed in 7.30 seconds.
New synthetic regressions protect journal type/key selection, menu and video
exclusion, content/locale ownership, large numeric IDs, unknown versus unavailable
voice evidence, schema failures, journal fingerprint invalidation and exact-hash
single/batch extraction. Fixtures contain invented text and audio. Native OCR,
Windows DPI/capture bounds, gameplay branches and physical mobile behavior are
not established by this data audit. Full publication checks belong to the parent
change and release CI.

## Primary format references

- [WolvenKit onscreen entry schema](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Types/Classes/localizationPersistenceOnScreenEntry.cs) documents primary/secondary localization keys and gender variants.
- [WolvenKit phone-message schema](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Types/Classes/gameJournalPhoneMessage.cs), [file schema](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Types/Classes/gameJournalFile.cs) and [email schema](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Types/Classes/gameJournalEmail.cs) identify the selected body fields and optional video references.
- [Message-authoring documentation](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/quest/how-to-add-new-text-messages-thread-to-cyberpunk-2077) describes journal-to-onscreen localization joins. Installed cooked `LocKey#` references were verified directly rather than assuming mod-authoring examples used the same representation.
- [WolvenKit embedded scene localization schema](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Types/Classes/scnlocLocStoreEmbedded.cs) separates scene response labels from external subtitle tables.
- [WolvenKit resource-path implementation](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Types/Primitives/Simples/ResourcePath.cs) and [FNV-1a implementation](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.Core/FNV1A/FNV1A64HashAlgorithm.cs) establish exact numeric resource keys and path normalization.
