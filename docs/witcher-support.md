# The Witcher 3, with or without Dual Subtitles

Stock **English or Simplified Chinese subtitles** work without a mod. The toolkit
matches them to the official bilingual text and extracts the corresponding
original Mandarin voice from the installed `cnpc.w3speech` container. DX11 and
DX12 use the same game profile. Choose the installation root in **Choose Game
Folders.cmd**, or use automatic Steam-library discovery.

The official Chinese voice pack must be installed through Steam. On this PC,
the completed installation provides 96,904 English/Chinese pairs and 64,720
original Mandarin voice mappings. It includes no installed playable expansion
directory; language files under `dlc` are indexed when present. The toolkit does
not acquire DLC or voice assets from elsewhere.

The linked [Dual Subtitles mod](https://www.nexusmods.com/witcher3/mods/8282)
combines two texts with ` ~ ` or `<br>~ ` according to the length of the primary
text. Its [author's script](https://github.com/maximumspoil/witcher3dualsubtitles/blob/main/dual_subtitles.py)
preserves localization IDs and the primary text. The toolkit handles Chinese
above/beside English, English above/beside Chinese, wrapped rows, and a leading
tilde on the translation row. Both halves resolve to one original subtitle ID.
Set the mod's language pair to English and Chinese for this study workflow.

Indexing reads the primary language from current installed files, rather than
depending on mod backups that may have become stale after Steam updates. Only
unambiguous English/Chinese components are accepted. The toolkit does not run
the mod installer, encode localization files, or change the game installation.

Local format readers support current version-164 UTF-8 localization and older
version-162/163 UTF-16 localization, including a measured UTF-8 buffer in an
older-version mod container. Original audio joins the same localization ID in
the CPSW speech table. Audio offsets preserve all 64 bits; playback reads only
the mapped RIFF payload and uses the existing vgmstream/FFmpeg decoder.
Unvoiced UI strings and repeated text with different performances are excluded.
Malformed or interrupted updates preserve the previous usable snapshot.

Format behavior was reviewed against the primary implementations in
[Witcher3StringEditor](https://github.com/0x7A2C9E5D/Witcher3StringEditor) and
[Lua-utils-for-Witcher-3](https://github.com/hhrhhr/Lua-utils-for-Witcher-3).
No additional Witcher extractor executable or online service is needed.

## Verification

The installed original Mandarin clip `witcher3:1185695` decoded to a non-silent
3.55-second MP3. An additional clip beyond the container's four-GiB boundary
also decoded successfully. English and Chinese matches resolved to the same
original speech identities.

Synthetic 3840 × 2160 screenshot fixtures passed through production cropping,
native Windows OCR, matching, stability, and strict voice gating for stock
English, stock Chinese, inline dual subtitles, and wrapped dual subtitles.
The corresponding Cyberpunk stock-English, stock-Chinese, and bilingual checks
also passed. The mod is optional in both games. Actual gameplay and the installed
mod's appearance remain untested because no game was launched.

The complete check passes 275 Python tests, 11 JavaScript tests, type checking,
and the production build. Chromium and Firefox passed 24 desktop/mobile/zoom
contexts, followed by eight checks of the final game status UI at 320 pixels
and 4K with 100%, 150%, and 200% scaling. Native Windows OCR and display capture
bounds also passed the preflight check.

Run `python scripts/check-subtitle-screenshots.py --fixtures` using the configured
Windows virtual environment to recreate the offline screenshots, or pass
`--game witcher3 --image "C:\path\screenshot.png"` to inspect existing screenshots
without starting a game. Test captures use isolated output databases rather
than the user's transcript history.
