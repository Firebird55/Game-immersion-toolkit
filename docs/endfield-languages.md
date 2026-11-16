# Arknights: Endfield language preparation

Choose **English, Simplified Chinese, Traditional Chinese, Japanese or Korean**
in **Setup → Languages**. Both Chinese scripts use original Mandarin audio.
Pair any study language with any of the game's **14 official text locales**
(70 study/translation combinations). The
[language matrix](languages/en.md#endfield) lists every supported combination.

**A game installation is optional.** Without a game folder, choose **Setup →
Games → Arknights: Endfield → Install game tools**, then prepare your study and
translation languages in **Languages**. The Windows companion indexes the
selected Global or Mainland China Windows release. It reads the publisher’s original localization,
story and radio tables and retrieves recordings directly from that publisher. Cached
recordings work offline. Ordinary dialogue follows publisher resource updates.
When the publisher updates a release, the toolkit checks each known film's
configuration, localized timeline, voice banks and original recording before
reusing its times. Two different Global 1.6 resource revisions passed this check.
Global 1.6.4 resource `11775769-12` retains 467 English, 483 Japanese, 459 Korean
and 483 Mandarin line clips. It adds 32 English, 12 Japanese, 38 Korean and
18 Mandarin complete-scene context bindings. Both Chinese script selections use
the same Mandarin sources. Context recordings are labeled explicitly and span
14.5–224.5 seconds; they include the complete original performance rather than
an exact sentence cut. Two captions per dub retain unknown audio. The
[current subtitle inventory](game-audits/endfield-current-subtitle-acceptance.md)
records their exact boundaries and remaining acceptance work.

For dialogue with separate Endministrator performances, set the player voice to
match your game. The reader selects the corresponding recording and renders
gender-specific translations when the game supplies them. Scene summaries shown
when skipping dialogue use the existing unvoiced-text capture option. Radio
captions whose original data explicitly disables the performer use that same
option. A missing actor field or recording does not establish silence. The
separate **Include subtitles without available audio** option preserves verified
authored captions with unknown or unavailable audio, subject to complete,
unambiguous text and player selection. General reactions stay separate from
sentence audio. Ambiguous short captions can require a proven preceding caption.
Include the official speaker label in the capture area when it is shown above a
short radio caption. The reader can use the complete name and caption together;
the same sentence from another speaker remains separate. Anonymous labels such
as `???` do not identify a recording or resolve an ambiguous translation.
Written instruction-book bodies, guide-page explanations and referenced
operator-training steps also use the unvoiced-text option. Their text is read
across the full game frame; a bottom subtitle crop is not required. Illustrative
videos, images, headings and short skill labels are separate from these written
bodies. A tutorial video is not offered as the voice of its accompanying text.
The
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
[publisher's original tables](game-audits/endfield.md). The installed-reader fallback also retains the
[third-party game-data mirror](https://github.com/rmxlinux/EndfieldData). One immutable release supplies the selected
subtitle and translation tables. Only an exact authored source hash can bind an
installed original voice. Conflicting sources are skipped.

Verified text-only choices, story panels, messages and readables can be prepared
without audio. Missing recordings and missing metadata are never relabeled
silent. Preparation reports unresolved metadata separately from known source
paths absent from the chosen locale; reinstalling a voice pack cannot repair a
missing metadata reference.

Endfield resolves the complete authored source path and its locale-specific Wwise external hash. StreamingAssets and Persistent layers are combined with patch precedence. Only the selected voice group, initial audio and hotfix group are read; unrelated music and effects are excluded.

Use **Capture setup → Endministrator voice** for ambiguous player performances.
Dialogue and cinematic regions have separate per-PC calibration. Check
subtitle size, resolution and display scaling; include the whole frame where
the caption can move. A bottom-only region does not cover every presentation. YouTube evidence
and reproducible replay instructions are in
[game OCR presentations](game-ocr-presentations.md#starrail-genshin-endfield).

## Updates, reading and mobile

After the official launcher finishes a patch or voice download, choose
**Refresh game data**. Automatic checks revisit prepared locales about every
two minutes. A failed build leaves the previous complete table available.
Installation-free preparation discovers the selected publisher's current
resource indexes and derives text, recording and supported scene bindings from
that release. Reader-20 checks cover original 1.5.3 and live 1.6.4 with unchanged
toolkit code and format metadata, including added text and voices. Separate
recovery checks cover an interrupted official transfer, fresh-process retry
and retained older recordings. A changed
version or chapter alone does not require a new toolkit release. Unsupported
format changes and unresolved audio remain explicit.

History, favorites, original playback, explicit game-deck export, Lexirise
reading and independent Migaku mode use the existing language-aware workflow.
Export a private mobile library for independent phone/tablet OCR, or pair the
phone with the running Windows companion. Catalogs and voices remain private.

Game files, recordings, extracted catalogs, compiled readers and audio caches
are never committed or included in the public mobile preview. No account writes
are needed to prepare a language or run the capture checks.
