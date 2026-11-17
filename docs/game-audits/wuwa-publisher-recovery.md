# Wuthering Waves publisher metadata recovery

## November 16, 2026 · Verified-input retention

Normal publisher discovery previously needed both the mutable archive-parameter
endpoint and the pinned catalogue-format source again in a fresh process. A
working prior preparation alone did not preserve those inputs. The toolkit now
retains them in the selected tool cache using the desktop user's protected
storage, without writing account settings or publishing plaintext parameters.

An archive parameter enters this recovery state only after the actual original
PAK's complete main index and directory both pass their SHA-1 checks. A mount
prefix or a candidate from the public feed alone cannot authorize retention.
Preparation still checks fresh candidates when the provider is reachable and
combines them with the validated retained set. During a provider outage, retained
parameters can read packages using the same parameters. A missing/invalid host
envelope cannot authorize anything; with no retained parameter, preparation
reports an actionable metadata failure and keeps prior data.

The catalogue-format source is retained only when its complete bytes match the
existing fixed SHA-256 software pin. Both inputs stay bound to the selected tool
cache, including separate regional caches. Another host/user cannot silently
reuse a protected envelope. Concurrent readers retain validated inputs under a
process lock, and interrupted writes preserve the previous protected file.
Failure to retain optional recovery state never discards a prepared index.

### Real ordinary-worker evidence

The current Global core 3.8.11 English preparation was run through the ordinary
language worker with no game installation, current publisher discovery, frozen
previously recorded third-party metadata and authenticated original source
caches. The complete 144,022 records remained identical to the prior verified
preparation. Fifteen distinct archive parameters were retained after native
package validation; the pinned format source was also retained.

A new Python process then ran the same ordinary worker with **both third-party
endpoints deliberately unavailable**. It followed the publisher launcher,
bootstrap and resource manifests normally. The resulting complete payload was
identical to the first process's payload, including all source references,
translations, audio states and inventory fields. Both workers took about 63
seconds and fetched 189,074 bytes in 714 original package ranges each. Cached
original assets were reused; this is not a cold-download proof. Synthetic tests
also cover an untried incorrect candidate, a matching mount prefix with corrupt
index bytes, another cache scope, corrupted protection, a pinned source change
and interrupted retention.

This proves recovery for the observed Global English source and parameters.
Other language/regional recovery has not been claimed from this single run.
Original single/batch/offline playback evidence remains separate in
[the music audit](wuwa-music-subtitles.md).

### Independent key derivation remains open

Retaining a previously verified parameter does **not** derive an unknown rotated
parameter. A new key is not classified as a new package format merely because
its value differs. A first preparation still needs usable candidates, and the
frozen two-generation changed-content acceptance remains open. An encrypted
original that cannot be opened with available parameters reports a distinct
`archive_parameters_missing` state, rather than asserting a package-format change.

A bounded passive inspection acquired the original Global 3.8.0
`Client-Win64-ShippingBase.dll` (38,673,736 bytes), verified its publisher MD5,
and inspected the official Shipping executable's complete second download chunk
(61,402,632 bytes) after verifying that chunk's publisher MD5. No client code was
loaded or executed. The separate 64-KiB PE header probe is not covered by that
second chunk and is not claimed as full-file authentication. The executable's
remaining first 100 MiB was not downloaded.

The inspected data did not contain any of the 525 frozen candidate parameters
as contiguous raw, hexadecimal or UTF-16 hexadecimal values. Original UTF-16
Kuro configuration markers were present. The inspected executable-code windows
had high entropy, and most of the DLL was in a separate protected section. These
are bounded negative findings, not proof that static derivation is impossible
or that the package format changed. The original consumer/assembly rule still
needs to be established before claiming autonomous unknown-key updates.

### Two-generation evidence boundary

Authentic retained catalogues include Global 3.7.19 and 3.8.9/10/11 plus mainland
3.8.9/10. The November 9 research also retained decoded launcher, bootstrap and
platform JSON for the earlier Global source. Decoded retained objects are not
claimed as byte-identical historical wire receipts.

The 3.8.10-to-3.8.11 changed packages examined contain scripts and database
updates, without audio members. The 3.8.9-to-3.8.10 inventory includes additional
ambient banks and one new common WEM; the 79 original WEMs shared by the two
examined audio packages retained their authored member checksums. This does not
prove changed subtitled speech. Non-subtitled ambience is not an acceptance
requirement. The remaining proof must select actual changed/added subtitles,
translations and their associated original audio through authentic version
roots, with unchanged tooling and third-party inputs.

Sources: [Global publisher launcher](https://prod-alicdn-gamestarter.kurogame.com/launcher/game/50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json),
[mainland publisher launcher](https://prod-volcdn-gamestarter.kurogame.xyz/launcher/game/10003_oLNgHF1CESo51DGHN2odtp40e3oI1HfZ/G152/official/index.json),
[pinned catalogue format software](https://github.com/Yumeo0/mornye-tools/blob/4591ef24949688ec9835bf910a204d6bbc4b339c/src-tauri/crates/game-client/src/discovery.rs),
and [archive metadata provider](https://github.com/yarik0chka/wuwa-keys).
