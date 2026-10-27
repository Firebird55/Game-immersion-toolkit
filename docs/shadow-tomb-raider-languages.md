# Shadow of the Tomb Raider language preparation

The Windows reader supports these official study/audio pack identities:

| Locale | Official pack token | Native evidence on the audited installation |
| --- | --- | --- |
| English (`en`) | `english` | Text, exact voice bindings and playback verified |
| French (`fr`) | `french` | Text verified; voice pack absent |
| German (`de`) | `german` | Text verified; voice pack absent |
| Italian (`it`) | `italian` | Text verified; voice pack absent |
| Spanish, Latin America (`es-419`) | `latamspanish` | Text verified; voice pack absent |
| Spanish, Spain (`es-ES`) | `iberspanish` | Text verified; voice pack absent |
| Japanese (`ja`) | `japanese` | Official manifest/format identity; pack absent |
| Portuguese, Brazil (`pt-BR`) | `portuguese` | Text verified; voice pack absent |
| Polish (`pl`) | `polish` | Text verified; voice pack absent |
| Russian (`ru`) | `russian` | Text verified; voice pack absent |
| Traditional Chinese (`zh-Hant`) | `chinese` | Text verified; voice pack absent |
| Simplified Chinese (`zh-Hans`) | `simplechinese` | Text verified; voice pack absent |
| Arabic (`ar`) | `arabic` | Text verified; voice pack absent |

Korean (`ko`, `korean`) is an official translation locale, not a voiced study
locale. The global [Steam language matrix](https://store.steampowered.com/app/750920?curator_clanid=38172546)
lists eleven full-audio language rows plus Korean text. The installed official
`game.specmasks.toc` additionally identifies Japanese and Latin American Spanish
voice/text archives. Their identifiers agree with the reviewed
[language format implementation](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/Shadow/ShadowGameInfo.cs).
These regional identities remain supported even when a storefront's global
language table omits them. Availability can depend on edition, region and
launcher selection; the reader does not download game content or change that
selection. Native playback outside English remains unverified.

Select the desired official launcher language and finish its download before
preparing it in the toolkit. `SOTTR.exe` and Windows TAFS version-5 `.tiger`
archives identify this installation. The reader is implemented in Python and
needs no external archive extractor. Original Wwise audio uses the toolkit's
existing pinned vgmstream decoder. Linux/macOS and other archive versions are
not covered by this Windows reader.

Each source uses its exact text and voice locale masks. Traditional and
Simplified Chinese have separate official archive identities; the reader does
not substitute one for the other or claim their recordings are identical.
Only requested installed translation tables are loaded, and translations join
by the authored localization key. Missing text packs produce an actionable
preparation error; missing voice packs retain text with unavailable/unknown
voice states and a download message. English is never borrowed as another dub.

Voice matching uses the original WEM label and localization key, or a unique
authored GUID shared by a collectible recording and its localized text. A
unique isolated line recording takes precedence over an alternate timed scene
mix with the same key. Multiple isolated performances remain unavailable.
Movie clips require both authored subtitle start and end cues; no timing is
estimated from text length. Immersion-mode neutral recordings have no selected
dub identity and are not substituted into a study-language pack.

Synthetic tests cover all thirteen audio pack identities, regional and Chinese
pack separation, missing packs, exact translations, malformed tables, cinematic
cues, duplicate performances, collectible GUID collisions, extraction reference
validation and patch changes. The [native audit](game-audits/shadow-tomb-raider.md)
records the installed evidence and remaining gameplay/capture limits.
