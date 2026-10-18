# Game immersion toolkit

**Read the dialogue. Stay in the story.** Proxy Transcript brings official game
dialogue, original voices and language-specific reading tools to desktop, phone and tablet.

Open the [online companion](https://firebird55.github.io/Game-immersion-toolkit/).
Choose **Receiver**, then choose a transcript source:

- **Mobile OCR:** open a privately exported game catalog and optional voice ZIPs
  in **Library**, pair with a screen-sharing device in **Connection**, and start
  OCR. Return to **Reader** for the current line, searchable history and favorites.
  The small video surface stays visible while OCR runs. The PC can be off.
- **Paired PC:** in the Windows companion click **Share transcript to another
  device**. Keep its sharing page and companion running. Select the same game on
  the receiver, open **Connection**, and scan the offer QR. No screen-capture
  permission or mobile library is needed. Older history and original voices are
  requested directly from the paired PC.

Pairing supports devices on the **same network**. With automatic recovery enabled,
the reply travels through encrypted signaling; otherwise scan the receiver's
answer back on the sender. Pairing files and copy/paste are also available.
Stopping sharing immediately closes transcript and audio access. Receiver
favorites stay on the receiver and never alter PC history or favorites.

In **Reader**, use **History / Favorites**, search, **Original voice**, and
**Reading options**. In **Settings**, choose independent Migaku mode or connect
Lexirise for analysis, dictionary/character/context/example lookups, vocabulary
choices and explicit sentence/deck saving. Migaku requires a supported browser
extension; mobile browsers that cannot run it still show plain bilingual text.

PC capture also keeps verified ZZZ comic bubbles when the game catalogue has no
voice mapping. Their prepared official text appears in Current line
and History; audio stays unavailable unless an original voice is verified.

## Connect Lexirise

In **Settings → Lexirise**, enter your own Pro API key and confirm a passphrase of
at least 12 characters. The key is encrypted in this browser's IndexedDB using
AES-256-GCM and PBKDF2-SHA-256 with 600,000 iterations, a random 16-byte salt and
fresh 12-byte IV. Neither the plaintext key nor passphrase is stored.

Unlock after reopening. **Lock**, page exit/reload, or five minutes in the
background removes the in-memory key and cancels account requests. Local reading
and audio continue. **Change passphrase** re-encrypts the saved key. A forgotten
passphrase requires entering the key again. **Forget key** removes local
credentials but does not revoke the key at Lexirise. Encryption protects stored
credentials, not a compromised page while unlocked.

Lexirise works with the PC off through a separate, stateless HTTPS gateway. It
forwards only approved reading/account operations to Lexirise, stores no keys,
transcripts or account responses, disables caching/logging/tracing, and applies
request limits. Opening the companion or restoring preferences never creates a
deck or writes account settings. Account writes require your explicit controls.

## Install the Windows companion

Download a [release](https://github.com/Firebird55/Game-immersion-toolkit/releases)
and double-click **Install.cmd**. **Setup** locates your installed games, prepares
reader tools and voice indexes, and configures capture and reading preferences.
Game assets are never included in a release. Supported catalogs include Zenless
Zone Zero, PRAGMATA, Cyberpunk 2077, Wuthering Waves, The Witcher III, Neverness to
Everness and Hito's World. See each game's guide
for coverage and required voice packs. Existing transcripts remain Chinese.

## Keeping your data

Updates preserve libraries, history, favorites and calibration. When an update
notification appears, stop sharing and finish library operations before applying
it. Installed static assets and cached catalogs support offline reading; Lexirise
needs a network connection. Voice ZIPs must be reselected after reopening. Keep
copies in Files or on your USB drive: browser storage is best effort. Clearing
site data removes cached transcripts, favorites, settings and the encrypted key.
PC data and credentials remain local to the PC.

Browser capture may be unavailable on iPad or stop when switching apps. This
release **does not include the unfinished native iPad capture helper**. A Home
Screen installation does not add background capture capability.

- [Pairing, sources and recovery](docs/mobile-capture.md)
- [Exporting and opening local libraries](docs/mobile-library.md)
- [Installation](INSTALL.md) · [Desktop details](docs/desktop-companion.md)
- [Developer verification](docs/online-companion-development.md)
- [Contributing](CONTRIBUTING.md) · [Agent rules](AGENTS.md) · [Release / rollback](RELEASE.md)

Created by [Firebird55](https://github.com/Firebird55/Game-immersion-toolkit).

Honkai Impact 3rd is archived and unsupported. It is not available in setup, capture or the web UI. See [archived support](docs/archived-honkai.md).

Use [Languages and local accounts](docs/languages-and-accounts.md) to explicitly
prepare a game language, switch protected accounts and follow each learning
language's Lexirise translation, dictionary and reading preferences.

BEYOND: Two Souls adds explicit language preparation and original Dutch speech.
See [setup and tested coverage](docs/beyond-support.md); full-game OCR acceptance remains incomplete.

HEAVY RAIN adds official text and original audio in ten voiced languages,
including Dutch with aligned Chinese translations. See [tested coverage](docs/heavy-rain-support.md).

NTE supports all four original dubs and both Chinese scripts; see
[language preparation and validation](docs/nte-languages.md).
PRAGMATA supports all eleven original dubs and fourteen official text locales;
see [language preparation and validation](docs/pragmata-languages.md).
Wuthering Waves supports all four original dubs and both Chinese scripts;
see [language preparation and validation](docs/wuthering-languages.md).
ZZZ supports all four original dubs and both Chinese scripts;
see [language preparation and validation](docs/zzz-languages.md).
