# Frontend notice supplements

The notice collector retains complete installed package notices recursively,
including separate vendored-library licenses. It conservatively covers the
production package lock used by both desktop and legacy static browser bundles.
Absent dependencies are excluded only when the lock marks them development-only
or optional with an incompatible operating system, CPU, or libc. The supported
Linux desktop build uses glibc.

`sources.json` binds each supplement to the exact package name, version and npm
tarball integrity, and records the source URL, immutable source commit and actual
notice hash. All files are retained locally; runtime builds do not download
licenses. Source commits were resolved from the exact npm version's `gitHead`
where available, or the supplier's matching version tag (Rolldown, Victory,
Yoga and Unpic Core). The full tr46 author notice was added upstream after the
old locked version, whose original package already declares MIT; that distinction
is recorded explicitly.

Some exact packages supply a MIT declaration and author metadata but omit a full
license file. Their entries preserve that actual declaration and use the
verbatim standard MIT permission, conditions and warranty paragraphs from the
pinned SPDX license-list source. The SPDX template copyright placeholders are
omitted. No new copyright statement is invented, and the collector does not
claim the supplier provided a LICENSE file. `copyright_notice` records the
missing upstream copyright statement. In particular, a later license file from
an unrelated project is never substituted for the missing file.

The Tesseract data packages declare MIT for their npm packaging. Their actual
traineddata retains the separate upstream Apache-2.0 terms, also included here.
The model license is not replaced by npm metadata. Victory's vendored D3/Internmap
licenses and the RSC plugin's vendored React license are collected independently
from their actual installed files.

The frontend build fingerprint includes every consumed notice, package metadata
declaration and supplement pin. Changed, missing or mismatched evidence prevents
silent reuse of a previous build. A full-notice inventory does not establish
which optional native modules were shipped or satisfy independent source/build
obligations for another runtime artifact.
