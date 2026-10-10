# Updating after a game patch

Finish the patch and Mandarin voice downloads in the game's official launcher.
Open **Setup → Games → Refresh game data**. Users can do this on their own PC;
compatible content changes do not require a new toolkit release or a change to
the toolkit repository. The toolkit reads the installation without modifying it.

## What refresh updates

Most adapters rebuild bilingual text and original-voice mappings directly from
installed game files. ZZZ also refreshes its external language/scene metadata.
NTE reads English/Chinese localization, subtitle cue times and original Mandarin
media locally; its movie-to-voice binding tables come from
[NTE_Assets](https://github.com/Waifus-Grace/NTE_Assets).
Honkai's bilingual text hashes and authored event references come from
[HonkaiImpactData](https://github.com/nairieberry/HonkaiImpactData), then are checked
against installed Mandarin banks and sources.

NTE movie bindings and Honkai catalogs now check those fixed sources' default
branches once a day while the companion runs. A detected game-file change or
explicit **Refresh game data** checks immediately. Every refresh resolves one
immutable commit first and reads all required files from that commit. Complete
schemas and usable bilingual/event links must validate before the catalog is
published. A changed catalog rebuilds the index even if game files have not
changed. NTE's extracted-event cache also accounts for the catalog change.

Downloaded catalogs are JSON data, never executable reader updates. Sources and
file paths are fixed in the adapter; remote responses cannot choose download
URLs, output paths, scripts or commands. Runtime snapshots retain their source
revision and cache checksums. These checks detect corrupt caches and interrupted
downloads; they do not independently certify an upstream translation's accuracy.
The source is still a trust dependency. Installed-language, event, media and
ambiguity validation remains required for playable mappings.

## Failed updates and coverage limits

An unavailable or incompatible catalog update keeps the last complete catalog
and displays a warning in setup. An existing reviewed cache can be upgraded to
the new snapshot layout offline. A fresh install needs a successful complete
download; the reviewed seed revision is a fallback when the latest source is
unavailable. Failed indexing preserves the previous complete dialogue index.
Changed game files continue to block stale voice extraction until rebuilt.
Private snapshots stay in ignored `data/<game>/catalog-snapshots`; they are not
included in source or installers. Capture calibration and credentials remain
separate and are preserved.

**Honkai's currently available bilingual source remains the older 4.7 catalog.**
This update mechanism does not unlock Part 2 or newer chapters. They become
eligible only when a complete compatible bilingual catalog supplies their exact
authored event references and the reader verifies the corresponding installed
Mandarin source. Do not combine an old language map with a newer dialogue table,
guess IDs, translate OCR text, or substitute recorded audio to claim support.

Changes to archive encryption, serialization, bank layouts, or presentation
formats can still require a reader/OCR change and a normal toolkit release.
Automatic data refresh is not a promise of compatibility with every future
patch. Setup reports catalog availability separately from playable index state.

## Contributor validation

Use synthetic catalogs and mocked downloads. Check same-commit language
consistency, complete schema validation, cache integrity, explicit refresh,
scheduled throttling, offline upgrade, partial-download failure and a changed
catalog with unchanged installed files. Verify that missing or ambiguous
installed voices cannot replace the last playable index. Never commit catalogs,
game text, audio, or credentials. Keep executable dependencies checksum pinned;
data refresh must not install code from a moving branch.
