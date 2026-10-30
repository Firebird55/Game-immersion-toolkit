# Xiph FLAC 1.5.0 complete source delivery

This directory retains the exact source kit used to build the selected R19
Windows x64 codec. It contains source and build recipes only. It grants no
production-runtime or Windows acceptance and contains no codec executable/DLL.

File: [codec-sources.zip](codec-sources.zip), 1,086,902 bytes, SHA-256
7dc11c7fc0c87c6304b0d09af81d76a4d6229c15ce8590681a74e14ca85d2f6b.
The [selection ledger](../../../docs/r19-codec-replacement.json) records each raw
entry hash, selected binary/notice identity and successful independent rebuild.
Do not regenerate or replace this archive when changing the live repository.
A new codec/configuration/recipe needs a new reviewed source-kit identity.

## Contents and licenses

The archive has exactly five files:

- inputs/flac-1.5.0.tar.xz: the entire original upstream source release, SHA-256
  f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920.
- packaging/codecs/flac-reference.json: exact source/configuration policy.
- scripts/build-reference-codec.ps1 and scripts/reference-codec.py: the complete
  build and verification recipes used for this candidate.
- LICENSE: the toolkit license for those recipes; it does not relicense FLAC.

The original tarball retains all 907 entries, source files, build systems,
copyright headers, AUTHORS, COPYING.GPL, COPYING.LGPL, COPYING.Xiph and
COPYING.FDL. The CLI/UTF-8 support is GPL-2.0-or-later; getopt is
LGPL-2.0-or-later and ReplayGain support is LGPL-2.1-or-later. The selected
reference library uses BSD-3-Clause. Documentation and other original files
retain their own notices. Preserve all of them, including contributor notices
inside files. This is third-party licensed source, not an MIT-only asset.
The build recipes use the custom Firebird55 Attribution License. The
[distribution review](../../../docs/r19-xiph-distribution-review.md) records the
unresolved additional-terms question before future GPLv2 binary/source delivery.

## Verify and rebuild

On a Windows build host with Python 3.12+, CMake and supported MSVC/Windows SDK
tools, verify the SHA-256 above, extract to a fresh directory, then run:

```powershell
Expand-Archive -LiteralPath codec-sources.zip -DestinationPath source-kit
& ./source-kit/scripts/build-reference-codec.ps1 `
  -SourceArchive ./source-kit/inputs/flac-1.5.0.tar.xz `
  -OutputRoot ./fresh-codec-build
```

The delivered scripts are self-contained; they do not need a toolkit checkout.
The source kit was produced on Windows and retains CRLF recipe bytes. Verify
raw hashes before comparing canonical LF text with Git. Successful rebuild and
same-image matching binary hashes are recorded in the selection/integration
dossiers; matching a different future compiler/image is not promised.
Recipient modifications and relinking are permitted under the applicable
licenses. The toolkit's verified experimental resolver intentionally rejects
different binaries; run a modified standalone codec separately. Do not disable
runtime integrity checks to test a recipient's modified build.

## Retention and future binary delivery

Keep this complete archive in retained Git history. Use a commit-pinned source
link when citing it. This copy survives expiry of the seven-day Actions review
artifacts. A PR branch is not proof of protected upstream retention or a
published production source service. Before any future binary download, retain
the source on the canonical release lineage and provide this exact complete
source kit beside that binary with checksums and source directions.
Release only through the clean-main process in RELEASE.md. No release, tag,
repository protection change or installer is created by adding this source copy.
