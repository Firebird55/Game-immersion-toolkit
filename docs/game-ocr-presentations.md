# Game-specific subtitle presentations

For the October 2026 installed-file inventory, unvoiced capture and update
resilience work, see the [per-game dialogue audits](game-audits/README.md).
The footage replay results below cover the specific older samples described;
they are not a full acceptance run for every newly indexed presentation.

The Steam expansion gives each game its own saved caption crop, initially
`(.04, .60, .92, .38)`. This broad lower lane retains left-aligned Source captions
and text beside character portraits; it does not apply the older centered-HUD
filter. These are adjustable starting bounds, not measurements certified for
every subtitle-size setting, scene or Windows DPI. Confirm the preview while
playing and adjust **Capture setup** if a presentation falls outside it.
Confirmed text-only choices and readables use the separate full-window exact
pass when **Include unvoiced dialogue** is enabled. Catalog eligibility, stable
observations and original-audio identity checks still apply.

The **Current line** keeps the last confirmed subtitle after it disappears from
the game. A new subtitle replaces it. The retained line stays scoped to the
selected game and current capture session. History column headings follow the
stored source/translation locales; mixed-language rows use generic headings.

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

## NTE and Honkai footage

NTE's tested movie captions, character introduction cards, normal wrapped story
dialogue and walk-and-talk captions use the lower dialogue lane. Honkai's older
right-edge visual-novel panel and newer centered visual-novel panel also use that
lane. Honkai's tested crop is `.04, .72, .96, .24`; the previous narrower crop
cut off final words. NTE's crop remains `.10, .70, .80, .28`. These games have
separate calibration and an explicit centered 16:9 picture-area option for black
bars. Existing saved calibration is preserved; use the tested-crop button to
apply the revised default.

