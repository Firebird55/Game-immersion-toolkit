# Cyberpunk archive runtime delivery

Reviewed 2026-10-31. Windows x64 candidates can include the same verified archive
reader used by source preparation. The application executes a fixed owned managed
entry through its own .NET runtime; users of an installer do not need .NET or an
SDK installed separately. Indexing and original-voice extraction share this path.

The collector is `scripts/build-cyberpunk-toolchain.py --platform win-x64 --cache
<download-cache> --output <fresh-resources> --sdk-root <build-sdk>`. The build host
needs SDK 10.0.403; it compiles only the owned entry with fixed references, without
NuGet, MSBuild targets or project hooks. Its output must reproduce the pinned hash.
Source development can set `PROXY_TRANSCRIPT_DOTNET_SDK` to the same SDK directory.
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

Run `scripts/probe-native-cyberpunk.py --resources <resources> --output <report>`
on Windows x64. It runs the actual app-local host with an empty PATH, verifies the
managed entry rejects write commands, extracts an authored RED4 archive, exercises
Kraken via the compressed embedded hash tables, and checks that the input and
runtime remain unchanged. It needs neither a game installation nor an SDK. This
probe does not establish complete game-archive/CR2W format coverage.

Remaining work:

- The supplier dependency manifest targets `net10.0/win-x64` and includes native
  Windows ClearScript, SQLite and other libraries. Linux/macOS Cyberpunk reader
  closure is not yet verified; those platforms report unavailable instead of
  searching for a system executable.
- Native retained-source and notice review must cover all supplier third-party
  libraries, including Kraken and other native components. The pinned upstream
  source archive and original included notices are retained, but this is not a
  claim that their complete corresponding-source obligations are satisfied.
- The resource collector and native probe leave redistribution approval pending.
  Production publication still requires the normal shared approval/evidence
  gate. Real installed-game archive and CR2W playback validation remains separate.
