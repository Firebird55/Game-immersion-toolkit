# Shadow of the Tomb Raider narrative audit

Audited 2026-10-27 against a read-only Windows Steam installation with
`SOTTR.exe`, 89 TAFS version-5 archive families, official patch priorities
through `update3`, thirteen installed localization tables and the English voice
pack. The effective archive directory contains 69,829 entries. Other dubbed
voice packs and Japanese localization are absent. No entitlement or launcher
account was queried or modified.

Game text, extracted sounds, full indexes, source research and private paths
remain in ignored `output/checks/`. No game asset is bundled or published.

## Narrative presentations

| Presentation | Native evidence and reader behavior | Remaining limit |
| --- | --- | --- |
| Normal conversations, side missions and gameplay dialogue | Original WEM `LIST/adtl/labl` metadata names the exact localization key. Authored numeric scene keys classify 17,534 verified voices as dialogue. | Naming-based categories are useful inventory labels, not a complete scene graph or proof of every mission path. |
| Cinematics and in-engine scenes | 1,611 verified voices have cinematic keys. Scene WEMs also contain `subtitle-start`/`subtitle-end` labels with sample positions. | A unique isolated line WEM takes precedence over its alternate scene mix. Cue-only playback requires a unique complete pair; the scene mix can include other original sounds. |
| Ambient NPC chatter, combat barks and traversal | 6,998 verified voices have ambient/systemic key forms. The exact binding is still required regardless of category. | Unlabeled/nonverbal audio is not reconstructed as dialogue. Actor names alone do not prove a recording's spoken language. |
| Narrated documents, murals and relics | 82 verified voices match collectible key forms. Collectible labels with a different descriptive prefix can join through an identical unique authored GUID. | Titles, short descriptions and narration may be separate authored entries. The reader does not infer paragraph timing or combine them by matching words. Other verified voices can remain unclassified. |
| Seven DLC narrative groups | Installed voiced keys identify all seven DLC groups; `.nfo` package priorities and exact archive identities resolve patched resources. | Presence of shared DLC resources does not establish ownership, accessibility, or completion of every DLC. |
| Immersion mode and native-language background speech | The official installation includes a distinct neutral archive mask; these records are inventoried by the archive reader. | Neutral/indigenous recordings are not relabeled as the selected dub. Immersion-mode capture and language attribution remain unverified. |
| Interaction choices, readable UI and other localization | Text is retained for exact translation lookup. Entries with no verified voice or authored silence remain unknown or unavailable. | No proven silent narrative schema was found. This adapter emits zero `unvoiced` rows, so the optional silent-capture setting cannot turn missing audio into silent dialogue. |

The [official product page](https://www.tombraider.com/products/games/shadow-of-the-tomb-raider)
describes the Definitive Edition's seven DLC challenge tombs. The developer's
[immersion-mode interview](https://www.gamespot.com/articles/e3-2018-shadow-of-the-tomb-raiders-immersion-mode-/1100-6459817/)
explains native-language NPC conversations; this does not establish that a
neutral recording belongs to any chosen study locale.

## Format and identity review

The bounded Python implementation was checked against the format author's
[TAFS archive reader](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/Shadow/ShadowArchive.cs),
[localization reader](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/Shadow/ShadowLocalsBin.cs)
and [Wwise chunk structures](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/WwiseSound.cs)
at commit `a79c48b75f1ffaaf623dc73a625211bf98ff0504`. The research checkout
was inspected as source; no mod loader, hook or game-writing tool was run.
No external filename dictionary or published subtitle database is needed.

The localization resource uses 64-bit offsets into UTF-8 key/value strings.
Language IDs and archive locale masks must agree. WEM metadata is parsed within
a one-MiB bound before its audio chunk. Full voice reads are capped at 128 MiB.
Malformed pointers, counts, sizes, encodings, chunk boundaries and unsupported
cue representations fail with an update/verify action. Prefix inspection is
ordered by physical archive position. Both raw and bounded CDRM archive reads
are supplied by the shared TIGER reader.

Each subtitle must resolve to a unique isolated recording, or to a unique
complete movie cue pair if no isolated recording exists. The audited pack has
1,080 isolated-recording/scene-mix alternatives and 170 unresolved ambiguous
subtitle bindings. A GUID join is allowed only when one localization key owns
that GUID; no prefix similarity or transcript text is used to select audio.
Extraction reopens the current effective archive entry and revalidates its
label, locale and timing. Archive and `.nfo` changes invalidate the fingerprint;
changes during preparation preserve the previous completed snapshot.

The [language matrix](../shadow-tomb-raider-languages.md) includes all thirteen
official audio pack identities, including regional Japanese and Latin American
Spanish. Synthetic format support is distinguished from native playback, and
the two Chinese script packs keep independent identities.

## Verification

The native English index produced 38,233 nonempty rows: 27,064 verified original
voice bindings, 616 unavailable rows, 10,553 unknown rows and zero confirmed
silent rows. It inspected 29,872 English WEM files; 1,517 lacked a unique subtitle
binding and 882 labels had no matching selected localization. There were 783
unique GUID binding candidates. Counts describe this installed build, not every
line accessible in gameplay. Indexing took 10.09 seconds on the audit host.

All thirteen installed text tables parsed with their expected language IDs:
English, French, German, Italian, both Spanish variants, Brazilian Portuguese,
Polish, Russian, Korean, both Chinese scripts and Arabic. Japanese was absent.
Separate Arabic, Simplified Chinese and Traditional Chinese preparations
retained 37,589, 37,624 and 37,611 nonempty text rows respectively, with zero
voice bindings and explicit missing-pack messages; none borrowed English.

Five English examples decoded through the existing pinned vgmstream tool to
nonzero PCM: ordinary dialogue, ambient speech, an isolated cinematic line,
a narrated collectible and a cinematic scene track. Four used 48 kHz and the
collectible used 16 kHz. The cinematic track's authored 2,966–3,700 ms cue was
within the decoded duration and produced a nonempty MP3 with the existing
FFmpeg trim path. These are format/decode checks, not listening or complete
gameplay verification.

The toolkit's `LocalVoiceAssetService` also loaded the native snapshot with
27,064 bindings and completed a single dialogue extraction plus a two-item
cinematic/collectible batch, producing three nonempty MP3s through the normal
service path. All thirteen lightweight voice-pack probes completed in 0.062
seconds: English present, the other twelve missing. The probe inspected bounded
headers and declared parts, without rebuilding the dialogue index.

Twenty-seven dedicated synthetic tests passed in 0.96 seconds. Private evidence
is in ignored `output/checks/shadow-native/native-evidence.json` and its adjacent
index/audio files, with the service/probe results in `integration-evidence.json`.
No physical game capture, live OCR calibration, alternate
installed dubs, immersion-mode playback, every quest branch, or per-line
translation completeness has been established by these probes.
