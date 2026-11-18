# Publisher hash runtime boundary

This component supplies only unseeded XXH3-64 for original Endfield directory
derivation. Inputs are inert bytes, at most 4096 bytes. The complete unsigned
result crosses JNI as exactly sixteen lowercase hexadecimal characters, then
becomes a Python integer. No original client code, account key, environment
library path, or Python `xxhash` replacement is used.

The supplier is the existing desktop pin, [python-xxhash 4.1.0](https://pypi.org/project/xxhash/4.1.0/),
with its bundled xxHash 0.8.4 header. The recipe pins the whole original archive,
the selected header, and both complete BSD notices. The builder extracts only
those three members into private build output. Supplier source is not vendored
into the repository, and no Python extension is installed.

`scripts/build-android-publisher-hash.py` accepts the already acquired archive,
the existing NDK 27.3.13750724, its authenticated original archive, and a private
output directory. It produces arm64-v8a and x86_64 libraries, checks the existing
ELF policy with 16-KiB load alignment, permits only libc, and checks the exact
three owned exports. The generated bundle retains licenses, source and compiler
identities, software hashes, and a manifest. It performs no network acquisition,
APK construction, or target execution.

The Java loader accepts only its manifest, notices, ABI, and exact stored signed
APK library entry. There is no system-library fallback. The Python consumer
requires the actual maintained Java class and verified proof. Endfield's default
Windows version, native-member hash, and notice checks remain unchanged;
`hash64(data, hashing=...)` is an explicit additional consumer seam.

The existing VFS parser accepts an optional maintained publisher-crypto object
on `chacha`, `parse_index`, and `PackageSource`. Every range begins at the original
stream position `64 + offset`. Existing 96-MiB text-index support is partitioned
into primitive calls of at most 64 MiB; the cipher limit is not widened. Invalid
offsets, nonce/key sizes, counter wrap, and unknown providers fail closed. The
default desktop implementation remains the pinned original supplier.

The 47 authored vectors cover short/long input boundaries, empty input, UTF-8,
and unsigned results above 2^63 using the verified desktop software reference.
`android_publisher_hash.authored_probe` also requires native rejection of null
and oversized inputs. A desktop Java-class simulation is not Android/JNI proof.

This library is deliberately not added to the APK bundle policy, Gradle native
inputs, or production Endfield provider in this checkpoint. Compilation, Java
typechecking, source tests, and software-reference parity establish neither
APK/JNI acceptance nor independent Endfield preparation. Reviewed packaging and
actual target execution must precede that claim. Original source acquisition,
master parameters, NumPy-dependent audio transforms, and audio codecs retain
their separate gates. The existing game support matrix is not expanded.
