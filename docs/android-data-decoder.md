# Android original-data decoder

The application packages Capstone 5.0.7 as software, compiled for Android
`arm64-v8a` and `x86_64`. It disassembles original x64 client bytes as data.
It never loads or executes a game binary. This dependency alone does not make
any game's complete preparation, key derivation or audio pipeline available.

`packaging/android/native-decoders.json` pins the original PyPI source archive,
its size and SHA-256, the fixed x86 C translation units and Android NDK revision.
`scripts/build-android-data-decoders.py` verifies the compiler and sysroot against
the original pinned NDK archive before compiling the owned JNI transport. No
Python Capstone wheel, environment library path or system Capstone is used on
Android. The existing Windows wheel, DLL and notice hash gate remains separate.

The build emits both ABI libraries, a software receipt, and all three original
Capstone package/core/LLVM license notices. Those notices are included unchanged
under `assets/native-decoder-licenses/` in the APK. The notices originate from
the authenticated archive, not reconstructed license summaries.

The APK audit checks both native entries, ELF machine type, 16-KiB load and ZIP
alignment, exact library hashes, the complete license inventory and the current
owned transport recipe. At runtime the Java loader verifies the exact stored
entry in its own signed APK, then loads that explicit entry. It has no system
or downloaded-library fallback. Python enables the provider only after the
actual Java object and all fifteen authored CAPI fixtures agree with the pinned
Windows reference. Operand widths/access, signed 64-bit immediates/displacements,
unsigned addresses above 2^53 and 2^63, register names, register accesses and
instruction groups are compared without passing numbers through JavaScript.

Host reference tests, ELF/archive checks and standalone C probes are distinct
from running this path in an Android APK. The normal authored Android runtime
probe requires the APK-specific decoder receipt and the full exact CAPI proof
both before and after the same-signer update. No game code or provider payload
is written to that report.

For a private build, supply the existing SDK, verified Python wheelhouse, shared
reader frontend, Python/Java programs, original NDK archive and pinned decoder
source archive to `scripts/build-android-app.ps1`. Its `-NdkArchive` and
`-DecoderSourceArchive` inputs keep those source transfers explicit; a developer
may opt into the pinned source download with `-DownloadDecoderSource`. An
existing Gradle cache may be selected with `-GradleUserHome`. Production signing
keys remain on the protected owner host and are not workflow inputs.
