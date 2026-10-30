# Play on mobile with one library file

The [mobile companion](https://firebird55.github.io/Game-immersion-toolkit/)
reads your private library from Files. Your PC prepares it from your installed
game and can be off during play. Game libraries never belong in GitHub, Pages
or toolkit releases.

## Export on Windows

1. In **Setup → Games & Languages**, choose **Keep mobile library updated**.
   The same controls are available in the first-run wizard.
2. Choose an existing private export folder, preferably one synchronized with a
   cloud-storage service available on your phone. Select voice languages and one
   translation for each, then **Save settings**. Chinese text scripts share
   Mandarin audio. Each selected script remains a distinct library.
3. The companion waits for stable game files and creates one ZIP per selection:
   **Zenless Zone Zero/Zenless Zone Zero - Japanese - English translation - Mobile Library.zip**.
   Cloud synchronization is performed by your cloud application. **Updated in
   export folder** does not mean the phone has downloaded it.

Automatic rules are per-PC settings, independent of Lexirise credentials and
active reading selections. The companion must be running to detect updates.
It checks at startup and periodically, catches up after downtime, and preserves
**Pause** across restart. **Resume**, **Update now**, and **Retry** are available.
Adding a language queues a package; removing it stops updates without deleting
existing ZIPs. Manual account-scoped exports remain under **Export mobile library**.

Voice status is separate from table preparation: **Installed**, **Not detected —
install this voice language in the game/launcher**, **Incomplete**, or **Unable to
verify**. Checks are bounded; shared or encrypted archives may require successful
language preparation to establish their locale. An unprepared table does not
mean that the voice pack is absent. Missing selections stay configured and wait;
no other language's audio is substituted.

Working files and verified converted clips stay in host-local managed storage,
outside the synchronized destination. Publication copies and verifies a temporary
ZIP before replacing the final filename. Copy, disk-space, locked-file and source
change failures preserve the old ZIP. One previous completed ZIP is kept in local
recovery storage. Interrupted work resumes; unknown repeated preparation failures
require **Retry**. Unrelated destination files are never removed.

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
   Enter its stream code or complete private viewer link on the receiving phone.
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

Leave **Keep on this device** checked when importing. A dedicated worker copies
bounded chunks into browser-owned private file storage; the library selector
shows each retained game's languages and size. Several games and language
variants can coexist. The last retained selection reopens automatically, including
voices. **Update from file** replaces the matching variant only after a successful
copy and validation. Interrupted copies are cleaned up without deleting the last
working copy. **Remove downloaded copy** preserves history, favorites, calibration
and credentials.

The app requests persistent storage, but browser/OS eviction, private browsing,
user clearing and device storage pressure can still remove it. Missing files keep
their library metadata and show restoration instructions. Keep your ZIP in Files
or cloud storage as the recovery source. Quota or unavailable file-system support
produces an explicit session-only warning. Uncheck **Keep on this device** for
session-only use; selecting the original file is then required after reopening.

On iPhone, Safari cannot silently reopen a previous Files-provider selection to
read its replacement. After the desktop updates a cloud ZIP, select the new ZIP
once. The retained copy then reopens automatically. No cloud API or hosted account
service is used. Safari and Home Screen storage must be tested separately.

A disabled **Play voice** now explains whether the line has no exported audio or
this session needs the original file. Tap **Open voice library** beside the line
to reselect it directly. Reopening refreshes saved voice references against the
current catalog while preserving favorites. If Safari requests another gesture,
tap play on the visible audio control.

ZZZ comic recognition groups text by bubble and handles multiple visible bubbles
independently. It accepts the same 88% OCR similarity threshold as desktop for
authored comic lines, rejects ambiguous matches and confirms each bubble in two
frames. A bubble is added once while it remains visible, including slow scans.

Download cloud-provider files locally before playing, or keep a selected USB
drive connected. Safari/Files may stage the file temporarily. Browser quota is
not actual device free space; use iPhone Storage settings to check that.
If retaining the package fails, this session can still work; reopen the file next time.

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

VDO.Ninja uses its hosted viewer and may use relay services. The private link stays in memory unless **Remember on this device** is enabled; OCR runs locally with one bounded, self-hosted worker. Hidden
pages suspend reading; resuming requires fresh frames. Automatic same-link
recovery retains OCR intent. **Disconnect screen** cancels that intent, while
**Pause** pauses recognition without stopping the gaming device's broadcast.

Automatic rules prepare new libraries after game updates while the companion runs.
Software updates replace only static assets and preserve libraries and settings.
Disconnect before applying **Reload latest**, then tap **Start playing** to connect.
Remembered links restore the controls without starting a connection.

Catalog coverage and recognition vary by game, scene, font and subtitle layout.
See [Games & Languages](https://firebird55.github.io/Game-immersion-toolkit/games.html).
Physical iPhone Files/provider and native broadcast endurance remain explicit
acceptance checks; desktop WebKit is not a physical iPhone pass.
