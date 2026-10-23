# Mobile libraries in On My iPhone

The public [mobile companion](https://firebird55.github.io/Game-immersion-toolkit/)
reads ZIPs you select from Files. Your PC prepares those ZIPs from your own
installed game; it can be off during play. Catalogs and voices are never hosted
on Pages, uploaded to an OCR service or included in toolkit releases.

## Export on Windows

1. Install the current toolkit release and open **Setup → Games**.
2. Choose one supported game, configure its installed folder and install its
   Mandarin voice pack. Install/repair its reader tools if Setup requests them.
3. After the launcher finishes updating, click **Refresh game data** and wait
   for the index to become ready. Check the game's documented coverage.
4. Under **Mobile library**, choose **Save libraries to → Browse**, or paste an
   absolute folder path. This destination is remembered on this PC. Each game
   gets its own subfolder. Choose a drive with enough free space for ZIPs,
   conversion and reusable caches; Setup shows an approximate working-space budget.
   Leave **Original Mandarin voices** enabled and click **Export mobile library**.
   Uncheck it for a smaller, text-only catalog. Setup shows an estimated size in
   GB before export, a range and the estimate's basis. Typical clip sizes are used
   initially, or the size of a previous completed export. During conversion the
   estimate is refined from measured clips and deduplication; completed ZIP bytes
   are exact. First voice conversion can take considerable time.
5. Open the readable **Game - Mobile Library - revision** folder. Its catalog
   and numbered voice ZIPs are the transfer files. Copy only that completed
   folder, not the parent folder of an older export: it may contain thousands of
   cached clips. New exports keep resumable work in `.toolkit-mobile-work`
   outside the selected save folder, on the same drive. Legacy work moves there
   when the same destination is next exported; completed libraries stay in place. Copy the completed **catalog ZIP and voice ZIPs** to your phone.
   Keep them zipped, in **Files → On My iPhone**, with enough free space. Transfer
   using your normal cable, AirDrop from a Mac, or file-transfer method. A cloud
   file provider can be used for transfer, but download/move the final copies
   locally before playing. Alternatively, select ZIPs directly from a connected
   USB drive in Files. Keep the drive connected and the phone unlocked. The app
   does not copy voice packs into browser storage; Safari/Files may still stage
   selected files temporarily, so zero temporary device storage is not guaranteed.

The CLI uses the same exporter, from the toolkit folder:

```powershell
python scripts/export-mobile-library.py --game zzz
python scripts/export-mobile-library.py --game cyberpunk --catalog-only
```

Use the toolkit's installed Python environment if system Python lacks its
dependencies. `--output <private-folder>` changes the destination. `--max-lines`
is a verification subset, not a complete-game export. The default private
destination is `output/mobile-libraries/<game>/<revision>/`; `latest.json` points
to the last completed readable folder. Use its `folder` and `catalog` fields
rather than constructing a path from the revision hash. Intermediate caches and decoded originals are
not transfer files. Do not upload any of these to GitHub.

Cancel and retry safely. Completed decoded clips are verified and reused;
unchanged completed voice packs can be reused. Previous valid exports remain
available if indexing, decoding, cancellation, disk space or source checks fail.
Do not patch the game during an export. Refresh and export again afterward.
The exporter detects changes to its source files and refuses to publish a mixed
snapshot. The desktop Cancel button stops the isolated export process and its
decoder children, including during catalog preparation. Setup shows **Stopping…**
until the process exits, then **Resume export**. Cancellation keeps verified
completed clips and the previous valid export. The CLI uses the same package
writer; Ctrl+C interrupts its current command.

Voice conversion automatically uses up to eight parallel workers, scaled to
the PC's CPU count. Existing audio quality and cinematic timing are preserved.
All eight voice-supported games convert up to eight clips per worker batch
to reduce decoder launches. Archive extraction groups compatible resources,
including Cyberpunk DLC, and reuses package tables within each batch. Wuthering
uses shared prefixes only when its installed inventory bounds the extraction.
Each clip keeps its verified binding, player variant and cinematic timing;
PRAGMATA retains its authored layer mix. Hito remains catalog-only.
The CLI accepts `--workers 1` through `--workers 8` for manual tuning. Use the
same destination when resuming so verified clips can be reused.

## Open on the receiving phone

1. Open the companion in Safari, then use **Share → Add to
   Home Screen** if desired. Set up the library in the surface you intend to use;
   Safari and a Home Screen application can have separate browser storage.
2. Choose **Receiver → Mobile OCR** and your game. Open **Library**, then tap
   the file picker, browse **On My iPhone** or your connected USB drive, and select the catalog and multiple
   voice ZIPs. You can open additional matching voice packs later.
3. Check the bilingual row count, partial coverage notice, selected pack size
   and the count of voice clips **accessible this session**. Remembered catalog
   information does not mean the audio files are currently open.
4. Connect the gaming device in **Connection**: choose **VDO.Ninja native iPhone /
   iPad** and its complete private viewer link for two iOS devices, or **Browser
   screen pairing** for the existing offer/answer flow. Follow the
   [native SCREEN instructions](mobile-capture.md#two-ios-devices-with-native-vdoninja).
   Select English, Simplified Chinese or Traditional Chinese subtitles, and the player voice if the
   game has player variants. Tap **Start OCR**. Keep the receiving page visible.
   A small live preview stays visible while OCR runs, including when you scroll
   to the transcript; browsers can suspend video that moves off screen.
5. Read the prepared learning/translation transcript and tap **Play original voice**. If Safari
   requires another playback gesture, use the visible audio control. **Find line**
   searches English or Chinese fragments without a live stream. Multiple scenes
   or voice variants are listed for explicit selection. Unvoiced bilingual text
   is retained and labeled **No verified original voice**, rather than silently
   omitted. Existing voice-only exports need a newly exported catalog for that
   additional text; unchanged voice-pack identities remain usable.

See [Games & Languages](https://firebird55.github.io/Game-immersion-toolkit/games.html)
for each game's learning/audio and official translation combinations. Catalogs
retain the selected learning, translation and audio locales. Mobile OCR's three
recognition models do not cover every learning language; use supported in-game
subtitle text that exists in the prepared catalog, or use the paired-PC reader.
Full-game footage coverage remains incomplete.

After reopening or rebooting, text/history can be restored from browser storage,
but select the voice ZIPs again. Files permissions and objects are session-only.
The page verifies the selected packs against the remembered catalog. If browser
data was cleared, reopen the catalog as well. Missing, corrupt or wrong-game
packs cannot enable playback. Keep the Files copies as your recovery source.

The page requests persistent browser storage and displays the actual granted
status. The page checks remaining browser quota against an estimated catalog cache
budget, excluding voice-pack sizes. This is website quota, not actual device free
disk space; consult **Settings → General → iPhone Storage** for that. If quota is
low or caching fails, the current session remains usable and requests catalog
reselection next time. Persistence permission requests are bounded and do not
block catalog caching. A request is not a guarantee: Safari may still clear best-effort data or
the user can delete it. Audio stays in Files; only catalogs, preferences,
calibration, bounded transcript history and favorites are cached. A voice is read
by ZIP entry using `File.slice()` when played, rather than importing a multi-GB
pack into IndexedDB. Opening validates directories and manifests with four reads
per ZIP; selected entries receive local-header, bounds and checksum validation
before use. Progress, cancellation and file-read timeouts explain slow or
disconnected providers. Large catalogs stay in the worker rather than being
copied into the page, and fuzzy OCR indexing is delayed until needed. SHA-256 and ZIP CRC checks protect those reads.

## Capture, matching and updates

Direct pairing and reconnect remain available; reconnecting
does not clear your library or history. The gaming device must actually supply
moving frames while the game is foregrounded. iPad Safari generally cannot
provide that system capture. The native VDO.Ninja **SCREEN** route uses the
gaming iOS device's broadcast extension and the other device's static receiver;
no PC is required during play. Physical two-device acceptance remains pending.
Use a supported browser sender, or choose **Paired PC** to receive the desktop transcript.
A Home Screen shortcut does not add a missing screen-capture API.

OCR runs in one pinned, self-hosted Tesseract.js 7 worker on the receiver. Native
stream delivery uses the external hosted viewer and may involve VDO.Ninja relay
services; OCR does not upload frames. Scans use the newest frame, without a queued backlog, and suspend when
paused, hidden, disconnected or superseded by a new stream/game. Each resume or
source switch invalidates pending frames, OCR and catalog replies. Normalized
crop coordinates survive changing frame dimensions; recheck subtitle placement
after rotation. Two stable
sightings confirm an accepted line. Short/ambiguous text and response menus are
rejected; additional presentations retain stricter, exact matching.

**Capture regions and calibration** lets you select dialogue, overhead, comic or
card regions independently. **Preview dialogue crop** shows the selected region.
Use **Original image** for custom colors/fonts if outlined-subtitle preparation
loses text. Percentages follow video pixels, not phone orientation or browser
zoom. Select **Centered 16:9** when the video has black bars. Recheck after stream
resolution, subtitle size, aspect ratio or safe-zone changes. Overhead captions,
comics and centered cards can be enabled separately. A supported catalog does
not prove recognition of every layout, font or scene.

Only catalog-backed bilingual text is displayed. Original voice playback needs
a unique exact binding and an open pack. Unmatched scenes and ambiguous bindings
are skipped explicitly. Export supports ZZZ, Wuthering, PRAGMATA, Cyberpunk,
Witcher, NTE and limited Honkai catalogs. Hito exports its fixed verified rows
without audio; its desktop runtime grammar generator is not included on mobile.
Installed DLC is included where the existing adapter maps it, including
Cyberpunk Phantom Liberty. Honkai's newer chapters remain outside the verified
catalog; successful export does not extend that coverage. Upstream format
changes can still require a toolkit update.

After a game patch, refresh and export on your PC and transfer the new catalog
and required voice packs. Unchanged pack identities may remain usable. No new
GitHub release is required for an ordinary locally readable game-data update.

Software updates cache only allowlisted application/OCR assets. The service
worker waits rather than replacing an active session. Stop sharing, tap
**Reload latest**, check the build version, then pair again. Application updates
preserve and migrate the catalog/history/preferences database in place.
The first visit requires Internet access. Start OCR once with each subtitle
language you intend to use offline, so its worker, core and model are cached.
Remembered catalogs and local voice playback do not require a model download.

## Reading and account tools

Choose **Receiver → Mobile OCR**, then use **Library** to open ZIPs, search catalog
text, start/pause OCR and calibrate regions if necessary. Return to **Reader** for
the current line and bilingual history. Favorites belong to this browser.
**Settings** controls reading modes, translation visibility and encrypted Lexirise
credentials. Paired PC reading does not need an exported library.

Application updates migrate existing catalog, calibration and history storage in
place. Clearing browser/site data removes these and your encrypted key. Keep
original ZIPs. Updates wait for sharing and library operations to finish; select
voice packs again after reloading. See the [main guide](../README.md) for vault
locking and gateway data handling.
