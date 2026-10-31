# R19 static PE/CLR image review

Status: implemented authored-byte contracts; collector integration and actual
frozen Windows execution remain pending. This adds no runtime capability,
installer, supplier approval or change to PR #59.

## Boundary and API

[native_images.py](../packaging/runtime-bundle/native_images.py) provides
`inspect_pe(data)` and
`review_native_images(inventory, inventory_path, application_root)`. The latter
consumes the existing complete final inventory. It does not enumerate a second
output tree, discover a tool, load an image, resolve a dependency or write a
report. The integrator may write a separate quarantined observation only after
the complete call returns. No collector/spec/workflow is changed by this slice.

The manifest's complete raw JSON, duplicate keys, fixed experimental identity,
all file/directory names, case aliases, entry sizes/hashes, totals and parent
relationships are checked before selecting a native file. Each selected image
is bound to its existing file identity before and after parsing. The inventory
is rechecked after all files. The existing A2 `native_path` and
`native_file_identity` enforce raw ancestor/reparse rejection and stable file
identity. There is no fallback to PATH, an SDK, another installation, a game DLL
or proprietary OCR files.

The resulting `proxy-r19-native-images-v1` observation binds source commit,
build ID and exact inventory bytes/SHA-256. Its files retain the original
path/bytes/hash plus static PE/CLR evidence. `tree=main/asr` identifies the
packaged directory tree, not proof of which process loads a helper DLL. The
two fixed PyInstaller entry images must be native AMD64 executables. Other
selected images may be AMD64 or declared IL-only AnyCPU; no implicit x86 helper
exception is introduced. Future intentionally separate x86 tools need their own
reviewed policy instead of weakening this x64 cohort.

## Original format inspection

This is an original standard-based implementation. Existing ASR/game-codec
parsers were inventoried, but no code was copied from or changed in
`scripts/reference-codec.py`, which has its own additional GPL route. It imports
only the Python standard library plus the existing project guard modules.

Primary format references, read on 2026-10-31:

- [Microsoft PE/COFF format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format): DOS/COFF/optional headers, section mapping, import and delay-import directories.
- [Microsoft CorFlags tool](https://learn.microsoft.com/en-us/dotnet/framework/tools/corflags-exe-corflags-conversion-tool): IL-only, required/preferred 32-bit behavior and DLL limitations.
- [Microsoft .NET 10.0.0 CLR header definitions](https://github.com/dotnet/runtime/blob/v10.0.0/src/coreclr/inc/corhdr.h): CLR directory/header layout, native entrypoint interpretation and the paired required/preferred flags.

The parser distinguishes PE32/PE32+, I386/AMD64/ARM64, DLL/executable,
native/managed IL/managed-native, and separate normal/delay module imports.
Overlapping virtual/raw sections, truncated tables, unbacked name RVAs,
unterminated/aliased module names, reserved delay attributes and malformed CLR
headers are refused with fixed safe codes. Old delay descriptors use VAs; modern
ones use RVAs. Writable IAT/module-handle storage may be virtual, while names,
lookup metadata and parsed header payloads must be file-backed.

CLR classification requires the bounded directory, supported 72-byte header,
metadata range/signature/version-string bounds and interpreted entry token/RVA.
Required/preferred bits are a pair: `00` ordinary, `10` x86-required, `11`
platform-neutral but 32-bit-preferred, and `01` reserved. A managed-native header
or native fixup/entry hints prevents an AnyCPU classification. Merely seeing
I386 does not reject an otherwise declared IL-only AnyCPU library. The current
x64 cohort refuses x86-required/preferred images rather than using that flag as
permission to start another runtime.

The bounds are 512 MiB per selected image, 8 GiB selected bytes, 20,000 native
files, 96 sections, 512 descriptors per import table, 255-byte module names,
4 MiB import-directory spans, 4 KiB CLR-directory spans and 32 MiB metadata.
The raw inventory is at most 16 MiB with 100,000 file/directory entries each.
Exceeding a bound fails; no truncated observation is presented as complete.
Errors never interpolate a private path, import spelling, raw PE data or native
exception. Successful module-name fields accept portable ASCII basenames only.

## What remains unverified

AnyCPU is a CLR-header observation, not proof of native P/Invoke compatibility.
This is not full IL/metadata verification, import-symbol/ABI resolution, Windows
loader emulation, API-set resolution, delay-load success, CPU instruction/CRT
compatibility, dynamic LoadLibrary observation, signing or incorporated-code
attribution. Module names do not confer an OS/supplier role or permission to
copy a DLL. Runtime load origins still need the independent native probes.

All observation gates stay `observed-not-approved`, rights pending, native
closure unverified, production/source-delivery false and Windows 11/R19
acceptance unavailable. Authored structural PE fixtures exercise the parser
and real temporary file bindings without executing a native image. Actual
collected images and downloaded evidence still require independent review.

One additional static compatibility observation used the already cached exact
CMake 4.4.5 Windows x64 ZIP. Archive SHA-256
326c826486d46a23cf9d5a1c9ee3a567d427bdd02c4a34071937a2a675cff004
and its cmake.exe member SHA-256
84935c0b7cb09c140de0d3b042d4e93e5fac4e6371e75bf28eae3d841f79dfb3
matched the existing [build-only pin](../packaging/build-tools/cmake-4.4.5-windows-x64.json).
`ZipFile.read` supplied its original bytes directly to the parser: AMD64,
PE32+, native, 13 normal imports and zero delay imports. No Windows file was
extracted or executed. CMake remains build-only; this is parser compatibility,
not runtime collection, rights, loader or Windows acceptance evidence.
