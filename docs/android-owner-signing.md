# Owner-host Android candidate signing

The ordinary hosted `debug` candidate uses a separate application ID ending in
`.debug` and its test key. A durable owner candidate uses the base application ID
and a reusable host-protected signer. No release is created by either build.

Initialize the owner identity once on the Windows owner host, outside the source
checkout. Use a private disk location under the host's workspace policy:

```powershell
pwsh scripts/initialize-android-signing.ps1 -IdentityRoot <private-identity> -JavaHome <jdk>
```

The initializer refuses an existing directory. It creates a 3072-bit RSA PKCS12
key, protects its random password with Windows CurrentUser DPAPI, and restricts
the directory and inherited files to the current owner and SYSTEM. The public
certificate digest and reserved version counter stay in the protected identity
record. Neither the private key nor its password belongs in source, exported
libraries, workflow secrets or hosted build caches. Only APKs, public provenance
and audits are candidate-transfer artifacts; never upload the identity or the
owner build workspace. DPAPI recovery depends on the owner's protected Windows
profile; the initializer does not export credentials or silently rotate keys.

Build an owner candidate using the same SDK, verified offline wheelhouse and
shared frontend arguments as the ordinary Android build, including the mandatory
`-NdkArchive`, `-PublisherCryptoSourceArchive` and either `-DecoderSourceArchive`
or `-DownloadDecoderSource`. The publisher crypto source must be the authenticated
original archive pinned by [its native recipe](android-publisher-crypto.md):

```powershell
pwsh scripts/build-android-app.ps1 <build-arguments> -Variant ownerCandidate `
  -SigningIdentityRoot <private-identity> -VersionCode <increasing-integer>
```

The owner variant is explicitly rejected inside GitHub Actions. Its version
code must exceed every previous reserved version, including failed builds; gaps
are allowed. An exclusive host lock protects simultaneous builds. The builder
checks file ownership/ACLs, protected password, actual APK certificate, actual
application ID and actual version. It stops its Gradle daemon before clearing
temporary password environment variables. Public provenance records
`application_id`, `version_code`, `variant` and `signing_certificate_sha256`.

`ownerCandidate` remains debuggable for authored emulator acceptance. Its base
application ID and signer can be reused by a later nondebuggable `release`
variant with a higher version code. Native self-test intent handling and WebView
debugging remain guarded by `BuildConfig.DEBUG`; they are absent from release
behavior. A successful signed build establishes update identity, while an actual
Android install followed by `adb install -r` and retained history/preferences
establishes update-in-place acceptance. No production or physical-device
acceptance follows from the build alone.
