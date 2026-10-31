# Cyberpunk archive runtime delivery

Reviewed 2026-10-31. Windows x64 candidates can include the same verified archive
reader used by source preparation. The application executes a fixed owned managed
entry through its own .NET runtime; users of an installer do not need .NET or an
SDK installed separately. Indexing and original-voice extraction share this path.

The collector is `scripts/build-cyberpunk-toolchain.py --platform win-x64 --cache
<download-cache> --output <fresh-resources> --sdk-root <build-sdk>
--native-toolchain <w64devkit-directory>`. The build host
needs SDK 10.0.403 and the pinned w64devkit 2.11.0 used by the audio collector.
The SDK compiles only the owned entry with fixed references, without
NuGet, MSBuild targets or project hooks. Its output must reproduce the pinned hash.
Source development can set `PROXY_TRANSCRIPT_DOTNET_SDK` and
`PROXY_TRANSCRIPT_NATIVE_TOOLCHAIN` to those directories.
The installed application never discovers or invokes a compiler.

Inputs are the exact [WolvenKit 9.0.1 release](https://github.com/WolvenKit/WolvenKit/releases/tag/9.0.1)
and [.NET 10.0.14 official runtime metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json).
The supplier ZIP SHA-256, official runtime SHA-256/SHA-512, retained source archive,
owned source and compiled entry hashes are pinned in `backend/cyberpunk_toolchain.py`.
Every installed file and directory is checked, including the outer application
resource inventory. Changing a local marker or regenerating its hashes does not
authorize changed code. Downloads use bounded retries and atomically publish only
verified bytes. Mutable source caches publish a complete versioned slot.

The supplier's usual `Program.Main` calls `Oodle.Load`, which may discover a game
through the registry and load/copy a library through a Windows KnownFolder. The
owned entry bypasses that startup, explicitly disables `UseOodle`, and binds the
Core assembly's native import only to the bundled `kraken.dll`. The retained
supplier source was searched for other calls: `Oodle.Load` occurs only in that
startup path; the registered basic `HookService` does not load script plugins.
Only `unbundle`, serialization-only `cr2w`, help and identity are exposed. Output
stays separate from the immutable runtime and, in packaged apps, inside private
data/work/cache roots. Child ownership is retained through timeout cleanup.

The standalone `ToolkitCyberpunkReader` component is GPL-3.0-or-later; its source
header and `CyberpunkReader.LICENSE` state this explicitly. The toolkit's existing
license is unchanged. The collector retains the upstream top-level GPL terms and
project-level declarations rather than rewriting conflicting supplier metadata.

The fixed operations do not use the supplier's editor, scripting, SQLite, audio
or texture conversions. Those optional managed/native stacks are omitted from
the delivered reader. This removes opaque wwtools, opus-tools, LAME and DirectXTex
copies without reducing the archive/CR2W operations used by the toolkit. Original
voice conversion continues through the toolkit's shared audio runtime.

Kraken is rebuilt from pinned revision
`f75df7ab817d9ffb43ea8ad84a698ad3df9ba4c1`. The retained build adapter applies only
strict MinGW header portability fixes, builds all upstream compression and
decompression sources, disables linker timestamps and checks the exact resulting
DLL hash. It uses no CPU-specific `-march=native` option. The DLL imports only
Windows `KERNEL32.dll` and `msvcrt.dll`; no user compiler or C++ runtime installation
is needed. Its complete upstream source, patch/build recipe, GPL terms, GCC runtime
exception and MinGW runtime notices accompany the resource.

`notices/cyberpunk/components.json` maps every selected DLL/EXE to an exact supplier
archive/member or reproducible owned build. Fifty selected NuGet packages are
pinned in `packaging/cyberpunk/redistribution.json`, with the delivered member
hashes, original package metadata and full upstream terms. The retained WolvenKit
source ZIP contains the five delivered projects, embedded source resources and
root build inputs. Test game samples, the unrelated desktop editor and opaque
copied binaries are excluded by the retained deterministic selection recipe.
The input reviewer verifies the evidence against actual archives and committed
pins; the collector does not grant itself redistribution approval.

Run `scripts/probe-native-cyberpunk.py --resources <resources> --output <report>`
on Windows x64. It runs the actual app-local host with an empty PATH, verifies the
managed entry rejects write commands, extracts an authored RED4 archive, exercises
Kraken via the compressed embedded hash tables, serializes an authored CR2W
localization resource and compares its key and both text variants. Nine checks
also verify that the inputs and runtime remain unchanged. It needs neither a game
installation nor an SDK. This is representative format validation, not a claim
of complete installed-game archive coverage.

Remaining work:

- The supplier dependency manifest targets `net10.0/win-x64`. Linux/macOS Cyberpunk reader
  closure is not yet verified; those platforms report unavailable instead of
  searching for a system executable.
- The resource collector and native probe leave redistribution approval pending.
  Production publication still requires the normal shared approval/evidence
  gate. Real installed-game archive and CR2W playback validation remains separate.
