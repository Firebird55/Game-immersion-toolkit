# Languages and local accounts

Open **Account settings → Lexirise accounts on this PC** to choose a saved
account. **Add account securely** opens a local hidden-input prompt. The key is
verified with the read-only identity endpoint and protected with Windows DPAPI.
The browser receives profile labels and opaque identifiers, never credentials.
The existing local credential remains available.

Each learning language uses its own Lexirise `effectiveTranslationLanguage`.
The global effective translation language is used only when that language has
no effective target. Inline glosses, readings, dictionaries and popup settings
come from that learning language. Changing accounts or reloading settings does
not save preferences or create decks. Account changes require an explicit save.
Where the public API does not offer a writable per-language translation target,
change it in Lexirise; the companion consumes its effective value.

In **Setup → Games → Languages**, select a game locale and click **Prepare
selected language**. Only the requested source and translation tables are
prepared. Available locale choices depend on the installed toolkit reader;
an unavailable reader or voice pack is reported, never substituted. Languages
are not prepared by opening setup, adding an account or starting the companion.

Previously prepared languages check for compatible game updates automatically.
Selecting another locale requires its own prepared table. A translation-target
change offers preparation of that target instead of building every language.
**Configure this language’s reading and dictionaries** opens that language’s
preferences. Per-device display overrides are stored by account and language.
Removing a preparation disables capture for that selection and stops its
automatic updates; it does not remove game files or shared extraction tools.

Game sentence translations use aligned official localization only. Missing
target text is shown as unavailable. Lexirise dictionary glosses remain
demand-driven and use the account’s per-learning-language target. No dictionary
entries are generated for an entire game catalog.

Sentence destinations are scoped by account and study language. Each destination
must be an owned sentence snapshot deck in that language. Selection, creation,
exports and preference writes are explicit actions. In-flight operations pin
their credentials, and stale account requests cannot run under another account.

The language-aware runtime uses new versioned transcript, export and reading
cache stores. Older local files remain untouched; their history is not silently
migrated or deleted. Game folders, calibration, protected credentials and
independent Migaku configuration remain on the PC. Recordings, account
diagnostics and extracted game data are never included in releases.
