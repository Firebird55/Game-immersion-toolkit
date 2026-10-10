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

On this PC, the installed text provides 47,119 dialogue variant records and
the downloaded Mandarin pack provides 46,280 exact original voice mappings.
Original dialogue `wuwa:Character_JiYan_12_1` decoded to a non-silent 3.84-second
clip. Female and male variants of `Character_JiYan_18_1` also decoded to distinct,
non-silent 2.62- and 2.93-second clips. Ownership, gender selection, missing-pack
behavior, foreign-language rejection, resource isolation, and automatic update
fingerprints are covered by offline regression checks.

The initial synthetic 3840 × 2160 English and Chinese screenshot fixtures passed
through production cropping and native Windows OCR. Both correctly remained in
`waiting_for_voice` without creating transcript rows while the Chinese pack
was absent. Browser checks cover Rover selection, independent calibration,
asset refresh, and the missing-pack message even when the subtitle index is
ready. Actual gameplay appearance remains untested because no game was launched.
Optional official HD/SD video downloads and valid small empty patch archives are
accepted by the extractor; unknown archive paths are still rejected.

After the Mandarin download, all 40 English/Chinese cases in the
[resolution matrix](ocr-resolutions.md) captured the exact original voice ID
at ten resolutions and two subtitle font sizes.
