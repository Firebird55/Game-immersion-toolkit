# Portable original APK signature verification

The shared passive APK-v2 reader accepts keyword-only `crypto=None` in
`signing_metadata`, `ApkLayout.validate` and `verify_stream`. An Android source
factory passes its explicit verified `PublisherCrypto` capability. The desktop
compatibility default imports the locked reference only when verifying an
actual signature. Provider objects are never stored in layouts or restore
handles, and no global Crypto shim or environment-selected provider is used.

Certificate/SPKI extraction is bounded pure-data DER parsing. It requires exact
container boundaries, canonical definite lengths, positive canonical RSA
integers and the same SPKI in the certificate and APK signer. The evidenced
profile permits RSA/PKCS1-SHA256, 2048–4096-bit APK keys, bounded odd public
exponents and exact signature lengths. It rejects unsupported algorithms,
attributes and signature schemes. Cryptographic verification must return the
literal `True` before any whole-carrier stream read. APK certificate identity
alone is not proof that a self-signed key belongs to the publisher.

Whole-original content/chunk digests, cached metadata equality, exact selected
member boundaries, EOF and full signed-data verification are unchanged. The
four-zero-byte source dialect remains opt-in and fully covered by the signature.
Failure does not establish a package-format change or authorize a key fallback.

Authored host checks cover strict DER, v1/v3 certificate envelopes, mismatched
SPKI, weak-key rejection, signature rejection before stream I/O, complete stream
digests and explicit capability propagation in a fresh process that denies all
Crypto/Java imports. The latter uses a clearly authored verifier, not a claim of
Android cryptographic execution. The separate actual host JCA/reference tests
exercise the explicit primitives. Android APK/JNI loading and original-source
replays require their own exact artifact receipts.
