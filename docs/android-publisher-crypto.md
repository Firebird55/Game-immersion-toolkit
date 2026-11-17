# Android publisher cryptography: next runtime boundary

Reviewed November 17, 2026 against Android checkpoint `502e82f5`, including the
complete publisher source cohort `d7c7b1f0`. This is an implementation inventory
and bounded next-cohort plan. No additional source archive, APK, crypto binary,
provider capability or target execution has been acquired or established here.
The [64-source/Zstandard checkpoint](android-zstandard.md) remains separate.

## Actual consumer requirements

The primitive is determined by the original source reader, not by a guessed
game-wide encryption scheme. All eight game IDs remain in scope; two metadata
factories in the APK are not the final preparation goal.

| Game | Existing source consumer and actual crypto API | Boundary still outside Android |
| --- | --- | --- |
| ZZZ | `hoyo_dispatch_metadata` eagerly imports `Crypto.PublicKey.RSA` and `Crypto.Cipher.PKCS1_v1_5`; `zzz_native_key_data` constructs and validates original RSA CRT numbers. RSA block decryption uses PKCS#1 v1.5, returning no accepted plaintext on padding failure. | The dispatcher module also eagerly imports Brotli. The original Unity/BLK text reader and its actual codec closure remain separate. No AES bootstrap requirement is inferred from other games. |
| Genshin | The current native-input factory imports Sophon and has no direct cipher import. Later `genshin_hotfix` constructs an original RSA key and decrypts complete PKCS#1 v1.5 blocks. | Original dispatch/bindings and Android BLB preparation remain gated. BLB's original custom tables/round parameters are not replaced by standard AES. |
| Star Rail | No direct PyCryptodome cipher primitive is evidenced in the current Python factory/Star Rail module imports. | Original metadata/table/schema runtime and original audio acquisition still require their own reviewed host. A generic AES capability does not implement that runtime. |
| Endfield | `endfield_vfs.chacha` requires `ChaCha20.new(key=..., nonce=...)`, `seek(64 + offset)` and byte-exact decryption. Current VFS readers supply a 32-byte key and **12-byte nonce**, including independently addressed resource ranges. | The factory's current non-Windows gate, original authentication and XXH3/runtime/source integration remain. Its separate custom timeline transform is not ordinary AES. Audio adds other native codecs and its original source parameters. |
| Wuthering Waves | `_native()` lazily loads `publisher_apk`: DER/SPKI RSA import, SHA-256 digest, PKCS#1 v1.5 signature verification and ASN.1 sequence handling. Later original PAK reading uses AES-ECB; original release-manifest reading uses AES-CBC plus strict PKCS#7 unpadding. | Current `_save` and source-cache writers still have lazy desktop `game_tools` imports to isolate. The unresolved original manifest key/IV, compressed-member reader and original audio codec remain independent gates. The publisher text-table authoring route is Python SQLite/FlatBuffer, not a mandatory managed extractor. |
| Neverness to Everness | Its packaged compatibility stage uses only the standard library. Later `nte_archive_keys`, `nte_archive_metadata` and `nte_publisher_pak` use AES-ECB with original source-bound parameters. | Android's early gate must still refuse the separate managed UE/schema/content reader. Zstandard, AES and a managed Oodle implementation do not by themselves create that host. |
| Reverse: 1999 | No cipher primitive is used by the current metadata-only factory. | Original key/overlay/text/voice preparation is unresolved. Do not invent an AES/RSA requirement from a generic Unity format. |
| Infinity Nikki | No factory is registered yet. Original helpers use AES-256-CBC for launcher configuration; source-selected AES or single-DES, ECB or CBC, with explicit PKCS#7 and HEX/Base64 SDK transport. Native-wrapper and PAK helpers use AES-ECB. SDK signing uses standard-library HMAC-MD5; APK integrity reuses the shared RSA/SHA-256 reader. | Authenticated source acquisition, current overlay/text/binding stages, compressed-member support and the actual factory must still be integrated. |

Plain source hashing, HMAC and strict padding/ASN.1 validation should retain
their existing ownership. Signature verification alone does not authenticate
an arbitrary self-signed APK as the publisher: the original URL, manifest,
complete-stream digest and generation binding remain mandatory.

## Existing Android capabilities

`AccountProtection.java` implements AndroidKeystore AES-256-GCM for account
credentials. Its nonexportable key, aliases, associated data and account root
are separate from publisher inputs. It is not an AES-ECB/CBC resource decoder,
RSA service or generic game-key store, and must not be repurposed.

The current `FrameOcr`/`NativeX64Decoder` bridge offers OCR and the pinned
data-only x64 decoder. It exposes no publisher crypto API. Java's existing
SHA-256 usage is digest verification only. The 64-source package contains
neither PyCryptodome nor a publisher crypto native library.

