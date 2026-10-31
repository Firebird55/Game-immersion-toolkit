# Endfield archive runtime

Updated 2026-10-30. The normal runtime now uses owned Python VFS and selected
PCK readers instead of building or launching the historical .NET bridge. Source
and frozen layouts use the same archive operation. The historical compiled
helper experiment does not determine this operation's availability.

The implementation reads VFS schema 3/4/5, validates index CRC and bounds, and
handles ChaCha20 index/file streams, optional locale groups, persistent-to-base
chunk fallback, encrypted AKPK headers, direct WEMs, 64-bit external media IDs
and embedded BNK DIDX/DATA spans. It uses range reads rather than loading an
entire package. Voice IDs still come from the exact authored source hash;
package order and adjacent dialogue never choose a recording. A missing pack
stays unavailable and all four official voice languages remain selectable.

The numerical metadata supplier is
[EndfieldStudio revision 48c40a5](https://github.com/EIHRTeam/EndfieldStudio/tree/48c40a5e6a931b08223384077b74b41b484a540f/AnimeStudio.Endfield).
`backend/endfield_metadata.py` pins exact SHA-256 identities for `Keys.cs`,
`BlockHashes.cs` and `Processors/AkpkCrypto.cs`. Each bounded document is checked
before parsing the required numerical fields. All documents validate before
replacing any private cache entry. They are never imported, compiled, executed
or copied into a release. Neither their numerical values nor game assets are
included in public fixtures. The upstream implementation and its port comments
remain format references; this path does not redistribute that compiled code.

The owned reader uses already pinned NumPy and PyCryptodome. The latter's
[ChaCha20 seek interface](https://www.pycryptodome.org/src/cipher/chacha20)
supports bounded random access from the evidenced initial counter. Their native
files and notices remain part of the ordinary runtime closure. No .NET SDK,
NuGet restore or extra executable is required for this archive operation.

## Validation

Thirty-two new authored binary cases exercise all four voice groups and three
VFS schemas, encrypted range reads, 64-bit IDs, a bank with intervening metadata,
unaligned stream offsets, base fallback, absent packs, corrupt/truncated inputs,
out-of-range media and metadata checksum failure. Existing language/audit and
helper contracts remain covered: 132 passed, one Windows link-privilege case
skipped in the focused run. The old Endfield compiler-refusal tests were replaced
by an actual built-in parsing operation with SDK discovery/process launch set
to fail. NTE and historical REE compiled-helper refusal cases remain applicable.

Private installed-input checks observed:

- All four language manifests plus initial/hotfix groups parse. Chinese has
  35,161 persistent inventory entries; absent English/Japanese/Korean chunk files
  do not manufacture voices from their manifests.
- Initial and hotfix samples match the historical bridge byte-for-byte. A
  Chinese sample from a package over 1.6 GB is selected without loading the whole
  package and has a valid RIFF header. This is extraction evidence, not a new
  claim of playback for absent packs.
- The production language join returns 51,049 Chinese records: 22,639 voiced,
  17,196 verified unvoiced, 185 unknown, 11,025 missing source references and
  four missing locale recordings. Its existing source-hash/locale-guarded
  extraction path returns a 31,494-byte RIFF sample. Preparation took 7.5 seconds
  on this host and did not overwrite the user's prepared snapshot.

These counts reproduce the prior authored-binding audit. Current native output
is private, and no recording, key, installation path or localization table is
published. See the [language/coverage audit](game-audits/endfield.md) for the
remaining cinematic, image-only and unresolved-metadata limitations.

## Remaining delivery work

This removes the compiler and embedded-metadata barrier for selected archives.
The shared voice codec closure, frozen candidate execution, platform-native
capture/audio and final release gates still require their own evidence under
[R19](r19-completion-plan.md) and [desktop delivery](desktop-delivery-completion-plan.md).
Do not infer that the entire frozen candidate is approved from a passing archive
operation, or that uninstalled language packs have been played.
