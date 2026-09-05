# Original Mandarin voice playback

The companion can use the installed game's original Mandarin audio instead of
estimating recording boundaries. It never writes to the game, injects code,
reads game memory, or opens Story Recap.

## Exact mapping, not text similarity

1. Read the resource catalog and GalScript Perform bundles.
2. Pair `dialogueKey` with `externalVoiceKey`/`voiceKey` in the same dialogue node.
3. Combine that source leaf with the matching speaker prefixes from VoiceData.
4. Verify the complete Mandarin path against the 64-bit FNV-1 ID in the local PCK.
5. Accept only one unambiguous asset per TextMap ID.

There is deliberately no matching by approximate sentence text or speaker-local
line numbers. A short phrase repeated by another character is not interchangeable.

Some recap and comic voices deliberately have no source filename in the shipped
metadata. For those assets, the companion builds a compact acoustic landmark
index from unmapped Mandarin story packages. The first loopback clip is used only
as a recognition probe. A match is accepted only with a large landmark margin and
independent waveform verification; the transcript audio is then replaced by the
isolated local WEM. The verified TextMap-to-WEM alias is checksummed in
`learned-manifest.json`, so later occurrences use the game file immediately.

The initial local index resolved 25,511 lines, including 49 of a snapshot of the
last 50 transcript entries. This is not coverage of every game dialogue type.
Nanson's `Side_GalGame_ZenkovS1_100100007_011` resolves to
`GalGame_ZenkovS1_Nanson_100100007_001`, hash `c115aa5da661096e`, and decodes
to 570,816 samples at 48 kHz (11.892 seconds).

## Runtime

`data/voice-assets/manifest.json` holds the exact mappings and package size/mtime
fingerprints. Each requested clip is read directly from its PCK offset and decoded
by `data/voice-assets/vgmstream/vgmstream-cli.exe`, then encoded by ffmpeg.
Only small tables and requested clips are read, not whole multi-GB voice packs.
One background worker and a bounded queue keep this off the OCR thread.

The original clip is not VAD-trimmed: its own beginning and end are retained.
Recording remains available until extraction succeeds. A late recording callback
cannot delete or replace an original. Originals use per-transcript-row files in
`data/audio`, so the existing 50-line retention and favorites rules still apply.
The current-line button identifies original audio; all playback uses the same API.

If a package has changed, fingerprint evidence is ambiguous, or decoding fails,
recording is used instead. The background story indexer detects package changes
and refreshes automatically while capture continues; stale offsets are never
used. This does not fix OCR lines that were never recognized, and video cutscenes
with audio embedded in video are not covered by the external-WEM index.

## Local rebuild

The initial read-only extraction helper and downloaded resources are retained in
`work/voice-assets`. The helper `scripts/extract_voice_links.mjs` uses the upstream
[GalScript reader](https://github.com/simon300000/zenless-voice/blob/bb2b9790d2d45a5c662c36cd9f046d05893d0ef4/galgame-perform.ts)
with `ooz-wasm` and `xxhash-wasm`. It reads the installed resource catalog and
the blocks containing the selected Zenkov Perform assets (those shared blocks
also contain many other scenes). It writes `scene-links.json` in that scratch
folder, not in the game. The independent local PCK reader is in
`backend/voice_assets.py`.

After regenerating the links and fetching matching `VoiceData.json`, run:

```powershell
node scripts/extract_voice_links.mjs `
  'F:\SteamLibrary\steamapps\common\Zenless Zone Zero\games\ZenlessZoneZero Game\ZenlessZoneZero_Data' `
  work/voice-assets zenkov

.\.venv\Scripts\python.exe -m scripts.index_voice_assets `
  --game-data 'F:\SteamLibrary\steamapps\common\Zenless Zone Zero\games\ZenlessZoneZero Game\ZenlessZoneZero_Data' `
  --links work/voice-assets/scene-links.json `
  --prefixes work/voice-assets/VoiceData.json `
  --decoder-dir work/voice-assets/vgmstream
```

The decoder is the [official vgmstream r2117 Windows x64 release](https://github.com/vgmstream/vgmstream/releases/tag/r2117),
retained with its accompanying license files. No game assets, downloaded metadata,
or decoder binaries are committed. Restart only the companion backend after
indexing. `/api/status` exposes readiness, mapped-line count, and extraction errors.

To replace existing finalized recordings where an exact original exists, run
`python -m scripts.restore_original_voice`, then refresh the web interface.
This preserves favorites and transcript text, replacing only their playback files.
Superseded loopback recordings are removed; original clips remain reproducible
from the installed game packages.

The compact unnamed-story index can also be built manually with:

```powershell
.\.venv\Scripts\python.exe -m scripts.build_story_fingerprints `
  --game-data 'F:\SteamLibrary\steamapps\common\Zenless Zone Zero\games\ZenlessZoneZero Game\ZenlessZoneZero_Data'
```

`/api/status` reports its indexed candidate count, update state, last candidate
scores, and the last accepted local asset.