| Source | Reviewed segments (source seconds) | Verified presentation |
| --- | --- | --- |
| [NTE Co-Ex beta PC](https://www.youtube.com/watch?v=Tbuu2k9LFyg) | 78–88, 113–123, 517–524 | Opening radio/movie captions and an explicit female player movie branch |
| Same NTE recording | 998–1004, 2395–2403, 4197–4205 | Speaker-name exclusion, wrapped dialogue and walk-and-talk |
| [NTE released PS5 footage](https://www.youtube.com/watch?v=zh_sfTZN5XI) | 143–155, 207–213 | Wrapped movie radio captions and character introduction card |
| [Honkai 2018 mobile footage](https://www.youtube.com/watch?v=eBg1v3G5bas) | 401–408, 425–435, 443–453 | Right-edge visual-novel panel and complete performances recognized through authored dialogue pages |
| [Honkai 2020 4K source recording](https://www.youtube.com/watch?v=ZIZc1STmUqo) | 238–246 | Newer centered visual-novel panel |

The annotations also require **zero entries** for NTE's upgrade menu, unmapped
upper floating status, an unconfigured movie player variant, Honkai's tutorial
bubble and battle HUD. The source images, movies, indexes and extracted voices
remain private local artifacts. The tracked manifest stores only IDs, source
links, timestamps, picture settings and expectations.

All **119 resolution cases** passed: 17 annotated segments at seven sizes,
1,932 frame evaluations and 105 accepted entries. The same 17 segments passed
at the normal four scans per second (552 frames, 17 entries); two brief movie
captions have explicitly reviewed cadence-specific expectations. After Unicode
numeral normalization changed, all five negative segments passed again at all
seven sizes (504 frames, zero entries). The ten previous Cyberpunk/Witcher/Wuthering
segments also passed at 1080p (568 frames, 33 entries). Together these are
**181 replay cases and 3,556 frame evaluations**.

All 474 NTE movie cue/variant timings fit their 35 installed original sources,
checked using the original decoder's stream sample counts. Sample fixed and
female/male movie clips and the recovered Honkai whole-page performances decoded
to nonempty original MP3s. English/Chinese synthetic fixtures passed at 720p/4K
with 75% font size. Chromium/Firefox checks passed in 24 desktop/mobile/zoom/4K
layouts, plus eight setup cases and both real WebRTC mobile pairing cases.

Resolution tests preserve each recording's aspect ratio and fit it into the
target window. They exercise 800×600, 1280×720, 1920×1080, 2560×1440, 3840×2160,
3440×1440 and 5120×1440 with the explicit centered 16:9 setting. The Honkai
centered-panel source is a 3840×2160 recording; other recordings are 720p/1080p.
Upscaling or adding bars tests OCR/crop behavior, **not native game UI reflow**.
Check live preview after changing native aspect ratio, safe zones or subtitle size.

NTE movie matching uses installed localization keys, subtitle timing and exact
original Mandarin CG sources, including explicitly selected player branches.
Honkai page matching uses the complete verified original performance. Neither
adds raw OCR, machine translation or recorded-audio fallback. Old English
rewrites without a verified catalog anchor and newer Honkai chapters remain
outside the [documented catalog coverage](nte-honkai-support.md#verified-coverage).

Native OneOCR runs on the replay images through production capture logic.
Physical crop coordinates, including negative monitor origins and DPI/preview
agreement, are covered by unit tests. This session could not validate live game
capture or Windows DPI interactively: the Windows input desktop was inaccessible
and native screen acquisition failed. Offline footage results do not imply that
live desktop preflight passed.


## Starrail Genshin Endfield

Honkai: Star Rail, Genshin Impact and Arknights: Endfield use independent bottom
dialogue crops (`.10, .70, .80, .28`). Each keeps its own calibration and player
voice choice. Short, repeated interjections are withheld when they cannot safely
identify an authored scene.

| Source | Reviewed segments (source seconds) | Expected capture |
| --- | --- | --- |
| [Star Rail opening](https://www.youtube.com/watch?v=_ZkiGS6Eug0&t=100) | 100–140 | Six opening conversation identities |
| Same Star Rail recording | 165–185 | Zero combat HUD entries |
| [Genshin opening](https://www.youtube.com/watch?v=rdEhIflJCUA&t=320) | 320–355 | Five Paimon traversal dialogue identities |
| Same Genshin recording | 195–215; 110–120 | Zero controls-menu or ambiguous movie-interjection entries |
| [Endfield opening](https://www.youtube.com/watch?v=ORNaegEfhL4&t=315) | 315–340; 370–415 | Six radio dialogue identities during the opening, combat and traversal |
| Same Endfield recording | 300–314 | Zero combat HUD entries |

All **16 cases passed**: eight independently annotated segments at both 1280×720
and 1920×1080. Each resolution produced exactly the 17 expected identities,
with no missed or unexpected entries. Native OneOCR ran on sequential frames
through production cropping, multilingual matching, confirmation, deduplication
and isolated transcript storage. English footage matched the prepared Chinese
study catalog and its official English translations.

The [annotation manifest](../backend/tests/fixtures/new-rpg-video-ocr.json)
contains provenance, timestamps and expected IDs, without game dialogue or media.
Reacquire the clips locally to reproduce the checks:

```powershell
python scripts/replay-video-ocr.py backend/tests/fixtures/new-rpg-video-ocr.json --catalog-bindings-only --resolution 1280x720 --output output/new-rpg-video-720.json
python scripts/replay-video-ocr.py backend/tests/fixtures/new-rpg-video-ocr.json --catalog-bindings-only --resolution 1920x1080 --output output/new-rpg-video-1080.json
```

Use the companion virtual environment with native OneOCR. The explicit
`--catalog-bindings-only` mode uses temporary authored voice bindings for OCR
verification; its audio sink is mocked and it does not alter prepared indexes.
Original playback separately resolves exact installed source hashes. A locally
installed Star Rail Mandarin source also decoded successfully to original MP3.
Recordings, extracted frames, catalogs, tools and playback caches remain ignored
local artifacts.

## Floating dialogue and separate panels

Persona 5 Royal, both Portal games, DEATH STRANDING and both Metal Gear Solid V games retain their calibrated lower
subtitle lane and additionally
check spatial text groups across the game window for longer original-voice
dialogue. This covers the implemented recognition path for upper navigator
bubbles, NPC balloons and tape/iDroid panels outside the lower lane. The extra pass requires an
exact, unique catalog match and at least two stable observations. It never
fuzzily searches the whole screen. Short interjections and text shared with a
confirmed silent choice or unknown UI are excluded, even when silent capture is disabled.
Independent bubbles retain independent confirmation and original voices.

The existing **Include unvoiced dialogue** control independently enables
confirmed silent choices, thoughts and messages. Unknown UI and unresolved
voice selectors remain excluded. Synthetic production-pipeline regressions
exercise separated bubbles, choice collisions, short labels and OCR errors;
they do not certify every retail layout, resolution or physical capture setup.
