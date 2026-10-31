# Exact desktop input review

`scripts/review-desktop-inputs.py` inspects an immutable candidate and produces
the input report consumed by `scripts/accept-desktop-runtime.py`. It does not
edit the payload, download dependencies, accept an approval flag, or perform
native execution acceptance. Run it using the prepared build interpreter after
the desktop bundle has been built:

```text
python -I scripts/review-desktop-inputs.py --runtime-root output/candidate/runtime/GameImmersionToolkit --provenance output/candidate/CANDIDATE-PROVENANCE.json --observed-inputs output/candidate/OBSERVED-INPUTS.json --python-archive output/cache/pinned-python.tar.gz --wheelhouse output/wheels --target windows-x64 --output output/input-review.json
```

Use the corresponding `linux-x64` or `macos-arm64` target on those hosts. Supply
each additional supplier archive with `--native-archive path`: for example the
pinned Node archive, Windows vgmstream ZIP and the owned reader's .NET runtime
NuGet packages. SHA-256, SHA-512 or NuGet base64 SHA-512 identities must occur in
the exact source snapshot. An arbitrary adjacent archive cannot establish a
binary's origin. `--source-root` identifies the checkout containing the review
policy, Git history and prepared locked frontend dependencies. `--node` selects
that build host's Node executable; neither option is a user prerequisite.

The output must be new and outside the candidate. Exit 0 means the six input
checks passed, 2 means the report contains concrete blockers, and 1 means the
candidate/evidence could not be inspected. The report binds the source commit,
build ID, target, provenance hash and exact file/directory inventory. It includes
the review script hash, observed-input hash and native binary origins, without
host profile paths. Preserve this report with the native probe reports.

The checks verify:

- The actual pinned Python archive, recorded installed supplier files, build
  executable and selected frozen Python library.
- The target's source-controlled dependency locks and actual wheel archive
  hashes, metadata and complete RECORD contents. Nested vendored metadata is
  distinct from the enclosing wheel's own RECORD.
- Every native resource receipt against delivered bytes; matching supplier
  members or explicitly identified owned source builds. The Windows prebuilt
  vgmstream DLLs must match their supplier ZIP; an adjacent FFmpeg build recipe
  cannot approve them. Owned reader source and closed runtime receipts are
  checked separately from its unmodified managed dependency supplier.
- Full wheel notices, including `LICENCE`, declared copyright/author files,
  and pinned source-only notices. A short metadata license name is insufficient
  when its full terms are absent. A supplier's express MIT declaration may be
  resolved by separately attributed standard permission/warranty terms; this
  does not invent a copyright holder or claim an absent supplier LICENSE file.
- Actual retained sources and notices for the known Qt, GEOS, OCR, ASR and
  codec dependencies. Default Sherpa TTS dependencies retain their full GPL
  source/license texts. GPL presence itself is not a failed check. Source
  archives alone do not prove unknown supplier patches; the optional Qt Mesa
  renderer needs that correspondence if selected in the payload.
- The actual frontend notice text against the complete locked production
  dependency closure, nested notices, exact supplements and font license.
  Absent optional incompatible packages and absent development packages are
  explicitly identified. License text in a build folder does not count unless
  retained in the delivered frontend.

These checks establish the stated evidence, not a legal certification or an
independent reproduction of compiled outputs. Changed Mach-O load commands or
other native post-processing need an explicit verification adapter if the output
does not match an inspected supplier member. An unmapped native file remains a
named blocker. New toolchain correspondence adapters must inspect their actual
source/notice bytes; they cannot inherit another toolchain's approval.

The separate native reports still need to prove the installed target's startup,
browser navigation, status window, tray, crash recovery and shutdown. The accepted
receipt may mark a target distributable while the broader R19 plan remains open.
