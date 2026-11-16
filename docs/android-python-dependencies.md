# Android shared-core Python dependencies

The Android host uses the maintained Python matching, model and transcript
modules. It does not substitute an Android-only matcher. Python, its native
extensions and the original voice files imported by the user belong inside the
app's private runtime/data; users do not install Python or a compiler.

## Build inputs

`packaging/android/python-dependencies.json` pins the original PyPI sources and
pure wheels, Chaquopy Python **3.12.15-0** target distributions, Rust **1.95.0**,
Android NDK **27.3.13750724**, API **24**, and both **arm64-v8a** and **x86_64**.
The runtime dependency versions equal the desktop pins. The source builder is a
development tool; it is not an Android runtime installer or update mechanism.

The pinned PyPI inventories have no Android wheels for pydantic-core or
RapidFuzz. The builder therefore compiles the original **pydantic-core 2.50.1**
Rust source using its unchanged `Cargo.lock` and the actual target
`libpython3.12.so`. It packages the original Python files and type stubs with the
extension. Original MIT and locked Rust dependency license documents travel in
the wheel. Native ELF checks reject a desktop/wrong-ABI library, wrong Python
dependency, unexpected shared library or a load segment without 16-KiB alignment.

RapidFuzz **3.14.6** already supplies portable Python algorithms. Its official
build backend produces the pure wheel with `wheel.cmake=false`; no new fuzzy
algorithm or compatibility shim is introduced. Exact and fuzzy production
matching still require device performance/identity checks; a cross-build alone
does not establish that a target interpreter loaded the extension.

## Build-host invocation

Use Python 3.12 and the pinned Rust toolchain on the development/build host.
Point `CARGO_HOME`, `RUSTUP_HOME`, `TEMP`, `TMP` and other tool caches at the owned
build directory. Install Rust's `aarch64-linux-android` and
`x86_64-linux-android` standard-library targets. No task cache belongs inside a
user profile or the public source tree.

The currently authenticated NDK supplier archive is the official Windows r27d
ZIP. Extract it into a private SDK's `ndk/27.3.13750724` directory and retain the
archive under the build work directory. The builder compares actual LLVM and
sysroot inputs against that checksum-pinned archive. A Linux build host requires
its own pinned original supplier archive; a matching version label is not
sufficient evidence.

```text
python scripts/build-android-python-dependencies.py \
  --work-dir <private-build-directory> \
  --wheelhouse <private-offline-wheelhouse> \
  --ndk-root <private-sdk>/ndk/27.3.13750724 \
  --download
```

`--download` acquires only the pinned Python/software inputs. NDK and Rust are
explicit build-host prerequisites. Cargo verifies the unchanged locked crate
checksums; it cannot select newer versions. The script verifies the full native
compiler/sysroot archive correspondence, includes original license notices and
emits `python-wheels-receipt.json` without absolute host paths. Subsequent native
builds use `--locked --offline`. The resulting wheelhouse also contains
`requirements-android.lock.txt`; the checked-in equivalent is
`packaging/android/python-requirements.lock.txt`.

## Evidence boundary

The software recipe and owned malformed-ABI/archive/RECORD tests are independent
of game data. Successful compilation proves an Android ELF and package contract,
not Android execution, OCR, audio focus, storage, lifecycle or physical-device
acceptance. The app's instrumentation must load these exact wheels, exercise
the shared modules with identical desktop fixtures, and preserve voice/text
identity through restart before reporting shared-core hosting as passed.

The embedding and target compatibility guidance comes from
[Python's Android documentation](https://docs.python.org/3/using/android.html)
and [Chaquopy's Gradle documentation](https://chaquo.com/chaquopy/doc/current/android.html),
reviewed November 16, 2026. PyPI source files are pinned in the input policy;
the license and source provenance is retained with each built wheel.
