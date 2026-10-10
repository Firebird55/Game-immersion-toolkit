# Game-specific subtitle presentations

The lower subtitle lane is sufficient for ordinary cutscenes, radio and most
walk-and-talk dialogue in the reviewed footage. It is insufficient for these
separate presentations:

| Game | Additional capture | Default normalized crop (left, top, width, height) |
| --- | --- | --- |
| Cyberpunk 2077 | Conversations above NPC heads | .10, .12, .70, .62 |
| The Witcher 3 | NPC chatter, including captions at the top edge | .08, 0, .76, .74 |
| Wuthering Waves | Large centered story cards on black backgrounds | .12, .20, .76, .43 |
| Wuthering Waves | Optional top-right battle/portrait messages | .58, .05, .40, .32; **off by default** |

Every region has independent per-PC calibration, preview and an enable switch
in Capture setup. Existing lower-lane and ZZZ calibrations remain intact.
Regions use physical client pixels and the existing resolution-aware OCR scale.
Where Winds Meet remains excluded because reliable original-file voice matching
is unresolved, as requested by the owner.

## Research and confirmed placement

[CD Projekt's Cyberpunk accessibility documentation](https://support.cdprojektred.com/en/cyberpunk/xbox/gameplay/issue/2659/accessibility-features-2)
distinguishes lower cinematic subtitles from overhead background conversations.
[Recorded retail gameplay](https://www.youtube.com/watch?v=x-acLmfcl5U)
confirms wrapped overhead captions around 23–30% screen height, beyond the
previous crop.

[The Witcher next-gen change list](https://www.thewitcher.com/us/en/news/47105/next-gen-update-list-of-changes)
lists separate font scaling for subtitles, NPC chatter and dialogue choices.
[Next-gen gameplay](https://www.youtube.com/watch?v=qK4gTahM18o&t=2650)
shows soldier chatter at the top edge while approaching the Nilfgaardian camp.
The moving overhead caption can reach the first few percent of screen height.
Cutscene subtitles and lower traveling conversations remain in the main crop.
Stock support does not require a mod. Dual Subtitles uses the same lower lane
and localization identities; its inline/wrapped handling is preserved.

The installed Wuthering JavaScript defines separate `PlotBattleTopRightTipsView`,
`PlotBattleTipsView`, `PlotViewGiantSubtitle` and floating-subtitle views. These
are evidence of separate presentation types, but their existence alone does
not establish screen placement or prove that a particular update uses them.
[Version 3.0 retail story footage](https://www.youtube.com/watch?v=dh3l4P31Ylg&t=8635)
confirms a centered, voiced black-screen card at approximately half screen
height. Ordinary [early-game story/exploration](https://www.youtube.com/watch?v=hknCrKujg94&t=310)
and the sampled 3.0 dialogues use the lower lane. No positive top-right voice
example was found in the reviewed clips, so that optional channel is explicitly
experimental and disabled. Unverified floating/comic layouts are not scanned
across the whole screen.

## Matching safeguards

Extra regions require a normalized exact text match, a unique original Mandarin
voice mapping, and consecutive stable sightings. Exact lookups do not run a
fuzzy search over the entire dialogue index. Independent paragraphs can match
independent NPCs. Short labels are excluded (at least 12 normalized Latin
characters or six Hanzi). Main dialogue and right-hand response menus suppress
extra-region emission. A shared original ID cannot replay from overlapping
regions within the global cooldown.

Wuthering's centered mode additionally requires a mostly black crop with a
small number of text rows. It does not indiscriminately capture ordinary HUD
or response screens. A partially occluded Witcher caption in the crafting
tutorial lacks consecutive complete sightings at the slower replay rate and
is intentionally skipped.

Short isolated words outside the observed caption band are also excluded.
At the normal 250-ms cadence, a moving Witcher herb label matched a voiced
plant name; that original ID is now an explicit negative in the replay.

Actual footage revealed that response choices and HUD labels can match original
voiced strings from unrelated scenes. The replay includes those exact problem
IDs as explicit negatives, plus Witcher Gwent UI. Unique voice ownership alone
is therefore not a sufficient screen-selection rule.

## Local verification

The native OneOCR replay uses real, sequential video frames through production
cropping, matching, stability, freshness, deduplication and isolated SQLite
storage. Only screen acquisition and the audio job sink are replaced; there
are no game launches, synthesized screenshots, recordings or account writes.

Ten annotated segments at 1080p passed (568 frames, 33 accepted lines). Six
focused segments passed again at 720p and 3840×2160 (318 frames and 16 accepted
lines each). The three new-region segments also passed at the normal four scans per second
(284 frames, eight accepted lines). Total: **1,468 frame evaluations**. Expected original IDs appeared
and the annotated choice/HUD/Gwent false positives were absent. Source footage
was acquired at 1080p: the 4K test is a resize test, not a native-4K recording.
These samples do not prove every quest, subtitle-size setting or mod appearance.
The check passed 317 Python tests, 11 JavaScript tests, type checking and the
production build. Chromium/Firefox desktop, mobile, zoom and 4K checks passed;
Witcher stock English/Chinese and inline/wrapped dual-subtitle fixtures passed
again at 720p/4K with 75% font size.

The installed original files for the newly exercised Cyberpunk overhead,
Witcher chatter and Wuthering card IDs decoded to non-silent 4.13-, 15.89- and
4.30-second clips. Native screen/OCR preflight passed. Offline tests also cover
unmapped/fuzzy/short/unpositioned text, blank-frame confirmation reset, disabled
channels, main-dialogue priority and black-card/menu rejection.

Media, extracted original audio and runtime reports remain ignored local
artifacts. The tracked [annotation manifest](../backend/tests/fixtures/game-video-ocr.json)
contains only provenance, relative local paths and test IDs. Reacquire the
listed clips from their recording owners to reproduce the replay; do not add
game assets or videos to the repository.

```powershell
python scripts/replay-video-ocr.py backend/tests/fixtures/game-video-ocr.json --resolution 1920x1080 --output output/video-ocr-1080.json
python scripts/replay-video-ocr.py backend/tests/fixtures/game-video-ocr.json --resolution 3840x2160 --output output/video-ocr-4k.json
```

The default replay samples two frames per second. `--fps 4` tests consecutive
frames at the companion's default 250-ms cadence. Use the installed companion
virtual environment with native OneOCR and the owner's Mandarin indexes.
