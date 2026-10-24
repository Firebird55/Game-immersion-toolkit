# Play on mobile with one library file

The [mobile companion](https://firebird55.github.io/Game-immersion-toolkit/)
reads your private library from Files. Your PC prepares it from your installed
game and can be off during play. Game libraries never belong in GitHub, Pages
or toolkit releases.

## Export on Windows

1. In **Setup → Games**, prepare the chosen game, learning language and original
   voices. Refresh game data after a launcher update.
2. Choose a private save folder and **Export mobile library**. Leave original
   voices enabled for audio. Setup estimates both transfer and working space.
3. Transfer the single **Game - Audio Language - Mobile Library.zip** from the
   completed folder to your phone. For example,
   **Zenless Zone Zero - Mandarin - Mobile Library.zip**. Keep it zipped.

Conversion still uses up to eight parallel workers and compatible batches.
Verified clips and bounded inner packs remain in a separate private workspace
for resuming. The final STORE bundle includes the catalog automatically, without
re-encoding voices. Its last packaging step streams files from disk.
Cancellation or changed game assets cannot replace the last completed pointer.
Keep enough space for decoded clips, inner packs and the final bundle.

The existing CLI keeps its game, output, worker and catalog-only options:

```powershell
python scripts/export-mobile-library.py --game zzz --output <private-folder>
python scripts/export-mobile-library.py --game zzz --catalog-only
```

To combine an existing catalog and matching voice ZIPs without decoding again:

```powershell
python scripts/bundle-mobile-library.py '<Catalog ZIP>' --output '<private-folder>'
```

Use the installed toolkit Python environment when system dependencies are missing.
`latest.json` identifies the completed folder and bundle; its `catalog` field
also points to the transferable bundle for older folder readers. Export status
adds `bundle` and retains a private inner `catalog` path for local tooling.
Neither the work directory nor its decoded audio is a transfer item.

## Open and play

1. Open the companion on the receiving phone. Add it to the Home Screen first
   if that is where you intend to use it; Safari can have separate storage.
2. On **Play**, tap **Open library** and select the single Mobile Library ZIP.
   Check the game title and **Voices ready** status.
3. On the gaming iPhone/iPad, start the native VDO.Ninja **SCREEN** broadcast.
   Paste its complete private viewer link on the receiving phone.
4. Tap **Start playing**. It connects the screen and starts subtitle recognition.
   Keep this receiving page visible. Tap **Play voice** on matched dialogue.

English subtitle recognition is the default. **Settings** contains other subtitle
languages, optional OCR downloads, player voice selection, calibration, library
search, reading options and accounts. Select the player variant when a game has
ambiguous protagonist performances. Matching never guesses a missing voice.
Lexirise is optional; plain transcript and independent Migaku mode remain usable.

**Paired PC** is also in Settings. It receives the running desktop companion's
transcript and needs no mobile library. Browser screen pairing has been removed;
VDO.Ninja is the only screen source. See [connection setup](mobile-capture.md).

## Reopening, storage and recovery

After reloading or rebooting, tap **Reopen voice library** and select the same
file. History, favorites, calibration and the catalog may remain remembered;
voice file permissions last only for the current page session. Audio is never
copied into IndexedDB. Keep the ZIP in Files as the recovery source.

Download cloud-provider files locally before playing, or keep a selected USB
drive connected. Safari/Files may stage the file temporarily. Browser quota is
not actual device free space; use iPhone Storage settings to check that.
If catalog caching fails, this session can still work; reopen the file next time.

Older exports remain supported: select their **Catalog ZIP plus matching Voices
ZIPs together**. Seven voice ZIPs alone cannot supply subtitle matching unless
the correct catalog was already remembered. A missing catalog now produces an
explicit message. Picker resets no longer erase the visible selection/result.
Malformed, mismatched or cancelled replacements preserve the working library.

The reader validates the bundle directory and opens bounded inner packs through
file slices. ZIP64 supports large outer files; every inner pack stays at most
512 MiB. Catalog segments and played clips keep their bounds, CRC and SHA-256
checks. Whole voice packs are not read into browser memory. Unsupported archive
paths, compression, overlapping entries and unsafe offsets are rejected.

## Capture and updates

VDO.Ninja uses its hosted viewer and may use relay services. The private link
stays in memory; OCR runs locally with one bounded, self-hosted worker. Hidden
pages suspend reading; resuming requires fresh frames. Automatic same-link
recovery retains OCR intent. **Disconnect screen** cancels that intent, while
**Pause** pauses recognition without stopping the gaming device's broadcast.

After a game update, refresh and export a new library on the PC. Software updates
wait for an idle session and preserve browser data. Disconnect before applying
**Reload latest**, then reopen the library and paste the viewer link again.

Catalog coverage and recognition vary by game, scene, font and subtitle layout.
See [Games & Languages](https://firebird55.github.io/Game-immersion-toolkit/games.html).
Physical iPhone Files/provider and native broadcast endurance remain explicit
acceptance checks; desktop WebKit is not a physical iPhone pass.
