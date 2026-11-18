# Old browser history and favorites

The hosted gaming page is retired. Its old browser-origin data is not deleted
by this transition. The Android candidate provides an explicit history-only
export/import route; it cannot read another browser's storage automatically.
No released Android delivery or physical mobile-browser acceptance is claimed.

1. Keep the original browser profile and site data. Do not clear its IndexedDB,
   installed offline copy or retained voice libraries.
2. In Android **Library and device → Import old browser history → Export from
   the old browser**, copy the complete export bookmark. On the old device,
   create a bookmark and replace its address with that JavaScript address.
   Open the original toolkit address in the same browser and run the bookmark.
   A normal HTTP 404 page at that origin can still access its existing storage;
   a different origin, cleared profile or browser-internal network error cannot.
   JavaScript bookmark execution is browser-dependent and still needs physical
   mobile verification. Keep the old data if the browser blocks execution.
3. Alternatively, advanced users can run the complete reviewed
   [history-only exporter](../scripts/export-browser-history.js) in developer
   tools at that original origin. It reads only the `history` and `pc-history`
   entries in a read-only transaction. It does not open a vault, account API,
   remembered credentials, stream links, OPFS files or game libraries.
4. Transfer `toolkit-browser-history.json` to Android Files. Select the intended
   local account first. Choose **Browser history backup**, inspect the counts,
   games and study languages, then explicitly **Import history and favorites**.
   Preview does not write history. Re-importing the same backup does not create
   duplicate lines; it may promote a favorite and never clears an existing one.
5. Use **Imported history** in the reader to browse all imported rows in bounded
   pages, including **Imported favorites only**. These archived rows retain their
   original timestamps, text, language and favorite state and are not removed
   by live-capture pruning. An explicitly deleted row stays deleted on replay.

The history export contains no audio files. Earlier known recordings are marked
unavailable on imported lines; unknown recordings stay unknown, and explicit
unvoiced states remain distinct. No newer or nearby recording is substituted.
Browser text excerpts stay labeled as imported excerpts, without a full-text
capture-verification claim. Retain the original voice libraries and re-export a
native prepared library from desktop for subsequent capture/playback.

Reconnect accounts explicitly using Android-protected storage. Set reading
preferences, stream connections and calibration separately in the app; these
values are not silently imported. Existing browser stores remain unchanged.
An interrupted transfer is not a claim of rollback: inspect history and retry
the same backup safely. Imports are account-generation fenced and atomic.

Authored Chromium/Firefox checks exercise real old-origin IndexedDB, the exact
export script, shared React preview/import, both HTTP account services and
302 saved rows, including paging past the live-history limit and the oldest
favorite. Native protection and remote accounts in that test are explicit
desktop mocks. Native Android migration and physical mobile bookmark execution
remain acceptance checks.
