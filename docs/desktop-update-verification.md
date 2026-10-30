# Immutable desktop update verification

Implemented on 2026-10-30. This is source-level update delivery and rejection
coverage, not a claim that an eligible native release has been published.

The native packager emits a separate `DESKTOP-PROVENANCE-<target>.json` and
`Game-immersion-toolkit-<version>-<target>-runtime.zip` for each target. The ZIP
contains exactly the runtime inventory plus the unchanged `PROVENANCE.json`
receipt. Windows setup, Linux installation and the macOS application wrapper
remain separate installation artifacts. Empty directories and permitted native
links are part of the closed inventory.

`backend.desktop_release.prepare_update` accepts only a stable release from the
canonical repository. It binds the target-specific metadata and runtime ZIP to
GitHub's asset sizes and SHA-256 digests, resolves the release tag to its commit,
and compares the commit, version, build identity, native acceptance and runtime
receipt. Candidate artifacts and historical source-only releases are unavailable
as desktop updates. Unreviewed, mutated or incompatible payloads cannot be
activated through a command-line override.

The current trust boundary is the canonical repository's HTTPS release API and
asset digests. This implementation does **not** verify a Sigstore attestation,
Windows Authenticode signature or macOS notarization ticket. Those are separate
release properties; unsigned releases report that state explicitly. A locally
constructed candidate cannot supply their evidence by changing approval strings.
Target eligibility uses the exact input and native evidence described in
[desktop target acceptance](desktop-target-acceptance.md), independently of the
remaining all-game R19 plan.

The downloaded archive is bounded in compressed size, expanded size and file
count. Extraction rejects traversal, Windows device names and alternate streams,
duplicate names, escaped links, encrypted entries and special files. Every
runtime file, directory, resource and frontend manifest is checked before the
slot is published. Cancellation or failure retains the running application.

Slots live beside the platform settings directory, in a sibling with the suffix
`-runtimes`. They never overlap immutable Program Files resources or the mutable
settings/data/tool/export roots. Verification does not start a process, change
the active pointer or migrate data. The desktop host owns the operation lease,
writer barrier and route switch described in [runtime-writer-handoff.md](runtime-writer-handoff.md).

Successful online verification creates a trust ticket protected by the current
user's DPAPI on Windows, Keychain on macOS or SecretService on Linux. There is no
plaintext fallback. The ticket binds the release identity, target, archive and
receipt hashes and managed slot name. `verify_selected` rechecks the protected
ticket, exact inventory and frontend before offline restart. It does not treat a
saved path or PID as proof of ownership or trust. Host protocol and storage epoch
must both be the supported exact integer `1`; migration requires a separate
implemented protocol.

Regression tests use authored executable headers, temporary release receipts,
mocked HTTPS responses and mocked protected storage. They cover retained data
roots, offline revalidation, byte/directory/ticket tampering, trusted URL/tag/
commit/checksum binding, incompatible epochs, cancellation, failed keychain
protection, archive traversal and bounded download redirects. They do not modify
real accounts or publish releases.

Remaining acceptance:

- Exercise the final frozen archive through the host's complete service switch
  and offline restart with copied synthetic stores on each declared platform.
- Verify protected storage using disposable TEST entries on native macOS/Linux
  acceptance hosts, and Windows DPAPI using a disposable test installation.
- Complete each native release's dependency/source/notice and target evidence,
  explicitly disclose signing/notarization status, then publish receipts and update
  ZIPs together with installation artifacts and verify downloaded checksums.
- Verify installer repair/uninstall and recovery from interrupted downloads,
  full disks, failed activation and retained browser chunks in packaged builds.
