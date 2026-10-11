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
4. Leave **Include original Mandarin voices** enabled and click **Export mobile
   library**. Uncheck it for a smaller, text-only catalog. First voice conversion
   can take considerable time; progress and the final size appear in Setup.
5. Copy the completed folder's **catalog ZIP and voice ZIPs** to your phone.
   Keep them zipped, in **Files → On My iPhone**, with enough free space. Transfer
   using your normal cable, AirDrop from a Mac, or file-transfer method. A cloud
   file provider can be used for transfer, but download/move the final copies
   locally before playing.

The CLI uses the same exporter, from the toolkit folder:

```powershell
python scripts/export-mobile-library.py --game zzz
python scripts/export-mobile-library.py --game cyberpunk --catalog-only
```

Use the toolkit's installed Python environment if system Python lacks its
dependencies. `--output <private-folder>` changes the destination. `--max-lines`
is a verification subset, not a complete-game export. The default private
destination is `output/mobile-libraries/<game>/<revision>/`; `latest.json` points
to the last completed revision. Intermediate caches and decoded originals are
not transfer files. Do not upload any of these to GitHub.

Cancel and retry safely. Completed decoded clips are verified and reused;
unchanged completed voice packs can be reused. Previous valid exports remain
available if indexing, decoding, cancellation, disk space or source checks fail.
Do not patch the game during an export. Refresh and export again afterward.
The exporter detects changes to its source files and refuses to publish a mixed
snapshot. Decoder cancellation takes effect between bounded work steps.

## Open on the receiving phone

1. Open the bookmark in Safari, tap **Reload latest**, then use **Share → Add to
   Home Screen** if desired. Set up the library in the surface you intend to use;
   Safari and a Home Screen application can have separate browser storage.
2. Choose **Receive screen** and your game. Under **Open your game library**, tap
   the file picker, browse **On My iPhone**, and select the catalog and multiple
   voice ZIPs. You can open additional matching voice packs later.
3. Check the bilingual row count, partial coverage notice, selected pack size
   and the count of voice clips **accessible this session**. Remembered catalog
   information does not mean the audio files are currently open.
4. Pair with the device sending the game using the existing offer/answer flow.
   Select English or Simplified Chinese subtitles, and the player voice if the
   game has player variants. Tap **Start OCR**. Keep the receiving page visible.
5. Read the Chinese/English transcript and tap **Play original voice**. If Safari
   requires another playback gesture, use the visible audio control. **Find line**
   also lets you verify a catalog line and local playback without a live stream.

After reopening or rebooting, text/history can be restored from browser storage,
but select the voice ZIPs again. Files permissions and objects are session-only.
The page verifies the selected packs against the remembered catalog. If browser
data was cleared, reopen the catalog as well. Missing, corrupt or wrong-game
packs cannot enable playback. Keep the Files copies as your recovery source.

The page requests persistent browser storage and displays the actual granted
status. A request is not a guarantee: Safari may still clear best-effort data or
the user can delete it. Audio stays in Files; only catalogs, preferences,
calibration, bounded transcript history and favorites are cached. A voice is read
by ZIP entry using `File.slice()` when played, rather than importing a multi-GB
pack into IndexedDB. SHA-256 and ZIP CRC checks protect those reads.

## Capture, matching and updates

Direct pairing/reconnect and capture reports remain available; reconnecting
does not clear your library or history. The gaming device must actually supply
moving frames while the game is foregrounded. iPad Safari generally cannot
provide that system capture; a native sender helper is still outside this build.
Use a PC sender for receiver testing until a working mobile sender is available.
A Home Screen shortcut does not add a missing screen-capture API.

OCR runs in one pinned, self-hosted Tesseract.js 7 worker. Frames remain on the
devices. Scans use the newest frame, without a queued backlog, and suspend when
paused, hidden, disconnected or superseded by a new stream/game. Two stable
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
do not migrate or delete the catalog/history/preferences database.

## Physical iPhone acceptance test

Automated Chromium, Firefox and WebKit results do not establish physical iPhone
reliability. Perform these checks on the actual phone:

1. Record the displayed build and actual persistence status. Open a catalog plus
   multiple voice packs totaling **at least 2 GiB**. Record opening time/failures.
2. Play a known original clip and favorite its line. Verify audio is local and
   correct, and note playback timing in **Download library test report**.
3. Reload: remembered text/history should return, while playback requests pack
   reselection. Reselect, verify the accessible count, and play again.
4. Reboot the phone, reopen and repeat selection/playback. Retain the Files
   originals throughout. Check recovery if browser caching was unavailable.
5. Once a newer application build is published, stop capture, update, and check
   the same favorite, history and calibration before reselecting voices.
6. Complete **15 minutes** of actual gameplay, with dialogue, a supported special
   presentation, rotation/resolution changes, a pause and manual reconnect.
   Confirm moving game frames, correct bilingual lines and original playback.
7. Fill **Physical device verification** with only observed checks. Download the
   library report and both devices' capture reports. Library reports contain
   timings/counts/storage state and observations, without file names, original
   text, game frames, pairing messages, account details or installation paths.

To test large file providers without game content, contributors can generate
an owned synthetic 2.15 GiB library:

```powershell
python scripts/generate-mobile-storage-test.py
```

Transfer the six generated ZIPs from ignored `output/mobile-storage-test`, open
them and use **Find line → Storage test line 0** to play the small generated tone.
This tests storage access, not real game voices or gameplay OCR.

## Package and contributor checks

Format `proxy-mobile-library-v1` uses STORE-only ZIPs capped at 512 MiB. Catalog
NDJSON entries are approximately 4 MiB, with a 128 MiB/200,000-row total limit.
Manifest and voice-entry limits are 8 MiB and 64 MiB. Stable dialogue/variant,
revision, content and pack identities are retained; clips are deduplicated by
content hash. Readers reject compression, unsafe names, overlapping/truncated
entries, duplicate identities, mismatched packs and failed checksums. Imported
strings are rendered as text.

Run `npm run mobile:check`, repository checks and the public audit. Public CI
uses only authored synthetic text, video and tone fixtures. For private footage:

```powershell
python scripts/prepare-mobile-replay.py
node scripts/replay-mobile-ocr.mjs
```

The existing annotation manifest supplies positive/negative expectations.
Local media, prepared catalogs, images and detailed results stay in ignored
`output/`; the replay server binds only to loopback. Resized/padded footage
checks crop/OCR behavior, not native game UI reflow. Record failures honestly and
never mark a missing scene or chapter verified because packaging succeeded.
