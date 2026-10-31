# Shared managed reader platform builds

Updated 2026-10-31. NTE and Wuthering Waves use the same owned CUE4Parse bridge,
fixed read operations, verified managed dependencies and private output rules.
The apphost and .NET runtime are native to the desktop package's platform.
Neither game's installed bundle compiles code or searches for a system SDK.

| Native build host | Build RID | Resource platform | Apphost |
| --- | --- | --- | --- |
| Windows x64 | `win-x64` | `win-x64` | `NteReader.exe` |
| Linux x64 | `linux-x64` | `linux-x64` | `NteReader` |
| macOS arm64 | `osx-arm64` | `darwin-arm64` | `NteReader` |

`packaging/game-readers/inputs.json` pins SDK 10.0.403, runtime 10.0.14 and the
runtime/apphost NuGet packages separately for each RID. SHA-512 identities come
from Microsoft's [official .NET 10 release metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json)
and the exact NuGet catalog records retained beside each package pin. The SDK
exists only on the build host. Runtime distribution retains the full SDK and
runtime-package license/third-party notices, plus the reader dependency notices.

## Native builder interface

Use `scripts/prepare-game-reader-sdk.py --rid <RID> --output <fresh-directory>
--cache <evidence-directory>` to download, safely expand and verify the selected
pinned SDK archive before execution. Hosted construction passes its verified
paths directly to the helper builder. Its first invocation may create files, so
each independently invoked helper build needs a fresh expansion of the retained
archive.

```powershell
pwsh scripts/build-game-reader-helpers.ps1 `
  -Kind nte -RuntimeIdentifier linux-x64 `
  -OutputRoot output/helper-resources `
  -EvidenceRoot output/helper-build-evidence `
  -Dotnet /absolute/fresh-sdk/dotnet `
  -ExpectedSdkVersion 10.0.403 -Python python3 -BaseRef origin/main
python3 scripts/build-nte-toolchain.py --output output/reader-resources --platform linux-x64
```

Choose the actual PR target remote for `BaseRef`. Paths above are illustrative;
the output directory must be new and the evidence directory must already exist.
Windows uses the expanded `dotnet.exe`; macOS uses `-RuntimeIdentifier osx-arm64`
and collector `--platform darwin-arm64`. `-Kind probe` builds the separate authored
runtime probe with the same native contract. Each build must run on the matching
OS and architecture; cross-compilation does not count as native acceptance.

The helper builder creates `<OutputRoot>/nte`. Pass this directory to the desktop
builder's `--nte-helper-root`. The dependency collector produces a
`toolkit-native-resources-v1` manifest and `toolchains/nte` subtree; pass its output
root to `--resources-root`. The managed supplier bytes and their full notices are
identical across these platforms. The platform tag binds the dependencies to the
matching package; it is not proof of native execution.

Before executing the SDK, `verify-dotnet-sdk.py` verifies the official archive
hash and every expanded SDK file. ZIP and gzip TAR inventories reject links,
special members, path escapes, case aliases, altered files and additional files
or directories. Restore uses only the exact local runtime/apphost package feed.
The receipt binds the source commit, source files, SDK archive and expanded files,
restore lock and every runtime package member. Runtime loading validates that
receipt, the outer package inventory, the apphost architecture and OS-specific
CoreCLR files. POSIX packages must preserve executable permission on the apphost.

## Evidence and remaining limits

Synthetic regression tests cover each native image format and its exact runtime
closure, wrong-platform rejection, SDK archive tampering and isolated process
environments. The installed-file NTE and Wuthering index/voice probes described
in their [NTE](nte-runtime.md) and [Wuthering](wuthering-runtime.md) reports ran on
Windows x64. Linux x64 and macOS arm64 still require hosted apphost execution and
final desktop-package acceptance. No installed-game playback is claimed on those
platforms. This reader build change does not add game executable compatibility.

The self-contained runtime still uses normal OS libraries; Linux distribution
compatibility and macOS signing/executable permissions need validation on the
actual packaged application. Native OCR, media codecs and the desktop host have
their own platform checks. An unavailable helper reports a repairable capability
state without disabling the application's unrelated games or readers.
