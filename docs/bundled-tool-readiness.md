# Shared bundled tool preparation

Updated 2026-10-31. Companion to [R19](r19-completion-plan.md) and the
[shared reader work](shared-reader-completion.md).

The setup flow no longer rejects every voiced game solely because the app is
packaged. It checks the same immutable audio capabilities used by playback and
the particular archive operation required by the adapter. Included Python
readers can prepare as soon as their codec capabilities are present. NTE and Wuthering check
its actual app-local bridge and complete managed dependency inventory. An unrelated
missing reader does not disable another game.

The original-voice decoder and audio converter have separate missing states.
BEYOND and HEAVY RAIN require the converter but do not acquire an unused voice
decoder. Half-Life's explicitly text-only capability does not need either.
Endfield and RE PAK numerical format documents remain private, checksum-verified
data inputs. Status polling does not download them; preparation uses the owned
reader after the native capabilities have been checked.

Wuthering uses the common codec resolver and the same owned managed Unreal
helper as NTE. Its old FModelCLI/native codec acquisition path is removed.
Both indexing and original playback resolve the actual bundled apphost;
private data/cache filenames do not select a separate runtime. See the
[Wuthering production evidence](wuthering-runtime.md).

Cyberpunk still needs its exact WolvenKit and app-local .NET inventory wired
into shared preparation. A filename alone cannot establish that capability.
Packaged calls report the missing archive operation before executable acquisition
or process launch. This implementation gap is not a permanent game-specific
installation policy.

ZZZ still needs its real scene/voice graph reader closure. A synthetic Node
probe does not satisfy that operation. NTE's Windows native chain and supplier
obligations are recorded in its [runtime evidence](nte-runtime.md). Those readers
and the shared codecs must pass full native candidate acceptance before release.

Setup exposes the sanitized preparation error code and its actionable message,
and writes detailed exceptions to the local application log. It no longer replaces
every failure with a general experimental-bundle warning or a command-script
instruction. Source and packaged installs use the same progress and error flow.

Earlier validation: 127 focused preparation, setup, runtime-composition, Wuthering, RE
PAK and Endfield checks passed locally. Fixtures exercise every active game's
readiness branch, prohibit runtime executable acquisition, keep private metadata
separate from native tools and preserve an unrelated working reader when another
capability is missing. These checks are not a substitute for the frozen native
acceptance matrix.
The shared Unreal extension adds private-input, patch-shard, bounded extraction
and production voice-service regressions. Its installed-file evidence and
remaining native-platform checks are recorded in the linked runtime reports.
