# R19 authored Source PCM format experiment

Status: **source checks and exact acc68be extracted Windows checkpoint passed**.
Implemented 2026-10-30 as a bounded continuation of the
[unvoiced export experiment](r19-unvoiced-export.md) and
[R19 completion plan](r19-completion-plan.md). This exercises an existing
Portal format path; it adds no game, language, codec or runtime capability.

## PCM validation and publication

The existing Source reader can retain a single original uncompressed PCM WAV
without invoking a media decoder. Python's `wave.getnframes()` trusts the
declared data size: an owned 160-frame WAV truncated by ten bytes still reports
160 frames while only 310 of its declared 320 PCM bytes are readable. The old
fast path copied that damaged container into the output.

The path now checks RIFF length, complete chunk bounds, a single format/data
layout, PCM format fields, frame alignment and the actual readable frame bytes.
Malformed declared PCM never falls through to a source codec, even when one is
available. Valid non-PCM WAVE retains the existing source-codec path. Complete
original mono/stereo PCM and metadata retain their exact bytes; a final odd-byte
data chunk from an original writer remains supported.

Both the unchanged-PCM and existing source-codec paths now write to a private
pending WAV beside the output and publish atomically after validation. Rejected
input, codec failure and validation errors preserve the previous output and
remove the owned publication temporary directory. Existing source-codec scratch
inputs retain their caller-owned lifecycle. No general FFmpeg fallback becomes
available in the frozen runtime.

## Real format and worker chain

`backend/source_pcm_probe.py` creates owned VPK v1 archives containing a
KeyValues sound manifest/event, English/French title sidecars, compiled VCCD v1
caption blocks and distinct original PCM WAVs in the selected locale's voice
archive. The compiled text intentionally differs from the sidecar placeholder,
so the probe checks that VCCD remains authoritative.

The actual `game-index` and `language` child entrypoints prepare the records.
The existing Portal adapter then revalidates the authored event/voice reference,
extracts its VPK member with CRC checking and passes the original performance to
its existing PCM path. Extraction and PCM validation run in the probe process;
there is no new voice-extraction worker or dispatcher operation. The probe
checks both en → fr and fr → en text identities and exact distinct WAV/PCM hashes.

A separate missing-French fixture retains its French text with one unavailable
voice, an actionable voice-pack warning and zero unvoiced rows. It cannot borrow
the English recording. A changed locale binding and a corrupted VPK member CRC
are rejected. A truncated WAV inside a complete performance capsule is rejected
without replacing the previous good output. All authored install trees remain
unchanged. The source regression executes the real workers with an empty PATH
and prohibits external-codec/account initialization in extraction/PCM checks.

## Evidence and limits

Affected Source/Portal/Portal 2/Half-Life 2 checks and the new real-worker probe
pass locally. `runtime_probe` includes the same bounded path and emits sanitized
locale, size/hash and rejection metadata.

The exact extracted checkpoint at `acc68be` passed in
[run 41144087092](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41144087092).
The downloaded [source/metadata review](r19-frozen-checkpoint-20261031.json)
verified both en/fr directions through the actual frozen workers and existing
in-process extraction/PCM adapter, distinct WAV/PCM hashes, missing selected
pack state and binding/CRC/truncation rejection with previous-output retention.
Application inventory and owned cleanup passed. No external codec or installed
game was used; native binaries stayed runner-local and Windows 11 remains open.

This covers one inline VPK v1 member per original PCM recording and one caption
event. Numbered VPK chunks, VPK v2, scenes/composites, MP3, Bink, resampling,
playback and voiced mobile-library conversion require their separate probes.
There is no installed-game, full dialogue-format or full B2/B3 acceptance claim.
General game decoding and private helper redistribution remain rights gates.
Clean ordinary-user Windows 11 OCR/capture/DPI and CRT closure remain unavailable.
Production runtime stays disabled, `r19_complete` stays false, PR #59 is unchanged
and no installer, tag or release is built.
