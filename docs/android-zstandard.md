# Android Zstandard software cohort

The standalone recipe in `packaging/android/zstandard-native.json` builds the
unmodified Zstandard 0.25.0 Python C backend for Android CPython 3.12.15, ARM64
and x86_64. The original 711,513-byte source archive is pinned by SHA-256
`7713e1179d162cf5c7906da876ec2ccb9c3a9dcbdffef0cc7f70c3667a205f0b`.
The existing authenticated NDK 27.3.13750724 and CPython target archives supply
the compiler, headers and `libpython3.12.so`. No additional SDK, Rust, CFFI,
system Zstandard library or relabeled desktop wheel is used.

`scripts/build-android-zstandard.py` compiles the upstream single C translation
unit with its bundled Zstandard source. Linking rejects unresolved references;
the actual ELF files must have the expected ABI, 16-KiB load alignment and only
Android libc/libm/libdl plus the exact Python runtime as dependencies. The actual
`PyInit_backend_c` export is checked. Separate Android wheels and a source/NDK/
CPython/native-hash receipt are written to the requested private workspace; the
existing core wheelhouse is untouched.

The closed wheels contain the original Python facade, native backend and all
original wrapper/Zstandard license documents, the complete pythoncapi-compat
0BSD header notice, and original embedded copyright blocks from the upstream
amalgamation. Their actual bytes and inventories are rechecked before the
receipt is published. This is licensed toolkit software, never game code.

The authored vectors cover known and unknown frame sizes, exact output hashes,
short output bounds, truncated/corrupt frames, trailing/concatenated frames and
a rejected window size. They use no original game content. In the pinned C
backend, `max_window_size` is passed to `ZSTD_DCtx_setMaxWindowSize` in **bytes**.
`frame_content_size` returns signed `-1` for an unknown size even though the
separate `CONTENTSIZE_UNKNOWN` constant is unsigned `UINT64_MAX`.
An output bound alone does not validate a known advertised size: consumers must
also retain their independent declared-size, window, complete-frame and hash
checks. Correcting the unit does not authorize removing the expanded-size cap.

Successful host reference vectors, native compilation and wheel/ELF audits do
not establish Android import or decompression execution. This cohort has not
been incorporated into the earlier physical 54-module APK or a new publisher
APK. A later coherent APK must verify the actual native module, its version,
backend and fixture results on the Android targets. Sophon import isolation,
remaining crypto/managed/codec runtimes and full game preparation are separate
work; this dependency alone enables no game to report Ready.
