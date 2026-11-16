# Android Windows build supplier paths

The hosted Windows SDK installer deliberately sets `ANDROID_HOME` to an alias
without spaces. Its physical SDK lives under Program Files. Rejecting that alias
before recognizing its installed supplier blocked the candidate after both
native ABIs and the shared frontend had already built.

The app builder resolves **read-only SDK/Python/Java supplier paths** to physical
paths, checks representative tool bytes before/after resolution, then applies
the unchanged no-reparse guard to those physical paths and probes. All owned
wheelhouse, frontend and writable build roots retain their strict no-link rule.
No SDK copy/download or user-profile cache is introduced by this resolution.
PowerShell 7.2 or later provides the bounded filesystem-link resolution API.

The owned regression creates a real Windows junction inside its temporary
workspace, verifies both a root and an ancestor alias, checks identical supplier
bytes and confirms that a writable path under the alias remains rejected. It
uses a junction rather than requiring the local symlink-creation privilege.

The source of the hosted alias is the official
[runner image SDK installer](https://github.com/actions/runner-images/blob/main/images/windows/scripts/build/Install-AndroidSDK.ps1),
reviewed November 17, 2026. A successful path regression is not a substitute for
the hosted complete APK/runtime job.
