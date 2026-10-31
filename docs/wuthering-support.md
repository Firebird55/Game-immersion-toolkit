# Wuthering Waves

The toolkit reads official dialogue from the installed game's ConfigDB. Prepare
English, Japanese, Korean, Simplified Chinese or Traditional Chinese in
**Settings → Games & Languages**. Choose the installation in Setup or let the
toolkit discover the Steam library. See [language preparation](wuthering-languages.md)
for selected study text, aligned translations and original voice availability.

Original voice ownership follows the game's `PlotAudio` ID and
`FileName` fields, plus its own per-dub gender flags and external-source filename
rules. Choose **Rover voice** in Capture setup for lines addressed to, or spoken
by, female or male Rover. Ambiguous repeated text, dynamic filenames, and shared
language-independent creature audio are excluded from selected-dub capture. No
event-name guesses, recordings, or synthesized voice fallbacks are used.

Download the **selected voice pack inside Wuthering Waves** to enable voiced
capture and original playback. Both Chinese scripts use Mandarin. Without the
pack, official text is indexed and the companion
shows a missing-pack message. A later pack download changes the archive
fingerprint and triggers automatic reindexing. Base files and patch files are
read together, with the extractor preserving patch priority. User mods are
outside the supported indexing contract; the toolkit never installs mods or
changes game archives.

Extraction uses the same owned, app-local managed archive helper as NTE, with
checksum-pinned CUE4Parse dependencies. Complete Windows x64 desktop bundles
need no SDK or separately installed runtime; native Oodle/zlib downloads are
not used. See the [runtime evidence and platform limits](wuthering-runtime.md).
Original assets are never redistributed. Public archive metadata comes from the endpoint
documented by [wuwa-keys](https://github.com/yarik0chka/wuwa-keys) and remains in
memory. It travels on private stdin and is never stored in source, manifests,
command arguments or logs. Complete helper source/dependency notices accompany
its resource inventory.

The initial Chinese-only probe provided 47,119 dialogue variant records and
the downloaded Mandarin pack provides 46,280 exact original voice mappings.
Original dialogue `wuwa:Character_JiYan_12_1` decoded to a non-silent 3.84-second
clip. Female and male variants of `Character_JiYan_18_1` also decoded to distinct,
non-silent 2.62- and 2.93-second clips. Ownership, gender selection, missing-pack
behavior, foreign-language rejection, resource isolation, and automatic update
fingerprints are covered by offline regression checks.
The newer production managed-reader pass includes narrative records and all
five study locales; its current counts and original playback evidence are in
the [runtime report](wuthering-runtime.md).

The initial synthetic 3840 × 2160 English and Chinese screenshot fixtures passed
through production cropping and native Windows OCR. Both correctly remained in
`waiting_for_voice` without creating transcript rows while the Chinese pack
was absent. Browser checks cover Rover selection, independent calibration,
asset refresh, and the missing-pack message even when the subtitle index is
ready. Recorded retail footage now verifies early-game/3.0 dialogue and centered
story cards; see [game-specific OCR presentations](game-ocr-presentations.md).
No game was launched.
Optional official HD/SD video downloads and valid small empty patch archives are
accepted by the extractor; unknown archive paths are still rejected.

After the Mandarin download, all 40 English/Chinese cases in the
[resolution matrix](ocr-resolutions.md) captured the exact original voice ID
at ten resolutions and two subtitle font sizes.
