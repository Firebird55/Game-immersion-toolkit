# Source installation to native desktop handoff

This is the reviewed one-time Windows transition procedure, not an implemented
general migration service or a record of a completed installation. Execute it
only after the replacement release, downloaded checksums and provenance are
verified. The source installation can continue running during preparation.
Keep local inventory, receipts, backups and account diagnostics private.

## Roots and preserved state

The source installation stores game data under its `data` directory and Windows
settings under `%LOCALAPPDATA%/Proxy Transcript`. Its protected account files
live under `%LOCALAPPDATA%/Programs/Proxy Transcript`. The native app defaults to
`%LOCALAPPDATA%/Game Immersion Toolkit`, with settings at that root and separate
`data`, `credentials`, `cache`, `tools`, `work`, `state` and `exports` directories.
An explicit native `--data-root` selects this whole per-user base, not its `data`
child. It must be outside the source checkout and installed application payload.

Inventory these families before the handoff, including any existing fallback
settings in source `data/settings.json`. An absent optional family is not a
reason to create or replace it with defaults.

| Family | Destination and treatment |
| --- | --- |
| `settings.json`, `game-paths.json`, `setup.json`, `languages.json`, `languages.requests.json` | Native settings root. Preserve capture calibration, Belle/Wise choice, prepared-language selection and account scope. The existing per-user settings file takes precedence over its older `data/settings.json` fallback. |
| `mobile-library.json`, `mobile-library/`, `automatic-mobile-libraries/rules.json` | Native settings root, preserving explicitly chosen destinations. Leave already exported libraries at their existing locations. Do not carry abandoned worker/picker state as an active operation. |
| `transcript-v2.db`, `lexirise/exports-v2.db`, `lexirise/reading-cache-v2.db` | Same relative paths under native `data`. Use SQLite's backup API for live copies; never copy only the main file of an open WAL database. Preserve older database generations in the private backup. |
| `audio/`, `textmaps/`, `voice-assets/`, `languages/`, per-game prepared caches | Same relative paths under native `data`. Preserve original audio and authored text/voice metadata. Installed-game paths remain references to the user's game files; do not move those games. |
| `accounts.dpapi`, `key.dpapi` | Copy opaque protected files into native `credentials` for the same Windows user and machine. Preserve a legacy `data/lexirise/key.dpapi` fallback when present. Never decrypt or log keys for the transfer. |

Prepared snapshots may contain absolute installed-game paths, which remain valid
when the game does not move. Validate any generated-cache path against the new
root before treating the cache as reusable. Runtime helpers come from the
verified native payload; old source `.venv`, `node_modules`, downloaded helper
executables and build intermediates are not installation inputs.

## Transition

1. Install the verified native payload with its final launch option disabled
   (silent installation also skips that post-install launch). Run its
   `--host-check` as the original desktop user. This checks the payload without
   starting a second API, capture owner or public gateway. The installer can
   stop an earlier registered native host; it does not stop a legacy source app.
2. Record a private source/destination inventory and backup. SQLite online
   backups can run while the old app is active. Pre-copy other durable files
   into private staging to reduce interruption, but do not call that live copy
   the final consistent snapshot.
3. Acquire the old source installation's `companion-operation.lock` through its
   existing operation-lease helper. Request API writer quiescence and require
   success. Use recorded process identities and retained process handles to
   stop its owned backend, frontend, router and remaining owned workers; verify
   they exited and the configured public ports are free. A PID or port alone
   does not establish ownership. `stop-companion.ps1` by itself does not provide
   the quiescence and lease steps.
4. While the old installation remains stopped, make the final SQLite backups
   and sync the inventoried durable files into the new root. Verify database
   integrity and copied-file identities before launch. Do not rewrite the old
   tree. Exclude old `processes.json`, `companion-runtime.json`, route/control
   records, active-slot/update transactions, lock files, temporary workers and
   source runtime-code slots. Remove stale metadata only from the new root.
5. Launch the installed executable as the original desktop user. Keep its
   status window visible. Confirm startup readiness, the selected game and
   language, preserved transcript/favorites and audio, capture calibration,
   protected account availability and the browser's usual local origin.
   Account validation is read-only. The native gateway retains ports 3000 and
   8766 by default; if the old setup used different options, resolve that
   explicitly before launching. Phones may need to pair again because gateway
   pairing sessions are process-local.
6. Release the old operation lease once the replacement owns the active session
   or rollback is complete. Retain the source installation, final backup and
   native root until acceptance is complete. Do not start the source app beside
   the native host.

Browser preferences survive only when the same browser profile and exact origin
(scheme, hostname and port) are retained. `localhost` and `127.0.0.1` are distinct
origins. Do not copy browser profile files or silently replace local storage.

## Rollback

If preparation fails before the old app is stopped, leave it running. If final
copy or native startup fails, stop the replacement using its authenticated host
control and verify its workers have exited before restarting the untouched
source installation. Keep the failed native root and private diagnostics.

If the native app has already accepted new transcript, favorite or account
changes, its state is newer than the old tree. Preserve a quiescent backup of
that state before rollback and reconcile the changed stores explicitly; never
blindly overwrite it with the pre-handoff backup. Retaining the old installation
does not itself migrate newly written data back to the old schema.

The source updater is a source-to-source path and must not receive a native
payload. Native slot updates likewise require two compatible native layouts;
neither path implements this initial source-to-native transition. The runtime
settings isolation fix is covered by synthetic frozen/source composition tests;
this document does not claim live migration or cross-machine credential portability.
