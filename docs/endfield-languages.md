# Arknights: Endfield language preparation

Choose **English, Simplified Chinese, Traditional Chinese, Japanese or Korean**
in **Setup → Languages**. Both Chinese scripts use original Mandarin audio.
Pair any study language with any of the game's **14 official text locales**
(70 study/translation combinations). The
[language matrix](languages/en.md#endfield) lists every supported combination.

**A game installation is optional.** Without a game folder, choose **Setup →
Games → Arknights: Endfield → Install game tools**, then prepare your study and
translation languages in **Languages**. The Windows companion indexes the
verified Global 1.6.4 text snapshot and downloads original recordings directly
from GRYPHLINE on demand. The first download needs internet access. A cached
film recording can be used offline for its other captions in the same dub.
The verified film captions cover 388 Mandarin intervals, 388 English, 399 Japanese
and 314 Korean. Both Chinese study selections use the same 388 Mandarin intervals.

For dialogue with separate Endministrator performances, set the player voice to
match your game. The reader selects the corresponding recording and renders
gender-specific translations when the game supplies them. Scene summaries shown
when skipping dialogue use the existing unvoiced-text capture option. The
[publisher-source audit](game-audits/endfield.md#publisher-resources-and-story-coverage-november-8-2026)
records the 1,179 paired lines, remaining voice gaps and cinematic coverage.

## Voice language support and verification

The publisher's current [Steam language table](https://store.steampowered.com/app/4732690/Arknights_Endfield/)
lists **English, Mandarin Chinese, Japanese and Korean** full audio, alongside
14 subtitle languages. The [official Gryphline language announcement](https://endfield.gryphline.com/en-us/news/0767)
also identifies those four voice languages. Traditional Chinese is an additional
subtitle choice that uses Mandarin recordings; it is not a fifth voice pack.

All four voice formats are implemented and selectable regardless of which packs
are installed. The same exact source-path/hash binding and VFS reader handle
each namespace; initial and hotfix packages are included for every selection.

| Study selection | Voice package / VFS group | Installation-free playback | Installed game playback at the earlier audit |
| --- | --- | --- | --- |
| English (`en`) | `english` / AudioEnglish | Global conversation and timed film MP3 verified | English pack absent |
| Simplified Chinese (`zh-Hans`) | `chinese` / AudioChinese | Global conversation and timed film MP3 verified | Conversation and combat bark decoded |
| Traditional Chinese (`zh-Hant`) | `chinese` / AudioChinese | Both MP3s verified with Traditional Chinese text and Mandarin voice | Shares Mandarin recordings |
| Japanese (`ja`) | `japanese` / AudioJapanese | Global conversation and timed film MP3 verified | Japanese pack absent |
| Korean (`ko`) | `korean` / AudioKorean | Global conversation and timed film MP3 verified | Korean pack absent |

All four publisher dubs were decoded using the desktop playback service. The
installed reader reports missing packs separately. See the
[Endfield audit](game-audits/endfield.md) for presentation gaps and revision scope.

## Setup

To use installed packages, select the client folder containing **Endfield.exe and
Endfield_Data/StreamingAssets/VFS** in **Setup → Games** and install the chosen
voice through the game's language settings. The toolkit reads the folder without modifying it.
Prepare only the study language and translation you want. Missing official text
or audio stays unavailable; another language is never silently substituted.

The archive reader is built into the toolkit and needs no SDK, compiler or
separate .NET installation. **Install game tools** acquires exact, checksum-checked
numerical format metadata into the private tool cache. Those documents are read
as data, never compiled or executed. Large voice packages are read by selected
byte range. See [archive runtime evidence](endfield-runtime.md) for source
identities and the separate codec/frozen-platform acceptance still required.

## Dialogue and original voice

The reader follows **DialogTextTable and RadioTable text ID → audioOverride → AudioDialog source path**, plus authored TextTable/TextVoIdTable narration, operator profile voices and exact AIBarkText voice-ID joins, from the
[third-party game-data mirror](https://github.com/rmxlinux/EndfieldData). One immutable catalog revision supplies the selected
subtitle and translation tables. Only an exact authored source hash can bind an
installed original voice. Conflicting sources are skipped.

Verified text-only choices, story panels, messages and readables can be prepared
without audio. Missing recordings and missing metadata are never relabeled
silent. Preparation reports unresolved metadata separately from known source
paths absent from the chosen locale; reinstalling a voice pack cannot repair a
missing metadata reference.

Endfield resolves the complete authored source path and its locale-specific Wwise external hash. StreamingAssets and Persistent layers are combined with patch precedence. Only the selected voice group, initial audio and hotfix group are read; unrelated music and effects are excluded.

Use **Capture setup → Endministrator voice** for ambiguous player performances.
The bottom dialogue crop has separate per-PC calibration for this game. Check
it against your subtitle size, resolution and display scaling. YouTube evidence
and reproducible replay instructions are in
[game OCR presentations](game-ocr-presentations.md#starrail-genshin-endfield).

## Updates, reading and mobile

After the official launcher finishes a patch or voice download, choose
**Refresh game data**. Automatic checks revisit prepared locales about every
two minutes. A failed build leaves the previous complete table available.
Installation-free preparation uses the audited Global resource revision
`11529267-11`. Support for a later publisher revision requires new validated
package indexes, text and film clocks.

History, favorites, original playback, explicit game-deck export, Lexirise
reading and independent Migaku mode use the existing language-aware workflow.
Export a private mobile library for independent phone/tablet OCR, or pair the
phone with the running Windows companion. Catalogs and voices remain private.

Game files, recordings, extracted catalogs, compiled readers and audio caches
are never committed or included in the public mobile preview. No account writes
are needed to prepare a language or run the capture checks.
