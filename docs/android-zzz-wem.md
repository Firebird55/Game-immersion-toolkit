# Android ZZZ original WEM decoder

The retained international ZZZ controls use modern little-endian Wwise
Vorbis. A header census covered 57 retained sentence and presentation samples
and seven separately tracked whole-context controls. All 64 inspected files
had format tag `0xffff`, a 66-byte `fmt ` chunk with `cbSize=0x30`, one complete
`data` chunk, and a setup packet ending exactly at the first audio packet.
They contained 53 mono files across 16, 24, 32, 36 and 48 kHz and 11 stereo
files at 44.1 kHz. The seven acquired context controls cover all four dubs
and last about 40.257 seconds each. The other Mandarin control remains
unacquired. This census covers the retained controls.

## Pinned NDK closure

The compiler inputs are the existing reviewed vgmstream r2168, libvorbis
1.3.7 and libogg 1.3.5 archives and their full notices. The linker selects
four vgmstream units for Wwise packet reconstruction and codebooks, Xiph's
Ogg bit reader, 20 libvorbis core units, and the toolkit C adapter. The adapter
uses the original v62-first/v56-retry codebook selection and a memory-only
`STREAMFILE` with no open capability. It checks the modern Wwise layout,
reads bounded packets, and returns original-rate interleaved PCM16. A
decoder error fails the stream instead of padding the clip with silence.
The local link uses the existing authenticated Android NDK 27.3.13750724
and verifies the ELF ABI, 16 KiB alignment, `libc.so` and `libm.so`
dependencies and the export list `zzz_wem_open`, `zzz_wem_read`, `zzz_wem_close`.
The recipe uses the source pins in [audio-runtime.json](../packaging/codecs/audio-runtime.json).

```powershell
python scripts/build-android-zzz-wem.py --suppliers <retained-audio-sources> --ndk <verified-ndk> --ndk-archive <retained-ndk-archive> --output <fresh-private-directory>
```

The bundle records both ABI binaries, their C and JNI exports and
the three complete original notices. The standalone recipe can recheck an
existing bundle with `--verify <bundle-directory>`.

Supply `build-android-app.ps1 -ZzzWemSources <retained-audio-sources>` to
include it in a candidate. The release build requires this input and the pinned
Android catalogue assets. The verified offline wheelhouse includes FlatBuffers
and its original license for reading the publisher's FlexBuffers audio index. The APK audit checks the exact asset and ABI
namespace, the original notices, the actual ELF headers, the native
dependencies, and the manifest hashes. The app's Java decoder checks the
actual installed ABI member before loading it by its exact APK path. The
Python opener attests that Java capability and uses one scoped JNI ticket
per recording. Missing assets, mismatched software and unsupported runtime
identities leave this capability unavailable.

## Recording handoff

`ZzzWavCodec` takes an attested caller-owned PCM stream opener. It reconciles
engine metadata with the authenticated WEM header, accepts up to 64 MiB of
source, requests at most 4,096 frames per read, and checks exact completion
and the 128 MiB WAV limit. It preserves native sample rate, channel count
and frame count for a complete sentence or whole context. A timed cue keeps
the source samples within its authored window. Its 120-second deadline and
cancellation checks run between bounded native calls. Cancellation, decode
failure and incompatible metadata discard the pending file and keep any
previously retained recording. Gain and channel remixes remain unavailable.
The prepared-library recording store and Android reader accept PCM WAV.

The local checks exercise the PCM handoff with authored data and verify that
changed bounds, late failure and cancellation leave existing audio intact.
They also verify the linked Android software in the APK component auditor.
The app uses cooperative cancellation between bounded native calls.
Installed target decode, the PCM comparison on the retained original
controls, and original publisher Audio Ready remain pending.
