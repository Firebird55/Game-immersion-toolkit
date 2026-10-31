# Isolated CMake 4.4.5 build-host input

The [shared policy](../packaging/build-tools/cmake-4.4.5-windows-x64.json) pins
Kitware's original Windows x64 ZIP, original SHA-256 list, executable and
selected original notices. The complete ZIP/tree retains every original notice.
Its source-archive reference identifies review material; it is not a rebuilt
source-to-binary proof or complete compiler-supplier approval.

[pinned-build-cmake.py](../scripts/pinned-build-cmake.py) uses the same input for
the isolated FFmpeg and ASR experiments. It downloads and hashes bytes without
executing them. Preparation uses the ZIP without an MSI, installer, registry
change or installed-tool discovery. Native tool payload stays on the build host.
It is excluded from source review/source delivery kits and the product runtime.
The helper and policy retain the project LICENSE; the three-file Xiph FLAC
additional grant and existing FLAC source kits are unchanged.

## Shared API

Run acquisition after the development prerequisite check. On the Windows build
host, select one fresh input directory and one fresh tool container:

```powershell
python -I -B scripts/pinned-build-cmake.py acquire --input-root C:/r19-cmake-inputs
python -I -B scripts/pinned-build-cmake.py prepare --archive C:/r19-cmake-inputs/cmake-4.4.5-windows-x86_64.zip --output C:/r19-build-tools/cmake-4.4.5
python -I -B scripts/pinned-build-cmake.py verify --root C:/r19-build-tools/cmake-4.4.5
```

Every command must return zero before the next step. CLI output is safe summary
metadata, without absolute host paths, native output or raw error text. The
caller knows its tool root and uses the single executable at
`<root>/cmake-4.4.5-windows-x86_64/bin/cmake.exe`. There is no PATH,
ProgramFiles, Strawberry, download-latest or alternate-version fallback.

The container holds the complete upstream tree, original unmodified ZIP under
`inputs/cmake-4.4.5-windows-x86_64.zip`, and `PINNED-CMAKE.json`. Acquisition also
retains the original SHA-256 list in its input directory. Static verification
checks every archive member's CRC/hash, bounds, selected executable/notices and
all prepared files and directories. Traversal, duplicate/case aliases, Windows
reserved names, symlinks/reparse points, oversized entries and extra empty
directories fail. Existing output is preserved. Receipt changes cannot approve
different bytes: verification derives the expected tree from the pinned ZIP.

Python callers can import the helper and call `verify(root)` for its safe
summary dictionary. `payload_root(root)` constructs the upstream payload path;
it does not verify it. Verify before the first native invocation and after all
build work, and include the policy/helper in the experiment's recipe identity.
Portable unit functions use authored invalid-PE fixtures; real CLI preparation
requires Windows. Local archive inspection is static and does not expand or
execute the Windows payload.

This is a build input receipt, not codec, model, game, frozen runtime or Windows
11 acceptance. Rights/source-delivery approval, production execution, runtime
collection and R19 completion remain false. The original ZIP is retained only
in the isolated tool container and is never copied into a source-review ZIP.
