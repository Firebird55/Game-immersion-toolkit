# Rise of the Tomb Raider languages

The adapter reads the Windows game's own TIGER archives. It supports the twelve
full-audio languages listed by the [official Steam store](https://store.steampowered.com/app/391220/?CC=nz&l=english),
plus Latin American Spanish and Arabic where the installation contains their
official localized DLC archives. Arabic is **partial DLC support**, not a claim
that the Windows base game provides a complete Arabic dub. Dutch is a translation
target with no supported original Dutch speech pack.

| Locale | Original archive suffix | Native evidence on 2026-10-27 |
| --- | --- | --- |
| `en` | `ENGLISH` | Base game and four DLC families; native recording decoded |
| `fr` | `FRENCH` | Four DLC families; native recording decoded |
| `de` | `GERMAN` | Four DLC families; native recording decoded |
| `it` | `ITALIAN` | Four DLC families; native recording decoded |
| `es-419` | `LATAMSPANISH` | Four DLC families; native recording decoded |
| `es-ES` | `IBERSPANISH` | Four DLC families; native recording decoded |
| `ja` | `JAPANESE` | Four DLC families; native recording decoded |
| `pt-BR` | `PORTUGUESE` | Four DLC families; native recording decoded |
| `pl` | `POLISH` | Four DLC families; native recording decoded |
| `ru` | `RUSSIAN` | Four DLC families; native recording decoded |
| `ko` | `KOREAN` | Four DLC families; native recording decoded |
| `zh-Hant` | `CHINESE` | Four DLC families; distinct original recording decoded |
| `zh-Hans` | `SIMPLECHINESE` | Four DLC families; distinct original recording decoded |
| `ar` | `ARABIC` | Blood Ties and Cold Darkness; native recording decoded |
| `nl` | No supported voice suffix | Installed official localization; translation only |

The four observed DLC families are Blood Ties, Cold Darkness, Endurance and
Baba Yaga. Their installed data does not establish account entitlement or that
every branch of each DLC has been played. Native evidence covers those installed
packs; non-English **base-game** playback remains inferred from the same
reviewed MUL/FSB layout and official language support, because those base packs
were absent on the audit host. Synthetic tests exercise every archive suffix
without requiring proprietary fixtures.

Select a missing base language in Steam Properties → Language, let the download
finish, then prepare that study language again. This is the procedure described
by [Nixxes' official support reply](https://steamcommunity.com/app/391220/discussions/1/451852225137889187/).
The cheap setup check reports installed DLC without the base pack as incomplete;
prepared DLC recordings remain usable. Neither setup nor preparation changes
the launcher language or downloads game assets automatically.

Subtitles carry explicit numeric language IDs inside their original audio
streams. The two Chinese packs retain separate source identities. English audio
is never substituted when a selected recording is absent, even when an English
archive's broad locale mask includes other text languages.

See the [narrative audit](game-audits/rise-tomb-raider.md) for exact bindings,
cinematic grouping, native counts and remaining movie/readable limitations.
