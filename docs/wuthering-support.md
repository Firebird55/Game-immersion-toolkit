# Wuthering Waves

The toolkit reads official English and Simplified Chinese dialogue from the
installed game's ConfigDB and captures either subtitle language. Study text
stays Chinese. Choose the installation root in **Choose Game Folders.cmd**,
or let the toolkit discover the Steam library automatically.

Original Mandarin voice ownership follows the game's `PlotAudio` ID and
`FileName` fields, plus its own `CheckGenderZh` and external-source filename
rules. Choose **Rover voice** in Capture setup for lines addressed to, or spoken
by, female or male Rover. Ambiguous repeated text, dynamic filenames, and shared
language-independent creature audio are excluded from Mandarin capture. No
event-name guesses, recordings, or synthesized voice fallbacks are used.

Download the **Chinese voice pack inside Wuthering Waves** to enable capture
and original playback. Without it, official text is indexed and the companion
shows a missing-pack message. A later pack download changes the archive
fingerprint and triggers automatic reindexing. Base files and patch files are
read together, with the extractor preserving patch priority. User mods are
outside the supported indexing contract; the toolkit never installs mods or
changes game archives.

Extraction uses checksum-pinned [FModelCLI 1.0.2](https://github.com/Herselfta/FModelCLI/releases/tag/v1.0.2),
which uses FModel/CUE4Parse. The executable and decompression libraries are
downloaded into ignored local `data/wuwa/tools`; original assets are never
redistributed. Public archive extraction metadata comes from the endpoint
documented by [wuwa-keys](https://github.com/yarik0chka/wuwa-keys) and remains in
memory. It is never stored in source, manifests, or logs. FModelCLI is an
external GPL-3.0 tool; its license and source are available in its repository.

On this PC, the installed text provides 47,120 dialogue variant records. Its
current files contain no Mandarin external-source pack, so original Mandarin
playback awaits that download. Ownership, gender selection, missing-pack
behavior, foreign-language rejection, resource isolation, and automatic update
fingerprints are covered by offline regression checks.
