# Common native audio delivery

All packaged games resolve audio tools through the same immutable, hash-checked
resource manifest. Missing tools produce a capability/repair state. Runtime code
does not search developer PATH, install a compiler, or make exceptions by game.

The native construction job builds a small audio-only FFmpeg 9.0.2 executable
against LAME 4.0 from exact source archives. Network support, automatic library
detection, GPL/nonfree features, video scaling and external video codecs are
disabled. PCM, FLAC, original game-audio decoding, MP3 export and the shared
dialogue trimming/mixing filters remain enabled. The unmodified FFmpeg/LAME
archives, exact hashes, selected licenses and build recipe travel with the
resource inventory. The Windows build compiler is an isolated, verified
w64devkit 2.11.0 build-host tool; it is not needed by users.

Windows currently collects the maintained upstream vgmstream r2168 artifact and
its companion DLLs with exact archive checksums, source revision and dependency
notices. Its complete native dependency corresponding-source review remains
open. The current upstream Linux executable includes additional static GPL
dependencies, and the macOS executable refers to Homebrew absolute paths. Those
binaries are not silently relabeled or included as self-contained installers.
Native vgmstream source builds and their dependency source closure remain needed
for Linux and macOS. FFmpeg construction is wired for all three native jobs;
Windows execution evidence does not prove the other jobs have passed.

On 2026-10-30 the Windows source-built FFmpeg passed an authored one-second audio
probe with developer PATH removed: exact lossless FLAC-to-PCM, MP3 encoding and
8 kHz resampling, and dialogue filters. The pinned vgmstream passed exact authored
RIFF decoding. FFmpeg imports only bcrypt, Kernel32, msvcrt and Shell32 from the
operating system; its binary does not embed the local profile/build path. The
probe stores only synthetic test results and binary hashes, never game audio.
These are native codec checks, not complete game playback or R19 acceptance.

Run `scripts/build-audio-runtime.py --help` on a prepared build host, then
`scripts/probe-native-audio.py --resources <output> --output <evidence.json>`.
The resource inventory can be passed to `build-desktop-runtime.py` through
`--resources-root`; this option may be repeated for independently built helpers.
Each complete input manifest is retained in observed build and candidate
provenance, including source/license facts, not only flattened file hashes.

Primary references reviewed on 2026-10-30:
[FFmpeg releases](https://ffmpeg.org/download.html),
[FFmpeg licensing](https://ffmpeg.org/legal.html),
[LAME current release](https://lame.sourceforge.io/download.php),
[vgmstream r2168](https://github.com/vgmstream/vgmstream/releases/tag/r2168),
[w64devkit 2.11.0](https://github.com/skeeto/w64devkit/releases/tag/v2.11.0).