Android's documented `Cipher` transformations include AES, DES and RSA on the
supported modern versions, and ChaCha20 from API 28. However, the explicit
`ChaCha20ParameterSpec` nonce/counter class was added in **API 35**. Thus a
direct implementation using that class would not cover the existing API 34
test target. Endfield needs efficient positioned ranges, not sequential
discarding of an arbitrarily large prefix. These are platform API facts, not
execution proof. See [Android Cipher](https://developer.android.com/reference/javax/crypto/Cipher)
and [ChaCha20ParameterSpec](https://developer.android.com/reference/javax/crypto/spec/ChaCha20ParameterSpec).

The original current Endfield nonce is the RFC-style 12-byte variant. Do not
silently substitute the 8-byte original ChaCha variant or XChaCha. The upstream
[ChaCha20 API](https://www.pycryptodome.org/src/cipher/chacha20) documents their
different counter/nonce contracts; source readers remain authoritative.

## Pinned Python option and its import boundary

The project pins `pycryptodome==3.24.1`. Its previously inspected primary PyPI
metadata identifies a 4,932,558-byte source archive, SHA-256
`3f9e74444c0ecbec7af232a95d282c74b114d53212ce075ed17b7fd7dca32bb3`.
The archive has not been downloaded for this plan. The existing pinned desktop
package can be inspected read-only, but its Windows binaries cannot enter an
Android artifact. The primary [PyPI source record](https://pypi.org/pypi/pycryptodome/3.24.1/json)
is the acquisition identity, not permission to substitute another version.

This is not a pure-Python wheel. The inspected pinned facade loads native
`_raw_aes`, `_raw_ecb`, `_raw_cbc`, `_raw_des`, `_chacha20`, `_SHA256` and the
`_pkcs1_decode` and `_modexp` helpers; AES also imports `_cpuid_c`. RSA may select
`_IntegerGMP`, `_IntegerCustom`/`_modexp` or a Python integer implementation.
The exact transitive selection must be proved before defining a trimmed wheel.

Two upstream loader behaviors require explicit review rather than a blind copy:

- `Crypto.Math.Numbers` first tries the optional GMP backend. An unreviewed
  system library must not become an implicit Android dependency.
- Without CFFI, `Crypto.Util._raw_api.load_lib` calls `platform.architecture()`
  before using ctypes; its own source notes the subprocess. The target's real
  behavior needs proof. Adding CFFI would itself add a separate native closure.

No global `Crypto` namespace shim, `sys.modules` spoof, environment switch or
unrestricted library search is a valid fix. The supplier's public-domain/BSD
terms and all selected embedded notices must be retained; a full source package
can also contain separately licensed components outside this proposed subset.
See the [upstream license](https://www.pycryptodome.org/src/license).

## Recommended smallest coherent implementation

Prefer one explicit **owned publisher-crypto contract**, injected through the
trusted native host into owned source consumers. Do not impersonate the
PyCryptodome namespace. The desktop implementation can call the existing
locked dependency; Android can use its platform without changing source
bindings, original parameters, padding decisions or transport budgets.

1. Define bounded byte operations for AES-ECB/CBC and single-DES-ECB/CBC with
   `NoPadding`, DER/SPKI RSA/SHA-256 verification, and validated RSA CRT block
   decryption. Preserve the current fail-closed PKCS#1 behavior and exact public
   and private number consistency checks. Unsigned RSA numbers cross the
   Python/Java boundary as bytes or canonical decimal strings, never JS numbers.
2. Use a dedicated private JCA adapter for these standard operations. Reuse
   neither account keys nor WebView interfaces. No source/credential/key data
   belongs in logs, diagnostics, artifact manifests or UI state.
3. For consistent API 34/36 positioned ChaCha, investigate the **existing pinned
   supplier's original small ChaCha C core** plus a narrow owned JNI adapter.
   The inspected facade declares `chacha20_init`, `chacha20_seek`,
   `chacha20_encrypt`, and `chacha20_destroy`; the adapter need expose only the
   actual 32-byte-key/12-byte-nonce positioned operation. Authenticate and inspect
   the original source/header/license closure before committing this selection.
   Do not write a new cipher implementation or assume a C filename/API ABI from
   a different upstream release.
4. Build only the reviewed software for ARM64 and x86_64 with the existing
   authenticated NDK. Bind the exact source, patch-free core, compiler, adapter,
   exported API, needed libraries, hashes and 16-KiB ELF/ZIP alignment. A complete
   PyCryptodome Android wheel is an alternative only after its loader and exact
   import closure are proved; it is not the default large dependency grab.

The next acquisition, if approved, is only the pinned 4.93 MB source archive
for header/license/compile-interface inspection. No new SDK, managed runtime,
game artifact, complete APK build or live account action is needed to decide
this boundary.

## Required tests before advertising the capability

Use authored or public standard vectors against the actual locked desktop
reference. Cover AES/DES ECB/CBC encrypt/decrypt, invalid sizes/IV/padding,
DER/public-key mismatch, valid and invalid RSA signatures, RSA CRT consistency,
invalid v1.5 blocks, and 64-bit/unsigned number preservation. For ChaCha, include
offsets 0/1/63/64/65, large independently addressed offsets, split versus whole
range equality, 12-byte nonce rejection boundaries and counter exhaustion.

Exercise the existing original-source **authored** APK, Nikki SDK/config,
Endfield VFS and NTE encrypted-index fixtures through the same owned consumers,
with external network, subprocesses and unreviewed native loading denied.
Text only must still cause zero optional voice transfers. Cancelling, changing
account/source or deleting a managed cache must preserve the existing leases,
history, favorites and retained original recordings.

Finally load the exact packaged library/API and run the same vectors on actual
Android API 34/36, including an ARM64 target and verified artifact hashes.
Host, compilation and archive checks are separate evidence. Keep the original
reader/source/.NET/BLB/codec gates explicit until their own real implementations
and complete game snapshot acceptance exist.
